"""Portable rendering failure boundaries; synthetic files are not visual-review evidence."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import doctor
import render_portable as renderer


class ExportProcessTests(unittest.TestCase):
    def test_timeout_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "timed out"):
            renderer.run_export([sys.executable, "-c", "import time;time.sleep(30)"], 0.05)

    def test_nonzero_export_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "export failed"):
            renderer.run_export([sys.executable, "-c", "raise SystemExit(2)"], 3)

    def test_missing_explicit_soffice_does_not_fall_back(self):
        with patch("render_portable.shutil.which", return_value=None):
            with self.assertRaisesRegex(ValueError, "Configured SOFFICE"):
                renderer.find_soffice("intentionally-missing-soffice")


@unittest.skipUnless(importlib.util.find_spec("pymupdf") and importlib.util.find_spec("PIL"),
                     "Install the project Python dependencies for render tests.")
class RenderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "fixture.pptx"
        self.output = self.root / "render"
        with zipfile.ZipFile(self.source, "w") as archive:
            archive.writestr("ppt/presentation.xml",
                '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
                '<p:sldIdLst><p:sldId id="256"/><p:sldId id="257"/></p:sldIdLst></p:presentation>')

    def tearDown(self):
        self.temporary.cleanup()

    def exporter(self, count=2, mutate=False):
        def export(command, timeout):
            import pymupdf
            snapshot = Path(command[-1])
            self.assertNotEqual(snapshot, self.source)
            self.assertEqual(renderer.sha256(snapshot), renderer.sha256(self.source))
            self.assertTrue(any(arg.startswith("-env:UserInstallation=file:") for arg in command))
            options = command[command.index("--convert-to") + 1]
            self.assertEqual(json.loads(options.split(":", 2)[2])
                             ["ExportHiddenSlides"]["value"], "true")
            with pymupdf.open() as pdf:
                for _ in range(count):
                    page = pdf.new_page(width=720, height=405)
                    page.insert_text((40, 40), "Synthetic render fixture")
                pdf.save(self.output / "candidate.pdf")
            if mutate:
                self.source.write_bytes(self.source.read_bytes() + b"changed")
            return {"command": command, "exit_code": 0, "stdout": "", "stderr": ""}
        return export

    def render_with(self, exporter):
        with patch("render_portable.find_soffice", return_value="fixture-soffice"), \
             patch("render_portable.run_export", side_effect=exporter), \
             patch("render_portable.subprocess.run") as version:
            version.return_value.stdout = "Synthetic renderer"
            version.return_value.stderr = ""
            return renderer.render(self.source, self.output, dpi=72)

    def test_records_final_file_and_all_page_hashes_without_claiming_review(self):
        record = self.render_with(self.exporter())
        self.assertEqual(record["pptx_sha256"], renderer.sha256(self.source))
        self.assertEqual(record["pdf"]["source_binding"], renderer.sha256(self.source))
        self.assertEqual(record["pdf"]["sha256"], renderer.sha256(self.output / "candidate.pdf"))
        self.assertEqual([page["number"] for page in record["pages"]], [1, 2])
        for page in record["pages"]:
            self.assertEqual(page["status"], "unverified")
            self.assertEqual(page["image_sha256"], renderer.sha256(self.output / page["image"]))
        self.assertEqual(record["visual_review"]["status"], "unverified")
        self.assertTrue((self.output / "contact-sheet.png").is_file())

    def test_refuses_existing_directory_and_preserves_its_contents(self):
        self.output.mkdir()
        (self.output / "render-record.json").write_text("preserve")
        with self.assertRaises(FileExistsError):
            self.render_with(self.exporter())
        self.assertEqual((self.output / "render-record.json").read_text(), "preserve")

    def test_export_success_without_pdf_is_failure(self):
        with self.assertRaisesRegex(ValueError, "without creating"):
            self.render_with(lambda *args: {"exit_code": 0, "stdout": "", "stderr": ""})
        self.assertFalse((self.output / "render-record.json").exists())
        self.assertEqual(json.loads((self.output / "render-error.json").read_text())["status"], "error")

    def test_page_count_mismatch_is_failure(self):
        with self.assertRaisesRegex(ValueError, "page count"):
            self.render_with(self.exporter(count=1))
        self.assertFalse((self.output / "render-record.json").exists())

    def test_source_changed_during_export_is_failure(self):
        with self.assertRaisesRegex(ValueError, "changed during"):
            self.render_with(self.exporter(mutate=True))
        self.assertFalse((self.output / "render-record.json").exists())

    def test_powerpoint_requires_unchanged_open_and_all_slide_read_receipt(self):
        def export(command, timeout):
            import pymupdf
            snapshot, output = Path(command[-2]), Path(command[-1])
            self.assertEqual(renderer.sha256(snapshot), renderer.sha256(self.source))
            with pymupdf.open() as pdf:
                for _ in range(2):
                    pdf.new_page(width=720, height=405)
                pdf.save(output)
            return {"command": command, "exit_code": 0,
                    "stdout": "fixture-version|2|saved=true|slides_read=2", "stderr": ""}
        with patch("render_portable.platform.system", return_value="Darwin"), \
             patch("render_portable.run_export", side_effect=export):
            record = renderer.render(self.source, self.output, renderer="powerpoint", dpi=72)
        self.assertEqual(record['application_open_verification']['slides_read'], 2)
        self.assertFalse(record['application_open_verification']['repair_action_sent'])
        self.assertEqual(record['visual_review']['status'], 'unverified')

    def test_powerpoint_count_only_receipt_does_not_prove_normal_open(self):
        for stdout in ['fixture-version|2', 'fixture-version|2|saved=false|slides_read=2',
                       'fixture-version|2|saved=true|slides_read=1']:
            with self.subTest(stdout=stdout), \
                 tempfile.TemporaryDirectory() as temporary, \
                 patch("render_portable.platform.system", return_value="Darwin"), \
                 patch("render_portable.run_export", return_value={
                     "exit_code": 0, "stdout": stdout, "stderr": ""}):
                with self.assertRaisesRegex(ValueError, 'unchanged normal open'):
                    renderer.render(self.source, Path(temporary) / 'render', renderer='powerpoint')


class DoctorTests(unittest.TestCase):
    def environment(self, fonts="pass"):
        with patch("doctor.shutil.which", return_value="/tool"), \
             patch("doctor.run", return_value={"status": "pass", "output": "v22.0.0"}), \
             patch("doctor.module_report", return_value={"status": "pass"}), \
             patch("doctor.font_report", return_value={"status": fonts, "files": []}), \
             patch("doctor.find_soffice", return_value="/soffice"):
            return doctor.inspect_environment()

    def test_image_provider_is_not_a_required_prerequisite(self):
        with patch.dict(os.environ, {}, clear=True):
            report = self.environment()
        self.assertTrue(report["ready_for_generation_and_rendering"])
        self.assertEqual(report["capabilities"]["image_generation"]["status"], "unverified")
        self.assertEqual(report["capabilities"]["all_page_visual_review"]["status"], "unverified")

    def test_missing_font_prevents_readiness(self):
        report = self.environment(fonts="unavailable")
        self.assertFalse(report["ready_for_generation_and_rendering"])
        self.assertEqual(report["required_checks"]["fonts"], "unavailable")

    def test_windows_per_user_font_directory_is_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            font = Path(temporary) / "Microsoft/Windows/Fonts/FixtureFont-Regular.ttf"
            font.parent.mkdir(parents=True)
            font.write_bytes(b"font presence fixture")
            with patch.dict(os.environ, {"LOCALAPPDATA": temporary}), \
                 patch("doctor.shutil.which", return_value=None):
                report = doctor.font_report("Fixture Font")
            self.assertEqual(report["status"], "pass")
            self.assertIn(str(font), [item["path"] for item in report["files"]])


if __name__ == "__main__":
    unittest.main()
