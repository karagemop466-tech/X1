#!/usr/bin/env python3
"""Check links and page contracts across the repository's static site trees.

This checks emitted HTML attributes (not strings inside JavaScript templates), because
runtime-rendered template strings are data, not links in the HTML source. Each independently
built site tree has its own root and stylesheet. The live official-source tree additionally
gets its dynamic navigation from ``assets/x1-live/site.js``; its JSON row citations are checked
by ``scripts/pipeline/verify_site.py``.

The script also retains the small arithmetic regression guards used by the site prose.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
SNAP = "2026-11-14"

BASE_APPROVED = {
    "nflpaweb.blob.core.windows.net",
    "github.com",
    "karagemop466-tech.github.io",
    "www.itl.nist.gov",
    "itl.nist.gov",
    "www.espn.com",       # corroboration-only links on the Flagged for Review page
    "www.foxsports.com",  # corroboration-only links on the Flagged for Review page
}
RESEARCH_APPROVED = {
    "media.nfl.com", "nextgenstats.nfl.com", "operations.nfl.com", "static.www.nfl.com",
}
ANNEX_APPROVED = {
    "raw.githubusercontent.com", "nbcsports.com", "www.nbcsports.com",
    "sofistadium.com", "www.sofistadium.com", "profootballhof.com",
    "www.profootballhof.com", "nytimes.com", "www.nytimes.com",
    "sports.yahoo.com",
}
DASHBOARD_APPROVED = {"www.espn.com", "www.foxsports.com"}

errors: list[str] = []
checks: list[str] = []


def check(condition: bool, message: str) -> None:
    if condition:
        checks.append(message)
    else:
        errors.append(message)


class HTMLAttributes(HTMLParser):
    """Collect actual attributes from tags; HTMLParser does not parse script text as tags."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.classes: set[str] = set()

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: D102
        values = dict(attrs)
        for key in ("href", "src"):
            if values.get(key):
                self.links.append(values[key])
        if values.get("class"):
            self.classes.update(values["class"].split())


def parse_html(path: Path) -> tuple[str, HTMLAttributes]:
    text = path.read_text(encoding="utf-8")
    parser = HTMLAttributes()
    parser.feed(text)
    return text, parser


def page_tree(path: Path) -> str:
    rel = path.relative_to(ROOT)
    return rel.parts[0] if len(rel.parts) > 1 and rel.parts[0] in {
        "dashboard", "research", "site", "live"
    } else "root"


def html_files() -> list[Path]:
    out: list[Path] = []
    excluded = {".git", "node_modules", "tools", ".arena", "archive", "_site"}
    for path in ROOT.rglob("*.html"):
        if any(part in excluded for part in path.relative_to(ROOT).parts):
            continue
        out.append(path)
    return sorted(out)


def official_club_hosts() -> set[str]:
    """Get official club domains from the NFL-owned team registry snapshot."""
    path = ROOT / "data/pipeline/club_registry.json"
    try:
        rows = json.loads(path.read_text(encoding="utf-8")).get("rows", [])
    except (OSError, json.JSONDecodeError, AttributeError):
        return set()
    hosts: set[str] = set()
    for row in rows:
        host = urlparse(row.get("official_site", "")).hostname
        if host:
            hosts.add(host.lower())
            hosts.add(host.lower().removeprefix("www."))
            hosts.add("www." + host.lower().removeprefix("www."))
    return hosts


CLUB_HOSTS = official_club_hosts()


def host_is_nfl(host: str) -> bool:
    host = host.lower().rstrip(".")
    return host == "nfl.com" or host.endswith(".nfl.com") or host == "operations.nfl.com"


def approved_host(host: str, tree: str) -> bool:
    host = host.lower().rstrip(".")
    if host_is_nfl(host) or host in BASE_APPROVED or host in CLUB_HOSTS:
        return True
    if tree == "research" and host in RESEARCH_APPROVED:
        return True
    if tree == "site" and host in ANNEX_APPROVED:
        return True
    if tree == "dashboard" and host in DASHBOARD_APPROVED:
        return True
    return False


def external_or_local(path: Path, url: str, tree: str) -> Path | None:
    """Return an internal target path, or None for an approved external/special URL."""
    parsed = urlparse(url)
    if parsed.scheme or parsed.netloc:
        host = parsed.hostname or ""
        check(url.startswith("https://"), f"{path.relative_to(ROOT)}: external link is https ({url[:70]})")
        check(approved_host(host, tree), f"{path.relative_to(ROOT)}: external host approved ({host})")
        return None
    if url.startswith(("#", "mailto:", "javascript:", "tel:", "data:")):
        return None
    if not parsed.path:
        return None
    target_path = unquote(parsed.path)
    if target_path.startswith("/"):
        return (ROOT / target_path.lstrip("/")).resolve()
    return (path.parent / target_path).resolve()


