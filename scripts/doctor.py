#!/usr/bin/env python3
"""Report local production capabilities without installing software or claiming a visual review."""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

from render_portable import find_soffice


def run(args):
    try:
        process = subprocess.run(args, capture_output=True, text=True, timeout=30)
        return {"status": "pass" if process.returncode == 0 else "unavailable",
                "exit_code": process.returncode,
                "output": (process.stdout + process.stderr).strip()[:4000]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "unavailable", "reason": str(exc)}


def module_report(name):
    try:
        module = importlib.import_module(name)
        return {"status": "pass", "version": str(getattr(
            module, "__version__", getattr(module, "VersionBind", "unknown")))}
    except (ImportError, OSError) as exc:
        return {"status": "unavailable", "reason": str(exc)}


def font_report(name="Noto Sans JP"):
    roots = [Path("/Library/Fonts"), Path.home() / "Library/Fonts",
             Path("/usr/share/fonts"), Path("/usr/local/share/fonts"),
             Path.home() / ".local/share/fonts", Path.home() / ".fonts",
             Path.home() / ".nix-profile/share/fonts"]
    if os.environ.get("WINDIR"):
        roots.append(Path(os.environ["WINDIR"]) / "Fonts")
    if os.environ.get("LOCALAPPDATA"):
        roots.append(Path(os.environ["LOCALAPPDATA"]) / "Microsoft/Windows/Fonts")
    normalise = lambda value: re.sub(r"[\W_]", "", value.casefold())
    target = normalise(name)
    if not target:
        raise ValueError("Specify a non-empty font family.")
    files = []
    for root in roots:
        if root.exists():
            for path in root.rglob("*"):
                if (path.is_file() and path.suffix.lower() in (".ttf", ".otf", ".ttc")
                        and target in normalise(path.stem)):
                    files.append({"path": str(path),
                                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    matched_family = False
    if shutil.which("fc-list"):
        listing = subprocess.run(["fc-list", "--format=%{family}\n"], capture_output=True,
                                 text=True, timeout=30, check=False)
        matched_family = any(target == normalise(family.strip())
                             for line in listing.stdout.splitlines()
                             for family in line.split(","))
    return {"status": "pass" if files or matched_family else "unavailable",
            "requested_family": name, "files": files,
            "fontconfig_family_found": matched_family,
            "scope": "Presence only; actual font selection must be checked in final renders."}


def inspect_environment(backend="portable", renderer=None, font="Noto Sans JP"):
    renderer = renderer or ("libreoffice" if backend == "portable" else "artifact-tool")
    root = Path(__file__).resolve().parents[1]
    report = {"schema_version": 1, "backend": backend, "renderer": renderer,
              "platform": platform.platform(), "architecture": platform.machine(),
              "python": sys.version, "python_executable": sys.executable, "tools": {}}
    for tool in ("uv", "ni", "nix", "node", "fc-list", "soffice", "opencode", "claude"):
        executable = shutil.which(tool)
        report["tools"][tool] = {"path": executable,
                                "status": "available" if executable else "unavailable"}
    node = os.environ.get("RUNTIME_NODE") or shutil.which("node")
    report["node_version"] = run([node, "--version"]) if node else {"status": "unavailable"}
    if report["node_version"]["status"] == "pass":
        match = re.search(r"v(\d+)", report["node_version"]["output"])
        if not match or int(match[1]) < 20:
            report["node_version"].update(status="unavailable", reason="Node.js 20 or later is required.")
    modules = (os.environ.get("RUNTIME_NODE_MODULES") or
               os.environ.get("CODEX_PRIMARY_RUNTIME_NODE_MODULES"))
    names = ["pptxgenjs", "sharp"] if backend == "portable" else ["@oai/artifact-tool", "sharp"]
    base = str(root / "package.json") if backend == "portable" else (
        str(Path(modules) / "package.json") if modules and Path(modules).is_absolute() else None)
    if node and base:
        code = ("import {createRequire} from 'node:module';"
                "import {pathToFileURL} from 'node:url';"
                "const r=createRequire(process.argv[1]);"
                "for(const n of JSON.parse(process.argv[2])){"
                "const p=r.resolve(n);await import(pathToFileURL(p).href);console.log(n,p)}")
        report["node_import"] = run(
            [node, "--input-type=module", "-e", code, base, json.dumps(names)])
    else:
        report["node_import"] = {"status": "unavailable", "reason":
            "Node is missing, or the Codex backend needs an absolute RUNTIME_NODE_MODULES."}
    report["python_modules"] = {name: module_report(name) for name in ("pymupdf", "PIL")}
    report["fonts"] = font_report(font)
    report["font_files"] = report["fonts"]["files"]
    report["font_rendering"] = {"status": "unverified",
        "reason": "Font presence does not establish the font used by the renderer."}
    if renderer == "libreoffice":
        try:
            executable = find_soffice()
            report["render_engine"] = {**run([executable, "--version"]), "path": executable}
        except ValueError as exc:
            report["render_engine"] = {"status": "unavailable", "reason": str(exc)}
    elif renderer == "powerpoint":
        locations = [Path("/Applications/Microsoft PowerPoint.app"),
                     Path.home() / "Applications/Microsoft PowerPoint.app"]
        found = platform.system() == "Darwin" and any(path.is_dir() for path in locations)
        report["render_engine"] = {"status": "pass" if found else "unavailable",
            "scope": "Application presence only. Export may require macOS Automation permission."}
    elif renderer == "artifact-tool" and backend == "codex":
        report["render_engine"] = report["node_import"].copy()
    else:
        report["render_engine"] = {"status": "unavailable",
                                  "reason": "artifact-tool rendering requires the codex backend."}
    checks = {
        "python_version": sys.version_info >= (3, 10),
        "node": report["node_version"]["status"] == "pass",
        "node_modules": report["node_import"]["status"] == "pass",
        "fonts": report["fonts"]["status"] == "pass",
        "renderer": report["render_engine"]["status"] == "pass",
    }
    if renderer in ("libreoffice", "powerpoint"):
        checks["python_render_modules"] = all(
            item["status"] == "pass" for item in report["python_modules"].values())
    report["required_checks"] = {name: "pass" if passed else "unavailable"
                                 for name, passed in checks.items()}
    report["ready_for_generation_and_rendering"] = all(checks.values())
    report["capabilities"] = {
        "planning": {"status": "pass"},
        "pptx_generation": {"status": "pass" if checks["node"] and checks["node_modules"]
                           else "unavailable"},
        "static_rendering": {"status": "pass" if checks["renderer"] and
                            checks.get("python_render_modules", True) else "unavailable"},
        "image_generation": {"status": "unverified", "required_for_strict": False,
            "reason": "The selected client/model determines available image-generation tools; "
                      "this local check neither requires an API key nor tests a provider."},
        "all_page_visual_review": {"status": "unverified", "required_for_strict": False,
            "reason": "The client/model must actually open and inspect every final page image."},
        "application_edit_and_video": {"status": "unverified", "required_for_strict": False,
            "reason": "Requires actual operation in the target application."},
    }
    report["application_edit_and_video"] = report["capabilities"]["application_edit_and_video"]
    report["scope"] = "Strict success confirms prerequisites only, never presentation quality or client end-to-end execution."
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--backend", choices=("portable", "codex"), default="portable")
    parser.add_argument("--renderer", choices=("libreoffice", "powerpoint", "artifact-tool"))
    parser.add_argument("--font", default="Noto Sans JP")
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 when generation/rendering prerequisites are missing.")
    args = parser.parse_args()
    try:
        report = inspect_environment(args.backend, args.renderer, args.font)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"Environment check failed: {exc}\n")
    print(json.dumps({"report": str(args.report), "backend": args.backend,
                      "required_checks": report["required_checks"],
                      "ready_for_generation_and_rendering":
                          report["ready_for_generation_and_rendering"]}, ensure_ascii=False))
    return 1 if args.strict and not report["ready_for_generation_and_rendering"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
