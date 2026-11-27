#!/usr/bin/env python3
"""Correct known OOXML compatibility defects in a new copy of a PPTX.

This is a narrow package repair, not a renderer or deck finaliser. It preserves
every untouched ZIP member byte for byte and changes only the invalid table
anchor, presentation child order, orphan content-type entries, and the unused
third axis reference emitted for 2D bar/line charts by PptxGenJS.
It also gives notes/handout masters independent byte-identical themes when their
theme part is shared with another owner, which PowerPoint does not reliably open.
It does not renumber objects, rebuild slides, or establish PowerPoint validation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import posixpath
import re
import tempfile
import xml.parsers.expat as expat
from xml.etree.ElementTree import ParseError
from xml.sax.saxutils import escape, quoteattr
import zipfile

from check_pptx import inspect, parse_xml, relationship_owner, resolve_target

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
THEME_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.theme+xml"
# ECMA-376 PresentationML CT_Presentation sequence. Each child occurs at most once.
PRESENTATION_CHILDREN = (
    "sldMasterIdLst", "notesMasterIdLst", "handoutMasterIdLst", "sldIdLst",
    "sldSz", "notesSz", "smartTags", "embeddedFontLst", "custShowLst",
    "photoAlbum", "custDataLst", "kinsoku", "defaultTextStyle", "modifyVerifier", "extLst",
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def tag_end(data, start):
    """Locate an XML tag end without confusing a quoted '>' for its boundary."""
    quote = None
    for index in range(start, len(data)):
        value = data[index]
        if quote is not None:
            if value == quote:
                quote = None
        elif value in (34, 39):
            quote = value
        elif value == 62:
            return index + 1
    raise ValueError("Unterminated XML tag")


def xml_spans(data):
    """Get namespace-aware byte spans without reserialising user-authored XML."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\0" in data[:128]:
        raise ValueError("Compatibility repair supports UTF-8 XML only")
    declaration = re.match(br"(?:\xef\xbb\xbf)?\s*<\?xml\b[^?]*\?>", data)
    if declaration:
        encoding = re.search(br"encoding\s*=\s*(['\"])(.*?)\1", declaration.group())
        if encoding and encoding.group(2).lower() not in (b"utf-8", b"utf8", b"us-ascii"):
            raise ValueError("Compatibility repair supports UTF-8 XML only")
    parser = expat.ParserCreate(namespace_separator="}")
    stack, nodes = [], []

    def reject_doctype(*_):
        raise ValueError("DTD declarations are not supported in OOXML parts")

    def start(name, attributes):
        offset = parser.CurrentByteIndex
        node = {"tag": name, "attributes": attributes, "depth": len(stack),
                "start": offset, "start_end": tag_end(data, offset),
                "index": len(nodes), "parent": stack[-1]["index"] if stack else None}
        node["self_closing"] = data[offset:node["start_end"]].endswith(b"/>")
        nodes.append(node)
        stack.append(node)

    def end(_):
        node = stack.pop()
        offset = parser.CurrentByteIndex
        node["end"] = node["start_end"] if node["self_closing"] else tag_end(data, offset)

    parser.StartDoctypeDeclHandler = reject_doctype
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.Parse(data, True)
    return nodes


def replacements(data, edits):
    for start, end, value in sorted(edits, reverse=True):
        data = data[:start] + value + data[end:]
    return data


def relationship_part(owner):
    directory, basename = posixpath.split(owner)
    return posixpath.join(directory, "_rels", basename + ".rels")


def change_attribute(data, node, attribute, value):
    tag = data[node["start"]:node["start_end"]]
    match = re.search(rb"(?<=\s)" + attribute.encode("ascii") + rb"\s*=\s*(['\"])(.*?)\1", tag)
    if match is None:
        raise ValueError(f"Unsupported XML attribute representation: {attribute}")
    escaped = escape(value, {'"': "&quot;", "'": "&apos;"}).encode("utf-8")
    return replacements(data, [(node["start"] + match.start(2), node["start"] + match.end(2), escaped)])


