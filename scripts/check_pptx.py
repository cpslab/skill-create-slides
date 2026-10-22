#!/usr/bin/env python3
"""Inspect PPTX structure without extracting files or requiring third-party modules.

Exit 0 means the package checks passed, not that visual quality or editing was verified.
"""

import argparse
from collections import Counter
from io import BytesIO
import json
from pathlib import Path
import posixpath
import sys
from urllib.parse import unquote
import xml.etree.ElementTree as ET
import zipfile

NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}

XSI_TYPE = "{http://www.w3.org/2001/XMLSchema-instance}type"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
# ECMA-376 CT_Presentation sequence and ST_TextAnchoringType. These checks are
# deliberately targeted; they do not claim full OOXML schema validation.
PRESENTATION_CHILD_ORDER = (
    "sldMasterIdLst", "notesMasterIdLst", "handoutMasterIdLst", "sldIdLst",
    "sldSz", "notesSz", "smartTags", "embeddedFontLst", "custShowLst",
    "photoAlbum", "custDataLst", "kinsoku", "defaultTextStyle",
    "modifyVerifier", "extLst",
)
TEXT_ANCHORS = frozenset(("t", "ctr", "b", "just", "dist"))


def parse_xml(data):
    """Parse XML and validate namespace bindings inside QName-valued xsi:type.

    ElementTree checks prefixes in element/attribute names, but not prefixes
    embedded in attribute values. Keep the actual per-element namespace scope.
    """
    scopes = [{"xml": "http://www.w3.org/XML/1998/namespace"}]
    pending = {}
    findings = []
    parser = ET.iterparse(BytesIO(data), events=("start-ns", "start", "end"))
    for event, value in parser:
        if event == "start-ns":
            prefix, uri = value
            pending[prefix] = uri
        elif event == "start":
            scope = {**scopes[-1], **pending}
            pending.clear()
            scopes.append(scope)
            qname = value.get(XSI_TYPE)
            if qname is not None:
                qname = qname.strip()
                if not qname or any(c.isspace() for c in qname) or qname.count(":") > 1:
                    findings.append(f"Malformed xsi:type QName: {qname!r}")
                elif ":" in qname:
                    prefix, local = qname.split(":")
                    if not local or not prefix or not scope.get(prefix):
                        findings.append(f"Undeclared xsi:type QName prefix: {qname!r}")
        else:
            scopes.pop()
    return parser.root, findings


def relationship_owner(name):
    if name == "_rels/.rels":
        return ""
    parent, basename = posixpath.split(name)
    return posixpath.join(posixpath.dirname(parent), basename[:-5])


def resolve_target(owner, target):
    target = unquote(target.split("#", 1)[0])
    return posixpath.normpath(
        target.lstrip("/") if target.startswith("/")
        else posixpath.join(posixpath.dirname(owner), target)
    )


