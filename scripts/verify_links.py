#!/usr/bin/env python3
"""
X1 — internal link & asset checker.

Scans every HTML file in the site, extracts local href/src attributes, resolves
them relative to each file, and reports any that point to a missing file.
External (http/https) links and anchors are listed but not fetched (the sandbox
has restricted egress); this check guarantees the *internal* site has no broken
links, which is the build requirement.

Exit code: 0 if no broken internal links, 1 if any are found.
Usage:  python3 scripts/verify_links.py [--root .]
"""
import os
import re
import sys
from pathlib import Path

ATTR_RE = re.compile(r'(?:href|src)\s*=\s*"([^"]+)"', re.IGNORECASE)
HTML_RE = re.compile(r"\.html?$", re.IGNORECASE)


def iter_html_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        # skip non-site, non-persisted dirs
        dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", "build", "dist", ".github"}]
        for name in filenames:
            if HTML_RE.search(name):
                yield Path(dirpath) / name


def main():
    root = Path(sys.argv[sys.argv.index("--root") + 1]) if "--root" in sys.argv else Path(".")
    root = root.resolve()

    broken = []
    external = set()
    checked = 0

    for html in iter_html_files(root):
        rel = html.relative_to(root)
        text = html.read_text(encoding="utf-8", errors="replace")
        for raw in ATTR_RE.findall(text):
            link = raw.strip()
            if not link or link.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
                continue
            if link.startswith(("http://", "https://")):
                external.add(link)
                continue
            # strip fragment
            target = link.split("#", 1)[0]
            if not target:
                continue
            # resolve relative to the html file's directory
            candidate = (html.parent / target).resolve()
            checked += 1
            # allow directory targets that contain an index.html
            if not candidate.exists() and candidate.is_dir() is False:
                broken.append((str(rel), link, str(candidate)))
            elif candidate.is_dir():
                if not (candidate / "index.html").exists():
                    broken.append((str(rel), link, str(candidate / "index.html")))

    print(f"Checked {checked} internal link/asset reference(s) across HTML files in {root}")
    if external:
        print(f"External links found (not fetched, {len(external)}):")
        for e in sorted(external):
            print(f"  - {e}")

    if broken:
        print("\nBROKEN INTERNAL LINKS:")
        for f, link, resolved in broken:
            print(f"  - {f}: '{link}' -> {resolved} (MISSING)")
        print(f"\nRESULT: FAIL — {len(broken)} broken internal link(s).")
        return 1

    print("\nRESULT: PASS — no broken internal links.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
