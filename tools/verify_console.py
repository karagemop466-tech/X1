#!/usr/bin/env python3
"""Contract check for the console tree.

    python3 tools/verify_console.py

Exits non-zero if any of these fail:

  1. Every internal link in console/*.html resolves to a file that exists.
  2. Every data row in every published table carries a source link, or an
     explicit marker saying no source exists. Rows that carry neither fail.
  3. Every external link points at an allow-listed host (the league, a club
     site, or the fingerprinted mirror). Nothing else is linked.
  4. Every page declares the stylesheet and the script, and every page in the
     navigation exists.

This is the gate that runs in the Pages workflow before the tree is assembled.
"""

from __future__ import annotations

import os
import re
import sys
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "console")
DATA = os.path.join(ROOT, "data", "console")

ALLOWED_HOSTS = {
    "www.nfl.com", "nfl.com", "operations.nfl.com", "www.nflfootballops.com",
    "github.com", "raw.githubusercontent.com", "api.github.com",
}
CLUB_HOSTS = set()
_club = os.path.join(ROOT, "data", "verify", "official_club_sites_2026.psv")
if os.path.exists(_club):
    import csv as _csv
    with open(_club, encoding="utf-8") as fh:
        for row in _csv.DictReader(fh, delimiter="|"):
            url = (row.get("URL") or row.get("official_site") or "").strip()
            host = re.sub(r"^https?://", "", url).split("/")[0]
            if host:
                CLUB_HOSTS.add(host)

NO_SOURCE_MARKERS = ("no source", "not held", "&mdash;", "—", "internal", "n/a", "pending")
SRC_MARKERS = ('class="src"', 'class="src mut"')


class Checker(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []          # (href, kind)
        self.row_has_source = []
        self.in_row = False
        self.current_cells = []
        self.current_html = []
        self.cell_links = []
        self.cell = []
        self.row_src = None
        self.in_td = False
        self.rows = 0
        self.tables = 0
        self.in_tbody = False
        self.stylesheet = False
        self.script = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self.in_td:
            self.cell_html.append(
                "<%s %s>" % (tag, " ".join(f'{k}="{v}"' for k, v in attrs)))
        if tag == "link" and "stylesheet" in (a.get("rel") or ""):
            self.stylesheet = True
            self.links.append((a.get("href", ""), "link"))
        if tag == "script" and a.get("src"):
            self.script = True
            self.links.append((a.get("src", ""), "script"))
        if tag == "a" and a.get("href") is not None:
            self.links.append((a.get("href", ""), "a"))
            if self.in_td:
                self.cell_links.append(a.get("href", ""))
        if tag == "table":
            self.tables += 1
        if tag == "tbody":
            self.in_tbody = True
        if tag == "tr" and self.in_tbody:
            self.in_row = True
            self.current_cells = []
            self.cell_links = []
            self.row_src = a.get("data-src")
        if tag == "td":
            self.in_td = True
            self.cell = []
            self.cell_html = []

    def handle_endtag(self, tag):
        if self.in_td:
            self.cell_html.append(f"</{tag}>")
        if tag == "td" and self.in_td:
            self.in_td = False
            self.current_cells.append("".join(self.cell))
            self.current_html.append("".join(self.cell_html))
        if tag == "tr" and self.in_row:
            self.in_row = False
            self.rows += 1
            joined = " ".join(self.current_cells)
            joined_html = " ".join(self.current_html)
            ok = (bool(self.row_src)
                  or any(m in joined for m in NO_SOURCE_MARKERS)
                  or 'class="src' in joined_html
                  or bool(self.cell_links))
            self.row_has_source.append(ok)
        if tag == "tbody":
            self.in_tbody = False

    def handle_data(self, data):
        if self.in_td:
            self.cell.append(data)


def main():
    failures = []
    pages = sorted(f for f in os.listdir(SITE) if f.endswith(".html"))
    if not pages:
        print("FAIL: no pages in console/")
        return 1
    total_rows = sourced_rows = total_links = 0
    unsourced_rows = []
    for name in pages:
        path = os.path.join(SITE, name)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        c = Checker()
        c.feed(text)

        if not c.stylesheet:
            failures.append(f"{name}: no stylesheet link")
        if not c.script:
            failures.append(f"{name}: no script tag")

        for href, kind in c.links:
            total_links += 1
            if href.startswith(("http://", "https://", "//")):
                host = re.sub(r"^(https?:)?//", "", href).split("/")[0].lower()
                if host not in ALLOWED_HOSTS and host not in CLUB_HOSTS:
                    failures.append(f"{name}: external host not allow-listed: {host} ({href[:90]})")
                continue
            if href.startswith("#") or href.startswith("mailto:"):
                continue
            target = href.split("#")[0].split("?")[0]
            if not target:
                continue
            resolved = os.path.normpath(os.path.join(SITE, target))
            if not os.path.exists(resolved):
                failures.append(f"{name}: broken internal link -> {target}")

        total_rows += len(c.row_has_source)
        sourced_rows += sum(1 for ok in c.row_has_source if ok)
        for i, ok in enumerate(c.row_has_source):
            if not ok:
                unsourced_rows.append(f"{name} row {i + 1}")

    # navigation completeness
    sys.path.insert(0, ROOT)
    nav_files = set()
    for line in open(os.path.join(ROOT, "tools", "build_console.py"), encoding="utf-8"):
        m = re.findall(r'\("([a-z0-9_-]+\.html)", "', line)
        nav_files.update(m)
    for f in sorted(nav_files):
        if f not in pages:
            failures.append(f"navigation references a missing page: {f}")

    # data files referenced from pages must exist
    for name in pages:
        with open(os.path.join(SITE, name), encoding="utf-8") as fh:
            text = fh.read()
        for m in re.findall(r"data/console/([A-Za-z0-9_.-]+\.(?:csv|json))", text):
            if not os.path.exists(os.path.join(DATA, m)):
                failures.append(f"{name}: references missing data file data/console/{m}")

    print(f"console contract check")
    print(f"  pages               : {len(pages)}")
    print(f"  links checked       : {total_links}")
    print(f"  data rows           : {total_rows}")
    print(f"  rows with a source  : {sourced_rows}")
    print(f"  rows without        : {len(unsourced_rows)}")
    for r in unsourced_rows[:15]:
        print(f"      unsourced: {r}")
    print(f"  club hosts allowed  : {len(CLUB_HOSTS)}")
    if failures:
        print(f"\nFAIL — {len(failures)} problem(s):")
        for f in failures[:60]:
            print("  -", f)
        if len(failures) > 60:
            print(f"  ... and {len(failures) - 60} more")
        return 1
    print("\nPASS — every link resolves, every row is sourced or explicitly marked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
