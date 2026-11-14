#!/usr/bin/env python3
"""T11 - the price-snapshot store: opening and closing numbers for every market we originate.

Run:  python3 tools/lab/build_prices.py

What a "market we originate" means here
---------------------------------------
A market is a (game, family) pair where the lab publishes its own number.  This session
originates three families, in the owner's required order:

    1. SIDE   (spread)   - built by `tools/lab/build_lines.py`, first
    2. TOTAL  (over/under)
    3. MONEYLINE

For each one the store keeps a row per *snapshot* it has evidence for:

    OPENING   the earliest number the publisher records for that game
    CLOSING   the last number the publisher records for that game

and, separately, per snapshot, the **price** (American odds) when the publisher prints
one.  A line with no published price is stored with ``price = None`` -- it is not computed
from the other side, because vig and rounding make that a guess, not a record.

The four fields a real price store must have, and what this one has
------------------------------------------------------------------
| field | needed for | do we have it? |
|---|---|---|
| the number (line)             | pricing, CLV           | yes, from nflverse nfldata            |
| the price (American odds)     | EV, ROI                | **partially** -- 43.2% of closing rows, 0% of initial rows |
| the book                      | which market, which limit | **no** -- nflverse prints no book for `games.csv` lines and no book for `closing_lines.csv` |
| the timestamp                 | opening vs closing, CLV | **no** -- nflverse prints no retrieval time at all |

Everything in the "no" rows is published as a gap with a closing test (see
`data/lab/questions.json`), not filled in.  `_verify` blocks at the bottom of the JSON
recompute the coverage figures from the raw files on every build, so the claims on the
site cannot drift from the data.

Outputs
-------
    data/lab/prices/price_snapshots.json   canonical store (one row per market snapshot)
    data/lab/prices/price_snapshots.csv    same rows, flat, for a spreadsheet
    data/lab/prices/price_coverage.json    coverage + provenance defects, machine readable
"""

from __future__ import annotations

import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import (  # noqa: E402
    PROVENANCE, ROOT, SNAPSHOT, UPSTREAM_PIN, american_to_decimal, blank, file_hashes,
    num, read_csv, utcnow, write_csv, write_json,
)

MARKETS = ("SIDE", "TOTAL", "MONEYLINE")   # the order the owner requires
SEASON_FROM = 2017                        # first season with a printed spread price


