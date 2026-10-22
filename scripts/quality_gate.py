#!/usr/bin/env python3
"""構造・配置・全ページ目視を最終ファイルのSHA-256に束ねる。未検証は完成にしない。"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from check_pptx import inspect
from extract_reference import sha256
from check_memo import check as check_memo


def layout_report_errors(report, slide_count):
    """Reject role sidecars and incomplete reports, even when their PPTX hash matches."""
    if not isinstance(report, dict):
        return ['Layout inspection report must be an object.']
    required = {'schema_version', 'pptx_sha256', 'slide_count', 'findings', 'checks',
                'errors', 'review_items', 'unverified', 'status'}
    if not required.issubset(report):
        return ['Supply the check_layout.py report, not the generation .layout.json sidecar.']
    if report['schema_version'] != 1 or report['slide_count'] != slide_count:
        return ['Layout report schema or slide count does not match the presentation.']
    if any(not isinstance(report[key], list) for key in
           ('findings', 'checks', 'errors', 'review_items', 'unverified')):
        return ['Layout findings, checks and severity groups must be arrays.']
    findings = report['findings']
    if any(not isinstance(f, dict) or not isinstance(f.get('id'), str) or not f['id']
           or f.get('status') not in ('error', 'review_required', 'unverified')
           or not isinstance(f.get('message'), str) for f in findings):
        return ['Layout findings must have an ID, recognised status and message.']
    if len({f['id'] for f in findings}) != len(findings):
        return ['Layout finding IDs must be unique.']
    for severity, key in [('error', 'errors'), ('review_required', 'review_items'),
                          ('unverified', 'unverified')]:
        if report[key] != [f for f in findings if f['status'] == severity]:
            return ['Layout severity groups do not agree with the findings.']
    status = ('error' if report['errors'] else 'review_required' if report['review_items']
              else 'unverified' if report['unverified'] else 'pass')
    if report['status'] != status:
        return ['Layout report status does not agree with the findings.']
    checks = report['checks']
    if any(not isinstance(c, dict) or type(c.get('slide')) is not int or
           any(type(c.get(k)) is not int or c[k] < 0 for k in
               ('native_tables', 'native_charts', 'native_connectors')) for c in checks):
        return ['Layout checks must include slide numbers and native-element counts.']
    if sorted(c['slide'] for c in checks) != list(range(1, slide_count + 1)):
        return ['Layout inspection must cover every slide exactly once.']
    return []


def memo_report_errors(report, current):
    """A receipt cannot replace a current inspection or omit its semantic review items."""
    if not isinstance(report, dict) or report.get('report_kind') != 'presentation_memo':
        return ['Supply the check_memo.py report for the current independent input and external memo.']
    keys = ('schema_version', 'pptx_sha256', 'deck_spec_sha256', 'layout_sha256',
            'memo_sha256', 'generated_sha256', 'slide_count', 'format', 'applicability',
            'pages', 'user_additions', 'findings', 'errors', 'review_items', 'unverified', 'status')
    errors = [f'Memo report {key} is missing, stale or incomplete.' for key in keys
              if key not in report or report[key] != current[key]]
    for key in ('file', 'deck_spec_file', 'memo_file'):
        expected, recorded = current.get(key), report.get(key)
        if bool(expected) != bool(recorded) or (expected and Path(expected).resolve() != Path(recorded).resolve()):
            errors.append(f'Memo report {key} does not identify the inspected file.')
    return errors


def evaluate(pptx, layout_report, visual_review=None, review_base=None,
             deck_spec=None, memo_report=None, memo=None):
    current = sha256(pptx)
    structure = inspect(pptx)
    issues = []
    def add(code, message, status='error'):
        issues.append({'code': code, 'status': status, 'message': message})
    if structure['errors']:
        for error in structure['errors']:
            add('structure', error)
    malformed = layout_report_errors(layout_report, structure.get('slide_count', 0))
    for message in malformed:
        add('layout_report_schema', message)
    if malformed:
        # Keep collecting visual issues without trusting malformed finding entries.
        layout_report = {'pptx_sha256': layout_report.get('pptx_sha256')
                         if isinstance(layout_report, dict) else None, 'findings': []}
    if layout_report.get('pptx_sha256') != current:
        add('layout_sha', 'Layout report is missing or belongs to another PPTX.')
    if deck_spec is not None:
        try:
            source = json.loads(Path(deck_spec).read_text(encoding='utf-8'))
            source_content_sha = hashlib.sha256(json.dumps(source, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
            recorded_source_sha = layout_report.get('deck_spec_content_sha256')
            if not recorded_source_sha:
                add('layout_input_sha', 'Layout report has no independent-input content hash; rerun the layout inspection.', 'unverified')
            elif recorded_source_sha != source_content_sha:
                add('layout_input_sha', 'Layout report belongs to a different independent input specification.')
        except (OSError, ValueError) as exc:
            add('layout_input_sha', f'Independent input could not be inspected: {exc}', 'unverified')
    checked_memo = None
    if memo_report is None:
        add('memo_report_missing', 'External memo correspondence has not been inspected; supply --deck-spec and --memo-report.', 'unverified')
    elif deck_spec is None:
        add('memo_input_missing', 'The current independent input file is required to verify the memo report.', 'unverified')
    else:
        try:
            # Reinspect actual files: matching hashes alone must not accept a report
            # whose page records or required semantic findings have been removed.
            recorded = memo_report if isinstance(memo_report, dict) else {}
            # Without an explicit --memo, rediscover the sibling file rather than
            # silently treating a recorded path as permission to choose among originals.
            checked_memo = check_memo(pptx, deck_spec, memo, recorded.get('layout_file'))
            malformed_memo = memo_report_errors(memo_report, checked_memo)
            for message in malformed_memo:
                add('memo_report_schema', message)
            if malformed_memo:
                checked_memo = None
        except (OSError, ValueError, KeyError, TypeError) as exc:
            add('memo_inspection', f'Current memo inspection failed: {exc}', 'unverified')
    visual = visual_review or {}
    if deck_spec is not None:
        try:
            if visual.get('deck_spec_sha256') != sha256(deck_spec):
                add('visual_input_sha', 'Visual and source-meaning review must identify the current independent-input SHA-256.', 'unverified')
        except OSError as exc:
            add('visual_input_sha', f'Independent input could not be read: {exc}', 'unverified')
    if visual.get('pptx_sha256') != current:
        add('visual_sha', 'All-page visual review must identify the current PPTX SHA-256.', 'unverified')
    pages = visual.get('pages', [])
    numbers = [p.get('number') for p in pages]
    if sorted(n for n in numbers if isinstance(n, int)) != list(range(1, structure.get('slide_count', 0) + 1)):
        add('visual_pages', 'Visual review must contain every page exactly once.', 'unverified')
    image_records = []
    for page in pages:
        number = page.get('number')
        if page.get('status') != 'pass' or not page.get('reviewer') or not page.get('notes'):
            add('visual_incomplete', f'Page {number}: pass, reviewer/method and concrete review notes are required.', 'unverified')
        image_path = Path(page.get('image', ''))
        if not image_path.is_absolute():
            image_path = Path(review_base or '.') / image_path
        if not image_path.is_file():
            add('visual_image_missing', f'Page {number}: reviewed image does not exist.', 'unverified')
        else:
            image_sha = sha256(image_path)
            if page.get('image_sha256') != image_sha:
                add('visual_image_sha', f'Page {number}: reviewed image SHA-256 missing or stale.', 'unverified')
            image_records.append({'number': number, 'image': str(image_path), 'image_sha256': image_sha})
    resolutions = {r.get('id'): r for r in visual.get('resolved_findings', [])}
    known = ({f.get('id') for f in layout_report.get('findings', [])}
             | {'structure:' + item for item in structure.get('review_items', [])}
             | {f.get('id') for f in (checked_memo or {}).get('findings', [])})
    for iid in resolutions:
        if iid not in known:
            add('unknown_resolution', f'Resolution {iid} does not belong to this layout report.')
    for finding in layout_report.get('findings', []):
        resolution = resolutions.get(finding.get('id'), {})
        if finding['status'] == 'error':
            add('layout_error', f'{finding["id"]}: {finding["message"]}')
        elif not (resolution.get('status') == 'pass' and resolution.get('reason') and resolution.get('method') and resolution.get('evidence')):
            add('unresolved_finding', f'{finding["id"]}: {finding["message"]}', finding['status'])
    for finding in (checked_memo or {}).get('findings', []):
        resolution = resolutions.get(finding['id'], {})
        if finding['status'] == 'error':
            add('memo_error', f'{finding["id"]}: {finding["message"]}')
        elif not (resolution.get('status') == 'pass' and resolution.get('reason')
                  and resolution.get('method') and resolution.get('evidence')
                  and resolution.get('memo_sha256') == checked_memo['memo_sha256']
                  and resolution.get('deck_spec_sha256') == checked_memo['deck_spec_sha256']):
            add('memo_unresolved', f'{finding["id"]}: {finding["message"]} '
                'Resolution must identify the current memo and independent-input SHA-256 values.', finding['status'])
    for item in structure.get('review_items', []):
        # External relationships and inherited native text need explicit disposition too.
        resolution = resolutions.get('structure:' + item, {})
        if not (resolution.get('status') == 'pass' and resolution.get('reason') and resolution.get('method') and resolution.get('evidence')):
            add('structure_review', item, 'review_required')
    application = visual.get('application_checks', {})
    if application.get('required') and application.get('status') != 'pass':
        add('application', 'Required target-application operations have not passed.', 'unverified')
    result = {'schema_version': 1, 'file': str(pptx), 'pptx_sha256': current,
              'status': 'pass' if not issues else 'not_complete', 'verified_complete': not issues,
              'structure': structure, 'issues': issues, 'images': image_records,
              'memo': checked_memo or {'status': 'unverified', 'reason': 'No valid current memo inspection was supplied.'},
              'application_checks': application or {'status': 'unverified', 'required': False,
                    'reason': 'No application editing/playback evidence was supplied; native XML inspection is distinct.'},
              'scope': 'This gate binds recorded checks to files. It does not independently establish the truth of human/agent review statements.'}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pptx', type=Path)
    parser.add_argument('--layout-report', type=Path, required=True)
    parser.add_argument('--visual-review', type=Path)
    parser.add_argument('--deck-spec', type=Path)
    parser.add_argument('--memo-report', type=Path)
    parser.add_argument('--memo', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    try:
        layout = json.loads(args.layout_report.read_text())
        visual = json.loads(args.visual_review.read_text()) if args.visual_review else {}
        memo_report = json.loads(args.memo_report.read_text()) if args.memo_report else None
        result = evaluate(args.pptx, layout, visual, args.visual_review.parent if args.visual_review else None,
                          deck_spec=args.deck_spec, memo_report=memo_report, memo=args.memo)
        output = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
        if args.report:
            inputs = [args.pptx, args.layout_report, args.visual_review, args.deck_spec, args.memo_report, args.memo]
            # Protect both possible originals even when inspection fails before
            # selecting one (for example, MD/TXT ambiguity or a malformed receipt).
            inputs += [Path(str(args.pptx.with_suffix('')) + '-発表メモ' + ext) for ext in ('.md', '.txt')]
            inputs.append(args.pptx.with_suffix('.layout.json'))
            if result.get('memo', {}).get('memo_file'):
                inputs.append(Path(result['memo']['memo_file']))
            if result.get('memo', {}).get('layout_file'):
                inputs.append(Path(result['memo']['layout_file']))
            if args.report.resolve() in [p.resolve() for p in inputs if p]:
                parser.error('--report must not overwrite an inspected source or report')
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(output)
        sys.stdout.write(output)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'Quality gate failed: {exc}\n')
    return 0 if result['verified_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
