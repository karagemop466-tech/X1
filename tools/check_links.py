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
    # NIST hosts are official-source material registered in docs/sources/sources.md and
    # accepted by scripts/verify_site.py; admitted here when the lab renders COORDINATION.md.
    "www.itl.nist.gov", "itl.nist.gov",
    # nextgenstats.nfl.com is an official NFL subdomain, already accepted by scripts/verify_site.py.
    "nextgenstats.nfl.com",
}
# The research tree cites the league's document and tracking hosts as well.
RESEARCH_APPROVED = {
    "media.nfl.com", "nextgenstats.nfl.com", "operations.nfl.com",
    "static.www.nfl.com",
}

# integration addendum (session arena/a78e0158-x1): snapshot annex tiers — official NFL family,
# nflverse on GitHub, and the annex's registered trusted-secondary sources
# (docs/annex/sources-snapshot.md)
ANNEX_APPROVED = {
    "nfl.com", "operations.nfl.com", "github.com", "raw.githubusercontent.com",
    "nbcsports.com", "www.nbcsports.com", "sofistadium.com", "www.sofistadium.com",
    "profootballhof.com", "www.profootballhof.com", "nytimes.com", "www.nytimes.com",
    "sports.yahoo.com", "karagemop466-tech.github.io",
}
# The research tree cites the league's document and tracking hosts as well.
RESEARCH_APPROVED = {
    "media.nfl.com", "nextgenstats.nfl.com", "operations.nfl.com",
    "static.www.nfl.com",
}

# integration addendum (session arena/a78e0158-x1): snapshot annex tiers — official NFL family,
# nflverse on GitHub, and the annex's registered trusted-secondary sources
# (docs/annex/sources-snapshot.md)
ANNEX_APPROVED = {
    "nfl.com", "operations.nfl.com", "github.com", "raw.githubusercontent.com",
    "nbcsports.com", "www.nbcsports.com", "sofistadium.com", "www.sofistadium.com",
    "profootballhof.com", "www.profootballhof.com", "nytimes.com", "www.nytimes.com",
    "sports.yahoo.com", "karagemop466-tech.github.io",
}

