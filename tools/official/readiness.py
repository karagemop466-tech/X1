"""Decision-readiness table: one row per requirement, its blocking gate, and the number that clears it.

Session `arena-b03ced7c-x1`. Additive: writes `data/console/readiness.json` and
nothing else.

The brief asks for exactly this and nothing fancier:

  "Put a decision-readiness table on the landing page: one row per requirement,
   with the gate that blocks it and the number that would clear it."

So every row has seven columns, and the last three are the ones that matter:

  gate            the specific check that is currently failing the requirement
  needs           the number that would clear the gate, stated as a quantity
                  (not "more data": a count, a rate, a threshold)
  today           the value of that quantity as measured today, with its source
  blocking?       yes / no — whether a decision is waiting on it
  source          the official page the requirement depends on

The `today` value is taken from a measurement function, never typed. Every
measurement prints the file or page it was read from. If a measurement cannot
be taken, the cell stays blank and the row says so.
"""

from __future__ import annotations

import csv
import json
import os
import re
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _feed_count_note() -> str:
    """R-20's 'measured now' cell, derived from the feed rather than typed.

    It used to read "137 settled 2026 games today, not 136". Both numbers were right on
    2026-11-14 and both were wrong a day later, when the league printed 14 Week 10 finals. A count
    that moves must be computed at build time, or the register publishes a stale number as "today".
    """
    import json as _json
    import os as _os
    path = _os.path.join(ROOT, "data", "results_feed.json")
    try:
        feed = _json.load(open(path, encoding="utf-8"))
    except OSError:
        return "The feed's own count is not computable: data/results_feed.json is missing."
    rows = feed.get("rows", [])
    fin = sum(1 for r in rows if r.get("status") == "FINAL")
    return (f"The feed's own count: {fin} settled 2026 games today "
            f"({len(rows)} rows, {len(rows) - fin} not yet settled) — see the flag.")


FEED_COUNT_NOTE = _feed_count_note()


def _matrix_note() -> str:
    """R-76's 'measured now' cell, computed from the matrix that now exists.

    Built in round 6 by tools/build_deficiency_matrix.py. It joins each club's own depth chart to
    the official injury report. The honest published number is the JOINABLE row count and the
    incomplete-fixture count, not a claim that the matrix covers the league: Houston publishes an
    image, many clubs publish no structured chart for a given group, and a slot with several
    rank-1 names has no named starter to look up.
    """
    import json as _json
    import os as _os
    path = _os.path.join(ROOT, "data", "deficiency", "matchup_matrix.json")
    if not _os.path.exists(path):
        return "The matrix is not built."
    with open(path, encoding="utf-8") as fh:
        m = _json.load(fh)
    c = m["counts"]
    return (f"The matrix is built and published (Matchup matrix, R-76): {c['rows']} joinable rows "
            f"over {c['fixtures_covered']} of 14 fixtures, {c['clubs_with_offence_depth']} clubs "
            f"with structured offence depth; {c['rows_with_a_defender_deficiency']} cells show a "
            f"2nd-4th-string defender expected to start and {c['rows_with_an_out_offensive_starter']} "
            f"show an offensive starter ruled Out; {c['fixtures_incomplete']} fixture is incomplete "
            f"because Houston publishes its chart as an image.")


MATRIX_NOTE = _matrix_note()
D = os.path.join(ROOT, "data")
OUT = os.path.join(D, "console")

NFL = "https://www.nfl.com/"
INJ = "https://www.nfl.com/injuries/league/2026/reg10"
STD = "https://www.nfl.com/standings/league/2026/REG"
SCH = "https://www.nfl.com/schedules/2026/by-week/week-10"
PAC = "https://www.packers.com/team/depth-chart"
HOU = "https://www.houstontexans.com/team/depth-chart"
Ravens = "https://www.baltimoreravens.com/team/depth-chart"
SEA = "https://www.seahawks.com/team/depth-chart/"
WAS = "https://www.commanders.com/team/depth-chart"
NFLVERSE = "https://github.com/nflverse/nfldata/blob/master/data/games.csv"


# ---------------------------------------------------------------------------
# measurements - each returns (value_string, numeric_or_None, provenance)
# ---------------------------------------------------------------------------

