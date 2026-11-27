"""制作記録の初期化と既存正本の保護を、一時作業先で確かめる。"""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "init_presentation.py"


class InitPresentationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / "presentation"

    def tearDown(self):
        self.temp.cleanup()

    def initialise(self, title="架空研究の発表"):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--project-dir", str(self.project),
             "--title", title],
            capture_output=True, text=True, check=False,
        )

    def test_new_record_is_markdown_without_other_documents(self):
        result = self.initialise()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([p.name for p in self.project.iterdir()], ["workflow.md"])
        content = (self.project / "workflow.md").read_text()
        self.assertIn("# ", content)
        self.assertIn("架空研究の発表", content)
        self.assertNotIn("{{TITLE}}", content)
        self.assertNotIn("{{DATE}}", content)

    def test_plain_title_characters_are_not_html_or_markdown_markup(self):
        result = self.initialise("A <sample> & [controls] *literal*")
        self.assertEqual(result.returncode, 0, result.stderr)
        heading = (self.project / "workflow.md").read_text().splitlines()[0]
        self.assertEqual(heading, r"# A &lt;sample&gt; &amp; \[controls\] \*literal\* 制作記録")

    def test_existing_markdown_or_org_record_is_preserved(self):
        self.project.mkdir()
        for name in ("workflow.md", "workflow.org"):
            with self.subTest(name=name):
                record = self.project / name
                record.write_text("User decisions and additions")
                result = self.initialise()
                self.assertEqual(result.returncode, 2)
                self.assertIn(name, result.stderr)
                self.assertEqual(record.read_text(), "User decisions and additions")
                self.assertEqual([p.name for p in self.project.iterdir()], [name])
                record.unlink()

    def test_both_existing_formats_are_not_changed(self):
        self.project.mkdir()
        for name in ("workflow.md", "workflow.org"):
            (self.project / name).write_text(name)
        self.assertEqual(self.initialise().returncode, 2)
        for name in ("workflow.md", "workflow.org"):
            self.assertEqual((self.project / name).read_text(), name)

    def test_workflow_links_in_either_format_are_not_followed(self):
        self.project.mkdir()
        sentinel = self.root / "sentinel.md"
        sentinel.write_text("Keep this original")
        for name in ("workflow.md", "workflow.org"):
            for destination in (sentinel, self.root / "missing.md"):
                with self.subTest(name=name, destination=destination.name):
                    link = self.project / name
                    link.symlink_to(destination)
                    result = self.initialise()
                    self.assertEqual(result.returncode, 2)
                    self.assertTrue(link.is_symlink())
                    self.assertEqual(sentinel.read_text(), "Keep this original")
                    self.assertFalse((self.root / "missing.md").exists())
                    link.unlink()


if __name__ == "__main__":
    unittest.main()