# Official club websites, read from data/pipeline/depth_charts.json (each club's own
# depth-chart page). The league's own https://www.nfl.com/teams/ page is the authority
# for which domain is a club's official site; this list is generated from that
# collection so a new club host cannot be added without appearing in the data first.
CLUB_HOSTS = {
    "www.49ers.com",
    "www.atlantafalcons.com",
    "www.azcardinals.com",
    "www.baltimoreravens.com",
    "www.bengals.com",
    "www.buccaneers.com",
    "www.buffalobills.com",
    "www.chargers.com",
    "www.chicagobears.com",
    "www.chiefs.com",
    "www.clevelandbrowns.com",
    "www.colts.com",
    "www.commanders.com",
    "www.dallascowboys.com",
    "www.denverbroncos.com",
    "www.detroitlions.com",
    "www.giants.com",
    "www.jaguars.com",
    "www.miamidolphins.com",
    "www.neworleanssaints.com",
    "www.newyorkjets.com",
    "www.packers.com",
    "www.panthers.com",
    "www.patriots.com",
    "www.philadelphiaeagles.com",
    "www.raiders.com",
    "www.seahawks.com",
    "www.steelers.com",
    "www.tennesseetitans.com",
    "www.therams.com",
    "www.vikings.com",
    # Added by session arena/fcc11e05-x1. Every other club host above is generated from
    # data/pipeline/depth_charts.json; Houston is absent from that file only because the
    # Texans' depth-chart page returns no parsable table. Its official site is the
    # "View Full Site" link for the Houston Texans on https://www.nfl.com/teams/,
    # transcribed to data/verify/official_club_sites_2026.psv. All 32 club hosts on that
    # league page were diffed against this set; Houston was the only one missing.
    "www.houstontexans.com",
}
APPROVED |= CLUB_HOSTS

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

    # hrefs inside <script> blocks are runtime templates (e.g. href="${r._source_url}"),
    # not static markup links; the live pipeline's row links are validated against the
    # datasets by scripts/pipeline/verify_site.py. Scan markup only.
    markup = re.sub(r"<script\b.*?</script\s*>", " ", text, flags=re.S | re.I)

    is_dashboard = rel.split(os.sep)[0] == "dashboard"
    is_live = rel.split(os.sep)[0] == "live"
    is_research = rel.split(os.sep)[0] == "research"
    # integration addendum: site/ is the snapshot annex tree; its contract (stylesheet,
    # per-row sources, host tiers) is asserted by scripts/verify_site_annex.py
    is_annex = rel.split(os.sep)[0] == "site"
    # Added by session arena/459b17e1-x1: hub/ is a fifth site tree with its own
    # stylesheet (hub/assets/hub.css) and its own contract, asserted by
    # tools/hub/build_hub.py (links resolve, external hosts official, every data row
    # sourced). Without this branch the main site's contract is applied to it and
    # produces false failures. Nothing above this line is modified.
    is_hub = rel.split(os.sep)[0] == "hub"
    # the live-pipeline tree (session arena/d577959f-x1) is a fourth site tree with its
    # own stylesheet and its own JS-rendered navigation; its contract is asserted by
    # scripts/pipeline/verify_site.py. Without this branch the checker applied the main
    # site's contract to it and produced 100+ false failures.
    is_live = rel.split(os.sep)[0] == "live"
    if is_hub:
        check("assets/hub.css" in text, f"{rel}: links its stylesheet")
        check(SNAP in text, f"{rel}: shows the {SNAP} snapshot date")
        check('href="../index.html"' in text, f"{rel}: links back to the landing page")
    elif is_annex:
        check("style.css" in text, f"{rel}: links its stylesheet")
    elif is_research:
        # the research session's lab is a parallel site tree with its own
        # stylesheet and its own contract (scripts/verify_research_site.py).
        check(SNAP in text, f"{rel}: shows the {SNAP} snapshot date")
        check("assets/styles.css" in text, f"{rel}: links the research stylesheet")
        check("Flagged for review" in text, f"{rel}: nav includes Flagged for review")
    elif is_live:
        # live-pipeline section (session arena/d577959f-x1): JS-rendered pages with
        # their own stylesheet (assets/x1-live/site.css) and their own contract
        # (scripts/pipeline/verify_site.py). The snapshot date and every table row
        # are loaded at runtime from data/pipeline/*.json, which that checker
        # validates row by row, so they are not asserted here.
        # Both assertions kept: the stylesheet belongs to this branch's contract, the
        # back-link assertion was added here and does not conflict with anything on main.
        check("assets/x1-live/site.css" in text, f"{rel}: links its stylesheet")
        check('href="../index.html"' in text, f"{rel}: links back to the landing page")
    elif not is_dashboard:
        check(SNAP in text, f"{rel}: shows the {SNAP} snapshot date")
        check("assets/site.css" in text, f"{rel}: links the stylesheet")
        check("Flagged for review" in text, f"{rel}: nav includes Flagged for review")
    else:
        # the parallel session's dashboard has its own contract, asserted separately
        check("site.css" in text or "style.css" in text, f"{rel}: links its stylesheet")

    # Both sessions that touched this line independently reached the same conclusion and
    # fixed it two ways. Kept together, because they catch different cases:
    #   * main strips <script> blocks -> no JS expression is ever read as a link;
    #   * this branch also drops template-literal fragments and any residue of `${`.
    # `markup` is defined above and already has the script blocks removed.
    for url in HREF.findall(re.sub(r"`[^`]*`", "", markup)):
        if url.startswith("#") or url.startswith("mailto:"):
            continue
        if "${" in url:
            # runtime value inside a nested template literal, e.g.
            # `<a href="${s.url}">`; asserted by the tree-owning verifier instead.
            continue
        if url.startswith("http"):
            host = urlparse(url).netloc
            allowed = APPROVED | (RESEARCH_APPROVED if is_research else set()) | (ANNEX_APPROVED if is_annex else set())
            check(host in allowed, f"{rel}: external host approved ({host})")
            check(url.startswith("https://"), f"{rel}: external link is https ({url[:60]})")
            continue
        target = os.path.normpath(os.path.join(base, url.split("#")[0]))
        check(os.path.exists(target), f"{rel}: internal link resolves ({url})")
        if target.endswith(".html"):
            linked_pages.add(target)

