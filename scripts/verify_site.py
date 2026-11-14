#!/usr/bin/env python3
"""Check local HTML links and require a publisher-owned source link per data-table row."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
import sys

ROOT = Path(__file__).resolve().parents[1]
# NFL / NIST sources support research. GitHub is allowed for repository-state
# rows only (the validator checks the host, not semantic relevance).
OFFICIAL_HOSTS = ("nfl.com", "nextgenstats.nfl.com", "itl.nist.gov", "github.com")
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
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr":
            self.in_row = True
            self.row_has_td = False
            self.cells = []
            self.row_number += 1
        elif self.in_row and tag in ("td", "th"):
            self.in_cell = True
            self.cells.append([])
            if tag == "td":
                self.row_has_td = True
        elif self.in_cell and tag == "a" and attrs.get("href"):
            self.cells[-1].append(attrs["href"])
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.in_cell:
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if self.row_has_td and self.cells:
                hrefs = [href for cell in self.cells for href in cell]
                valid = []
                for href in hrefs:
                    parsed = urlparse(href)
                    host = parsed.hostname or ""
                    if parsed.scheme == "https" and any(host == h or host.endswith("." + h) for h in OFFICIAL_HOSTS):
                        valid.append(href)
                if not valid:
                    errors.append(f"{self.file.relative_to(ROOT)}: table row {self.row_number} has no official https source link")
            self.in_row = False
            self.in_cell = False
            self.row_has_td = False


def main() -> int:
    html_files = sorted(ROOT.glob("*.html"))
    for file in html_files:
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
    print(f"Site verification passed: {len(html_files)} HTML pages; local links resolve; every data-table row has an official source link.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
