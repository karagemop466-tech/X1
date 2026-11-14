#!/usr/bin/env python3
"""Static site verifier.

Checks, before anything is published:
  1. every internal link in every page resolves to a file that exists;
  2. every navigation entry in the shared JS resolves to a real page;
  3. every `table[data-src]` points at a JSON file that exists and parses;
  4. every row in every published dataset has an official `_source_url`
     (or the dataset is explicitly declared empty-by-design);
  5. no page references a data file that is not present.

Exits non-zero on any hard failure so the deploy job stops.
"""

from __future__ import annotations

import json
import os
import re
import sys
from html.parser import HTMLParser
from typing import Dict, List, Set, Tuple
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# GitHub Pages is configured with the legacy branch builder on /, so the
# published site is the repository root itself.
SITE = ROOT
DATA = os.path.join(ROOT, "data")

# Datasets that are published empty on purpose because no official source exists.
EMPTY_BY_DESIGN = {"market_lines"}

HREF_RE = re.compile(r'href="([^"]+)"', re.I)
SRC_RE = re.compile(r'data-src="([^"]+)"', re.I)
NAV_RE = re.compile(r"\{\s*href:\s*'([^']+)'", re.I)


class LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: List[Tuple[str, str]] = []   # (attribute, value)
        self.tables: List[Dict[str, str]] = []

    def handle_starttag(self, tag, attrs):  # noqa: D102
        attr = dict(attrs)
        if tag == "a" and attr.get("href"):
            self.links.append(("href", attr["href"]))
        if tag == "link" and attr.get("href"):
            self.links.append(("link", attr["href"]))
        if tag == "script" and attr.get("src"):
            self.links.append(("script", attr["src"]))
        if tag == "table":
            self.tables.append(attr)


def is_external(url: str) -> bool:
    parsed = urlparse(url)
    return bool(parsed.netloc)


def main() -> int:
    problems: List[str] = []
    checked_pages = 0
    checked_links = 0
    referenced_data: Set[str] = set()

    pages = sorted(
        f for f in os.listdir(SITE)
        if f.endswith(".html") and os.path.isfile(os.path.join(SITE, f))
    )
    if not pages:
        problems.append("no HTML pages found in site/")

    for page in pages:
        checked_pages += 1
        with open(os.path.join(SITE, page), "r", encoding="utf-8") as handle:
            html = handle.read()
        parser = LinkCollector()
        parser.feed(html)

        for attr, url in parser.links:
            if is_external(url) or url.startswith(("#", "mailto:", "javascript:")):
                continue
            target = os.path.normpath(os.path.join(SITE, url.split("#")[0]))
            checked_links += 1
            if not os.path.exists(target):
                problems.append(f"{page}: <{attr}> points at a missing file: {url}")

        for table in parser.tables:
            src = table.get("data-src")
            if not src:
                continue
            referenced_data.add(os.path.basename(src))
            path = os.path.join(SITE, src)
            if not os.path.exists(path):
                problems.append(f"{page}: table {table.get('id', '(no id)')} missing data file {src}")
                continue
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    json.load(handle)
            except Exception as exc:  # noqa: BLE001
                problems.append(f"{page}: {src} is not valid JSON ({exc})")

    # ------------------------------------------------------------ navigation
    nav_path = os.path.join(SITE, "assets", "js", "site.js")
    if os.path.exists(nav_path):
        with open(nav_path, "r", encoding="utf-8") as handle:
            nav_src = handle.read()
        for href in set(NAV_RE.findall(nav_src)):
            if is_external(href):
                continue
            checked_links += 1
            if not os.path.exists(os.path.join(SITE, href)):
                problems.append(f"site.js nav: missing page {href}")
            if href not in pages:
                problems.append(f"site.js nav: {href} exists but is not a page in site/")

    # ------------------------------------------------------- data row sources
    row_stats: List[Dict[str, object]] = []
    total_rows = 0
    rows_without_source = 0
    if not os.path.isdir(DATA):
        problems.append("site/data is missing — run the copy step before building")
    else:
        for name in sorted(os.listdir(DATA)):
            if not name.endswith(".json") or name.startswith("_"):
                continue
            path = os.path.join(DATA, name)
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
            except Exception as exc:  # noqa: BLE001
                problems.append(f"data/{name}: unreadable ({exc})")
                continue
            rows = payload.get("rows") or []
            key = payload.get("dataset", name[:-5])
            missing = sum(1 for row in rows if not row.get("_source_url"))
            total_rows += len(rows)
            rows_without_source += missing
            row_stats.append({"dataset": key, "rows": len(rows), "without_source": missing})
            if missing and key not in EMPTY_BY_DESIGN:
                problems.append(f"data/{name}: {missing} row(s) have no _source_url")
            if not rows and key not in EMPTY_BY_DESIGN and not payload.get("empty"):
                problems.append(f"data/{name}: published with zero rows and not declared empty")

    # ------------------------------------------------------------------ report
    print(f"pages checked:        {checked_pages}")
    print(f"internal links:       {checked_links}")
    print(f"data rows checked:    {total_rows}")
    print(f"rows without source:  {rows_without_source}")
    for stat in row_stats:
        print(f"  {stat['dataset']:<16} rows={stat['rows']:<6} without_source={stat['without_source']}")
    if problems:
        print(f"\n{len(problems)} PROBLEM(S):")
        for problem in problems:
            print("  !", problem)
        return 1
    print("\nverify_site: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