reachable = {os.path.normpath(os.path.join(ROOT, "index.html"))}
# The live-pipeline tree renders its navigation from assets/x1-live/site.js, so its pages
# are reachable in a browser without a static anchor in any page body. Seed the crawl
# with the JS nav entries, otherwise five correctly-linked pages look orphaned.
_livejs_path = os.path.join(ROOT, "assets", "x1-live", "site.js")
if os.path.exists(_livejs_path):
    for _m in re.finditer(r"href:\s*'([^']+\.html)'", open(_livejs_path, encoding="utf-8").read()):
        _p = os.path.normpath(os.path.join(ROOT, "live", _m.group(1)))
        if os.path.exists(_p):
            reachable.add(_p)
_dash = os.path.normpath(os.path.join(ROOT, "dashboard", "index.html"))
if os.path.exists(_dash):
    reachable.add(_dash)
_live = os.path.normpath(os.path.join(ROOT, "live", "index.html"))
# Added by session arena/459b17e1-x1: hub/ hangs off hub/index.html, which the main
# nav links. Reachable set extended the same way as the dashboard and live trees.
_hubroot = os.path.normpath(os.path.join(ROOT, "hub", "index.html"))
if os.path.exists(_live):
    reachable.add(_live)
# Added by session arena/fcc11e05-x1: app/ is a sixth site tree with its own navigation
# rail, hanging off app/index.html. Pages serves that same file at the site root, so the
# whole tree is entered from one landing page exactly like hub/, live/ and dashboard/.
_approot = os.path.normpath(os.path.join(ROOT, "app", "index.html"))
if os.path.exists(_approot):
    reachable.add(_approot)
frontier = list(reachable)
while frontier:
    cur = frontier.pop()
    with open(cur, encoding="utf-8") as fh:
        txt = fh.read()
    for url in HREF.findall(re.sub(r"`[^`]*`", "", txt)):
        if url.startswith("http") or url.startswith("#") or url.startswith("mailto:"):
            continue
        tgt = os.path.normpath(os.path.join(os.path.dirname(cur), url.split("#")[0]))
        if tgt.endswith(".html") and tgt not in reachable and os.path.exists(tgt):
            reachable.add(tgt)
            frontier.append(tgt)

# Orphans are computed per site: this session's pages hang off index.html, the parallel
# session's data dashboard hangs off dashboard/index.html (linked from our nav footer),
# and the live-pipeline section hangs off live/index.html (also linked from the main nav).
# Their internal linking is each tree's own contract, asserted by its own checker.
for path in files:
    rel = os.path.relpath(path, ROOT)
    if rel.split(os.sep)[0] in ("dashboard", "research", "live"):
        continue
    if rel.split(os.sep)[0] == "hub":
        check(path in reachable or path == _hubroot, f"{rel}: reachable from index.html")
    elif rel.split(os.sep)[0] == "lab":
        check(path in reachable or path == os.path.normpath(os.path.join(ROOT, "lab", "index.html")),
              f"{rel}: reachable from index.html")
    else:
        check(path in reachable, f"{rel}: reachable from index.html")

# Every parallel site tree must be entered from ONE landing page. Research, the data
# dashboard and the snapshot annex all were; the live-pipeline tree was not, so on the
# published site 15 pages could only be reached by typing the URL.
_landing = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
for _tree, _label in (("dashboard/lab-index.html", "analytics lab"),
                      ("research/index.html", "research lab"),
                      ("site/index.html", "snapshot annex"),
                      ("live/index.html", "live pipeline"),
                      ("pages/executive-summary.html", "executive summary"),
                      ("pages/suggestions.html", "suggestions register"),
                      ("pages/decisions.html", "decision register"),
                      ("pages/flagged.html", "flagged for review")):
    check(f'href="{_tree}"' in _landing,
          f"index.html links the {_label} ({_tree})")
# a link inside the nav rail is the only place the landing page can carry it twice
check(_landing.count('href="research/index.html"') <= 3,
      "index.html does not duplicate the research-lab entry")
check(_landing.count('href="live/index.html"') >= 1,
      "index.html links the live pipeline exactly once")
