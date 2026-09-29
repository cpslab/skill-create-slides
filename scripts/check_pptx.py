#!/usr/bin/env python3
"""Inspect PPTX structure without extracting files or requiring third-party modules.

Exit 0 means the package checks passed, not that visual quality or editing was verified.
"""

import argparse
from collections import Counter
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
                        trees[name] = ET.fromstring(archive.read(name))
                    except ET.ParseError as error:
                        errors.append(f"Malformed XML: {name}: {error}")
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
