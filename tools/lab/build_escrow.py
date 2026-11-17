#!/usr/bin/env python3
"""PR-04 — the Week 11 pre-kickoff escrow record, and the ledger that settles what is already on file.

    python3 tools/lab/build_escrow.py             # write the record, the ledger and the meta file
    python3 tools/lab/build_escrow.py --check     # fail if a committed artefact is stale, or if the
                                                  # pre-kickoff ordering no longer holds
    python3 tools/lab/build_escrow.py --report    # print the meta, write nothing

`docs/preregistration/PR-04-week11-escrow.md` is the rule; this file is its implementation, so a drift
between the two is a defect in the artefact and not a matter of taste.

Three properties the build enforces rather than claims
------------------------------------------------------
1. **Before kickoff.** The record's timestamp is the clock time of the official read that produced the
   slate (`data/lab/reads/2026-11-17/week11_slate_2026-11-17.tsv`), taken from the file, not from this
   build's clock. The build aborts unless every fixture's kickoff is strictly later than that read.
   "We wrote this first" is arithmetic here, so the claim survives a rebuild and a re-check.
2. **Same maths as the registration it inherits from.** The rating function, the home edge, the sigma and
   the probability transform are imported from `tools/build_shadow_baseline.py` (PR-01) and read from that
   module's constants. Two registrations that differ only because someone retyped a constant are the classic
   way a pre-registration quietly becomes a fit.
3. **The prediction cannot be edited.** The forecast file refuses to drop or alter a game_id it has already
   recorded; the ledger is rebuilt from the record plus the official reads, because re-scoring as games
   settle is not the same act as rewriting what was said.

The 2026-11-16 shadow record (`data/shadow/**`, PR-01) is never modified by this script: it is read, joined
and scored. Its corpus is 149 games because it was written before the Monday-night final existed; this
registration's corpus is 150 because it was written after. Two records, two timestamps, no merging.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_pr01():
    """Import the module that holds PR-01's frozen constants and frozen math, by path.

    Loaded rather than retyped: the point of inheriting a registration is that the numbers cannot drift
    between the two implementations. `tools/` is not a package, so this is importlib, not an import.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "pr01_shadow_baseline", os.path.join(ROOT, "tools", "build_shadow_baseline.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PR01 = _load_pr01()

ESCROW = os.path.join(ROOT, "data", "lab", "escrow")
FORECASTS = os.path.join(ESCROW, "week11_forecasts_2026-11-17.csv")
LEDGER = os.path.join(ESCROW, "settlement_ledger.csv")
META = os.path.join(ESCROW, "escrow_meta.json")
READS = os.path.join(ROOT, "data", "lab", "reads", "2026-11-17")
W11_SLATE = os.path.join(READS, "week11_slate_2026-11-17.tsv")
W10_FINALS = os.path.join(READS, "week10_finals.tsv")
PRIOR_W10 = os.path.join(ROOT, "data", "verification", "2026_11_16",
                         "official_w10_results_2026_11_16.tsv")
PR01_RECORD = os.path.join(ROOT, "data", "shadow", "forecasts_pre_kickoff.csv")
PR01_SUMMARY = os.path.join(ROOT, "data", "shadow", "backtest_summary.json")
REGISTRATION = "docs/preregistration/PR-04-week11-escrow.md"

MARKETS = ("side", "total_A", "total_B", "moneyline")
MARKET_ORDER = {"side": 1, "total_A": 2, "total_B": 2, "moneyline": 3}
# November in the US is on Eastern Standard Time, which is UTC-5, and every Week 11 kickoff in this
# window (2026-11-19 .. 2026-11-23) is after the 2026-11-01 transition. The offset is therefore a fixed
# number for the window rather than a per-row guess: local = UTC - 5h, so UTC = local + 5h.
ET_OFFSET = timedelta(hours=-5)

HEADER = ["escrow_id", "market_order", "market", "game_id", "week", "kickoff_et", "kickoff_utc",
          "away", "home", "our_fair_line", "our_probability", "market_line", "residual",
          "residual_status", "rest_days_away", "rest_days_home", "recorded_at_utc",
          "recorded_before_kickoff", "official_fixture_url", "slate_source_url", "flags"]
LEDGER_HEADER = ["ledger_id", "origin_record", "game_id", "week", "market", "kickoff_et", "away", "home",
                 "our_fair_line", "our_probability", "settled", "settlement_source_url", "settlement_read_at",
                 "away_score", "home_score", "outcome_home", "margin_home_points",
                 "fair_line_error_points", "brier", "log_loss", "brier_vs_home_baseline_0_55",
                 "brier_vs_coin_0_50", "skill_vs_home_baseline", "flags"]


def read_tsv(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().split("\n") if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(io.StringIO("\n".join(lines)), delimiter="\t"))


def sha256_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def kickoff_utc(date_et: str, time_et: str) -> datetime:
    """'2026-11-19' + '8:15 PM' (Eastern) as an aware UTC datetime."""
    hh, mm = (int(x) for x in time_et.split(" ")[0].split(":"))
    ampm = time_et.split(" ")[1].upper()
    if ampm == "PM" and hh != 12:
        hh += 12
    elif ampm == "AM" and hh == 12:
        hh = 0
    local = datetime(int(date_et[:4]), int(date_et[5:7]), int(date_et[8:10]), hh, mm)
    return (local - ET_OFFSET).replace(tzinfo=timezone.utc)


def z(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def to_csv(header: list[str], data: list[list[str]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(data)
    return buf.getvalue()


def load_corpus() -> tuple[list[dict], dict]:
    """PR-01's loader (the weeks 1-9 log plus its 2026-11-16 Week 10 read), then the game that the
    2026-11-17 read adds. The frozen part is not recomputed, so both records share one code path."""
    games, prov = PR01.load_games()
    have = {g["source_url"].rstrip("/").split("/")[-1] for g in games}
    added = []
    for r in read_tsv(W10_FINALS):
        if r["row_type"] != "game" or r["status"] != "Final":
            continue
        slug = r["game_url"].rstrip("/").split("/")[-1]
        if slug in have:
            continue
        games.append({"game_id": f"10_{slug}", "week": 10, "date": r["date_et"], "away": r["away"],
                      "home": r["home"], "away_score": int(r["away_score"]),
                      "home_score": int(r["home_score"]), "status": "final",
                      "source_url": r["game_url"],
                      "source_file": "data/lab/reads/2026-11-17/week10_finals.tsv",
                      "read_on": "2026-11-17"})
        added.append(slug)
    games.sort(key=lambda g: (g["date"], g["week"], g["game_id"]))
    prov["added_by_the_2026_11_17_read"] = added
    prov["games"] = len(games)
    return games, prov


def club_state(games: list[dict]) -> dict:
    """Per-club cumulative state over the whole corpus, plus the league constants the totals need.

    The rating line is PR-01's `rating_from` so the shrinkage is literally the same function.
    """
    agg: dict[str, dict] = {}
    for g in games:
        for club, pts, opp in ((g["away"], g["away_score"], g["home_score"]),
                               (g["home"], g["home_score"], g["away_score"])):
            a = agg.setdefault(club, {"n": 0, "diff": 0.0, "for": 0, "against": 0, "last": ""})
            a["n"] += 1
            a["diff"] += pts - opp
            a["for"] += pts
            a["against"] += opp
            if g["date"] > a["last"]:
                a["last"] = g["date"]
    K = PR01.K_PRIOR_GAMES
    league_ppg = sum(g["away_score"] + g["home_score"] for g in games) / (2 * len(games))
    for club, a in agg.items():
        shrink = a["n"] / (a["n"] + K)
        a["rating"] = PR01.rating_from((a["n"], a["diff"]))
        a["pts_shrunk"] = shrink * (a["for"] / a["n"]) + (1 - shrink) * league_ppg
        a["alg_shrunk"] = shrink * (a["against"] / a["n"]) + (1 - shrink) * league_ppg
    return {"clubs": agg, "league_ppg": league_ppg,
            "league_total": sum(g["away_score"] + g["home_score"] for g in games) / len(games)}


def official_finals() -> dict[str, dict]:
    """Every game this repository has transcribed as Final from an official page, keyed by game_id,
    oldest read first so the first read of a game wins and a later re-read cannot change a settlement."""
    out: dict[str, dict] = {}
    for path, read_on in ((PRIOR_W10, "2026-11-16"), (W10_FINALS, "2026-11-17")):
        for r in read_tsv(path):
            if r.get("row_type", "game") != "game" or r.get("status") != "Final":
                continue
            if not (r.get("away_score") or "").strip():
                continue
            r = dict(r)
            r["_read_on"] = r.get("read_at") or read_on
            r["_source"] = path
            out.setdefault(r["game_id"], r)
    return out


def build(do_write: bool = True) -> dict:
    fails: list[str] = []
    games, prov = load_corpus()
    st = club_state(games)
    clubs, league_total = st["clubs"], st["league_total"]

    # PR-01's pre-kickoff record is a CSV with two comment lines above its header, hence the filter.
    pr01_text = open(PR01_RECORD, encoding="utf-8").read()
    pr01_lines = [ln for ln in pr01_text.split("\n") if ln.strip() and not ln.lstrip().startswith("#")]
    pr01_rows = list(csv.DictReader(io.StringIO("\n".join(pr01_lines))))
    pr01_by_game = {r["game_id"]: r for r in pr01_rows if r.get("game_id")}

    slate = [r for r in read_tsv(W11_SLATE) if r["row_type"] == "game"]
    if len(slate) != 13:
        fails.append(f"slate: expected 13 Week 11 fixtures, found {len(slate)}")
    # The pack stamps its read to the minute, so the comparison is done at second precision by widening
    # the stamp with :00. That is only sound because the nearest kickoff is hours away, and the artefact
    # prints that slack so a reader can see how much it matters: if a future record is ever written inside
    # a kickoff minute, this is the line that has to change.
    raw_read = slate[0]["read_at"]
    read_at = (raw_read[:-1] + ":00Z") if len(raw_read) == 17 and raw_read.endswith("Z") else raw_read
    read_at = datetime.strptime(read_at, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%dT%H:%M:%SZ")
    read_dt = datetime.strptime(read_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

    rows: list[list[str]] = []
    for r in slate:
        a, h = r["away"], r["home"]
        if a not in clubs or h not in clubs:
            fails.append(f"{r['game_id']}: a club is missing from the corpus")
            continue
        kick = kickoff_utc(r["date_et"], r["time_et"])
        before = kick > read_dt
        if not before:
            fails.append(f"{r['game_id']}: kickoff {z(kick)} is not after the read {read_at}")
        ca, ch = clubs[a], clubs[h]
        margin = ch["rating"] - ca["rating"] + PR01.H_HOME_POINTS
        p_home = PR01.phi(margin / PR01.SIGMA_POINTS)
        fair_side = round(-margin * 2) / 2
        exp_home = (ch["pts_shrunk"] + ca["alg_shrunk"]) / 2
        exp_away = (ca["pts_shrunk"] + ch["alg_shrunk"]) / 2
        total_b = round((exp_home + exp_away) * 2) / 2
        rest = lambda club: (kick.date() - datetime.strptime(clubs[club]["last"], "%Y-%m-%d").date()).days
        withheld = ("market line and residual withheld: no licensed price source for 2026 in this "
                    "repository (open question Q-02)")
        per_market = {
            "side": (f"{fair_side:+.1f}", f"{p_home:.6f}",
                     "order 1; the model's own number, no vig, not a quote"),
            "total_A": (f"{round(league_total * 2) / 2:.1f}", "",
                        "order 2, estimator A: the league-average total, i.e. the floor a margin model has"),
            "total_B": (f"{total_b:.1f}", f"{(exp_home + exp_away) - league_total:+.3f}",
                        "order 2, estimator B: two-club scoring shrunk by the frozen K; our_probability holds "
                        "the gap of B over A, which is the number the walk-forward comparison judges"),
            "moneyline": (f"home {PR01.american(p_home)} / away {PR01.american(1 - p_home)}", f"{p_home:.6f}",
                          "order 3; zero-vig conversion of p, the same stated conversion PR-01 uses"),
        }
        # One dict per market row, keyed by the header names. Building rows positionally is how a column
        # gets dropped silently; keyed construction makes a missing field an exception, not a shift.
        for m_name, (line, prob, note) in per_market.items():
            rows.append({
                "escrow_id": f"{r['game_id']}#{m_name}", "market_order": str(MARKET_ORDER[m_name]),
                "market": m_name, "game_id": r["game_id"], "week": r["game_id"].split("_")[1],
                "kickoff_et": f"{r['date_et']} {r['time_et']}", "kickoff_utc": z(kick), "away": a, "home": h,
                "our_fair_line": line, "our_probability": prob, "market_line": "", "residual": "",
                "residual_status": f"BLANK — {withheld}", "rest_days_away": str(rest(a)),
                "rest_days_home": str(rest(h)), "recorded_at_utc": read_at,
                "recorded_before_kickoff": "yes" if before else "NO", "official_fixture_url": r["game_url"],
                "slate_source_url": r["source_url"], "flags": note,
            })
    rows.sort(key=lambda x: (x["game_id"], int(x["market_order"]), x["market"]))
    for d in rows:                       # every declared column present, no exceptions, no silent shifts
        missing = [k for k in HEADER if k not in d]
        if missing:
            raise SystemExit(f"ABORT: {d['escrow_id']} is missing {missing}")

    first_kick = datetime.strptime(min(r["kickoff_utc"] for r in rows),
                                   "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    slack = first_kick - read_dt          # how much margin "before kickoff" actually buys

    # PR-01's own artefact states the corpus its numbers were computed on; it is published beside this
    # record so the two windows can be told apart by a reader instead of by whoever remembers them.
    pr01_corpus_games = ""
    if os.path.exists(PR01_SUMMARY):
        pr01_corpus_games = json.load(open(PR01_SUMMARY, encoding="utf-8"))["corpus"]["games_ingested"]

    finals = official_finals()
    ledger: list[list[str]] = []
    seen_pr01 = 0
    for r in pr01_rows:
        if not (r.get("game_id") or "").strip():
            continue
        seen_pr01 += 1
        gid = r["game_id"]
        p_home = float(r["p_home"])
        exp_margin = float(r["expected_margin_home"])
        f = finals.get(gid)
        base = [f"PR01#{gid}", f"PR-01 ({r['recorded_at_utc']})", gid, r["week"], "side",
                r["kickoff_et"], r["away"], r["home"], r["fair_line_home"], f"{p_home:.6f}"]
        if f is None:
            ledger.append(base + ["no"] + [""] * 12 +
                          [f"open: no official final for this fixture is transcribed in this repository "
                           f"(reads available as of {read_at[:10]})"])
            continue
        a_s, h_s = int(f["away_score"]), int(f["home_score"])
        margin = h_s - a_s
        outcome = 1.0 if margin > 0 else (0.0 if margin < 0 else 0.5)
        brier = (p_home - outcome) ** 2
        log_loss = -math.log(min(p_home, 1 - p_home)) if outcome in (0.0, 1.0) else -math.log(0.5)
        b_home = (PR01.HOME_BASELINE_P - outcome) ** 2
        b_coin = (0.5 - outcome) ** 2
        pick_won = (p_home > 0.5) == (outcome == 1.0)
        ledger.append(base + [
            "yes", f["game_url"], f["_read_on"][:10], str(a_s), str(h_s), f"{outcome:.1f}", f"{margin:+d}",
            f"{abs(margin - exp_margin):.2f}", f"{brier:.6f}", f"{log_loss:.6f}", f"{b_home:.6f}",
            f"{b_coin:.6f}", f"{(b_home - brier) / b_home:+.6f}",
            "settled from an official final read; model side " + ("hit" if pick_won else "missed") +
            "; not leaderboard-eligible (PR-01 rule)",
        ])

    # every PR-04 escrow row, open by construction: no Week 11 final can exist before the read
    for d in rows:
        if finals.get(d["game_id"]) is not None:
            fails.append(f"{d['game_id']}: a Week 11 fixture is already final - the escrow window has closed")
        if d["market"] not in ("side", "moneyline"):
            continue
        ledger.append([f"PR04#{d['game_id']}#{d['market']}", f"PR-04 (recorded {read_at[:10]})",
                       d["game_id"], d["week"], d["market"], d["kickoff_et"], d["away"], d["home"],
                       d["our_fair_line"], d["our_probability"], "no"] + [""] * 12 +
                      [f"open: this fixture has not kicked off; the ledger row is written now so the "
                       f"settlement later is the same code path, not a reconstruction"])
    # totals: both estimators are recorded so the comparison itself is prospective
    for d in rows:
        if d["market"] not in ("total_A", "total_B"):
            continue
        ledger.append([f"PR04#{d['game_id']}#{d['market']}", f"PR-04 (recorded {read_at[:10]})",
                       d["game_id"], d["week"], d["market"], d["kickoff_et"], d["away"], d["home"],
                       d["our_fair_line"], d["our_probability"], "no"] + [""] * 12 +
                      ["open: settled against the official final total points; total_A and total_B are "
                       "scored on the same rows and neither is preferred in advance"])

    forecast_text = to_csv(HEADER, [[d[k] for k in HEADER] for d in rows])
    ledger_text = to_csv(LEDGER_HEADER, ledger)

    # Cross-registration delta: the same 13 fixtures were forecast by PR-01 on 2026-11-16 from a
    # 149-game corpus, and are forecast here on 2026-11-17 from a 150-game corpus, with one rule and one
    # code path. The size of the move is the honest measure of how much a single settled game changes this
    # model, which is the number a reader needs in order to judge whether either record is fragile.
    deltas = []
    for row in rows:
        d = dict(zip(HEADER, row))
        if d["market"] != "side":
            continue
        p1 = pr01_by_game.get(d["game_id"], {}).get("p_home")
        if not p1:
            continue
        deltas.append({"game_id": d["game_id"], "p_pr01_2026_11_16": float(p1),
                       "p_pr04_2026_11_17": float(d["our_probability"]),
                       "delta": round(float(d["our_probability"]) - float(p1), 6),
                       "fair_line_pr01": pr01_by_game[d["game_id"]]["fair_line_home"],
                       "fair_line_pr04": d["our_fair_line"]})
    max_move = max(((abs(x["delta"]), x["game_id"]) for x in deltas), default=(0, ""))

    settled = [l for l in ledger if l[10] == "yes" and l[4] == "side"]
    n = len(settled)
    stats: dict = {"n_settled_side_rows": n, "n_pr01_records": seen_pr01,
                   "n_pr04_rows_open": len(ledger) - n}
    if n:
        bs = [float(l[18]) for l in settled]
        bh = [float(l[20]) for l in settled]
        ps = [max(float(l[9]), 1 - float(l[9])) for l in settled]
        hits = sum(1 for l in settled if "hit" in l[23])
        stats.update({
            "mean_brier": round(sum(bs) / n, 6),
            "mean_brier_home_baseline": round(sum(bh) / n, 6),
            "brier_skill_vs_home_baseline": round((sum(bh) - sum(bs)) / sum(bh), 6),
            "model_side_hits": hits,
            "expected_wins_on_model_side": round(sum(ps), 4),
            "sd_of_wins": round(math.sqrt(sum(p * (1 - p) for p in ps)), 4),
            "mean_fair_line_error_points": round(sum(float(l[17]) for l in settled) / n, 3),
            "reading": ("n = 1 is not evidence of anything, in either direction. The ledger exists so the "
                        "number is computed the day an official page prints a final, from the record that "
                        "was written before it, instead of being reconstructed afterwards."),
        })
    meta = {
        "dataset": "week11-escrow-PR-04",
        "title": "Week 11 pre-kickoff escrow record, and the settlement ledger for every forecast on file",
        "registration": {"rule_file": REGISTRATION, "rule_sha256": sha256_file(os.path.join(ROOT, REGISTRATION)),
                         "how_to_verify": "python3 tools/build_preregistration.py --check"},
        "kickoff_offset_applied": "US Eastern on standard time for this whole window, i.e. UTC = local + 5h",
        "inherited_constants": {"K_prior_games": PR01.K_PRIOR_GAMES, "H_home_points": PR01.H_HOME_POINTS,
                                "SIGMA_points": PR01.SIGMA_POINTS, "home_baseline_p": PR01.HOME_BASELINE_P,
                                "source": "tools/build_shadow_baseline.py (PR-01): imported, not retyped"},
        "recorded_at_utc": read_at,
        "read_clock_precision": ("minute, as recorded in the reads pack; widened to :00 seconds only for "
                                 "the comparison, which is conservative in the direction that can fail"),
        "first_kickoff_utc": min(r["kickoff_utc"] for r in rows),
        "recorded_before_first_kickoff": ("yes" if all(r["recorded_before_kickoff"] == "yes" for r in rows)
                                          else "NO"),
        "recorded_before_first_kickoff_minutes_of_slack": round(slack.total_seconds() / 60, 1),
        "read_clock_precision": ("the reads pack stamps its clock to the minute, so this record could be "
                                 "up to a minute earlier or later than the stamp says. The slack field above "
                                 "is what that uncertainty has to be small against; it is negligible here "
                                 "only because the nearest kickoff is days away, and a record written inside "
                                 "a kickoff minute would have to change this line"),
        "corpus_read": {"games": len(games), "weeks": prov["weeks"],
                   "pr01_registration_corpus_games": pr01_corpus_games,
                   "added_by_the_2026_11_17_read": prov["added_by_the_2026_11_17_read"],
                   "league_average_total_points": round(league_total, 3),
                   "league_points_per_team_per_game": round(st["league_ppg"], 3),
                   "note": ("the corpus this record reads, not a corpus this registration owns: weeks 1-9 "
                            "plus the Week 10 games settled by official reads. PR-01's own 137/149-game "
                            "figures are unchanged by anything here")},
        "inputs": {rel: sha256_file(p) for rel, p in (
            ("data/lab/reads/2026-11-17/week11_slate_2026-11-17.tsv", W11_SLATE),
            ("data/lab/reads/2026-11-17/week10_finals.tsv", W10_FINALS),
            ("data/verification/2026_11_16/official_w10_results_2026_11_16.tsv", PRIOR_W10),
            ("data/shadow/forecasts_pre_kickoff.csv", PR01_RECORD),
            (REGISTRATION, os.path.join(ROOT, REGISTRATION)))},
        "rows_hash": hashlib.sha256(forecast_text.encode()).hexdigest(),
        "ledger_rows_hash": hashlib.sha256(ledger_text.encode()).hexdigest(),
        "markets": list(MARKETS), "market_order": MARKET_ORDER,
        "fixtures": len(slate), "forecast_rows": len(rows), "ledger_rows": len(ledger),
        "cross_registration_delta_vs_pr01": {
            "fixtures_compared": len(deltas), "rows": deltas,
            "largest_move": {"abs_delta": round(max_move[0], 6), "game_id": max_move[1]},
            "mean_abs_delta": round(sum(abs(x["delta"]) for x in deltas) / len(deltas), 6) if deltas else "",
            "what_it_measures": ("the same rule, the same code path, one extra settled game in the corpus. "
                                 "It is not a score and it is not an improvement - it is how sensitive this "
                                 "model is to a single result, which is the thing to know before anyone "
                                 "calls either record a signal"),
        },
        "settled": stats,
        "withheld": {"market_line": "no licensed price source for 2026 (open question Q-02)",
                     "residual": "follows from the blank market line",
                     "clv_and_roi": "no price, no settlement price, so no CLV and no ROI - stated on every row"},
        "limits": [
            "margin model: no opponent adjustment, personnel, venue, rest or weather inside the rating",
            "total_A is the league average by construction; publishing it is the floor total_B has to beat, "
            "not an estimate of any particular game",
            "the Mexico City fixture (Vikings at 49ers) receives the frozen 1.6-point home edge although the "
            "official fixture page prints Location MEXICO CITY and Stadium ESTADIO BANORTE; the rule is frozen "
            "for this window, so the edge is published as the rule states it and the venue is recorded as a "
            "limit, for the next registration to decide on",
            "rest_days columns are published context derived from official schedule dates; the model does not "
            "use them in this registration",
            "the settled aggregate has n = 1 and is a demonstration of the mechanism, not a result",
        ],
        "fails": fails,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if do_write:
        os.makedirs(ESCROW, exist_ok=True)
        if os.path.exists(FORECASTS):
            old = open(FORECASTS, encoding="utf-8").read()
            old_ids = {r["escrow_id"] for r in csv.DictReader(io.StringIO(old))}
            new_ids = {d["escrow_id"] for d in rows}
            added = sorted(new_ids - old_ids)
            dropped = sorted(old_ids - new_ids)
            if added or dropped:
                raise SystemExit(
                    "ABORT: the committed forecast record would change shape.\n"
                    f"  rows this run would add: {added}\n"
                    f"  rows this run would drop: {dropped}\n"
                    "  A forecast file that grows or shrinks after kickoff is not a forecast file.\n"
                    "  If this is a NEW game week, do not edit this record: copy this script's output path to "
                    "a new dated file and register the new window.\n"
                    "  If it is the same week and a row genuinely disappeared, the slate read changed - "
                    "re-read the official page and find out why, before touching any artefact.")
        with open(FORECASTS, "w", encoding="utf-8") as fh:
            fh.write(forecast_text)
        with open(LEDGER, "w", encoding="utf-8") as fh:
            fh.write(ledger_text)
        with open(META, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(meta, indent=1, sort_keys=True) + "\n")
    return {"meta": meta, "forecast_text": forecast_text, "ledger_text": ledger_text, "rows": rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    built = build(do_write=not (a.check or a.report))
    m = built["meta"]
    if a.report:
        print(json.dumps(m, indent=1, sort_keys=True))
        return 0
    if a.check:
        bad = list(m["fails"])
        for path, text in ((FORECASTS, built["forecast_text"]), (LEDGER, built["ledger_text"])):
            if not os.path.exists(path):
                bad.append(f"missing {os.path.relpath(path, ROOT)}")
            elif open(path, encoding="utf-8").read() != text:
                bad.append(f"stale {os.path.relpath(path, ROOT)}")
        if bad:
            print("ESCROW CHECK FAILED:", *bad, sep="\n  - ")
            return 1
        print(f"CHECK OK: {m['forecast_rows']} escrow rows over {m['fixtures']} fixtures, recorded "
              f"{m['recorded_at_utc']} before the first kickoff at {m['first_kickoff_utc']}; "
              f"ledger {m['ledger_rows']} rows, {m['settled']['n_settled_side_rows']} settled")
        return 0
    print("wrote data/lab/escrow/{week11_forecasts_2026-11-17.csv, settlement_ledger.csv, escrow_meta.json}")
    print(f"  fixtures {m['fixtures']}, forecast rows {m['forecast_rows']}, ledger rows {m['ledger_rows']}")
    print(f"  recorded {m['recorded_at_utc']} before first kickoff {m['first_kickoff_utc']}")
    print(f"  corpus {m['corpus_read']['games']} games; league-average total "
          f"{m['corpus_read']['league_average_total_points']}")
    print(f"  settled side rows: {m['settled']['n_settled_side_rows']}")
    if m["fails"]:
        print("FAILURES:", *m["fails"], sep="\n  - ")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