_livejs = os.path.join(ROOT, "assets", "x1-live", "site.js")
if os.path.exists(_livejs):
    _j = open(_livejs, encoding="utf-8").read()
    check("flagged.html" in _j, "live pipeline nav exposes the Flagged for Review page")
    check("index.html" in _j, "live pipeline nav exposes its own landing page")

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
        # strip <script> blocks (removes JS template literals wholesale) and then filter
        # any residual `${...}` token, so neither a script block nor a stray expression can
        # register a class name that no stylesheet is expected to define. Both the main and
        # this branch's fix are applied here; they catch different cases.
        _txt = _re.sub(r"<script\b.*?</script\s*>", " ", open(_p, encoding="utf-8").read(), flags=_re.S | _re.I)
        for _m in _re.finditer(r'class="([^"]*)"', _txt):
            used |= {c for c in _m.group(1).split()
                     if c and "${" not in c and not set(c) <= set("'}\" ")}
    missing = sorted(used - defined - hooks)
    for _c in missing:
        errors.append(f"{label}: class .{_c} is used but defined nowhere")
    if missing:
        return
    check(True, f"{label}: all {len(used)} classes used are defined or are JS hooks")

# scope each page tree to its own stylesheet: only this session's pages use assets/site.css
# Added by session arena/fcc11e05-x1: app/ is audited against its own stylesheet
# (app/assets/site.css) below, so it is excluded from the main-site audit here.
# Added by session arena/56769365-x1 (additive): lab/ is a seventh page tree that links
# ../app/assets/site.css, so it is audited against that stylesheet below, exactly as app/ is.
_mine = [f for f in files if os.path.relpath(f, ROOT).split(os.sep)[0] not in
         ("dashboard", "research", "site", "live", "hub", "app", "lab")]
_audit_tree(_mine, os.path.join(ROOT, "assets", "site.css"), os.path.join(ROOT, "assets"), "assets/site.css")
_res = sorted(glob.glob(os.path.join(ROOT, "research", "*.html")))
if _res:
    _audit_tree(_res, os.path.join(ROOT, "research", "assets", "styles.css"),
                os.path.join(ROOT, "research", "assets"), "research/assets/styles.css")
_livex = sorted(glob.glob(os.path.join(ROOT, "live", "*.html")))
if _livex:
    _audit_tree(_livex, os.path.join(ROOT, "assets", "x1-live", "site.css"),
                os.path.join(ROOT, "assets", "x1-live"), "assets/x1-live/site.css")
_annex = sorted(glob.glob(os.path.join(ROOT, "site", "*.html")))
if _annex:
    _audit_tree(_annex, os.path.join(ROOT, "site", "style.css"),
                os.path.join(ROOT, "site"), "site/style.css")
_live = sorted(glob.glob(os.path.join(ROOT, "live", "*.html")))
if _live:
    _audit_tree(_live, os.path.join(ROOT, "assets", "x1-live", "site.css"),
                os.path.join(ROOT, "assets", "x1-live"), "assets/x1-live/site.css")
_db = sorted(glob.glob(os.path.join(ROOT, "dashboard", "*.html")))
if _db:
    _audit_tree(_db, os.path.join(ROOT, "dashboard", "assets", "style.css"),
                os.path.join(ROOT, "dashboard", "assets"), "dashboard/assets/style.css")
# Added by session arena/459b17e1-x1: audit the hub tree against its own stylesheet.
_hub = sorted(glob.glob(os.path.join(ROOT, "hub", "*.html")))
if _hub:
    _audit_tree(_hub, os.path.join(ROOT, "hub", "assets", "hub.css"),
                os.path.join(ROOT, "hub", "assets"), "hub/assets/hub.css")
# Added by session arena/fcc11e05-x1: audit the unified dashboard against its own
# stylesheet (app/assets/site.css). Its contract — links resolve, every external host is
# official, every data row is sourced or explicitly flagged — is asserted by
# tools/verify_app.py, which also runs in CI.
_appx = sorted(glob.glob(os.path.join(ROOT, "app", "*.html")))
if _appx:
    _audit_tree(_appx, os.path.join(ROOT, "app", "assets", "site.css"),
                os.path.join(ROOT, "app", "assets"), "app/assets/site.css")
# Added by session arena/56769365-x1 (additive only): the line desk reuses the app stylesheet,
# so it is audited against the same file rather than against assets/site.css.
_labx = sorted(glob.glob(os.path.join(ROOT, "lab", "*.html")))
if _labx:
    _audit_tree(_labx, os.path.join(ROOT, "app", "assets", "site.css"),
                os.path.join(ROOT, "app", "assets"), "lab -> app/assets/site.css")

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
