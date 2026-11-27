#!/usr/bin/env python3
"""外部発表メモを独立入力・最終PPTXへ対応付ける。文字一致は意味の合格にしない。"""
import argparse
import hashlib
import html
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

from extract_reference import extract, sha256

SEVERITIES = ('error', 'review_required', 'unverified')
MARKERS = {'markdown': ('<!-- GENERATED CONTENT START -->', '<!-- GENERATED CONTENT END -->'),
           'text': ('=== GENERATED CONTENT START ===', '=== GENERATED CONTENT END ===')}


def normal(value):
    """Compare characters, allowing only whitespace differences introduced by wrapping."""
    return re.sub(r'\s+', '', str(value))


def plain(value, markdown):
    if markdown:
        value = re.sub(r'\\([\\`*_[\]{}()#+\-.!|>~])', r'\1', value)
        value = html.unescape(value)
    return value.strip()


def memo_requirement(spec):
    reasons = []
    if spec.get('memo_required') is True:
        reasons.append('Input explicitly requires a presentation memo.')
    for number, slide in enumerate(spec.get('slides', []), 1):
        notes = slide.get('notes', '')
        text = notes.get('text', '') if isinstance(notes, dict) else notes
        evidence = notes.get('evidence', []) if isinstance(notes, dict) else []
        if isinstance(text, str) and text.strip():
            reasons.append(f'Page {number}: notes.text is supplied.')
        if evidence:
            reasons.append(f'Page {number}: notes.evidence is supplied.')
        if slide.get('notes_required'):
            reasons.append(f'Page {number}: notes_required is supplied.')
        if slide.get('memo_required') is True:
            reasons.append(f'Page {number}: memo_required is true.')
    return {'required': bool(reasons), 'reasons': reasons or [
        'Independent input contains no speaking notes, evidence notes, required notes or explicit memo requirement.']}


def validate_spec(spec):
    if not isinstance(spec, dict) or not isinstance(spec.get('slides'), list):
        raise ValueError('Independent deck specification must contain a slides array.')
    for slide in spec['slides']:
        if not isinstance(slide, dict):
            raise ValueError('Every input slide must be an object.')
        notes = slide.get('notes', '')
        if not isinstance(notes, (str, dict)):
            raise ValueError('notes must be a string or an object.')
        if isinstance(notes, dict):
            if not isinstance(notes.get('text', ''), str):
                raise ValueError('notes.text must be a string.')
            for key in ('evidence', 'preparation'):
                values = notes.get(key, [])
                if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
                    raise ValueError(f'notes.{key} must be an array of strings.')
        for key in ('notes_required', 'sources'):
            values = slide.get(key, [])
            if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
                raise ValueError(f'{key} must be an array of strings.')


def select_memo(pptx, memo=None):
    if memo is not None:
        return Path(memo), []
    stem = Path(pptx).with_suffix('')
    candidates = [Path(str(stem) + '-発表メモ' + ext) for ext in ('.md', '.txt')]
    present = [path for path in candidates if path.exists()]
    return (present[0] if len(present) == 1 else None), present if len(present) > 1 else []


