#!/usr/bin/env python3
"""PPTXの観測値を標準ライブラリで抽出する。描画・完全な継承解決は行わない。"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import posixpath
import re
import struct
import xml.etree.ElementTree as ET
import zipfile

from check_pptx import NS, relationship_owner, resolve_target

EMU_PER_INCH = 914400
EMU_PER_PT = 12700


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local(tag):
    return tag.rsplit('}', 1)[-1]


def properties(node):
    if node is None:
        return {}
    out = dict(node.attrib)
    for child in node:
        out.setdefault(local(child.tag), []).append(dict(child.attrib))
    return out


def dimensions(data):
    """画像ヘッダーのピクセル寸法。非対応形式は推測しない。"""
    if data.startswith(b'\x89PNG\r\n\x1a\n') and len(data) >= 24:
        return list(struct.unpack('>II', data[16:24]))
    if data[:6] in (b'GIF87a', b'GIF89a') and len(data) >= 10:
        return list(struct.unpack('<HH', data[6:10]))
    if data.startswith(b'\xff\xd8'):
        i = 2
        while i + 9 <= len(data):
            if data[i] != 255:
                i += 1
                continue
            marker = data[i + 1]
            i += 2
            if marker in (0xD8, 0xD9):
                continue
            length = int.from_bytes(data[i:i + 2], 'big')
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                return [int.from_bytes(data[i + 5:i + 7], 'big'), int.from_bytes(data[i + 3:i + 5], 'big')]
            if length < 2:
                break
            i += length
    return None


def parse_text(body):
    if body is None:
        return {'text': '', 'paragraphs': [], 'font_sizes_pt': [], 'unresolved_font': False}
    paragraphs, sizes, unresolved = [], [], False
    defaults = body.find('a:lstStyle/a:defPPr/a:defRPr', NS)
    for paragraph in body.findall('a:p', NS):
        ppr = paragraph.find('a:pPr', NS)
        default = paragraph.find('a:pPr/a:defRPr', NS)
        level = ppr.get('lvl', '0') if ppr is not None else '0'
        level_default = body.find(f'a:lstStyle/a:lvl{int(level) + 1}pPr/a:defRPr', NS)
        runs, chunks = [], []
        for run in paragraph:
            tag = local(run.tag)
            if tag == 'br':
                chunks.append('\n')
                continue
            if tag not in ('r', 'fld'):
                continue
            text = ''.join(run.itertext()) if run.find('a:t', NS) is None else run.findtext('a:t', '', NS)
            rp = run.find('a:rPr', NS)
            candidates = [rp, default, level_default, defaults]
            size = next((float(x.get('sz')) / 100 for x in candidates if x is not None and x.get('sz')), None)
            if text:
                if size is None:
                    unresolved = True
                else:
                    sizes.append(size)
            chunks.append(text)
            runs.append({'text': text, 'font_pt': size, 'properties': properties(rp),
                         'size_origin': 'local' if size is not None else 'unknown: layout/master/theme inheritance'})
        paragraphs.append({'text': ''.join(chunks), 'runs': runs, 'properties': properties(ppr)})
    return {'text': '\n'.join(p['text'] for p in paragraphs), 'paragraphs': paragraphs,
            'font_sizes_pt': sizes, 'unresolved_font': unresolved,
            'body_properties': properties(body.find('a:bodyPr', NS))}


def cache_values(parent, path):
    target = parent.find(path, NS)
    if target is None:
        return []
    points = target.findall('.//c:pt', NS)
    return [p.findtext('c:v', '', NS) for p in sorted(points, key=lambda p: int(p.get('idx', '0')))]


def chart_data(root):
    series = []
    for ser in root.findall('.//c:ser', NS):
        tx = ser.find('c:tx', NS)
        name = None
        if tx is not None:
            name = tx.findtext('c:v', None, NS)
            if name is None:
                values = cache_values(tx, 'c:strRef/c:strCache')
                name = values[0] if values else None
        categories = cache_values(ser, 'c:cat') or cache_values(ser, 'c:xVal')
        values = cache_values(ser, 'c:val') or cache_values(ser, 'c:yVal')
        series.append({'name': name, 'categories': categories,
                       'values': [float(v) if re.fullmatch(r'[-+\d.eE]+', v or 'x') else v for v in values],
                       'formulas': [n.text for n in ser.findall('.//c:f', NS)],
                       'name_origin': 'chart_xml' if name is not None else 'unknown'})
    fonts = [float(n.get('sz')) / 100 for n in root.iter() if n.get('sz')]
    axes = [{'kind': local(ax.tag), 'id': ax.find('c:axId', NS).get('val') if ax.find('c:axId', NS) is not None else None,
             'minimum': ax.find('c:scaling/c:min', NS).get('val') if ax.find('c:scaling/c:min', NS) is not None else None,
             'maximum': ax.find('c:scaling/c:max', NS).get('val') if ax.find('c:scaling/c:max', NS) is not None else None,
             'text': [n.text for n in ax.findall('.//a:t', NS)]}
            for ax in root.findall('.//c:catAx', NS) + root.findall('.//c:valAx', NS)]
    titles = [{'text': ''.join(n.text or '' for n in title.findall('.//a:t', NS) + title.findall('.//c:v', NS)),
               'reference_formulas': [n.text for n in title.findall('.//c:f', NS)]}
              for title in root.findall('.//c:title', NS)]
    return {'series': series, 'axes': axes, 'titles': titles, 'font_sizes_pt': fonts,
            'text': [n.text for n in root.findall('.//a:t', NS)],
            'external_data_relationship': root.find('c:externalData', NS).get('{' + NS['r'] + '}id') if root.find('c:externalData', NS) is not None else None}


def extract(path):
    result = {'schema_version': 1, 'file': str(path), 'pptx_sha256': sha256(path),
              'slides': [], 'media': [], 'limitations': [
                  'Font size is resolved only from local run, paragraph and list defaults; unresolved layout/master/theme inheritance is unknown.',
                  'Nested group transforms, rotation and flipping require separate verification.',
                  'Raster text, rendered wrapping, video playback and application editing are not verified by XML extraction.'],
              'rendering': {'status': 'unverified', 'reason': 'This extractor does not render slides.'}}
    with zipfile.ZipFile(path) as archive:
        trees = {n: ET.fromstring(archive.read(n)) for n in archive.namelist() if n.endswith(('.xml', '.rels'))}
        rels = {}
        for name, tree in trees.items():
            if name.endswith('.rels'):
                owner = relationship_owner(name)
                rels[owner] = {r.get('Id'): {'kind': r.get('Type', '').rsplit('/', 1)[-1],
                                             'target': r.get('Target') if r.get('TargetMode') == 'External' else resolve_target(owner, r.get('Target', '')),
                                             'external': r.get('TargetMode') == 'External'} for r in tree}
        presentation = trees['ppt/presentation.xml']
        size = presentation.find('p:sldSz', NS)
        result['slide_size_in'] = [int(size.get(k)) / EMU_PER_INCH for k in ('cx', 'cy')]
        media_by_part = {}
        for name in archive.namelist():
            if name.startswith('ppt/media/'):
                data = archive.read(name)
                media = {'part': name, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'pixels': dimensions(data)}
                result['media'].append(media)
                media_by_part[name] = media
        result['inherited_parts'] = {name: {'sha256': hashlib.sha256(archive.read(name)).hexdigest(),
                                            'name': tree.get('name') or (tree.find('p:cSld', NS).get('name') if tree.find('p:cSld', NS) is not None else None),
                                            'fonts': sorted({n.get('typeface') for n in tree.iter() if n.get('typeface')}),
                                            'explicit_font_sizes_pt': sorted({float(n.get('sz')) / 100 for n in tree.iter() if n.get('sz')}),
                                            'colours': sorted({n.get('val') for n in tree.findall('.//a:srgbClr', NS)})}
                                     for name, tree in trees.items() if name.startswith(('ppt/slideLayouts/', 'ppt/slideMasters/', 'ppt/theme/')) and name.endswith('.xml')}
        for number, entry in enumerate(presentation.findall('p:sldIdLst/p:sldId', NS), 1):
            part = rels['ppt/presentation.xml'][entry.get('{' + NS['r'] + '}id')]['target']
            root = trees[part]
            slide_rels = rels.get(part, {})
            layout = next((r['target'] for r in slide_rels.values() if r['kind'] == 'slideLayout'), None)
            note_parts = [r['target'] for r in slide_rels.values() if r['kind'] == 'notesSlide']
            notes = ['\n'.join(parse_text(s.find('p:txBody', NS))['text'] for s in trees[n].findall('.//p:sp', NS)
                               if s.find('p:nvSpPr/p:nvPr/p:ph', NS) is None or s.find('p:nvSpPr/p:nvPr/p:ph', NS).get('type') not in ('sldNum', 'hdr', 'ftr', 'dt')) for n in note_parts]
            slide = {'number': number, 'internal_id': entry.get('id'), 'part': part, 'hidden': root.get('show') == '0',
                     'layout_part': layout, 'layout_name': result['inherited_parts'].get(layout, {}).get('name'),
                     'notes': '\n'.join(notes), 'notes_parts': note_parts, 'elements': [],
                     'relationships': slide_rels, 'timing_xml': ET.tostring(root.find('p:timing', NS), encoding='unicode') if root.find('p:timing', NS) is not None else None}
            def visit(container, grouped=False):
                for node in container:
                    kind = local(node.tag)
                    if kind not in ('sp', 'pic', 'graphicFrame', 'cxnSp', 'grpSp'):
                        continue
                    nv = node.find('.//p:cNvPr', NS)
                    name = nv.get('name', '') if nv is not None else ''
                    role_match = re.search(r'(?:^|\|)role:([^|]+)', name)
                    id_match = re.search(r'(?:^|\|)id:([^|]+)', name)
                    xfrm = node.find('p:xfrm', NS) if kind == 'graphicFrame' else node.find('p:spPr/a:xfrm', NS)
                    if kind == 'grpSp':
                        xfrm = node.find('p:grpSpPr/a:xfrm', NS)
                    bounds = None
                    if xfrm is not None:
                        off, ext = xfrm.find('a:off', NS), xfrm.find('a:ext', NS)
                        if off is not None and ext is not None:
                            bounds = [int(off.get('x', 0)) / EMU_PER_INCH, int(off.get('y', 0)) / EMU_PER_INCH,
                                      int(ext.get('cx', 0)) / EMU_PER_INCH, int(ext.get('cy', 0)) / EMU_PER_INCH]
                    data = {'shape_id': nv.get('id') if nv is not None else None, 'id': id_match.group(1) if id_match else None,
                            'name': name, 'role': role_match.group(1) if role_match else None, 'kind': kind,
                            'bounds_in': bounds, 'transform': properties(xfrm), 'grouped': grouped,
                            'transform_resolved': not grouped and kind != 'grpSp' and not (xfrm is not None and any(xfrm.get(k) not in (None, '0', 'false') for k in ('rot', 'flipH', 'flipV'))),
                            'colours': sorted({n.get('val') for n in node.findall('.//a:srgbClr', NS)}),
                            **parse_text(node.find('p:txBody', NS))}
                    data['placeholder'] = properties(node.find('.//p:ph', NS)) or None
                    table = node.find('.//a:tbl', NS)
                    if table is not None:
                        data['kind'] = 'table'
                        data['table'] = {'columns_in': [int(c.get('w')) / EMU_PER_INCH for c in table.findall('a:tblGrid/a:gridCol', NS)],
                                         'rows': [[parse_text(c.find('a:txBody', NS)) for c in r.findall('a:tc', NS)] for r in table.findall('a:tr', NS)],
                                         'row_heights_in': [int(r.get('h')) / EMU_PER_INCH for r in table.findall('a:tr', NS)],
                                         'cell_properties': [[properties(c.find('a:tcPr', NS)) for c in r.findall('a:tc', NS)] for r in table.findall('a:tr', NS)]}
                        data['text'] = '\n'.join(c['text'] for r in data['table']['rows'] for c in r)
                        data['font_sizes_pt'] = [v for r in data['table']['rows'] for c in r for v in c['font_sizes_pt']]
                        data['unresolved_font'] = any(c['unresolved_font'] for r in data['table']['rows'] for c in r)
                    chart = node.find('.//c:chart', NS)
                    if chart is not None:
                        target = slide_rels[chart.get('{' + NS['r'] + '}id')]['target']
                        data.update(kind='chart', chart=chart_data(trees[target]), chart_part=target)
                    if kind == 'pic':
                        blip = node.find('.//a:blip', NS)
                        rid = blip.get('{' + NS['r'] + '}embed') if blip is not None else None
                        relation = slide_rels.get(rid, {})
                        media = media_by_part.get(relation.get('target'), {})
                        crop = node.find('.//a:srcRect', NS)
                        data['media'] = {**media, 'relationship_id': rid, 'crop': properties(crop)}
                        if bounds and media.get('pixels') and bounds[2] > 0 and bounds[3] > 0:
                            cropv = properties(crop)
                            data['media']['effective_ppi'] = [media['pixels'][0] * (1 - (int(cropv.get('l', 0)) + int(cropv.get('r', 0))) / 100000) / bounds[2],
                                                              media['pixels'][1] * (1 - (int(cropv.get('t', 0)) + int(cropv.get('b', 0))) / 100000) / bounds[3]]
                        data['video'] = [r for key, r in slide_rels.items() if r['kind'] in ('video', 'media') and any(n.get('{' + NS['r'] + '}link') == key or n.get('{' + NS['r'] + '}embed') == key for n in node.iter())]
                    if kind == 'cxnSp':
                        data['connections'] = {'from': properties(node.find('p:nvCxnSpPr/p:cNvCxnSpPr/a:stCxn', NS)),
                                               'to': properties(node.find('p:nvCxnSpPr/p:cNvCxnSpPr/a:endCxn', NS)),
                                               'head': properties(node.find('p:spPr/a:ln/a:headEnd', NS)),
                                               'tail': properties(node.find('p:spPr/a:ln/a:tailEnd', NS))}
                    slide['elements'].append(data)
                    if kind == 'grpSp':
                        visit(node, True)
            visit(root.find('p:cSld/p:spTree', NS))
            slide['text'] = '\n'.join(e['text'] for e in slide['elements'] if e['text'])
            slide['citation_markers'] = re.findall(r'\[[\d,\-– ]+\]', slide['text'])
            result['slides'].append(slide)
        result['slide_count'] = len(result['slides'])
        result['counts'] = dict(Counter(e['kind'] for s in result['slides'] for e in s['elements']))
    return result


def write_reports(inventory, directory):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'reference-inventory.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + '\n')
    sizes = Counter(v for s in inventory['slides'] for e in s['elements'] for v in e['font_sizes_pt'])
    colours = Counter(v for s in inventory['slides'] for e in s['elements'] for v in e['colours'])
    style = ['# 参照の観測値', '', f"SHA-256: `{inventory['pptx_sha256']}`", '', f"実寸: {inventory['slide_size_in']} inch / {inventory['slide_count']} pages", '',
             '頻度は観測値であり、役割・採用値・下限を意味しない。レイアウト名だけでページの目的を分類しない。', '', '## 明示フォントサイズ（pt）', '',
             *[f'- {size:g}: {count} runs' for size, count in sizes.most_common()], '', '## 明示色', '', *[f'- #{colour}: {count} elements' for colour, count in colours.most_common()], '', '## 未検証', '', *['- ' + x for x in inventory['limitations']]]
    (directory / 'reference-style.md').write_text('\n'.join(style) + '\n')
    catalog = ['# 全ページの抽出カタログ', '', '抽出内容の観測記録。意味分類と表示品質は別にレビューする。', '']
    for slide in inventory['slides']:
        catalog += [f"## {slide['number']}（内部ID {slide['internal_id']} / layout={slide['layout_name']}）", '',
                    f"要素: {dict(Counter(e['kind'] for e in slide['elements']))}", '', slide['text'], '', '### ノート', '', slide['notes'], '']
    (directory / 'slide-catalog.md').write_text('\n'.join(catalog) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pptx', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        inventory = extract(args.pptx)
        write_reports(inventory, args.output_dir)
    except (OSError, KeyError, ValueError, ET.ParseError, zipfile.BadZipFile) as exc:
        parser.exit(1, f'Extraction failed: {exc}\n')
    print(json.dumps({k: inventory[k] for k in ('pptx_sha256', 'slide_count', 'slide_size_in', 'counts')}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
