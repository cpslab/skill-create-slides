"""配布検査の挙動を小さい合成配布物で確かめる。実研究は使わない。"""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_package.py"
SPEC = importlib.util.spec_from_file_location("check_package", MODULE_PATH)
package_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package_check)


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "SKILL.md").write_text('---\nname: fictional-test\nmetadata:\n  version: "1.5.0"\n---\n# Title\n')
        (self.root / "README.md").write_text("現在のスキル版は **1.5.0** です。\n[Guide](references/guide.md#日本語の節)\n")
        (self.root / "AGENTS.md").write_text("# Rules\n")
        (self.root / "references").mkdir()
        (self.root / "references/guide.md").write_text("# 日本語の節\n")
        (self.root / "package-manifest.json").write_text(json.dumps({
            "version": "1.4.0", "packaged_on": "2000-01-01",
            "visual_example": {"actual_review": "historical"}, "files": {}
        }))

    def tearDown(self):
        self.temp.cleanup()

    def test_refresh_preserves_history_and_current_hashes(self):
        result = package_check.check(self.root, refresh=True)
        self.assertEqual(result["status"], "pass")
        manifest = json.loads((self.root / "package-manifest.json").read_text())
        self.assertEqual(manifest["version"], "1.5.0")
        self.assertEqual(manifest["packaged_on"], "2000-01-01")
        self.assertEqual(manifest["visual_example"], {"actual_review": "historical"})
        self.assertIn("AGENTS.md", manifest["files"])
        self.assertNotIn("package-manifest.json", manifest["files"])
        self.assertEqual(package_check.check(self.root)["status"], "pass")
        (self.root / "AGENTS.md").write_text("# Changed\n")
        self.assertIn("hash_or_size", {x["code"] for x in package_check.check(self.root)["issues"]})

    def test_bad_link_and_version_do_not_refresh(self):
        manifest_before = (self.root / "package-manifest.json").read_bytes()
        (self.root / "README.md").write_text("現在のスキル版は **9.0.0** です。\n[missing](references/guide.md#absent)")
        result = package_check.check(self.root, refresh=True)
        self.assertTrue({"version_sources", "missing_anchor"}.issubset({x["code"] for x in result["issues"]}))
        self.assertEqual((self.root / "package-manifest.json").read_bytes(), manifest_before)

    def test_missing_and_escaping_links_are_detected(self):
        (self.root / "references/guide.md").write_text("[missing](absent.md)\n[outside](../../other.md)\n")
        codes = {x["code"] for x in package_check.check(self.root)["issues"]}
        self.assertTrue({"missing_link", "outside_link"}.issubset(codes))

    def test_hidden_files_and_bytecode_are_excluded(self):
        (self.root / "scripts").mkdir()
        cache = self.root / "scripts" / "__pycache__"
        cache.mkdir()
        (cache / "ignored.py").write_text("ignored")
        (self.root / "scripts/.DS_Store").write_text("ignored")
        (self.root / "scripts/ok.py").write_text("print('ok')\n")
        (self.root / "scripts/render.applescript").write_text('return "fixture"\n')
        files, issues = package_check.inventory(self.root)
        self.assertFalse(issues)
        self.assertIn("scripts/ok.py", files)
        self.assertIn("scripts/render.applescript", files)
        self.assertNotIn("scripts/__pycache__/ignored.py", files)

    def test_private_paths_in_sources_and_pptx_xml_are_detected(self):
        # Construct fixture values so the distributed test file contains no personal path.
        private = "/" + "Users" + "/" + "example-person" + "/private/input"
        (self.root / "references/guide.md").write_text(private)
        (self.root / "assets").mkdir()
        with zipfile.ZipFile(self.root / "assets/example.pptx", "w") as archive:
            archive.writestr("docProps/core.xml", "<source>" + private + "</source>")
        found = [x for x in package_check.check(self.root)["issues"] if x["code"] == "personal_absolute_path"]
        self.assertEqual(len(found), 2)
        self.assertTrue(any("!docProps/core.xml" in x["path"] for x in found))

    def test_relative_module_import_and_symlink(self):
        (self.root / "scripts").mkdir()
        (self.root / "scripts/main.mjs").write_text("import {a} from './missing.mjs';\n")
        (self.root / "scripts/link.py").symlink_to(self.root / "AGENTS.md")
        codes = {x["code"] for x in package_check.check(self.root)["issues"]}
        self.assertTrue({"missing_link", "symlink"}.issubset(codes))


if __name__ == "__main__":
    unittest.main()
