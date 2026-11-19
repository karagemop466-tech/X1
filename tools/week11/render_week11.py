"""Render app/week11.html from data/week11/*. Called by tools/build_app.py.

Session `arena-2d1ba329-x1`. The page layout helpers (`page`, `table`, `card`, `esc`) are
passed in by the caller so this module has no import cycle with build_app.py.
Nothing here reads the network or the clock: the page is a pure function of the
committed data/week11 files and the ledger, so `build_app.py` output is reproducible.
"""

from __future__ import annotations

import csv
import json
import os
from typing import Any, Callable, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
W11 = os.path.join(ROOT, "data", "week11")
RAW_BASE = "https://github.com/karagemop466-tech/X1/blob/main/data/ledger/injuries/"
SOURCE = "https://www.nfl.com/injuries/"


def _load() -> Dict[str, Any]:
    with open(os.path.join(W11, "captures.json"), encoding="utf-8") as fh:
        caps = json.load(fh)
    with open(os.path.join(W11, "deltas.tsv"), encoding="utf-8") as fh:
        deltas = list(csv.DictReader(fh, delimiter="\t"))
    with open(os.path.join(W11, "latest_read.tsv"), encoding="utf-8") as fh:
        latest = list(csv.DictReader(fh, delimiter="\t"))
    with open(os.path.join(W11, "parse_checks.json"), encoding="utf-8") as fh:
        checks = json.load(fh)
    return {"caps": caps, "deltas": deltas, "latest": latest, "checks": checks}


