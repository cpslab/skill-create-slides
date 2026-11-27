"""架空の固定入力で、PowerPoint の修復につながる既知の OOXML 違反を検査する。"""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from xml.sax.saxutils import quoteattr
import zipfile

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from check_pptx import inspect

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
C = "http://schemas.openxmlformats.org/drawingml/2006/chart"


def fixture_parts(slide_xml=None, presentation_children=None, content_types=None):
    """Small independent package; only targeted compatibility constraints apply.

    Deliberately omit unrelated mandatory OOXML detail: this test must not make
    the lightweight checker promise complete schema or application validation.
    """
    if presentation_children is None:
        presentation_children = '<p:sldIdLst><p:sldId id="256" r:id="s1"/></p:sldIdLst>'
    if slide_xml is None:
        slide_xml = f'<p:sld xmlns:p="{P}" xmlns:a="{A}"><p:cSld><p:spTree/></p:cSld></p:sld>'
    if content_types is None:
        content_types = (
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
            '<Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        )
    return {
        "[Content_Types].xml": f'<Types xmlns="{CT}">{content_types}</Types>',
        "_rels/.rels": f'<Relationships xmlns="{RELS}"><Relationship Id="root" Type="{R}/officeDocument" Target="ppt/presentation.xml"/></Relationships>',
        "ppt/presentation.xml": f'<p:presentation xmlns:p="{P}" xmlns:r="{R}">{presentation_children}</p:presentation>',
        "ppt/_rels/presentation.xml.rels": f'<Relationships xmlns="{RELS}"><Relationship Id="s1" Type="{R}/slide" Target="slides/slide1.xml"/></Relationships>',
        "ppt/slides/slide1.xml": slide_xml,
    }


class OoxmlCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "fictional.pptx"

    def tearDown(self):
        self.temp.cleanup()

    def write(self, parts):
        with zipfile.ZipFile(self.path, "w") as archive:
            for name, content in parts.items():
                archive.writestr(name, content)

    def errors(self, parts):
        self.write(parts)
        return inspect(self.path)["errors"]

    def test_valid_package_does_not_require_unrelated_schema_details(self):
        self.assertEqual(self.errors(fixture_parts()), [])

    def test_all_schema_text_anchor_values_and_default_pass(self):
        for anchor in (None, "t", "ctr", "b", "just", "dist", "  ctr  "):
            attribute = "" if anchor is None else " anchor=" + quoteattr(anchor)
            for local in ("bodyPr", "tcPr"):
                parts = fixture_parts()
                parts["ppt/notesSlides/notesSlide1.xml"] = (
                    f'<p:notes xmlns:p="{P}" xmlns:a="{A}"><a:{local}{attribute}/></p:notes>'
                )
                self.assertEqual(self.errors(parts), [], (local, anchor))

    def test_invalid_table_and_text_anchors_report_part_and_property(self):
        parts = fixture_parts(
            slide_xml=f'<p:sld xmlns:p="{P}" xmlns:a="{A}"><a:bodyPr anchor="center"/><a:tcPr anchor="mid"/></p:sld>'
        )
        errors = self.errors(parts)
        self.assertEqual(len(errors), 2)
        self.assertTrue(any("a:bodyPr[1] anchor='center'" in error for error in errors))
        self.assertTrue(any("a:tcPr[1] anchor='mid'" in error for error in errors))
        self.assertTrue(all("ppt/slides/slide1.xml" in error for error in errors))

    def test_non_xml_whitespace_does_not_mask_invalid_anchor(self):
        parts = fixture_parts(slide_xml=f'<p:sld xmlns:p="{P}" xmlns:a="{A}"><a:tcPr anchor="&#160;ctr"/></p:sld>')
        errors = self.errors(parts)
        self.assertEqual(len(errors), 1)
        self.assertIn("Invalid DrawingML text anchor", errors[0])

    def test_anchor_checks_cover_non_slide_parts_and_exact_namespace(self):
        parts = fixture_parts()
        parts["ppt/slideMasters/slideMaster1.xml"] = (
            f'<p:sldMaster xmlns:p="{P}" xmlns:a="{A}" xmlns:other="urn:fictional">'
            '<a:bodyPr anchor="mid"/><other:bodyPr anchor="mid"/>'
            '<other:tcPr anchor="mid"/><a:other anchor="mid"/></p:sldMaster>'
        )
        errors = self.errors(parts)
        self.assertEqual(len(errors), 1)
        self.assertIn("ppt/slideMasters/slideMaster1.xml", errors[0])

    def test_ordered_presentation_children_and_extension_namespace_pass(self):
        children = (
            "<p:sldMasterIdLst/><p:notesMasterIdLst/><p:handoutMasterIdLst/>"
            '<p:sldIdLst><p:sldId id="256" r:id="s1"/></p:sldIdLst>'
            "<p:sldSz/><p:notesSz/><p:smartTags/><p:embeddedFontLst/>"
            "<p:custShowLst/><p:photoAlbum/><p:custDataLst/><p:kinsoku/>"
            '<foreign:notesMasterIdLst xmlns:foreign="urn:fictional"/>'
            "<p:defaultTextStyle/><p:modifyVerifier/><p:extLst/>"
        )
        self.assertEqual(self.errors(fixture_parts(presentation_children=children)), [])

    def test_notes_master_after_slide_list_is_rejected(self):
        children = (
            '<p:sldIdLst><p:sldId id="256" r:id="s1"/></p:sldIdLst>'
            "<p:notesMasterIdLst/><p:sldSz/><p:notesSz/>"
        )
        errors = self.errors(fixture_parts(presentation_children=children))
        self.assertEqual(len(errors), 1)
        self.assertIn("Invalid presentation child order: ppt/presentation.xml", errors[0])
        self.assertIn("p:notesMasterIdLst must precede p:sldIdLst", errors[0])

    def test_later_sequence_violation_is_also_rejected(self):
        children = (
            '<p:sldIdLst><p:sldId id="256" r:id="s1"/></p:sldIdLst>'
            "<p:notesSz/><p:sldSz/>"
        )
        errors = self.errors(fixture_parts(presentation_children=children))
        self.assertTrue(any("p:sldSz must precede p:notesSz" in error for error in errors))

    def test_duplicate_presentation_singleton_is_rejected(self):
        children = (
            "<p:notesMasterIdLst/><p:notesMasterIdLst/>"
            '<p:sldIdLst><p:sldId id="256" r:id="s1"/></p:sldIdLst>'
        )
        errors = self.errors(fixture_parts(presentation_children=children))
        self.assertEqual(len(errors), 1)
        self.assertIn("Duplicate presentation child: ppt/presentation.xml: p:notesMasterIdLst", errors[0])

    def test_stale_content_type_override_is_rejected(self):
        parts = fixture_parts()
        parts["[Content_Types].xml"] = parts["[Content_Types].xml"].replace(
            "</Types>", '<Override PartName="/ppt/slideMasters/slideMaster2.xml" ContentType="application/xml"/></Types>'
        )
        errors = self.errors(parts)
        self.assertEqual(len(errors), 1)
        self.assertIn("Missing content type override target: [Content_Types].xml", errors[0])
        self.assertIn("/ppt/slideMasters/slideMaster2.xml", errors[0])

    def test_encoded_existing_override_target_passes(self):
        parts = fixture_parts()
        parts["customXml/fictional note.xml"] = "<root/>"
        parts["[Content_Types].xml"] = parts["[Content_Types].xml"].replace(
            "</Types>", '<Override PartName="/customXml/fictional%20note.xml" ContentType="application/xml"/></Types>'
        )
        self.assertEqual(self.errors(parts), [])

    def test_duplicate_content_type_entries_are_rejected(self):
        parts = fixture_parts()
        parts["[Content_Types].xml"] = parts["[Content_Types].xml"].replace(
            "</Types>", '<Default Extension="XML" ContentType="application/xml"/>'
            '<Override PartName="/ppt/presentation.xml" ContentType="application/xml"/></Types>'
        )
        errors = self.errors(parts)
        self.assertEqual(len(errors), 2)
        self.assertTrue(any("Duplicate content type default" in error for error in errors))
        self.assertTrue(any("Duplicate content type override" in error for error in errors))

    def test_two_dimensional_bar_and_line_reject_extra_axis_reference(self):
        for chart_type in ("barChart", "lineChart"):
            with self.subTest(chart_type=chart_type):
                parts = fixture_parts()
                parts["ppt/charts/chart1.xml"] = (
                    f'<c:chartSpace xmlns:c="{C}"><c:chart><c:plotArea>'
                    f'<c:{chart_type}><c:axId val="10"/><c:axId val="20"/>'
                    f'<c:axId val="30"/></c:{chart_type}>'
                    '</c:plotArea></c:chart></c:chartSpace>'
                )
                errors = self.errors(parts)
                self.assertEqual(len(errors), 1)
                self.assertIn("Too many 2D chart axis references: ppt/charts/chart1.xml", errors[0])
                self.assertIn(f"c:{chart_type}[1] has 3 c:axId children", errors[0])

    def test_two_dimensional_combination_chart_counts_each_type_separately(self):
        parts = fixture_parts()
        parts["ppt/charts/chart1.xml"] = (
            f'<c:chartSpace xmlns:c="{C}"><c:chart><c:plotArea>'
            '<c:barChart><c:axId val="10"/><c:axId val="20"/></c:barChart>'
            '<c:lineChart><c:axId val="10"/><c:axId val="20"/></c:lineChart>'
            '</c:plotArea></c:chart></c:chartSpace>'
        )
        self.assertEqual(self.errors(parts), [])

    def test_three_dimensional_and_extension_charts_can_have_three_axes(self):
        for chart_type, namespace in (
            ("bar3DChart", C), ("line3DChart", C), ("barChart", "urn:fictional"),
        ):
            with self.subTest(chart_type=chart_type, namespace=namespace):
                parts = fixture_parts()
                parts["ppt/charts/chart1.xml"] = (
                    f'<root xmlns:c="{C}" xmlns:chart="{namespace}">'
                    f'<chart:{chart_type}><c:axId val="10"/><c:axId val="20"/>'
                    f'<c:axId val="30"/></chart:{chart_type}></root>'
                )
                self.assertEqual(self.errors(parts), [])

    def theme_parts(self, notes_theme="theme2.xml", presentation_theme=True, slide_master_theme=True):
        parts = fixture_parts()
        theme = f'<a:theme xmlns:a="{A}" name="Fictional theme"/>'
        parts["ppt/theme/theme1.xml"] = theme
        parts["ppt/theme/theme2.xml"] = theme
        parts["ppt/notesMasters/notesMaster1.xml"] = f'<p:notesMaster xmlns:p="{P}"/>'
        parts["ppt/notesMasters/_rels/notesMaster1.xml.rels"] = (
            f'<Relationships xmlns="{RELS}"><Relationship Id="theme" Type="{R}/theme" Target="../theme/{notes_theme}"/></Relationships>'
        )
        if presentation_theme:
            parts["ppt/_rels/presentation.xml.rels"] = parts["ppt/_rels/presentation.xml.rels"].replace(
                "</Relationships>", f'<Relationship Id="theme" Type="{R}/theme" Target="theme/theme1.xml"/></Relationships>'
            )
        if slide_master_theme:
            parts["ppt/slideMasters/slideMaster1.xml"] = f'<p:sldMaster xmlns:p="{P}"/>'
            parts["ppt/slideMasters/_rels/slideMaster1.xml.rels"] = (
                f'<Relationships xmlns="{RELS}"><Relationship Id="theme" Type="{R}/theme" Target="../theme/theme1.xml"/></Relationships>'
            )
        return parts

    def test_notes_master_shared_theme_is_powerpoint_compatibility_error(self):
        for presentation, slide_master in ((True, False), (False, True), (True, True)):
            with self.subTest(presentation=presentation, slide_master=slide_master):
                errors = self.errors(self.theme_parts("theme1.xml", presentation, slide_master))
                self.assertEqual(len(errors), 1)
                self.assertIn("PowerPoint notes-master theme sharing: ppt/notesMasters/notesMaster1.xml", errors[0])
                self.assertIn("ppt/theme/theme1.xml", errors[0])

    def test_separate_byte_identical_notes_theme_allows_normal_slide_theme_sharing(self):
        # Same contents are safe: part identity, not theme bytes, is the issue.
        parts = self.theme_parts()
        self.assertEqual(parts["ppt/theme/theme1.xml"], parts["ppt/theme/theme2.xml"])
        self.assertEqual(self.errors(parts), [])

    def test_notes_master_can_be_the_only_owner_of_theme1(self):
        self.assertEqual(self.errors(self.theme_parts("theme1.xml", False, False)), [])

    def test_handout_master_theme_sharing_uses_preventive_normalization_policy(self):
        # Synthetic policy test; this is not an additional PowerPoint app test.
        for theme_name, expected_errors in (("theme1.xml", 1), ("theme2.xml", 0)):
            with self.subTest(theme_name=theme_name):
                notes_parts = self.theme_parts(theme_name)
                parts = {
                    name.replace("notesMasters", "handoutMasters").replace("notesMaster", "handoutMaster"):
                    content.replace("notesMaster", "handoutMaster")
                    for name, content in notes_parts.items()
                }
                errors = self.errors(parts)
                self.assertEqual(len(errors), expected_errors)
                if errors:
                    self.assertIn("PowerPoint handout-master theme sharing", errors[0])

    def test_cli_fails_known_defect_and_accepts_corrected_value(self):
        parts = fixture_parts(slide_xml=f'<p:sld xmlns:p="{P}" xmlns:a="{A}"><a:tcPr anchor="mid"/></p:sld>')
        self.write(parts)
        bad = subprocess.run([sys.executable, str(SCRIPTS / "check_pptx.py"), str(self.path)], capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("anchor='mid'", json.loads(bad.stdout)["errors"][0])
        parts["ppt/slides/slide1.xml"] = parts["ppt/slides/slide1.xml"].replace('anchor="mid"', 'anchor="ctr"')
        self.write(parts)
        good = subprocess.run([sys.executable, str(SCRIPTS / "check_pptx.py"), str(self.path)], capture_output=True, text=True)
        self.assertEqual(good.returncode, 0)
        self.assertEqual(json.loads(good.stdout)["errors"], [])


if __name__ == "__main__":
    unittest.main()
