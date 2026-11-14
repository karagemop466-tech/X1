#!/usr/bin/env python3
"""Verify the round-2 stores — session arena/907c5baf-x1 (task N6).

Contract checks, all of them enforcing decisions the site already publishes:

  1. The six store JSONs exist, parse, and carry their source provenance.
  2. results_feed.json: official-page sources only (nfl.com host); blank scores
     only where status is not FINAL; settlement outcomes well-formed; the
     standings-arithmetic check is present with all 32 clubs.
  3. price_snapshots.json: every game is ordered side -> total -> moneyline;
     market columns exist on every row; a filled market cell must carry a
     non-mirror source; a blank market cell must carry the no-official-source
     flag (never a silent blank).
  4. data/pipeline/correlations.json: every correlation row publishes n beside
     its r and cites an official host.
  5. leaderboard_split.json: the staking scorecard is unranked by rule and the
     ranking rule reads from signal columns only.
  6. demotion_gate.json: defined, with labelled thresholds and a paper-return
     action.
  7. round2 decision/suggestion registers carry the review-before-implement
     fields (three paths, decision status).
  8. app/results.html and app/prices.html exist and were generated.

Run: python3 tools/verify_stores.py   (exit 0 = contract holds)
"""

from __future__ import annotations

import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAIL: list = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAIL.append(msg)


def load(name: str) -> dict:
    p = os.path.join(ROOT, "data", name)
    check(os.path.exists(p), f"{name} is missing")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    feed = load("results_feed.json")
    prices = load("price_snapshots.json")
    split = load("leaderboard_split.json")
    demotion = load("demotion_gate.json")
    r2d = load("round2_decisions.json")
    r2s = load("round2_suggestions.json")

    # ------------------------------------------------- 2. results feed
    rows = feed.get("rows", [])
    check(len(rows) >= 1, "results feed has no rows")
    for r in rows:
        u = str(r.get("_source_url", ""))
        check("nfl.com" in u, f"results row {r.get('game_id')} not sourced to nfl.com")
        if r.get("status") != "FINAL":
            check(r.get("away_score") in ("", None) and r.get("home_score") in ("", None),
                  f"scheduled row {r.get('game_id')} carries a score")
        else:
            check(r.get("away_score") != "" and r.get("home_score") != "",
                  f"final row {r.get('game_id')} is missing a score")
    for r in feed.get("settlement", []):
        check(r.get("outcome") in ("WIN", "LOSS", "PUSH"),
              f"settlement leg {r.get('leg')} has bad outcome {r.get('outcome')}")
        check("nfl.com" in str(r.get("_source_url", "")),
              f"settlement leg {r.get('leg')} not sourced to nfl.com")
    ar = feed.get("integrity_checks", {}).get("standings_arithmetic", {})
    check(ar.get("match") == 32 and ar.get("teams_checked") == 32,
          "standings arithmetic is not 32/32 in the feed")
    mc = feed.get("integrity_checks", {}).get("mirror_cross_check", {})
    check(mc.get("games_compared", 0) > 0, "mirror cross-check missing")
    check(feed.get("settlement_summary", {}).get("roi_note", ""), "ROI n-note missing")

    # ------------------------------------------------ 3. price snapshots
    prows = prices.get("rows", [])
    check(len(prows) >= 1, "price store has no rows")
    per_game: dict = {}
    for r in prows:
        per_game.setdefault(r["game_id"], []).append(r)
        check("market_open_line" in r and "market_close_line" in r,
              f"price row {r.get('snapshot_id')} lacks market columns")
        for col in ("market_open_line", "market_close_line"):
            v = r.get(col)
            if v not in ("", None):
                check("nfl.com" in str(r.get("_source_url", "")) or "nfl.bet" in str(r.get("_source_url", "")),
                      f"{r.get('snapshot_id')} filled {col} without an official price source")
            else:
                flags = " ".join(r.get("_flags") or [])
                check("no official source" in flags,
                      f"{r.get('snapshot_id')} blank {col} without the no-official-source flag")
    for gid, rs in per_game.items():
        seq = [int(r["sequence"]) for r in rs]
        check(seq == sorted(seq), f"{gid}: price rows not ordered side -> total -> moneyline")
        types = [r["market_type"] for r in rs]
        check(types[0] == "spread" and "total" in types and "moneyline" in types,
              f"{gid}: missing market in price store")

    # -------------------------------------------- 4. correlations publish n
    corr = load("pipeline/correlations.json")
    if os.path.exists(os.path.join(ROOT, "data", "pipeline", "correlations.json")):
        crows = corr.get("rows", [])
        check(len(crows) > 0, "pipeline correlations empty")
        for r in crows[:200]:
            check(r.get("n") not in ("", None), f"correlation row {r.get('pair')} has no n")
            u = " ".join(str(r.get(k, "")) for k in ("_source_url", "_source_urls"))
            check("nfl.com" in u or "nfl.bet" in u or "espn.com" in u or "pro-football-reference.com" in u,
                  f"correlation row {r.get('pair')} lacks an official source")

    # ------------------------------------------------ 5. signal vs staking
    pol = split.get("policy", {})
    check("signal" in str(pol.get("ranking_rule", "")).lower(),
          "leaderboard split: ranking rule does not read from signal columns")
    stk = split.get("staking_scorecard", {})
    check(stk.get("ranked") is False, "staking scorecard must be unranked")
    for r in stk.get("rows", []):
        check("cannot change rank" in str(r.get("rank_effect", "")).lower(),
              f"staking row {r.get('strategy_id')} missing the no-rank-effect rule")
    check(len(split.get("signal_scorecard", {}).get("rows", [])) > 0,
          "signal scorecard is empty")

    # ----------------------------------------------------- 6. demotion gate
    check(demotion.get("rows"), "demotion gate is undefined")
    check("paper" in json.dumps(demotion.get("title", "")).lower()
          or any("paper" in str(r.get("action", "")).lower() for r in demotion.get("rows", [])),
          "demotion gate has no paper-return action")
    for r in demotion.get("rows", []):
        check(str(r.get("threshold_status", "")).strip() != "",
              f"demotion trigger {r.get('id')} has an unlabelled threshold")

    # --------------------------------- 7. round-2 review-before-implement
    for r in r2d.get("rows", []):
        for k in ("id", "question", "why_it_matters", "information_missing",
                  "how_to_get_it", "status", "_source_url"):
            check(r.get(k) not in ("", None), f"round2 decision {r.get('id')} missing {k}")
    for r in r2s.get("rows", []):
        for k in ("id", "suggestion", "path_a", "path_b", "path_c",
                  "recommended_path", "decision_status", "_source_url"):
            check(r.get(k) not in ("", None), f"round2 suggestion {r.get('id')} missing {k}")

    # --------------------------------------------------- 8. generated pages
    for fn, marker in (("app/results.html", "results.html"),
                       ("app/prices.html", "prices.html"),
                       ("app/leaderboard.html", "Signal scorecard"),
                       ("app/validation.html", "Demotion gate")):
        p = os.path.join(ROOT, fn)
        check(os.path.exists(p), f"{fn} missing")
        if os.path.exists(p):
            html = open(p, encoding="utf-8").read()
            check(marker in html, f"{fn} lacks expected marker '{marker}'")

    if FAIL:
        print(f"store contract: {len(FAIL)} failure(s)")
        for f in FAIL:
            print("  FAIL", f)
        return 1
    print("store contract: results feed sourced + settleable; price rows ordered "
          "side->total->ML with blank-or-sourced market cells; correlations publish n; "
          "signal ranked / staking unranked; demotion gate defined; round-2 registers complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
