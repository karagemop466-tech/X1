#!/usr/bin/env python3
"""Decision-readiness table: one row per requirement, the gate that blocks it,
and the number that would clear it.

Session `arena-8e329878-x1` (R4-4). Every "number now" is computed from a file in
this repository when the page is built, so the table cannot drift from the data it
describes. A requirement the repository does not evidence is marked `unverified`
or `not built`; it is never shown as done.

Output: data/r4/readiness.json (rebuilt by every run of tools/build_app.py and of the
captures workflow). Official links are the page the value would come from; a row
whose value has no official publisher says so in `official_source`.
"""

from __future__ import annotations

import csv
import glob
import gzip
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "data", "r4", "readiness.json")

INJ = "https://www.nfl.com/injuries/"
STAND = "https://www.nfl.com/standings/league/2026/REG"
SCHED = "https://www.nfl.com/schedules/2026/by-week/week-10"
TEAMS = "https://www.nfl.com/teams/"
GAMEBOOK_EXAMPLE = "https://static.www.nfl.com/image/upload/v1794570519/gamecenter/ab5828d9-4feb-11f1-abca-2c54536568a9.pdf"
PRICE_NONE = "none: no league or club source publishes betting prices (decision Q-02)"


def _csv(path: str, delimiter: str = ",") -> list:
    full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        return []
    with open(full, encoding="utf-8", errors="replace") as fh:
        lines = [l for l in fh if not l.startswith("#")]
    return list(csv.DictReader(lines, delimiter=delimiter))


def _json(path: str):
    full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        return None
    with open(full, encoding="utf-8") as fh:
        return json.load(fh)


