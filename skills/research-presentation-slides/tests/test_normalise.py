import sys
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from normalise_generated import normalise_xml, A


class NormaliseTests(unittest.TestCase):
    def test_only_identical_level_removed(self):
        source = f'''<a:txBody xmlns:a="{A}"><a:bodyPr/><a:lstStyle>
        <a:defPPr algn="l"><a:defRPr sz="1800"/></a:defPPr>
        <a:lvl1pPr algn="l"><a:defRPr sz="1800"/></a:lvl1pPr>
        <a:lvl2pPr algn="r"><a:defRPr sz="1400"/></a:lvl2pPr>
        </a:lstStyle><a:p><a:r><a:t>Keep 12.3 ppm &amp; source [1]</a:t></a:r></a:p></a:txBody>'''
        result, count = normalise_xml(source.encode())
        self.assertEqual(count, 1)
        root = ET.fromstring(result)
        self.assertIsNone(root.find(f".//{{{A}}}lvl1pPr"))
        self.assertIsNotNone(root.find(f".//{{{A}}}lvl2pPr"))
        self.assertEqual(root.find(f".//{{{A}}}t").text, "Keep 12.3 ppm & source [1]")
        self.assertEqual(normalise_xml(result), (result, 0))

    def test_without_default_is_unchanged(self):
        source = f'<a:lstStyle xmlns:a="{A}"><a:lvl1pPr algn="l"/></a:lstStyle>'.encode()
        self.assertEqual(normalise_xml(source), (source, 0))


if __name__ == "__main__":
    unittest.main()