files = html_files()
check(len(files) >= 14, f"at least 14 HTML files (found {len(files)})")
parsed_pages: dict[Path, tuple[str, HTMLAttributes]] = {}

for path in files:
    text, attrs = parse_html(path)
    parsed_pages[path] = (text, attrs)
    rel = path.relative_to(ROOT).as_posix()
    tree = page_tree(path)

    if tree == "live":
        check("assets/x1-live/site.css" in text, f"{rel}: links the live-pipeline stylesheet")
    elif tree == "research":
        check(SNAP in text, f"{rel}: shows the {SNAP} snapshot date")
        check("assets/styles.css" in text, f"{rel}: links the research stylesheet")
        check("Flagged for review" in text, f"{rel}: nav includes Flagged for review")
    elif tree == "site":
        check("style.css" in text, f"{rel}: links the snapshot-annex stylesheet")
    elif tree == "dashboard":
        check("site.css" in text or "style.css" in text, f"{rel}: links its stylesheet")
    else:
        check(SNAP in text, f"{rel}: shows the {SNAP} snapshot date")
        check("assets/site.css" in text, f"{rel}: links the stylesheet")
        check("Flagged for review" in text, f"{rel}: nav includes Flagged for review")

    for url in attrs.links:
        target = external_or_local(path, url, tree)
        if target is not None:
            check(target.exists(), f"{rel}: internal link resolves ({url})")

# JavaScript-generated nav links are real runtime links and should still be checked.
LIVE_NAV_RE = re.compile(r"\{\s*href:\s*'([^']+)'\s*,\s*label:", re.I)
NAV_FILES = {
    "live": ROOT / "assets/x1-live/site.js",
}
nav_targets: dict[str, list[Path]] = {}
for tree, js_path in NAV_FILES.items():
    try:
        js = js_path.read_text(encoding="utf-8")
    except OSError:
        errors.append(f"missing {js_path.relative_to(ROOT)}")
        continue
    targets = []
    for href in sorted(set(LIVE_NAV_RE.findall(js))):
        target = (ROOT / tree / href).resolve()
        check(target.exists(), f"{tree} JavaScript nav target resolves ({href})")
        targets.append(target)
    nav_targets[tree] = targets

# Reachability is verified separately for each independently built site tree. This prevents
# an archived experiment from being mistaken for a missing page in the main dashboard.
roots = {
    "root": [ROOT / "index.html"],
    # The legacy dashboard and its separate research lab are independent trees.
    "dashboard": [ROOT / "dashboard/index.html", ROOT / "dashboard/lab-index.html"],
    "research": [ROOT / "research/index.html"],
    "site": [ROOT / "site/index.html"],
    "live": [ROOT / "live/index.html"],
}
for tree, root_candidates in roots.items():
    tree_files = [p for p in files if page_tree(p) == tree]
    if not tree_files:
        continue
    tree_roots = [p.resolve() for p in root_candidates if p.exists()]
    check(bool(tree_roots), f"{tree}: has a landing page")
    if not tree_roots:
        continue
    reachable = set(tree_roots)
    frontier = list(tree_roots)
    while frontier:
        current = frontier.pop()
        _, attrs = parsed_pages.get(current, parse_html(current))
        links = list(attrs.links)
        if tree in nav_targets and page_tree(current) == tree:
            links.extend(os.path.relpath(p, current.parent) for p in nav_targets[tree])
        for url in links:
            parsed = urlparse(url)
            if parsed.scheme or parsed.netloc or url.startswith(("#", "mailto:", "javascript:", "tel:", "data:")):
                continue
            target = external_or_local(current, url, tree)
            if (target is not None and target.suffix.lower() == ".html" and target.exists()
                    and page_tree(target) == tree and target not in reachable):
                reachable.add(target)
                frontier.append(target)
    for path in tree_files:
        check(path.resolve() in reachable, f"{path.relative_to(ROOT)}: reachable from {tree}/index.html")

