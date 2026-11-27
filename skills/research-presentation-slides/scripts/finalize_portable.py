#!/usr/bin/env python3
"""Finalise generated PptxGenJS connectors and run the shared structural check.

Only used on a generated candidate, never on a manually edited presentation.
PptxGenJS exports lines as shapes; attach native connector endpoints from the
authored diagram and retain geometry, arrowheads, text, chart workbooks and media.
"""
import argparse
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile
from check_pptx import inspect
from tag_generated import tag
from repair_pptx_compat import normalise_parts

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS = {"p": P, "a": A}


def finalise(candidate, specification):
    tag(candidate, specification)
    with zipfile.ZipFile(candidate) as archive:
        parts = {n: archive.read(n) for n in archive.namelist()}
    for page in specification["slides"]:
        filename = f'ppt/slides/slide{page["number"]}.xml'
        root = ET.fromstring(parts[filename])
        tree = root.find("p:cSld/p:spTree", NS)
        # PptxGenJS table IDs can collide with neighbouring shape IDs. This
        # candidate has no timing or pre-existing connector references yet.
        # Assign IDs before attaching endpoints; do not do this to user decks.
        if root.find("p:timing", NS) is not None or tree.find(".//p:cxnSp", NS) is not None:
            raise ValueError("Finalisation requires a fresh, unconnected generated candidate")
        for number, props in enumerate(tree.findall(".//p:cNvPr", NS), 1):
            props.set("id", str(number))
        objects = {}
        for obj in tree:
            props = obj.find(".//p:cNvPr", NS)
            if props is not None and "|id:" in props.get("name", ""):
                objects[props.get("name").split("|id:", 1)[1]] = (obj, props.get("id"))
        for element in page["expected_elements"]:
            if element["kind"] != "connector":
                continue
            obj, _ = objects[element["id"]]
            if obj.tag != f"{{{P}}}sp":
                raise ValueError("Expected generated line shape for native connector")
            obj.tag = f"{{{P}}}cxnSp"
            nv = obj.find("p:nvSpPr", NS)
            nv.tag = f"{{{P}}}nvCxnSpPr"
            cnv = nv.find("p:cNvSpPr", NS)
            cnv.tag = f"{{{P}}}cNvCxnSpPr"
            edge = element["edge"]
            sides = {"top": 0, "left": 1, "bottom": 2, "right": 3}
            ET.SubElement(cnv, f"{{{A}}}stCxn",
                          id=objects[edge["from"]][1], idx=str(sides[edge["from_side"]]))
            ET.SubElement(cnv, f"{{{A}}}endCxn",
                          id=objects[edge["to"]][1], idx=str(sides[edge["to_side"]]))
            body = obj.find("p:txBody", NS)
            if body is not None:
                obj.remove(body)
        parts[filename] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    # Normalise known package defects (including a shared notes-master theme)
    # before the shared checker; this preserves themes and slide content.
    parts, compatibility_changes = normalise_parts(parts)
    temporary = candidate.with_suffix(".portable.pptx")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename, content in parts.items():
            archive.writestr(filename, content)
    os.replace(temporary, candidate)
    result = inspect(candidate)
    result["compatibility_changes"] = compatibility_changes
    if result["errors"]:
        raise ValueError("Generated PPTX structural errors: " + "; ".join(result["errors"]))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("specification", type=Path)
    args = parser.parse_args()
    finalise(args.candidate, json.loads(args.specification.read_text()))