def parse_memo(text, format_name):
    """Parse the documented MD/TXT formats only; never rewrite an unfamiliar original."""
    markdown = format_name == 'markdown'
    start, end = MARKERS[format_name]
    meta = {'marker_status': 'absent', 'generated_sha256': None,
            'declared_generated_sha256': None, 'user_additions': ''}
    body = text
    if start in text or end in text:
        if text.count(start) != 1 or text.count(end) != 1 or text.index(start) >= text.index(end):
            return [], {**meta, 'marker_status': 'invalid'}, 'Generated block markers are missing, repeated or out of order.'
        body = text.split(start, 1)[1].split(end, 1)[0]
        outside = text[:text.index(start)] + text[text.index(end) + len(end):]
        meta['user_additions'] = re.sub(r'^(?:## )?利用者の追記（再生成時も保持）[：:]?\s*$', '', outside, flags=re.M).strip()
        marker = (r'^\n<!-- GENERATED CONTENT SHA256: ([0-9a-f]{64}) -->\n' if markdown
                  else r'^\n=== GENERATED CONTENT SHA256: ([0-9a-f]{64}) ===\n')
        match = re.match(marker, body)
        if match:
            body = body[match.end():]
            meta.update(marker_status='present', declared_generated_sha256=match.group(1),
                        generated_sha256=hashlib.sha256(body.encode('utf-8')).hexdigest())
        else:
            meta['marker_status'] = 'legacy'
            body = body[1:] if body.startswith('\n') else body
    pattern = r'^## 表示ページ (\d+)\s*$' if markdown else r'^表示ページ番号：(\d+)\s*$'
    headings = list(re.finditer(pattern, body, re.M))
    if not headings:
        return [], meta, 'Unsupported memo format; retain the original and review its page mapping manually.'
    pages = []
    for index, match in enumerate(headings):
        chunk = body[match.end():headings[index + 1].start() if index + 1 < len(headings) else len(body)]
        fields = {}
        fields_pattern = (r'^- (スライドID|題名)：' if markdown else r'^(スライドID|題名)：')
        field_matches = list(re.finditer(fields_pattern, chunk, re.M))
        section_pattern = (r'^### (画面の主張|口頭補足|根拠|根拠・確認情報)\s*$' if markdown
                           else r'^(画面の主張|口頭補足|根拠|根拠・確認情報)：')
        section_matches = list(re.finditer(section_pattern, chunk, re.M))
        boundaries = sorted([item.start() for item in field_matches + section_matches] + [len(chunk)])
        for field in field_matches:
            if field.group(1) in fields:
                return [], meta, 'Repeated ID or title fields in a page block.'
            end_position = next(position for position in boundaries if position > field.start())
            fields[field.group(1)] = plain(chunk[field.end():end_position], markdown)
        sections = {}
        for item_index, section in enumerate(section_matches):
            key = section.group(1)
            if key in sections:
                return [], meta, 'Repeated memo section in a page block.'
            value = chunk[section.end():section_matches[item_index + 1].start() if item_index + 1 < len(section_matches) else len(chunk)]
            sections[key] = plain(value, markdown)
        pages.append({'number': int(match.group(1)), 'id': fields.get('スライドID'),
                      'title': fields.get('題名'), 'claims': sections.get('画面の主張', ''),
                      'text': sections.get('口頭補足', ''), 'sources': sections.get('根拠', ''),
                      'evidence': sections.get('根拠・確認情報', ''), 'sections': list(sections)})
    return pages, meta, None


