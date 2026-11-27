#!/usr/bin/env python3
"""Remove redundant exported paragraph levels from generated candidates only.

Some renderer versions clip text when nine identical list levels are exported.
Remove a level only when its attributes and children exactly equal defPPr.
Distinct level formatting, all paragraph/run text, geometry and media survive.
This is a generation step, never a repair of a user's manually edited deck.
"""
import argparse
import copy
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
ET.register_namespace("a", A)
ET.register_namespace("p", P)


def normalise_xml(raw):
    root = ET.fromstring(raw)
    count = 0
    for style in root.iter(f"{{{A}}}lstStyle"):
        default = style.find(f"{{{A}}}defPPr")
        if default is None:
            continue
        for child in list(style):
            if not re.fullmatch(rf"\{{{re.escape(A)}\}}lvl[1-9]pPr", child.tag):
                continue
            probe = copy.deepcopy(child)
            probe.tag = default.tag
            if ET.tostring(probe) == ET.tostring(default):
                style.remove(child)
                count += 1
    return (ET.tostring(root, encoding="utf-8", xml_declaration=True) if count else raw), count


def normalise(file):
    with zipfile.ZipFile(file) as z:
        entries = [(i, z.read(i.filename)) for i in z.infolist()]
    changed = 0
    out = []
    for info, raw in entries:
        if re.fullmatch(r"ppt/(slides|notesSlides)/[^/]+\.xml", info.filename):
            raw, n = normalise_xml(raw)
            changed += n
        out.append((info, raw))
    temp = file.with_suffix(".normalised.pptx")
    with zipfile.ZipFile(temp, "w") as z:
        for info, raw in out:
            z.writestr(info, raw)
    os.replace(temp, file)
    return changed


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("candidate", type=Path)
    args = p.parse_args()
    print(f"Redundant paragraph levels removed: {normalise(args.candidate)}")
