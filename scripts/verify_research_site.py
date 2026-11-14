#!/usr/bin/env python3
"""Link, contract and source check for the research site (`research/`).

The research lab is a parallel site tree with its own stylesheet, so it carries
its own contract.  This checker enforces the same discipline the integration
session applies to the main site:

  1. every internal href/src resolves;
  2. every external link is https and points at an approved publisher host;
  3. no page is orphaned - every page is reachable from research/index.html;
  4. every page shows the data snapshot date and links its stylesheet;
  5. no escaped markup renders as literal text;
  6. no unfilled placeholders ("nan", "None", "{}") survive into the output;
  7. every CSS class used by a page is defined in research/assets/styles.css
     (or is a JavaScript hook).

Exit code 1 on any failure.
"""

from __future__ import annotations

import glob
import os
import re
import sys
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TREE = os.path.join(ROOT, "research")
CSS = os.path.join(TREE, "assets", "styles.css")
JS_ROOT = os.path.join(TREE, "assets")

# League-operated publishers plus the repository host.  Community mirrors are
# allowed because the research lab names them as mirrors on every row.
APPROVED = {
    "nfl.com", "www.nfl.com", "media.nfl.com", "nextgenstats.nfl.com",
    "operations.nfl.com", "support.nfl.com", "static.www.nfl.com", "github.com",
    "karagemop466-tech.github.io", "www.buffalobills.com", "www.seahawks.com",
    "www.detroitlions.com", "www.packers.com", "www.baltimoreravens.com",
}

SNAP = "2026-11-14"
PLACEHOLDERS = ("nan%", "None</td>", "{}", "&mdash;&mdash;")

errors: list[str] = []
checks: list[str] = []


def check(cond, msg):
    if cond:
        checks.append(msg)
    else:
        errors.append(msg)


def html_files() -> list[str]:
    return sorted(glob.glob(os.path.join(TREE, "**", "*.html"), recursive=True))


HREF = re.compile(r'(?:href|src)="([^"]+)"')
files = html_files()
check(len(files) >= 15, f"at least 15 research pages (found {len(files)})")

linked = set()
for path in files:
    rel = os.path.relpath(path, ROOT)
    text = open(path, encoding="utf-8").read()
    base = os.path.dirname(path)

    check(SNAP in text, f"{rel}: shows the {SNAP} snapshot date")
    check("assets/styles.css" in text, f"{rel}: links the research stylesheet")
    check("Flagged for review" in text, f"{rel}: nav includes Flagged for review")

    leaks = re.findall(r"&lt;(b|span|a|code|i|br|em|table|tr|td)&gt;", text)
    check(not leaks, f"{rel}: no escaped markup rendered as literal text")

    for bad in PLACEHOLDERS:
        check(bad not in text, f"{rel}: no unfilled placeholder {bad!r}")

    for url in HREF.findall(text):
        if url.startswith("#") or url.startswith("mailto:"):
            continue
        if url.startswith("http"):
            host = urlparse(url).netloc
            check(host in APPROVED, f"{rel}: external host approved ({host})")
            check(url.startswith("https://"), f"{rel}: external link is https ({url[:60]})")
            continue
        target = os.path.normpath(os.path.join(base, url.split("#")[0]))
        check(os.path.exists(target), f"{rel}: internal link resolves ({url})")
        if target.endswith(".html"):
            linked.add(target)

# reachability from the research landing page
root_page = os.path.normpath(os.path.join(TREE, "index.html"))
reachable = {root_page} if os.path.exists(root_page) else set()
frontier = list(reachable)
while frontier:
    cur = frontier.pop()
    text = open(cur, encoding="utf-8").read()
    for url in HREF.findall(text):
        if url.startswith("http") or url.startswith("#") or url.startswith("mailto:"):
            continue
        tgt = os.path.normpath(os.path.join(os.path.dirname(cur), url.split("#")[0]))
        if tgt.endswith(".html") and tgt not in reachable and os.path.exists(tgt):
            reachable.add(tgt)
            frontier.append(tgt)

for path in files:
    rel = os.path.relpath(path, ROOT)
    check(os.path.normpath(path) in reachable, f"{rel}: reachable from research/index.html")

# CSS completeness for this tree
css_classes = set(re.findall(r"\.([a-zA-Z][a-zA-Z0-9_-]*)", open(CSS, encoding="utf-8").read()))
js_hooks = set()
for js in glob.glob(os.path.join(JS_ROOT, "*.js")):
    for m in re.finditer(r"querySelectorAll?\(['\"]([^'\"]+)", open(js, encoding="utf-8").read()):
        for c in re.findall(r"\.([a-zA-Z][a-zA-Z0-9_-]*)", m.group(1)):
            js_hooks.add(c)
used = set()
for path in files:
    for m in re.finditer(r'class="([^"]*)"', open(path, encoding="utf-8").read()):
        used |= set(m.group(1).split())
missing = sorted(used - css_classes - js_hooks)
check(not missing, "every CSS class used is defined or is a JavaScript hook"
      + (f" (missing: {missing})" if missing else ""))

print(f"files checked : {len(files)}")
print(f"assertions    : {len(checks)}")
if errors:
    print(f"\nFAILURES ({len(errors)}):")
    for e in errors:
        print("  FAIL ", e)
    sys.exit(1)
print("research site verification passed: links resolve, no orphans, approved hosts only, no placeholders")
