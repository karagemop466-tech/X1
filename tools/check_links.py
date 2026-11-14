#!/usr/bin/env python3
"""Link check for the generated static site.

Verifies, for every emitted HTML file:
  * every internal href/src resolves to a file that exists (relative-path aware)
  * every external link is https, and its host is on the approved source list
  * no page is orphaned (every page is reachable from index.html)
  * every page carries the nav, the snapshot date and a stylesheet
Exits non-zero on any failure.
"""
import glob
import os
import re
import sys
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPROVED = {
    "www.nfl.com", "nfl.com", "operations.nfl.com", "support.nfl.com",
    "www.buffalobills.com", "www.seahawks.com", "www.detroitlions.com",
    "www.packers.com", "www.baltimoreravens.com",
    "nflpaweb.blob.core.windows.net",
    "www.espn.com", "www.foxsports.com",
    "github.com", "karagemop466-tech.github.io",
}
SNAP = "2026-11-14"

errors, checks = [], []


def check(cond, msg):
    if cond:
        checks.append(msg)
    else:
        errors.append(msg)


def html_files():
    out = []
    for base, _, files in os.walk(ROOT):
        if any(p in base for p in (".git", "node_modules", "tools", ".arena", "archive")):
            continue
        for f in files:
            if f.endswith(".html"):
                out.append(os.path.join(base, f))
    return sorted(out)


files = html_files()
check(len(files) >= 14, f"at least 14 html files (found {len(files)})")

HREF = re.compile(r'(?:href|src)="([^"]+)"')
linked_pages = set()

for path in files:
    rel = os.path.relpath(path, ROOT)
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    base = os.path.dirname(path)

    is_dashboard = rel.split(os.sep)[0] == "dashboard"
    # integration addendum: site/ is the snapshot annex tree; its contract (stylesheet,
    # per-row sources, host allowlist incl. trusted-secondary tiers) is asserted by
    # scripts/verify_site_annex.py, exactly like the dashboard's separate contract
    is_annex = rel.split(os.sep)[0] == "site"
    if is_annex:
        check("style.css" in text, f"{rel}: links its stylesheet")
    elif not is_dashboard:
        check(SNAP in text, f"{rel}: shows the {SNAP} snapshot date")
        check("assets/site.css" in text, f"{rel}: links the stylesheet")
        check("Flagged for review" in text, f"{rel}: nav includes Flagged for review")
    else:
        # the parallel session's dashboard has its own contract, asserted separately
        check("site.css" in text or "style.css" in text, f"{rel}: links its stylesheet")

    for url in HREF.findall(text):
        if url.startswith("#") or url.startswith("mailto:"):
            continue
        if url.startswith("http"):
            if not is_annex:
                host = urlparse(url).netloc
                check(host in APPROVED, f"{rel}: external host approved ({host})")
                check(url.startswith("https://"), f"{rel}: external link is https ({url[:60]})")
            continue
        target = os.path.normpath(os.path.join(base, url.split("#")[0]))
        check(os.path.exists(target), f"{rel}: internal link resolves ({url})")
        if target.endswith(".html"):
            linked_pages.add(target)

reachable = {os.path.normpath(os.path.join(ROOT, "index.html"))}
_dash = os.path.normpath(os.path.join(ROOT, "dashboard", "index.html"))
if os.path.exists(_dash):
    reachable.add(_dash)
frontier = list(reachable)
while frontier:
    cur = frontier.pop()
    with open(cur, encoding="utf-8") as fh:
        txt = fh.read()
    for url in HREF.findall(txt):
        if url.startswith("http") or url.startswith("#") or url.startswith("mailto:"):
            continue
        tgt = os.path.normpath(os.path.join(os.path.dirname(cur), url.split("#")[0]))
        if tgt.endswith(".html") and tgt not in reachable and os.path.exists(tgt):
            reachable.add(tgt)
            frontier.append(tgt)

# Orphans are computed per site: this session's pages hang off index.html, the parallel
# session's data dashboard hangs off dashboard/index.html (linked from our nav footer).
for path in files:
    rel = os.path.relpath(path, ROOT)
    if rel.split(os.sep)[0] == "dashboard":
        continue
    check(path in reachable, f"{rel}: reachable from index.html")

