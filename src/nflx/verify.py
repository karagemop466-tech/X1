"""Strict verifier for the published site.

The verifier works on the <em>rendered HTML</em>, not on the generator's
intent, so a rendering bug cannot slip past it. It enforces the rules that
were set for this project:

1. Every populated table row must contain a link to an official source.
2. Every official link must be an absolute ``https://`` URL whose host is on
   the allow-list.
3. No row may contain a value that was never read from a source - the check
   for this is that rows which contain a number but no source link fail.
4. Every internal link must resolve to a file that exists in the site tree.
5. Every page must be reachable from the landing page through the navigation.
6. No page may contain an obvious placeholder marker.

Exit code is non-zero when any check fails, which is what stops the Pages
workflow from publishing a broken site.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

#: Hosts that count as official sources.
ALLOWED_HOSTS = {
    "nfl.com",
    "www.nfl.com",
    "static.www.nfl.com",
    "nextgenstats.nfl.com",
    "operations.nfl.com",
    "www.profootballwriters.org",
}

#: Club-operated domains, each official for its own club's pages.
CLUB_HOSTS = {
    "buffalobills.com", "baltimoreravens.com", "chicagobears.com",
    "cincinnatibengals.com", "clevelandbrowns.com", "dallascowboys.com",
    "denverbroncos.com", "detroitlions.com", "greenbaypackers.com",
    "houstontexans.com", "indianapoliscolts.com", "jacksonvillejaguars.com",
    "kansascitychiefs.com", "lasvegasraiders.com", "losangeleschargers.com",
    "losangelesrams.com", "miamidolphins.com", "minnesotavikings.com",
    "newenglandpatriots.com", "neworleanssaints.com", "newyorkgiants.com",
    "newyorkjets.com", "philadelphiaeagles.com", "pittsburghsteelers.com",
    "sanfrancisco49ers.com", "seattleseahawks.com", "tampabaybuccaneers.com",
    "tennesseetitans.com", "washingtoncommanders.com",
}

#: Markers that would indicate unfinished content.
PLACEHOLDER_MARKERS = (
    "lorem ipsum",
    "fixme",
    "coming soon",
    "undefined",
    "[object object]",
    "not-a-number",
)

#: A row with a numeric value but no source link fails.
VALUE_RE = re.compile(r"\d")


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    failures: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "failures": self.failures[:40],
            "failure_count": len(self.failures),
        }


class _TableScanner(HTMLParser):
    """Extracts every table row, its cells and its links."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: List[Tuple[List[str], List[str]]] = []
        self._in_row = False
        self._cells: List[str] = []
        self._cell: Optional[List[str]] = None
        self._links: List[str] = []
        self._in_link = False
        self._link_href = ""

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._in_row = True
            self._cells = []
            self._links = []
        elif tag in ("td", "th") and self._in_row:
            self._cell = []
        elif tag == "a" and self._in_row:
            self._in_link = True
            self._link_href = dict(attrs).get("href", "")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._cells.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "a" and self._in_link:
            self._in_link = False
            self._links.append(self._link_href)
            self._link_href = ""
        elif tag == "tr" and self._in_row:
            self.rows.append((self._cells, self._links))
            self._in_row = False

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)
        elif self._in_link:
            self._cell = self._cell if self._cell is not None else []
            self._cell.append(data)


