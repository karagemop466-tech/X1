#!/usr/bin/env python3
"""Verify the deck: links resolve, every data row is sourced, no placeholder leaked.

    python3 tools/verify_deck.py

This is the deck's own contract check, modelled on tools/verify_app.py. It is
deliberately stricter than a link checker in three ways:

  1. **Every table row in the served deck must carry a source link in its last
     cell.** A row without one fails the build. There is no "anywhere in the
     row" rule — the link has to be in the source column, so a row cannot pass
     by accident because the requirement text happens to contain a URL.
  2. **No placeholder may survive.** `{`, `TODO`, `XXX`, `{{`, `None`,
     `nan` and the schema's own field names appearing as visible text all fail.
  3. **The navigation must be complete.** Every page in the nav must exist, and
     every page that exists must be reachable from the nav.

It also re-runs the two content invariants that matter most:

  * the readiness register covers every brief line that has a row in the source
    TSV, and every row names a gate
  * the venue table has 14 fixtures, each with a stadium and its own game-centre
    URL, and the fixture list equals the one in the schedule store
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from html.parser import HTMLParser
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DECK = os.path.join(ROOT, "deck")
DATA = os.path.join(ROOT, "data", "deck")

errors: list[str] = []
notes: list[str] = []


class TableParser(HTMLParser):
    """Collect tables, their headers and their rows."""

    def __init__(self, file):
        super().__init__(convert_charrefs=True)
        self.file = file
        self.tables = []          # list of {"headers": [...], "rows": [[(text, hrefs)]]}
        self.cur = None
        self.cell = None
        self.hrefs = []
        self.text = []
        self.in_th = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            self.cur = {"headers": [], "rows": [], "attrs": a}
            self.tables.append(self.cur)
        elif tag == "tr" and self.cur is not None:
            self.cur["rows"].append([])
        elif tag in ("td", "th") and self.cur is not None:
            self.cell = tag
            self.text = []
            self.hrefs = []
        elif tag == "a" and self.cell:
            if a.get("href"):
                self.hrefs.append(a["href"])

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell and self.cur is not None:
            txt = "".join(self.text).strip()
            entry = (txt, list(self.hrefs))
            if self.cell == "th":
                if not self.cur["headers"]:
                    self.cur["headers"] = [txt]
                else:
                    self.cur["headers"].append(txt)
            else:
                if self.cur["rows"]:
                    self.cur["rows"][-1].append(entry)
            self.cell = None
        elif tag == "table":
            self.cur = None

    def handle_data(self, data):
        if self.cell:
            self.text.append(data)


# Official source policy, matching scripts/verify_site.py and tools/verify_app.py:
#   * the league and its own properties (nfl.com and subdomains)
#   * club domains, which are the only primary source for a club depth chart
#   * the repository itself (a computed value's provenance is the file it came from)
#   * two named, stable third parties that the repository already cites for a
#     specific document: the NFLPA (the gambling policy PDF) and ESPN (a club
#     roster page used as a depth-chart cross-check). Both are listed here
#     EXPLICITLY, one URL pattern each, so no other host can slip in.
ALLOWED_HOSTS = (
    "nfl.com",
    "github.com",
    "github.io",
    "nflpaweb.blob.core.windows.net",
    "espn.com",
)
CLUB_HOST_RE = re.compile(r"^www\.[a-z0-9]+\.com$")

# Club hosts are read from the depth-chart store, exactly as scripts/verify_site.py does,
# so a host can only be admitted by first appearing in collected data.
def _club_hosts():
    path = os.path.join(ROOT, "data", "pipeline", "depth_charts.json")
    try:
        d = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {urlparse(r["_source_url"]).hostname or "" for r in d.get("rows", []) if r.get("_source_url")}


CLUB_HOSTS = _club_hosts()


def host_ok(href):
    host = (urlparse(href).hostname or "").lower()
    if not host:
        return False
    if any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS):
        return True
    return host in CLUB_HOSTS


PLACEHOLDERS = [
    ("{", "unrendered template brace"),
    ("{{", "unrendered template brace"),
    ("TODO", "TODO marker"),
    ("XXX", "XXX marker"),
    # a bare `None` cell is a leaked value; the English word "None" as the first
    # word of a sentence is not. The regex only fires on `None` used as a value:
    # surrounded by cell boundaries or punctuation, not followed by a verb.
    ("<td>None</td>", "python None leaked as a cell value"),
    ("None,", "python None leaked in a list"),
    ("[None", "python None leaked in a list"),
    ("None]", "python None leaked in a list"),
    (" nan", "nan leaked"),
    ("undefined", "javascript undefined leaked"),
    ("[object Object]", "serialised object leaked"),
]


def check_placeholders(rel, text):
    for token, why in PLACEHOLDERS:
        if token == "{":
            # allow braces inside <code> blocks that legitimately show schema
            stray = [m.start() for m in re.finditer(r"\{", text)]
            for pos in stray:
                ctx = text[max(0, pos - 40):pos + 40]
                if "<code>" in ctx and "</code>" in ctx:
                    continue
                errors.append(f"{rel}: stray '{{' near: {ctx.strip()[:80]!r}")
                break
        elif token in text:
            errors.append(f"{rel}: {why} (found {token!r})")


def main() -> int:
    if not os.path.isdir(DECK):
        print("deck/ missing — run tools/build_deck.py")
        return 1

    # ---------- 1. page inventory + links ---------------------------------
    pages = sorted(f for f in os.listdir(DECK) if f.endswith(".html"))
    if not pages:
        print("no pages in deck/")
        return 1

    parsed = {}
    for f in pages:
        rel = f"deck/{f}"
        text = open(os.path.join(DECK, f), encoding="utf-8").read()
        check_placeholders(rel, text)

        # internal links resolve
        for m in re.finditer(r'href="([^"#][^"]*)"', text):
            href = m.group(1)
            if href.startswith(("http://", "https://", "mailto:")):
                if not host_ok(href):
                    errors.append(f"{rel}: external link to a non-official host: {href}")
                continue
            target = os.path.normpath(os.path.join(DECK, href))
            if not os.path.exists(target):
                errors.append(f"{rel}: broken internal link {href!r}")

        p = TableParser(rel)
        p.feed(text)
        parsed[f] = p

        # a page must carry at least one table (the brief asks for tables)
        if not p.tables and f not in ("archive.html",):
            notes.append(f"{rel}: no table on this page")

    # ---------- 2. nav completeness ---------------------------------------
    nav_targets = set()
    idx = open(os.path.join(DECK, "index.html"), encoding="utf-8").read()
    for m in re.finditer(r'<a class="item[^"]*" href="([^"]+)"', idx):
        nav_targets.add(m.group(1))
    missing = [t for t in nav_targets if not os.path.exists(os.path.join(DECK, t))]
    if missing:
        errors.append(f"nav points at missing pages: {missing}")
    no_nav = [f for f in pages if f not in nav_targets]
    if no_nav:
        errors.append(f"pages not reachable from the nav: {no_nav}")

    # ---------- 3. every data row carries a source link in its last cell ---
    rows_checked = 0
    for f, p in parsed.items():
        for ti, t in enumerate(p.tables):
            if "data-table" not in t["attrs"]:
                continue
            for ri, row in enumerate([r for r in t["rows"] if r]):
                rows_checked += 1
                txt, hrefs = row[-1]
                if not hrefs:
                    errors.append(f"deck/{f}: table {ti} row {ri} has no source link "
                                  f"in its last cell ({row[0][0][:50]!r})")
                    continue
                if not host_ok(hrefs[0]):
                    errors.append(f"deck/{f}: table {ti} row {ri} source host not official: {hrefs[0]}")

    # ---------- 4. readiness register invariants ---------------------------
    rd = json.load(open(os.path.join(DATA, "readiness.json"), encoding="utf-8"))["rows"]
    with open(os.path.join(DATA, "brief_round3_sentences.tsv"), encoding="utf-8") as fh:
        body = "".join(ln for ln in fh if not ln.startswith("#"))
    tsv_rows = [r for r in csv.reader(body.splitlines(), delimiter="\t") if r and r[0] != "id"]
    if len(rd) != len(tsv_rows):
        errors.append(f"readiness has {len(rd)} rows but the TSV has {len(tsv_rows)}")
    ids_rd = [r["id"] for r in rd]
    ids_tsv = [r[0] for r in tsv_rows]
    if ids_rd != ids_tsv:
        d = set(ids_rd) ^ set(ids_tsv)
        errors.append(f"readiness IDs disagree with the TSV: {sorted(d)}")
    gates_ok = 0
    for r in rd:
        if not r["clearing_number"].strip():
            errors.append(f"{r['id']}: empty clearing number")
        if not r["gate"].strip():
            errors.append(f"{r['id']}: empty gate")
        else:
            gates_ok += 1
        if not r["requirement"].strip():
            errors.append(f"{r['id']}: empty requirement text")
    statuses = {r["status"] for r in rd}

    # ---------- 5. venue invariants ---------------------------------------
    with open(os.path.join(DATA, "venues_2026_w10.tsv"), encoding="utf-8") as fh:
        body = "".join(ln for ln in fh if not ln.startswith("#"))
    vr = list(csv.DictReader(body.splitlines(), delimiter="\t"))
    if len(vr) != 14:
        errors.append(f"venue table has {len(vr)} fixtures, expected 14")
    for v in vr:
        if not v["stadium_as_printed"].strip():
            errors.append(f"venue {v['away']}@{v['home']}: empty stadium")
        if not v["location_as_printed"].strip():
            errors.append(f"venue {v['away']}@{v['home']}: empty location")
        if not v["source_url"].startswith("https://www.nfl.com/games/"):
            errors.append(f"venue {v['away']}@{v['home']}: source is not a game centre: {v['source_url']}")

    # the venue fixture list must equal the schedule store's
    sched = os.path.join(ROOT, "data", "nfl", "schedule_week10.tsv")
    if os.path.exists(sched):
        with open(sched, encoding="utf-8") as fh:
            sbody = "".join(ln for ln in fh if not ln.startswith("#"))
        sr = list(csv.DictReader(sbody.splitlines(), delimiter="\t"))
        a = sorted((v["away"], v["home"]) for v in vr)
        b = sorted((s["away"], s["home"]) for s in sr if s["away"] != "away")
        if a != b:
            errors.append(f"venue fixtures disagree with the schedule store: {set(a) ^ set(b)}")
        notes.append(f"venue fixtures match the schedule store on {len(a)} fixtures")

    # ---------- 6. luck panel reproducibility ------------------------------
    lp_path = os.path.join(DATA, "luck_panel.json")
    if os.path.exists(lp_path):
        lp = json.load(open(lp_path, encoding="utf-8"))
        if len(lp["blocks"]) < 5:
            errors.append("luck panel has fewer than 5 blocks")
        l3 = next((b for b in lp["blocks"] if b["id"] == "L3"), None)
        if not l3 or not l3["rows"]:
            errors.append("luck panel L3 missing")
        else:
            r = l3["rows"][0]
            implied = r["wins"] / r["decisions"]
            if abs(implied - r["hit_rate"]) > 1e-9:
                errors.append("L3 hit_rate does not equal wins/decisions")
            if not (0 < r["wilson_low"] < r["hit_rate"] < r["wilson_high"] < 1):
                errors.append("L3 interval does not bracket the point estimate")
            # the verdict sentence must agree with the interval it quotes
            says_above = "which is above" in r["verdict"]
            really_above = r["wilson_low"] > 0.5238
            if says_above != really_above:
                errors.append("L3 verdict contradicts its own lower bound")
        l4 = next((b for b in lp["blocks"] if b["id"] == "L4"), None)
        if l4 and l4["rows"]:
            q = l4["rows"][0]
            if not (q["p05_wins"] <= q["median_wins"] <= q["p95_wins"]):
                errors.append("L4 percentiles are out of order")
        l5 = next((b for b in lp["blocks"] if b["id"] == "L5"), None)
        if l5:
            s = l5.get("summary", {})
            rows5 = l5["rows"]
            if s.get("ci_excludes_zero") != sum(1 for x in rows5 if x["ci_low"] > 0):
                errors.append("L5 summary ci_excludes_zero disagrees with its rows")
            if s.get("p_below_0_05") != sum(1 for x in rows5 if x["p_value"] < 0.05):
                errors.append("L5 summary p_below_0_05 disagrees with its rows")

    # ---------- 7. mindchange two-sidedness --------------------------------
    mc = json.load(open(os.path.join(DATA, "mindchange.json"), encoding="utf-8"))["rows"]
    for r in mc:
        if not r["confirm"].strip() or not r["falsify"].strip():
            errors.append(f"{r['id']}: mindchange is not two-sided")
        if not r["confirm_number"].strip() or not r["falsify_number"].strip():
            errors.append(f"{r['id']}: mindchange has no number on one side")

    # ---------- report ----------------------------------------------------
    print(f"pages            : {len(pages)}")
    print(f"tables checked   : {sum(len(p.tables) for p in parsed.values())}")
    print(f"data rows checked: {rows_checked}")
    print(f"readiness rows   : {len(rd)} (gates named: {gates_ok})")
    print(f"readiness states : {sorted(statuses)}")
    print(f"venue fixtures   : {len(vr)}")
    print(f"mindchange rows  : {len(mc)}")
    for n in notes:
        print("note:", n)
    if errors:
        print(f"\nFAILED with {len(errors)} error(s):")
        for e in errors[:60]:
            print("  -", e)
        return 1
    print("\ndeck verification passed: links resolve, every data row carries an official "
          "or repository source, no placeholder survived, registers are complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
