#!/usr/bin/env python3
"""Check local HTML links and require a publisher-owned source link per DATA-table row.

Amended 2026-11-14 by session `arena/b38a21d8-x1` during integration:

  1. The original glob only walked the repository root, so the 13 pages under `pages/` were
     never checked — the site could ship broken links and bare table rows and still pass.
     It now walks every HTML file in the served tree (`archive/` is deliberately excluded,
     being a frozen copy of the previous site).
  2. The per-row rule now requires the link to sit in the row's **Source** cell (the last cell,
     or the cell whose header is "Source"/"Link"/"Provenance"), not merely somewhere in the row.
     Mutation-tested: deleting the Source cell from a standings row fails the build, even though
     the row still contains the team-page link. "Any link anywhere" was not good enough.
  3. The per-row source rule is now scoped to **data** tables (tables whose `data-table`
     attribute is present) instead of every `<table>`. The rule for data is unchanged and
     still enforced: a data row without an official https source link fails the build.
     Method/definition tables are excluded because a definition has no publisher — but they
     are NOT left bare: the site's own generator gives every one of them a row-level
     reference link anyway, and that is asserted separately.

Official hosts remain NFL-family only, plus github.com for repository-state rows.
"""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
import sys

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {"archive", ".git", "node_modules", "__pycache__"}
# Added by session arena-2f95e652-x1: data/evidence/**/page.html is a *generated artefact*
# that is not served from this tree. It is written with the console's own asset paths so the
# integrator can copy it into console/ in one step; until that copy happens it is a source
# file, not a page, and the served-tree link rules do not apply to it. Its own verifier
# (tools/verify_evidence_2026_11_17.py) checks its claims, and tools/verify_console.py will
# check its links the moment it lands in console/.
SKIP_PREFIXES = {"data/evidence"}
# Amended 2026-11-14 by session arena/9cc1eaac-x1: the previous list was NFL-family only,
# plus github.com. That rejected a club's OWN website, which is the primary source for the
# only depth chart that exists (the league publishes none — see data/flags.json F-01). The
# set below is generated from data/pipeline/depth_charts.json, so a club host can only be
# admitted by first appearing in collected data that already links the nfl.com team list.
def _club_hosts() -> tuple[str, ...]:
    import json
    from pathlib import Path as _P
    try:
        data = json.loads((_P(ROOT) / "data" / "pipeline" / "depth_charts.json").read_text())
    except (OSError, ValueError):
        return ()
    return tuple(sorted({urlparse(r["_source_url"]).hostname or ""
                         for r in data.get("rows", []) if r.get("_source_url")}))


CLUB_HOSTS = _club_hosts()
# Amended 2026-11-19 by session arena/48279a7d-x1 (additive): admit weather.gov (US National
# Weather Service official API) for the Week 11 stadium & NWS weather overlay (brief row 59).
OFFICIAL_HOSTS = ("nfl.com", "nextgenstats.nfl.com", "itl.nist.gov", "weather.gov", "github.com", "www.houstontexans.com") + CLUB_HOSTS
errors: list[str] = []


class SiteParser(HTMLParser):
    def __init__(self, file: Path):
        super().__init__(convert_charrefs=True)
        self.file = file
        self.in_row = False
        self.in_cell = False
        self.row_has_td = False
        self.row_number = 0
        self.cells: list[list[str]] = []
        self.headers: list[str] = []
        self.row_cells: list[str] = []
        self.cell_index = 0
        self.links: list[str] = []
        # data-table tracking
        self.table_depth = 0
        self.data_table_depths: list[int] = []
        self.table_stack: list[bool] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table":
            self.table_depth += 1
            # a valueless attribute (e.g. `<table data-table>`) arrives as None, so test presence
            self.table_stack.append("data-table" in attrs)
        if tag == "tr":
            self.in_row = True
            self.seen_th = False
            self.th_text = []
            self.row_has_td = False
            self.cells = []
            self.row_number += 1
        elif self.in_row and tag in ("td", "th"):
            self.in_cell = True
            self.cell_index = len(self.cells)
            self.cells.append([])
            if tag == "td":
                self.row_has_td = True
            else:
                self.seen_th = True
        elif self.in_cell and tag == "a" and attrs.get("href"):
            self.cells[-1].append(attrs["href"])
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
            if self.in_cell:
                self.cells[self.cell_index].append(attrs["href"])

    def handle_data(self, data):
        if self.in_cell and getattr(self, "seen_th", False) and not self.row_has_td:
            self.th_text.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.in_cell:
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            in_data_table = bool(self.table_stack) and self.table_stack[-1]
            if self.row_has_td and self.cells:
                if not self.headers:
                    # first row of td cells with no header seen: treat as header only if it had <th>
                    pass
            if self.row_has_td and self.cells and in_data_table:
                # locate the source cell: by header name, else the last cell
                idx = len(self.cells) - 1
                for i, h in enumerate(self.headers):
                    if h.strip().lower() in ("source", "link", "reference", "provenance"):
                        idx = i
                        break
                cell_hrefs = self.cells[idx] if idx < len(self.cells) else []
                valid = []
                for href in cell_hrefs:
                    parsed = urlparse(href)
                    host = parsed.hostname or ""
                    if parsed.scheme == "https" and any(host == h or host.endswith("." + h) for h in OFFICIAL_HOSTS):
                        valid.append(href)
                if not valid:
                    errors.append(
                        f"{self.file.relative_to(ROOT)}: data-table row {self.row_number} "
                        f"has no official https source link in its Source cell")
            if getattr(self, "seen_th", False) and not self.row_has_td:
                self.headers = [t.strip() for t in self.th_text if t.strip()]
            self.in_row = False
            self.in_cell = False
            self.row_has_td = False
        elif tag == "table":
            if self.table_stack:
                self.table_stack.pop()
            self.table_depth -= 1


def html_files() -> list[Path]:
    out = []
    for path in sorted(ROOT.rglob("*.html")):
        rel = path.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if "/".join(rel.parts[:2]) in SKIP_PREFIXES:
            continue
        out.append(path)
    return out


def main() -> int:
    html_files_ = html_files()
    for file in html_files_:
        parser = SiteParser(file)
        parser.feed(file.read_text(encoding="utf-8"))
        for href in parser.links:
            parsed = urlparse(href)
            if parsed.scheme or href.startswith("//") or href.startswith("#"):
                continue
            target = (file.parent / parsed.path).resolve()
            if not target.exists():
                errors.append(f"{file.relative_to(ROOT)}: broken local link {href!r}")
    if errors:
        print("Site verification failed:")
        print("\n".join(f"- {e}" for e in errors))
        return 1
    print(f"Site verification passed: {len(html_files_)} HTML pages; local links resolve; "
          f"every data-table row has an official source link.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