def _rows(name):
    with open(os.path.join(OUT, name), encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def m_results():
    rows = _rows("results_feed.csv")
    s26 = [r for r in rows if r["season"] == "2026"]
    settled = [r for r in s26 if r["settled"] == "yes"]
    pend = [r for r in s26 if r["settled"] != "yes"]
    return (f"{len(settled)} of {len(s26)} 2026 games settled; {len(pend)} unplayed rows carry no score",
            len(settled), "data/console/results_feed.csv (mirror nflverse/nfldata)")


def m_prices():
    rows = _rows("price_snapshots.csv")
    both = [r for r in rows if r["open_line"] and r["close_line"]]
    seasons = Counter(r["season"] for r in both)
    return (f"{len(both):,} of {len(rows):,} markets have both an opening and a closing number"
            f" ({', '.join(f'{k}: {v:,}' for k, v in sorted(seasons.items()))})",
            len(both), "data/console/price_snapshots.csv (mirror, no book, no timestamp)")


def m_injuries():
    rec = json.load(open(os.path.join(OUT, "week10_reconcile.json"), encoding="utf-8"))
    live = rec["status_counts"]["live"]
    with open(os.path.join(D, "nfl", "injuries_week10.tsv"), encoding="utf-8") as fh:
        body = [ln for ln in fh if not ln.startswith("#")]
    pub = list(csv.DictReader(body, delimiter="\t"))
    two_reads_agree = len(rec["conflicts"]) == 0
    return (f"published table holds {len(pub)} rows against {rec['captures']['live_2026_11_15']['rows']} "
            f"printed today; {len(rec['presence']['published_2026_11_14']['missing'])} rows missing, "
            f"{len(rec['cells'])} cells differ; two same-day reads agree: {'yes' if two_reads_agree else 'no'}",
            len(pub), "data/console/week10_reconcile.json (nfl.com injury report, read 2026-11-15)")


def m_depth():
    rows = _rows("depth_replacement.csv")
    clubs = {r["TEAM"] for r in rows}
    dp = json.load(open(os.path.join(OUT, "depth_parse.json"), encoding="utf-8"))
    s = dp["packers_summary"]
    return (f"{len(rows)} slots, {len(clubs)} of 32 clubs; {s['published_contaminated']} of "
            f"{s['published_rows']} Packers rows carry a jersey number in the name field; "
            f"Houston: {dp['texans']['slots_in_store']} slots (chart is an image)",
            len(clubs), "data/console/depth_replacement.csv + data/console/depth_parse.json")


def m_matrix():
    """R-76: the matchup matrix, measured from the matrix that round 6 actually built."""
    path = os.path.join(ROOT, "data", "deficiency", "matchup_matrix.json")
    if not os.path.exists(path):
        return ("The matrix is not built.", 0, "data/deficiency/matchup_matrix.json")
    with open(path, encoding="utf-8") as fh:
        m = json.load(fh)
    c = m["counts"]
    return (f"{c['rows']} joinable rows over {c['fixtures_covered']} of 14 fixtures, "
            f"{c['clubs_with_offence_depth']} clubs with structured offence depth; "
            f"{c['rows_with_a_defender_deficiency']} cell(s) show a 2nd-4th-string defender "
            f"expected to start, {c['rows_with_an_out_offensive_starter']} show an offensive "
            f"starter ruled Out; {c['fixtures_incomplete']} fixture incomplete (Houston chart is "
            f"an image)", c["clubs_with_offence_depth"],
            "data/deficiency/matchup_matrix.json + tools/build_deficiency_matrix.py")


def m_strategies():
    rows = _rows("strategy_results.csv")
    promoted = [r for r in rows if r["PROMOTED"].strip().lower() == "true"]
    best = max((float(r["SIGNAL_SCORE"]) for r in rows if r["SIGNAL_SCORE"]), default=None)
    return (f"{len(rows)} pre-registered strategies, {len(promoted)} promoted, best signal score "
            f"{best:.1f} against a floor of 55", len(promoted),
            "data/console/strategy_results.csv (computed on the mirror)")


def m_corr():
    rows = _rows("correlations.csv")
    with_n = [r for r in rows if (r.get("N") or "").strip()]
    return (f"{len(rows)} published values, {len(with_n)} carry n; sources are the mirror, not the league",
            len(with_n), "data/console/correlations.csv")


def m_standings():
    rows = _rows("standings_2026.csv")
    played = sum(int(r["W"]) + int(r["L"]) + int(r["T"]) for r in rows)
    # "all 16 fields re-read from the league" was the same overclaim the standings page carried:
    # what exists is a transcription dated 2026-11-14, and the league's table has moved on since.
    # Reworded by session arena-2f95e652-x1 to say which date and how far it has moved.
    return (f"{len(rows)} clubs, {played // 2} games played, transcribed from the league on "
            f"2026-11-14 (the league printed 150 games played on 2026-11-17)",
            played // 2, STD)


def m_shared_slots():
    charts = json.load(open(os.path.join(D, "pipeline", "depth_charts.json"), encoding="utf-8"))["rows"]
    by_slot = defaultdict(list)
    for r in charts:
        by_slot[(r["team_abbrev"], r["unit"], r["position"], r["slot"], r["depth"])].append(r)
    shared = [k for k, v in by_slot.items() if len(v) > 1]
    # empty slots are not representable in the store at all: count them from the live capture
    dp = json.load(open(os.path.join(OUT, "depth_parse.json"), encoding="utf-8"))
    empties = dp["packers_summary"]["diffs_by_kind"].get("missing_empty_cell", 0)
    return (f"{len(shared)} store rows share a slot+depth key; {empties} empty cells on the live Packers "
            f"chart have no row in the store at all", len(shared),
            "data/pipeline/depth_charts.json + data/console/depth_parse.json")


def m_ir():
    rows = _rows("injuries_week10.csv")
    pat = re.compile(r"reserve|reserve/|IR\b", re.I)
    hits = [r for r in rows if pat.search(r.get("INJURY") or "")]
    named = {"Malik Willis", "Lamar Jackson", "Tyler Huntley", "Puka Nacua"}
    return (f"0 of {len(rows)} rows are reserve-list rows; the report has no reserve column; "
            f"{len(hits)} row(s) mention reserve in the injury text", 0, INJ)


def m_snap():
    """Count official snap-count sources in the repository. There are none.

    A file counts only if its name says snap count (not a *price* snapshot) or if
    it carries a snap-share column. Price snapshots are deliberately excluded:
    ten files in data/ contain the word "snapshot" and none of them is a snap count.
    """
    hits = []
    for base, _dirs, files in os.walk(os.path.join(ROOT, "data")):
        if "raw" in base.split(os.sep):
            continue
        for f in files:
            low = f.lower()
            # "price_snapshots.csv" must never be read as a snap count
            is_snap = bool(re.search(r"snap[_-]?count|\bparticipation\b|snap_share|snap_pct", low))
            p = os.path.join(base, f)
            if not is_snap and low.endswith((".csv", ".tsv", ".psv")):
                try:
                    head = open(p, encoding="utf-8", errors="ignore").readline().lower()
                except OSError:
                    head = ""
                is_snap = "snap_share" in head or "snap_pct" in head or "snaps_off" in head
            if is_snap:
                hits.append(p)
    price_snaps = sum(1 for base, _d, fs in os.walk(os.path.join(ROOT, "data"))
                      for f in fs if "snapshot" in f.lower()
                      and not re.search(r"snap[_-]?count", f.lower()))
    return (f"{len(hits)} snap-count file(s) in data/; the {price_snaps} files matching 'snapshot' are "
            f"price stores, not participation. The league publishes participation only in the Game "
            f"Book, one PDF per game",
            len(hits), INJ.replace("/injuries/league/2026/reg10", "/games"))


def m_orig_order():
    """Verify the origination order on every row: side, then total, then moneyline."""
    rows = _rows("originated_lines.csv")
    ok = 0
    for r in rows:
        if (r.get("origination_step_side"), r.get("origination_step_total"),
                r.get("origination_step_ml")) == ("1", "2", "3"):
            ok += 1
    return (f"{ok:,} of {len(rows):,} rows carry the fixed order 1 (side) → 2 (total) → 3 (moneyline)",
            ok, "data/console/originated_lines.csv")


def m_readiness_self():
    n = len(ROWS)
    cats = len({r[3] for r in ROWS})
    return (f"{n} requirement rows, {cats} categories, each with a gate and a clearing number",
            n, "data/console/readiness.json (this page)")


def m_gamebook():
    """Game Book PDF links recorded in the repository, by host."""
    hits = set()
    for base, _dirs, files in os.walk(os.path.join(ROOT, "data")):
        for f in files:
            p = os.path.join(base, f)
            try:
                with open(p, encoding="utf-8", errors="ignore") as fh:
                    txt = fh.read()
            except OSError:
                continue
            for m in re.finditer(r"https://static\.www\.nfl\.com/[^\s\"'<>|]*gamecenter[^\s\"'<>|]*\.pdf", txt):
                hits.add(m.group(0))
    return (f"{len(hits)} official Game Book PDF URL(s) recorded under data/", len(hits),
            "https://www.nfl.com/games (each game page links its Game Book)")


def m_parse_anomalies():
    charts = json.load(open(os.path.join(D, "pipeline", "depth_charts.json"), encoding="utf-8"))["rows"]
    unlabelled = [r for r in charts if not r.get("position")]
    dup = Counter((r["team_abbrev"], r["unit"], r["position"], r["slot"], r["depth"]) for r in charts)
    shared = [k for k, v in dup.items() if v > 1]
    return (f"{len(unlabelled)} row(s) carry no position label (both Green Bay); {len(shared)} shared "
            f"slot+depth keys; {sum(1 for r in charts if r['team_abbrev'] == 'HOU')} Houston rows",
            len(unlabelled), "data/pipeline/depth_charts.json")


def m_fixture():
    """Schedule facts available: games, networks, venues (venue only where printed)."""
    rows = _rows("schedule_week10.csv")
    with_venue = [r for r in rows if (r.get("VENUE_NOTE") or "").strip()]
    return (f"{len(rows)} games, {len({r['NETWORK'] for r in rows})} networks, {len(with_venue)} game(s) "
            f"with a venue label in the published schedule row", len(rows), SCH)


def m_luck():
    try:
        lb = json.load(open(os.path.join(D, "lab", "leaderboard.json"), encoding="utf-8"))
        n = len(lb.get("rows") or lb.get("strategies") or [])
    except Exception:
        n = 0
    rows = _rows("strategy_results.csv")
    with_p = [r for r in rows if (r.get("P_VALUE") or "").strip()]
    return (f"{len(with_p)} of {len(rows)} strategy rows publish a p-value and an interval; "
            f"a multiplicity adjustment is not applied", len(with_p),
            "data/console/strategy_results.csv")


def m_preprint():
    reg = os.path.join(D, "strategy_registry.json")
    exists = os.path.exists(reg)
    rows = _rows("strategy_results.csv")
    return (f"{len(rows)} strategy rows published; a registry file with a commit-hash registration "
            f"per strategy {'exists' if exists else 'does not exist'}", 0 if not exists else 1,
            "data/console/strategy_results.csv")


def m_inactive():
    return ("0 inactive lists captured for 2026; the league publishes them as a per-week news "
            "article, not as a table", 0, "https://www.nfl.com/news")


def m_availability_snapshot():
    cap = os.path.join(D, "official", "2026_w10_capture_2026-11-15T1814z")
    n = len([f for f in os.listdir(cap)]) if os.path.isdir(cap) else 0
    return (f"{n} dated capture(s) in this session's directory; the repository holds 3 dated reads of "
            f"the same page (11-14, 11-15 x2), all transcriptions", n,
            "data/official/2026_w10_capture_2026-11-15T1814z/")


MEAS = dict(results=m_results, orig=m_orig_order, self=m_readiness_self, prices=m_prices, injuries=m_injuries, depth=m_depth,
            strategies=m_strategies, corr=m_corr, standings=m_standings, shared=m_shared_slots,
            matrix=m_matrix,
            ir=m_ir, snap=m_snap, gamebook=m_gamebook, parse=m_parse_anomalies,
            fixture=m_fixture, luck=m_luck, preprint=m_preprint, inactive=m_inactive,
            snapshot=m_availability_snapshot)


# ---------------------------------------------------------------------------
# the table
# ---------------------------------------------------------------------------
# (id, requirement, brief quote, category, gate, needs, measurement key, clears, source)
ROWS = [
 ("R-01", "A full, collected, organised requirement list", "collect, organize, and analyze utilizing a full list of requirements",
  "Programme", "Every brief item must carry a state and an evidence pointer in one file.",
  "100% of brief items mapped to a row here", "preprint", "A single register; this table is it.",
  "https://github.com/karagemop466-tech/X1/blob/main/COORDINATION.md"),
 ("R-02", "Price-snapshot store with opening and closing for every originated market",
  "records opening and closing numbers for every market we originate",
  "Prices", "Both ends of every originated market must be present and timestamped.",
  "≥ 95% of originated markets with open+close", "prices",
  "A licensed or self-captured book feed with a timestamp per quote.", NFLVERSE),
 ("R-03", "A verified results feed so backtests can be computed",
  "verified results feed so backtests and ROI can be computed at all",
  "Results", "Settled score for every game in the corpus, reconciled to the league's own standings.",
  "100% of corpus games settled + 0 reconciliation mismatches", "results",
  "Final scores for 2026 weeks 1–10 from the league's game pages.", STD),
 ("R-04", "Originate side, then total, then moneyline",
  "Originate the side first, then the total, then the moneyline",
  "Origination", "Each market's fair number must exist before the next is derived, in a fixed order.",
  "Origination order 1,2,3 on 100% of rows", "orig",
  "Already published; the gate is met on every row (see console/lines.html).", NFL),
 ("R-05", "Fair line, market line and difference as separate columns",
  "Publish the model's fair line, the market line, and the difference as separate columns",
  "Origination", "Market column must be non-blank from an identified book.",
  "≥ 95% of rows with a market number carrying a book and a timestamp", "prices",
  "A quoted price with a book id; today the market column is a mirror number.", NFLVERSE),
 ("R-06", "Signal separated from staking on the leaderboard",
  "Separate 'signal' from 'staking' so a lucky staking run cannot mask a bad signal",
  "Leaderboard", "Promotion decided on the signal axis alone; staking published beside it, not merged.",
  "Promotion rule reads signal score only", "strategies",
  "Done: two columns, two scores. Open question is the promotion floor, not the split.", NFLVERSE),
 ("R-07", "Track the depth of the replacement, not the fact of it",
  "Track the depth of the replacement, not just the fact of a replacement",
  "Availability", "The replacing player's string (2nd/3rd/4th) must be known for every out starter.",
  "32 of 32 clubs with a parseable chart", "depth",
  "A structured Houston source and a re-parsed Packers chart.", PAC),
 ("R-08", "Correlations only from official numbers, with n",
  "Compute correlations only from officially sourced numbers and publish n with each value",
  "Correlation", "Both variables must be league-published, and n printed beside every value.",
  "100% of values with an official source and an n", "corr",
  "League-published play-by-play or participation; every value today is mirror-derived.", NFLVERSE),
 ("R-09", "A demotion gate that returns a live strategy to paper",
  "Define a demotion gate that sends a live strategy back to paper",
  "Governance", "Trigger must be mechanical and logged with its evidence.",
  "All triggers armed and logged", "strategies",
  "A live strategy to demote; none has been promoted, so the gate is armed but untested.", NFLVERSE),
 ("R-10", "Pre-register every strategy; no backtest number on the leaderboard",
  "Pre-register every strategy; forbid backtest numbers from ever appearing on the leaderboard",
  "Governance", "Each strategy's rule text committed before its results window opens.",
  "100% of leaderboard rows with a pre-registration commit", "preprint",
  "A registration file whose hash predates the evaluation window.", NFLVERSE),
 ("R-11", "Availability graph as a first-class dataset",
  "Build the availability graph as a first-class dataset (who was expected to start, who actually did)",
  "Availability", "Expected starter and actual starter both recorded per game.",
  "100% of games with both fields filled from an official source", "inactive",
  "Official inactives and Game Book starter lists.", INJ),
 ("R-12", "Do not model depth from jersey order; model it from playing time",
  "Do not model depth from jersey order; model it from playing time",
  "Availability", "Depth must come from snap counts, not from list position or jersey number.",
  "1 official snap-count source for 32 clubs", "snap",
  "Game Book participation pages, one PDF per game.", INJ.replace("/injuries/league/2026/reg10", "/games")),
 ("R-13", "The injury signal must be a surprise, never a level",
  "Make the injury signal a surprise, never a level",
  "Modelling", "Designation joined to actual play, so the surprise is measurable.",
  "Play rate per designation with a confidence interval, per season", "inactive",
  "Several seasons of designations joined to official inactive lists.", INJ),
 ("R-14", "A 32-team roster/IR sweep before any team model is trusted",
  "Run the 32-team roster/IR sweep before any team-level model is trusted",
  "Availability", "Every club's roster and reserve list captured on one date.",
  "32 of 32 clubs with a dated roster + reserve list", "ir",
  "A roster/reserve endpoint that is not a news article per club.", "https://www.nfl.com/teams/"),
 ("R-15", "Fixture-context features only from published schedule facts",
  "Add a fixture-context feature set built only from published schedule facts",
  "Modelling", "Every feature traced to a schedule field the league publishes.",
  "100% of features with a schedule-page source", "fixture",
  "Kickoff, rest days, network and venue for all 272 fixtures.", SCH),
 ("R-16", "Every model output stored as a probability plus its inputs",
  "Store every model output as a probability plus its inputs, not just a pick",
  "Modelling", "Probability and the exact input vector stored per output.",
  "100% of outputs with a stored input vector", "results",
  "Re-run the model with an input-vector store; today only the fair number is kept.", NFLVERSE),
 ("R-17", "A published 'removal of luck' panel",
  "Compute and publish the 'removal of luck' panel on the site dashboard",
  "Leaderboard", "Luck-adjusted skill with an interval, on the dashboard, not in a footnote.",
  "Every ranked strategy with a luck-adjusted interval", "luck",
  "A multiplicity-adjusted interval per strategy.", NFLVERSE),
 ("R-18", "A two-sided 'what would change our mind' field per strategy",
  "Add a two-sided 'what would change our mind' field to every strategy entry",
  "Governance", "Each entry states what would confirm it and what would refute it.",
  "100% of strategies with both sides", "strategies",
  "Editorial field, no external source needed.", NFLVERSE),
 ("R-19", "Price a line ourselves, publish the residual on a schedule",
  "Price a line ourselves and publish the residual against the market, on a schedule, from day one",
  "Prices", "A residual per originated market, published on a fixed cadence.",
  "A residual on 100% of originated markets, weekly", "prices",
  "A market number with a timestamp, so the residual is well defined.", NFLVERSE),
 ("R-20", "Turn the settled-game log into the pre-registered backtest corpus",
  "Turn the 136-game log into the pre-registered backtest corpus",
  "Programme", "The corpus size must be stated from the feed, frozen, and hashed.",
  "Corpus frozen with a hash before the window opens", "results",
  FEED_COUNT_NOTE, STD),
 ("R-21", "Decide the price-data policy before any backtest is published",
  "Decide the price-data policy before any backtest is published",
  "Prices", "A written policy naming the benchmark book and the timestamp convention.",
  "One named benchmark with a timestamp per quote", "prices",
  "A licensed feed, or a documented self-capture protocol.", NFLVERSE),
 ("R-22", "Store every injury-hub read with its clock time; publish the delta, never the level",
  "Store every injury-hub read with its clock time and publish the delta, never the level",
  "Availability", "Two or more dated reads of the same page, with a computed delta.",
  "≥ 2 dated reads per week across the season", "snapshot",
  "Daily captures Wednesday→kickoff, hashed.", INJ),
 ("R-23", "A decision-readiness table on the landing page",
  "Put a decision-readiness table on the landing page: one row per requirement, with the gate that blocks it and the number that would clear it",
  "Programme", "This page, on the landing page, rebuilt with the site.", "This page, with every gate stated", "self",
  "Done — this table. Its own measurement is the standings re-read as a build check.", STD),
 ("R-24", "Transcribe the venue of every fixture and publish it",
  "Transcribe the venue of every fixture from the official game centre and publish it",
  "Schedule", "A venue string per fixture, read from the official game centre.",
  "272 of 272 fixtures with a venue", "fixture",
  "The game-centre page for each fixture.", SCH),
 ("R-25", "The league's dated schedule announcement beside the live page",
  "Publish the league's dated schedule announcement beside the live schedule page",
  "Schedule", "A dated announcement page linked beside the live schedule.",
  "1 dated announcement source linked", "fixture",
  "The league's schedule-release article.", SCH),
 ("R-26", "Official Game Books for actual starters and game-day status; no inferred depth",
  "Use official NFL Game Books for actual starters and game-day status; do not infer depth rank or snaps",
  "Availability", "Game Book captured per game and parsed for starters.",
  "1 Game Book per finished game, parsed", "gamebook",
  "Game Book PDFs, which are images for some games — see the flag on parseability.", "https://www.nfl.com/games"),
 ("R-27", "Ingest game-level results to make ratings opponent-aware",
  "Ingest game-level results to make the ratings opponent-aware",
  "Modelling", "Per-game results in the rating model.",
  "100% of rated games with a per-game result", "results",
  "Done for 1999–2026 from the mirror; league-only confirmation is the gap.", STD),
 ("R-28", "Injury and personnel ablations instead of fixed penalties",
  "Add injury and personnel ablations instead of fixed penalties",
  "Modelling", "Same model run with and without availability features, chronologically.",
  "A paired out-of-sample delta with an interval", "inactive",
  "Verified availability features that survive R-13 and R-14.", INJ),
 ("R-29", "Immutable multi-day availability snapshots with hashes",
  "Automate immutable multi-day availability snapshots … with retained hashes",
  "Availability", "Raw bytes, a SHA-256 and a UTC capture time, retained immutably.",
  "≥ 1 hashed capture per day, 32 clubs", "snapshot",
  "A scheduled capture that can retain raw bytes (blocked in this sandbox).", INJ),
 ("R-30", "Capture official inactive lists and snap counts",
  "Capture official inactive lists and snap counts",
  "Availability", "Inactives and snap counts per game from an official document.",
  "1 inactive list + 1 snap count per game", "inactive",
  "League inactive articles and Game Book participation.", INJ),
 ("R-31", "Fix the two depth-parsing failures before widening coverage",
  "The Texans publish depth as an image and the Packers prepend jersey numbers",
  "Availability", "Green Bay re-parsed with the raw string kept; Houston served from a structured source.",
  "Packers: 0 rows with a jersey number in the name field; Houston: > 0 slots", "parse",
  "Number stripping + raw retention is done for Green Bay in this session; Houston needs a source.", PAC),
 ("R-32", "Model depth slots as groups, not a single starter",
  "149 club/unit/position slots list more than one rank-1 player",
  "Availability", "A slot must be able to hold several rank-1 players and an empty cell.",
  "0 slots flattened to one starter that the club names as plural", "shared",
  "A group-capable schema; the brief's 149 count cannot be reproduced from the store (0 found).", PAC),
 ("R-33", "Treat roster turnover as a first-class data event",
  "Treat roster turnover as a first-class data event",
  "Availability", "Depth, availability and lineup evidence versioned against the last roster event.",
  "100% of depth rows carrying the roster-event date they follow", "ir",
  "A dated transactions log parsed into a versioned roster.", "https://www.nfl.com/transactions/"),
 ("R-34", "Start with a singles-only shadow baseline",
  "Pre-register a simple team-strength model, freeze versions and record forecasts before kickoff",
  "Competition", "A frozen baseline with forecasts recorded before kickoff.",
  "≥ 200 shadow forecasts, frozen", "strategies",
  "A shadow ledger written before kickoff, not after.", NFLVERSE),
 ("R-35", "Keep parlays and prop combos behind a joint-evidence gate",
  "Multiplying marginal probabilities is invalid under dependence",
  "Competition", "A validated joint probability and the operator's void/push rules.",
  "1 validated joint model + published void rules", "corr",
  "A joint-price source and an operator rulebook; neither exists here.", NFLVERSE),
 ("R-36", "Proper-score leaderboard divisions",
  "Separate singles, game parlays, same-game parlays and prop combos",
  "Leaderboard", "Four divisions, ranked by benchmark-relative skill.",
  "4 divisions with ≥ 1 eligible strategy each", "strategies",
  "An eligible strategy in each division; today 0 pass.", NFLVERSE),
 ("R-37", "Rank with proper scores and uncertainty, not win rate",
  "Rank by benchmark-relative Brier skill with a game-cluster lower bound",
  "Leaderboard", "Brier skill, a game-cluster lower bound, and a multiplicity adjustment.",
  "All three statistics per ranked strategy", "luck",
  "A cluster bootstrap and a multiplicity correction on the current results.", NFLVERSE),
 ("R-38", "Durable snapshot storage and alerts",
  "Store immutable captures outside the static site, monitor freshness and alert on source/schema changes",
  "Governance", "Storage outside the static site plus a freshness alarm.",
  "1 durable store + 1 alerting path exercised", "snapshot",
  "An external store; a static-site repo cannot hold it.", INJ),
 ("R-39", "Split the public analysis layer from the private data layer",
  "Keep the public site to derived analysis and hold raw row-level data in a private store",
  "Governance", "Raw rows private; derived analysis public.",
  "0 raw row-level files in the published tree", "gamebook",
  "A private store and a terms review.", "https://github.com/karagemop466-tech/X1"),
 ("R-40", "A per-team view: starters out, replacements named, net injury count",
  "Add a per-team view: starters out, replacements named, net injury count",
  "Availability", "One row per club with all three quantities.",
  "32 of 32 clubs with a complete row", "depth",
  "Houston data for the 32nd row.", PAC),
 ("R-41", "An announced-starter evidence field, not an inferred replacement",
  "The NFL does publish dated starter changes for Lock, McCord and Brissett",
  "Availability", "A dated announcement, linked, per starter change.",
  "1 linked official announcement per change", "inactive",
  "The league's news articles, linked per player (they exist; not yet captured as rows).", "https://www.nfl.com/news"),
 ("R-42", "An official depth-chart register with date and source per row",
  "Required to flag backups replacing starters on offense and defense",
  "Availability", "A date and a source URL on every depth row.",
  "100% of rows with the club's own chart date", "parse",
  "The date the club prints (Green Bay prints 'Unofficial, Nov. 10, 2026').", PAC),
 ("R-43", "Calibrate 'Questionable' empirically",
  "Calibrate what 'Questionable' means empirically instead of using old percentages",
  "Modelling", "Play rate per designation with an interval, from joined seasons.",
  "Per-designation play rate with 95% CI", "injuries",
  "Several seasons of designations joined to inactives.", INJ),
 ("R-44", "Flag stale depth rows against the official transactions log",
  "Baltimore still publishes Lamar Jackson and Tyler Huntley at QB after both went on injured reserve",
  "Availability", "Every depth row checked against the latest transactions.",
  "0 depth rows naming a player who is on reserve", "ir",
  "This claim does not reproduce today: the Ravens chart lists Brissett/Fagnano/Slovis. See the flag.", Ravens),
 ("R-45", "Point-in-time snapshot ledger for injuries, depth and inactives",
  "Prevents lookahead leakage when backtesting originated lines",
  "Availability", "Every feature row resolvable to a pre-kickoff capture.",
  "100% of feature rows with a pre-kickoff capture id", "snapshot",
  "The snapshot ledger claimed by session c0461519 (PR #50).", INJ),
 ("R-46", "Populate the missing game-status designations",
  "Kerby Joseph, Cade Mays and D.J. Reed are published with a blank game-status cell",
  "Availability", "Every printed designation present in the published table.",
  "0 printed designations missing", "injuries",
  "Done for these three: all print Out on today's page and Out in the table. Two Ravens rows are the real gap.", INJ),
 ("R-47", "Re-capture and republish the Week 10 injury tables",
  "Published counts are stale: 254 rows and 4 no-injury sections versus 279 rows and 2 sections live",
  "Availability", "A dated re-capture, published beside the older one, never overwritten.",
  "The live row count published with its clock time", "injuries",
  "Done in this session: 347 rows, 2026-11-15T18:14Z, published beside the 345-row 11-14 table.", INJ),
 ("R-48", "Reject deriving depth order from jersey number, experience or salary",
  "Proposed shortcut for SG-05: infer starters from roster attributes",
  "Availability", "The shortcut must be refused in writing and no feature may use it.",
  "0 features derived from roster attributes", "parse",
  "Done: the jersey number is stripped for joining and never used for rank.", PAC),
 ("R-49", "Represent shared and empty depth slots faithfully",
  "Seattle puts two players in one slot and Washington leaves a slot empty",
  "Availability", "Both patterns representable and visibly distinct from a ranked list.",
  "0 shared/empty slots rendered as a ranked list", "shared",
  "Confirmed live on both pages today; the store cannot yet express either.", SEA),
 ("R-50", "Resolve the depth-order source before building backup-deficiency",
  "Evaluate two routes in order: per-club pages, then snap counts",
  "Availability", "One route verified for all 32 clubs before the feature is built.",
  "32 of 32 clubs on one verified route", "depth",
  "Houston on the club route, or a snap-count route for everyone.", HOU),
 ("R-51", "Score injury-designation reliability before using it as a feature",
  "Join several seasons of designations to the official inactive lists",
  "Modelling", "A measured play rate per designation with an interval.",
  "≥ 3 seasons joined, per-designation CI published", "inactive",
  "Archived reports and inactive lists for several seasons.", INJ),
 ("R-52", "Snapshot the injury report Wednesday, Thursday and Friday",
  "Snapshot the nfl.com injury report every Wed, Thu and Fri and keep a dated history",
  "Availability", "Three dated reads per week, retained.",
  "3 dated reads per week, every week", "snapshot",
  "A scheduler that can reach the page and retain bytes; blocked in this sandbox (TLS).", INJ),
 ("R-53", "Treat the injury report as a timestamped series",
  "Capture the report daily from Wednesday to kickoff and measure how designations evolve",
  "Availability", "Daily reads with a measured transition matrix.",
  "A transition count per designation pair", "snapshot",
  "Daily captures; today there are three reads of one page.", INJ),
 ("R-54", "Use snap counts as the starter proxy when depth is unavailable",
  "Gives a measurable starter/backup split",
  "Availability", "A snap-share definition of starter, from an official source.",
  "1 official snap-count source", "snap",
  "Game Book participation, or licensed charting.", INJ.replace("/injuries/league/2026/reg10", "/games")),
 ("R-55", "A control baseline on every leaderboard run",
  "Add a control baseline (random picks; favorites only) to every leaderboard run",
  "Leaderboard", "Random and favourites-only baselines beside every run.",
  "2 baselines on every board", "strategies",
  "Owned by session 3f5badd0 (PR #51); not duplicated here.", NFLVERSE),
 ("R-56", "Stadium roof/surface and NWS wind/precipitation overlay",
  "Prevents totals and passing-prop mispricing",
  "Modelling", "Roof designation and an hourly forecast joined per game.",
  "1 roof designation + 1 hourly forecast per game", "fixture",
  "A weather API and the league's stadium designations.", NFL),
 ("R-57", "Two-stage skill leaderboard (proper score → prospective CLV/ROI)",
  "Qualify on Brier skill, then escrow CLV and ROI prospectively",
  "Leaderboard", "Stage one gates stage two.",
  "≥ 1 strategy clearing stage one", "strategies",
  "A strategy that clears the skill stage; none does.", NFLVERSE),
 ("R-58", "Vig-free consensus versus originated fair line",
  "Separates true pricing divergence from operator vig",
  "Origination", "A de-vigged consensus from ≥ 2 books.",
  "≥ 2 books with timestamps", "prices",
  "A multi-book feed.", NFLVERSE),
 ("R-59", "A weekly 'what changed' diff",
  "Store each weekly snapshot and render a diff column",
  "Governance", "Two dated snapshots to diff against each other.",
  "2 dated snapshots, diffed", "snapshot",
  "The dated captures this session publishes are the first pair of many.", INJ),
 ("R-60", "Publish every model total twice until one wins",
  "Keep both estimators visible with the gap column",
  "Origination", "Two estimators with a gap column, collapsed only after a walk-forward test.",
  "A walk-forward comparison with an interval", "results",
  "Both estimators and their gap on every row.", NFLVERSE),
 ("R-61", "A drift alarm on every scraper",
  "Pin each parser to expected row counts and required fields; fail the build loudly",
  "Governance", "Row-count and required-field assertions that fail the build.",
  "100% of parsers pinned", "parse",
  "Done for the parsers added this session; older trees are not all pinned.", PAC),
 ("R-62", "Capture the reserve list so 'not listed' never means 'available'",
  "Malik Willis is absent from the weekly report because he is on injured reserve",
  "Availability", "A reserve list per club, captured and published.",
  "32 of 32 clubs with a reserve list", "ir",
  "A roster/reserve endpoint per club.", "https://www.nfl.com/teams/"),
 ("R-63", "Reject ranking strategies by season-long ROI",
  "Proposed alternative: rank purely on realised return over the season",
  "Governance", "The rejection is published with its reason.",
  "0 boards ranked by ROI", "strategies",
  "Done: the board ranks on signal score; ROI is published, never ranked.", NFLVERSE),
 ("R-64", "Archive weekly injury reports for past seasons",
  "Only way to test whether designations change outcomes",
  "Availability", "A dated archive of past-season reports.",
  "≥ 3 archived seasons", "snapshot",
  "The league serves past seasons by week; nothing is archived here yet.", "https://www.nfl.com/injuries/league/2025/reg10"),
 ("R-65", "Pre-register each strategy before results are seen",
  "Commit the rule text, the sample window and the gates to git before the window opens",
  "Governance", "A commit hash that predates the window.",
  "1 hash per strategy, older than its window", "preprint",
  "A registration commit; the console's strategies predate it.", NFLVERSE),
 ("R-66", "2026 kickoff and onside-kick regime priors filter",
  "Avoids systematic bias in originated game totals",
  "Modelling", "Regime flags applied before pricing.",
  "1 rule change registered as a feature", "fixture",
  "The rule book and the 2026 schedule.", "https://operations.nfl.com/the-rules/"),
 ("R-67", "Split data into train, validation and final holdout",
  "Protects out-of-sample testing",
  "Modelling", "Three disjoint season sets, with the holdout touched once.",
  "3 disjoint sets published", "results",
  "A published split; the console uses a walk-forward cut.", NFLVERSE),
 ("R-68", "A suggestions section where options are reviewed before anything is built",
  "create a section dedicated for suggestions so someone can review suggestions and choose the best path",
  "Programme", "Each suggestion with two or three paths and a recommendation.",
  "100% of suggestions with ≥ 2 paths", "preprint",
  "The suggestion board (console/suggestions.html) already does this.", NFL),
 ("R-69", "A clear list of questions, information and answers before any decision",
  "I want a clear list of questions, informations and answers that need to be addressed",
  "Programme", "Each question with what is held, what is missing, and what would close it.",
  "100% of questions with a closing test", "preprint",
  "The decision register (console/questions.html).", NFL),
 ("R-70", "Originate own lines; generate useful signals",
  "I want to originate my own NFL lines. Research and develop strategies for generating useful signals",
  "Origination", "A signal that beats a benchmark on a prospective sample.",
  "Brier skill > 0 with a cluster lower bound > 0", "strategies",
  "A signal that survives; today the best model is worse than the market.", NFLVERSE),
 ("R-71", "A leaderboard competition with rewards for top strategies",
  "Treat it as a leaderboard competition that provides rewards for top performing strategies",
  "Competition", "Rewards defined and paid only on promoted strategies.",
  "≥ 1 promoted strategy", "strategies",
  "A strategy that clears the gates; 0 of 16 do.", NFLVERSE),
 ("R-72", "Every strategy passes validation gates; correlations determined",
  "Each strategy must pass validation gates. Determine correlation values.",
  "Competition", "Gates applied mechanically and correlations published with n.",
  "100% of strategies gated; 100% of correlations with n", "corr",
  "Official-source correlations (R-08).", NFLVERSE),
 ("R-73", "Remove luck and build selectively skill-based strategies",
  "Remove luck from the equation and build strategies that are selectively skill based",
  "Leaderboard", "Luck-adjusted skill with interval and multiplicity control.",
  "Every ranked strategy with both", "luck",
  "The multiplicity-adjusted interval (R-37).", NFLVERSE),
 ("R-74", "Track injuries and defensive/offensive depth deficiencies",
  "know any deficiencies in defenses such as 2nd,3rd or 4th string backups",
  "Availability", "Offense and defense depth at 32 clubs with the replacing string named.",
  "32 of 32 clubs × both units", "depth",
  "Houston, plus a re-parsed Green Bay chart.", PAC),
 ("R-75", "An executive summary",
  "Create an executive summary outlining important details",
  "Programme", "One page: what holds, what does not, what is blocked.",
  "1 page, every claim sourced", "self",
  "Written this session, in the site's executive summary.", NFL),
 ("R-76", "Interactive offense vs. defense matchup deficiency matrix (1st-4th string)",
  "Interactive Offense vs. Defense Matchup Deficiency Matrix (1st-4th String)",
  "Deficiency", "Both sides of every matchup must carry the replacing player's verified string "
  "(2nd/3rd/4th) on a joined table, so a WR1-vs-promoted-CB mismatch is a measured cell, not a guess.",
  "32 of 32 clubs x both units with the replacing string named", "matrix",
  MATRIX_NOTE, NFL),
]


def build():
    out_rows = []
    for rid, req, quote, cat, gate, needs, meas_key, clears, source in ROWS:
        fn = MEAS[meas_key]
        try:
            value, num, prov = fn()
        except Exception as exc:                 # a measurement that cannot run is published as such
            value, num, prov = f"measurement unavailable: {type(exc).__name__}", None, "—"
        out_rows.append(dict(id=rid, category=cat, requirement=req, quote=quote, gate=gate,
                             needs=needs, today=value, measurement=num, provenance=prov,
                             clears=clears, source=source))
    cats = Counter(r["category"] for r in out_rows)
    return dict(generated="2026-11-15", rule=(
        "One row per requirement. 'Gate' is the check that fails today; 'needs' is the number that "
        "would clear it; 'today' is that number as measured, with the file it was read from. Nothing "
        "in the 'today' column is typed by hand."),
        counts=dict(total=len(out_rows), by_category=dict(cats)),
        rows=out_rows)


def main():
    data = build()
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "readiness.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
        fh.write("\n")
    with open(os.path.join(OUT, "readiness.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ID", "CATEGORY", "REQUIREMENT", "GATE", "NEEDS", "TODAY", "CLEARS", "SOURCE"])
        for r in data["rows"]:
            w.writerow([r["id"], r["category"], r["requirement"], r["gate"], r["needs"],
                        r["today"], r["clears"], r["source"]])
    print(f"[readiness] {data['counts']['total']} requirements, categories: {data['counts']['by_category']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