def compatibility_errors(trees, members):
    """Find known repair-triggering errors without needing an external schema.

    Check exact OOXML namespaces, including text in notes/masters/charts, and
    leave unrelated extension markup and omitted optional attributes alone.
    """
    errors = []
    anchor_tags = {f'{{{NS["a"]}}}{tag}' for tag in ("bodyPr", "tcPr")}
    two_dimensional_axis_tags = {f'{{{NS["c"]}}}{tag}' for tag in ("barChart", "lineChart")}
    for name, tree in trees.items():
        counters = Counter()
        for node in tree.iter():
            if node.tag in two_dimensional_axis_tags:
                local = node.tag.rsplit("}", 1)[-1]
                counters[local] += 1
                axis_count = len(node.findall("c:axId", NS))
                if axis_count > 2:
                    errors.append(
                        f"Too many 2D chart axis references: {name}: "
                        f"c:{local}[{counters[local]}] has {axis_count} c:axId children; "
                        "maximum is 2")
            if node.tag not in anchor_tags:
                continue
            local = node.tag.rsplit("}", 1)[-1]
            counters[local] += 1
            anchor = node.get("anchor")
            # The XSD base is xsd:token; all enum values are single tokens.
            # Trim only XML whitespace, not arbitrary Unicode whitespace.
            if anchor is not None and anchor.strip(" \t\r\n") not in TEXT_ANCHORS:
                errors.append(
                    f"Invalid DrawingML text anchor: {name}: "
                    f"a:{local}[{counters[local]}] anchor={anchor!r}; "
                    "expected t, ctr, b, just, or dist")

    presentation = trees.get("ppt/presentation.xml")
    if presentation is not None and presentation.tag == f'{{{NS["p"]}}}presentation':
        ranks = {f'{{{NS["p"]}}}{local}': rank
                 for rank, local in enumerate(PRESENTATION_CHILD_ORDER)}
        seen = set()
        previous_rank = -1
        previous_local = None
        for child in presentation:
            if child.tag not in ranks:
                continue
            local = child.tag.rsplit("}", 1)[-1]
            rank = ranks[child.tag]
            if child.tag in seen:
                errors.append(
                    f"Duplicate presentation child: ppt/presentation.xml: p:{local}")
            seen.add(child.tag)
            if rank < previous_rank:
                errors.append(
                    "Invalid presentation child order: ppt/presentation.xml: "
                    f"p:{local} must precede p:{previous_local}")
            else:
                previous_rank = rank
                previous_local = local

    content_types = trees.get("[Content_Types].xml")
    if content_types is not None:
        seen_overrides = set()
        seen_defaults = set()
        for child in content_types:
            if child.tag == f"{{{CONTENT_TYPES_NS}}}Override":
                part_name = child.get("PartName", "")
                target = unquote(part_name.lstrip("/"))
                if target in seen_overrides:
                    errors.append(
                        f"Duplicate content type override: [Content_Types].xml: {part_name!r}")
                seen_overrides.add(target)
                if not part_name.startswith("/") or not target or target not in members:
                    errors.append(
                        "Missing content type override target: [Content_Types].xml: "
                        f"{part_name!r}")
            elif child.tag == f"{{{CONTENT_TYPES_NS}}}Default":
                extension = child.get("Extension", "").casefold()
                if extension in seen_defaults:
                    errors.append(
                        f"Duplicate content type default: [Content_Types].xml: {extension!r}")
                seen_defaults.add(extension)
    return errors


def powerpoint_theme_errors(trees, relationships):
    """Detect a PowerPoint compatibility constraint beyond XML schema validity.

    Notes/handout masters use separate theme parts. Sharing a theme between a
    presentation and its slide master is normal and is deliberately allowed.
    PowerPoint 16.111 for macOS repairs a notes master's shared theme even when
    the relationship graph and XML each pass the generic structural checks.
    The handout-master check follows the same preventive normalization policy;
    it has a synthetic regression test, not a separate application verification.
    """
    theme_owners = {}
    for owner, relations in relationships.items():
        for relation in relations.values():
            if relation["kind"] == "theme" and not relation["external"]:
                theme_owners.setdefault(relation["target"], set()).add(owner)
    errors = []
    for target, owners in theme_owners.items():
        if len(owners) < 2:
            continue
        for owner in sorted(owners):
            tree = trees.get(owner)
            master_kind = {
                f'{{{NS["p"]}}}notesMaster': "notes-master",
                f'{{{NS["p"]}}}handoutMaster': "handout-master",
            }.get(tree.tag) if tree is not None else None
            if master_kind is not None:
                errors.append(
                    f"PowerPoint {master_kind} theme sharing: {owner}: {target} "
                    f"is also owned by {', '.join(sorted(owners - {owner}))}; "
                    f"use a separate {master_kind} theme part")
    return errors


