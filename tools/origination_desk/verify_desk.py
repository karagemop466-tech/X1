#!/usr/bin/env python3
"""Comprehensive verifier for `data/origination_desk/**` and `origination-desk/*.html`.

Asserts:
  1. All four deterministic builders pass `--check` (no stale CSV, JSON, or HTML).
  2. Every CSV row has an official `https://` source URL (`nfl.com`, `operations.nfl.com`,
     `api.weather.gov`, or official NFL club domain).
  3. Zero-inference blanks are preserved: all 172 W10 inactive rows have `snap_count == ""`,
     all 13 W11 venue rows have `official_90min_roof_status == ""` and `official_playing_surface == ""`,
     `vikings-at-49ers` has empty NWS cells, and all 52 prospective PR-04 rows have empty market/vig cells.
  4. Zero retrospective backtests are qualified for Stage 1 or Stage 2 on the leaderboard.
  5. Every `origination-desk/*.html` page uses only CSS classes defined in `assets/site.css`,
     resolves all local links, carries `2026-11-14` and `Flagged for review`, and places an
     official `https://` source link in the last `<td>` of every `<table data-table>` row.
"""
from __future__ import annotations

import csv
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
DESK_HTML_DIR = ROOT / "origination-desk"
DATA_DIR = ROOT / "data" / "origination_desk"

CLUB_HOSTS = {
    urlparse(r["_source_url"]).hostname or ""
    for r in json.loads((ROOT / "data" / "pipeline" / "depth_charts.json").read_text(encoding="utf-8")).get("rows", [])
    if r.get("_source_url")
} | {"www.houstontexans.com"}

OFFICIAL_SUFFIXES = ("nfl.com", "weather.gov", "itl.nist.gov", "github.com")


def _is_official_https(url: str) -> bool:
    p = urlparse(url)
    host = p.hostname or ""
    if p.scheme != "https" or not host:
        return False
    if host in CLUB_HOSTS:
        return True
    return any(host == s or host.endswith("." + s) for s in OFFICIAL_SUFFIXES)


class _TableSourceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.table_stack: list[bool] = []
        self.in_tr = False
        self.in_td = False
        self.row_has_td = False
        self.cells: list[list[str]] = []
        self.links: list[str] = []
        self.data_rows = 0
        self.unsourced_rows: list[int] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = dict(attrs)
        if tag == "table":
            self.table_stack.append("data-table" in ad)
        elif tag == "tr":
            self.in_tr = True
            self.row_has_td = False
            self.cells = []
        elif self.in_tr and tag in ("td", "th"):
            self.in_td = True
            if tag == "td":
                self.row_has_td = True
            self.cells.append([])
        elif tag == "a" and ad.get("href"):
            href = ad["href"]
            self.links.append(href)
            if self.in_td and self.cells:
                self.cells[-1].append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th"):
            self.in_td = False
        elif tag == "tr" and self.in_tr:
            if self.row_has_td and self.cells and self.table_stack and self.table_stack[-1]:
                self.data_rows += 1
                last_hrefs = self.cells[-1]
                if not any(_is_official_https(h) for h in last_hrefs):
                    self.unsourced_rows.append(self.data_rows)
            self.in_tr = False
        elif tag == "table" and self.table_stack:
            self.table_stack.pop()