def append_content_type(data, part):
    root = xml_spans(data)[0]
    if root["tag"] != CT + "}Types":
        raise ValueError("Unsupported content-types root")
    entry = (f'<Override xmlns="{CT}" PartName={quoteattr("/" + part)} '
             f'ContentType="{THEME_CONTENT_TYPE}"/>').encode("utf-8")
    if root["self_closing"]:
        qname = re.match(rb"<([^\s/>]+)", data[root["start"]:root["start_end"]]).group(1)
        return replacements(data, [(root["start_end"] - 2, root["start_end"], b">" + entry + b"</" + qname + b">")])
    end_start = data.rfind(b"</", root["start_end"], root["end"])
    return replacements(data, [(end_start, end_start, entry)])


def separate_auxiliary_themes(parts, update):
    """Separate shared auxiliary-master themes without altering their contents.

    A theme clone stays in the source directory, so its copied relationship
    targets still resolve to the same dependencies. Only auxiliary masters are
    redirected; ordinary slide/presentation theme sharing is left unchanged.
    """
    relationships = []
    for name, data in parts.items():
        if not name.endswith(".rels"):
            continue
        owner = relationship_owner(name)
        for node in xml_spans(data):
            attributes = node["attributes"]
            if node["tag"] == REL + "}Relationship" and attributes.get("Type") == R + "/theme" and attributes.get("TargetMode") != "External":
                relationships.append({"part": name, "owner": owner, "id": attributes.get("Id"),
                                      "target": resolve_target(owner, attributes.get("Target", ""))})
    auxiliary = set()
    for relation in relationships:
        owner = relation["owner"]
        if owner in parts and xml_spans(parts[owner])[0]["tag"] in (P + "}notesMaster", P + "}handoutMaster"):
            auxiliary.add(owner)
    for owner in auxiliary:
        if sum(relation["owner"] == owner for relation in relationships) != 1:
            raise ValueError(f"Cannot separate ambiguous auxiliary-master theme relationships: {owner}")
    for theme in sorted({relation["target"] for relation in relationships}):
        owners = {relation["owner"] for relation in relationships if relation["target"] == theme}
        candidates = sorted(owner for owner in owners if owner in auxiliary)
        for owner in candidates:
            if len(owners) <= 1:
                break
            if theme not in parts or xml_spans(parts[theme])[0]["tag"] != A + "}theme":
                raise ValueError(f"Cannot clone unsupported shared theme: {theme}")
            ctypes = xml_spans(parts["[Content_Types].xml"])
            declared = [node["attributes"].get("ContentType") for node in ctypes
                        if node["tag"] == CT + "}Override" and resolve_target("", node["attributes"].get("PartName", "")) == theme]
            if not declared:
                declared = [node["attributes"].get("ContentType") for node in ctypes
                            if node["tag"] == CT + "}Default" and node["attributes"].get("Extension") == "xml"]
            if declared != [THEME_CONTENT_TYPE]:
                raise ValueError(f"Cannot clone a theme without an unambiguous theme content type: {theme}")
            original_rels = relationship_part(theme)
            if original_rels in parts:
                for node in xml_spans(parts[original_rels]):
                    attributes = node["attributes"]
                    if node["tag"] != REL + "}Relationship" or attributes.get("TargetMode") == "External":
                        continue
                    target = resolve_target(theme, attributes.get("Target", ""))
                    if target not in parts or target in (theme, original_rels):
                        raise ValueError(f"Cannot safely clone theme dependencies: {original_rels}: {target}")
            directory = posixpath.dirname(theme)
            serial = 1
            while True:
                clone = posixpath.join(directory, f"theme{serial}.xml")
                clone_rels = relationship_part(clone)
                if clone not in parts and clone_rels not in parts:
                    break
                serial += 1
            finding = {"code": "shared_auxiliary_theme", "count": 1, "owner": owner, "source": theme, "clone": clone}
            update(clone, parts[theme], [finding])
            if original_rels in parts:
                update(clone_rels, parts[original_rels], [finding])
            relation = next(relation for relation in relationships if relation["owner"] == owner)
            nodes = [node for node in xml_spans(parts[relation["part"]])
                     if node["tag"] == REL + "}Relationship" and node["attributes"].get("Id") == relation["id"]]
            if len(nodes) != 1:
                raise ValueError(f"Cannot safely redirect duplicate theme relationship IDs: {owner}")
            target = posixpath.relpath(clone, posixpath.dirname(owner))
            update(relation["part"], change_attribute(parts[relation["part"]], nodes[0], "Target", target), [finding])
            update("[Content_Types].xml", append_content_type(parts["[Content_Types].xml"], clone), [finding])
            owners.remove(owner)


