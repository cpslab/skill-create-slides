"""Narrow compatibility repair uses fictional inputs and preserves authored bytes."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from repair_pptx_compat import normalise_parts, repair

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
ROOT = Path(__file__).resolve().parents[1]


def fixture_parts():
    parts = {
        "[Content_Types].xml": f'''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="{CT}"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/>
<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
<Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
<Override PartName="/ppt/notesMasters/notesMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesMaster+xml"/>
<Override PartName="/ppt/notesSlides/notesSlide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"/>
<Override PartName="/ppt/slideLayouts/unused.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/></Types>''',
        "_rels/.rels": f'<Relationships xmlns="{REL}"><Relationship Id="root" Type="{R}/officeDocument" Target="ppt/presentation.xml"/></Relationships>',
        "ppt/presentation.xml": f'''<p:presentation xmlns:p="{P}" xmlns:r="{R}" xmlns:a="{A}">
<p:sldIdLst><p:sldId id="314" r:id="slide"/></p:sldIdLst>
<p:sldSz cx="9144000" cy="5143500"/>
<p:notesSz cx="6858000" cy="9144000"/>
<p:notesMasterIdLst><p:notesMasterId r:id="notesMaster"/></p:notesMasterIdLst>
<p:defaultTextStyle><a:defPPr/></p:defaultTextStyle></p:presentation>''',
        "ppt/_rels/presentation.xml.rels": f'<Relationships xmlns="{REL}"><Relationship Id="slide" Type="{R}/slide" Target="slides/slide1.xml"/><Relationship Id="notesMaster" Type="{R}/notesMaster" Target="notesMasters/notesMaster1.xml"/></Relationships>',
        "ppt/slides/slide1.xml": f'''<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}" xmlns:review="urn:fictional:review" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><p:cSld><p:spTree>
<p:sp><p:nvSpPr><p:cNvPr id="83" name="Manually edited title"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>架空研究 — Preserve &amp; edit</a:t></a:r></a:p></p:txBody></p:sp>
<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="122" name="Edited table"/></p:nvGraphicFramePr><p:xfrm/><a:graphic><a:graphicData><a:tbl><a:tblGrid><a:gridCol w="900000"/></a:tblGrid><a:tr h="400000"><a:tc><a:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>Original cell</a:t></a:r></a:p></a:txBody><a:tcPr anchor = 'mid' marL="100"/></a:tc></a:tr></a:tbl></a:graphicData></a:graphic></p:graphicFrame>
<p:pic><p:nvPicPr><p:cNvPr id="405" name="Original evidence crop"/></p:nvPicPr><p:blipFill><a:blip r:embed="image"/><a:srcRect l="4200" r="1900"/></p:blipFill><p:spPr/></p:pic>
</p:spTree></p:cSld><p:extLst><p:ext uri="urn:fixture"><review:data xsi:type="review:Type">Keep extension and namespaces</review:data></p:ext></p:extLst></p:sld>''',
        "ppt/slides/_rels/slide1.xml.rels": f'<Relationships xmlns="{REL}"><Relationship Id="image" Type="{R}/image" Target="../media/evidence.png"/><Relationship Id="notes" Type="{R}/notesSlide" Target="../notesSlides/notesSlide1.xml"/></Relationships>',
        "ppt/notesMasters/notesMaster1.xml": f'<p:notesMaster xmlns:p="{P}"><p:cSld/></p:notesMaster>',
        "ppt/notesSlides/notesSlide1.xml": f'<p:notes xmlns:p="{P}" xmlns:a="{A}"><p:cSld><p:spTree><p:sp><p:nvSpPr><p:cNvPr id="77" name="My notes"/></p:nvSpPr><p:txBody><a:p><a:r><a:t>Hand-edited spoken notes.</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:notes>',
        "ppt/media/evidence.png": b"fictional unchanged binary image payload\x00\xff",
    }
    return {name: value.encode("utf-8") if isinstance(value, str) else value for name, value in parts.items()}


class CompatibilityRepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.source = self.directory / "original.pptx"
        self.output = self.directory / "repaired.pptx"
        self.report_path = self.directory / "repair.json"
        self.parts = fixture_parts()
        self.write()

    def tearDown(self):
        self.temp.cleanup()

    def write(self):
        with zipfile.ZipFile(self.source, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.comment = b"Keep original ZIP comment"
            for name, data in self.parts.items():
                archive.writestr(name, data)

    def test_three_repairs_preserve_original_and_all_other_content(self):
        before = self.source.read_bytes()
        report = repair(self.source, self.output, self.report_path)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(report["input_sha256"], hashlib.sha256(before).hexdigest())
        self.assertEqual(report["output_sha256"], hashlib.sha256(self.output.read_bytes()).hexdigest())
        self.assertEqual(report["powerpoint_open"], "not_performed")
        self.assertEqual(json.loads(self.report_path.read_text()), report)
        expected = {"[Content_Types].xml", "ppt/presentation.xml", "ppt/slides/slide1.xml"}
        self.assertEqual({change["part"] for change in report["changed_parts"]}, expected)
        self.assertEqual({change["changes"][0]["code"] for change in report["changed_parts"]},
                         {"table_anchor_mid", "presentation_child_order", "orphan_content_type"})
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(archive.comment, b"Keep original ZIP comment")
            self.assertEqual(archive.namelist(), list(self.parts))
            for name, data in self.parts.items():
                if name not in expected:
                    self.assertEqual(archive.read(name), data, name)
            self.assertEqual(archive.read("ppt/slides/slide1.xml"), self.parts["ppt/slides/slide1.xml"].replace(b"anchor = 'mid'", b"anchor = 'ctr'"))
            updated, changes = normalise_parts({name: archive.read(name) for name in archive.namelist()})
            self.assertEqual(changes, [])
            self.assertEqual(updated["ppt/slides/slide1.xml"], archive.read("ppt/slides/slide1.xml"))

    def test_cli_rejects_overwrite_and_symlinks(self):
        command = [sys.executable, str(ROOT / "scripts/repair_pptx_compat.py"), "--input", str(self.source),
                   "--output", str(self.output), "--report", str(self.report_path)]
        sentinel = self.directory / "sentinel.txt"
        sentinel.write_text("Retain this file")
        for destination in (self.output, self.report_path):
            destination.symlink_to(sentinel)
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Symbolic links", result.stderr)
            self.assertEqual(sentinel.read_text(), "Retain this file")
            destination.unlink()
        self.output.write_bytes(b"Existing presentation")
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already exists", result.stderr)
        self.assertEqual(self.output.read_bytes(), b"Existing presentation")

    def test_cli_success_records_hashes_and_original_survives(self):
        before = self.source.read_bytes()
        result = subprocess.run([sys.executable, str(ROOT / "scripts/repair_pptx_compat.py"),
                                 "--input", str(self.source), "--output", str(self.output),
                                 "--report", str(self.report_path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(json.loads(result.stdout)["output_sha256"], hashlib.sha256(self.output.read_bytes()).hexdigest())

    def test_dangling_relationship_is_not_hidden_by_override_removal(self):
        name = "ppt/_rels/presentation.xml.rels"
        self.parts[name] = self.parts[name].replace(b"</Relationships>",
            f'<Relationship Id="bad" Type="{R}/slideLayout" Target="slideLayouts/unused.xml"/></Relationships>'.encode())
        self.write()
        with self.assertRaisesRegex(ValueError, "missing relationship target"):
            repair(self.source, self.output, self.report_path)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.report_path.exists())

    def test_unknown_or_duplicate_presentation_children_stop(self):
        for child in (b"<p:unsupported/>", b'<p:notesSz cx="1" cy="1"/>'):
            parts = fixture_parts()
            parts["ppt/presentation.xml"] = parts["ppt/presentation.xml"].replace(b"</p:presentation>", child + b"</p:presentation>")
            with self.assertRaisesRegex(ValueError, "unknown or duplicate presentation child"):
                normalise_parts(parts)

    def test_last_self_closing_child_does_not_consume_parent_end_tag(self):
        self.parts["ppt/presentation.xml"] = f'<p:presentation xmlns:p="{P}"><p:sldSz cx="1" cy="1"/><p:notesSz cx="1" cy="1"/><p:sldIdLst/></p:presentation>'.encode()
        updated, _ = normalise_parts(self.parts)
        root = ET.fromstring(updated["ppt/presentation.xml"])
        self.assertEqual([child.tag.split("}")[-1] for child in root], ["sldIdLst", "sldSz", "notesSz"])
        # The final orphan Override in the fixture is also immediately followed
        # by the parent's close tag; deleting it must retain that close tag.
        self.assertEqual(ET.fromstring(updated["[Content_Types].xml"]).tag, "{" + CT + "}Types")

    def test_duplicate_content_type_is_not_silently_removed(self):
        self.parts["[Content_Types].xml"] = self.parts["[Content_Types].xml"].replace(b"</Types>",
            b'<Override PartName="/ppt/slideLayouts/unused.xml" ContentType="application/xml"/></Types>')
        with self.assertRaisesRegex(ValueError, "Duplicate content-type"):
            normalise_parts(self.parts)

    def test_unsupported_xml_encoding_and_dtd_stop_without_rewriting(self):
        for data in ("<root/>".encode("utf-16"), b'<!DOCTYPE root [<!ENTITY x "text">]><root>&x;</root>'):
            parts = fixture_parts()
            parts["customXml/preserve.xml"] = data
            with self.assertRaises(ValueError):
                normalise_parts(parts)

    def chart_parts(self, kind="barChart", extra_axis=b""):
        parts, _ = normalise_parts(fixture_parts())
        parts["ppt/charts/chart1.xml"] = (f'<c:chartSpace xmlns:c="{C}"><c:chart><c:plotArea>'
            f'<c:{kind}><c:ser><c:tx><c:v>Fictional data</c:v></c:tx><c:val><c:numLit><c:pt idx="0"><c:v>42</c:v></c:pt></c:numLit></c:val></c:ser>'
            f'<c:axId val="11"/><c:axId val="22"/><c:axId val="33"/></c:{kind}>'
            '<c:catAx><c:axId val="11"/><c:crossAx val="22"/></c:catAx>'
            '<c:valAx><c:axId val="22"/><c:crossAx val="11"/></c:valAx>').encode() + extra_axis + b'</c:plotArea></c:chart></c:chartSpace>'
        parts["ppt/embeddings/fictional.xlsx"] = b"Unchanged fictional workbook payload\x00\xff"
        return parts

    def test_only_unbound_extra_2d_axis_is_removed_without_changing_chart_data(self):
        for kind in ("barChart", "lineChart"):
            with self.subTest(kind=kind):
                parts = self.chart_parts(kind)
                updated, changes = normalise_parts(parts)
                self.assertEqual(len(changes), 1)
                self.assertEqual(changes[0]["changes"][0]["code"], "orphan_2d_chart_axis")
                self.assertEqual(updated["ppt/charts/chart1.xml"], parts["ppt/charts/chart1.xml"].replace(b'<c:axId val="33"/>', b""))
                for name in parts:
                    if name != "ppt/charts/chart1.xml":
                        self.assertEqual(updated[name], parts[name])
                self.assertEqual(normalise_parts(updated)[1], [])

    def test_3d_chart_axis_references_are_preserved(self):
        parts = self.chart_parts("bar3DChart", b'<c:serAx><c:axId val="33"/><c:crossAx val="22"/></c:serAx>')
        updated, changes = normalise_parts(parts)
        self.assertEqual(changes, [])
        self.assertEqual(updated, parts)

    def test_active_or_ambiguous_third_axis_stops_instead_of_removing_data(self):
        for extra in (b'<c:serAx><c:axId val="33"/><c:crossAx val="22"/></c:serAx>',
                      b'<c:lineChart><c:axId val="33"/></c:lineChart>'):
            with self.subTest(extra=extra):
                with self.assertRaisesRegex(ValueError, "active or ambiguous third"):
                    normalise_parts(self.chart_parts(extra_axis=extra))

    def theme_parts(self, owner="notesMaster", with_children=True):
        parts, _ = normalise_parts(fixture_parts())
        source = b'<a:theme xmlns:a="' + A.encode() + b'" name="Original editable theme"><a:themeElements/></a:theme>'
        parts["ppt/theme/theme1.xml"] = source
        parts["[Content_Types].xml"] = parts["[Content_Types].xml"].replace(b"</Types>",
            b'<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/></Types>')
        parts["ppt/_rels/presentation.xml.rels"] = parts["ppt/_rels/presentation.xml.rels"].replace(b"</Relationships>",
            f'<Relationship Id="theme" Type="{R}/theme" Target="theme/theme1.xml"/></Relationships>'.encode())
        if owner == "handoutMaster":
            parts["ppt/handoutMasters/handoutMaster1.xml"] = f'<p:handoutMaster xmlns:p="{P}"><p:cSld/></p:handoutMaster>'.encode()
        master = f"ppt/{owner}s/{owner}1.xml"
        master_rels = f"ppt/{owner}s/_rels/{owner}1.xml.rels"
        parts[master_rels] = f'<Relationships xmlns="{REL}"><Relationship Id="theme" Type="{R}/theme" Target="../theme/theme1.xml"/></Relationships>'.encode()
        if with_children:
            parts["ppt/theme/_rels/theme1.xml.rels"] = f'<Relationships xmlns="{REL}"><Relationship Id="picture" Type="{R}/image" Target="../media/evidence.png"/></Relationships>'.encode()
        return parts, master, master_rels

    def test_shared_auxiliary_theme_clone_preserves_bytes_dependencies_and_ids(self):
        for owner in ("notesMaster", "handoutMaster"):
            with self.subTest(owner=owner):
                parts, master, master_rels = self.theme_parts(owner)
                updated, changes = normalise_parts(parts)
                clone = "ppt/theme/theme2.xml"
                self.assertEqual(updated[clone], parts["ppt/theme/theme1.xml"])
                self.assertEqual(updated["ppt/theme/_rels/theme2.xml.rels"], parts["ppt/theme/_rels/theme1.xml.rels"])
                self.assertEqual(updated[master_rels], parts[master_rels].replace(b'../theme/theme1.xml', b'../theme/theme2.xml'))
                self.assertEqual(updated[master], parts[master])
                for name in parts:
                    if name not in (master_rels, "[Content_Types].xml"):
                        self.assertEqual(updated[name], parts[name], name)
                self.assertEqual({change["part"] for change in changes if change["before_sha256"] is None},
                                 {clone, "ppt/theme/_rels/theme2.xml.rels"})
                self.assertEqual(normalise_parts(updated)[1], [])

    def test_theme_clone_avoids_existing_filenames_and_writer_keeps_new_members(self):
        self.parts, _, _ = self.theme_parts()
        self.parts["ppt/theme/theme2.xml"] = self.parts["ppt/theme/theme1.xml"].replace(b"Original", b"Independent")
        self.write()
        before = self.source.read_bytes()
        report = repair(self.source, self.output, self.report_path)
        self.assertEqual(self.source.read_bytes(), before)
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(archive.read("ppt/theme/theme2.xml"), self.parts["ppt/theme/theme2.xml"])
            self.assertEqual(archive.read("ppt/theme/theme3.xml"), self.parts["ppt/theme/theme1.xml"])
            self.assertEqual(archive.read("ppt/theme/_rels/theme3.xml.rels"), self.parts["ppt/theme/_rels/theme1.xml.rels"])
            self.assertEqual(normalise_parts({name: archive.read(name) for name in archive.namelist()})[1], [])
        self.assertTrue(any(change["before_sha256"] is None for change in report["changed_parts"]))

    def test_independent_auxiliary_theme_needs_no_clone(self):
        parts, _, master_rels = self.theme_parts(with_children=False)
        parts["ppt/theme/theme2.xml"] = parts["ppt/theme/theme1.xml"]
        parts[master_rels] = parts[master_rels].replace(b"theme1.xml", b"theme2.xml")
        updated, changes = normalise_parts(parts)
        self.assertEqual(updated, parts)
        self.assertEqual(changes, [])

    def test_ambiguous_shared_theme_or_unsafe_dependency_fails(self):
        parts, _, master_rels = self.theme_parts()
        parts[master_rels] = parts[master_rels].replace(b"</Relationships>",
            f'<Relationship Id="duplicateTheme" Type="{R}/theme" Target="../theme/theme1.xml"/></Relationships>'.encode())
        with self.assertRaisesRegex(ValueError, "ambiguous auxiliary-master"):
            normalise_parts(parts)
        parts, _, _ = self.theme_parts()
        parts["ppt/theme/_rels/theme1.xml.rels"] = parts["ppt/theme/_rels/theme1.xml.rels"].replace(b"../media/evidence.png", b"theme1.xml")
        with self.assertRaisesRegex(ValueError, "Cannot safely clone theme dependencies"):
            normalise_parts(parts)


if __name__ == "__main__":
    unittest.main()