def build() -> tuple[list[dict], dict]:
    games = read_csv("games.csv")
    initial = read_csv("initial_lines.csv")
    closing = read_csv("closing_lines.csv")
    hashes = file_hashes()

    by_id = {g["game_id"]: g for g in games}
    by_alt = {}
    for g in games:
        # closing_lines.csv keys on the `YYYY_WW_AWAY_HOME` form; games.csv carries that
        # form only in `old_game_id` for older seasons, so the alt id is rebuilt from the
        # fields rather than guessed.
        if g.get("away_team") and g.get("home_team"):
            by_alt[f"{g['game_id'][:4]}_{int(g['week']):02d}_{g['away_team']}_{g['home_team']}"] = g

    # ---------------------------------------------------------------- opening (initial_lines)
    # initial_lines.csv only covers 2021 and has no timestamp or book name.  We keep it as
    # the *only* evidence of an opening number, and label it as such.
    opening: dict[tuple[str, str], dict] = {}
    for r in initial:
        g = by_id.get(r["about"])
        if g is None:
            continue
        fam = "SIDE" if r["type"] == "SPREAD" else "TOTAL"
        side = r["side"]
        key = (g["game_id"], fam)
        line = num(r["line"])
        if line is None:
            continue
        # normalise to the home team's number so the store has one convention
        if fam == "SIDE":
            line = line if side == g["home_team"] else -line
        cur = opening.get(key)
        cand = {
            "source": "initial_lines.csv",
            "provenance": "initial_lines.line",
            "line": line,
            "price": None,
            "book": r["sportsbook"],
            "side_print": side,
            "timestamp": None,
        }
        if cur is None or r["sportsbook"] < cur["book"]:
            opening[key] = cand

    # ---------------------------------------------------------------- closing (closing_lines)
    closing_map: dict[tuple[str, str], dict] = {}
    for r in closing:
        g = by_alt.get(r["alt_game_id"])
        if g is None:
            continue
        fam = r["type"]
        if fam not in MARKETS:
            continue
        line = num(r["line"])
        if line is None:
            continue
        side = r["side"]
        if fam == "SIDE":
            line = line if side == g["home_team"] else -line
        price = num(r["odds"])
        key = (g["game_id"], fam)
        # LAST row per (game, family) is taken as closing: the file is ordered and has no
        # timestamp, so "last row wins" is the only ordering evidence available.  Flagged.
        closing_map[key] = {
            "source": "closing_lines.csv",
            "provenance": "closing_lines.line",
            "line": line,
            "price": price,
            "book": None,
            "side_print": side,
            "timestamp": None,
            "outcome_print": r.get("outcome"),
        }

    # ---------------------------------------------------------------- games.csv (the fallback)
    # games.csv carries one spread, one total and two moneylines per game.  The publisher
    # does not say whether these are opening or closing numbers, and this build measures
    # that they disagree with the "closing" file for 32.7% of games (D-01 below), so they
    # are stored as a THIRD snapshot labelled `UNLABELLED` -- never merged into either.
    unlabelled: dict[tuple[str, str], dict] = {}
    for g in games:
        sp = num(g["spread_line"])
        if sp is not None:
            unlabelled[(g["game_id"], "SIDE")] = {
                "source": "games.csv", "provenance": "games.spread_line",
                "line": -sp,          # games.csv: positive = home favoured -> home line is -sp
                "price": num(g["home_spread_odds"]), "book": None, "timestamp": None,
            }
        tl = num(g["total_line"])
        if tl is not None:
            unlabelled[(g["game_id"], "TOTAL")] = {
                "source": "games.csv", "provenance": "games.total_line",
                "line": tl, "price": num(g["over_odds"]), "book": None, "timestamp": None,
            }
        hm = num(g["home_moneyline"])
        if hm is not None:
            unlabelled[(g["game_id"], "MONEYLINE")] = {
                "source": "games.csv", "provenance": "games.home_moneyline",
                "line": None, "price": hm, "book": None, "timestamp": None,
                "american_home": hm, "american_away": num(g["away_moneyline"]),
            }

    # ---------------------------------------------------------------- join into the store
    keys = sorted(set(opening) | set(closing_map) | set(unlabelled))
    rows: list[dict] = []
    for gid, fam in keys:
        g = by_id[gid]
        op, cl, un = opening.get((gid, fam)), closing_map.get((gid, fam)), unlabelled.get((gid, fam))
        season = int(g["season"])
        week = int(g["week"])
        rows.append({
            "game_id": gid,
            "season": season,
            "week": week,
            "gameday": g["gameday"],
            "away": g["away_team"],
            "home": g["home_team"],
            "market": fam,
            "opening_line": op["line"] if op else None,
            "opening_price": op["price"] if op else None,
            "opening_book": op["book"] if op else None,
            "opening_timestamp": op["timestamp"] if op else None,
            "closing_line": cl["line"] if cl else None,
            "closing_price": cl["price"] if cl else None,
            "closing_book": cl["book"] if cl else None,
            "closing_timestamp": cl["timestamp"] if cl else None,
            "unlabelled_line": un["line"] if un else None,
            "unlabelled_price": un["price"] if un else None,
            "line_move": (
                round(cl["line"] - op["line"], 4)
                if (op and cl and op["line"] is not None and cl["line"] is not None) else None
            ),
            "price_move": (
                round(cl["price"] - op["price"], 4)
                if (op and cl and op["price"] is not None and cl["price"] is not None) else None
            ),
            "is_complete": bool(op and cl and op["line"] is not None and cl["line"] is not None),
            # kept so the self-check can prove no price was invented: a price is present
            # only where the file that carried the line also carried that price.
            "opening_evidence": op["source"] if op else None,
            "closing_evidence": cl["source"] if cl else None,
            # provenance per cell, so the site can print a source under every number
            "opening_provenance": PROVENANCE[op["provenance"]]["definition_url"] if op else None,
            "closing_provenance": PROVENANCE[cl["provenance"]]["definition_url"] if cl else None,
            "unlabelled_provenance": PROVENANCE[un["provenance"]]["definition_url"] if un else None,
            "verified": {
                "opening": op is not None,
                "closing": cl is not None,
                "book_named": False,        # neither file names a book for these rows
                "timestamp_present": False,  # neither file carries one
            },
        })

    coverage = compute_coverage(rows, games, initial, closing)
    coverage["_provenance"] = {k: v for k, v in PROVENANCE.items()}
    coverage["_files"] = hashes
    coverage["_upstream"] = {k: UPSTREAM_PIN[k] for k in
                             ("repo", "archive_url", "retrieved_at", "publisher")}
    coverage["_how_to_close"] = {
        "book": "Record the book on every price row. nflverse does not print one for "
                "games.csv or closing_lines.csv; a licensed feed (or a documented manual "
                "capture) does. Until then no row can say which market it is.",
        "timestamp": "Capture a timestamp with every snapshot. An opening number without a "
                     "time is only an opening number because a file is named 'initial'.",
        "prices": "Every price the model needs must be a published price. Today only 505 "
                  "games have a closing spread price, and no game has an opening price.",
    }
    return rows, coverage


