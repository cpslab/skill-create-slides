#!/usr/bin/env python3
"""配布対象・相対リンク・版・hash・個人パスを確認する。--refresh は一覧と版だけ更新する。"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
from urllib.parse import unquote, urlsplit
import zipfile


ROOT_FILES = {"AGENTS.md", "README.md", "SKILL.md"}
PACKAGE_DIRS = {"agents", "assets", "references", "scripts", "tests"}
EXTENSIONS = {
    ".md", ".org", ".txt", ".json", ".yaml", ".yml", ".py", ".mjs", ".js", ".sh", ".applescript",
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".pptx", ".mp4", ".csv", ".tsv",
}
TEXT_EXTENSIONS = EXTENSIONS - {".png", ".jpg", ".jpeg", ".webp", ".gif", ".pptx", ".mp4"}
SKIP_DIRS = {"__pycache__", "node_modules"}
MANIFEST = "package-manifest.json"
# Match user-home prefixes, not research names. Placeholder examples are not personal paths.
PERSONAL_PATH = re.compile(
    r"(?:/(?:Users|home)/[A-Za-z0-9_.-]+/|[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z0-9_.-]+[\\/]+)"
)
MD_LINK = re.compile(r"!?\[[^\]\n]*\]\(\s*(<[^>]+>|[^)\n]+)\s*\)")
MD_REFERENCE = re.compile(r"^\s*\[[^\]\n]+\]:\s*(<[^>]+>|\S+)", re.M)
ORG_LINK = re.compile(r"\[\[(?:file:)?([^\]\n]+)\](?:\[[^\]\n]*\])?\]")
MODULE_IMPORT = re.compile(r"""(?:from\s*|import\s*\(\s*)['"](\.[^'"]+)['"]""")


def digest(path):
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def inventory(root):
    """Only intentionally supported files enter the distribution; never follow symlinks."""
    files, issues = {}, []
    for name in sorted(ROOT_FILES):
        path = root / name
        if path.is_symlink() or not path.is_file():
            issues.append({"code": "required_file", "path": name, "message": "Required regular file missing."})
        else:
            files[name] = digest(path)
    for directory in sorted(PACKAGE_DIRS):
        base = root / directory
        if not base.exists():
            continue
        if base.is_symlink():
            issues.append({"code": "symlink", "path": directory, "message": "Package directories must be portable regular directories."})
            continue
        for current, dirs, names in os.walk(base, followlinks=False):
            retained = []
            for name in sorted(dirs):
                path = Path(current) / name
                if name.startswith(".") or name in SKIP_DIRS:
                    continue
                if path.is_symlink():
                    issues.append({"code": "symlink", "path": path.relative_to(root).as_posix(),
                                   "message": "Symlink directories are not packaged."})
                else:
                    retained.append(name)
            dirs[:] = retained
            for name in sorted(names):
                path = Path(current) / name
                if name.startswith(".") or path.suffix.lower() not in EXTENSIONS:
                    continue
                relative = path.relative_to(root).as_posix()
                if path.is_symlink():
                    issues.append({"code": "symlink", "path": relative, "message": "Symlink files are not portable distribution inputs."})
                else:
                    files[relative] = digest(path)
    return dict(sorted(files.items())), issues


def versions(root):
    skill = (root / "SKILL.md").read_text()
    readme = (root / "README.md").read_text()
    front = skill.split("---", 2)[1] if skill.startswith("---") else ""
    sv = re.search(r'^\s*version:\s*["\']?([0-9]+\.[0-9]+\.[0-9]+)', front, re.M)
    rv = re.search(r"現在のスキル版は\s*\*\*([0-9]+\.[0-9]+\.[0-9]+)\*\*", readme)
    return sv.group(1) if sv else None, rv.group(1) if rv else None


def headings(text):
    """GitHub-style heading IDs sufficient for the maintained Markdown vocabulary."""
    result, counts = set(), {}
    for line in text.splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        title = re.sub(r"<[^>]+>", "", match.group(1)).lower().replace("`", "")
        slug = re.sub(r"[^\w\- ]", "", title).replace(" ", "-")
        count = counts.get(slug, 0)
        counts[slug] = count + 1
        result.add(slug if count == 0 else f"{slug}-{count}")
    return result


def link_destination(raw):
    if raw.startswith("<"):
        return raw[1:raw.index(">")]
    # Optional Markdown title follows whitespace and a quote; paths with spaces use <...>.
    return re.split(r'\s+["\']', raw.strip(), maxsplit=1)[0]


def local_link(root, source, target, packaged):
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or target.startswith("$") or "<" in target:
        return None
    path_text = unquote(parsed.path)
    if not path_text:
        destination = source
    elif path_text.startswith(("/", "\\")):
        return {"code": "absolute_link", "message": f"Use a portable relative link: {target}"}
    else:
        destination = source.parent / path_text
    resolved = destination.resolve()
    try:
        relative = resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return {"code": "outside_link", "message": f"Relative link escapes the package: {target}"}
    if not resolved.exists():
        return {"code": "missing_link", "message": f"Target is missing: {target}"}
    if resolved.is_file() and relative != MANIFEST and relative not in packaged:
        return {"code": "unpackaged_link", "message": f"Target is outside the explicit distribution list: {target}"}
    if parsed.fragment and resolved.suffix.lower() == ".md":
        if unquote(parsed.fragment) not in headings(resolved.read_text()):
            return {"code": "missing_anchor", "message": f"Heading anchor is missing: {target}"}
    return None


def inspect_content(root, files):
    issues, checked_links, scanned_parts = [], 0, 0
    for relative in files:
        path = root / relative
        texts = []
        if path.suffix.lower() in TEXT_EXTENSIONS:
            try:
                texts.append((relative, path.read_text(encoding="utf-8")))
            except UnicodeDecodeError:
                issues.append({"code": "text_encoding", "path": relative, "message": "Text file is not UTF-8."})
        elif path.suffix.lower() == ".pptx":
            try:
                with zipfile.ZipFile(path) as package:
                    for name in package.namelist():
                        if name.endswith((".xml", ".rels")):
                            texts.append((relative + "!" + name, package.read(name).decode("utf-8")))
            except (zipfile.BadZipFile, UnicodeDecodeError) as exc:
                issues.append({"code": "pptx_read", "path": relative, "message": str(exc)})
        for location, text in texts:
            scanned_parts += 1
            for match in PERSONAL_PATH.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                issues.append({"code": "personal_absolute_path", "path": location, "line": line,
                               "message": "Personal home-directory path found; replace it with a portable input/configuration."})
        if not texts or path.suffix.lower() not in {".md", ".org", ".mjs", ".js"}:
            continue
        text = texts[0][1]
        if path.suffix.lower() == ".md":
            links = [link_destination(m.group(1)) for regex in (MD_LINK, MD_REFERENCE) for m in regex.finditer(text)]
        elif path.suffix.lower() == ".org":
            links = [m.group(1).split("::", 1)[0] for m in ORG_LINK.finditer(text)]
        else:
            links = [m.group(1) for m in MODULE_IMPORT.finditer(text)]
        for target in links:
            checked_links += 1
            issue = local_link(root, path, target, files)
            if issue:
                issues.append({**issue, "path": relative})
    # The manifest itself is not hash-listed, but is scanned for private paths.
    manifest_text = (root / MANIFEST).read_text()
    if PERSONAL_PATH.search(manifest_text):
        issues.append({"code": "personal_absolute_path", "path": MANIFEST,
                       "message": "Personal home-directory path found in manifest metadata."})
    return issues, checked_links, scanned_parts


def check(root, refresh=False):
    root = Path(root)
    manifest_path = root / MANIFEST
    manifest = json.loads(manifest_path.read_text())
    files, issues = inventory(root)
    skill_version, readme_version = versions(root)
    if not skill_version or not readme_version or skill_version != readme_version:
        issues.append({"code": "version_sources", "message": "SKILL frontmatter and README current version must exist and match."})
    content_issues, checked_links, scanned_parts = inspect_content(root, files)
    issues.extend(content_issues)
    if refresh:
        # Never bless an incomplete or non-portable package, or invent validation dates/results.
        if not issues:
            manifest["version"] = skill_version
            manifest["files"] = files
            temp = manifest_path.with_suffix(".json.tmp")
            temp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
            temp.replace(manifest_path)
    if manifest.get("version") != skill_version:
        issues.append({"code": "manifest_version", "message": "Manifest version differs from SKILL.md."})
    listed = manifest.get("files", {})
    if not isinstance(listed, dict):
        issues.append({"code": "manifest_files", "message": "Manifest files must be an object."})
        listed = {}
    for relative in sorted(set(files) | set(listed)):
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or "\\" in relative:
            issues.append({"code": "manifest_path", "path": relative, "message": "Unsafe/non-portable manifest key."})
        elif relative not in listed:
            issues.append({"code": "unlisted", "path": relative, "message": "Distribution file is absent from the manifest."})
        elif relative not in files:
            issues.append({"code": "unexpected_manifest_file", "path": relative, "message": "Listed file is missing or outside the explicit distribution set."})
        elif listed[relative] != files[relative]:
            issues.append({"code": "hash_or_size", "path": relative, "message": "Manifest bytes/SHA-256 differ from the current file."})
    return {
        "schema_version": 1, "status": "pass" if not issues else "error",
        "refreshed": bool(refresh and not issues), "version": skill_version,
        "file_count": len(files), "checked_links": checked_links, "scanned_text_parts": scanned_parts,
        "distribution": {"root_files": sorted(ROOT_FILES), "directories": sorted(PACKAGE_DIRS),
                         "extensions": sorted(EXTENSIONS), "exclude": ["dotfiles/directories", "__pycache__", "node_modules", MANIFEST]},
        "issues": issues,
        "scope": "Checks file consistency and user-home paths in UTF-8 sources and PPTX XML/rels. It does not inspect image pixels or establish research provenance, visual quality, or application behaviour.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--refresh", action="store_true", help="Refresh files and version only; preserve validation metadata and dates.")
    parser.add_argument("--report", type=Path, help="Optional JSON report outside packaged directories.")
    args = parser.parse_args()
    if args.report:
        resolved = args.report.resolve()
        try:
            relative = resolved.relative_to(args.root.resolve())
            if relative.as_posix() in ROOT_FILES | {MANIFEST} or relative.parts[0] in PACKAGE_DIRS:
                parser.error("--report must not modify a distribution file or directory")
        except ValueError:
            pass
    try:
        result = check(args.root, args.refresh)
    except (OSError, ValueError, IndexError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"Package check failed: {exc}\n")
    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output)
    sys.stdout.write(output)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
