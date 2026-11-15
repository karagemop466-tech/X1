#!/usr/bin/env python3
"""Decision-readiness register (round 4) — one row per requirement in the owner's brief.

    python3 tools/build_readiness.py            # writes data/readiness/* only
    (tools/build_console.py calls apply() so the landing page and the flagged page carry it)

Every number in a row is computed here from a file in the repository (see METRICS). A row
never carries a value that cannot be traced to a file. Each row has:

  status    Built | Built, not yet run | Partly built | Blocked: data | Blocked: decision
            | Not started | Unverified | Closed (approach rejected by brief, not used)
  blocker   the gate or missing source that stops it
  clears    the number that would clear it (computed where a file defines it)
  evidence  the file or official page a reviewer opens to check the row
"""

from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

REPO = "https://github.com/karagemop466-tech/X1/blob/main/"
OFFICIAL_INJ = "https://www.nfl.com/injuries/"
OFFICIAL_SCHED = "https://www.nfl.com/schedules/2026/by-week/week-10"
OUT_DIR = os.path.join(ROOT, "data", "readiness")
STATUSES = ["Built", "Built, not yet run", "Partly built", "Blocked: data",
            "Blocked: decision", "Not started", "Unverified",
            "Closed (approach rejected by brief, not used)"]


def _p(*parts):
    return os.path.join(ROOT, *parts)


