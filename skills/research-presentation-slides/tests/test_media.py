"""Structural media tests use a synthetic MP4 header, never a playback claim."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

MODULE_PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'embed_media.py'
SPEC = importlib.util.spec_from_file_location('embed_media', MODULE_PATH)
MEDIA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MEDIA)


class MediaEmbedding(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.file = self.root / 'candidate.pptx'
        self.movie = b'\x00\x00\x00\x18ftypmp42' + b'fixture-only-not-playable'
        (self.root / 'background.mp4').write_bytes(self.movie)
        ns = MEDIA.NS
        # Use a nonsequential part name to check presentation-order resolution.
        self.slide_part = 'ppt/slides/slide7.xml'
        slide = f'''<p:sld xmlns:p="{ns['p']}" xmlns:a="{ns['a']}" xmlns:r="{ns['r']}">
          <p:cSld><p:spTree>
          <p:pic><p:nvPicPr><p:cNvPr id="9" name="role:background|id:cover-media"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>
          <p:blipFill><a:blip r:embed="rIdPoster"/></p:blipFill><p:spPr/></p:pic>
          <p:sp><p:nvSpPr><p:cNvPr id="10" name="role:title|id:cover-title"/></p:nvSpPr><p:txBody><a:p><a:r><a:t>Editable title</a:t></a:r></a:p></p:txBody></p:sp>
          </p:spTree></p:cSld></p:sld>'''
        parts = {
            '[Content_Types].xml': f'<Types xmlns="{MEDIA.CT}"/>',
            'ppt/presentation.xml': f'<p:presentation xmlns:p="{ns["p"]}" xmlns:r="{ns["r"]}"><p:sldIdLst><p:sldId id="256" r:id="rIdSlide"/></p:sldIdLst></p:presentation>',
            'ppt/_rels/presentation.xml.rels': f'<Relationships xmlns="{MEDIA.REL}"><Relationship Id="rIdSlide" Target="/ppt/slides/slide7.xml" Type="{ns["r"]}/slide"/></Relationships>',
            self.slide_part: slide,
            'ppt/slides/_rels/slide7.xml.rels': f'<Relationships xmlns="{MEDIA.REL}"><Relationship Id="rIdPoster" Target="../media/poster.png" Type="{ns["r"]}/image"/></Relationships>',
            'ppt/media/poster.png': b'poster-fixture',
        }
        with zipfile.ZipFile(self.file, 'w') as archive:
            for name, value in parts.items():
                archive.writestr(name, value)

    def tearDown(self):
        self.temp.cleanup()

    def spec(self, **settings):
        return {'slides': [{'number': 1, 'media': [{
            'poster_id': 'cover-media', 'path': 'background.mp4',
            'sha256': hashlib.sha256(self.movie).hexdigest(), **settings,
        }]}]}

    def test_preserves_media_poster_text_and_records_looped_muted_autoplay(self):
        report = MEDIA.embed(self.file, self.spec(), self.root)
        item = report['embedded_media'][0]
        self.assertEqual(item['application_playback'], 'unverified')
        self.assertTrue(item['autoplay'])
        with zipfile.ZipFile(self.file) as archive:
            self.assertEqual(archive.read(item['package_part']), self.movie)
            self.assertEqual(archive.read('ppt/media/poster.png'), b'poster-fixture')
            root = ET.fromstring(archive.read(self.slide_part))
            self.assertEqual(root.find('.//p:blipFill/a:blip', MEDIA.NS).get(f'{{{MEDIA.NS["r"]}}}embed'), 'rIdPoster')
            self.assertEqual(root.find('.//a:t', MEDIA.NS).text, 'Editable title')
            media = root.find('.//p:cMediaNode', MEDIA.NS)
            self.assertEqual(media.get('mute'), '1')
            self.assertEqual(media.find('p:cTn', MEDIA.NS).get('repeatCount'), 'indefinite')
            self.assertEqual(media.find('p:cTn/p:stCondLst/p:cond', MEDIA.NS).attrib, {'delay': '0'})
            self.assertEqual(media.find('p:tgtEl/p:spTgt', MEDIA.NS).get('spid'), '9')
            links = ET.fromstring(archive.read('ppt/slides/_rels/slide7.xml.rels'))
            self.assertEqual(len([link for link in links if link.get('Type') in (MEDIA.MEDIA_REL, MEDIA.NS['r'] + '/video')]), 2)
            self.assertIsNone(root.find('.//a:hlinkClick', MEDIA.NS).get(f'{{{MEDIA.NS["r"]}}}id'))
            content_types = ET.fromstring(archive.read('[Content_Types].xml'))
            self.assertTrue(any(e.get('Extension') == 'mp4' and e.get('ContentType') == 'video/mp4' for e in content_types))

    def test_manual_unmuted_single_play_uses_the_poster_as_click_target(self):
        MEDIA.embed(self.file, self.spec(autoplay=False, loop=False, muted=False), self.root)
        with zipfile.ZipFile(self.file) as archive:
            root = ET.fromstring(archive.read(self.slide_part))
        media = root.find('.//p:cMediaNode', MEDIA.NS)
        self.assertEqual(media.get('mute'), '0')
        self.assertEqual(media.get('vol'), '100000')
        self.assertIsNone(media.find('p:cTn', MEDIA.NS).get('repeatCount'))
        cond = media.find('p:cTn/p:stCondLst/p:cond', MEDIA.NS)
        self.assertEqual(cond.get('evt'), 'onClick')
        self.assertEqual(cond.find('p:tgtEl/p:spTgt', MEDIA.NS).get('spid'), '9')

    def test_bad_settings_or_changed_media_leave_the_candidate_unchanged(self):
        before = self.file.read_bytes()
        with self.assertRaisesRegex(ValueError, 'JSON booleans'):
            MEDIA.embed(self.file, self.spec(autoplay='yes'), self.root)
        self.assertEqual(self.file.read_bytes(), before)
        (self.root / 'background.mp4').write_bytes(self.movie + b'changed')
        with self.assertRaisesRegex(ValueError, 'Video changed'):
            MEDIA.embed(self.file, self.spec(), self.root)
        self.assertEqual(self.file.read_bytes(), before)

    def test_embedding_twice_is_rejected(self):
        MEDIA.embed(self.file, self.spec(), self.root)
        before = self.file.read_bytes()
        with self.assertRaisesRegex(ValueError, 'already has a video'):
            MEDIA.embed(self.file, self.spec(), self.root)
        self.assertEqual(self.file.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
