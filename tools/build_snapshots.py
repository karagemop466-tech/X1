#!/usr/bin/env python3
"""Build the PRICE-SNAPSHOT STORE (round-3 requirement S1).

Session `arena/600e6009-x1`.

What this produces
------------------
  data/snapshots/price_snapshots.json   one record per (market we originate x stage)
  data/snapshots/price_snapshots.csv    same, flat

Store contract
--------------
For EVERY market the model originates (side, total, moneyline — in that order,
see tools/build_origination.py) the store keeps two stages:

  open   the number as originated, captured before kickoff
  close  the number as published at our cut-off, captured at kickoff

Two numbers are tracked per stage:
  our_line      our own originated number        — computed, always recorded
  market_line   the market's number at that stage — blank unless an OFFICIAL
                source publishes prices (none does today: Q-02), flagged not filled

Capture integrity is part of the record. A stage that was not captured in time
is stored with an explicit status (`pending_kickoff`, `not_captured_before_kickoff`,
`captured_post_final`) instead of being back-filled with the open value. The
repository snapshot clock is 2026-11-14, which is AFTER the Week 10 Thursday
final — that game's captures are post-hoc and the store says so.

Usage
-----
  python3 tools/build_snapshots.py           # build + verify
  python3 tools/build_snapshots.py --check   # also fail if the commit is stale
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "snapshots")
SNAPSHOT = "2026-11-14"
MARKETS = [("side", 1), ("total", 2), ("moneyline", 3)]   # origination order S3


def load_originated() -> list[dict]:
    path = os.path.join(ROOT, "data", "lines", "originated_lines_2026_week10.csv")
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def build() -> dict:
    games = load_originated()
    if len(games) != 14:
        raise SystemExit(f"FAIL: expected 14 originated games, found {len(games)}")

    records = []
    for g in games:
        game_id = g["game_id"]
        played = str(g.get("played", "")).strip().upper() == "Y"
        for market, seq in MARKETS:
            if market == "side":
                our_line = g["x1_spread_away"]
                our_alt = ""
                our_label = f"{g['away']} spread {our_line}"
            elif market == "total":
                our_line = g["x1_total"]
                our_alt = ""
                our_label = f"game total {our_line}"
            else:
                our_line = g["x1_ml_away"]
                our_alt = g["x1_ml_home"]
                our_label = f"{g['away']} {our_line} / {g['home']} {our_alt}"

            common = {
                "game_id": game_id,
                "gameday": g["date"],
                "away_team": g["away"],
                "home_team": g["home"],
                "market": market,
                "origination_sequence": seq,
                "our_line": our_line,
                "our_line_alt": our_alt,
                "our_line_label": our_label,
                "market_line": "",
                "market_line_alt": "",
                "difference": "",
                "market_line_status": (
                    "blocked — no official source publishes betting prices (Q-02)"
                ),
                "source_url": "https://www.nfl.com/schedules/2026/by-week/week-10",
                "model_source": "data/lines/originated_lines_2026_week10.csv",
            }

            # ---- open stage ----
            if played:
                open_rec = {
                    **common,
                    "stage": "open",
                    "captured_at": SNAPSHOT,
                    "status": "captured_post_final",
                    "status_note": (
                        "The repository snapshot clock (2026-11-14) is after this game's "
                        "kickoff (2026-11-12), so this record cannot serve as a true opening "
                        "capture. Recorded as-is, flagged, never back-dated."
                    ),
                }
                close_rec = {
                    **common,
                    "stage": "close",
                    "captured_at": "",
                    "status": "not_captured_before_kickoff",
                    "status_note": (
                        "No close capture exists for this game: the store went live after the "
                        "final. Left blank rather than filled with the open value."
                    ),
                }
            else:
                open_rec = {
                    **common,
                    "stage": "open",
                    "captured_at": SNAPSHOT,
                    "status": "recorded",
                    "status_note": "Captured before kickoff.",
                }
                close_rec = {
                    **common,
                    "stage": "close",
                    "captured_at": "",
                    "status": "pending_kickoff",
                    "status_note": (
                        "Close capture is taken at kickoff by the scheduled pipeline; this "
                        "game had not kicked off at the snapshot clock."
                    ),
                }
            records.append(open_rec)
            records.append(close_rec)

    # invariants
    if len(records) != 14 * 3 * 2:
        raise SystemExit(f"FAIL: expected 84 records, built {len(records)}")
    for r in records:
        if r["market_line"] != "":
            raise SystemExit(f"FAIL: {r['game_id']} market_line must stay blank (Q-02)")
        if r["difference"] != "":
            raise SystemExit(f"FAIL: {r['game_id']} difference must stay blank while market is blank")
        if not str(r["model_source"]).endswith(".csv"):
            raise SystemExit("FAIL: record without a model source")

    from collections import Counter
    status_counts = Counter(r["status"] for r in records)

    return {
        "dataset": "price_snapshots",
        "title": "Price-snapshot store — opening and closing numbers for every market we originate",
        "generated_at": SNAPSHOT,
        "contract": {
            "markets_per_game": ["side", "total", "moneyline"],
            "origination_order": "side first, then total, then moneyline (S3)",
            "stages_per_market": ["open", "close"],
            "our_line": "our own originated number — computed by the repo model, always recorded",
            "market_line": (
                "the market's number at that stage — recorded only from an official source; "
                "blank and flagged today because no league or club source publishes prices (Q-02)"
            ),
            "difference": (
                "fair line minus market line — must stay blank while market_line is blank; "
                "never derived from a third-party number"
            ),
            "capture_rule": (
                "a stage not captured in time keeps its status and an empty value; it is never "
                "back-filled from the other stage"
            ),
        },
        "rows_count": len(records),
        "columns": [
            "game_id", "gameday", "market", "origination_sequence", "stage",
            "captured_at", "status", "our_line", "our_line_alt", "market_line",
            "market_line_alt", "difference", "source_url", "model_source",
        ],
        "source": {
            "url": "https://www.nfl.com/schedules/2026/by-week/week-10",
            "label": "NFL.com Week 10 schedule (the games these markets are originated on)",
            "org": "NFL",
        },
        "status_counts": dict(status_counts),
        "verification": {
            "records": len(records),
            "games": 14,
            "markets_per_game": 3,
            "stages_per_market": 2,
            "market_line_values_published": 0,
            "market_line_blank_and_flagged": len(records),
            "violations": 0,
        },
        "note": (
            "This store is append-ready: tools/build_snapshots.py regenerates it from the "
            "origination file and the capture log. When an official price source is settled "
            "(Q-02), market_line and difference fill from recorded captures only."
        ),
        "rows": records,
    }


def main() -> int:
    store = build()
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "price_snapshots.json"), "w", encoding="utf-8") as fh:
        json.dump(store, fh, indent=1)
        fh.write("\n")

    cols = store["columns"]
    with open(os.path.join(OUT, "price_snapshots.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in store["rows"]:
            w.writerow(r)

    print(
        f"price_snapshots: {store['rows_count']} records, "
        f"statuses={store['status_counts']}, "
        f"market_line published=0 (all blank+flagged)"
    )

    if "--check" in sys.argv:
        rel = ["data/snapshots/price_snapshots.json", "data/snapshots/price_snapshots.csv"]
        out = subprocess.run(["git", "diff", "--exit-code", "--"] + rel,
                             cwd=ROOT, capture_output=True, text=True)
        if out.returncode != 0:
            print("FAIL: committed snapshot store is stale")
            print(out.stdout[:2000])
            return 1
        print("check: committed snapshot store matches a fresh build")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