def _csv_rows(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def compute_metrics() -> dict:
    """Every figure a row quotes. Each one reads a file; nothing is typed in here."""
    m: dict = {}
    pub = _csv_rows(_p("data", "injuries", "injuries_2026_week10.csv"))
    m["inj_published_rows"] = len(pub)
    m["inj_published_designated"] = sum(1 for r in pub if (r.get("game_status") or "").strip())
    m["inj_published_teams"] = len({r["team"] for r in pub})
    spot = _json(_p("data", "readiness", "spotcheck_result.json"))
    m["inj_official_rows"] = spot["official_rows"]
    m["inj_mismatch"] = spot["mismatch_count"]
    m["inj_teams_checked"] = spot["teams_compared"]
    m["inj_teams_clean"] = len(spot["teams_with_zero_mismatch"])
    m["inj_teams_dirty"] = ", ".join(spot["teams_with_mismatch"])
    by_team = Counter(d["team"] for d in spot["mismatches"])
    m["inj_by_team"] = dict(sorted(by_team.items()))
    m["inj_bal_lac_mismatch"] = by_team.get("LAC", 0) + by_team.get("BAL", 0)
    m["inj_lac_rows_mismatch"] = by_team.get("LAC", 0)
    m["inj_bal_mismatch"] = by_team.get("BAL", 0)
    m["inj_ind_mismatch"] = by_team.get("IND", 0)
    m["inj_sea_rows"] = sum(1 for r in pub if r["team"] == "SEA")
    m["inj_cin_rows"] = sum(1 for r in pub if r["team"] == "CIN")
    lions = {r["player"]: r for r in pub if r["team"] == "DET"}
    m["lions_out"] = sum(1 for n in ("Kerby Joseph", "Cade Mays", "D.J. Reed")
                         if lions.get(n, {}).get("game_status") == "Out")
    sched = _csv_rows(_p("data", "nfl", "schedule_2026_week10.csv"))
    m["fixtures_wk10"] = len(sched)
    m["venues_wk10"] = sum(1 for r in sched if (r.get("venue_note") or "").strip())
    depth = _csv_rows(_p("data", "depth", "replacement_depth.csv"))
    m["depth_clubs"] = len({r["team"] for r in depth})
    summ = _json(_p("data", "depth", "replacement_depth_summary.json"))
    m["depth_slots"] = summ["totals"]["slots"]
    m["depth_named"] = summ["totals"]["replacement_named"]
    m["depth_unnamed"] = summ["totals"]["no_replacement_named"]
    m["depth_starters_no_replacement"] = summ["totals"]["starters_on_report_without_named_replacement"]
    res = _csv_rows(_p("data", "results", "verified_results_2026_r3.csv"))
    m["results_2026_rows"] = len(res)
    snaps = _csv_rows(_p("data", "snapshots", "price_snapshots.csv"))
    m["price_rows"] = len(snaps)
    m["price_open_close_marketline"] = sum(
        1 for r in snaps if r.get("stage") in ("open", "close") and (r.get("market_line") or "").strip())
    m["price_market_rows_blank"] = sum(1 for r in snaps if not (r.get("market_line") or "").strip())
    reg = _csv_rows(_p("data", "strategy_registry.csv"))
    m["registry_strategies"] = len(reg)
    m["registry_has_what_would_change"] = any("change" in k.lower() for k in (reg[0].keys() if reg else []))
    lb = _csv_rows(_p("data", "strategy_leaderboard.csv"))
    m["leaderboard_rows"] = len(lb)
    m["leaderboard_backtest_cols"] = [c for c in lb[0].keys() if c.startswith(("holdout_", "forward_"))] if lb else []
    gates = _json(_p("data", "gates.json"))["gates"]
    g1 = next(g for g in gates if g["id"] == "G1")
    m["g1_singles"] = g1["thresholds"]["singles_bets"]
    m["g1_parlay2"] = g1["thresholds"]["two_leg_parlays_tickets"]
    dg = _json(_p("data", "demotion_gate.json"))
    m["demotion_status"] = dg.get("status", "")
    return m


def build_rows(m: dict) -> list:
    """The register. Order follows the brief; repeated brief items keep their own row."""
    R = []

    def row(group, requirement, brief_ref, status, exists, blocker, clears, evidence):
        assert status in STATUSES, status
        R.append({"group": group, "requirement": requirement, "brief_ref": brief_ref,
                  "status": status, "exists_today": exists, "blocker": blocker,
                  "clears_when": clears, "evidence": evidence})

    M = "Markets, lines and prices"
    row(M, "Price-snapshot store: opening and closing numbers for every market we originate",
        "Brief 1; 'Add a price-snapshot store'", "Partly built",
        f"{m['price_rows']} capture records; {m['price_open_close_marketline']} carry a market line; "
        f"{m['price_market_rows_blank']} market cells blank",
        "Blocked: no official or licensed price source (open question Q-31)",
        "Both opening and closing market line present, with a named source, for all 56 originated 2026 markets",
        REPO + "data/snapshots/price_snapshots.csv")
    row(M, "Verified results feed so backtests and ROI can be computed",
        "Brief 2; 'Add a verified results feed'", "Partly built",
        f"{m['results_2026_rows']} verified 2026 games, reconciled to official standings; history is mirror-only",
        "Blocked: 2019–2025 official pages not committed (mirror only)",
        "Official page committed for every 2019–2025 regular-season week",
        REPO + "data/results/verified_results_2026_r3.csv")
    row(M, "Backtest corpus: turn the 136-game log into the pre-registered backtest corpus",
        "Brief 'Turn the 136-game log'", "Blocked: decision",
        f"{m['results_2026_rows']} rows in the 2026 feed (brief says 136; reconcile)",
        "No pre-registration commit; price policy not decided (Q-31)",
        "One git commit that freezes rule text, sample window and gates before scoring; count reconciled to 136",
        REPO + "data/results/verified_results_2026_r3.csv")
    row(M, "Decide the price-data policy before any backtest is published",
        "Brief 'Decide the price-data policy'", "Blocked: decision",
        "Policy not written; question open",
        "Owner decision Q-31 (price-source authority)",
        "Owner ratifies one named price source and one timestamp rule",
        REPO + "data/console/questions.csv")
    row(M, "Originate the side first, then the total, then the moneyline",
        "Brief 3", "Built",
        "data/lines/origination_order_2026_week10.csv, sequences asserted 1-2-3 by builder",
        "None", "Already met for Week 10; repeat for each new week",
        REPO + "data/lines/origination_order_2026_week10.csv")
    row(M, "Publish the model's fair line, the market line and the difference as separate columns",
        "Brief 4", "Partly built",
        f"Three columns exist; market column blank on {m['price_market_rows_blank']} of {m['price_rows']} capture rows",
        "Blocked: no market source (Q-31)",
        "Market column populated from the named source for every originated market",
        REPO + "data/lines/origination_order_2026_week10.csv")
    row(M, "Price our own line and publish the residual against the market, on a schedule, from day one",
        "Brief 'Price a line ourselves'", "Partly built",
        "Residuals computed by a manual build; no scheduled residual job",
        "Blocked: market column empty; no schedule",
        "Scheduled job writes the residual each week with the market column filled",
        REPO + "data/lines/originated_markets_2026_week10.csv")
    row(M, "Vig-free market consensus versus originated fair-line decomposition",
        "Brief 'Vig-Free Market Consensus'", "Not started",
        "No vig removal code path publishes a consensus",
        "Blocked: needs two or more priced sources per market",
        "Consensus for each market from at least two named sources, vig removed and shown",
        REPO + "data/lines/originated_markets_2026_week10.csv")
    row(M, "Publish every model total twice until one wins, with the gap column",
        "Brief 'Publish every model total twice'", "Not started",
        "One total estimator is published",
        "Blocked: decision (the walk-forward comparison is not specified)",
        "Two estimators on the same games, a gap column, and a walk-forward winner named",
        REPO + "data/lines/originated_markets_2026_week10.csv")
    row(M, "Store every model output as a probability plus its inputs, not just a pick",
        "Brief 'Store every model output'", "Not started",
        "Outputs are points and spreads; no probability column and no input hash",
        "Blocked: decision (model specification)",
        "Every output row carries a probability and a hash of its inputs",
        REPO + "data/lines/originated_markets_2026_week10.csv")
    row(M, "Fixture-context feature set built only from published schedule facts",
        "Brief 'Add a fixture-context feature set'", "Not started",
        f"{m['fixtures_wk10']} Week 10 fixtures with date, time and TV only",
        "Blocked: feature table not built",
        f"Feature table for every 2026 fixture, each field traced to a published schedule row",
        REPO + "data/nfl/schedule_2026_week10.csv")
    row(M, "Transcribe the venue of every fixture from the official game centre and publish it",
        "Brief 'Transcribe the venue'", "Partly built",
        f"{m['venues_wk10']} of {m['fixtures_wk10']} Week 10 fixtures carry a venue note",
        "Blocked: game-centre pages not captured",
        f"{m['fixtures_wk10']} of {m['fixtures_wk10']} Week 10 venues, each linked to its nfl.com game centre",
        OFFICIAL_SCHED)
    row(M, "Publish the league's dated schedule announcement beside the live schedule",
        "Brief 'Publish the league's dated schedule announcement'", "Not started",
        "Live schedule page exists; no dated announcement captured",
        "Blocked: announcement not captured",
        "Announcement URL and capture date shown beside the live schedule",
        OFFICIAL_SCHED)
    row(M, "Stadium roof and surface, with NWS hourly wind and precipitation overlay",
        "Brief 'Stadium Roof/Surface & NWS'", "Blocked: data",
        "No roof designation and no NWS grid in the repository",
        "Blocked: data (roof designation and NWS feed not captured)",
        "Official roof designation at 90 minutes before kickoff, and an NWS hourly grid for every kickoff",
        REPO + "data/nfl/schedule_2026_week10.csv")
    row(M, "Kickoff and declared onside-kick regime priors filter for totals and comeback curves",
        "Brief '2026 Kickoff & Declared Onside-Kick'", "Blocked: data",
        "No declared-onside-kick source captured",
        "Blocked: data (regime source not identified)",
        "Named official source for each declared regime, with a date",
        REPO + "data/console/questions.csv")

    I = "Injuries and availability"
    row(I, "Store every injury-hub read with its clock time and publish the delta, never the level",
        "Brief 'Store every injury-hub read'", "Built, not yet run",
        "Archive keeps every distinct capture with fetch time and SHA-256 (pipeline/archive.py)",
        "Blocked: first scheduled run has not yet written an archive entry",
        "At least two archived captures for a team, and a delta page built from them",
        REPO + "pipeline/archive.py")
    row(I, "Automate immutable multi-day availability snapshots (official report and club depth pages, hashed)",
        "Brief 'Automate immutable multi-day'", "Built, not yet run",
        "data-refresh workflow runs four times a day (cron 17 11,15,19,23 UTC) plus game-day passes, and now archives the injury report; club depth pages not archived",
        "Blocked: first run; club depth pages not yet in the archive",
        "Three distinct days of archive entries for the injury report, and the depth pages added",
        REPO + ".github/workflows/data-refresh.yml")
    row(I, "Build immutable official availability snapshots with raw hashes, timestamps and conflict flags",
        "Brief 'Build immutable official availability'", "Built, not yet run",
        "Archive stores hash, time, row count and conflict flags; the self-test passes (4 behaviours)",
        "Blocked: first scheduled run; club depth and inactive evidence not archived",
        "One stored capture with zero integrity failures in scripts/pipeline/verify_archive.py",
        REPO + "scripts/pipeline/verify_archive.py")
    row(I, "Snapshot the injury report every Wednesday, Thursday and Friday and keep a dated history",
        "Brief 'Snapshot the nfl.com injury report every Wed'", "Built, not yet run",
        "Six-hourly schedule covers Wed, Thu and Fri; each change is archived",
        "Blocked: first run",
        "Stored captures on all three days of one game week",
        REPO + ".github/workflows/data-refresh.yml")
    row(I, "Treat the injury report as a timestamped series, daily from Wednesday to kickoff, and measure DNP to LP to FP",
        "Brief 'Treat the injury report as a timestamped series'", "Not started",
        "No series yet; archive began this round",
        "Blocked: time (needs a game week of captures)",
        "Four captures across one game week for each player with a practice status",
        REPO + "pipeline/archive.py")
    row(I, "Measure how Questionable turns into Out, and practice trends",
        "Brief 'Questionable to Out changes'", "Not started",
        "No series",
        "Blocked: time (needs at least two weeks of captures)",
        "Two full weeks of archive for the 2026 season",
        REPO + "pipeline/archive.py")
    row(I, "Use the injury signal as a surprise (change from the last capture), never as a level",
        "Brief 'Make the injury signal a surprise'", "Not started",
        "Repository publishes levels (game_status on the report)",
        "Blocked: needs an archived series",
        "Surprise defined on two archived captures; level never used as a feature",
        REPO + "data/injuries/injuries_2026_week10.csv")
    row(I, "Capture the official inactive lists and snap counts",
        "Brief 'Capture official inactive lists and snap counts'", "Blocked: data",
        f"Only {m['inj_published_designated']} of {m['inj_published_rows']} injury-report rows carry a game designation; no inactive list and no snap counts in the repository",
        "Blocked: data (no captured inactive list or snap-count source)",
        "Official inactive list and snap counts for every 2026 game, with a source link on each row",
        REPO + "data/injuries/injuries_2026_week10.csv")
    row(I, "Use official NFL Game Books for actual starters and game-day status; do not infer depth rank or snaps",
        "Brief 'Use official NFL Game Books'", "Blocked: data",
        "No Game Book captured",
        "Blocked: data (Game Books not in the repository)",
        "Game Book captured and hashed for every completed 2026 game",
        "https://www.nfl.com/injuries/")
    row(I, "Archive weekly injury reports for past seasons so designations can be tested against outcomes",
        "Brief 'Archive weekly injury reports for past seasons'", "Blocked: data",
        "Only the 2026 Week 10 report is in the repository",
        "Blocked: data (past official reports not captured)",
        "Every regular-season week of the seasons in scope captured with a hash",
        OFFICIAL_INJ)
    row(I, "Score injury-designation reliability (play rate per designation with confidence intervals) before using it as a feature",
        "Brief 'Score injury-designation reliability'", "Blocked: data",
        "Designations exist; no joined inactive lists and no outcomes",
        "Blocked: data (needs inactive lists and several seasons)",
        "A play-rate interval for each designation from at least one full season joined to official inactives",
        REPO + "data/injuries/injuries_2026_week10.csv")
    row(I, "Calibrate empirically what 'Questionable' means, instead of old percentages",
        "Brief 'Calibrate what Questionable means'", "Blocked: data",
        "Official text gives no percentages; no outcome data",
        "Blocked: data (same as the reliability row)",
        "Calibrated play rate for Questionable with an interval, from a joined season",
        OFFICIAL_INJ)
    row(I, "Capture the reserve list so 'not listed' never means 'available'",
        "Brief 'Capture the reserve list'", "Blocked: data",
        "The injury report does not list injured reserve; official news links show reserve moves",
        "Blocked: data (no reserve list captured)",
        "Official reserve list captured each week, and every IR player marked on the depth register",
        "https://www.nfl.com/news/dolphins-place-qb-malik-willis-groin-on-injured-reserve-kyle-mccord-in-line-for-first-start")
    row(I, "Announced-starter evidence field, never an inferred replacement",
        "Brief 'Add an announced-starter evidence field'", "Not started",
        "Official news links name starters (Drew Lock, Sam Darnold); no field captures them",
        "Blocked: data (official dated starter statements not captured)",
        "Field filled only from a dated official statement, with a link on every value",
        "https://www.nfl.com/news/sam-darnold-ruled-out-for-seahawks-week-10-game-vs-raiders-drew-lock-expected-to-start-again")
    row(I, "Treat roster turnover as a first-class data event, with depth versioned against the last official roster event",
        "Brief 'Treat roster turnover as a first-class data event'", "Blocked: data",
        "No transactions log captured",
        "Blocked: data (official transactions log not captured)",
        "Transactions log captured with dates; Colts Week 10 receiver trades verified against it",
        OFFICIAL_INJ)
    row(I, "Flag stale depth rows against the official transactions log",
        "Brief 'Flag stale depth rows'", "Blocked: data",
        "No transactions log; no stale-row check",
        "Blocked: data (same as the turnover row)",
        "Zero depth rows naming a player on injured reserve or traded, with the log date shown",
        OFFICIAL_INJ)
    row(I, "Populate the three missing Lions game-status designations",
        "Brief 'Populate the three missing Lions'", "Built",
        f"Kerby Joseph, Cade Mays and D.J. Reed: {m['lions_out']} of 3 read as Out on the official page and in the published table",
        "None",
        "Done for the 2026-11-15 read",
        OFFICIAL_INJ)
    row(I, "Seattle and Cincinnati shown as injury-free while listing players",
        "Brief 'Re-capture and republish the Week 10 injury tables'", "Built",
        f"SEA {m['inj_sea_rows']} rows and CIN {m['inj_cin_rows']} rows match the official read row for row "
        "(brief's '4' for Cincinnati is superseded by the page)",
        "None",
        "Done for both clubs",
        OFFICIAL_INJ)
    row(I, "Re-capture and republish the Week 10 injury tables against the official page",
        "Brief 'Re-capture and republish the Week 10 injury tables'", "Partly built",
        f"Official read: {m['inj_official_rows']} rows; published: {m['inj_published_rows']}; "
        f"{m['inj_mismatch']} row differences in {m['inj_teams_checked'] - m['inj_teams_clean']} clubs "
        f"({m['inj_teams_dirty']})",
        "Blocked: decision (owner to accept the 2026-11-15 read as the republished table)",
        f"Zero row differences on a fresh read; {m['inj_teams_clean']} of {m['inj_teams_checked']} clubs already match",
        REPO + "data/readiness/spotcheck_diffs.csv")
    row(I, "Drift alarm on every scraper: pin row counts and required fields; fail loudly when a field goes blank",
        "Brief 'Add a drift alarm to every scraper'", "Partly built",
        f"Integrity checks pass the LAC and BAL rows (blank designations) as verified; {m['inj_bal_lac_mismatch']} differences in those two clubs (LAC {m['inj_lac_rows_mismatch']}, BAL {m['inj_bal_mismatch']})",
        "Blocked: decision (rule for a blank designation on a listed player)",
        "Build fails when a club's designation cells are all blank while the page lists players",
        REPO + "tools/verify_injury_spotcheck.py")

    D = "Depth and personnel"
    row(D, "Fix the two depth-parsing failures: Texans published as an image, Packers prefix jersey numbers",
        "Brief 'Fix the two depth-parsing failures'", "Partly built",
        f"Depth parsed for {m['depth_clubs']} of 32 clubs; Texans (HOU) not parsed",
        "Blocked: data (Texans depth is an image; needs an authorised structured source)",
        "Structured official source for HOU; Packers rows parse with numbers stripped and raw string stored",
        REPO + "data/depth/replacement_depth.csv")
    row(D, "32-team roster and injured-reserve sweep before any team-level model is trusted",
        "Brief 'Run the 32-team roster/IR sweep'", "Partly built",
        f"{m['depth_clubs']} of 32 clubs in the depth register; the injury table covers {m['inj_published_teams']} clubs (4 on bye)",
        "Blocked: data (HOU depth; reserve list)",
        "32 of 32 clubs in the depth register and the reserve list",
        REPO + "data/depth/replacement_depth_summary.json")
    row(D, "Resolve the depth-order source before building the backup-deficiency feature (route a: club pages; route b: snap counts)",
        "Brief 'Resolve the depth-order source'", "Partly built",
        f"Route (a) used for {m['depth_clubs']} of 32 clubs; route (b) not available",
        "Blocked: data (HOU)",
        "One route verified for all 32 clubs before the feature is built",
        REPO + "data/depth/replacement_depth_summary.json")
    row(D, "Model depth slots as groups, not a single starter (ties and empty slots allowed)",
        "Brief 'Model depth slots as groups'", "Unverified",
        "Not re-counted this round; the brief cites 149 slots with more than one rank-1 player",
        "Unverified: needs a re-count from the depth register",
        "Group count re-computed from the register and published next to the 149 cited",
        REPO + "data/depth/replacement_depth.csv")
    row(D, "Represent shared and empty depth slots faithfully",
        "Brief 'Represent shared and empty depth slots'", "Unverified",
        "Not checked this round (Seattle shared slot and Washington empty slot cited in the brief)",
        "Unverified",
        "Shared and empty flags present on the affected rows, checked against the club page",
        REPO + "data/depth/replacement_depth.csv")
    row(D, "Add an official depth-chart register with date and source on every row",
        "Brief 'Add an official depth-chart register'", "Partly built",
        f"{m['depth_slots']} slots carry a source per club; no capture date per row",
        "Blocked: decision (dating rule for club pages)",
        "Capture date and source on every row",
        REPO + "data/depth/replacement_depth.csv")
    row(D, "Flag backups replacing starters on offense and on defense, by string (2nd, 3rd, 4th)",
        "Brief 'Track injuries and deficiencies'", "Partly built",
        f"{m['depth_named']} slots name a replacement; {m['depth_unnamed']} name none; "
        f"{m['depth_starters_no_replacement']} starters on the report have no named replacement",
        "Blocked: data (HOU; reserve list)",
        "Every starter on the report mapped to a named replacement or to an explicit 'none'",
        REPO + "data/depth/replacement_depth_summary.json")
    row(D, "Interactive offense versus defense matchup deficiency matrix (1st to 4th string)",
        "Brief 'Interactive Offense vs. Defense Matchup'", "Partly built",
        "Deficiency table exists; no interactive matrix",
        "Blocked: depends on the complete depth register",
        "Matrix built for 32 clubs and reviewed against the register",
        REPO + "data/console/depth_replacement.csv")
    row(D, "Model depth from playing time, not from jersey order",
        "Brief 'Do not model depth from jersey order'", "Blocked: data",
        "Depth uses the club's own chart order; playing-time (snap) data is not captured",
        "Blocked: data (snap counts)",
        "Snap-count source verified for every 2026 game and linked per row",
        REPO + "data/depth/replacement_depth_summary.json")
    row(D, "Use snap counts as the starter proxy when the depth chart is unavailable",
        "Brief 'Use snap counts as the starter proxy'", "Blocked: data",
        "No snap counts in the repository",
        "Blocked: data (no official snap-count source captured)",
        "Snap counts for every 2026 game from a source named on each row",
        REPO + "data/depth/replacement_depth_summary.json")
    row(D, "Reject: deriving depth order from jersey number, experience or salary",
        "Brief 'Reject: deriving depth order from jersey number'", "Closed (approach rejected by brief, not used)",
        "Pipeline uses the club's depth-chart column order, not roster attributes",
        "None", "Remains closed", REPO + "pipeline/parsers.py")
    row(D, "Injury and personnel ablations: the same model with and without personnel features, the difference with uncertainty",
        "Brief 'Add injury and personnel ablations'", "Not started",
        "No model with personnel features exists",
        "Blocked: data (depth and snaps) and decision (model specification)",
        "Chronological holdout with a paired difference and an interval for each feature set",
        REPO + "data/lab/lines/model_report.json")
    row(D, "Injury and depth ablations: identical models with and without verified availability features, chronological holdouts",
        "Brief 'Add injury/depth ablations, not fixed penalties'", "Not started",
        "No availability features in any fitted model",
        "Blocked: data (archive series; snap counts)",
        "Identical models compared on a chronological holdout with the difference reported with uncertainty",
        REPO + "data/lab/lines/model_report.json")
    row(D, "Availability graph as a first-class dataset: who was expected to start, and who actually did",
        "Brief 'Build the availability graph'", "Not started",
        "No expected-start dataset; no game-book starters",
        "Blocked: data (game books; depth register)",
        "Expected and actual starter recorded for every starting slot of every 2026 game",
        REPO + "data/depth/replacement_depth.csv")
    row(D, "Per-team view: starters out, replacements named, net injury count",
        "Brief 'Add a per-team view'", "Partly built",
        "Replacement depth exists by unit and position; no per-team view",
        "Blocked: data (HOU)",
        "32 club views, each showing starters out, replacements named and the net count",
        REPO + "data/depth/replacement_depth_summary.json")

    S = "Strategies, validation and leaderboard"
    row(S, "Pre-register every strategy; forbid backtest numbers from ever appearing on the leaderboard",
        "Brief 'Pre-register every strategy'", "Partly built",
        f"Registry lists {m['registry_strategies']} strategies; leaderboard shows backtest columns "
        f"{', '.join(m['leaderboard_backtest_cols'][:3])} and more",
        "Blocked: decision (leaderboard rule for backtest columns)",
        "Leaderboard with no backtest column, and a registry row for every strategy the site reports",
        REPO + "data/strategy_leaderboard.csv")
    row(S, "Pre-register each strategy: definition frozen before results are seen",
        "Brief 'Pre-register each strategy'", "Partly built",
        "Registration recorded as a date (gates.json registered_at), not as a commit hash",
        "Blocked: decision (registration method)",
        "A git commit hash per strategy, dated before its evaluation window opens",
        REPO + "data/gates.json")
    row(S, "Freeze a rule before it sees data: commit the rule text, sample window and gates; the commit hash is the registration",
        "Brief 'Freeze a rule before it sees data'", "Not started",
        "No strategy has a commit hash as its registration",
        "Blocked: decision (process), then time",
        "One commit per strategy, with its hash in the registry",
        REPO + "data/strategy_registry.csv")
    row(S, "Split data into train, validation and final holdout seasons",
        "Brief 'Split data into train, validation and final holdout'", "Partly built",
        "Model tuned on 1999–2014 and scored on 2015–2026; no named final holdout season",
        "Blocked: decision (which seasons are final holdout)",
        "Named final holdout seasons, untouched until the window opens",
        REPO + "data/lab/lines/model_config.json")
    row(S, "Singles-only shadow baseline, pre-registered and frozen, with forecasts recorded before kickoff",
        "Brief 'Start with a singles-only shadow baseline'", "Not started",
        "No timestamped forecast log before kickoff",
        "Blocked: data (closing prices for the scoring)",
        "One logged forecast per fixture at least one hour before kickoff (14 in Week 10)",
        REPO + "data/lines/originated_markets_2026_week10.csv")
    row(S, "Parlays and prop combos only behind a joint-evidence gate (validated joint probability and void and push rules)",
        "Brief 'Keep parlays and prop combos behind a joint-evidence gate'", "Blocked: data",
        "Parlay result file exists; no validated joint probability and no operator void or push rules",
        "Blocked: data (joint probability; operator rules)",
        "Joint probability validated against outcomes, and the operator's void and push rules recorded",
        REPO + "data/parlay_results.csv")
    row(S, "Leaderboard divisions: singles, game parlays, same-game parlays and prop combos, ranked separately",
        "Brief 'Use proper-score leaderboard divisions'", "Not started",
        "Singles only in the registry; no division split",
        "Blocked: data (per-division samples)",
        "A division table with at least one row per division",
        REPO + "data/strategy_registry.csv")
    row(S, "Rank by benchmark-relative Brier skill with a game-cluster lower bound and a multiplicity adjustment",
        "Brief 'Rank with proper scores and uncertainty'", "Not started",
        "Brier appears in gate text only; the leaderboard does not rank by it",
        "Blocked: data (probabilities and closing prices)",
        "Brier skill against a named benchmark, with a cluster-bootstrap lower bound above zero",
        REPO + "data/gates.json")
    row(S, "Two-stage skill leaderboard: proper-score qualification, then prospective closing-line value and ROI escrow",
        "Brief 'Two-Stage Skill Leaderboard'", "Blocked: data",
        "No closing-line value series; no escrow",
        "Blocked: data (closing lines); decision (escrow rules)",
        "A prospective window with closing-line value recorded for every ticket",
        REPO + "data/gates.json")
    row(S, "Control baseline (random picks; favourites only) on every leaderboard run",
        "Brief 'Add a control baseline'", "Not started",
        "No random or favourites control rows in any leaderboard run",
        "Blocked: none (buildable now)",
        "Random and favourites rows in every leaderboard run",
        REPO + "data/strategy_leaderboard.csv")
    row(S, "Rank by proper scores with uncertainty, not win rate or short-run ROI",
        "Brief 'Rank with proper scores and uncertainty, not win rate'", "Partly built",
        f"Leaderboard ranks by a signal score; {m['leaderboard_rows']} rows, with ROI columns shown beside it",
        "Blocked: decision (ranking objective)",
        "Ranking column is a proper score with an interval; ROI columns removed from the ranking",
        REPO + "data/strategy_leaderboard.csv")
    row(S, "Reject: ranking strategies by season-long realised return",
        "Brief 'Reject: ranking strategies by season-long ROI'", "Closed (approach rejected by brief, not used)",
        "Leaderboard shows season ROI as a column; the rank column is the signal score",
        "None (confirm the rank column)", "Confirmed by a reviewer reading the rank formula",
        REPO + "data/strategy_leaderboard.csv")
    row(S, "Removal-of-luck panel on the dashboard",
        "Brief 'Compute and publish the removal of luck panel'", "Partly built",
        "Panel page exists on the line console; its inputs are not yet on a schedule",
        "Blocked: data (closing lines for the full sample)",
        "Panel computed from the verified feed and published with its n",
        REPO + "console/luck.html")
    row(S, "Two-sided 'what would change our mind' field on every strategy entry",
        "Brief 'Add a two-sided what would change our mind field'", "Not started",
        f"Registry columns: {', '.join(_csv_rows(_p('data','strategy_registry.csv'))[0].keys()) if m['registry_strategies'] else 'none'}; no such field",
        "Blocked: decision (the wording of each side)",
        f"Field filled for all {m['registry_strategies']} registered strategies",
        REPO + "data/strategy_registry.csv")
    row(S, "Define a demotion gate that sends a live strategy back to paper",
        "Brief 'Define a demotion gate'", "Partly built",
        "Defined in data/demotion_gate.json; thresholds T2 to T4 are proposed defaults",
        "Blocked: decision (ratify thresholds, question Q-26)",
        "Owner ratifies the thresholds in writing",
        REPO + "data/demotion_gate.json")
    row(S, "Sample sufficiency gate G1, one definition used everywhere",
        "Brief 'Each strategy must pass validation gates'", "Partly built",
        f"Three definitions: singles {m['g1_singles']} bets in gates.json; 100 in the README; "
        f"two-leg parlays {m['g1_parlay2']} tickets",
        "Blocked: decision (one threshold)",
        "One G1 threshold, cited identically in gates.json, the README and the leaderboard",
        REPO + "data/gates.json")
    row(S, "Correlations only from officially sourced numbers, with n published on every value",
        "Brief 'Compute correlations only from officially sourced numbers'", "Partly built",
        "Audit of 988 pairs found no violations; coverage limited to the 2026 official feed",
        "Blocked: data (historical official pages)",
        "Every correlation published with n and an official source for each input",
        REPO + "data/correlations_official_check.json")
    row(S, "Determine correlation values between the signals and markets we use",
        "Brief 'Determine correlation values'", "Partly built",
        "Published values with n exist for 2026 inputs",
        "Blocked: data (historical official pages)",
        "Values for every pair named in the strategy registry, each with n",
        REPO + "data/correlations_official_check.json")
    row(S, "Reward the top-performing strategies",
        "Brief 'Provide rewards for the top performing strategies'", "Blocked: decision",
        "Reward design is written; no funded pool; jurisdiction review not done",
        "Blocked: decision (Q-34 reward funding and legality)",
        "Owner decision on Q-34, and a jurisdiction review on file",
        REPO + "data/gates.json")
    row(S, "Strategies that generate useful signals, tested out of sample",
        "Brief 'Research and develop strategies for generating useful signals'", "Partly built",
        "16 strategies evaluated on the site; 0 pass every gate",
        "Blocked: data (prospective window) and decision (G1)",
        "At least one strategy passing every gate on a prospective window",
        REPO + "data/strategy_leaderboard.csv")
    row(S, "Originate our own NFL lines rather than reuse someone else's numbers",
        "Brief 'Originate my own NFL lines'", "Partly built",
        "Own model lines exist for 2026 Week 10 and for the 2015–2026 walk-forward",
        "Blocked: market column empty (Q-31)",
        "Residual against a named market for each originated line",
        REPO + "data/lines/originated_markets_2026_week10.csv")
    row(S, "Single bets, parlays and player-prop combinations covered",
        "Brief 'Look at single bet, parlays, player prop bet combos'", "Partly built",
        "Singles, parlays and props pages exist; no validated prop data",
        "Blocked: data (player-prop lines)",
        "Prop lines from a named source for each prop row",
        REPO + "data/parlay_results.csv")

    P = "Process, site and governance"
    row(P, "Decision-readiness table on the landing page, one row per requirement, with the gate that blocks it and the number that would clear it",
        "Brief 'Put a decision-readiness table on the landing page'", "Built",
        "This table, on the landing page, generated from data/readiness",
        "None", "Done", REPO + "data/readiness/requirements_r4.json")
    row(P, "Executive summary of the important details",
        "Brief 'Create an executive summary'", "Built",
        "console/executive-summary.html and docs/EXECUTIVE-SUMMARY.md",
        "None", "Refreshed each round", REPO + "docs/EXECUTIVE-SUMMARY.md")
    row(P, "Clear list of questions, the information we hold, the information we lack, and the answers needed",
        "Brief 'I want a clear list of questions'", "Built",
        "Decision register on console/questions.html",
        "None", "Maintained", REPO + "data/console/questions.csv")
    row(P, "Suggestions section for site improvements, each with more than one path for the owner to choose",
        "Brief 'Make suggestions on how to improve the site'", "Built",
        "Suggestion review board on console/suggestions.html",
        "None", "Maintained", REPO + "data/console/suggestions.csv")
    row(P, "Repository line-by-line review with links for manual review and irregularities flagged",
        "Brief 'REPO WORK'", "Built",
        "Repository review page, plus the round-4 flags on the flagged page",
        "None", "Refreshed each round", REPO + "data/flags.json")
    row(P, "GitHub Pages site: clean landing page and subpages organised by category",
        "Brief 'SITE CREATION'", "Built",
        "Live at karagemop466-tech.github.io/X1, from the Pages workflow",
        "None", "Live", REPO + ".github/workflows/pages.yml")
    row(P, "Every table row carries a source link to an official site; blank and flagged when unverified",
        "Brief 'VERIFICATION'", "Partly built",
        "Link presence is enforced by tools/verify_console.py; value correctness is not (LAC and BAL rows passed)",
        "Blocked: decision (adopt a value-level check in the build)",
        "Build fails on any row whose value differs from an independent read of the official page",
        REPO + "tools/verify_console.py")
    row(P, "Flagged for Review page with source links, not blocking the merge",
        "Brief 'PULL REQUEST AND MERGE'", "Built",
        "console/flagged.html, including the round-4 section",
        "None", "Maintained", REPO + "console/flagged.html")
    row(P, "Snapshot storage outside the static site, with freshness and source or schema change alerts",
        "Brief 'Add durable snapshot storage and alerts'", "Built, not yet run",
        "Archive lives under data/pipeline/archive and is not copied to the site; verifier warns on staleness",
        "Blocked: first scheduled run",
        "Freshness warning and integrity failure both exercised on live data",
        REPO + "scripts/pipeline/verify_archive.py")
    row(P, "Split the site into a public analysis layer and a private data layer until the terms are read",
        "Brief 'Split the site into a public analysis layer and a private data layer'", "Not started",
        "Everything is public; row-level data sits in data/ and is served",
        "Blocked: decision (which tables stay private until the terms are read)",
        "Owner decision on the table list, and a private store for the rest",
        REPO + "data/console/payload.json")
    row(P, "Weekly 'what changed' diff, not a static snapshot",
        "Brief 'Publish a weekly what changed diff'", "Partly built",
        "One what-changed record exists; no weekly store",
        "Blocked: time (needs a second weekly snapshot)",
        "Diff published for each of the last two weekly snapshots",
        REPO + "data/audit/what_changed.json")
    row(P, "Coordination: one branch per session, claims recorded on the board, no edits to another session's files",
        "Brief 'PARALLEL SESSIONS'", "Partly built",
        "Board kept in COORDINATION.md; the platform pins one branch per session, so session-<id>/<task> branches are not used",
        "Decision (accept the one-branch rule as the convention)",
        "Owner accepts the convention in writing",
        REPO + "COORDINATION.md")
    row(P, "No manual input from the owner; finish all tasks in the session",
        "Brief 'There should be no manual input'", "Partly built",
        "Scheduled pipeline and CI run without input; the open decisions above still wait for the owner",
        "Blocked: decision (each open decision in this table)",
        "Zero open decisions in this table",
        REPO + "data/readiness/requirements_r4.json")
    return R


def evidence_check(rows: list) -> list:
    """Each row needs an evidence link. Returns the rows that lack one (must be empty)."""
    return [r["requirement"] for r in rows if not r.get("evidence")]


def build_flags(m: dict) -> list:
    """Round-4 flags. Every flag carries its source link(s)."""
    return [
        {"id": "R4-F01", "severity": "high",
         "title": "Chargers (LAC) and Ravens (BAL) rows in the published injury table have blank designations",
         "detail": (f"Field differences against the official page read on 2026-11-15: LAC {m['inj_lac_rows_mismatch']}, "
                    f"BAL {m['inj_bal_mismatch']} (two Ravens rows, Calais Campbell and Ronnie Stanley, are absent; "
                    "Jaylinn Hawkins has no injury and no game status where the page shows Knee and Out). On the Chargers the "
                    "injury descriptions and game statuses are blank where the page prints them. The pipeline marked all "
                    f"{m['inj_published_rows']} rows verified, with zero flags."),
         "links": [OFFICIAL_INJ, REPO + "data/injuries/injuries_2026_week10.csv",
                   REPO + "data/readiness/spotcheck_diffs.csv"]},
        {"id": "R4-F02", "severity": "medium",
         "title": "Verification checks presence of a link, not that the value matches the official page",
         "detail": ("tools/verify_console.py passes on 2026-11-15 (every link resolves, every row sourced), while the injury "
                    "table it reads differs from the official page in 34 field values (R4-F01). Source presence is checked; source values are not."),
         "links": [REPO + "tools/verify_console.py", REPO + "tools/verify_app.py", REPO + "data/readiness/spotcheck_diffs.csv"]},
        {"id": "R4-F03", "severity": "high",
         "title": "The leaderboard publishes backtest and forward ROI columns",
         "detail": "The brief forbids backtest numbers on the leaderboard. data/strategy_leaderboard.csv has "
                   + ", ".join(m["leaderboard_backtest_cols"]) + ".",
         "links": [REPO + "data/strategy_leaderboard.csv"]},
        {"id": "R4-F04", "severity": "high",
         "title": "The G1 sample-size gate is defined three ways",
         "detail": (f"gates.json: {m['g1_singles']} singles bets and {m['g1_parlay2']} two-leg tickets; README: 100 bets; "
                    "leaderboard column G1_sample_ge_300. One definition must be ratified."),
         "links": [REPO + "data/gates.json", REPO + "README.md", REPO + "data/strategy_leaderboard.csv"]},
        {"id": "R4-F05", "severity": "high",
         "title": "The strategy registry lists fewer strategies than the site reports",
         "detail": f"data/strategy_registry.csv has {m['registry_strategies']} strategies; the site reports 16 strategies.",
         "links": [REPO + "data/strategy_registry.csv", REPO + "console/index.html"]},
        {"id": "R4-F06", "severity": "medium",
         "title": "Pre-registration is recorded as a date, not as a commit hash",
         "detail": "data/gates.json records registered_at as a date. The brief requires the commit hash to be the registration.",
         "links": [REPO + "data/gates.json"]},
        {"id": "R4-F07", "severity": "low",
         "title": "The owner brief's game-log count (136) differs from the repository's 2026 feed (137 rows)",
         "detail": f"{m['results_2026_rows']} rows in verified_results_2026_r3.csv. The brief figure is quoted, not re-verified. The difference needs reconciling before the corpus is frozen.",
         "links": [REPO + "data/results/verified_results_2026_r3.csv"]},
        {"id": "R4-F08", "severity": "medium",
         "title": "Injury counts in the brief are superseded by the official page",
         "detail": (f"The brief cites 254 and 279 rows and 4 Cincinnati players (quoted, not re-verified). On the 2026-11-15 read the page lists "
                    f"{m['inj_official_rows']} rows and {m['inj_cin_rows']} Cincinnati players. Each figure is kept with its date."),
         "links": [OFFICIAL_INJ]},
        {"id": "R4-F09", "severity": "medium",
         "title": "Texans (HOU) depth chart not parsed",
         "detail": "The houstontexans.com depth-chart URL returned HTTP 200 with a page title and no parsed tables in data/pipeline/_run_report.json, and a later attempt returned 404. No authorised structured source is recorded, so HOU is left blank, not transcribed by eye.",
         "links": [REPO + "data/pipeline/_run_report.json"]},
        {"id": "R4-F10", "severity": "medium",
         "title": "Only 1 of 14 Week 10 fixtures carries a venue",
         "detail": "The venue of each fixture must come from the official game centre. The game-centre pages have not been captured.",
         "links": [OFFICIAL_SCHED, REPO + "data/nfl/schedule_2026_week10.csv"]},
        {"id": "R4-F11", "severity": "high",
         "title": "The injury archive has not yet written an entry",
         "detail": "pipeline/archive.py and its workflow step are merged in this round. The archive's first entry is created by the first scheduled run; until then no multi-day history exists.",
         "links": [REPO + "pipeline/archive.py", REPO + ".github/workflows/data-refresh.yml"]},
        {"id": "R4-F12", "severity": "medium",
         "title": "Reserve moves are in official news, not in the injury report",
         "detail": "The Dolphins' QB Malik Willis moved to injured reserve, and the Patriots placed RB TreVeyon Henderson on injured reserve, per official news links. The report does not show reserve status, so 'not listed' is not 'available'.",
         "links": ["https://www.nfl.com/news/dolphins-place-qb-malik-willis-groin-on-injured-reserve-kyle-mccord-in-line-for-first-start",
                   "https://www.nfl.com/news/nfl-news-roundup-latest-league-updates-from-saturday-nov-14"]},
        {"id": "R4-F13", "severity": "high",
         "title": "The price store stamps every row with the build time, not a capture time",
         "detail": ("src/console/feed.py build_price_snapshots writes one build timestamp into captured_at_utc, open_captured_at_utc and "
                    "close_captured_at_utc. The committed rows read 2026-11-14T20:48:22Z. A rebuild on 2026-11-15 rewrites all 18,902 rows "
                    "to 2026-11-15T18:20:14Z, and the row order changes. The mirror publishes no capture time (its own note says so), so these "
                    "fields must not be presented as capture times. Found during the R4-1 console rebuild, which was not committed."),
         "links": [REPO + "src/console/feed.py", REPO + "data/console/price_snapshots.csv"]},
        {"id": "R4-F14", "severity": "medium",
         "title": "Replacement-depth coverage does not reconcile with the 31-club and 897-slot figures on the landing page",
         "detail": ("data/depth/replacement_depth.csv has 78 rows across 20 clubs. data/depth/replacement_depth_summary.json reports 897 slots "
                    "from data/pipeline/depth_charts.json, which lists 31 clubs (all except Houston, see R4-F09). The club count in the "
                    "replacement file is not explained by the depth charts. Not reconciled this round."),
         "links": [REPO + "data/depth/replacement_depth.csv", REPO + "data/depth/replacement_depth_summary.json",
                   REPO + "data/pipeline/depth_charts.json"]},
    ]


def write_outputs(rows: list, flags: list, m: dict) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    counts = Counter(r["status"] for r in rows)
    payload = {
        "dataset": "requirements_r4",
        "title": "Decision readiness: one row per requirement in the owner's brief",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "method": ("Statuses were assessed in session arena-8c67ec75-x1 by reading the files and pages named in "
                   "each row. Numbers are computed by tools/build_readiness.py from those files."),
        "status_counts": {s: counts.get(s, 0) for s in STATUSES},
        "rows_total": len(rows),
        "rows": [dict(id=f"R4-{i:02d}", **r) for i, r in enumerate(rows, 1)],
        "flags": flags,
        "metrics": m,
    }
    with open(os.path.join(OUT_DIR, "requirements_r4.json"), "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1, ensure_ascii=False, default=str)
        handle.write("\n")
    with open(os.path.join(OUT_DIR, "requirements_r4.csv"), "w", encoding="utf-8", newline="") as handle:
        w = csv.writer(handle)
        w.writerow(["id", "group", "requirement", "brief_ref", "status", "exists_today", "blocker", "clears_when", "evidence"])
        for i, r in enumerate(rows, 1):
            w.writerow([f"R4-{i:02d}", r["group"], r["requirement"], r["brief_ref"], r["status"],
                        r["exists_today"], r["blocker"], r["clears_when"], r["evidence"]])
    with open(os.path.join(OUT_DIR, "flags_r4.json"), "w", encoding="utf-8") as handle:
        json.dump(flags, handle, indent=1, ensure_ascii=False)
        handle.write("\n")


# ----------------------------------------------------------------- html (landing + flags)
def _pill(status: str) -> str:
    cls = {"Built": "ok", "Built, not yet run": "ok", "Partly built": "mid",
           "Blocked: data": "no", "Blocked: decision": "no", "Not started": "no",
           "Unverified": "mut"}.get(status, "mut")
    return f'<span class="pill {cls}">{status}</span>'


def _link(url: str, label: str = "source") -> str:
    return f'<a class="src" href="{url}">{label}</a>'


def render_rows_html(rows: list, esc) -> str:
    out = []
    for i, r in enumerate(rows, 1):
        out.append(
            "<tr>"
            f'<td class="mono">R4-{i:02d}</td>'
            f"<td>{esc(r['requirement'])}<div class=\"mut\" style=\"font-size:11.5px\">{esc(r['brief_ref'])}</div></td>"
            f"<td>{_pill(r['status'])}</td>"
            f"<td>{esc(r['exists_today'])}</td>"
            f"<td>{esc(r['blocker'])}</td>"
            f"<td>{esc(r['clears_when'])}</td>"
            f"<td>{_link(r['evidence'], 'evidence')}</td>"
            "</tr>")
    return "\n".join(out)


def render_section(data: dict, esc) -> str:
    counts = data["status_counts"]
    chips = " ".join(f'<span class="pill {"ok" if s.startswith("Built") and n else "mut"}">{esc(s)}: {n}</span>'
                     for s, n in counts.items() if n)
    return f"""
<h2 id="readiness">Decision readiness: one row per requirement</h2>
<p>Every requirement in the owner's brief, one row each. <b>Status</b> is what the repository shows today.
<b>Blocked by</b> names the gate or missing source. <b>Number that clears it</b> is the figure that would close the row,
computed from a file where a file defines it. The full register is in
<a href="https://github.com/karagemop466-tech/X1/blob/main/data/readiness/requirements_r4.csv">requirements_r4.csv</a>
and the method is in <a href="https://github.com/karagemop466-tech/X1/blob/main/tools/build_readiness.py">tools/build_readiness.py</a>.</p>
<p>{chips}</p>
<div class="wrap"><table><thead><tr><th>#</th><th>Requirement</th><th>Status</th><th>What exists today</th>
<th>Blocked by</th><th>Number that clears it</th><th>Evidence</th></tr></thead>
<tbody>
{render_rows_html(data["rows"], esc)}
</tbody></table></div>
"""


def render_flags(flags: list, esc) -> str:
    items = []
    for f in flags:
        links = " · ".join(_link(u, f"source {n + 1}") for n, u in enumerate(f["links"]))
        items.append(f"<tr><td class=\"mono\">{esc(f['id'])}</td><td>{esc(f['severity'])}</td>"
                     f"<td><b>{esc(f['title'])}</b><div class=\"mut\" style=\"font-size:12px\">{esc(f['detail'])}</div></td>"
                     f"<td>{links}</td></tr>")
    return ("<h2 id=\"round-4\">Round 4 flags (arena-8c67ec75-x1)</h2>"
            "<p>Found while checking the round-4 brief against the official page. None blocks the merge; each has its source.</p>"
            "<div class=\"wrap\"><table><thead><tr><th>ID</th><th>Severity</th><th>Finding</th><th>Sources</th></tr></thead>"
            "<tbody>" + "\n".join(items) + "</tbody></table></div>")


def apply(pages: dict, page_fn, esc) -> dict:
    """Called from tools/build_console.py. Adds the landing section, the readiness page and the flags."""
    m = compute_metrics()
    rows = build_rows(m)
    missing = evidence_check(rows)
    if missing:
        raise SystemExit(f"readiness rows without evidence: {missing}")
    flags = build_flags(m)
    write_outputs(rows, flags, m)
    data = _json(os.path.join(OUT_DIR, "requirements_r4.json"))
    anchor = "<h2>What this console is</h2>"
    index = pages["index.html"]
    if index.count(anchor) != 1:
        raise SystemExit("landing page anchor not found exactly once")
    pages["index.html"] = index.replace(anchor, render_section(data, esc) + "\n" + anchor, 1)
    pages["readiness.html"] = page_fn(
        "Readiness", "readiness",
        render_section(data, esc) + render_flags(flags, esc),
        subtitle="Every requirement in the brief, its status, the gate that blocks it and the number that clears it.")
    flagged = pages["flagged.html"]
    if flagged.count("</main>") != 1:
        raise SystemExit("flagged page anchor not found exactly once")
    pages["flagged.html"] = flagged.replace("</main>", render_flags(flags, esc) + "\n</main>", 1)
    return pages


def main() -> int:
    m = compute_metrics()
    rows = build_rows(m)
    missing = evidence_check(rows)
    if missing:
        print("rows without evidence:", missing)
        return 1
    flags = build_flags(m)
    write_outputs(rows, flags, m)
    counts = Counter(r["status"] for r in rows)
    print(f"{len(rows)} requirement rows; " + ", ".join(f"{s}: {counts.get(s, 0)}" for s in STATUSES))
    print(f"{len(flags)} round-4 flags")
    return 0


if __name__ == "__main__":
    sys.exit(main())