def check(pptx, deck_spec, memo=None, layout=None):
    pptx, spec_path = Path(pptx), Path(deck_spec)
    spec = json.loads(spec_path.read_text(encoding='utf-8'))
    validate_spec(spec)
    inv = extract(pptx)
    layout_path = Path(layout) if layout is not None else pptx.with_suffix('.layout.json')
    report = {'schema_version': 1, 'report_kind': 'presentation_memo', 'file': str(pptx),
              'pptx_sha256': inv['pptx_sha256'], 'deck_spec_file': str(spec_path),
              'deck_spec_sha256': sha256(spec_path), 'layout_file': str(layout_path),
              'layout_sha256': None, 'memo_file': None, 'memo_sha256': None,
              'generated_sha256': None, 'format': None, 'slide_count': inv['slide_count'],
              'user_additions': '',
              'applicability': memo_requirement(spec), 'pages': [], 'findings': [],
              'scope': 'Independent input, final native slide text and external memo are compared. '
                       'Matching text or hashes does not establish source truth, semantic agreement, or delivery timing.'}

    def issue(status, code, number, message):
        base = f'memo_{code}:{number or 0}'
        iid, suffix = base, 2
        while any(item['id'] == iid for item in report['findings']):
            iid, suffix = f'{base}:{suffix}', suffix + 1
        report['findings'].append({'id': iid, 'status': status, 'code': f'memo_{code}',
                                   'slide': number, 'message': message})

    def finish():
        for status, key in [('error', 'errors'), ('review_required', 'review_items'), ('unverified', 'unverified')]:
            report[key] = [f for f in report['findings'] if f['status'] == status]
        report['status'] = ('error' if report['errors'] else 'review_required' if report['review_items']
                            else 'unverified' if report['unverified'] else 'pass')
        return report

    if len(spec['slides']) != inv['slide_count']:
        issue('error', 'source_count', None, 'Independent input and final PPTX have different slide counts.')

    selected, conflicts = select_memo(pptx, memo)
    if conflicts:
        issue('error', 'ambiguous', None, 'Both Markdown and TXT memos exist; explicitly select the authoritative memo.')
        report['applicability']['status'] = 'applicable'
        return finish()
    if selected is None or not selected.is_file():
        if memo is not None or report['applicability']['required']:
            issue('error', 'missing', None, 'Required or explicitly supplied external presentation memo is missing.')
            report['applicability']['status'] = 'applicable'
        else:
            report['applicability']['status'] = 'not_applicable'
        return finish()
    report['applicability']['status'] = 'applicable'
    report.update(memo_file=str(selected), memo_sha256=sha256(selected))
    if selected.resolve().parent != pptx.resolve().parent:
        issue('error', 'directory', None, 'The presentation memo must be in the same directory as the final PPTX.')
    suffix = selected.suffix.lower()
    if suffix not in ('.md', '.txt'):
        issue('unverified', 'format', None, 'Unsupported memo format; preserve it without conversion and review manually.')
        return finish()
    format_name = 'markdown' if suffix == '.md' else 'text'
    report['format'] = format_name
    memo_pages, meta, parsing_error = parse_memo(selected.read_bytes().decode('utf-8'), format_name)
    report['generated_sha256'] = meta['generated_sha256']
    report['user_additions'] = meta['user_additions']
    if meta['user_additions']:
        issue('review_required', 'user_additions', None,
              'Review the preserved user_additions text alongside the final page records; confirm its scope and page references.')
    if meta['marker_status'] == 'invalid':
        issue('error', 'markers', None, parsing_error)
    elif meta['marker_status'] in ('absent', 'legacy'):
        issue('unverified', 'generated_hash_missing', None, 'Memo has no managed generated-content hash; retain and review the original.')
    elif meta['generated_sha256'] != meta['declared_generated_sha256']:
        issue('review_required', 'generated_hash', None,
              'Generated memo content has changed since generation. Preserve the edits and review the current content; automatic regeneration remains protected separately.')
    if parsing_error:
        if meta['marker_status'] != 'invalid':
            issue('unverified', 'format', None, parsing_error)
        return finish()

    sidecar = {}
    if layout_path.is_file():
        report['layout_sha256'] = sha256(layout_path)
        sidecar = json.loads(layout_path.read_text(encoding='utf-8'))
        if not isinstance(sidecar, dict):
            issue('error', 'layout_schema', None, 'Layout sidecar must be an object.')
            sidecar = {}
        if sidecar.get('pptx_sha256') != inv['pptx_sha256'] or sidecar.get('source_sha256') != report['deck_spec_sha256']:
            issue('error', 'layout_binding', None, 'Layout sidecar must identify the current PPTX and independent input hashes.')
        recorded = sidecar.get('memo', {})
        if not isinstance(recorded, dict) or not recorded:
            issue('unverified', 'receipt_missing', None, 'Layout sidecar has no memo receipt.')
        else:
            expected = {'file': selected.name, 'format': format_name, 'sha256': report['memo_sha256'],
                        'generated_sha256': report['generated_sha256']}
            for key, value in expected.items():
                if recorded.get(key) != value:
                    issue('review_required' if key in ('sha256', 'generated_sha256') else 'error',
                          'receipt_' + key, None,
                          f'Generation receipt {key} differs from the current memo. Review the current file and bind the decision to its new hashes.')
    else:
        issue('unverified', 'layout_missing', None, 'No layout sidecar is available for final slide-ID and memo receipt binding.')

    sources = spec['slides']
    if [p['number'] for p in memo_pages] != list(range(1, inv['slide_count'] + 1)):
        issue('error', 'page_order', None, 'Memo pages must cover the final presentation exactly once, in display order.')
    ids = [normal(p['id']) if p['id'] is not None else None for p in memo_pages]
    if any(not item for item in ids) or len(set(ids)) != len(ids):
        issue('error', 'ids', None, 'Memo slide IDs are missing or duplicated.')
    source_ids = [s.get('id') for s in sources]
    if any(not isinstance(item, str) or not item for item in source_ids) or len(set(source_ids)) != len(source_ids):
        issue('error', 'source_ids', None, 'Independent input slide IDs are missing or duplicated.')
    if sidecar and len(sidecar.get('slides', [])) != inv['slide_count']:
        issue('error', 'layout_count', None, 'Layout sidecar must contain every final slide exactly once.')

    for index, slide in enumerate(inv['slides']):
        number = index + 1
        source = sources[index] if index < len(sources) else {}
        matches = [p for p in memo_pages if p['number'] == number]
        memo_page = matches[0] if len(matches) == 1 else {}
        title = source.get('title') or spec.get('metadata', {}).get('title', '')
        notes = source.get('notes', '')
        note_text = notes.get('text', '') if isinstance(notes, dict) else notes
        evidence = notes.get('evidence', []) if isinstance(notes, dict) else []
        preparation = notes.get('preparation', []) if isinstance(notes, dict) else []
        claims = source.get('semantic_claims', [])
        semantic_texts = [c['text'] for c in claims if isinstance(c, dict) and c.get('text')]
        claim_texts = [source['message']] if isinstance(source.get('message'), str) and source['message'].strip() else semantic_texts
        record = {'number': number, 'id': source.get('id'), 'title': title,
                  'input': {'notes': note_text, 'evidence': evidence, 'sources': source.get('sources', []),
                            'notes_required': source.get('notes_required', []),
                            'message': source.get('message'), 'semantic_claims': claims},
                  'memo': memo_page, 'final_slide_text': slide['text'], 'final_embedded_notes': slide['notes']}
        report['pages'].append(record)
        if not memo_page:
            issue('error', 'page_missing', number, 'One unique memo page is required for this final slide.')
            continue
        if normal(memo_page.get('id')) != normal(source.get('id')):
            issue('error', 'id', number, 'Memo slide ID differs from independent input at this display position.')
        if normal(memo_page.get('title', '')) != normal(title):
            issue('error', 'title', number, 'Memo title differs from independent input.')
        layout_slides = sidecar.get('slides', [])
        if index < len(layout_slides) and layout_slides[index].get('id') != source.get('id'):
            issue('error', 'layout_id', number, 'Final layout slide ID differs from independent input order.')
        if index < len(layout_slides) and layout_slides[index].get('number') != number:
            issue('error', 'layout_number', number, 'Layout sidecar display numbering differs from the final page order.')
        titles = [e['text'] for e in slide['elements'] if e['role'] == 'title']
        if not titles:
            issue('unverified', 'final_title_role', number, 'Final title role is unavailable; verify title-to-page mapping manually.')
        elif normal(title) not in normal('\n'.join(titles)):
            issue('error', 'final_title', number, 'Final slide title does not match the memo and independent input.')
        visible_numbers = [normal(e['text']) for e in slide['elements'] if e['role'] == 'page']
        if not visible_numbers:
            issue('unverified', 'final_page_role', number, 'Final page-number role is unavailable.')
        elif visible_numbers != [str(number)]:
            issue('error', 'final_page', number, 'Visible slide number does not match its memo display page.')
        for heading in ('口頭補足', '根拠'):
            if heading not in memo_page.get('sections', []):
                issue('error', 'section_missing', number, f'Required memo section is missing: {heading}')
        required_notes = ([note_text] if isinstance(note_text, str) and note_text else []) + source.get('notes_required', [])
        for text in required_notes:
            if normal(text) not in normal(memo_page.get('text', '')):
                issue('error', 'text', number, f'Independent speaking note is absent from its memo page: {text!r}')
        for text in evidence:
            if normal(text) not in normal(memo_page.get('evidence', '')):
                issue('error', 'evidence', number, f'Independent evidence note is absent: {text!r}')
        for text in source.get('sources', []):
            if normal(text) not in normal(memo_page.get('sources', '')):
                issue('error', 'source', number, f'Independent source is absent from the memo: {text!r}')
        for text in claim_texts:
            if normal(text) not in normal(memo_page.get('claims', '')):
                issue('error', 'claim', number, f'Independent screen claim is absent from the memo: {text!r}')
        for text in list(dict.fromkeys(claim_texts + semantic_texts)):
            if normal(text) not in normal(slide['text']):
                issue('error', 'final_claim', number, f'Independent screen claim is absent from the final slide: {text!r}')
        embedded_required = required_notes + evidence + source.get('sources', []) + claim_texts
        for text in dict.fromkeys(embedded_required):
            if normal(text) not in normal(slide['notes']):
                issue('error', 'embedded_text', number, f'Independent speaking, evidence, source or claim text is absent from final PPTX notes: {text!r}')
        speaking_content = '\n'.join(str(memo_page.get(key, '')) for key in ('claims', 'text', 'sources', 'evidence'))
        for text in preparation:
            if normal(text) and not any(normal(text) in normal(item) for item in embedded_required):
                if normal(text) in normal(speaking_content) or normal(text) in normal(slide['notes']):
                    issue('error', 'preparation_leak', number, 'Preparation-only text is mixed into speaking notes; keep it in the private preparation record.')
        issue('review_required', 'semantics', number,
              'Compare the page record: final screen claims, speaking notes, evidence, source scope and evidence status. '
              'Confirm that shortening or moving conditions did not change the meaning; matching text is insufficient.')
    return finish()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pptx', type=Path)
    parser.add_argument('--deck-spec', type=Path, required=True)
    parser.add_argument('--memo', type=Path)
    parser.add_argument('--layout', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    try:
        result = check(args.pptx, args.deck_spec, args.memo, args.layout)
        output = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
        if args.report:
            protected = [args.pptx, args.deck_spec, args.layout or args.pptx.with_suffix('.layout.json')]
            selected, conflicts = select_memo(args.pptx, args.memo)
            protected.extend(conflicts)
            if selected:
                protected.append(selected)
            if args.report.resolve() in [p.resolve() for p in protected]:
                parser.error('--report must not overwrite an inspected source file')
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(output, encoding='utf-8')
        sys.stdout.write(output)
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError, zipfile.BadZipFile) as exc:
        parser.exit(1, f'Memo inspection failed: {exc}\n')
    return 1 if result['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
