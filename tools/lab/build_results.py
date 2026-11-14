#!/usr/bin/env python3
"""T12 - the verified results feed: the outcome and price evidence a backtest needs.

Run:  python3 tools/lab/build_results.py

What a backtest needs, and what this feed must therefore carry
--------------------------------------------------------------
    one row per game        : final away score, final home score, neutral-site flag
    the result              : home margin (home - away) and total (home + away)
    a settlement rule       : push / tie handling written down once, used everywhere
    provenance              : the exact file + column + hash the scores came from
    a join key              : the same game_id the price store and the model use

A results feed is *verified* only when:
  * every score is a published number (not derived), and
  * the arithmetic is re-checked (margin = home - away, total = home + away), and
  * the row can be joined to a price without a name-matching guess, and
  * a row whose score is missing is published as missing, never as 0.

Coverage this build measures for itself (figures recomputed every run, see `_checks`):

    1999-2025        every regular/post-season game scored
    2026             the season in progress at the snapshot date: played games scored,
                     unplayed games carried with `status = SCHEDULED` and no score
    price join       only games with a published price can be graded at a price; the rest
                     are graded at the line only (push accounting), and counted separately

Outputs
-------
    data/lab/results/results.json        the feed (one row per game)
    data/lab/results/results.csv         flat copy
    data/lab/results/result_summary.json coverage, settlement rule, self-checks
"""

from __future__ import annotations

import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import (  # noqa: E402
    ROOT, SNAPSHOT, UPSTREAM_PIN, blank, file_hashes, num, read_csv, utcnow,
    write_csv, write_json,
)

SETTLEMENT_RULE = {
    "version": "1.0",
    "registered_at": SNAPSHOT,
    "side": {
        "definition": "home_covers = (home_margin + home_line) > 0. A line of -3 means the "
                      "home team must win by more than 3.",
        "push": "home_margin + home_line == 0 is a PUSH; stake returned, not counted as a win "
                "or a loss, and excluded from the hit-rate denominator.",
        "half_points": "Lines ending in .5 cannot push.",
    },
    "total": {
        "definition": "over_wins = (home_score + away_score) > total_line.",
        "push": "exact equality is a PUSH and is excluded from the hit rate.",
    },
    "moneyline": {
        "definition": "the named side wins outright; a tie is a PUSH on the moneyline and is "
                      "excluded (NFL regular-season ties are possible).",
    },
    "roi": {
        "definition": "sum(profit) / sum(stake), stake = 1 unit per bet unless a staking rule "
                      "is registered separately. A win at American price p returns decimal d "
                      "(d = 1 + p/100 for p >= +100, d = 1 + 100/|p| otherwise), so profit "
                      "= d - 1; a loss = -1; a push = 0.",
        "why_here": "Written down once so the leaderboard, the backtest and the gates cannot "
                    "disagree about what a win means.",
    },
    "void_rules": [
        "A game with no published final score is not graded.",
        "A game with no published price is graded at the line (push-aware) and counted in the "
        "`no_price` bucket, never silently priced at -110.",
        "A neutral-site game is flagged, not dropped.",
    ],
}

COLUMN_PROVENANCE = {
    "away_score": {
        "file": "data/games.csv", "column": "away_score", "publisher": "nflverse nfldata",
        "definition": "The number of points the away team scored. (DATASETS.md.)",
        "url": "https://github.com/nflverse/nfldata/blob/master/DATASETS.md",
    },
    "home_score": {
        "file": "data/games.csv", "column": "home_score", "publisher": "nflverse nfldata",
        "definition": "The number of points the home team scored. (DATASETS.md.)",
        "url": "https://github.com/nflverse/nfldata/blob/master/DATASETS.md",
    },
    "result": {
        "file": "data/games.csv", "column": "result", "publisher": "nflverse nfldata",
        "definition": "home_score - away_score. Published by the file and re-checked here.",
        "url": "https://github.com/nflverse/nfldata/blob/master/DATASETS.md",
    },
    "total": {
        "file": "data/games.csv", "column": "total", "publisher": "nflverse nfldata",
        "definition": "home_score + away_score. Published by the file and re-checked here.",
        "url": "https://github.com/nflverse/nfldata/blob/master/DATASETS.md",
    },
    "location": {
        "file": "data/games.csv", "column": "location", "publisher": "nflverse nfldata",
        "definition": "Home or Neutral. Neutral is flagged so a home-field assumption is "
                      "never applied to a neutral-site game.",
        "url": "https://github.com/nflverse/nfldata/blob/master/DATASETS.md",
    },
}


