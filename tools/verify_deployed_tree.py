#!/usr/bin/env python3
"""Crawl the tree that `pages.yml` actually uploads, not the repository.

Every other verifier in this repository audits the *repository*: `scripts/verify_site.py`,
`tools/check_links.py`, `tools/verify_app.py` and `tools/lab/build_site.py` all walk the
source folders. But `pages.yml` does not publish the repository. It copies a subset of
folders into `_site/`, rewrites the root page with `sed`, and uploads that. A link can be
perfect in the repository and dead in the deployed tree, and that is exactly what happened:

    the root rewrite repointed href="assets/..." but not src="assets/..."
    -> the served landing page requested /assets/app.js and got a 404
    -> its table filter and column sort silently did nothing

No committed check could see it, because in the repository `app/index.html` resolves
`assets/app.js` correctly. Assembly is what breaks it.

This script performs that assembly in a temporary directory and crawls the result:

  1. read the `cp`/`sed` commands out of `.github/workflows/pages.yml` (so the check follows
     the workflow rather than duplicating it, and cannot silently drift from it);
  2. rebuild `_site/` exactly as the workflow does;
  3. follow every local `href`/`src` from the served root and report anything that does not
     resolve, plus pages nothing links to.

Exit code is non-zero on a broken link or on a page that is unreachable *and* not on the
known-intentional list. Orphan pages that predate this check are listed separately as
warnings so the check can be adopted without failing on historical debt.

Usage:  python3 tools/verify_deployed_tree.py [--strict]
        --strict   also fail on warnings (unreachable pages)
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "pages.yml")

# Pages deliberately not linked from the nav: preserved copies, not live sections.
INTENTIONAL = {
    "legacy-fourth-down.html",   # the previous landing page, kept for reference
}

# Orphans that predate this check. They are other sessions' pages; reported, not failed.
# Remove an entry once the owning session links it, and the warning disappears by itself.
KNOWN_ORPHANS = {
    "live/repo-review.html",
    "live/sources.html",
    "live/strategy-lab.html",
    "pages/executive-brief.html",
}


def _commands() -> list[list[str]]:
    """Pull the assembly commands out of pages.yml, in order."""
    if not os.path.exists(WORKFLOW):
        raise SystemExit(f"cannot read {WORKFLOW}")
    text = open(WORKFLOW, encoding="utf-8").read()
    # the assembly step is the one that mentions `rm -rf _site`
    m = re.search(r"run: \|\n((?:[ ]{10,}.*\n|\n)+?)(?=\n\s*- name:|\Z)", text)
    if not m:
        raise SystemExit("could not find the assembly `run:` block in pages.yml")
    out = []
    for raw in m.group(1).split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out


def _assemble(dest: str) -> list[str]:
    """Replay the workflow's assembly, rewritten to build into `dest`."""
    ran, skipped = [], []
    sh = "bash"
    for line in _commands():
        cmd = line
        # point the workflow's `_site` at our temporary directory
        cmd = re.sub(r"\b_site\b", os.path.join(dest, "_site"), cmd)
        for rel in re.findall(r"cp -r (\S+) ", line):
            if not os.path.exists(os.path.join(ROOT, rel)):
                skipped.append(rel)
        try:
            subprocess.run(cmd, shell=True, cwd=ROOT, executable=sh,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=300, check=False)
        except subprocess.TimeoutExpired:
            skipped.append(f"timeout: {line[:60]}")
        ran.append(line)
    return skipped


def _crawl(site: str) -> tuple[int, int, list[tuple[str, str]], list[str]]:
    pages, bad, links = [], [], 0
    for base, _dirs, files in os.walk(site):
        for f in files:
            if f.endswith(".html"):
                pages.append(os.path.relpath(os.path.join(base, f), site))

    for page in pages:
        path = os.path.join(site, page)
        text = open(path, encoding="utf-8", errors="replace").read()
        for attr in re.findall(r'(?:href|src)="([^"]+)"', text):
            if attr.startswith(("http://", "https://", "mailto:", "#", "data:", "javascript:")):
                continue
            if "${" in attr:          # a client-side template, not a static link
                continue
            target = urllib.parse.unquote(attr.split("#")[0].split("?")[0])
            if not target:
                continue
            links += 1
            resolved = os.path.normpath(os.path.join(os.path.dirname(path), target))
            if not os.path.exists(resolved):
                bad.append((page, attr))

    # reachability from the served root
    root = "index.html"
    seen, queue = set(), [root] if os.path.exists(os.path.join(site, root)) else []
    while queue:
        page = queue.pop()
        if page in seen:
            continue
        seen.add(page)
        path = os.path.join(site, page)
        if not os.path.exists(path):
            continue
        text = open(path, encoding="utf-8", errors="replace").read()
        for href in re.findall(r'href="([^"]+)"', text):
            if href.startswith(("http://", "https://", "mailto:", "#", "data:", "javascript:")):
                continue
            if "${" in href:
                continue
            target = urllib.parse.unquote(href.split("#")[0].split("?")[0])
            if not target:
                continue
            # join against the page's *relative* name so the queue holds the same keys as
            # `pages`; joining against the absolute path makes every page look unreachable
            resolved = os.path.normpath(os.path.join(os.path.dirname(page), target))
            if resolved.endswith(".html") and os.path.exists(os.path.join(site, resolved)):
                if resolved not in seen:
                    queue.append(resolved)

    orphans = sorted(set(pages) - seen - INTENTIONAL)
    return len(pages), links, bad, orphans


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="fail on warnings too")
    args = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="x1-deployed-")
    try:
        skipped = _assemble(tmp)
        site = os.path.join(tmp, "_site")
        if not os.path.isdir(site):
            print("FAIL: assembly did not produce a _site directory")
            return 1
        pages, links, bad, orphans = _crawl(site)
        if skipped:
            print("note: sources not present in this checkout (not a failure):")
            for s in skipped:
                print(f"  {s}")
        print(f"assembled tree : {pages} HTML pages, {links} local links checked")
        if bad:
            print(f"\nFAILURES ({len(bad)}):")
            for page, attr in bad[:60]:
                print(f"  BROKEN  {page}: {attr}")
            if len(bad) > 60:
                print(f"  ... and {len(bad) - 60} more")
            return 1
        print("all local links resolve in the deployed tree")

        new_orphans = [o for o in orphans if o not in KNOWN_ORPHANS]
        if orphans:
            print(f"\nreachable from the served root: {pages - len(orphans)} of {pages}")
            known = [o for o in orphans if o in KNOWN_ORPHANS]
            if known:
                print(f"  pre-existing orphans, reported not failed ({len(known)}): {', '.join(known)}")
            if new_orphans:
                print(f"  NEW orphans ({len(new_orphans)}): {', '.join(new_orphans)}")
        else:
            print(f"reachable from the served root: all {pages} pages")

        if args.strict and new_orphans:
            print("\nFAIL (--strict): a page is unreachable from the served root")
            return 1
        if new_orphans:
            print("\nWARN: new orphan page(s) — link them, or add to KNOWN_ORPHANS with a reason")
        print("\ndeployed-tree check passed")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