def normalise_parts(parts):
    """Return new member bytes and an audit trail; fail on ambiguous repairs."""
    parts = dict(parts)
    members = set(parts)
    trees, spans = {}, {}
    for name, data in parts.items():
        if name.endswith((".xml", ".rels")):
            spans[name] = xml_spans(data)
            trees[name], problems = parse_xml(data)
            if problems:
                raise ValueError(f"Unsupported XML in {name}: {'; '.join(problems)}")
    references = set()
    for name, tree in trees.items():
        if not name.endswith(".rels"):
            continue
        for relation in tree:
            if relation.get("TargetMode") != "External":
                target = resolve_target(relationship_owner(name), relation.get("Target", ""))
                references.add(target)
                if target not in members:
                    raise ValueError(f"Cannot repair a missing relationship target: {name}: {target}")
    changes = []

    def update(name, data, findings):
        before = parts.get(name)
        if data != before:
            changes.append({"part": name, "before_sha256": digest(before) if before is not None else None,
                            "after_sha256": digest(data), "changes": findings})
            parts[name] = data

    for name, nodes in spans.items():
        edits = []
        for node in nodes:
            if node["tag"] != A + "}tcPr" or node["attributes"].get("anchor") != "mid":
                continue
            tag = parts[name][node["start"]:node["start_end"]]
            match = re.search(br"(?<=\s)anchor\s*=\s*(['\"])mid\1", tag)
            if match is None:
                raise ValueError(f"Unsupported representation of table anchor: {name}")
            value = re.sub(br"(['\"])mid\1$", lambda m: m.group(1) + b"ctr" + m.group(1), match.group())
            edits.append((node["start"] + match.start(), node["start"] + match.end(), value))
        if edits:
            update(name, replacements(parts[name], edits), [{"code": "table_anchor_mid", "count": len(edits)}])

    name = "ppt/presentation.xml"
    if name not in spans or not spans[name] or spans[name][0]["tag"] != P + "}presentation":
        raise ValueError("Missing or unsupported PresentationML root")
    children = [node for node in spans[name] if node["depth"] == 1]
    ranks = {P + "}" + tag: rank for rank, tag in enumerate(PRESENTATION_CHILDREN)}
    seen = set()
    for node in children:
        if node["tag"] not in ranks or node["tag"] in seen:
            raise ValueError(f"Cannot reorder unknown or duplicate presentation child: {node['tag']}")
        seen.add(node["tag"])
    ordered = sorted(children, key=lambda node: ranks[node["tag"]])
    if children != ordered:
        data = parts[name]
        edits = [(old["start"], old["end"], data[new["start"]:new["end"]])
                 for old, new in zip(children, ordered)]
        update(name, replacements(data, edits), [{"code": "presentation_child_order", "count": 1,
               "before": [node["tag"].split("}")[-1] for node in children],
               "after": [node["tag"].split("}")[-1] for node in ordered]}])

    name = "[Content_Types].xml"
    if name not in spans or not spans[name] or spans[name][0]["tag"] != CT + "}Types":
        raise ValueError("Missing or unsupported content-types root")
    edits, removed, seen = [], [], set()
    for node in spans[name]:
        if node["depth"] != 1 or node["tag"] != CT + "}Override":
            continue
        target = node["attributes"].get("PartName", "")
        if not target.startswith("/") or "#" in target or "?" in target:
            raise ValueError(f"Unsupported content-type PartName: {target!r}")
        resolved = resolve_target("", target)
        if resolved in seen:
            raise ValueError(f"Duplicate content-type Override: {target}")
        seen.add(resolved)
        if resolved not in members:
            if resolved in references:
                raise ValueError(f"Cannot remove a referenced content-type Override: {target}")
            edits.append((node["start"], node["end"], b""))
            removed.append(target)
    if edits:
        update(name, replacements(parts[name], edits), [{"code": "orphan_content_type", "count": len(edits), "parts": removed}])

    for name in spans:
        # Recompute spans because table fixes could have changed byte offsets.
        nodes = xml_spans(parts[name])
        edits, removed = [], []
        for chart in nodes:
            if chart["tag"] not in (C + "}barChart", C + "}lineChart"):
                continue
            axes = [node for node in nodes if node["parent"] == chart["index"] and node["tag"] == C + "}axId"]
            if len(axes) <= 2:
                continue
            if len(axes) != 3:
                raise ValueError(f"Cannot repair ambiguous 2D chart axis references: {name}")
            plot = nodes[chart["parent"]] if chart["parent"] is not None else {}
            if plot.get("tag") != C + "}plotArea":
                raise ValueError(f"Cannot repair 2D chart outside a plot area: {name}")
            bound = {}
            for axis in nodes:
                if axis["parent"] == plot["index"] and axis["tag"] in (C + "}catAx", C + "}dateAx", C + "}valAx", C + "}serAx"):
                    ids = [node["attributes"].get("val") for node in nodes
                           if node["parent"] == axis["index"] and node["tag"] == C + "}axId"]
                    if len(ids) != 1 or not ids[0] or ids[0] in bound:
                        raise ValueError(f"Cannot repair ambiguous chart axis definitions: {name}")
                    bound[ids[0]] = axis["tag"].split("}")[-1]
            values = [node["attributes"].get("val") for node in axes]
            types = {bound.get(value) for value in values[:2]}
            references = [node for node in nodes if node["tag"] in (C + "}axId", C + "}crossAx")
                          and node["attributes"].get("val") == values[2]]
            if (any(not value for value in values) or len(set(values)) != 3
                    or types not in ({"catAx", "valAx"}, {"dateAx", "valAx"})
                    or values[2] in bound or len(references) != 1):
                raise ValueError(f"Cannot remove an active or ambiguous third 2D chart axis: {name}")
            edits.append((axes[2]["start"], axes[2]["end"], b""))
            removed.append({"chart": chart["tag"].split("}")[-1], "axis_id": values[2]})
        if edits:
            update(name, replacements(parts[name], edits), [{"code": "orphan_2d_chart_axis", "count": len(edits), "axes": removed}])
    separate_auxiliary_themes(parts, update)
    return parts, changes