def verify_all() -> tuple[int, list[str]]:
    checks = 0
    errors: list[str] = []

    def require(cond: bool, msg: str) -> None:
        nonlocal checks
        checks += 1
        if not cond:
            errors.append(msg)

    # 1. Run --check on all 4 deterministic builders
    for script in (
        "tools/origination_desk/build_roster_audit.py",
        "tools/origination_desk/build_weather_overlay.py",
        "tools/origination_desk/build_skill_desk.py",
        "tools/origination_desk/build_site.py",
    ):
        res = subprocess.run([sys.executable, str(ROOT / script), "--check"], cwd=ROOT, capture_output=True, text=True)
        require(res.returncode == 0, f"{script} --check failed: {res.stdout.strip()} {res.stderr.strip()}")

    def _load_csv(rel: Path) -> list[dict[str, str]]:
        with (DATA_DIR / rel).open(encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    # 2. Zero-inference & provenance checks on CSVs
    inactives = _load_csv(Path("roster/official_inactives_2026_week10.csv"))
    require(len(inactives) == 172, f"expected 172 W10 inactive rows, found {len(inactives)}")
    for i, r in enumerate(inactives, 1):
        require(r["snap_count"] == "", f"inactives row {i}: snap_count must be blank")
        require(_is_official_https(r["source_url"]), f"inactives row {i}: non-official source_url")
        require(_is_official_https(r["game_center_url"]), f"inactives row {i}: non-official game_center_url")

    weather = _load_csv(Path("weather/week11_stadium_nws_overlay.csv"))
    require(len(weather) == 13, f"expected 13 W11 weather rows, found {len(weather)}")
    for r in weather:
        require(r["official_90min_roof_status"] == "", f"{r['slug']}: pre-90min roof must be blank")
        require(r["official_playing_surface"] == "", f"{r['slug']}: Game Center surface must be blank")
        require(_is_official_https(r["game_center_url"]), f"{r['slug']}: invalid game_center_url")
        if r["slug"] == "vikings-at-49ers":
            require(r["nws_temp_f"] == "" and r["nws_precip_pct"] == "" and r["nws_source_url"] == "",
                    "vikings-at-49ers Mexico City row must leave NWS fields blank")
        else:
            require(_is_official_https(r["nws_source_url"]), f"{r['slug']}: invalid nws_source_url")

    vf_rows = _load_csv(Path("skill/vig_free_decomposition.csv"))
    require(len(vf_rows) == 66, f"expected 66 vig-free rows, found {len(vf_rows)}")
    for r in vf_rows:
        require(_is_official_https(r["source_url"]), f"{r['game_id']}: invalid source_url")
        if r["track"] == "PROSPECTIVE_ESCROW_PR04":
            require(r["raw_market_quote_home"] == "" and r["vig_free_mult_home"] == "" and r["vig_free_alpha_home_pct"] == "",
                    f"{r['game_id']} {r['market']}: prospective Q-02 market/vig cells must be blank")

    lb_json = json.loads((DATA_DIR / "skill" / "skill_desk_summary.json").read_text(encoding="utf-8"))
    sc = lb_json["two_stage_leaderboard"]["stage_counts"]
    require(sc["stage1_qualified"] == 0 and sc["stage2_qualified_live"] == 0,
            "zero strategies may be marked Stage-1 or Stage-2 qualified")

    corr_rows = _load_csv(Path("skill/official_correlations_with_n.csv"))
    require(len(corr_rows) == 9, "expected 9 official correlation rows")
    for r in corr_rows:
        require(int(r["n"]) in (32, 150), f"{r['corr_id']}: unexpected sample size n={r['n']}")
        require(_is_official_https(r["source_url"]), f"{r['corr_id']}: invalid source_url")

    diff_rows = _load_csv(Path("skill/weekly_what_changed_w9_w10_w11.csv"))
    require(len(diff_rows) == 32, f"expected 32 clubs in weekly diff, found {len(diff_rows)}")

    # 3. HTML / CSS / Link / Per-Row Source checks on origination-desk/*.html
    defined_css = set(re.findall(r"\.([a-zA-Z][a-zA-Z0-9_-]*)", (ROOT / "assets" / "site.css").read_text(encoding="utf-8")))
    html_pages = sorted(DESK_HTML_DIR.glob("*.html"))
    require(len(html_pages) == 8, f"expected 8 HTML pages in origination-desk/, found {len(html_pages)}")

    total_html_rows = 0
    for hp in html_pages:
        txt = hp.read_text(encoding="utf-8")
        no_script = re.sub(r"<script\b.*?</script\s*>", " ", txt, flags=re.S | re.I)
        require("assets/site.css" in txt, f"{hp.name}: missing assets/site.css")
        require("2026-11-14" in txt, f"{hp.name}: missing 2026-11-14 baseline date")
        require("2026-11-19" in txt, f"{hp.name}: missing 2026-11-19 verification date")
        require("Flagged for review" in txt, f"{hp.name}: missing 'Flagged for review' nav label")
        require(not re.findall(r"&lt;(b|span|a|code|i|br|em|table|tr|td)&gt;", txt),
                f"{hp.name}: escaped HTML tag leaked as text")

        used_cls: set[str] = set()
        for m in re.finditer(r'class="([^"]*)"', no_script):
            used_cls |= {c for c in m.group(1).split() if c}
        missing_cls = sorted(used_cls - defined_css)
        require(not missing_cls, f"{hp.name}: undefined CSS classes {missing_cls}")

        parser = _TableSourceParser()
        parser.feed(no_script)
        total_html_rows += parser.data_rows
        require(parser.data_rows > 0, f"{hp.name}: expected at least 1 data-table row")
        require(not parser.unsourced_rows, f"{hp.name}: unsourced data-table rows {parser.unsourced_rows}")

        for href in parser.links:
            if href.startswith(("#", "mailto:")):
                continue
            if href.startswith(("http://", "https://")):
                require(_is_official_https(href), f"{hp.name}: unapproved external link {href}")
            else:
                tgt = (hp.parent / href.split("#")[0]).resolve()
                require(tgt.exists(), f"{hp.name}: broken local link {href}")

    require(total_html_rows >= 350, f"expected >= 350 sourced HTML rows across desk, found {total_html_rows}")
    return checks, errors


def main() -> int:
    checks, errors = verify_all()
    if errors:
        print(f"FAIL verify_desk ({len(errors)} errors across {checks} checks):")
        for e in errors:
            print("  -", e)
        return 1
    print(f"OK verify_desk: all {checks} checks passed across data/origination_desk/ and origination-desk/*.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
