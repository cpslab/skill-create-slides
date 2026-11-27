#!/usr/bin/env python3
"""Render a saved PPTX through LibreOffice or macOS PowerPoint, then PyMuPDF.

Rendering is verification, not a visual-review pass. A new output directory is
required. No Codex runtime or network service is used.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def find_soffice(explicit=None):
    """An explicitly configured path must work; never silently ignore it."""
    configured = explicit or os.environ.get("SOFFICE")
    if configured:
        candidate = shutil.which(configured)
        if not candidate:
            raise ValueError("Configured SOFFICE executable was not found: " + configured)
        return candidate
    candidates = [
        shutil.which("soffice"), shutil.which("libreoffice"),
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ]
    for root in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
        if os.environ.get(root):
            candidates.append(str(Path(os.environ[root]) / "LibreOffice/program/soffice.exe"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    raise ValueError("LibreOffice was not found. Install it or set SOFFICE to its executable.")


def slide_count(path):
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("ppt/presentation.xml"))
    count = len(root.findall(
        "{http://schemas.openxmlformats.org/presentationml/2006/main}sldIdLst/"
        "{http://schemas.openxmlformats.org/presentationml/2006/main}sldId"))
    if not count:
        raise ValueError("The source PPTX contains no presentation slide IDs.")
    return count


def run_export(command, timeout):
    """Terminate only this export's process group on timeout."""
    kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "text": True}
    if os.name == "posix":
        kwargs["start_new_session"] = True
    process = subprocess.Popen(command, **kwargs)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            # taskkill /T is limited to this newly created export process tree.
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, timeout=10, check=False)
            process.kill()
        process.communicate()
        raise ValueError(f"Presentation export timed out after {timeout} seconds.")
    result = {"command": command, "exit_code": process.returncode,
              "stdout": stdout[-16000:], "stderr": stderr[-16000:]}
    if process.returncode:
        raise ValueError("Presentation export failed: " + json.dumps(result, ensure_ascii=False))
    return result