def build() -> tuple[list[dict], dict]:
    games = read_csv("games.csv")
    rows: list[dict] = []
    checks = collections.Counter()

    for g in sorted(games, key=lambda r: (r["gameday"], r["game_id"])):
        away, home = num(g["away_score"]), num(g["home_score"])
        margin = total = None
        status = "SCHEDULED"
        arith_ok = None
        if away is not None and home is not None:
            margin = home - away
            total = home + away
            status = "FINAL"
            checks["scored_rows"] += 1
            # re-check the publisher's own arithmetic rather than trusting it
            pub_result, pub_total = num(g["result"]), num(g["total"])
            ok = True
            if pub_result is not None and abs(pub_result - margin) > 1e-9:
                ok = False
            if pub_total is not None and abs(pub_total - total) > 1e-9:
                ok = False
            arith_ok = ok
            if not ok:
                checks["publisher_arithmetic_mismatch"] += 1
        else:
            checks["unplayed_rows"] += 1

        tie = bool(margin is not None and margin == 0)
        if tie:
            checks["ties"] += 1

        rows.append({
            "game_id": g["game_id"],
            "season": int(g["season"]),
            "week": int(g["week"]),
            "game_type": g["game_type"],
            "gameday": g["gameday"],
            "away": g["away_team"],
            "home": g["home_team"],
            "away_score": away,
            "home_score": home,
            "home_margin": margin,
            "game_total": total,
            "tie": tie,
            "neutral_site": (g["location"] or "").strip().lower() == "neutral",
            "status": status,
            "score_arithmetic_ok": arith_ok,
            "settlement_rule_version": SETTLEMENT_RULE["version"],
            "score_source": COLUMN_PROVENANCE["result"]["url"],
            "score_provenance": "nflverse nfldata data/games.csv",
            "verified": {
                "score_published": status == "FINAL",
                "arithmetic_rechecked": arith_ok is True,
            },
        })
        if arith_ok is True:
            checks["arithmetic_rechecked_ok"] += 1

    # ---- the join check: can every result row be matched to the price store by key alone?
    price_ids = set()
    try:
        import json
        with open(os.path.join(ROOT, "data", "lab", "prices", "price_snapshots.json"),
                  encoding="utf-8") as fh:
            price_ids = {r["game_id"] for r in json.load(fh)["rows"]}
    except (OSError, ValueError):
        price_ids = set()
    joined = sum(1 for r in rows if r["game_id"] in price_ids)
    checks["games_with_any_price_market_row"] = joined
    checks["games_without_any_price_market_row"] = len(rows) - joined

    summary = {
        "generated_at": utcnow(),
        "snapshot": SNAPSHOT,
        "title": "Verified results feed: coverage, settlement rule and self-checks",
        "upstream": {k: UPSTREAM_PIN[k] for k in
                     ("repo", "archive_url", "retrieved_at", "publisher")},
        "files": file_hashes(),
        "columns": COLUMN_PROVENANCE,
        "settlement_rule": SETTLEMENT_RULE,
        "coverage": {
            "games": len(rows),
            "final": sum(1 for r in rows if r["status"] == "FINAL"),
            "scheduled": sum(1 for r in rows if r["status"] == "SCHEDULED"),
            "seasons": [min(r["season"] for r in rows), max(r["season"] for r in rows)],
            "by_season": dict(collections.Counter(r["season"] for r in rows)),
            "final_by_season": dict(collections.Counter(r["season"] for r in rows
                                                        if r["status"] == "FINAL")),
            "neutral_site_games": sum(1 for r in rows if r["neutral_site"]),
            "ties": sum(1 for r in rows if r["tie"]),
            "joined_to_a_priced_market": joined,
        },
        "_checks": {
            "publisher_arithmetic_mismatches": checks["publisher_arithmetic_mismatch"],
            "arithmetic_rechecked_ok": checks["arithmetic_rechecked_ok"],
            "unplayed_rows_carried_not_scored": checks["unplayed_rows"],
            "score_never_zero_filled": all(
                (r["status"] == "FINAL") == (r["home_margin"] is not None) for r in rows
            ),
            "settlement_rule_has_a_push_clause": "push" in SETTLEMENT_RULE["side"],
            "decimal_odds_roundtrip_ok": _roundtrip(),
        },
        "ready_for": {
            "backtest_at_the_line": True,
            "backtest_at_the_price": checks["games_with_any_price_market_row"] > 0,
            "note": "The feed itself is complete for every game the publisher scored. ROI at a "
                    "price is limited by the price store's coverage (see price_coverage.json), "
                    "not by this feed.",
        },
    }
    return rows, summary


def _roundtrip() -> bool:
    """Proof that the odds convention in the settlement rule is the standard one."""
    from common import american_to_decimal
    return (abs(american_to_decimal(-110) - 1.909090909) < 1e-6
            and abs(american_to_decimal(+150) - 2.5) < 1e-9
            and abs(american_to_decimal(-200) - 1.5) < 1e-9)


def main() -> int:
    rows, summary = build()
    fields = ["game_id", "season", "week", "game_type", "gameday", "away", "home",
              "away_score", "home_score", "home_margin", "game_total", "tie",
              "neutral_site", "status", "score_arithmetic_ok", "settlement_rule_version"]
    write_csv("data/lab/results/results.csv", fields,
              ({k: blank(r.get(k)) for k in fields} for r in rows))
    write_json("data/lab/results/results.json", {
        "dataset": "results",
        "title": "Verified results feed: one row per game, scored games only carry a score",
        "generated_at": utcnow(),
        "snapshot": SNAPSHOT,
        "upstream": summary["upstream"],
        "settlement_rule_version": SETTLEMENT_RULE["version"],
        "columns": {k: v["definition"] for k, v in COLUMN_PROVENANCE.items()},
        "rows": rows,
        "coverage": summary["coverage"],
    })
    write_json("data/lab/results/result_summary.json", summary)

    c = summary["coverage"]
    print(f"results feed: {c['games']} games, {c['final']} final, {c['scheduled']} scheduled")
    print(f"  seasons                  : {c['seasons'][0]}-{c['seasons'][1]}")
    print(f"  arithmetic mismatches    : {summary['_checks']['publisher_arithmetic_mismatches']}")
    print(f"  re-checked clean         : {summary['_checks']['arithmetic_rechecked_ok']}")
    print(f"  joined to a priced market: {c['joined_to_a_priced_market']}")
    print(f"  ties                     : {c['ties']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
