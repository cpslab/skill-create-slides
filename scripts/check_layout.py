#!/usr/bin/env python3
"""役割付きPPTXの配置・編集可能性・入力照合。終了値0も目視完了を意味しない。"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

from extract_reference import extract, sha256

SEVERITIES = ('error', 'review_required', 'unverified')
DEFAULT_MIN = {'title': 24, 'body': 16, 'question': 28, 'header': 11, 'running_header': 11,
               'table': 14, 'label': 14, 'diagram-node': 14, 'source': 8.5, 'page': 9}


def normal(text):
    return ' '.join(str(text).split())


def direction_matches(connections, direction):
    expected = {'forward': (False, True), 'backward': (True, False),
                'both': (True, True), 'none': (False, False),
                'to': (False, True), 'directed': (False, True)}
    actual = tuple(connections.get(end, {}).get('type') not in (None, 'none') for end in ('head', 'tail'))
    return direction in expected and actual == expected[direction]


def overlap(a, b):
    return max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])) * max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))


def find_spec(spec, number):
    slides = spec.get('slides', [])
    return next((s for s in slides if s.get('number') == number), slides[number - 1] if number <= len(slides) else {})


def source_texts(source):
    """Read authored input fields, independently of generator-produced sidecars."""
    texts = []
    for key in ('title', 'question', 'premise', 'message', 'interpretation', 'caption', 'label'):
        if isinstance(source.get(key), str) and source[key]:
            texts.append(source[key])
    for key in ('blocks', 'steps', 'takeaways'):
        texts.extend(v for v in source.get(key, []) if isinstance(v, str))
    for item in source.get('conditions', []) + source.get('items', []):
        for key in ('title', 'text', 'description'):
            if item.get(key):
                texts.append(item[key])
    for node in source.get('diagram', {}).get('nodes', []):
        if node.get('text'):
            texts.append(node['text'])
    if source.get('chart', {}).get('scope_label'):
        texts.append(source['chart']['scope_label'])
    def objects(items):
        for item in items:
            if item.get('text'):
                texts.append(item['text'])
            objects(item.get('children', []))
    objects(source.get('objects', []))
    for element in source.get('elements', []):
        if element.get('kind') == 'text' and element.get('text'):
            texts.append(element['text'])
    return texts


def source_tables(source):
    tables = [source['table']] if source.get('table') else []
    tables += [e['data'] for e in source.get('elements', []) if e.get('kind') == 'table']
    tables += [e for e in source.get('objects', []) if e.get('type') == 'table']
    result = []
    for table in tables:
        rows = []
        for row in table['rows']:
            cells = row.get('cells', []) if isinstance(row, dict) else row
            rows.append([normal(c.get('text', '\n'.join(p.get('text', '') for p in c.get('paragraphs', [])))) if isinstance(c, dict) else normal(c) for c in cells])
        result.append(rows)
    return result


def source_charts(source):
    charts = [source['chart']] if source.get('chart') else []
    charts += [e['data'] for e in source.get('elements', []) if e.get('kind') == 'chart']
    charts += [e for e in source.get('objects', []) if e.get('type') == 'chart']
    return charts


def check(path, profile=None, deck_spec=None, layout=None):
    profile, deck_spec, layout = profile or {}, deck_spec or {}, layout or {}
    inv = extract(path)
    report = {'schema_version': 1, 'file': str(path), 'pptx_sha256': inv['pptx_sha256'],
              'slide_count': inv['slide_count'], 'findings': [], 'checks': [],
              'scope': 'Generated roles and explicit OOXML properties; visual and source judgement remain separate.',
              'errors': [], 'review_items': [], 'unverified': []}
    def issue(severity, code, number, element, message):
        eid = str(element or 'slide')
        base = f'{code}:{number or 0}:{eid}'
        iid = base
        count = 2
        while any(x['id'] == iid for x in report['findings']):
            iid = f'{base}:{count}'
            count += 1
        report['findings'].append({'id': iid, 'status': severity, 'code': code, 'slide': number,
                                   'element': element, 'message': message})
    minimums = {**DEFAULT_MIN, **profile.get('minimum_font_pt', {})}
    if 'running_header' in minimums and 'header' not in profile.get('minimum_font_pt', {}):
        minimums['header'] = minimums['running_header']
    tolerance = profile.get('geometry_tolerance_in', profile.get('bounds_tolerance_in', 0.02))
    for source_name, source in [('layout', layout), ('deck_spec', deck_spec)]:
        expected_sha = source.get('pptx_sha256')
        if expected_sha and expected_sha != inv['pptx_sha256']:
            issue('error', 'stale_evidence', None, source_name, 'PPTX SHA-256 does not match this evidence.')
    if not layout:
        issue('unverified', 'layout_missing', None, None, 'No layout sidecar; input-to-element mapping is unavailable.')
    if not deck_spec:
        issue('unverified', 'source_missing', None, None, 'No independent input specification; source meaning cannot be checked.')
    expected_count = len(deck_spec.get('slides', [])) or len(layout.get('slides', []))
    if expected_count and expected_count != inv['slide_count']:
        issue('error', 'slide_count', None, None, f'Expected {expected_count}; found {inv["slide_count"]}.')
    dimensions = profile.get('slide_size_in')
    if dimensions and any(abs(float(a) - float(b)) > tolerance for a, b in zip(dimensions, inv['slide_size_in'])):
        issue('error', 'slide_size', None, None, 'Slide dimensions do not match the selected profile.')
    width, height = inv['slide_size_in']
    page_values = []
    for slide in inv['slides']:
        number = slide['number']
        expected = find_spec(layout, number)
        source = find_spec(deck_spec, number)
        elements = slide['elements']
        by_id = {e['id']: e for e in elements if e['id']}
        by_shape_id = {e['shape_id']: e for e in elements}
        expected_elements = expected.get('expected_elements', [])
        # A role map is explicit metadata, never inferred from arbitrary shape names.
        for e in elements:
            match = next((x for x in expected_elements if x.get('id') == e['id'] and e['id']), None)
            if match is not None and not e['role']:
                e['role'] = match.get('role')
        pages = [e for e in elements if e['role'] == 'page']
        if len(pages) != 1:
            issue('error' if layout else 'unverified', 'page_count', number, None, f'Expected exactly one role:page, found {len(pages)}.')
        for page in pages:
            page_values.append((number, normal(page['text'])))
            if normal(page['text']) != str(number):
                issue('error', 'page_number', number, page['id'], f'Visible page number must be {number}, got {page["text"]!r}.')
            if page['kind'] != 'sp':
                issue('error', 'page_native', number, page['id'], 'Visible page number is not native text.')
        if slide['hidden'] and not source.get('hidden', False):
            issue('error', 'hidden_slide', number, None, 'Unexpected hidden slide.')
        for e in elements:
            eid, role = e['id'] or e['shape_id'], e['role']
            if not role:
                issue('unverified', 'role_unknown', number, eid, 'Element role is not declared; size thresholds are not inferred from its name.')
            if e['grouped'] or e['kind'] == 'grpSp' or not e['transform_resolved']:
                issue('unverified', 'transform_unsupported', number, eid, 'Group, rotation or flip transform is not resolved by this checker.')
            bounds = e['bounds_in']
            if bounds is None:
                issue('unverified', 'bounds_unknown', number, eid, 'No local transform; inherited placement is unknown.')
            elif e['transform_resolved']:
                x, y, w, h = bounds
                if x < -tolerance or y < -tolerance or x + w > width + tolerance or y + h > height + tolerance or w < 0 or h < 0:
                    issue('error', 'out_of_bounds', number, eid, f'Bounds {bounds} exceed slide {[width, height]}.')
            if e['unresolved_font']:
                issue('unverified', 'font_inheritance', number, eid, 'Some text has unresolved layout/master/theme font size.')
            if role in minimums:
                small = sorted({v for v in e['font_sizes_pt'] if v + 0.01 < minimums[role]})
                if small:
                    issue('error', 'font_too_small', number, eid, f'{role}: {small} pt below adopted minimum {minimums[role]} pt.')
            body_props = e.get('body_properties', {})
            if 'normAutofit' in body_props:
                for fit in body_props['normAutofit']:
                    scale = float(fit.get('fontScale', '100000')) / 100000
                    if scale < 1:
                        issue('error', 'auto_shrink', number, eid, f'Automatic text shrinking fontScale={scale}.')
            if e['kind'] == 'table':
                table = e['table']
                row_lengths = {len(row) for row in table['rows']}
                if len(row_lengths) > 1 or (row_lengths and next(iter(row_lengths)) != len(table['columns_in'])):
                    issue('error', 'table_dimensions', number, eid, 'Table grid and cell counts disagree.')
                for ri, row in enumerate(table['rows']):
                    for ci, cell in enumerate(row):
                        if cell['unresolved_font']:
                            issue('unverified', 'table_font_inheritance', number, f'{eid}[{ri},{ci}]', 'Table cell font size is unresolved.')
            if e['kind'] == 'chart':
                if not e['chart']['series']:
                    issue('error', 'chart_empty', number, eid, 'Native chart has no readable series cache.')
                if any(not t['text'].strip() and not t['reference_formulas'] for t in e['chart'].get('titles', [])):
                    issue('error', 'chart_empty_title', number, eid, 'An explicitly empty native chart/axis title can display an application placeholder. Omit the title element when no title is intended.')
                if not e['chart']['font_sizes_pt']:
                    issue('unverified', 'chart_font_inheritance', number, eid, 'Chart text formatting is inherited.')
                issue('review_required', 'chart_meaning', number, eid, 'Confirm units, population, aggregation, axis and interpretation against the source.')
            if e['kind'] == 'pic' and role not in ('logo', 'background'):
                issue('review_required', 'raster_content', number, eid, 'Confirm raster labels, cropping and truthful content in the final render against the input.')
                ppi = e.get('media', {}).get('effective_ppi')
                if ppi and min(ppi) < profile.get('minimum_image_ppi', 100):
                    issue('review_required', 'image_resolution', number, eid, f'Effective resolution {ppi}; inspect important labels at presentation size.')
            if e['kind'] == 'pic' and e.get('video'):
                issue('unverified', 'video_playback', number, eid, 'Embedded video requires target-application playback, mute, loop and transition checks.')
        for want in expected_elements:
            eid = want.get('id')
            actual = by_id.get(eid)
            if actual is None:
                issue('error', 'element_missing', number, eid, 'Expected native element is missing.')
                continue
            expected_kind = want.get('kind')
            aliases = {'text': 'sp', 'shape': 'sp', 'image': 'pic', 'connector': 'cxnSp', 'native-table': 'table', 'native-chart': 'chart'}
            if expected_kind and aliases.get(expected_kind, expected_kind) != actual['kind']:
                issue('error', 'native_kind', number, eid, f'Expected {expected_kind}, found {actual["kind"]}; flattening does not satisfy editability.')
            if want.get('role') and actual['role'] != want['role']:
                issue('error', 'role_mismatch', number, eid, f'Expected role {want["role"]}, found {actual["role"]}.')
            if 'text' in want and normal(actual['text']) != normal(want['text']):
                issue('error', 'text_mismatch', number, eid, 'Native text differs from the fixed input-to-element mapping.')
            if want.get('bounds_in') and actual['bounds_in'] and actual['transform_resolved']:
                if any(abs(float(a) - float(b)) > tolerance for a, b in zip(want['bounds_in'], actual['bounds_in'])):
                    issue('error', 'placement_mismatch', number, eid, f'Placement differs from declared geometry by more than {tolerance} inch.')
            if want.get('table') and actual.get('table'):
                rows = [[normal(c['text']) for c in row] for row in actual['table']['rows']]
                wanted_rows = [[normal(c.get('text', '') if isinstance(c, dict) else c) for c in row] for row in want['table']['rows']]
                if rows != wanted_rows:
                    issue('error', 'table_values', number, eid, 'Table cell values do not match input.')
            if want.get('chart') and actual.get('chart'):
                wanted_series = want['chart'].get('series', [])
                actual_series = actual['chart']['series']
                if len(wanted_series) != len(actual_series):
                    issue('error', 'chart_series', number, eid, 'Series count differs from input.')
                else:
                    for index, (ws, ac) in enumerate(zip(wanted_series, actual_series)):
                        categories = ws.get('categories', want['chart'].get('categories'))
                        if normal(ws.get('name', '')) != normal(ac['name'] or ''):
                            issue('error', 'chart_name', number, eid, f'Series {index} name differs from XML cache.')
                        if categories is not None and list(map(normal, categories)) != list(map(normal, ac['categories'])):
                            issue('error', 'chart_categories', number, eid, f'Series {index} categories differ from input.')
                        values = ws.get('values', [])
                        if len(values) != len(ac['values']) or any(not isinstance(b, (int, float)) or not math.isclose(float(a), b, rel_tol=1e-9, abs_tol=1e-9) for a, b in zip(values, ac['values'])):
                            issue('error', 'chart_values', number, eid, f'Series {index} values differ from input.')
            if want.get('asset', {}).get('sha256') and actual.get('media', {}).get('sha256') != want['asset']['sha256']:
                issue('error', 'asset_hash', number, eid, 'Embedded asset bytes differ from the declared input asset.')
            edge = want.get('edge')
            if edge:
                connections = actual.get('connections', {})
                for endpoint in ('from', 'to'):
                    target = by_shape_id.get(connections.get(endpoint, {}).get('id'), {})
                    if target.get('id') != edge.get(endpoint):
                        issue('error', 'diagram_connection', number, eid, f'{endpoint} does not connect to {edge.get(endpoint)}.')
                if edge.get('direction') is not None and not direction_matches(connections, edge['direction']):
                    issue('error', 'diagram_direction', number, eid, 'Start/end arrowheads do not match the declared direction.')
        for edge in source.get('diagram', {}).get('edges', []):
            actual = by_id.get(edge.get('id'), {})
            connections = actual.get('connections', {})
            for endpoint in ('from', 'to'):
                actual_node = by_shape_id.get(connections.get(endpoint, {}).get('id'), {})
                if actual_node.get('id') != edge.get(endpoint):
                    issue('error', 'source_diagram_connection', number, edge.get('id'), f'Native {endpoint} does not match the independent input edge.')
            if not direction_matches(connections, edge.get('direction', 'forward')):
                issue('error', 'source_diagram_direction', number, edge.get('id'), 'Start/end arrowheads differ from the independent input direction.')
        # Independent source text is checked in addition to the generated mapping.
        required = source_texts(source) + list(source.get('required_text', [])) + list(expected.get('required_text', [])) + list(source.get('sources', []))
        if source.get('type') == 'cover':
            required.extend(deck_spec.get('metadata', {}).get(k, '') for k in ('title', 'authors', 'venue', 'fictional_label'))
        if source.get('type') == 'summary' and deck_spec.get('metadata', {}).get('contact'):
            required.append(deck_spec['metadata']['contact'])
        for index, wanted_rows in enumerate(source_tables(source)):
            tables = [e for e in elements if e.get('table')]
            if index >= len(tables):
                issue('error', 'source_table_missing', number, None, 'Input requires an editable table that is absent.')
            elif wanted_rows != [[normal(c['text']) for c in row] for row in tables[index]['table']['rows']]:
                issue('error', 'source_table_values', number, tables[index]['id'], 'Native cells differ from the independent source input.')
        for index, wanted_chart in enumerate(source_charts(source)):
            charts = [e for e in elements if e.get('chart')]
            if index >= len(charts):
                issue('error', 'source_chart_missing', number, None, 'Input requires an editable chart that is absent.')
                continue
            actual_series = charts[index]['chart']['series']
            wanted_series = wanted_chart.get('series', [])
            if len(wanted_series) != len(actual_series):
                issue('error', 'source_chart_series', number, charts[index]['id'], 'Series count differs from independent source input.')
            for ws, ac in zip(wanted_series, actual_series):
                cats = ws.get('categories', wanted_chart.get('categories'))
                values = ws.get('values', [])
                if normal(ws.get('name', '')) != normal(ac['name'] or '') or cats is not None and list(map(normal, cats)) != list(map(normal, ac['categories'])):
                    issue('error', 'source_chart_labels', number, charts[index]['id'], 'Native series/category labels differ from independent input.')
                if len(values) != len(ac['values']) or any(not isinstance(b, (int, float)) or not math.isclose(float(a), b, rel_tol=1e-9, abs_tol=1e-9) for a, b in zip(values, ac['values'])):
                    issue('error', 'source_chart_values', number, charts[index]['id'], 'Native chart values differ from independent input even if sidecar agrees.')
        for text in required:
            if normal(text) not in normal(slide['text']):
                issue('error', 'required_text', number, None, f'Required input text absent: {text!r}')
        source_notes = source.get('notes')
        if isinstance(source_notes, dict):
            source_notes = source_notes.get('text')
        for text in list(source.get('notes_required', [])) + list(expected.get('notes_required', [])) + ([source_notes] if isinstance(source_notes, str) and source_notes else []):
            if normal(text) not in normal(slide['notes']):
                issue('error', 'notes_required', number, None, f'Required note absent: {text!r}')
        if slide['notes']:
            issue('review_required', 'notes_meaning', number, None, 'Confirm notes against source and final page mapping; presence alone is not semantic validation.')
        claims = source.get('semantic_claims', expected.get('semantic_claims', []))
        for claim in claims:
            if not claim.get('source') or claim.get('status') not in ('measured', 'illustrative', 'hypothesis', 'plan', 'reported', 'interpretation'):
                issue('error', 'claim_provenance', number, None, 'Each claim needs source and explicit evidence status.')
            for key in ('text', 'unit', 'subject', 'aggregation', 'visible_condition'):
                if claim.get(key) and normal(claim[key]) not in normal(slide['text']):
                    issue('error', 'claim_condition', number, None, f'Semantic {key} not visible: {claim[key]!r}')
        if source or expected:
            issue('review_required', 'source_meaning', number, None, 'Confirm claims, conditions, citations and evidence status against input; text equality cannot establish meaning.')
        permitted = {frozenset(pair) for pair in expected.get('allowed_overlaps', [])}
        for i, left in enumerate(elements):
            if not left['bounds_in'] or not left['transform_resolved'] or left['role'] in ('background', 'rule', 'diagram-edge'):
                continue
            for right in elements[i + 1:]:
                if not right['bounds_in'] or not right['transform_resolved'] or right['role'] in ('background', 'rule', 'diagram-edge'):
                    continue
                if frozenset([left['id'], right['id']]) in permitted:
                    continue
                area = overlap(left['bounds_in'], right['bounds_in'])
                if area > tolerance * tolerance:
                    issue('review_required', 'overlap', number, f'{left["id"] or left["shape_id"]}+{right["id"] or right["shape_id"]}',
                          'Bounding boxes intersect; verify visible content or declare a justified allowed overlap.')
        report['checks'].append({'slide': number, 'native_tables': sum(e['kind'] == 'table' for e in elements),
                                 'native_charts': sum(e['kind'] == 'chart' for e in elements),
                                 'native_connectors': sum(e['kind'] == 'cxnSp' for e in elements)})
    for value in set(v for _, v in page_values):
        numbers = [n for n, v in page_values if v == value]
        if len(numbers) > 1:
            issue('error', 'page_duplicate', None, value, f'Visible number duplicated on slides {numbers}.')
    for status, key in [('error', 'errors'), ('review_required', 'review_items'), ('unverified', 'unverified')]:
        report[key] = [f for f in report['findings'] if f['status'] == status]
    report['status'] = 'error' if report['errors'] else 'review_required' if report['review_items'] else 'unverified' if report['unverified'] else 'pass'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pptx', type=Path)
    parser.add_argument('--profile', type=Path)
    parser.add_argument('--deck-spec', type=Path)
    parser.add_argument('--layout', type=Path, help='Default: <PPTX stem>.layout.json if it exists')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    layout_path = args.layout or args.pptx.with_suffix('.layout.json')
    def read(path):
        return json.loads(path.read_text()) if path and path.exists() else {}
    try:
        for label, path in [('profile', args.profile), ('deck-spec', args.deck_spec), ('layout', args.layout)]:
            if path and not path.is_file():
                raise ValueError(f'Explicit --{label} file does not exist: {path}')
        report = check(args.pptx, read(args.profile), read(args.deck_spec), read(layout_path))
    except (OSError, KeyError, ValueError) as exc:
        parser.exit(1, f'Layout check failed: {exc}\n')
    output = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.report:
        if args.report.resolve() == args.pptx.resolve():
            parser.error('--report must not overwrite the PPTX')
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output)
    sys.stdout.write(output)
    return 1 if report['errors'] else 2 if report['findings'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
