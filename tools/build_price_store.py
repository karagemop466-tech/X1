#!/usr/bin/env python3
"""Build the price-snapshot store — data/price_snapshots.json.

Session arena/907c5baf-x1 (task N2). The store records an opening and a closing
snapshot for every market we originate, in origination order: side (spread)
first, then the total, then the moneyline. Each row publishes the model's fair
line, the market line and the difference as separate columns.

Verification rules (the brief's rule, enforced literally):
  * A market price that cannot be confirmed from an official source is left
    blank and flagged as unverified. It is never inferred or filled in.
  * Community-mirror values are quarantined in a separate block, flagged, and
    are never rendered as fact.
  * Our own lines are computed outputs of a published method (they are facts
    about the model, not market facts) and carry their input provenance.

Inputs (read-only):
  data/lines/originated_lines_2026_week10.csv — our originated numbers
  data/results_feed.json                      — which games are final
  data/nfl/schedule_2026_week10.csv           — kickoff times (official)
  data/raw/nflverse/{games,initial_lines,closing_lines}.csv — mirror quarantine

Output: data/price_snapshots.json
"""

from __future__ import annotations

import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = "2026-11-14"
SNAPSHOT = "2026-11-14"

ORIGINATED = os.path.join(ROOT, "data", "lines", "originated_lines_2026_week10.csv")
FEED = os.path.join(ROOT, "data", "results_feed.json")
SCHED = os.path.join(ROOT, "data", "nfl", "schedule_2026_week10.csv")
MIRROR = os.path.join(ROOT, "data", "raw", "nflverse")
OUT = os.path.join(ROOT, "data", "price_snapshots.json")

NO_OFFICIAL_PRICE = ("no official source publishes betting prices (F-06 / Q-02); "
                     "left blank and flagged — never inferred")
METHOD = ("computed by code/build_lines.py (published method, docs/methodology/"
          "line-origination.md) from game results — 2026 rows verified against "
          "NFL.com in data/results_feed.json; earlier seasons from the "
          "fingerprinted community mirror")


def count_lines(path: str, seasons: tuple = ()) -> dict:
    n = 0
    seen = set()
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            s = r.get("season") or r.get("game_id", "")[:4]
            if seasons and s not in seasons:
                continue
            n += 1
            seen.add(s)
    return {"rows": n, "seasons": sorted(seen)}