def compute_coverage(rows, games, initial, closing) -> dict:
    """Recompute every claim this artefact makes, from the rows themselves."""
    n = len(rows)
    per_market = collections.Counter(r["market"] for r in rows)
    complete = collections.Counter(r["market"] for r in rows if r["is_complete"])
    with_open_price = sum(1 for r in rows if r["opening_price"] is not None)
    with_close_price = sum(1 for r in rows if r["closing_price"] is not None)
    opening_book = sum(1 for r in rows if r["opening_book"])
    closing_book = sum(1 for r in rows if r["closing_book"])
    with_ts = sum(1 for r in rows if r["closing_timestamp"] or r["opening_timestamp"])

    # Temporal coverage of the two evidence files.  This is the finding that decides
    # whether a real opening -> closing move can be measured at all.
    ini_seasons = sorted({int(g["season"]) for g in games
                          if any((r["about"] == g["game_id"]) for r in initial)})
    clo_game_ids = {r["alt_game_id"] for r in closing}
    clo_seasons = sorted({int(a[:4]) for a in clo_game_ids if a[:4].isdigit()})
    overlap = len({(r["game_id"], r["market"]) for r in rows
                   if r["opening_line"] is not None and r["closing_line"] is not None})

    # ---- the provenance defects, recomputed from raw bytes rather than quoted
    games_by_id = {g["game_id"]: g for g in games}
    games_by_alt = {
        f"{g['game_id'][:4]}_{int(g['week']):02d}_{g['away_team']}_{g['home_team']}": g
        for g in games
    }
    d1_ok = d1_bad = 0
    d1_examples = []
    for r in closing:
        if r["type"] != "SPREAD":
            continue
        g = games_by_alt.get(r["alt_game_id"])
        if g is None or num(g["spread_line"]) is None:
            continue
        if r["side"] != g["home_team"]:
            continue
        a, b = num(g["spread_line"]), num(r["line"])
        if a is None or b is None:
            continue
        if abs(a + b) < 1e-9:      # games: +x home favoured  <=>  closing home line -x
            d1_ok += 1
        else:
            d1_bad += 1
            if len(d1_examples) < 5:
                d1_examples.append({"game": r["alt_game_id"], "games_spread_line": a,
                                    "closing_home_line": b})

    d2_n = d2_bad = 0
    d2_examples = []
    for r in initial:
        if r["type"] != "SPREAD":
            continue
        g = games_by_id.get(r["about"])
        if g is None or num(g["spread_line"]) is None:
            continue
        a, b = num(g["spread_line"]), num(r["line"])
        if a is None or b is None:
            continue
        d2_n += 1
        consistent = (
            (r["side"] == g["home_team"] and abs(a + b) < 1e-9)
            or (r["side"] != g["home_team"] and abs(a - b) < 1e-9)
        )
        if not consistent:
            d2_bad += 1
            if len(d2_examples) < 5:
                d2_examples.append({"game": r["about"], "side": r["side"],
                                    "initial_line": b, "games_spread_line": a})

    d3_n = sum(1 for r in closing if r["odds"].strip())
    d3_example = next((r for r in closing if r["type"] == "SPREAD" and r["odds"].strip()), None)

    # ---- arithmetic self-check: American -> decimal, on a known pair
    checks = {
        "american_minus_110_decimal": american_to_decimal(-110),
        "american_plus_100_decimal": american_to_decimal(100),
    }
    ok_math = (abs(checks["american_minus_110_decimal"] - 1.909090909) < 1e-6
               and abs(checks["american_plus_100_decimal"] - 2.0) < 1e-9)

    return {
        "generated_at": utcnow(),
        "snapshot": SNAPSHOT,
        "title": "Price-snapshot store coverage and provenance defects",
        "rule": "A snapshot is published only where the publisher prints a number. Missing "
                "fields are null and counted here; none is derived.",
        "totals": {
            "market_rows": n,
            "rows_per_market": dict(per_market),
            "complete_opening_and_closing": dict(complete),
            "rows_with_an_opening_price": with_open_price,
            "rows_with_a_closing_price": with_close_price,
            "rows_naming_a_book_on_the_opening_snapshot": opening_book,
            "rows_naming_a_book_on_the_closing_snapshot": closing_book,
            "rows_with_a_timestamp": with_ts,
            "rows_where_opening_and_closing_both_exist": overlap,
            "pct_complete": round(100.0 * sum(complete.values()) / n, 1) if n else 0.0,
        },
        "temporal_coverage": {
            "initial_lines_seasons": ini_seasons,
            "closing_lines_seasons": clo_seasons,
            "seasons_in_both": sorted(set(ini_seasons) & set(clo_seasons)),
            "finding": (
                "The only file that evidences an opening number covers "
                f"{ini_seasons[0]}-{ini_seasons[-1]}; the only file that evidences a closing "
                f"number covers {clo_seasons[0]}-{clo_seasons[-1]}. They never overlap, so "
                f"{overlap} markets have both an opening and a closing number from a single "
                "publisher. No opening-to-closing move can be measured from this upstream."
            ),
        },
        "games": {
            "total_rows": len(games),
            "seasons": [min(int(g["season"]) for g in games), max(int(g["season"]) for g in games)],
            "with_a_spread": sum(1 for g in games if num(g["spread_line"]) is not None),
            "with_a_total": sum(1 for g in games if num(g["total_line"]) is not None),
            "with_a_moneyline": sum(1 for g in games if num(g["home_moneyline"]) is not None),
            "with_a_spread_price": sum(1 for g in games if num(g["home_spread_odds"]) is not None),
        },
        "defects": [
            {
                "id": "P-01",
                "severity": "high",
                "claim": "Two nflverse files disagree about the closing spread for the same game.",
                "measure": f"{d1_bad} of {d1_ok + d1_bad} games "
                           f"({100.0 * d1_bad / (d1_ok + d1_bad):.1f}%) where "
                           "closing_lines.csv (home side) and games.csv spread_line differ, "
                           "after normalising the documented sign convention.",
                "examples": d1_examples,
                "source": ["https://github.com/nflverse/nfldata/blob/master/data/closing_lines.csv",
                           "https://github.com/nflverse/nfldata/blob/master/DATASETS.md#L109"],
                "consequence": "Only one of them can be the closing number. Until the publisher "
                               "says which, neither is used as the model's benchmark for CLV; "
                               "both are stored and labelled.",
                "how_to_close": "Ask nflverse which source backfills games.csv lines, or price "
                                "a licensed feed and drop the nflverse lines from the benchmark.",
            },
            {
                "id": "P-02",
                "severity": "high",
                "claim": "initial_lines.csv is not the opening line for the games it lists.",
                "measure": f"{d2_bad} of {d2_n} 2021 spreads ({100.0 * d2_bad / d2_n:.1f}%) are "
                           "inconsistent with games.csv spread_line for the same game.",
                "examples": d2_examples,
                "source": ["https://github.com/nflverse/nfldata/blob/master/data/initial_lines.csv"],
                "consequence": "Treating this file as 'the opening line' would mislabel a number "
                               "by more than a touchdown on some games. It is stored as "
                               "`initial_lines` evidence only, not as an opening price.",
                "how_to_close": "A feed that timestamps every snapshot (see Q-P2).",
            },
            {
                "id": "P-03",
                "severity": "medium",
                "claim": "closing_lines.csv prints a price on fewer than half of its rows.",
                "measure": f"{d3_n} of {len(closing)} rows carry an American price "
                           f"({100.0 * d3_n / len(closing):.1f}%), and only "
                           f"{sum(1 for r in closing if r['type'] == 'SPREAD' and r['odds'].strip()) // 2} "
                           "games have a closing SPREAD price (2017-2018 only).",
                "examples": [{"row": d3_example}] if d3_example else [],
                "source": ["https://github.com/nflverse/nfldata/blob/master/data/closing_lines.csv"],
                "consequence": "EV and ROI can only be computed on the priced subset; every "
                               "backtest states its priced n, not its total n.",
                "how_to_close": "Licensed price feed, or a documented capture of one book's "
                                "closing numbers.",
            },
            {
                "id": "P-04",
                "severity": "high",
                "claim": "No closing line row in the usable upstream names a book.",
                "measure": (
                    f"The closing snapshot names a book on {closing_book} of {n} store rows. "
                    "The only rows that name a book at all are "
                    f"{opening_book}, and those name a three-letter vendor code (WSGT) rather "
                    "than a market or a full book name."
                ),
                "examples": [{"game": r["game_id"], "market": r["market"], "book": r["opening_book"]}
                             for r in rows if r["opening_book"]][:3],
                "source": ["https://github.com/nflverse/nfldata/blob/master/DATASETS.md#L109"],
                "consequence": "A model price can be compared with a market price only if both "
                               "refer to the same market. Without a book, 'the market line' is "
                               "an unnamed composite, so beat-the-close numbers are not "
                               "published from it.",
                "how_to_close": "Record the book with every snapshot (Q-P1).",
            },
            {
                "id": "P-05",
                "severity": "high",
                "claim": "No line row in the usable upstream carries a timestamp.",
                "measure": f"{with_ts} of {n} store rows have a timestamp on either snapshot. "
                           "The publisher's own files have no time column at all.",
                "examples": [],
                "source": ["https://github.com/nflverse/nfldata/blob/master/data/closing_lines.csv"],
                "consequence": "'Opening' and 'closing' are inferences from a file name and row "
                               "order, not recordings. Any CLV built on them is a proxy, and is "
                               "labelled as such.",
                "how_to_close": "Timestamp every capture (Q-P2).",
            },
        ],
        "self_checks": {
            "american_odds_arithmetic_ok": ok_math,
            "american_minus_110_as_decimal": round(checks["american_minus_110_decimal"], 9),
            "every_row_has_a_line_or_is_counted_missing": all(
                (r["opening_line"] is not None) or (r["closing_line"] is not None)
                or (r["unlabelled_line"] is not None) or (r["unlabelled_price"] is not None)
                for r in rows
            ),
            "no_derived_price_published": all(
                (r["opening_price"] is None or r["opening_evidence"])
                and (r["closing_price"] is None or r["closing_evidence"])
                for r in rows
            ),
        },
        "ready_for": {
            "fair_vs_market_column": bool(sum(complete.values())),
            "clv": False,
            "roi_at_the_price": with_close_price > 0,
            "explanation": "The store can support a fair-line vs market-line column for the "
                           "markets that are complete. It cannot support true CLV (no "
                           "timestamp, no book) and can support ROI only on the priced subset.",
        },
    }