# ---- arithmetic guards: preserve the reviewed calculations used in explanatory copy ----
DEC = 1 + 100 / 110
holds = {k: 1 - DEC ** k / 2 ** k for k in range(1, 7)}
check(abs(holds[1] - 0.0455) < 0.0005, "hold at one -110 leg is 4.55%")
check(abs(holds[5] - 0.2075) < 0.0005, "hold at five -110 legs is 20.75%")
check(abs(holds[5] / holds[1] - 4.56) < 0.05, "five-leg hold is about 4.6x the one-leg hold")
p_ab = 0.25 + 0.25 * 0.30
check(abs(p_ab - 0.325) < 1e-9, "joint probability for two 50% legs at rho=0.30 is 0.325")
check(abs((1 - DEC ** 2 * p_ab) * 100 - (-18.5)) < 0.6, "book margin at rho=0.30 is about -18.5%")
z = (0.551 - 110 / 210) / ((0.551 * 0.449 / 500) ** 0.5)
check(abs(z - 1.22) < 0.02, "z for 55.1% over 500 bets is about 1.22 (not skill)")
n_eff = 400 / (1 + (2 - 1) * 0.3)
check(abs(n_eff - 307.7) < 0.5, "n_eff for 400 tickets, k=2, rho=0.3 is about 308")

# prose consistency: catch previously published arithmetic slips.
for path in files:
    text, _ = parsed_pages[path]
    rel = path.relative_to(ROOT).as_posix()
    check("2.5× the" not in text, f"{rel}: no stale '2.5x the house edge' claim")
    if "correlation" in rel.lower():
        check("0.125" not in text, f"{rel}: no stale independent-3-leg joint probability")

# ---- CSS completeness, separately for each built page tree ----
def classes_in_css(path: Path) -> set[str]:
    return set(re.findall(r"\.([a-zA-Z][a-zA-Z0-9_-]*)", path.read_text(encoding="utf-8")))


def js_selector_hooks(root: Path) -> set[str]:
    hooks: set[str] = set()
    for js_path in root.glob("*.js"):
        src = js_path.read_text(encoding="utf-8")
        for match in re.finditer(r"querySelectorAll?\(['\"]([^'\"]+)", src):
            hooks.update(re.findall(r"\.([a-zA-Z][a-zA-Z0-9_-]*)", match.group(1)))
    return hooks


def js_static_class_tokens(root: Path) -> set[str]:
    """Recognize static classes emitted by JS without treating `${...}` as class names."""
    result: set[str] = set()
    for js_path in root.glob("*.js"):
        src = js_path.read_text(encoding="utf-8")
        for match in re.finditer(r"class\s*=\s*['\"]([^'\"]+)['\"]", src):
            for token in match.group(1).split():
                if "$" not in token and "{" not in token and "}" not in token:
                    result.add(token)
    return result


def audit_css(html_paths: list[Path], css_path: Path, js_root: Path, label: str) -> None:
    if not css_path.exists():
        errors.append(f"{label}: stylesheet missing ({css_path.relative_to(ROOT)})")
        return
    defined = classes_in_css(css_path)
    hooks = js_selector_hooks(js_root)
    used: set[str] = set()
    for path in html_paths:
        _, attrs = parsed_pages[path]
        used.update(attrs.classes)
    used.update(js_static_class_tokens(js_root))
    missing = sorted(used - defined - hooks)
    for name in missing:
        errors.append(f"{label}: class .{name} is used but defined nowhere")
    if not missing:
        check(True, f"{label}: all {len(used)} observed classes are defined or are JS hooks")


mine = [p for p in files if page_tree(p) == "root"]
audit_css(mine, ROOT / "assets/site.css", ROOT / "assets", "assets/site.css")
for tree, css in (
    ("research", ROOT / "research/assets/styles.css"),
    ("site", ROOT / "site/style.css"),
    ("live", ROOT / "assets/x1-live/site.css"),
):
    paths = [p for p in files if page_tree(p) == tree]
    if paths:
        js_root = ROOT / ("assets/x1-live" if tree == "live" else tree)
        audit_css(paths, css, js_root, str(css.relative_to(ROOT)))

# Escaped markup in these static pages is generally a template error. Script contents are ignored
# by HTMLParser; check only the rendered text as an inexpensive regression guard.
for path in files:
    text, _ = parsed_pages[path]
    if re.search(r"&lt;(?:b|span|a|code|i|br|em|table|tr|td)&gt;", text):
        errors.append(f"{path.relative_to(ROOT)}: escaped tags may render as literal text")

print(f"files checked : {len(files)}")
print(f"assertions    : {len(checks)}")
if errors:
    print(f"\nFAILURES ({len(errors)}):")
    for item in errors:
        print("  FAIL ", item)
    sys.exit(1)
print("all internal links resolve; all site-tree pages reachable; external hosts approved")