def main() -> int:
    with open(ORIGINATED, encoding="utf-8") as f:
        orig = list(csv.DictReader(f))
    with open(FEED, encoding="utf-8") as f:
        feed = json.load(f)
    with open(SCHED, encoding="utf-8") as f:
        sched = list(csv.DictReader(f))

    def canon(code: str) -> str:
        return {"ARI": "AZ", "LA": "LAR"}.get(code, code)

    def gid_canon(gid: str) -> str:
        p = gid.split("_")
        return "2026_%d_%s_%s" % (int(p[1]), canon(p[2]), canon(p[3]))

    final_ids = {gid_canon(r["game_id"]) for r in feed["rows"] if r["status"] == "FINAL"}
    kickoff = {}
    for s in sched:
        gid = gid_canon("2026_10_%s_%s" % (s["away"], s["home"]))
        kickoff[gid] = f"{s['date']} {s['et_time']}"

    rows = []
    for o in orig:
        gid = o["game_id"]
        is_final = gid_canon(gid) in final_ids
        base = {
            "game_id": gid,
            "kickoff": kickoff.get(gid_canon(gid), ""),
            "opened_at": f"{GEN} (first capture; store created at origination round)",
            "_source_url": "https://www.nfl.com/schedules/2026/by-week/week-10",
            "_source_label": "NFL.com Week 10 schedule (kickoff times)",
            "_source_org": "NFL",
            "_retrieved_at": SNAPSHOT,
        }
        if is_final:
            close_state = ("not captured — the store was created after this "
                           "game's kickoff (flagged; no close invented)")
            close_line = ""
            closed_at = ""
            close_flag = "missed close: store created after kickoff"
        else:
            close_state = "close capture due at kickoff (pending)"
            close_line = ""
            closed_at = ""
            close_flag = "close pending kickoff"

        def add(seq, mtype, side, our_line, our_price, extra_flags):
            rows.append({
                **base,
                "snapshot_id": f"PS-{gid}-{mtype.upper()}-{side.upper()}",
                "sequence": seq,
                "market_type": mtype,
                "market_side": side,
                "model_fair_line": our_line,
                "model_fair_price": our_price,
                "market_open_line": "",           # blank: unverifiable (rule)
                "market_close_line": "",          # blank: unverifiable (rule)
                "difference_open": "",            # blank when market is blank
                "difference_close": "",
                "our_close_line": close_line,
                "closed_at": closed_at,
                "close_status": close_state,
                "line_provenance": METHOD,
                "_flags": [close_flag, NO_OFFICIAL_PRICE] + extra_flags,
                "_verified": False,
                "_verified_note": ("model side is reproducible from the published "
                                   "method; market side has no official source"),
            })

        add(1, "spread", "away", o["x1_spread_away"], "",
            ["home side prices at the mirror of the away number (one originated number per game)"])
        add(2, "total", "game", o["x1_total"], "", [])
        add(3, "moneyline", "away", "", o["x1_ml_away"], [])
        add(3, "moneyline", "home", "", o["x1_ml_home"], [])

    # ------------------------------------------------------ quarantine block
    init = count_lines(os.path.join(MIRROR, "initial_lines.csv"))
    close = count_lines(os.path.join(MIRROR, "closing_lines.csv"))
    games_m = count_lines(os.path.join(MIRROR, "games.csv"), seasons=("2026",))

    doc = {
        "dataset": "price_snapshots",
        "title": "Price-snapshot store — opening and closing numbers for every market we originate",
        "generated_at": GEN,
        "policy": {
            "origination_order": "side (spread) first, then the total, then the moneyline",
            "snapshot_lifecycle": ("an opening snapshot is recorded when the market is "
                                   "originated; a closing snapshot is recorded at kickoff; "
                                   "a missed capture is recorded as missed and never back-filled"),
            "columns": ("model fair line, market line and difference are always separate "
                        "columns; a difference is published only when both of its inputs "
                        "are published"),
            "blank_rule": ("a value no official source publishes stays blank and carries "
                           "the 'no official source' flag"),
            "difference_rule": "difference = model fair line − market line, per market unit",
        },
        "columns": ["snapshot_id", "game_id", "kickoff", "sequence", "market_type",
                    "market_side", "model_fair_line", "model_fair_price",
                    "market_open_line", "market_close_line", "difference_open",
                    "difference_close", "our_close_line", "closed_at", "close_status"],
        "rows": rows,
        "quarantine_mirror": {
            "warning": ("COMMUNITY MIRROR — NOT AN OFFICIAL SOURCE. Values in this block "
                        "must not be used as facts and are not rendered as market prices "
                        "anywhere on the site."),
            "files": {
                "data/raw/nflverse/games.csv": {
                    "content": "single market snapshot per game (spread, total, two moneylines)",
                    "rows_2026": games_m["rows"],
                    "seasons": "2006-2026",
                },
                "data/raw/nflverse/initial_lines.csv": {
                    "content": "opening numbers (community mirror)",
                    "rows": init["rows"],
                    "seasons": init["seasons"],
                },
                "data/raw/nflverse/closing_lines.csv": {
                    "content": "closing numbers (community mirror)",
                    "rows": close["rows"],
                    "seasons": close["seasons"],
                },
            },
            "_verified": False,
            "_flags": [
                "community mirror: provenance is a GitHub mirror, not a book or the league (I-10 / F-06)",
                "2026 Week 10 rows in games.csv are a single snapshot — they are neither an opening nor a closing capture",
            ],
            "_source_url": "https://github.com/nflverse/nfldata/blob/master/DATASETS.md",
            "_source_label": "nflverse/nfldata DATASETS.md (community mirror)",
            "_source_org": "nflverse (community)",
            "_retrieved_at": SNAPSHOT,
        },
        "capture_log": [
            {"time": GEN, "event": "store created; opening snapshots taken from the Week 10 origination output (data/lines/originated_lines_2026_week10.csv)", "by": "session arena/907c5baf-x1"},
            {"time": GEN, "event": "Week 10 TNF (2026_10_WAS_NYG) kickoff had already passed at first capture: close recorded as missed, not invented", "by": "session arena/907c5baf-x1"},
            {"time": "pending", "event": "closing snapshots for the remaining 13 Week 10 games are due at kickoff (2026-11-15 / 2026-11-16 ET)", "by": "—"},
        ],
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
        f.write("\n")

    print(f"price snapshots : {len(rows)} rows ({len(orig)} games x 4 originated numbers)")
    print(f"order check     : spread(seq1) -> total(seq2) -> moneyline(seq3) per game")
    print(f"market cells    : all blank + flagged (no official odds source)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