def load_package(path):
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len({info.filename for info in infos}) != len(infos):
            raise ValueError("Duplicate ZIP member names cannot be safely repaired")
        if archive.testzip():
            raise ValueError("Corrupt ZIP member cannot be repaired")
        return infos, archive.comment, {info.filename: archive.read(info) for info in infos}


def write_package(path, infos, comment, parts):
    with zipfile.ZipFile(path, "w") as archive:
        archive.comment = comment
        for info in infos:
            archive.writestr(info, parts[info.filename])
        original_names = {info.filename for info in infos}
        for name, data in parts.items():
            if name not in original_names:
                archive.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)


def safe_new_path(path):
    path = path.absolute()
    if path.is_symlink():
        raise ValueError(f"Symbolic links are not supported for repair outputs: {path}")
    if path.exists():
        raise ValueError(f"Repair output already exists: {path}")
    return path.parent.resolve() / path.name


def repair(source, output, report_path):
    source = Path(source).absolute()
    if source.is_symlink() or not source.is_file():
        raise ValueError("Repair input must be an existing regular file, not a symbolic link")
    output, report_path = safe_new_path(Path(output)), safe_new_path(Path(report_path))
    if output == report_path or source.resolve() in (output.resolve(), report_path.resolve()):
        raise ValueError("Input, output and report paths must be distinct")
    source_hash = digest(source.read_bytes())
    infos, comment, original = load_package(source)
    parts, changes = normalise_parts(original)
    with tempfile.TemporaryDirectory(prefix="pptx-compat-") as temporary:
        candidate = Path(temporary) / "candidate.pptx"
        write_package(candidate, infos, comment, parts)
        structure = inspect(candidate)
        if structure["errors"]:
            raise ValueError("Repaired copy still has structural errors: " + "; ".join(structure["errors"]))
        data = candidate.read_bytes()
    if digest(source.read_bytes()) != source_hash:
        raise ValueError("Input changed during compatibility repair")
    structure["file"] = str(output)
    report = {"kind": "pptx_compatibility_repair", "input": str(source), "output": str(output),
              "input_sha256": source_hash, "output_sha256": digest(data), "changed_parts": changes,
              "structure": structure, "powerpoint_open": "not_performed"}
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creates prevent replacing a file that appeared after preflight.
    with output.open("xb") as stream:
        stream.write(data)
    try:
        with report_path.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except OSError:
        output.unlink()
        raise
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = repair(args.input, args.output, args.report)
    except (OSError, ValueError, zipfile.BadZipFile, expat.ExpatError, ParseError) as error:
        parser.exit(1, f"Compatibility repair stopped: {error}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
