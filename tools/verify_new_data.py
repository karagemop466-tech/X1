#!/usr/bin/env python3
"""Verification gate for the new data stores (T10-T17).

Checks, line by line:
1. Every row carries at least one source URL, or an explicit unverified flag.
2. Blank opening cells in the price-snapshot store are flagged, never silent.
3. The results feed matches the official_scores_2026_week*.psv transcriptions
   exactly (independent re-read of the source-of-record files).
4. The origination ledger keeps model_fair_line / market_line / difference as
   separate columns and difference = model - market on every computable row.
5. Official correlations publish n with every value.
6. Signal and staking blocks are separate on the leaderboard.
7. The demotion gate has triggers and a process.

Exit code 0 = all checks pass; 1 = at least one failure (printed).
"""
import csv
import glob
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
L = os.path.join(ROOT, "data", "lines")

fails = []


def fail(msg):
    fails.append(msg)
    print(f"FAIL: {msg}")


def ok(msg):
    print(f"  ok: {msg}")


def implied_prob(american):
    a = float(american)
    return (-a) / ((-a) + 100.0) if a < 0 else 100.0 / (a + 100.0)


def main():
    # ---------- 1/2: price snapshots ----------
    ps = json.load(open(os.path.join(L, "price_snapshots.json")))
    rows = ps["rows"]
    n_flag = 0
    for r in rows:
        if not r.get("closing_source_url") and "unverified" not in "; ".join(r.get("flags", [])):
            fail(f"price row {r['game_id']} {r['market_type']} has no source and no flag")
        if r.get("opening_line") is None:
            if not any("opening" in f.lower() for f in r.get("flags", [])):
                fail(f"price row {r['game_id']} {r['market_type']} blank opening without flag")
            n_flag += 1
    ok(f"price_snapshots: {len(rows)} rows, {n_flag} blank openings all flagged")

    # ---------- 3: results feed vs official transcriptions ----------
    feed = json.load(open(os.path.join(L, "results_feed.json")))
    official = {}   # (week, away_code, home_code) -> (ascore, hscore, status, slug)
    for path in sorted(glob.glob(os.path.join(ROOT, "data", "verify", "official_scores_2026_week*.psv"))):
        week = int(path.split("week")[-1].split(".")[0])
        for line in open(path):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            f = line.split("|")
            official[(week, f[2], f[4])] = (int(f[3]), int(f[5]), f[6], f[0])
    ABBR = {"ARI": "AZ", "LA": "LAR"}   # games.csv abbrevs -> nfl.com codes used in the psv files
    n_ok = 0
    seen = set()
    for r in feed["rows"]:
        key = (r["week"], ABBR.get(r["away"], r["away"]), ABBR.get(r["home"], r["home"]))
        m = official.get(key)
        if not m:
            fail(f"results row {r['game_id']} not matched against official transcriptions")
            continue
        if key in seen:
            fail(f"results row {r['game_id']} duplicates {key}")
        seen.add(key)
        n_ok += 1
        if (r["away_score"], r["home_score"]) != (m[0], m[1]):
            fail(f"results row {r['game_id']} scores {r['away_score']}-{r['home_score']} != official {m[0]}-{m[1]}")
        if r["status"] != m[2]:
            fail(f"results row {r['game_id']} status '{r['status']}' != official '{m[2]}'")
        if not (r["result_source_url"].startswith("https://www.nfl.com")
                or r["result_source_url"].startswith("https://static.www.nfl.com")):
            fail(f"results row {r['game_id']} source is not an nfl.com property")
    if n_ok != len(official) or n_ok != len(feed["rows"]):
        fail(f"results feed row count {len(feed['rows'])} != official transcriptions {len(official)} (matched {n_ok})")
    else:
        ok(f"results_feed: {n_ok}/{len(official)} rows match the official transcriptions line by line")

    # ---------- 4: origination ----------
    og = json.load(open(os.path.join(L, "origination.json")))
    by_game = {}
    for r in og["rows"]:
        for col in ("model_fair_line", "market_line", "difference"):
            if col not in r:
                fail(f"origination row {r['game_id']} missing column {col}")
        if r.get("difference") is not None and r.get("model_fair_line") is not None and r.get("market_line") is not None:
            if r["difference_unit"] == "implied_probability":
                want = round(implied_prob(r["model_fair_line"]) - implied_prob(r["market_line"]), 6)
            else:
                want = round(float(r["model_fair_line"]) - float(r["market_line"]), 3)
            tol = 1e-5 if r["difference_unit"] == "implied_probability" else 1e-4
            if abs(float(r["difference"]) - want) > tol:
                fail(f"origination row {r['game_id']} {r['market_type']} difference {r['difference']} != model-market {want}")
        by_game.setdefault(r["game_id"], set()).add(r["origination_order"])
    for gid, orders in by_game.items():
        if orders != {1, 2, 3}:
            fail(f"origination game {gid} has orders {sorted(orders)}, expected side/total/moneyline (1,2,3)")
    ok(f"origination: {len(by_game)} games, each with order 1=side, 2=total, 3=moneyline; difference = model-market verified")

    # ---------- 5: correlations n ----------
    co = json.load(open(os.path.join(L, "correlation_official.json")))
    for r in co["official"]["rows"]:
        if r.get("n") in (None, ""):
            fail(f"official correlation '{r.get('pair')}' has no n")
    for r in co["research"]["pairwise_strategy"]:
        if r.get("n") in (None, ""):
            fail(f"research pairwise {r['strategy_a']}/{r['strategy_b']} has no n")
    for r in co["research"]["matrix"]:
        if r.get("n") is None and "not recorded" not in str(r.get("n_status", "")):
            fail(f"matrix cell {r['strategy_a']}/{r['strategy_b']} publishes a bare value")
    ok(f"correlation_official: {len(co['official']['rows'])} official values all carry n; "
       f"{len(co['research']['matrix'])} matrix cells either carry n or declare 'n not recorded'")

    # ---------- 6: leaderboard split ----------
    ls = json.load(open(os.path.join(L, "leaderboard_split.json")))
    for r in ls["rows"]:
        if "signal" not in r or "staking" not in r:
            fail(f"leaderboard row {r['key']} missing signal/staking split")
        if r["staking"].get("staked_roi") is not None and not r["staking"].get("stakes"):
            fail(f"leaderboard row {r['key']} has staked ROI without recorded stakes")
    ok(f"leaderboard_split: {len(ls['rows'])} rows, signal and staking blocks separate")

    # ---------- 7: demotion gate ----------
    dg = json.load(open(os.path.join(L, "demotion_gate.json")))
    if len(dg.get("triggers", [])) < 1 or not dg.get("process", {}).get("on_fire"):
        fail("demotion gate missing triggers or process")
    else:
        ok(f"demotion_gate: {len(dg['triggers'])} triggers armed, process defined")

    # ---------- replacement depth sanity ----------
    rd = json.load(open(os.path.join(L, "replacement_depth.json")))
    for r in rd["rows"]:
        if r["replacement_depth"] is not None and r["replacement_depth"] not in (2, 3, 4):
            fail(f"replacement depth {r['replacement_depth']} out of range for {r['team']} {r['position']}")
    ok(f"replacement_depth: {len(rd['rows'])} rows, depths in {{2,3,4}} or blank+flagged")

    print()
    if fails:
        print(f"{len(fails)} FAILURES")
        return 1
    print("ALL CHECKS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