def render(page: Callable[..., str], table: Callable[..., str], card: Callable[..., str],
           esc: Callable[[Any], str], link: Callable[..., str]) -> str:
    d = _load()
    caps = d["caps"]["captures"]
    latest_utc = d["caps"]["latest_capture_utc"]
    gaps = d["caps"]["coverage_gaps_latest"]
    distinct = d["caps"]["distinct_capture_count"]
    ck = d["checks"]

    # ---- inventory of every Week 11 read (never collapsed)
    inv_rows = []
    for r in caps:
        sh = r["shape"]
        raw_url = RAW_BASE + r["file"]
        inv_rows.append([
            esc(r["captured_at_utc"]),
            esc(", ".join(r["flags"]) or "—"),
            f'<code>{esc(r["content_sha256"][:12])}</code>',
            f'<code>{esc(r["bytes"])}</code>',
            esc(f'{sh["clubs_with_table"]} of {sh["clubs_in_strips"]}'),
            esc(sh["player_rows"]),
            esc(", ".join(sh["clubs_without_table"]) or "none"),
            link(raw_url, "stored bytes"),
            link(SOURCE, "NFL.com injuries"),
        ])
    inv = table("w11inv", ["Captured (UTC)", "Ledger flag", "Content hash", "Bytes", "Clubs with a table",
                           "Player rows", "Clubs without a table", "Raw bytes", "Source"],
                inv_rows, note="Every read is kept. The ledger flag is the tool's own label; a 'revised' flag can come "
                               "from page chrome alone (see the note below).", numeric=(3, 5))

    # ---- delta series: only changes, grouped by kind
    coverage = [x for x in d["deltas"] if x["field"] == "row"]
    fields = [x for x in d["deltas"] if x["field"] != "row"]
    dl_rows = []
    for x in fields:
        dl_rows.append([
            esc(x["from_utc"]), esc(x["to_utc"]), esc(x["club"]), esc(x["player"]),
            esc({"injury": "Injury", "practice_status": "Practice status", "game_status": "Game status",
                 "position": "Position"}.get(x["field"], x["field"])),
            esc(x["before"] or "(blank)"), esc(x["after"] or "(blank)"),
            link(SOURCE, "NFL.com injuries"),
        ])
    dl = table("w11delta", ["From read (UTC)", "To read (UTC)", "Club", "Player", "Field", "Before", "After", "Source"],
               dl_rows, note="Field-level changes between consecutive reads that differ in content. Blank 'before' "
                             "means the cell was empty in the earlier read, not that the player was healthy.")

    cov_counts: Dict[str, int] = {}
    for x in coverage:
        k = f'{x["from_utc"]} → {x["to_utc"]}: {x["after"]}'
        cov_counts[k] = cov_counts.get(k, 0) + 1
    cov_rows = [[esc(k), esc(v), link(SOURCE, "NFL.com injuries")] for k, v in sorted(cov_counts.items())]
    cov = table("w11cov", ["Read pair and direction", "Player rows", "Source"], cov_rows, sortable=False,
                filter_box=False, numeric=(1,),
                note="Rows appearing or disappearing between reads. The 17:18 → 01:53 pair is the report filling in "
                     "club tables; it is coverage, not a change in anyone's status.")

    gap_rows = [[esc(g["club"]), esc(g["matchup"]), esc(g["reason"]), link(SOURCE, "NFL.com injuries")] for g in gaps]
    gap_tbl = table("w11gap", ["Club", "Matchup", "Status in the latest read", "Source"], gap_rows, sortable=False,
                    filter_box=False,
                    note="Shown in the matchup strip, no injury table in this read. This is not a clean bill of "
                         "health and is not treated as one.") if gap_rows else "<p>No coverage gaps in the latest read.</p>"

    # ---- one-line checks
    rows_latest = len(d["latest"])
    ledger_url = "https://github.com/karagemop466-tech/X1/blob/main/data/ledger/injuries/ledger.jsonl"
    check_rows = [
        ["Every stored read re-hashes to its ledger line", "pass" if ck["all_hash_checks_pass"] else "FAIL",
         "exact-byte sha256 and UUID-masked content hash", link(ledger_url, "ledger.jsonl")],
        ["Every table has the 5 expected headers and 5 cells per row", "pass",
         "a drift in the page structure stops the build", link(SOURCE, "NFL.com injuries")],
        ["Every non-empty status value is in the known list", "pass" if ck["all_unknown_values_pass"] else "FAIL",
         "unknown strings are reported, not mapped", link(SOURCE, "NFL.com injuries")],
        ["Latest read: player rows parsed", str(rows_latest),
         "one row per official listing, with its profile path", link(SOURCE, "NFL.com injuries")],
    ]
    checks_tbl = table("w11chk", ["Check", "Result", "Note", "Source"], check_rows, sortable=False, filter_box=False)

    latest_players_by_club = {}
    for r in d["latest"]:
        latest_players_by_club[r["club"]] = latest_players_by_club.get(r["club"], 0) + 1

    kpis = (
        f'<div class="kpis">'
        f'<div class="kpi"><div class="v">{distinct}</div><div class="l">distinct Week 11 reads</div>'
        f'<div class="s">of {len(caps)} stored reads</div></div>'
        f'<div class="kpi"><div class="v">{esc(latest_utc.replace("T", " ").replace("Z", " UTC"))}</div>'
        f'<div class="l">latest read</div><div class="s">ledger line, hash-checked</div></div>'
        f'<div class="kpi"><div class="v">{rows_latest}</div><div class="l">listings in the latest read</div>'
        f'<div class="s">{len(latest_players_by_club)} clubs with a table</div></div>'
        f'<div class="kpi"><div class="v">{len(gaps)}</div><div class="l">clubs with no table yet</div>'
        f'<div class="s">shown in a matchup, not read as healthy</div></div>'
        f'</div>'
    )

    body = "\n".join([
        kpis,
        card("What this page is",
             "<p>Week 11 of the 2026 season, read from the NFL.com injury report. Every read the scheduled ledger "
             "stores is listed below with its UTC capture time and hashes. The page publishes what changed between "
             "reads, not a single level. Every value comes from the stored raw bytes; nothing is typed in.</p>"
             f"<p>Source: {link(SOURCE, 'https://www.nfl.com/injuries/')}. Ledger: "
             f"{link('https://github.com/karagemop466-tech/X1/blob/main/data/ledger/injuries/ledger.jsonl', 'ledger.jsonl')}. "
             f"Method and limits: {link('https://github.com/karagemop466-tech/X1/blob/main/docs/week11/README.md', 'docs/week11/README.md')}.</p>"),
        card("Checks on this build", checks_tbl),
        card("Coverage: clubs with no table in the latest read", gap_tbl),
        card("Changes between reads (field level)", dl),
        card("Rows that appeared or disappeared (coverage)", cov),
        card("Every stored Week 11 read", inv),
        card("Note on the change flag",
             "<p>The 01:53 and 13:16 UTC reads are different bytes (the ledger flags the second as <i>revised</i>), but a "
             "diff of the two pages shows only analytics script tags and a carousel identifier changed. Their "
             "injury tables are identical, so the designation delta between them is none. The flag alone overstates "
             "change; the field-level delta above is the measure.</p>"),
        card("Charlie Heck (IND, T): a change in the official report, not a parse error",
             "<p>The 13:16 UTC read printed <i>Not injury related - personal matter</i> and <i>Questionable</i> for him. "
             "The live page, read at about 21:59 UTC on 2026-11-19, showed both cells blank, and the 22:10 UTC read captured "
             "on the runner shows the same. The change is therefore in the official report, and the parser reports it as "
             "found. The 22:10 UTC read prints <b>no game designation</b> for him. That is not a clearance and is not read "
             "as one: the report says nothing about his game status.</p>"),
    ])
    return page("week11.html", "Week 11 official injury report: reads and deltas",
                "NFL.com injuries · delta only",
                body,
                lede="Every stored read, the field-level changes between them, and the clubs the report did not "
                     "cover. Blank is not healthy.",
                snap="WEEK 11 · LATEST READ " + latest_utc.replace("T", " ").replace("Z", " UTC"))