def render(source, output, renderer="libreoffice", soffice=None, dpi=144, timeout=240):
    import pymupdf
    from PIL import Image, ImageOps

    source = Path(source).resolve()
    output = Path(output).resolve()
    if source.suffix.lower() != ".pptx" or not source.is_file():
        raise ValueError("Supply an existing .pptx file.")
    if not 36 <= dpi <= 600 or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("DPI must be 36–600 and timeout must be positive.")
    if renderer not in ("libreoffice", "powerpoint"):
        raise ValueError("Choose libreoffice or powerpoint.")
    executable = find_soffice(soffice) if renderer == "libreoffice" else None
    if renderer == "powerpoint" and platform.system() != "Darwin":
        raise ValueError("The PowerPoint AppleScript renderer requires macOS.")
    expected_count = slide_count(source)
    source_hash = sha256(source)
    open_verification = None
    output.mkdir(parents=True, exist_ok=False)
    try:
        # The export reads this byte-identical snapshot, never a stale supplied PDF.
        with tempfile.TemporaryDirectory(prefix="cps-slide-export-") as temporary:
            temporary = Path(temporary)
            snapshot = temporary / "candidate.pptx"
            shutil.copyfile(source, snapshot)
            if sha256(snapshot) != source_hash:
                raise ValueError("The PPTX changed while its export snapshot was copied.")
            pdf = output / "candidate.pdf"
            if renderer == "libreoffice":
                # Private profile prevents reuse of an already-open user session.
                profile = temporary / "lo-profile"
                options = {"ExportHiddenSlides": {"type": "boolean", "value": "true"},
                           "ExportNotesPages": {"type": "boolean", "value": "false"}}
                command = [executable, "-env:UserInstallation=" + profile.as_uri(),
                           "--headless", "--nologo", "--nodefault", "--nofirststartwizard",
                           "--convert-to", "pdf:impress_pdf_Export:" + json.dumps(options),
                           "--outdir", str(output), str(snapshot)]
                log = run_export(command, timeout)
                version = subprocess.run([executable, "--version"], capture_output=True,
                                         text=True, timeout=30, check=False)
                engine = (version.stdout or version.stderr).strip()
            else:
                script = Path(__file__).with_name("render_powerpoint.applescript")
                log = run_export(["/usr/bin/osascript", str(script), str(snapshot), str(pdf)], timeout)
                parts = log["stdout"].strip().split("|")
                if (len(parts) != 4 or int(parts[1]) != expected_count
                        or parts[2] != "saved=true" or parts[3] != f"slides_read={expected_count}"):
                    raise ValueError("PowerPoint did not confirm an unchanged normal open and every requested slide.")
                engine = "Microsoft PowerPoint " + parts[0]
                open_verification = {
                    "status": "pass", "method": "Launch Services open of a new byte-identical snapshot; "
                    "exact file alias matched, saved=true before export, all slides read; no repair action sent.",
                    "slides_read": expected_count, "repair_action_sent": False,
                    "editing_and_playback": "unverified",
                }
            (output / "export-log.json").write_text(
                json.dumps({**log, "pptx_sha256": source_hash, "renderer": renderer,
                            "engine_version": engine}, ensure_ascii=False, indent=2) + "\n")
            if not pdf.is_file() or not pdf.stat().st_size:
                raise ValueError("The renderer returned without creating the requested PDF.")
            pages = []
            thumbnails = []
            with pymupdf.open(pdf) as document:
                if document.page_count != expected_count:
                    raise ValueError(f"PDF page count {document.page_count} differs from "
                                     f"PPTX slide count {expected_count}.")
                for number, page in enumerate(document, 1):
                    name = f"slide-{number:02d}.png"
                    image_path = output / name
                    pixmap = page.get_pixmap(dpi=dpi, alpha=False)
                    pixmap.save(image_path)
                    pages.append({"number": number, "image": name,
                                  "image_sha256": sha256(image_path),
                                  "width": pixmap.width, "height": pixmap.height,
                                  "status": "unverified"})
                    with Image.open(image_path) as image:
                        thumbnails.append(ImageOps.pad(image.convert("RGB"), (480, 270),
                                                       color="white"))
            columns = min(3, expected_count)
            sheet = Image.new("RGB", (columns * 490 + 10,
                                      math.ceil(expected_count / columns) * 280 + 10),
                              "#e6e6e6")
            for index, thumbnail in enumerate(thumbnails):
                sheet.paste(thumbnail, (10 + index % columns * 490,
                                        10 + index // columns * 280))
                thumbnail.close()
            sheet.save(output / "contact-sheet.png")
            if sha256(source) != source_hash or sha256(snapshot) != source_hash:
                raise ValueError("The PPTX changed during rendering; regenerate the render.")
            record = {
                "schema_version": 1, "pptx_sha256": source_hash,
                "renderer": f"{engine} → PDF → PyMuPDF {pymupdf.VersionBind}",
                "pdf": {"file": pdf.name, "sha256": sha256(pdf),
                        "source_binding": source_hash,
                        "method": "Direct export of a byte-identical PPTX snapshot",
                        "export_log": "export-log.json"},
                "dpi": dpi, "pages": pages,
                "contact_sheet": {"image": "contact-sheet.png",
                                  "image_sha256": sha256(output / "contact-sheet.png")},
                "visual_review": {"status": "unverified",
                                  "reason": "Review every page before completing the quality gate."},
            }
            if open_verification is not None:
                record["application_open_verification"] = open_verification
            (output / "render-record.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n")
            return record
    except Exception as exc:
        # Never publish a successful render record for an incomplete run.
        (output / "render-record.json").unlink(missing_ok=True)
        (output / "render-error.json").write_text(
            json.dumps({"status": "error", "pptx_sha256": source_hash,
                        "reason": str(exc)}, ensure_ascii=False, indent=2) + "\n")
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--renderer", choices=("libreoffice", "powerpoint"), default="libreoffice")
    parser.add_argument("--soffice", help="Executable override; otherwise SOFFICE, PATH or app paths.")
    parser.add_argument("--dpi", type=int, default=144)
    parser.add_argument("--timeout", type=float, default=240)
    args = parser.parse_args()
    try:
        record = render(args.input, args.output_dir, args.renderer, args.soffice,
                        args.dpi, args.timeout)
    except (OSError, ValueError, ImportError, zipfile.BadZipFile, ET.ParseError,
            subprocess.SubprocessError) as exc:
        parser.exit(1, f"Rendering failed: {exc}\n")
    print(json.dumps({"pages": len(record["pages"]), "pptx_sha256": record["pptx_sha256"],
                      "output_directory": str(args.output_dir.resolve())}))


if __name__ == "__main__":
    main()
