"""外部メモの欠落・取り違え・古い検査記録を、架空入力に対して検出する。"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_memo import check, parse_memo, memo_requirement
from check_layout import check as check_layout
from extract_reference import sha256
from quality_gate import evaluate
from test_quality import shape, write_pptx, textbody


def managed(body, text=False):
    digest = hashlib.sha256(body.encode()).hexdigest()
    if text:
        return f'=== GENERATED CONTENT START ===\n=== GENERATED CONTENT SHA256: {digest} ===\n{body}=== GENERATED CONTENT END ===\n', digest
    return f'<!-- GENERATED CONTENT START -->\n<!-- GENERATED CONTENT SHA256: {digest} -->\n{body}<!-- GENERATED CONTENT END -->\n\n## 利用者の追記（再生成時も保持）\n\n', digest


class MemoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pptx = self.root / 'fiction.pptx'
        self.spec_path = self.root / 'input.json'
        self.memo = self.root / 'fiction-発表メモ.md'
        self.layout_path = self.root / 'fiction.layout.json'
        self.spec = {'metadata': {'title': 'Fiction'}, 'slides': [
            {'id': 'plan', 'title': 'Planned comparison', 'message': 'Two conditions are planned',
             'notes': {'text': 'No participants have been recruited.', 'evidence': ['Protocol section 3.'],
                       'preparation': ['Confirm room allocation.']}, 'sources': ['Protocol draft']},
            {'id': 'pilot', 'title': 'Pilot observation', 'message': 'Four of six trials completed',
             'notes': 'The denominator is six trials, not six people.', 'sources': ['Pilot log']} ]}
        self.write_spec()
        self.write_deck()
        self.blocks = [
            '## 表示ページ 1\n\n- スライドID：plan\n- 題名：Planned comparison\n\n### 画面の主張\n\nTwo conditions are planned\n\n### 口頭補足\n\nNo participants have been recruited.\n\n### 根拠\n\nProtocol draft\n\n### 根拠・確認情報\n\nProtocol section 3.\n',
            '## 表示ページ 2\n\n- スライドID：pilot\n- 題名：Pilot observation\n\n### 画面の主張\n\nFour of six trials completed\n\n### 口頭補足\n\nThe denominator is six trials, not six people.\n\n### 根拠\n\nPilot log\n']
        self.write_memo()

    def tearDown(self):
        self.temp.cleanup()

    def write_spec(self):
        self.spec_path.write_text(json.dumps(self.spec), encoding='utf-8')

    def write_deck(self, reverse=False):
        slides = list(reversed(self.spec['slides'])) if reverse else self.spec['slides']
        write_pptx(self.pptx, [shape(2, 'title', 'title', s['title'], 24) +
                               shape(3, 'message', 'body', s.get('message', '')) +
                               shape(5, 'source', 'source', '\n'.join(s.get('sources', [])), 9) +
                               shape(4, 'page', 'page', number)
                               for number, s in enumerate(slides, 1)])
        with zipfile.ZipFile(self.pptx, 'a') as archive:
            for number, slide in enumerate(slides, 1):
                notes = slide.get('notes', '')
                parts = [notes.get('text', '')] + notes.get('evidence', []) if isinstance(notes, dict) else [notes]
                parts += slide.get('sources', []) + ([slide['message']] if slide.get('message') else [])
                archive.writestr(f'ppt/slides/_rels/slide{number}.xml.rels',
                    f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="notes" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide" Target="../notesSlides/notesSlide{number}.xml"/></Relationships>')
                archive.writestr(f'ppt/notesSlides/notesSlide{number}.xml',
                    '<p:notes xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree><p:sp><p:txBody>' + textbody('\n'.join(parts)) + '</p:txBody></p:sp></p:spTree></p:cSld></p:notes>')

    def write_memo(self, blocks=None):
        body = '# 発表メモ\n\n' + '\n'.join(self.blocks if blocks is None else blocks)
        text, self.digest = managed(body)
        self.memo.write_text(text, encoding='utf-8')
        self.receipt()

    def receipt(self):
        self.layout = {'pptx_sha256': sha256(self.pptx), 'source_sha256': sha256(self.spec_path),
                       'slides': [{'number': n, 'id': s['id']} for n, s in enumerate(self.spec['slides'], 1)],
                       'memo': {'file': self.memo.name, 'format': 'text' if self.memo.suffix == '.txt' else 'markdown',
                                'sha256': sha256(self.memo), 'generated_sha256': self.digest}}
        self.layout_path.write_text(json.dumps(self.layout), encoding='utf-8')

    def check(self, **kwargs):
        return check(self.pptx, self.spec_path, **kwargs)

    def codes(self, result):
        return {f['code'] for f in result['findings']}

    def test_matching_text_still_requires_meaning_review(self):
        result = self.check()
        self.assertEqual(result['status'], 'review_required')
        self.assertEqual(result['errors'], [])
        self.assertEqual([f['id'] for f in result['review_items']], ['memo_semantics:1', 'memo_semantics:2'])
        self.assertEqual(result['pages'][0]['input']['evidence'], ['Protocol section 3.'])
        self.assertIn('Two conditions', result['pages'][0]['final_slide_text'])
        self.assertNotIn('Confirm room allocation', self.memo.read_text())

    def test_fixed_placeholder_cannot_satisfy_independent_notes(self):
        self.write_memo([b.replace('No participants have been recruited.', '[object Object]')
                         .replace('The denominator is six trials, not six people.', '追加の口頭補足なし')
                         .replace('Protocol section 3.', '') for b in self.blocks])
        result = self.check()
        self.assertIn('memo_text', self.codes(result))
        self.assertIn('memo_evidence', self.codes(result))

    def test_page_swap_and_duplicate_are_detected(self):
        self.write_memo(list(reversed(self.blocks)))
        self.assertIn('memo_page_order', self.codes(self.check()))
        self.write_memo([self.blocks[0], self.blocks[0]])
        codes = self.codes(self.check())
        self.assertTrue({'memo_page_order', 'memo_ids', 'memo_page_missing'} <= codes)

    def test_ids_and_titles_are_checked_against_input(self):
        self.write_memo([self.blocks[0].replace('スライドID：plan', 'スライドID：other').replace('題名：Planned comparison', '題名：Wrong title'), self.blocks[1]])
        self.assertTrue({'memo_id', 'memo_title'} <= self.codes(self.check()))

    def test_final_slide_swap_is_detected_even_with_current_receipts(self):
        self.write_deck(reverse=True)
        self.receipt()
        codes = self.codes(self.check())
        self.assertTrue({'memo_final_title', 'memo_final_claim'} <= codes)

    def test_missing_external_memo_is_an_error(self):
        self.memo.unlink()
        result = self.check()
        self.assertIn('memo_missing', self.codes(result))
        self.assertTrue(result['applicability']['required'])

    def test_unnecessary_memo_needs_reasoned_not_applicable(self):
        self.memo.unlink()
        for s in self.spec['slides']:
            s.pop('notes')
        self.write_spec()
        result = self.check()
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['applicability']['status'], 'not_applicable')
        self.assertTrue(result['applicability']['reasons'])
        self.assertFalse(memo_requirement({'slides': [{'semantic_claims': [{'text': 'Visible claim'}], 'notes': {'preparation': ['Build only']}}]})['required'])

    def test_explicit_requirement_cannot_be_suppressed(self):
        self.assertTrue(memo_requirement({'memo_required': True, 'slides': []})['required'])
        self.assertTrue(memo_requirement({'slides': [{'memo_required': True}]})['required'])
        self.assertTrue(memo_requirement({'memo_required': False, 'slides': [{'notes': 'Needed'}]})['required'])

    def test_generation_hash_and_full_file_receipt_are_independent(self):
        self.memo.write_text(self.memo.read_text().replace('No participants', 'Several participants'), encoding='utf-8')
        self.assertTrue({'memo_generated_hash', 'memo_receipt_sha256'} <= self.codes(self.check()))
        self.write_memo()
        self.memo.write_text(self.memo.read_text() + 'A new user addition\n', encoding='utf-8')
        codes = self.codes(self.check())
        self.assertIn('memo_receipt_sha256', codes)
        self.assertNotIn('memo_generated_hash', codes)

    def test_handwritten_additions_can_be_reviewed_without_regeneration(self):
        self.memo.write_text(self.memo.read_text() + 'A preserved personal addition\n')
        result = self.check()
        self.assertEqual(result['errors'], [])
        self.assertIn('memo_receipt_sha256', self.codes(result))
        self.assertIn('memo_user_additions', self.codes(result))
        self.assertEqual(result['user_additions'], 'A preserved personal addition')
        layout, memo, visual = self.gate_inputs()
        self.assertTrue(self.gate(layout, memo, visual)['verified_complete'])

    def test_source_hash_change_is_detected(self):
        self.spec['slides'][0]['notes']['text'] = 'A new speaking condition.'
        self.write_spec()
        self.assertTrue({'memo_layout_binding', 'memo_text'} <= self.codes(self.check()))

    def test_ambiguous_md_and_txt_require_explicit_selection(self):
        self.memo.with_suffix('.txt').write_text('Another original')
        self.assertIn('memo_ambiguous', self.codes(self.check()))
        self.assertNotIn('memo_ambiguous', self.codes(self.check(memo=self.memo)))

    def test_custom_format_is_unverified_and_untouched(self):
        before = 'My private speaking plan\nFirst describe the system.\n'
        self.memo.write_text(before)
        result = self.check()
        self.assertIn('memo_format', self.codes(result))
        self.assertEqual(result['status'], 'unverified')
        self.assertEqual(self.memo.read_text(), before)

    def test_old_txt_is_parsed_without_conversion(self):
        self.memo.unlink()
        self.memo = self.root / 'fiction-発表メモ.txt'
        text = '\n'.join(f'表示ページ番号：{n}\nスライドID：{s["id"]}\n題名：{s["title"]}\n画面の主張：{s["message"]}\n口頭補足：{s["notes"]["text"] if isinstance(s["notes"], dict) else s["notes"]}\n根拠：{s["sources"][0]}\n' + ('根拠・確認情報：Protocol section 3.\n' if n == 1 else '') for n, s in enumerate(self.spec['slides'], 1))
        self.memo.write_text(text)
        self.digest = None
        self.receipt()
        result = self.check()
        self.assertEqual(result['errors'], [])
        self.assertIn('memo_generated_hash_missing', self.codes(result))
        self.assertEqual(result['format'], 'text')
        self.assertFalse(self.memo.with_suffix('.md').exists())
        self.assertEqual(self.memo.read_text(), text)

    def test_markdown_escapes_and_multiline_evidence_are_decoded(self):
        body = '# 発表メモ\n\n## 表示ページ 1\n\n- スライドID：a\\-b\n- 題名：A &amp; B\\.\n\n### 口頭補足\n\nLine 1\\.  \nLine 2\n\n### 根拠\n\n\\[1\\]\n'
        pages, meta, error = parse_memo(managed(body)[0], 'markdown')
        self.assertIsNone(error)
        self.assertEqual(pages[0]['id'], 'a-b')
        self.assertEqual(pages[0]['title'], 'A & B.')
        self.assertEqual(pages[0]['sources'], '[1]')

    def test_multiline_title_and_id_in_both_supported_formats(self):
        markdown = '# 発表メモ\n\n## 表示ページ 1\n\n- スライドID：first  \nsecond\n- 題名：Main title  \nSubtitle\n\n### 口頭補足\n\nNote\n\n### 根拠\n\nSource\n'
        text = '表示ページ番号：1\nスライドID：first\nsecond\n題名：Main title\nSubtitle\n口頭補足：Note\n根拠：Source\n'
        for value, format_name in ((markdown, 'markdown'), (text, 'text')):
            pages, _, error = parse_memo(managed(value, text=format_name == 'text')[0], format_name)
            self.assertIsNone(error)
            self.assertEqual(pages[0]['title'].split(), ['Main', 'title', 'Subtitle'])
            self.assertEqual(pages[0]['id'].split(), ['first', 'second'])

    def test_final_embedded_notes_cannot_use_a_placeholder(self):
        with zipfile.ZipFile(self.pptx) as archive:
            parts = {name: archive.read(name) for name in archive.namelist()}
        parts['ppt/notesSlides/notesSlide1.xml'] = parts['ppt/notesSlides/notesSlide1.xml'].replace(b'No participants have been recruited.', b'[object Object]')
        with zipfile.ZipFile(self.pptx, 'w') as archive:
            for name, value in parts.items():
                archive.writestr(name, value)
        self.receipt()
        self.assertIn('memo_embedded_text', self.codes(self.check()))

    def test_preparation_cannot_leak_into_speaking_text(self):
        self.write_memo([self.blocks[0].replace('No participants have been recruited.', 'No participants have been recruited. Confirm room allocation.'), self.blocks[1]])
        self.assertIn('memo_preparation_leak', self.codes(self.check()))

    def test_cli_protects_sources_and_reports_inspection(self):
        script = Path(__file__).resolve().parents[1] / 'scripts' / 'check_memo.py'
        result = subprocess.run([sys.executable, str(script), str(self.pptx), '--deck-spec', str(self.spec_path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'review_required')
        before = self.memo.read_bytes()
        result = subprocess.run([sys.executable, str(script), str(self.pptx), '--deck-spec', str(self.spec_path), '--report', str(self.memo)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.memo.read_bytes(), before)

    def test_cli_protects_both_ambiguous_originals(self):
        scripts = Path(__file__).resolve().parents[1] / 'scripts'
        text_memo = self.memo.with_suffix('.txt')
        text_memo.write_text('Original TXT to retain')
        layout_report = self.root / 'layout-report.json'
        layout_report.write_text('{}')
        for original in (self.memo, text_memo):
            before = original.read_bytes()
            for command in ([sys.executable, str(scripts / 'check_memo.py'), str(self.pptx), '--deck-spec', str(self.spec_path)],
                            [sys.executable, str(scripts / 'quality_gate.py'), str(self.pptx), '--layout-report', str(layout_report)]):
                result = subprocess.run(command + ['--report', str(original)], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(original.read_bytes(), before)

    def gate_inputs(self):
        # Synthetic receipts exercise gate contracts; these bytes are not render evidence.
        layout = check_layout(self.pptx, deck_spec=self.spec, layout=self.layout)
        image = self.root / 'fixture-image.png'
        image.write_bytes(b'synthetic receipt fixture, not a presentation render')
        memo = self.check()
        visual = {'pptx_sha256': sha256(self.pptx), 'deck_spec_sha256': sha256(self.spec_path),
                  'pages': [{'number': n, 'image': str(image), 'image_sha256': sha256(image),
                             'status': 'pass', 'reviewer': 'unit test fixture',
                             'notes': 'Synthetic receipt contract only; no human visual review claimed.'}
                            for n in (1, 2)],
                  'resolved_findings': [{'id': f['id'], 'status': 'pass', 'method': 'fixture',
                                         'reason': 'Synthetic contract fixture', 'evidence': 'fixture',
                                         'memo_sha256': memo['memo_sha256'],
                                         'deck_spec_sha256': memo['deck_spec_sha256']}
                                        for f in layout['findings'] + memo['findings']]}
        return layout, memo, visual

    def gate(self, layout, memo, visual):
        return evaluate(self.pptx, layout, visual, deck_spec=self.spec_path, memo_report=memo)

    def test_gate_requires_memo_report_and_current_semantic_resolution(self):
        layout, memo, visual = self.gate_inputs()
        self.assertTrue(self.gate(layout, memo, visual)['verified_complete'])
        no_report = evaluate(self.pptx, layout, visual)
        self.assertFalse(no_report['verified_complete'])
        self.assertIn('memo_report_missing', {i['code'] for i in no_report['issues']})
        for resolution in visual['resolved_findings']:
            if resolution['id'].startswith('memo_'):
                resolution.pop('memo_sha256')
        result = self.gate(layout, memo, visual)
        self.assertFalse(result['verified_complete'])
        self.assertIn('memo_unresolved', {i['code'] for i in result['issues']})

    def test_gate_rejects_removed_page_records_and_semantic_findings(self):
        layout, memo, visual = self.gate_inputs()
        for changed in ({**memo, 'pages': []}, {**memo, 'findings': [], 'review_items': [], 'status': 'pass'},
                        {**memo, 'applicability': {'required': False, 'status': 'not_applicable', 'reasons': ['Not needed']}}):
            result = self.gate(layout, changed, visual)
            self.assertFalse(result['verified_complete'])
            self.assertIn('memo_report_schema', {i['code'] for i in result['issues']})

    def test_gate_rejects_stale_external_memo_and_changed_user_additions(self):
        layout, memo, visual = self.gate_inputs()
        self.memo.write_text(self.memo.read_text() + 'A user clarification\n')
        self.assertFalse(self.gate(layout, memo, visual)['verified_complete'])
        # Fresh file/report receipts cannot reuse a semantic review of the old memo.
        self.receipt()
        current_memo = self.check()
        result = self.gate(layout, current_memo, visual)
        self.assertIn('memo_unresolved', {i['code'] for i in result['issues']})

    def test_gate_rejects_old_input_review_even_after_report_regeneration(self):
        layout, memo, visual = self.gate_inputs()
        self.spec['context'] = 'New independently supplied context requiring review.'
        self.write_spec()
        self.receipt()
        current_memo = self.check()
        for resolution in visual['resolved_findings']:
            resolution['deck_spec_sha256'] = current_memo['deck_spec_sha256']
        result = self.gate(layout, current_memo, visual)
        self.assertIn('visual_input_sha', {i['code'] for i in result['issues']})

    def test_gate_rejects_layout_inspected_against_another_input(self):
        layout, memo, visual = self.gate_inputs()
        layout['deck_spec_content_sha256'] = hashlib.sha256(b'other independent input').hexdigest()
        result = self.gate(layout, memo, visual)
        self.assertIn('layout_input_sha', {i['code'] for i in result['issues']})
        self.assertFalse(result['verified_complete'])

    def test_gate_cannot_resolve_memo_errors_manually(self):
        self.write_memo([self.blocks[0].replace('No participants have been recruited.', 'Placeholder'), self.blocks[1]])
        layout, memo, visual = self.gate_inputs()
        result = self.gate(layout, memo, visual)
        self.assertFalse(result['verified_complete'])
        self.assertIn('memo_error', {i['code'] for i in result['issues']})

    def test_memo_must_stay_beside_pptx(self):
        other = self.root / 'other'
        other.mkdir()
        moved = other / self.memo.name
        moved.write_bytes(self.memo.read_bytes())
        self.assertIn('memo_directory', self.codes(self.check(memo=moved)))


if __name__ == '__main__':
    unittest.main()