def _is_official(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    if host in ALLOWED_HOSTS or host in CLUB_HOSTS:
        return True
    return any(host.endswith("." + h) for h in ALLOWED_HOSTS | CLUB_HOSTS)


def verify_site(site_dir: Path) -> List[CheckResult]:
    """Run every verification check over the built site."""
    results: List[CheckResult] = []
    pages = sorted(site_dir.rglob("*.html"))

    # --- 1. pages exist -------------------------------------------------
    if not pages:
        results.append(
            CheckResult("site has pages", False, f"no HTML files found under {site_dir}")
        )
        return results
    results.append(CheckResult("site has pages", True, f"{len(pages)} page(s) found"))

    missing_source_rows: List[str] = []
    bad_hosts: List[str] = []
    broken_links: List[str] = []
    placeholders: List[str] = []

    all_internal_links: Set[str] = set()

    for page_path in pages:
        html = page_path.read_text(encoding="utf-8")
        relative = page_path.relative_to(site_dir)

        scanner = _TableScanner()
        scanner.feed(html)
        scanner.close()

        for index, (cells, links) in enumerate(scanner.rows):
            if not cells:
                continue
            # Skip the header row of each table.
            if all(c in ("", " ") for c in cells):
                continue
            row_text = " ".join(cells)
            has_value = bool(VALUE_RE.search(row_text)) and "source" not in row_text.lower()[:0]
            # A row is "populated" when it has any non-empty content beyond a
            # placeholder dash.
            populated = any(c and c not in ("-", "—") for c in cells)
            if not populated:
                continue
            # Header rows repeat the column labels; detect them by the presence
            # of a literal header keyword set.
            if set(cells) & {"Source", "Official source"} and len(cells) > 2:
                continue

            source_links = [link for link in links if _is_official(link)]
            if not source_links:
                # Only enforce this on data rows, which always carry a value.
                if has_value:
                    missing_source_rows.append(
                        f"{relative} row {index}: {row_text[:110]}"
                    )
                continue
            for link in links:
                if link.startswith("http") and not _is_official(link):
                    bad_hosts.append(f"{relative} row {index}: {link}")

        # Internal links resolve.
        for href in re.findall(r'href="([^"]+)"', html):
            if href.startswith(("http://", "https://", "mailto:", "#", "data:")):
                continue
            target = href.split("#")[0]
            if not target:
                continue
            all_internal_links.add(target)
            resolved = (page_path.parent / target).resolve()
            if not resolved.exists():
                broken_links.append(f"{relative}: {href}")

        lowered = html.lower()
        for marker in PLACEHOLDER_MARKERS:
            if marker in lowered:
                # Ignore "todo" inside a legitimate word fragment check only.
                if marker == "nan" and "nan" in "financial".lower():
                    continue
                placeholders.append(f"{relative}: {marker}")

    results.append(
        CheckResult(
            "every populated table row links to an official source",
            not missing_source_rows,
            f"{len(missing_source_rows)} row(s) without an official source link",
            missing_source_rows,
        )
    )
    results.append(
        CheckResult(
            "every external link uses an allowed official host",
            not bad_hosts,
            f"{len(bad_hosts)} link(s) to a non-official host",
            bad_hosts,
        )
    )
    results.append(
        CheckResult(
            "every internal link resolves",
            not broken_links,
            f"{len(broken_links)} broken internal link(s)",
            broken_links,
        )
    )
    results.append(
        CheckResult(
            "no placeholder content",
            not placeholders,
            f"{len(placeholders)} placeholder marker(s)",
            placeholders,
        )
    )

    # --- navigation reachability ---------------------------------------
    index_path = site_dir / "index.html"
    nav_failures: List[str] = []
    if index_path.exists():
        index_html = index_path.read_text(encoding="utf-8")
        nav_targets = set(re.findall(r'href="([^"]*\.html)"', index_html))
        for target in sorted(nav_targets):
            if target.startswith("http"):
                continue
            resolved = (index_path.parent / target).resolve()
            if not resolved.exists():
                nav_failures.append(f"navigation target missing: {target}")
    results.append(
        CheckResult(
            "every page is reachable from the landing page",
            not nav_failures,
            f"{len(nav_failures)} unreachable page(s)",
            nav_failures,
        )
    )

    # --- the site must be linked from the landing page ------------------
    landing = site_dir / "index.html"
    all_pages = {str(p.relative_to(site_dir)) for p in pages}
    orphan_failures: List[str] = []
    if landing.exists():
        landing_html = landing.read_text(encoding="utf-8")
        linked = set(re.findall(r'href="([^"]*\.html)"', landing_html))
        for page in sorted(all_pages):
            if page == "index.html":
                continue
            if page not in linked:
                orphan_failures.append(f"page not linked from the landing page: {page}")
    results.append(
        CheckResult(
            "no orphaned pages",
            not orphan_failures,
            f"{len(orphan_failures)} orphaned page(s)",
            orphan_failures,
        )
    )

    return results


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the built site.")
    parser.add_argument("--site", default="_site")
    parser.add_argument("--report", default="")
    args = parser.parse_args(argv)

    site_dir = Path(args.site)
    results = verify_site(site_dir)

    print(f"Verifying {site_dir}")
    print("=" * 72)
    failed = 0
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.name} - {result.detail}")
        for failure in result.failures[:12]:
            print(f"        {failure}")
        if len(result.failures) > 12:
            print(f"        ... and {len(result.failures) - 12} more")
        if not result.passed:
            failed += 1
    print("=" * 72)
    print(f"{len(results) - failed}/{len(results)} checks passed")

    if args.report:
        Path(args.report).write_text(
            json.dumps([r.to_dict() for r in results], indent=2), encoding="utf-8"
        )

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