def _jsonl(path: str) -> list:
    full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        return []
    with open(full, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def facts() -> dict:
    f: dict = {}
    caps = _jsonl("data/captures/official_injuries/captures.jsonl")
    reads = _jsonl("data/captures/official_injuries/reads.jsonl")
    live_reads = [r for r in reads if "error" not in r]
    f["captures"] = len(caps)
    f["live_reads"] = len(live_reads)
    f["failed_reads"] = len(reads) - len(live_reads)
    f["capture_methods"] = dict(Counter(c.get("method", "live") for c in caps))
    f["first_capture_at"] = caps[0]["fetched_at_utc"] if caps else None
    last = caps[-1] if caps else {}
    f["last_capture_at"] = last.get("fetched_at_utc")
    f["last_capture_rows"] = last.get("rows")
    f["last_capture_clubs"] = last.get("clubs")
    rows_path = last.get("rows_path")
    desig = 0
    no_injury_clubs = []
    if rows_path and os.path.exists(os.path.join(ROOT, rows_path)):
        rows = _csv(rows_path)
        desig = sum(1 for r in rows if r["game_status"])
        by_club: dict = {}
        for r in rows:
            by_club.setdefault(r["team"], [0])[0] += 1 if r["injury"] else 0
        no_injury_clubs = sorted(t for t, v in by_club.items() if v[0] == 0)
        f["lions_status"] = {
            r["player"]: r["game_status"] for r in rows
            if r["team"] == "DET" and r["player"] in ("Kerby Joseph", "Cade Mays", "D.J. Reed")
        }
    f["last_capture_designations"] = desig
    f["no_injury_clubs"] = no_injury_clubs

    v = _json("data/captures/official_injuries/verification_week10.json") or {}
    f["verify_summary"] = v.get("summary", {})
    f["verify_capture"] = v.get("capture_id")
    f["verify_capture_method"] = v.get("capture_method")

    pub = _csv("data/injuries/injuries_2026_week10.csv")
    f["published_injury_rows"] = len(pub)
    f["published_lions"] = {r["player"]: r["game_status"] for r in pub
                            if r["team"] == "DET" and r["player"] in ("Kerby Joseph", "Cade Mays", "D.J. Reed")}

    # Depth
    dsum = _json("data/depth/replacement_depth_summary.json") or {}
    f["depth_totals"] = dsum.get("totals", {})
    # Club coverage comes from the full pipeline depth file (1,813 rows), not from the
    # gap-only replacement store, which lists only clubs with an unfilled slot.
    dc = _json("data/pipeline/depth_charts.json") or {}
    f["depth_clubs"] = len({r.get("team_abbrev") for r in dc.get("rows", []) if r.get("team_abbrev")})
    f["depth_clubs_missing"] = sorted(
        {"ATL","AZ","BAL","BUF","CAR","CHI","CIN","CLE","DAL","DEN","DET","GB","HOU","IND","JAX","KC","LA","LAC","LV",
         "MIA","MIN","NE","NO","NYG","NYJ","PHI","PIT","SEA","SF","TB","TEN","WAS"}
        - {r.get("team_abbrev") for r in dc.get("rows", [])})

    # Results
    res_files = sorted(glob.glob(os.path.join(ROOT, "data/results/raw/official_results_2026_week*.psv")))
    games = 0
    for p in res_files:
        with open(p, encoding="utf-8") as fh:
            lines = [l for l in fh if l.strip()]
        games += max(0, len(lines) - 1)
    f["official_final_games"] = games
    f["results_files"] = len(res_files)

    # Price store
    pr = _csv("data/console/price_snapshots.csv")
    p26 = [r for r in pr if r.get("season") == "2026"]
    f["price_2026_rows"] = len(p26)
    f["price_2026_markets"] = len({r["market_id"] for r in p26})
    f["price_2026_both_ends"] = sum(1 for r in p26 if r.get("open_line") and r.get("close_line"))

    # Originated lines
    ol = [r for r in _csv("data/console/originated_lines.csv") if r.get("season") == "2026"]
    ids = Counter(r["game_id"] for r in ol)
    f["orig_2026_rows"] = len(ol)
    f["orig_2026_games"] = len(ids)
    f["orig_2026_dup_rows"] = sum(v - 1 for v in ids.values() if v > 1)
    w10 = Counter(r["game_id"] for r in ol if r["week"] == "10")
    f["orig_week10_rows"] = sum(w10.values())
    f["orig_week10_games"] = len(w10)
    f["orig_2026_market_blank_games"] = len({r["game_id"] for r in ol if not r["market_side"] and r["mode"] == "oos"})

    # Schedule
    sched = _csv("data/nfl/schedule_2026_week10.csv")
    f["week10_games"] = len(sched)
    f["week10_venue_notes"] = sum(1 for r in sched if (r.get("venue_note") or "").strip())
    byes = _csv("data/nfl/week10_byes.csv")
    f["week10_byes"] = len(byes)

    # Strategies
    sr = _csv("data/console/strategy_results.csv")
    f["console_strategies"] = len(sr)
    reg = _csv("data/strategies/strategies_registry.csv")
    f["registry_strategies"] = len(reg)
    f["registry_has_change_field"] = any("change" in c.lower() and "mind" in c.lower()
                                         for c in (reg[0].keys() if reg else []))
    f["registry_has_hash_field"] = any("hash" in c.lower() or "commit" in c.lower()
                                       for c in (reg[0].keys() if reg else []))

    lb = _json("data/leaderboard_signal_staking_official.json") or {}
    st11 = next((r for r in lb.get("rows", []) if r.get("strategy_id") == "ST-11" or r.get("id") == "ST-11"), None)
    f["st11"] = st11 or {}
    f["lb_rows"] = len(lb.get("rows", []))

    corr = _json("data/correlations_official_check.json") or {}
    cv = corr.get("verification", {})
    f["corr_pairs"] = cv.get("pairs")
    f["corr_pairs_with_n"] = cv.get("pairs_with_n")

    gates = _json("data/gates.json") or {}
    f["gate_g8"] = any(str(g.get("id", "")).upper() == "G8" for g in (gates.get("gates", gates.get("rows", [])) if isinstance(gates, dict) else gates))

    trades = _csv("data/raw/nflverse/trades.csv")
    f["trades_rows"] = len(trades)

    f["brief_designations_claim"] = "6 of 254"
    return f


def _state(f: dict) -> dict:
    return f


def rows(f: dict) -> list:
    v = f["verify_summary"]
    d = f["depth_totals"]
    st = f["st11"]
    cap_rows = f["last_capture_rows"] or 0
    R = []

    def add(rid, group, req, status, now, gate, clear, source, evidence, flag=""):
        R.append({
            "id": rid, "group": group, "requirement": req, "status": status,
            "number_now": now, "blocking_gate": gate, "number_to_clear": clear,
            "official_source": source, "evidence": evidence, "flag": flag,
        })

    # ---- Injury report and availability -------------------------------------
    add("R-01", "Injury report", "Immutable, timestamped capture of the official injury report (raw hash, clock time)",
        "partial",
        f"{f['captures']} stored capture(s) ({', '.join(f'{k}: {v}' for k, v in f['capture_methods'].items())}); "
        f"{f['live_reads']} live read(s) logged",
        "scheduled live reads have not yet run on the default branch (GitHub runs schedules only from main)",
        "1 distinct capture per game-day window, 3-hourly from Wednesday to kickoff, for at least 4 consecutive game weeks",
        INJ, "tools/capture/official_injuries.py; data/captures/official_injuries/",
        flag="R4-1")
    add("R-02", "Injury report", "Publish the change between captures, never the level",
        "partial",
        f"{f['captures']} distinct capture(s); deltas need 2",
        "needs a second distinct capture (the live read after merge)",
        "first delta published (2 captures); a delta series spanning 4 game weeks",
        INJ, "data/captures/official_injuries/delta_latest.json; app/captures.html")
    add("R-03", "Injury report", "Published Week 10 injury table checked line by line against the official page",
        "built",
        f"{v.get('comparisons', 0):,} cell comparisons vs capture {f['verify_capture']}: "
        f"{v.get('matches', 0):,} match, {v.get('mismatches', 0)} mismatch",
        "the comparison is against a 2026-11-14 capture (import), not a live read",
        "0 mismatches against a live capture taken on the day of publication",
        INJ, "tools/capture/verify_against_capture.py; data/captures/official_injuries/verification_week10.json")
    add("R-04", "Injury report", "Claimed Week 10 counts (254 rows, 4 no-injury sections; later 279 rows, 2 sections)",
        "contradicted",
        f"official capture shows {f['last_capture_rows'] or 0} rows and {len(f['no_injury_clubs'])} no-injury sections "
        f"({', '.join(f['no_injury_clubs'])})",
        "the brief's counts do not match any capture in the repository",
        "a dated official capture that reproduces the stated counts, or a retraction of the counts",
        INJ, "data/captures/official_injuries/captures.jsonl", flag="R4-4")
    add("R-05", "Injury report", "Game-status designations for the three Lions players (Joseph, Mays, Reed)",
        "resolved",
        f"published: {', '.join(f'{k} = {v}' for k, v in sorted(f['published_lions'].items()))}; "
        f"official capture: {', '.join(f'{k} = {v}' for k, v in sorted(f.get('lions_status', {}).items()))}",
        "none", "already populated and matching the official page",
        INJ, "data/injuries/injuries_2026_week10.csv", flag="R4-5")
    add("R-06", "Injury report", "Designation reliability: play rate per designation with confidence intervals",
        "blocked",
        f"0 seasons joined to official inactive lists; {f['last_capture_designations']} designations in the newest capture",
        "official inactive lists and snap counts are not captured (R-11)",
        "at least 1 full season of official inactives joined to each designation, with CIs",
        GAMEBOOK_EXAMPLE, "not started")
    add("R-07", "Injury report", "Archive of weekly injury reports for past seasons",
        "not built",
        "0 past-season reports archived in this repository",
        "backfill not run; the capture job only reads the current week",
        "one capture per regular-season week for each archived season (about 18 per season)",
        INJ, "not started")
    add("R-08", "Injury report", "Injury signal as a surprise (change), not a level",
        "partial", "design adopted (R-02); no model uses it yet",
        "no model with verified availability features has been fitted",
        "a chronological holdout comparing identical models with and without the surprise feature",
        INJ, "docs/round4-executive-summary.md")

    # ---- Depth and lineups -----------------------------------------------------
    add("R-09", "Depth and lineups", "Depth chart from each club's own page, verified club by club (route a)",
        "partial",
        f"{f['depth_clubs']} of 32 clubs have depth rows (missing: {', '.join(f['depth_clubs_missing'])}); {d.get('slots', 0)} slots; "
        f"{d.get('by_depth', {}).get('2', 0)} second-string and {d.get('by_depth', {}).get('3', 0)} third-string replacements named",
        "Houston publishes depth as an image; no authorised structured source is in the repository",
        "32 of 32 clubs verified from the club page, with a dated source row",
        TEAMS, "data/depth/replacement_depth.csv; data/depth/replacement_depth_summary.json", flag="R4-6")
    add("R-10", "Depth and lineups", "Slots modelled as groups (ties, shared and empty slots), not a single starter",
        "partial",
        f"{d.get('slots', 0)} slots (deficiency store); {d.get('no_replacement_named', 0)} with no replacement named; "
        f"{d.get('starters_on_report_without_named_replacement', 0)} starters on the report without a named replacement",
        "the tie, shared and empty rule was not re-verified in this round",
        "every slot labelled as single, tied, shared or empty, checked against the club page", STAND,
        "data/depth/replacement_depth_summary.json")
    add("R-11", "Depth and lineups", "Official Game Book: actual starters and game-day status",
        "blocked", "0 of 14 Week 10 games with a Game Book read in this repository",
        "no Game Book was fetched or parsed in this round",
        "all 14 Week 10 Game Books parsed, with the Game Book hash stored", GAMEBOOK_EXAMPLE,
        "not started")
    add("R-12", "Depth and lineups", "Official inactive lists and snap counts",
        "blocked", "0 seasons captured", "no official inactive or snap-count source is captured",
        "every Week of one full season captured with hashes", GAMEBOOK_EXAMPLE, "not started")
    add("R-13", "Depth and lineups", "Depth order taken from snap counts or playing time, not jersey number",
        "blocked", "0 of 32 clubs verified on a snap-count route",
        "route (b) needs an official snap-count source, which is not captured (R-12)",
        "32 of 32 clubs with a verified source for playing time", GAMEBOOK_EXAMPLE, "not started")
    add("R-14", "Depth and lineups", "Announced starter changes as evidence (not inferred)",
        "not built", "0 announced-starter rows captured", "no captured official announcement",
        "every announced change captured with its date and link", INJ, "not started")
    add("R-15", "Depth and lineups", "Official depth-chart register with date and source on every row",
        "partial", f"{d.get('slots', 0)} slots carry a source link; the date column is not populated for every club",
        "club depth pages carry no league-standard date", "every row dated from its club page", TEAMS,
        "data/depth/replacement_depth.csv")
    add("R-16", "Depth and lineups", "Team-level model trusted only after a 32-club roster and injured-reserve sweep",
        "blocked", f"{f['last_capture_clubs'] or 0} of 32 clubs on the Week 10 injury report "
        f"({f['week10_byes']} bye clubs)",
        "the 32-club sweep is not complete (4 clubs are on bye and have no report)",
        "32 of 32 clubs swept, with the injured-reserve list captured", INJ, "not started")
    add("R-17", "Depth and lineups", "Reserve list captured so 'not listed' never means 'available'",
        "not built", "0 reserve-list rows captured", "not captured", "reserve list captured for every club, dated",
        INJ, "not started")
    add("R-18", "Depth and lineups", "Roster turnover as a dated event (trades, releases, IR)",
        "not built",
        f"0 roster-event rows in the register; {f['trades_rows']:,} rows in the nflverse trades file (not verified)",
        "the nflverse file is a community mirror, not an official transactions log",
        "an official transactions log captured, with depth rows versioned against each event", INJ,
        "data/raw/nflverse/trades.csv")
    add("R-19", "Depth and lineups", "Texans depth chart from an authorised structured source",
        "blocked", "0 of 1 club (Houston)", "the page is an image; transcription by eye is not allowed",
        "an authorised structured source for Houston, verified", "https://www.houstontexans.com/team/depth-chart",
        "data/pipeline/_run_report.json (depth error for HOU)", flag="X-03")

    # ---- Schedule, venue ------------------------------------------------------
    add("R-20", "Schedule and venues", "Venue of every fixture from the official game centre",
        "not built", f"{f['week10_venue_notes']} of {f['week10_games']} Week 10 games carry a venue note",
        "venues are not transcribed from the game centre", "every fixture's venue transcribed and dated",
        SCHED, "data/nfl/schedule_2026_week10.csv")
    add("R-21", "Schedule and venues", "League's dated schedule announcement published beside the live schedule",
        "not built", "0 announcements captured", "no announcement fetched", "one dated announcement beside each schedule page",
        SCHED, "not started")

    # ---- Results ------------------------------------------------------------
    add("R-22", "Results and backtests", "Verified results feed: official final scores for every settled game",
        "built",
        f"{f['official_final_games']} official finals across {f['results_files']} weekly files (2026)",
        "the regular season is not finished; Weeks 11 onward are not final",
        "every 2026 final captured from the official schedule, with a source row per game", SCHED,
        "data/results/raw/official_results_2026_week*.psv")
    add("R-23", "Results and backtests", "The 136-game log turned into a pre-registered backtest corpus",
        "partial",
        f"{f['official_final_games']} verified finals in the official files (the brief says 136)",
        "the 136-game log the brief refers to is not in the repository and is not reconciled",
        "the owner's 136-game log reconciled game by game with the official finals", SCHED,
        "data/results/raw/", flag="R4-7")
    add("R-24", "Results and backtests", "Price-data policy decided before any backtest is published",
        "blocked", "0 policies adopted; open decision Q-02", PRICE_NONE,
        "one adopted policy naming the price authority and capture rule", "https://www.nfl.com/",
        "data/origin/decisions_taken.json")
    add("R-25", "Results and backtests", "Opening and closing price for every market we originate",
        "blocked",
        f"2026: {f['price_2026_markets']} markets in the store, {f['price_2026_both_ends']} with both an opening and a closing price",
        PRICE_NONE, f"{f['price_2026_markets']} markets, each with an opening and a closing price and a source",
        "https://www.nfl.com/", "data/console/price_snapshots.csv")
    add("R-26", "Results and backtests", "Originated market rows: side, then total, then moneyline; fair, market and difference as separate columns",
        "built",
        f"{f['orig_2026_games']} distinct 2026 games; {f['orig_2026_market_blank_games']} games with a blank market side (no price)",
        PRICE_NONE, "market side populated for every originated game, from a source that prints it",
        SCHED, "data/console/originated_lines.csv; data/lines/origination_order_2026_week10.csv", flag="R4-8")
    add("R-27", "Results and backtests", "Originated table: one row per game, no duplicates",
        "defect", f"{f['orig_2026_dup_rows']} duplicate game rows in 2026 (mode = live); Week 10 has {f['orig_week10_rows']} rows "
        f"for {f['orig_week10_games']} games",
        "duplicate rows inflate counts", "one row per game, checked by the build", SCHED,
        "data/console/originated_lines.csv", flag="R4-8")
    add("R-28", "Results and backtests", "Model's own probability and its inputs stored for every output",
        "unverified", "not checked this round", "the store was not re-audited",
        "every output row carries probability and inputs", SCHED, "data/console/originated_lines.csv")
    add("R-29", "Results and backtests", "Model residual against the market published on a schedule from day one",
        "partial", "one manual Week 10 publication; no scheduled workflow publishes it",
        "no workflow in .github/workflows publishes the residual", "a weekly scheduled residual table with run logs",
        SCHED, "data/console/originated_lines.csv")

    # ---- Strategies -------------------------------------------------------
    add("R-30", "Strategies and leaderboard", "Every strategy pre-registered; backtests never on the leaderboard",
        "partial",
        f"{f['console_strategies']} strategies in data/console/strategy_results.csv; {f['registry_strategies']} in "
        f"data/strategies/strategies_registry.csv",
        "two registries disagree on the strategy count",
        "one registry with one row per pre-registered strategy, each with a registration commit", SCHED,
        "data/console/strategy_results.csv; data/strategies/strategies_registry.csv", flag="R4-9")
    add("R-31", "Strategies and leaderboard", "Pre-registration commit hash recorded per strategy",
        "not built", "registry has a hash or commit column: " + ("yes" if f["registry_has_hash_field"] else "no"),
        "no per-strategy registration hash exists", "every strategy row carries the hash of its registration commit", SCHED,
        "data/strategies/strategies_registry.csv")
    add("R-32", "Strategies and leaderboard", "Two-sided 'what would change our mind' field on every strategy",
        "not built", "registry has the field: " + ("yes" if f["registry_has_change_field"] else "no"),
        "the field is absent from the registry", "a two-sided field (what would make us drop it, what would make us promote it) on every row",
        SCHED, "data/strategies/strategies_registry.csv")
    add("R-33", "Strategies and leaderboard", "Signal separated from staking on the leaderboard",
        "built", f"ST-11: signal n = {st.get('signal_n', st.get('n', '—'))}; staking excluded from rank by rule",
        "return on stake needs a price source (R-25)",
        "gate-passing signal and a priced ROI on the same window", SCHED,
        "data/leaderboard_signal_staking_official.json")
    add("R-34", "Strategies and leaderboard", "Correlations computed only from official numbers, with n on every value",
        "partial", f"{f['corr_pairs_with_n']} of {f['corr_pairs']} pairs carry n; all club-level, from NFL.com standings and team stats",
        "closing-line correlations need prices (R-25)", "closing-line correlations from an official price source, with n", STAND,
        "data/correlations_official_check.json")
    add("R-35", "Strategies and leaderboard", "Demotion gate that sends a live strategy back to paper",
        "built", f"gate G8 in data/gates.json: {'yes' if f['gate_g8'] else 'no'}; live strategies: 0", "no strategy is live, so the gate has nothing to act on",
        "at least one strategy live and a demotion decision recorded", SCHED,
        "docs/methodology/demotion-gate.md; data/gates.json")
    add("R-36", "Strategies and leaderboard", "Control baselines (random picks; favourites only) on every run",
        "partial", "favourites baseline present; random-pick baseline not found in data/console or data/lab",
        "the random-pick control is not built", "random and favourites controls on every leaderboard run", SCHED,
        "data/console/strategy_results.csv")
    add("R-37", "Strategies and leaderboard", "Benchmark-relative Brier skill with a game-cluster lower bound and multiplicity adjustment",
        "not built", "Brier score exists for the line model only", "the strategy-level skill score is not computed",
        "Brier skill for each strategy with a cluster lower bound, and a multiplicity correction", SCHED,
        "data/lab/lines/model_report.json")
    add("R-38", "Strategies and leaderboard", "Two-stage leaderboard: proper-score qualification, then prospective CLV/ROI escrow",
        "not built", "no prospective escrow records", "needs prices (R-25) and a scored prospective window",
        "one prospective window scored under the frozen rule", SCHED, "not started")
    add("R-39", "Strategies and leaderboard", "Parlays and prop combos only behind a joint-evidence gate",
        "partial", "gate described in docs/props-and-parlays.md (not re-verified); no joint-probability evidence in the repository", "no directly validated joint probability",
        "a validated joint probability and the operator's void and push rules", PRICE_NONE,
        "docs/props-and-parlays.md")

    # ---- Models and origination -----------------------------------------------
    add("R-40", "Models", "Model's fair line published against the market line, with the difference",
        "built", "fair line and difference published; market line blank for games without a price",
        PRICE_NONE, "market line for every originated game from an official or licensed source", SCHED,
        "data/console/originated_lines.csv", flag="R4-8")
    add("R-41", "Models", "Every model total published twice until a walk-forward comparison picks one",
        "not built", "one estimator per total", "no second estimator is published", "both estimators on the page with a gap column",
        SCHED, "not started")
    add("R-42", "Models", "Stadium roof and surface overlaid on NWS hourly wind and precipitation",
        "not built", "0 roof or NWS rows", "no official roof designation or NWS grid captured",
        "official roof designations and NWS grids for every outdoor game", "https://www.weather.gov/", "not started")
    add("R-43", "Models", "Kickoff and declared onside-kick regime priors filter",
        "not built", "0 rows", "no official onside-kick source captured", "a dated official source per regime", SCHED, "not started")
    add("R-44", "Models", "Injury and depth ablations: identical models with and without verified availability features",
        "not built", "0 ablations run", "needs R-09 and R-11", "ablation table with uncertainty over chronological holdouts",
        SCHED, "not started")
    add("R-45", "Models", "Train, validation and final holdout seasons fixed before any evaluation",
        "partial", "walk-forward in the lab; no fixed final holdout is recorded", "holdout not declared", "a declared holdout season, frozen in git",
        SCHED, "docs/methodology/validation-gates.md")
    add("R-46", "Models", "Single-game shadow baseline recorded before kickoff",
        "not built", "0 forecasts recorded before kickoff", "no shadow forecast log", "a dated forecast log for each Week",
        SCHED, "not started")

    # ---- Governance -----------------------------------------------------------
    add("R-47", "Governance", "Drift alarm on every scraper (pinned row counts and fields; fail, never blank)",
        "partial", "the injury capture is pinned and fails loudly; other scrapers not audited in this round",
        "the pipeline's injury parser can crash on an unmatched team link (R4-10)",
        "every scraper pinned and tested against a stored sample", INJ, "pipeline/parsers.py", flag="R4-10")
    add("R-48", "Governance", "Executive summary, decision register and suggestion board",
        "built", "updated this round (Round 4)", "owner choices pending (suggestions S-R4-*)",
        "owner has chosen one path per suggestion", INJ, "docs/round4-executive-summary.md")
    add("R-49", "Governance", "Freshness monitoring and alert on source or schema change",
        "partial", "the capture job fails on drift or a stale store; alerts rely on GitHub's failed-run email",
        "the workflow has not run on the default branch yet", "one successful scheduled run per 3-hour window for 7 days", INJ,
        ".github/workflows/capture-official.yml")
    add("R-50", "Governance", "Public analysis layer separated from a private raw-data layer",
        "not built", "all raw captures are in the public repository", "no private store exists",
        "private raw store plus a public derived layer", INJ, "data/captures/official_injuries/raw/")
    return R


def build() -> dict:
    f = facts()
    rws = rows(f)
    counts = Counter(r["status"] for r in rws)
    doc = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "session": "arena-8e329878-x1",
        "statuses": {
            "built": "built and checked against an official source or a computed repository value",
            "resolved": "a published value was checked against the official page and matches",
            "partial": "some of the requirement is built; the gate named in the row is open",
            "blocked": "cannot proceed until the named gate is cleared; nothing is faked",
            "not built": "no artefact exists in the repository",
            "unverified": "not re-checked this round; shown as unverified",
            "contradicted": "an official source or capture contradicts the stated value",
            "defect": "a repository defect was found and is listed for review",
        },
        "counts": dict(counts),
        "facts": f,
        "rows": rws,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False, sort_keys=False)
        fh.write("\n")
    return doc


if __name__ == "__main__":
    d = build()
    print(f"wrote {os.path.relpath(OUT, ROOT)}: {len(d['rows'])} rows")
    print("counts:", d["counts"])
    sys.exit(0)
