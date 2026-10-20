#!/usr/bin/env python3
"""Create only a presentation workflow record; never overwrite existing work."""

import argparse
import datetime as dt
import html
from pathlib import Path
import re
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", required=True, type=Path)
    parser.add_argument("--title", required=True)
    args = parser.parse_args()
    title = args.title.strip()
    if not title or any(c in title for c in "\r\n\x00"):
        parser.error("--title must be a non-empty single line")

    template = Path(__file__).resolve().parents[1] / "assets" / "workflow-template.md"
    source = template.read_text(encoding="utf-8")
    # A plain-text title must remain visible when the workflow is rendered as Markdown.
    markdown_title = re.sub(r"([\\`*_[\]{}()#+\-.!|>~])", r"\\\1", html.escape(title, quote=False))
    content = source.replace("{{DATE}}", dt.date.today().isoformat()).replace("{{TITLE}}", markdown_title)
    project = args.project_dir.expanduser().resolve()
    try:
        project.mkdir(parents=True, exist_ok=True)
        target = project / "workflow.md"
        for existing in (target, project / "workflow.org"):
            if existing.exists() or existing.is_symlink():
                print(f"Existing workflow preserved; no second record created: {existing}", file=sys.stderr)
                return 2
        # Exclusive creation refuses existing files and symlinks atomically.
        with target.open("x", encoding="utf-8") as stream:
            stream.write(content)
    except FileExistsError:
        print(f"Existing path preserved; no overwrite: {project / 'workflow.md'}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"Cannot create workflow record: {error}", file=sys.stderr)
        return 1
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