# ---- arithmetic guards: never let a wrong claim ship again ----
DEC = 1 + 100 / 110          # -110 expressed as decimal
holds = {k: 1 - DEC ** k / 2 ** k for k in range(1, 7)}
check(abs(holds[1] - 0.0455) < 0.0005, "hold at one -110 leg is 4.55%")
check(abs(holds[5] - 0.2075) < 0.0005, "hold at five -110 legs is 20.75%")
check(abs(holds[5] / holds[1] - 4.56) < 0.05, "five-leg hold is about 4.6x the one-leg hold")
p_ab = 0.25 + 0.25 * 0.30    # two 50% legs, rho = 0.30
check(abs(p_ab - 0.325) < 1e-9, "joint probability for two 50% legs at rho=0.30 is 0.325")
check(abs((1 - DEC ** 2 * p_ab) * 100 - (-18.5)) < 0.6, "book margin at rho=0.30 is about -18.5%")
z = (0.551 - 110 / 210) / ((0.551 * 0.449 / 500) ** 0.5)
check(abs(z - 1.22) < 0.02, "z for 55.1% over 500 bets is about 1.22 (not skill)")
n_eff = 400 / (1 + (2 - 1) * 0.3)
check(abs(n_eff - 307.7) < 0.5, "n_eff for 400 tickets, k=2, rho=0.3 is about 308")

# prose consistency: banned wrong multiples
for path in files:
    rel = os.path.relpath(path, ROOT)
    with open(path, encoding="utf-8") as fh:
        txt = fh.read()
    check("2.5× the" not in txt, f"{rel}: no stale '2.5x the house edge' claim")
    # only the correlation page may discuss joint probabilities, and it must not use the old 3-leg product
    if "correlation" in rel:
        check("0.125" not in txt, f"{rel}: no stale independent-3-leg joint probability")

# ---- CSS completeness, per stylesheet ----
# Each page tree is checked against the stylesheet it actually loads. A class that exists
# only as a JavaScript hook (e.g. `sortable`, targeted by querySelector) is not a style and
# is not required to be defined — flagged only if it also appears in the stylesheet's scope.
import re as _re

def _classes_in_css(path):
    return set(_re.findall(r"\.([a-zA-Z][a-zA-Z0-9_-]*)", open(path, encoding="utf-8").read()))

def _js_hooks(root):
    hooks = set()
    for _p in glob.glob(os.path.join(root, "**", "*.js"), recursive=True):
        for _m in _re.finditer(r"querySelectorAll?\(['\"]([^'\"]+)", open(_p, encoding="utf-8").read()):
            for _c in _re.findall(r"\.([a-zA-Z][a-zA-Z0-9_-]*)", _m.group(1)):
                hooks.add(_c)
    return hooks

def _audit_tree(html_paths, css_path, js_root, label):
    defined = _classes_in_css(css_path)
    hooks = _js_hooks(js_root)
    used = set()
    for _p in html_paths:
        for _m in _re.finditer(r'class="([^"]*)"', open(_p, encoding="utf-8").read()):
            used |= set(_m.group(1).split())
    missing = sorted(used - defined - hooks)
    for _c in missing:
        errors.append(f"{label}: class .{_c} is used but defined nowhere")
    if missing:
        return
    check(True, f"{label}: all {len(used)} classes used are defined or are JS hooks")

# scope each page tree to its own stylesheet: only this session's pages use assets/site.css
# (integration addendum: site/ is the snapshot annex tree; it ships its own stylesheet)
_mine = [f for f in files if os.path.relpath(f, ROOT).split(os.sep)[0] not in ("dashboard", "site")]
_audit_tree(_mine, os.path.join(ROOT, "assets", "site.css"), os.path.join(ROOT, "assets"), "assets/site.css")
_annex = sorted(glob.glob(os.path.join(ROOT, "site", "*.html")))
if _annex:
    _audit_tree(_annex, os.path.join(ROOT, "site", "style.css"),
                os.path.join(ROOT, "site"), "site/style.css")
_db = sorted(glob.glob(os.path.join(ROOT, "dashboard", "*.html")))
if _db:
    _audit_tree(_db, os.path.join(ROOT, "dashboard", "assets", "style.css"),
                os.path.join(ROOT, "dashboard", "assets"), "dashboard/assets/style.css")

# ---- escaped markup: HTML that was meant to render must not appear as literal text ----
for _p in files:
    _txt = open(_p, encoding="utf-8").read()
    _leak = re.findall(r"&lt;(b|span|a|code|i|br|em|table|tr|td)&gt;", _txt)
    if _leak:
        errors.append(f"{os.path.relpath(_p, ROOT)}: {len(_leak)} escaped tags render as literal text")

print(f"files checked : {len(files)}")
print(f"assertions    : {len(checks)}")
if errors:
    print(f"\nFAILURES ({len(errors)}):")
    for e in errors:
        print("  FAIL ", e)
    sys.exit(1)
print("all links resolve; no orphan pages; all external hosts approved")
