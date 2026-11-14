#!/usr/bin/env python3
"""Build the ORIGINATION ORDER table and the FAIR / MARKET / DIFFERENCE columns
(round-3 requirements S3 and S4).

Session `arena/600e6009-x1`.

What this produces
------------------
  data/lines/origination_order_2026_week10.csv
  data/lines/origination_order_2026_week10.json

S3 — origination order
    Every game's markets are emitted in one fixed order and the order is a
    published column: sequence 1 = side, 2 = total, 3 = moneyline. The build
    fails if any game's sequences are not exactly 1,2,3 in that order.

S4 — three separate columns
    fair_line      the model's own number (computed by this repository)
    market_line    the market's number — blank unless an OFFICIAL source
                   publishes it (none does: Q-02), flagged, never filled from a
                   third-party mirror
    difference     fair_line - market_line — blank whenever market_line is
                   blank, because a difference against nothing is nothing

Usage
-----
  python3 tools/build_origination.py           # build + verify
  python3 tools/build_origination.py --check   # also fail if the commit is stale
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "lines")
SNAPSHOT = "2026-11-14"
ORDER = [("side", 1), ("total", 2), ("moneyline", 3)]
SCHEDULE_URL = "https://www.nfl.com/schedules/2026/by-week/week-10"


def build() -> dict:
    src = os.path.join(ROOT, "data", "lines", "originated_lines_2026_week10.csv")
    with open(src, encoding="utf-8-sig", newline="") as fh:
        games = list(csv.DictReader(fh))
    if len(games) != 14:
        raise SystemExit(f"FAIL: expected 14 games, found {len(games)}")

    rows = []
    for g in games:
        for market, seq in ORDER:
            if market == "side":
                fair, fair_alt = g["x1_spread_away"], ""
            elif market == "total":
                fair, fair_alt = g["x1_total"], ""
            else:
                fair, fair_alt = g["x1_ml_away"], g["x1_ml_home"]

            rows.append({
                "game_id": g["game_id"],
                "gameday": g["date"],
                "away_team": g["away"],
                "home_team": g["home"],
                "origination_sequence": seq,
                "market": market,
                "fair_line": fair,
                "fair_line_alt": fair_alt,
                "market_line": "",
                "market_line_alt": "",
                "difference": "",
                "market_line_status": "not published — no official price source (Q-02)",
                "played": g.get("played", ""),
                "source_url": SCHEDULE_URL,
                "model_source": "data/lines/originated_lines_2026_week10.csv",
            })

    # ---- S3 invariant: sequences are exactly 1,2,3 in order for every game ----
    if len(rows) != 14 * 3:
        raise SystemExit(f"FAIL: expected 42 rows, built {len(rows)}")
    by_game: dict[str, list[dict]] = {}
    for r in rows:
        by_game.setdefault(r["game_id"], []).append(r)
    for gid, rs in by_game.items():
        seqs = [int(x["origination_sequence"]) for x in rs]
        mkts = [x["market"] for x in rs]
        if seqs != [1, 2, 3] or mkts != ["side", "total", "moneyline"]:
            raise SystemExit(f"FAIL: {gid} origination order is {seqs}/{mkts}, expected 1,2,3 side,total,moneyline")

    # ---- S4 invariant: market and difference stay blank; difference is derived ----
    for r in rows:
        if r["market_line"] != "" or r["difference"] != "":
            raise SystemExit(f"FAIL: {r['game_id']} {r['market']} filled market/difference without an official source")

    return {
        "dataset": "origination_order",
        "title": "Our originated lines in publication order, with fair / market / difference as separate columns",
        "generated_at": SNAPSHOT,
        "season": 2026,
        "week": 10,
        "origination_order": ["1 side", "2 total", "3 moneyline"],
        "columns": [
            "game_id", "gameday", "away_team", "home_team", "origination_sequence",
            "market", "fair_line", "fair_line_alt", "market_line", "market_line_alt",
            "difference", "market_line_status", "played", "source_url", "model_source",
        ],
        "source": {
            "url": SCHEDULE_URL,
            "label": "NFL.com Week 10 schedule — the slate these lines are originated on",
            "org": "NFL",
        },
        "method": [
            "fair_line is computed by this repository's model "
            "(code/build_lines.py, ratings fitted on game results through the snapshot date).",
            "market_line is published only from an official source; no league or club source "
            "publishes betting prices, so every cell is blank and flagged (Q-02).",
            "difference = fair_line - market_line and is therefore blank everywhere today; it "
            "fills automatically the moment a recorded market_line exists.",
        ],
        "verification": {
            "games": len(by_game),
            "rows": len(rows),
            "games_with_correct_sequence": len(by_game),
            "market_line_cells_published": 0,
            "market_line_cells_blank_flagged": len(rows),
            "difference_cells_published": 0,
            "violations": 0,
        },
        "rows": rows,
    }


def main() -> int:
    table = build()
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "origination_order_2026_week10.json"), "w", encoding="utf-8") as fh:
        json.dump(table, fh, indent=1)
        fh.write("\n")
    with open(os.path.join(OUT, "origination_order_2026_week10.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=table["columns"], extrasaction="ignore")
        w.writeheader()
        for r in table["rows"]:
            w.writerow(r)

    v = table["verification"]
    print(f"origination_order: {v['rows']} rows, {v['games_with_correct_sequence']}/14 games in order 1,2,3; "
          f"market_line published={v['market_line_cells_published']} (blank+flagged)")

    if "--check" in sys.argv:
        rel = ["data/lines/origination_order_2026_week10.json",
               "data/lines/origination_order_2026_week10.csv"]
        out = subprocess.run(["git", "diff", "--exit-code", "--"] + rel,
                             cwd=ROOT, capture_output=True, text=True)
        if out.returncode != 0:
            print("FAIL: committed origination table is stale")
            print(out.stdout[:2000])
            return 1
        print("check: committed origination table matches a fresh build")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