def inspect(path, expected=None):
    report = {
        "file": str(path), "errors": [], "review_items": [], "slides": [],
        "external_relationship_types": {},
        "visual_review": "not_performed", "application_editing_review": "not_performed",
    }
    errors = report["errors"]
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            members = set(names)
            if len(names) != len(members):
                errors.append("Duplicate ZIP entry names")
            corrupt = archive.testzip()
            if corrupt:
                errors.append(f"CRC failure: {corrupt}")
            for required in ("[Content_Types].xml", "_rels/.rels", "ppt/presentation.xml",
                             "ppt/_rels/presentation.xml.rels"):
                if required not in members:
                    errors.append(f"Missing required part: {required}")
            trees = {}
            for name in names:
                if name.endswith((".xml", ".rels")):
                    try:
                        trees[name], qname_errors = parse_xml(archive.read(name))
                        errors.extend(f"{message}: {name}" for message in qname_errors)
                    except ET.ParseError as error:
                        errors.append(f"Malformed XML: {name}: {error}")
            errors.extend(compatibility_errors(trees, members))
            relationships = {}
            external = Counter()
            for name, tree in trees.items():
                if not name.endswith(".rels"):
                    continue
                owner = relationship_owner(name)
                rels = relationships.setdefault(owner, {})
                for rel in tree:
                    rel_id = rel.get("Id")
                    target = rel.get("Target", "")
                    if rel_id in rels:
                        errors.append(f"Duplicate relationship ID: {owner}: {rel_id}")
                    is_external = rel.get("TargetMode") == "External"
                    kind = rel.get("Type", "").rsplit("/", 1)[-1]
                    resolved = target if is_external else resolve_target(owner, target)
                    rels[rel_id] = {"target": resolved, "external": is_external, "kind": kind}
                    if is_external:
                        external[kind] += 1
                    elif resolved not in members:
                        errors.append(f"Missing relationship target: {owner}: {resolved}")
            errors.extend(powerpoint_theme_errors(trees, relationships))
            report["external_relationship_types"] = dict(external)
            for name, tree in trees.items():
                if name.endswith(".rels"):
                    continue
                owner_rels = relationships.get(name, {})
                for node in tree.iter():
                    for attribute in ("id", "embed", "link"):
                        rel_id = node.get("{" + NS["r"] + "}" + attribute)
                        if rel_id and rel_id not in owner_rels:
                            errors.append(f"Missing relationship ID: {name}: {rel_id}")
            root = trees.get("ppt/presentation.xml")
            if root is None:
                report["errors"] = errors or ["Presentation XML is not readable"]
                return report
            if not root.tag.startswith("{" + NS["p"] + "}"):
                errors.append("Unsupported presentation XML namespace; manual inspection required")
            size = root.find("p:sldSz", NS)
            if size is not None:
                report["slide_size_emu"] = {k: size.get(k) for k in ("cx", "cy")}
            presentation_rels = relationships.get("ppt/presentation.xml", {})
            ordered = root.findall("p:sldIdLst/p:sldId", NS)
            report["slide_count"] = len(ordered)
            if not ordered:
                errors.append("No slides in presentation order")
            if expected is not None and len(ordered) != expected:
                errors.append(f"Expected {expected} slides, found {len(ordered)}")
            seen = set()
            for number, entry in enumerate(ordered, 1):
                rel_id = entry.get("{" + NS["r"] + "}id")
                relation = presentation_rels.get(rel_id, {})
                name = relation.get("target", "")
                slide = trees.get(name)
                if slide is None or relation.get("external") or relation.get("kind") != "slide":
                    errors.append(f"Unreadable slide at position {number}: {name}")
                    continue
                if name in seen:
                    errors.append(f"Repeated slide in presentation order: {name}")
                seen.add(name)
                object_ids = [node.get("id") for node in slide.findall(".//p:cNvPr", NS)]
                duplicates = [key for key, count in Counter(object_ids).items() if count > 1]
                if duplicates:
                    errors.append(f"Duplicate object IDs on slide {number}: {', '.join(str(x) for x in duplicates)}")
                texts = [node.text for node in slide.findall(".//a:t", NS) if node.text]
                counts = {
                    "text_runs": len(texts),
                    "shapes": len(slide.findall(".//p:sp", NS)),
                    "connectors": len(slide.findall(".//p:cxnSp", NS)),
                    "pictures": len(slide.findall(".//p:pic", NS)),
                    "tables": len(slide.findall(".//a:tbl", NS)),
                    "charts": len(slide.findall(".//c:chart", NS)),
                }
                notes = [rel["target"] for rel in relationships.get(name, {}).values()
                         if rel["kind"] == "notesSlide" and not rel["external"]]
                fonts = sorted({node.get("typeface") for node in slide.iter()
                                if node.get("typeface")})
                report["slides"].append({
                    "number": number, "part": name, "hidden": slide.get("show") == "0",
                    **counts, "notes_parts": notes, "explicit_fonts": fonts,
                })
                if not texts:
                    report["review_items"].append(
                        f"Slide {number}: no native text; verify intended editability and layout inheritance")
            report["notes_count"] = sum(bool(s["notes_parts"]) for s in report["slides"])
            if external:
                report["review_items"].append("External relationships exist; verify availability and intended use")
    except (OSError, zipfile.BadZipFile, RuntimeError, ValueError) as error:
        errors.append(f"Cannot inspect package: {error}")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pptx", type=Path)
    parser.add_argument("--expect-slides", type=int)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.expect_slides is not None and args.expect_slides < 1:
        parser.error("--expect-slides must be positive")
    report = inspect(args.pptx, args.expect_slides)
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        if args.report.resolve() == args.pptx.resolve():
            parser.error("--report must not overwrite the input PPTX")
        try:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(output, encoding="utf-8")
        except OSError as error:
            parser.error(f"Cannot write report: {error}")
    sys.stdout.write(output)
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
