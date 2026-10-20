#!/usr/bin/env python3
"""Embed supplied MP4 files behind role-tagged posters in newly generated decks.

This creates native media relationships and minimal playback timing. It neither
transcodes video nor proves playback in a presentation application.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import posixpath
import tempfile
import xml.etree.ElementTree as ET
import zipfile

NS = {
    'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'p14': 'http://schemas.microsoft.com/office/powerpoint/2010/main',
}
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
MEDIA_REL = 'http://schemas.microsoft.com/office/2007/relationships/media'
MEDIA_EXTENSION = '{DAA4B4D4-6D71-4841-9C94-3DE7FCFB9230}'
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


def child(parent, prefix, name, **attrs):
    return ET.SubElement(parent, f'{{{NS[prefix]}}}{name}', attrs)


def slide_parts(parts):
    relationships = ET.fromstring(parts['ppt/_rels/presentation.xml.rels'])
    targets = {r.get('Id'): r for r in relationships}
    presentation = ET.fromstring(parts['ppt/presentation.xml'])
    result = []
    for entry in presentation.findall('p:sldIdLst/p:sldId', NS):
        rel = targets[entry.get(f'{{{NS["r"]}}}id')]
        if rel.get('TargetMode') == 'External':
            raise ValueError('External slide relationships are unsupported')
        raw_target = rel.get('Target', '')
        target = posixpath.normpath(raw_target.lstrip('/') if raw_target.startswith('/') else posixpath.join('ppt', raw_target))
        if target not in parts or not target.startswith('ppt/slides/'):
            raise ValueError('Invalid slide relationship target')
        result.append(target)
    return result


def relationship(root, rel_type, target):
    existing = {r.get('Id') for r in root}
    i = 1
    while f'rIdMedia{i}' in existing:
        i += 1
    rid = f'rIdMedia{i}'
    ET.SubElement(root, f'{{{REL}}}Relationship',
                  {'Id': rid, 'Type': rel_type, 'Target': target})
    return rid


def playback_timing(root, movies):
    if root.find('p:timing', NS) is not None:
        raise ValueError('Existing timing is unsupported; embed only into a newly generated candidate')
    timing = ET.Element(f'{{{NS["p"]}}}timing')
    common = child(child(child(timing, 'p', 'tnLst'), 'p', 'par'),
                   'p', 'cTn', id='1', dur='indefinite', restart='never', nodeType='tmRoot')
    children = child(common, 'p', 'childTnLst')
    for i, (shape_id, settings) in enumerate(movies, 2):
        media = child(child(children, 'p', 'video'), 'p', 'cMediaNode',
                      vol='0' if settings['muted'] else '100000',
                      mute='1' if settings['muted'] else '0')
        attrs = {'id': str(i), 'fill': 'hold', 'display': '0'}
        if settings['loop']:
            attrs['repeatCount'] = 'indefinite'
        node = child(media, 'p', 'cTn', **attrs)
        cond_attrs = {'delay': '0'}
        if not settings['autoplay']:
            cond_attrs['evt'] = 'onClick'
        condition = child(child(node, 'p', 'stCondLst'), 'p', 'cond', **cond_attrs)
        if not settings['autoplay']:
            child(child(condition, 'p', 'tgtEl'), 'p', 'spTgt', spid=shape_id)
        child(child(media, 'p', 'tgtEl'), 'p', 'spTgt', spid=shape_id)
    extension = root.find('p:extLst', NS)
    root.insert(list(root).index(extension) if extension is not None else len(root), timing)


def embed(candidate, spec, input_dir):
    candidate, input_dir = Path(candidate), Path(input_dir)
    if candidate.is_symlink() or not candidate.is_file() or candidate.suffix.lower() != '.pptx':
        raise ValueError('Candidate must be a regular generated PPTX file')
    with zipfile.ZipFile(candidate) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    ordered_parts = slide_parts(parts)
    changes = []
    for page in spec['slides']:
        media_specs = page.get('media', [])
        if not media_specs:
            continue
        number = page['number']
        if not isinstance(number, int) or not 1 <= number <= len(ordered_parts):
            raise ValueError('Media slide number is outside the generated deck')
        part = ordered_parts[number - 1]
        root = ET.fromstring(parts[part])
        tree = root.find('p:cSld/p:spTree', NS)
        rel_name = posixpath.join(posixpath.dirname(part), '_rels', posixpath.basename(part) + '.rels')
        rels = ET.fromstring(parts[rel_name]) if rel_name in parts else ET.Element(f'{{{REL}}}Relationships')
        movies = []
        used_posters = set()
        for media in media_specs:
            poster_id = media['poster_id']
            if poster_id in used_posters:
                raise ValueError('Only one video may be attached to a poster')
            used_posters.add(poster_id)
            settings = {key: media.get(key, True) for key in ('autoplay', 'loop', 'muted')}
            if any(type(value) is not bool for value in settings.values()):
                raise ValueError('autoplay, loop and muted must be JSON booleans')
            matches = [pic for pic in tree.findall('p:pic', NS)
                       if pic.find('p:nvPicPr/p:cNvPr', NS).get('name', '').split('|')[-1] == f'id:{poster_id}']
            if len(matches) != 1:
                raise ValueError(f'Expected exactly one generated poster with ID {poster_id}')
            pic = matches[0]
            nonvisual = pic.find('p:nvPicPr', NS)
            properties = nonvisual.find('p:nvPr', NS)
            if properties is None:
                properties = child(nonvisual, 'p', 'nvPr')
            if properties.find('a:videoFile', NS) is not None or properties.find('.//p14:media', NS) is not None:
                raise ValueError('Poster already has a video')
            source = input_dir / media['path']
            movie_bytes = source.read_bytes()
            if source.suffix.lower() != '.mp4' or len(movie_bytes) < 12 or movie_bytes[4:8] != b'ftyp':
                raise ValueError('Only supplied MP4 files with an ftyp header are supported')
            digest = hashlib.sha256(movie_bytes).hexdigest()
            if media.get('sha256') and digest != media['sha256']:
                raise ValueError('Video changed after the layout was authored')
            target = f'ppt/media/video-{digest}.mp4'
            if target in parts and parts[target] != movie_bytes:
                raise ValueError('Media package name collision')
            parts[target] = movie_bytes
            relative = posixpath.relpath(target, posixpath.dirname(part))
            video_rid = relationship(rels, NS['r'] + '/video', relative)
            media_rid = relationship(rels, MEDIA_REL, relative)
            child(properties, 'a', 'videoFile', **{f'{{{NS["r"]}}}link': video_rid})
            extensions = properties.find('p:extLst', NS)
            if extensions is None:
                extensions = child(properties, 'p', 'extLst')
            child(child(extensions, 'p', 'ext', uri=MEDIA_EXTENSION), 'p14', 'media',
                  **{f'{{{NS["r"]}}}embed': media_rid})
            c_nv = nonvisual.find('p:cNvPr', NS)
            hyperlink = c_nv.find('a:hlinkClick', NS)
            if hyperlink is None:
                hyperlink = child(c_nv, 'a', 'hlinkClick')
            hyperlink.set('action', 'ppaction://media')
            hyperlink.attrib.pop(f'{{{NS["r"]}}}id', None)
            movies.append((c_nv.get('id'), settings))
            changes.append({'slide': number, 'poster_id': poster_id, 'package_part': target,
                            'sha256': digest, 'bytes': len(movie_bytes), **settings,
                            'codec_check': 'unverified', 'application_playback': 'unverified'})
        playback_timing(root, movies)
        parts[part] = ET.tostring(root, encoding='utf-8', xml_declaration=True)
        parts[rel_name] = ET.tostring(rels, encoding='utf-8', xml_declaration=True)
    if not changes:
        return {'embedded_media': [], 'application_playback': 'unverified'}
    content_types = ET.fromstring(parts['[Content_Types].xml'])
    mp4_types = [e for e in content_types if e.get('Extension', '').lower() == 'mp4']
    if mp4_types and any(e.get('ContentType') != 'video/mp4' for e in mp4_types):
        raise ValueError('Existing MP4 content type is incompatible')
    if not mp4_types:
        ET.SubElement(content_types, f'{{{CT}}}Default', {'Extension': 'mp4', 'ContentType': 'video/mp4'})
    ET.register_namespace('', CT)
    parts['[Content_Types].xml'] = ET.tostring(content_types, encoding='utf-8', xml_declaration=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.embedded-', suffix='.pptx', dir=candidate.parent, delete=False) as temp:
            temp_name = temp.name
        with zipfile.ZipFile(temp_name, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, data in parts.items():
                archive.writestr(name, data)
        os.replace(temp_name, candidate)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)
    return {'embedded_media': changes, 'application_playback': 'unverified'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('layout', type=Path)
    parser.add_argument('--input-dir', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    report = embed(args.candidate, json.loads(args.layout.read_text()), args.input_dir)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