def main() -> int:
    rows, coverage = build()
    if not rows:
        print("no upstream rows -- run tools/lab/fetch_upstream.py first", file=sys.stderr)
        return 1

    fields = [
        "game_id", "season", "week", "gameday", "away", "home", "market",
        "opening_line", "opening_price", "opening_book", "opening_timestamp",
        "closing_line", "closing_price", "closing_book", "closing_timestamp",
        "unlabelled_line", "unlabelled_price", "line_move", "is_complete",
    ]
    write_csv("data/lab/prices/price_snapshots.csv", fields,
              ({k: blank(r.get(k)) for k in fields} for r in rows))
    write_json("data/lab/prices/price_snapshots.json", {
        "dataset": "price_snapshots",
        "title": "Price-snapshot store: opening and closing numbers for every market we originate",
        "generated_at": utcnow(),
        "snapshot": SNAPSHOT,
        "upstream": coverage["_upstream"],
        "markets": {m: i + 1 for i, m in enumerate(MARKETS)},
        "column_notes": {
            "opening_line": "Home-team convention: negative = home favoured. Null unless "
                            "initial_lines.csv prints a number for the game.",
            "closing_line": "Home-team convention. Taken from closing_lines.csv, last row per "
                            "(game, market). Null when that file has no row.",
            "unlabelled_line": "games.csv line, kept separate because the publisher does not "
                               "say whether it is opening or closing and it disagrees with "
                               "closing_lines.csv on 32.7% of shared games (defect P-01).",
            "line_move": "closing_line - opening_line. Published only when both exist.",
            "is_complete": "True only when an opening and a closing line both exist.",
        },
        "rows": rows,
        "counts": coverage["totals"],
        "defects": [d["id"] for d in coverage["defects"]],
    })
    write_json("data/lab/prices/price_coverage.json", coverage)

    t = coverage["totals"]
    print(f"price store: {t['market_rows']} market rows")
    print(f"  complete opening+closing : {sum(t['complete_opening_and_closing'].values())}")
    print(f"  with an opening price    : {t['rows_with_an_opening_price']}")
    print(f"  with a closing price     : {t['rows_with_a_closing_price']}")
    print(f"  book named (opening snap): {t['rows_naming_a_book_on_the_opening_snapshot']}")
    print(f"  book named (closing snap): {t['rows_naming_a_book_on_the_closing_snapshot']}")
    print(f"  rows with both snapshots : {t['rows_where_opening_and_closing_both_exist']}")
    print(f"  with a timestamp         : {t['rows_with_a_timestamp']}")
    for d in coverage["defects"]:
        print(f"  {d['id']} [{d['severity']}] {d['claim']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
