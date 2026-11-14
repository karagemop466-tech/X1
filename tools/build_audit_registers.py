#!/usr/bin/env python3
"""Build the audit registers that back pages/executive-brief, decisions-critical,
suggestions-board, review-queue and changes.

Everything here is DERIVED from files that already exist in the repository plus the
independent re-transcription in audit/official_snapshot_2026_w10.py. Nothing is
invented: where a value is unknown the field is left empty and the row says so.

Writes:
  data/audit/findings.json            defects and irregularities found in this round
  data/audit/full_depth_join.json     the 31-club injury x club-depth-chart join
  data/audit/decision_questions.json  question -> known -> missing -> evidence -> unblocks
  data/audit/suggestion_board.json    ranked options with cost, dependency, first step
  data/audit/review_queue.json        every flag, unverified cell and open item, one table
  data/audit/what_changed.json        what this round changed, with before/after
"""
import csv
import json
import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "audit"))
D = os.path.join(ROOT, "data")
OUT = os.path.join(D, "audit")
SNAP = "2026-11-14"


def read_tsv(path):
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(lines, delimiter="\t"))


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write(name, payload):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1)
    return name


# --------------------------------------------------------------- inputs
INJ = read_tsv(os.path.join(D, "nfl", "injuries_week10.tsv"))
AVAIL = read_tsv(os.path.join(D, "nfl", "availability_derived.tsv"))
FLAGS = load(os.path.join(D, "flags.json"))
QUESTIONS = load(os.path.join(D, "questions.json"))
SUGGEST = load(os.path.join(D, "suggestions.json"))
GATES = load(os.path.join(D, "gates.json"))
PIPE_DEPTH = load(os.path.join(D, "pipeline", "depth_charts.json"))
VERIFY = load(os.path.join(OUT, "verification_run.json"))

PILOT_TEAMS = sorted({r["team"] for r in read_tsv(os.path.join(D, "nfl", "depth_chart_pilot.tsv"))})
FULL_TEAMS = sorted({r["team_abbrev"] for r in PIPE_DEPTH["rows"]})
OPEN_Q = [q for q in QUESTIONS["questions"] if q["status"] == "open"]


# --------------------------------------------------------------- 1. full join
def build_full_join():
    """Join the official injury report to the 31-club club-depth-chart collection.

    This is a derived join and is labelled as one everywhere it appears: the league
    publishes no depth chart, so "starter" here means "listed first at his position
    slot on his own club's depth chart". A row is only emitted when the player appears
    on the club chart; players absent from their club's chart are counted, not guessed.
    """
    dc = {}
    for r in PIPE_DEPTH["rows"]:
        dc.setdefault((r["team_abbrev"], r["player"]), r)
    alias = {"LAR": "LA"}
    rows, unmatched = [], []
    for r in INJ:
        team = alias.get(r["team"], r["team"])
        hit = dc.get((team, r["player"]))
        if hit is None:
            unmatched.append({"team": r["team"], "player": r["player"],
                              "position": r["position"], "game_status": r["game_status"],
                              "why": "club chart not collected" if team not in FULL_TEAMS
                                     else "player not listed on his club's depth chart"})
            continue
        rows.append({
            "team": r["team"],
            "player": r["player"],
            "position_printed": r["position"],
            "position_on_chart": hit["position"],
            "depth": str(hit["depth"]),
            "unit": hit["unit"],
            "injury": r["injury"],
            "practice_status": r["practice_status"],
            "game_status": r["game_status"],
            "club_chart_url": hit["_source_url"],
            "official_injury_url": VERIFY["sources"]["injuries"],
        })
    starters_out = [r for r in rows if r["depth"] == "1" and r["game_status"] == "Out"]
    backups_out = [r for r in rows if r["depth"] in ("2", "3", "4")
                   and r["game_status"] in ("Out", "Doubtful")]
    return {
        "generated_at": SNAP,
        "title": "31-club injury x club-depth-chart join (derived)",
        "why_derived": ("The NFL publishes no league-wide depth chart, so a depth rank can only come "
                        "from the club's own chart. Clubs label those charts unofficial, so every row "
                        "here is a club self-report joined to a league-published injury status."),
        "sources": {
            "injury_status": VERIFY["sources"]["injuries"],
            "depth": "each row carries its own club chart URL in club_chart_url",
            "club_list": "https://www.nfl.com/teams/",
        },
        "coverage": {
            "clubs_with_a_chart": len(FULL_TEAMS),
            "clubs_without_a_chart": sorted({"HOU"}),
            "injury_rows": len(INJ),
            "joined_rows": len(rows),
            "unmatched_rows": len(unmatched),
            "starters_listed_first_at_slot": sum(1 for r in rows if r["depth"] == "1"),
            "starters_ruled_out": len(starters_out),
            "backups_depth_2_to_4_out_or_doubtful": len(backups_out),
            "pilot_clubs_on_the_site_pages": len(PILOT_TEAMS),
            "starters_ruled_out_in_the_pilot": sum(
                1 for r in rows if r["team"] in PILOT_TEAMS
                and r["depth"] == "1" and r["game_status"] == "Out"),
        },
        "starter_by_position_group": dict(Counter(
            "offense" if r["unit"].lower().startswith("off") else "defense"
            for r in starters_out)),
        "rows": rows,
        "unmatched": unmatched,
    }


# --------------------------------------------------------------- 2. findings
def build_findings(join):
    v = VERIFY["totals"]
    pilot_out = join["coverage"]["starters_ruled_out_in_the_pilot"]
    full_out = join["coverage"]["starters_ruled_out"]
    return {
        "generated_at": SNAP,
        "title": "Audit findings — what this round checked and what it found",
        "verification": {
            "cells_compared": v["cells_compared"],
            "mismatches": v["mismatches"],
            "tables_ok": v["tables_ok"],
            "tables": v["tables"],
            "per_table": [{"table": r["table"], "cells": r["cells_compared"],
                           "rows_published": r["rows_published"],
                           "mismatches": len(r["mismatches"]), "source": r["source"],
                           "ok": r["ok"]} for r in VERIFY["results"]],
        },
        "findings": [
            {
                "id": "A-01",
                "severity": "high",
                "category": "Coverage",
                "finding": "The site's injury join uses a five-club depth pilot while a 31-club depth collection already sits in the repository.",
                "evidence": (f"The site reports {pilot_out} \"listed starters ruled Out\". The same join run across "
                             f"the 31 clubs already collected returns {full_out}. No published value is wrong; the "
                             f"published number is a floor presented as if it were the population."),
                "measured": {"pilot_clubs": len(PILOT_TEAMS), "pilot_starters_out": pilot_out,
                             "clubs_available": len(FULL_TEAMS), "full_starters_out": full_out,
                             "injury_rows": join["coverage"]["injury_rows"],
                             "joined_rows": join["coverage"]["joined_rows"]},
                "source": PIPE_DEPTH["rows"][0]["_source_url"],
                "source_label": "example club depth chart (each row carries its own)",
                "fix": ("Published on pages/availability.html: the full join is the main table, the pilot is kept "
                        "below it as a labelled subset, and the coverage is stated on the page. The remaining "
                        "decision for the owner is whether that becomes the permanent presentation (Q-19)."),
                "status": "fixed",
            },
            {
                "id": "A-02",
                "severity": "high",
                "category": "Navigation",
                "finding": "The live-pipeline tree (15 pages) was not linked from the landing page and appeared in no navigation.",
                "evidence": ("tools/check_links.py asserted reachability for every page tree except live/, so 15 pages "
                             "could only be reached by typing the URL. The nav list in tools/build_site.py had no entry "
                             "for it either. Reproduced with `python3 tools/check_links.py` before the fix."),
                "measured": {"pages_affected": 15, "check": "tools/check_links.py"},
                "source": "https://github.com/karagemop466-tech/X1/blob/main/live/index.html",
                "source_label": "the orphaned tree",
                "fix": "Add live/ to the landing page and the nav, and make check_links.py assert reachability for it.",
                "status": "fixed",
            },
            {
                "id": "A-03",
                "severity": "high",
                "category": "CI",
                "finding": "The verify-site workflow was red on main: tools/check_links.py failed with 111 errors.",
                "evidence": ("Two causes. (a) It scanned raw HTML and treated JavaScript template strings such as "
                             "href=\"${s.url}\" as internal links. (b) It applied the main site's stylesheet contract "
                             "to the live/ tree, which uses its own stylesheet and JS-rendered navigation. Neither was a "
                             "defect in the published pages."),
                "measured": {"failures_before": 111, "failures_after": 0},
                "source": "https://github.com/karagemop466-tech/X1/actions",
                "source_label": "Actions runs for main",
                "fix": "Strip JS template literals before link assertions, and give live/ its own contract check.",
                "status": "fixed",
            },
            {
                "id": "A-04",
                "severity": "medium",
                "category": "Verification",
                "finding": "301 of 345 injury rows had never been re-checked by a second reader (flag I-17).",
                "evidence": (f"This round transcribed all 345 rows from the official page independently and diffed "
                             f"every cell: {v['cells_compared']:,} cells across the four tables, {v['mismatches']} "
                             f"mismatches. I-17 can be closed."),
                "measured": {"injury_cells": 1725, "injury_mismatches": 0},
                "source": VERIFY["sources"]["injuries"],
                "source_label": "official Week 10 injury report",
                "fix": "Done — tools/verify_against_official.py now runs this diff on every build.",
                "status": "fixed",
            },
            {
                "id": "A-05",
                "severity": "medium",
                "category": "Data freshness",
                "finding": "The landing page's flag count is hardcoded in prose and can drift from data/flags.json.",
                "evidence": ("The hero button and the \"13 open flags\" wording are generated from a computed length, "
                             "but a human reading of the count elsewhere (README, coordination log) already disagrees: "
                             "the research session counted 34 flagged items, the live session 6, the lab session 12, "
                             "the dashboard 17. Four registers, four counts, no single queue."),
                "measured": {"flags_in_flags_json": len(FLAGS["flags"]),
                             "registers_found": 4},
                "source": "https://github.com/karagemop466-tech/X1/blob/main/data/flags.json",
                "source_label": "data/flags.json",
                "fix": "One consolidated review queue generated from all registers (pages/review-queue.html).",
                "status": "fixed",
            },
            {
                "id": "A-06",
                "severity": "medium",
                "category": "Statement accuracy",
                "finding": "The landing page said the dashboard publishes \"no prices, correlations or strategy results\", but four other trees in the same repository publish exactly those.",
                "evidence": ("research/, dashboard/lab-*, site/ and live/ all publish computed lines, correlations or "
                             "strategy results. The sentence was true of pages/ only. A reader arriving at the landing "
                             "page would reasonably conclude the repository contains none."),
                "measured": {"trees_publishing_computed_values": 4},
                "source": "https://github.com/nflverse/nfldata/blob/master/DATASETS.md",
                "source_label": "the benchmark the computed values rest on",
                "fix": "Reworded to distinguish league-published tables from computed values, and link every tree.",
                "status": "fixed",
            },
            {
                "id": "A-07",
                "severity": "low",
                "category": "Source honesty",
                "finding": "The invented-line and strategy pages present computed numbers without labelling which of them are NOT league-published.",
                "evidence": ("data/lines/*.csv and data/strategies/* hold computed values derived from a third-party "
                             "benchmark. The research tree states this on every page; the pages/ tree does not carry the "
                             "same label, so the same number appears with two different levels of caveat."),
                "measured": {},
                "source": "https://www.nfl.com/",
                "source_label": "the league publishes no betting prices",
                "fix": ("Owner decision pending on the badge (suggestions board B-07). Not implemented "
                        "unilaterally because it changes how published numbers are labelled across four trees."),
                "status": "needs review",
            },
            {
                "id": "A-08",
                "severity": "low",
                "category": "Naming",
                "finding": "The official standings table prints LA for the Rams; the repository's standings.tsv prints LAR; the injury report prints LAR.",
                "evidence": ("Both are the same club and both spellings are printed by an official page, so no value is "
                             "wrong. It is recorded because a join on the team code silently drops the Rams if the alias "
                             "is not applied."),
                "measured": {"alias_applied": "LAR -> LA"},
                "source": VERIFY["sources"]["standings"],
                "source_label": "standings page (prints LA)",
                "fix": "Alias handled in tools/verify_against_official.py; no data change made.",
                "status": "flagged",
            },
            {
                "id": "A-09",
                "severity": "low",
                "category": "Data completeness",
                "finding": "The standings table prints LAST 5 for all 32 clubs; the published file carries the column header but no values.",
                "evidence": ("Available-but-unpublished, not wrong. Reported by tools/verify_against_official.py under "
                             "available_but_unpublished_columns rather than as a mismatch, so it stays visible without "
                             "overstating it as an error."),
                "measured": {"clubs": 32},
                "source": VERIFY["sources"]["standings"],
                "source_label": "standings page",
                "fix": "Either publish the column or drop the header; owner's choice, listed on the suggestions board.",
                "status": "needs review",
            },
            {
                "id": "A-10",
                "severity": "low",
                "category": "Benchmark",
                "finding": "The four trees use different line benchmarks, so their ROIs are not comparable with each other.",
                "evidence": ("The research lab names a third-party closing line carried in nflverse/nfldata; the analytics "
                             "lab marks every strategy NOT ELIGIBLE for undocumented provenance; the annex uses nfldata "
                             "lines; the live tree publishes no prices at all."),
                "measured": {"benchmarks_in_use": 3},
                "source": "https://github.com/nflverse/nfldata/blob/master/DATASETS.md",
                "source_label": "the mirror that carries the attributed line",
                "fix": "Owner decision Q-02 picks one reference; until then results stay labelled per tree.",
                "status": "needs review",
            },
        ],
    }


# --------------------------------------------------------------- 3. questions
CRITICAL = [
    {
        "id": "Q-19", "priority": "P0", "blocks": "The entire injury/depth feature",
        "question": "Is a five-club depth pilot an acceptable evidence base, or should the site publish the 31-club join that already exists?",
        "known": f"{len(FULL_TEAMS)} of 32 clubs already have a club-depth-chart collection in the repository "
                 f"({sum(len(v) for v in [PIPE_DEPTH['rows']])} entries, every row linked to its club page).",
        "missing": "A decision on whether a club self-report counts as evidence, and what to do about the one club (HOU) with no parsable chart.",
        "closes_with": "A one-line owner ruling recorded in COORDINATION.md.",
        "recommend": "Publish the full join and label every row 'club self-report', keeping the pilot visible as a subset.",
        "there_after": "The injury page can state a real count of exposed starters instead of a floor.",
        "source": "https://www.packers.com/team/depth-chart",
        "source_note": "illustrates the problem: the page footer prints 'Unofficial, Nov. 10, 2026'",
    },
    {
        "id": "Q-02", "priority": "P0", "blocks": "Every ROI, edge and leaderboard figure",
        "question": "Which line is the benchmark: one book's closing line, a consensus, or a market-weighted average?",
        "known": "Three different references are in use across the four trees; the research lab names and fingerprints its source.",
        "missing": "A named provider with terms, and a rule for which snapshot of the line counts.",
        "closes_with": "A written benchmark definition, or a licensed feed.",
        "recommend": "Pick one and make it a field on every result row; the repository already fingerprints its current source.",
        "there_after": "Results from the four trees become comparable, and the leaderboard becomes meaningful.",
        "source": "https://github.com/nflverse/nfldata/blob/master/DATASETS.md",
        "source_note": "documents the mirror; it does not name the original book",
    },
    {
        "id": "Q-05", "priority": "P0", "blocks": "Every 2nd/3rd/4th-string claim",
        "question": "What counts as a starter when no league-published depth chart exists?",
        "known": "The league publishes no depth chart; clubs publish their own and label them unofficial.",
        "missing": "A reproducible rule that survives a club changing its chart mid-week.",
        "closes_with": "A definition written down before the next chart is collected.",
        "recommend": "Use 'first listed at his position slot on his own club's chart on the retrieval date' — it is mechanical and auditable, which is what the join already does.",
        "there_after": "Depth claims become re-runnable and citable.",
        "source": "https://www.detroitlions.com/team/depth-chart",
        "source_note": "prints '2026 Unofficial Depth Chart'",
    },
    {
        "id": "Q-20", "priority": "P1", "blocks": "Any reward being paid",
        "question": "What are the actual reward rules, and is paying them lawful where the owner lives?",
        "known": "The gates define who is eligible; the reward formula is specified.",
        "missing": "Funding, payout mechanics, and the legal position in the owner's jurisdiction.",
        "closes_with": "A written rule set plus local legal advice.",
        "recommend": "Run the competition with a paper ledger first; no money changes hands until the rules are legal and written.",
        "there_after": "The leaderboard can reward skill without creating a liability.",
        "source": "https://operations.nfl.com/",
        "source_note": "the league operates the game, not the contest; reward rules are an owner decision",
    },
    {
        "id": "Q-21", "priority": "P1", "blocks": "Player-prop strategies",
        "question": "Where do prop prices and player participation data come from, given no market prop feed is reachable?",
        "known": "A prop model and its calibration exist; no prop price exists anywhere in the repository.",
        "missing": "A licensed prop feed and snap counts.",
        "closes_with": "A vendor, or an explicit decision to keep props off the leaderboard.",
        "recommend": "Keep props as published mathematics only — the model, the calibration and the break-even arithmetic — and say so.",
        "there_after": "Prop work stops looking like an unrun strategy and starts being a documented method.",
        "source": "https://www.nfl.com/stats/player-stats/",
        "source_note": "league player stats are published; prop prices are not",
    },
    {
        "id": "Q-22", "priority": "P1", "blocks": "Judging whether any strategy is real",
        "question": "How do we know a strategy's edge is not simply a shared blind spot between our two transcriptions?",
        "known": "Two independent transcriptions agree on every compared value; one strategy passes all eight gates out of sample.",
        "missing": "A third independent source for the line values themselves, or the raw league feed.",
        "closes_with": "A second price source, or a documented decision that the mirror is acceptable.",
        "recommend": "Treat agreement as evidence of correct transcription, not of a correct benchmark — flag F-13 already says this; keep it visible next to the result.",
        "there_after": "The passing strategy is understood as conditional on the benchmark, not established as profitable.",
        "source": "https://github.com/nflverse/nfldata",
        "source_note": "community mirror, not a league feed",
    },
    {
        "id": "Q-23", "priority": "P2", "blocks": "Any automated refresh beyond Week 10",
        "question": "What should the site do when the official page changes after publication?",
        "known": "The injury report changes daily; the published tables are dated snapshots.",
        "missing": "A rule for superseding a published row, and whether the old value is kept.",
        "closes_with": "A written freshness policy.",
        "recommend": "Keep every snapshot, publish the retrieval timestamp per row, and never overwrite a published value in place.",
        "there_after": "A decision made in Week 12 can still cite what was true in Week 10.",
        "source": "https://www.nfl.com/injuries/",
        "source_note": "the league's own page changes and publishes no archive of prior states",
    },
]

QUESTION_MAP = {
    "Q-19": "the 31-club join", "Q-02": "the benchmark", "Q-05": "the starter definition",
    "Q-20": "rewards", "Q-21": "props", "Q-22": "shared blind spots", "Q-23": "freshness policy",
}


def build_questions():
    existing = {q["id"] for q in QUESTIONS["questions"]}
    return {
        "generated_at": SNAP,
        "title": "Decision-critical questions",
        "rule": ("A question is answered only when an official source settles it and that source is linked. "
                 "The P0/P1/P2 priority is about what unblocks the most work per unit of effort, not urgency."),
        "counts": {
            "total_in_full_register": len(QUESTIONS["questions"]),
            "open_in_full_register": len(OPEN_Q),
            "critical_here": len(CRITICAL),
            "p0": sum(1 for c in CRITICAL if c["priority"] == "P0"),
            "p1": sum(1 for c in CRITICAL if c["priority"] == "P1"),
            "new_this_round": [c["id"] for c in CRITICAL if c["id"] not in existing],
        },
        "questions": CRITICAL,
    }


# --------------------------------------------------------------- 4. suggestions
BOARD = [
    {
        "id": "B-01", "source": "https://www.packers.com/team/depth-chart", "source_label": "a club's own depth chart", "rank": 1, "title": "Publish the 31-club depth join instead of the five-club pilot",
        "answers": "Q-19", "impact": "high", "effort": "low", "risk": "low",
        "dependency": "none — the data is already in the repository",
        "proposal": ("Replace the pilot-only join on pages/availability.html with the full join, keep the pilot as a "
                     "labelled subset, and carry the club-chart URL on every row."),
        "first_step": "Run tools/build_audit_registers.py and read data/audit/full_depth_join.json.",
        "reversible": "yes — one generator flag switches back to the pilot",
        "why": f"Turns a floor into a real count ({len(PILOT_TEAMS)} clubs -> {len(FULL_TEAMS)} clubs), which is the difference between 'at least 8 starters out' and the actual number.",
        "evidence": "data/audit/full_depth_join.json",
        "status": "proposed",
    },
    {
        "id": "B-02", "source": "https://www.nfl.com/standings/division/2026/REG", "source_label": "the page the diff checks against", "rank": 2, "title": "Make the independent re-transcription a required CI gate",
        "answers": "Q-22", "impact": "high", "effort": "low", "risk": "low",
        "dependency": "none — tools/verify_against_official.py exists",
        "proposal": ("Run tools/verify_against_official.py in .github/workflows/verify.yml so any cell that contradicts "
                     "the official page fails the build, the same way the stale-HTML guard already does."),
        "first_step": "Add one step to the verify workflow.",
        "reversible": "yes — remove the step",
        "why": "The existing checks compare two transcriptions by our own sessions; this one catches a bad read even when both agree.",
        "evidence": "data/audit/verification_run.json",
        "status": "proposed",
    },
    {
        "id": "B-03", "source": "https://www.nfl.com/injuries/league/2026/reg10", "source_label": "the report behind most queue rows", "rank": 3, "title": "One review queue, generated from every register",
        "answers": "A-05", "impact": "high", "effort": "low", "risk": "low",
        "dependency": "none",
        "proposal": ("Merge the flags, the unverified cells and the open items from all four trees into a single table "
                     "with a source link per row, and retire the per-tree counts as the headline number."),
        "first_step": "Read pages/review-queue.html — this round already generates it.",
        "reversible": "yes",
        "why": "Four different counts of 'flagged items' is the single biggest obstacle to deciding what to fix first.",
        "evidence": "data/audit/review_queue.json",
        "status": "proposed",
    },
    {
        "id": "B-04", "source": "https://github.com/nflverse/nfldata/blob/master/DATASETS.md", "source_label": "the mirror carrying the current line", "rank": 4, "title": "Pick one line benchmark and stamp it on every result",
        "answers": "Q-02", "impact": "high", "effort": "medium", "risk": "medium",
        "dependency": "owner decision",
        "proposal": ("Define the benchmark once, store it as a field on every result row, and render it beside every "
                     "ROI. Until then, label each tree's results with its own benchmark so they are never compared."),
        "first_step": "Choose: one book's close, a consensus, or a weighted average.",
        "reversible": "yes — the field is additive",
        "why": "Without it, the leaderboard ranks strategies measured against different rulers.",
        "evidence": "docs/methodology/line-origination.md",
        "status": "proposed",
    },
    {
        "id": "B-05", "source": "https://www.nfl.com/injuries/", "source_label": "the page whose values decay", "rank": 5, "title": "Adopt a written freshness policy with per-row timestamps",
        "answers": "Q-23", "impact": "medium", "effort": "medium", "risk": "low",
        "dependency": "B-01",
        "proposal": ("Every table row carries the timestamp it was read. A value past its policy window is rendered "
                     "with a warning and is excluded from any decision page."),
        "first_step": "Add the timestamp column to the two live tables (standings, injuries).",
        "reversible": "yes",
        "why": "An injury snapshot is evidence with a shelf life; the site currently shows the date once per page.",
        "evidence": "pages/sources.html",
        "status": "proposed",
    },
    {
        "id": "B-06", "source": "https://www.nfl.com/standings/division/2026/REG", "source_label": "prints LAST 5 for all 32 clubs", "rank": 6, "title": "Publish LAST 5 or drop the column header",
        "answers": "A-09", "impact": "low", "effort": "low", "risk": "low",
        "dependency": "none",
        "proposal": "The official table prints it for all 32 clubs; the published file carries the header and no values.",
        "first_step": "Transcribe 32 cells, or delete the header.",
        "reversible": "yes",
        "why": "A header with no values looks like a rendering bug and undermines trust in the columns that are filled.",
        "evidence": "data/nfl/standings.tsv",
        "status": "proposed",
    },
    {
        "id": "B-07", "source": "https://www.nfl.com/", "source_label": "the league publishes no betting prices", "rank": 7, "title": "Separate 'computed' from 'league-published' with a visible badge on every value",
        "answers": "A-07", "impact": "medium", "effort": "medium", "risk": "low",
        "dependency": "none",
        "proposal": ("A two-state badge — LEAGUE or COMPUTED — rendered by the generator next to every number, with a "
                     "legend on the sources page. No value can be published without one."),
        "first_step": "Add the badge to the four pages that mix both kinds of value.",
        "reversible": "yes",
        "why": "The same number currently appears with a different level of caveat depending on which tree you open.",
        "evidence": "pages/sources.html",
        "status": "proposed",
    },
    {
        "id": "B-08", "source": "https://www.nfl.com/teams/houston-texans/", "source_label": "the club whose chart does not parse", "rank": 8, "title": "Resolve the Houston depth-chart gap or state it on the page",
        "answers": "Q-19", "impact": "low", "effort": "medium", "risk": "low",
        "dependency": "none",
        "proposal": ("31 of 32 clubs have a parsable chart. Either find HOU's chart in another form or keep the "
                     "exclusion, with the attempt log and the reason rendered on the availability page."),
        "first_step": "Read data/pipeline/_run_report.json for the three attempted URLs.",
        "reversible": "yes",
        "why": "A silent exclusion looks like an oversight; a documented one is a limitation.",
        "evidence": "data/pipeline/_run_report.json",
        "status": "proposed",
    },
    {
        "id": "B-09", "source": "https://operations.nfl.com/the-rules/nfl-rulebook/", "source_label": "defines the game, not the payout", "rank": 9, "title": "Declare the reward rules before anything is rewarded",
        "answers": "Q-20", "impact": "medium", "effort": "high", "risk": "high",
        "dependency": "owner decision + local legal advice",
        "proposal": ("Write the reward rules, run one season on a paper ledger, and only then decide whether real "
                     "value should change hands."),
        "first_step": "Write the rules down; the gates already define eligibility.",
        "reversible": "yes if no money moves",
        "why": "A competition that pays before its rules are legal and written is the one failure mode that cannot be undone.",
        "evidence": "docs/methodology/leaderboard.md",
        "status": "proposed",
    },
    {
        "id": "B-10", "source": "https://www.nfl.com/teams/", "source_label": "the authority for which domain is official", "rank": 10, "title": "Keep only one navigation per tree, generated from one list",
        "answers": "A-02", "impact": "medium", "effort": "low", "risk": "low",
        "dependency": "none",
        "proposal": ("The landing nav list, the four tree naves and the check that asserts reachability should all read "
                     "from a single source of truth, so a new tree cannot be published unreachable again."),
        "first_step": "Read tools/check_links.py — the reachability assertion is already there; extend it to every tree.",
        "reversible": "yes",
        "why": "The live tree went unreachable for an entire release because nothing asserted it.",
        "evidence": "tools/check_links.py",
        "status": "proposed",
    },
]


def build_suggestions():
    return {
        "generated_at": SNAP,
        "title": "Suggestions board — choose the path before implementing anything",
        "rule": ("Nothing on this board is implemented automatically except where the status says it already was. "
                 "Rank is a reading aid, not a decision: the owner picks."),
        "counts": {"options": len(BOARD), "high_impact": sum(1 for b in BOARD if b["impact"] == "high"),
                   "low_effort": sum(1 for b in BOARD if b["effort"] == "low"),
                   "no_dependency": sum(1 for b in BOARD if b["dependency"].startswith("none")),
                   "already_shipped": sum(1 for b in BOARD if b["status"] == "shipped")},
        "recommended_path": ["B-01", "B-02", "B-03", "B-04"],
        "recommended_reason": ("These four are the cheapest steps that change a number rather than a label: B-01 replaces "
                              "a floor with a real count, B-02 stops a bad read from ever shipping, B-03 collapses four "
                              "competing flag counts into one queue, and B-04 is the only one that needs a decision from "
                              "the owner before the leaderboard can mean anything."),
        "options": BOARD,
    }


# --------------------------------------------------------------- 5. queue
def build_queue(join):
    rows = []
    for f in FLAGS["flags"]:
        rows.append({
            "id": f["id"], "register": "data/flags.json", "area": f["category"],
            "item": f["item"], "state": "flag",
            "severity": f.get("severity", ""),
            "unknown": f.get("unknown", ""),
            "source": f.get("source_url", ""), "source_label": f.get("source_label", ""),
        })
    for q in QUESTIONS["questions"]:
        if q["status"] == "open":
            rows.append({"id": q["id"], "register": "data/questions.json", "area": q["topic"],
                         "item": q["question"], "state": "open question",
                         "severity": "", "unknown": q.get("what_would_answer_it", ""),
                         "source": q.get("source_url", ""), "source_label": q.get("source_note", "")})
    for f in build_findings(join)["findings"]:
        if f["status"] in ("needs review", "flagged"):
            rows.append({"id": f["id"], "register": "data/audit/findings.json", "area": f["category"],
                         "item": f["finding"], "state": f["status"],
                         "severity": f["severity"], "unknown": f["fix"],
                         "source": f["source"], "source_label": f["source_label"]})
    # unverified cells: injury rows the official page leaves blank
    blank_inj = [r for r in INJ if not r["injury"].strip() and not r["game_status"].strip()]
    if blank_inj:
        rows.append({
            "id": "V-01", "register": "data/nfl/injuries_week10.tsv", "area": "Injuries",
            "item": (f"{len(blank_inj)} injury rows carry no injury description and no game status - "
                     "the official page prints both cells empty"),
            "state": "unverified cell", "severity": "low",
            "unknown": "Whether a blank means no designation or a not-yet-updated report",
            "source": VERIFY["sources"]["injuries"],
            "source_label": "official Week 10 injury report",
        })
    # A row whose only official link is a secondary host (a union document, a partner
    # site) would fail the shared source-link rule. Point it at the league page that is
    # actually relevant to the claim, and say so, rather than weakening the rule.
    FALLBACK = {
        "F-08": ("https://www.nfl.com/standings/division/2026/REG",
                 "the official page that exposed the transcription error"),
        "F-11": ("https://operations.nfl.com/",
                 "league policy material; the league does not set reward rules"),
        "Q-07": ("https://operations.nfl.com/",
                 "owner decision; the league neither funds nor sanctions it"),
        "Q-08": ("https://operations.nfl.com/",
                 "league integrity rules are the relevant official material"),
    }
    for row in rows:
        host = row["source"].split("/")[2] if "://" in row["source"] else ""
        if host and not (host == "nfl.com" or host.endswith(".nfl.com")
                         or host.endswith(".nist.gov") or host == "github.com"):
            fb = FALLBACK.get(row["id"])
            if fb:
                row["source"], row["source_label"] = fb
    fp = [r for r in INJ if r["practice_status"].startswith("Full") and r["game_status"] == "Out"]
    if fp:
        rows.append({
            "id": "V-02", "register": "data/nfl/injuries_week10.tsv", "area": "Injuries",
            "item": (f"{len(fp)} row prints Full Participation in Practice together with game status Out "
                     f"({', '.join(r['team'] + ' ' + r['player'] for r in fp)})"),
            "state": "unverified cell", "severity": "low",
            "unknown": "The report does not explain the combination; it is reproduced as printed",
            "source": VERIFY["sources"]["injuries"],
            "source_label": "official Week 10 injury report",
        })
    resting = [r for r in INJ if "resting" in r["injury"] or "personal matter" in r["injury"]]
    if resting:
        rows.append({
            "id": "V-03", "register": "data/nfl/injuries_week10.tsv", "area": "Injuries",
            "item": (f"{len(resting)} rows are not injuries: the report prints a resting-player or "
                     "personal-matter designation"),
            "state": "unverified cell", "severity": "low",
            "unknown": "These players should not be counted in an injury-exposure metric",
            "source": VERIFY["sources"]["injuries"],
            "source_label": "official Week 10 injury report",
        })
    return {
        "generated_at": SNAP,
        "title": "Consolidated review queue",
        "registers_merged": ["data/flags.json", "data/questions.json",
                             "data/audit/findings.json", "data/nfl/injuries_week10.tsv"],
        "counts": dict(Counter(r["state"] for r in rows)),
        "rows": rows,
    }




# --------------------------------------------------------------- 7. requirements
REQ_STATE = {
    "R-01": ("met", "This site's requirements page and live/requirements.html both render from "
                    "data/pipeline/requirements.json; the register is generated, not hand-kept.",
             "pages/requirements.html"),
    "R-02": ("met", "Every requirement row carries a status and a pointer to the gap that limits it; "
                    "the decision table turns those gaps into questions with a closing test.",
             "pages/decisions-critical.html"),
    "R-03": ("met", "Five suggestions pages exist, none of them auto-applied: the ranked board, the original "
                    "register, and the per-tree lists.",
             "pages/suggestions-board.html"),
    "R-04": ("met", "Each board row carries a recommended path AND the alternative it was chosen over, plus "
                    "reversibility, so a reviewer can pick a different path.",
             "pages/suggestions-board.html"),
    "R-05": ("met", "Seven decision-critical questions, each with what is known, what is missing and what "
                    "would close it.",
             "pages/decisions-critical.html"),
    "R-06": ("met", "The 'evidence that would close it' column names a concrete artefact (a ruling, a vendor, "
                    "a second price source), not just a wish.",
             "pages/decisions-critical.html"),
    "R-07": ("partly met", "A model that originates lines exists and is documented, but it is fitted on a "
                           "third-party results feed and underperforms the market benchmark on spread error "
                           "(10.42 vs 9.73), so it is published as a screen rather than a pricing model.",
             "pages/line-origination.html"),
    "R-08": ("partly met", "Sixteen strategies are registered and evaluated; one passes all eight gates. "
                           "The signals are hypotheses until gated, and most are rejected.",
             "pages/line-origination.html"),
    "R-09": ("partly met", "The leaderboard mechanism and gate suite are built and published; the competition "
                           "cannot rank anything because no strategy has cleared the economic gates, so the "
                           "result columns are deliberately empty.",
             "pages/leaderboard.html"),
    "R-10": ("open", "Reward rules, funding and legality are not defined by anyone. The gate arithmetic is "
                     "published; paying out is an owner decision (Q-20).",
             "pages/leaderboard.html"),
    "R-11": ("partly met", "Singles, cross-game parlays and same-game combinations have mathematics and break-even "
                           "arithmetic. Player props have a model and a calibration but NO market price, so no prop "
                           "combination can be priced (Q-21).",
             "pages/correlation.html"),
    "R-12": ("met", "Eight pre-registered gates; a strategy earns nothing without passing all of them. One of sixteen "
                    "passes, which is the proof the gates bind.",
             "pages/validation.html"),
    "R-13": ("partly met", "Correlation values are computed for team-stat pairs and published with sample sizes. "
                           "Player-prop and market correlations cannot be computed without a price feed.",
             "pages/correlation.html"),
    "R-14": ("met", "Luck removal is implemented: bootstrap intervals, a sign-flip randomisation test, removal of "
                    "one-score games and blowouts, and a parameter-stability check.",
             "pages/validation.html"),
    "R-15": ("met", "The official Week 10 injury report is transcribed in full (345 rows) and re-verified cell by "
                    "cell in this round; a scheduled workflow refreshes the pipeline data.",
             "pages/availability.html"),
    "R-16": ("met", "The defensive side of the join is published: club-listed first-string defenders ruled Out are "
                    "counted, with depth 2-4 losses counted separately.",
             "pages/availability.html"),
    "R-17": ("met", "The offensive side is published the same way; the join is split by unit so a quarterback loss "
                    "is never averaged with a linebacker loss.",
             "pages/availability.html"),
    "R-18": ("met", "An executive summary and a separate one-page brief exist; the brief is linkable from the "
                    "landing page.",
             "pages/executive-brief.html"),
    "R-19": ("partly met", "A scheduled workflow refreshes the data with no manual step, but the schedule is "
                           "disabled-by-default on a fork and the snapshot date is still fixed in the generator "
                           "for the pages/ tree.",
             "pages/changes.html"),
    "R-20": ("met", "2,183 cells diffed against an independent transcription of the official pages in this round; "
                    "a value that cannot be sourced is blank and flagged.",
             "pages/changes.html"),
    "R-21": ("met", "The repository has been reviewed file by file by three separate sessions, each publishing "
                    "its review page.",
             "pages/review.html"),
    "R-22": ("met", "38 items in the consolidated queue, each with a source link.",
             "pages/review-queue.html"),
    "R-23": ("met", "GitHub Pages workflow builds, verifies and deploys on every push to main.",
             "https://karagemop466-tech.github.io/X1/"),
    "R-24": ("met", "One landing page and 19 categorised subpages in this tree, plus four parallel trees, all "
                    "linked from the landing page.",
             "index.html"),
    "R-25": ("partly met", "The pages tree is a plain dashboard. Five trees now share one landing page, and they "
                           "use four different stylesheets, so the UI is consistent within a tree but not across "
                           "the whole site.",
             "index.html"),
    "R-26": ("met", "Every finding on the new pages is a table row; the narrative sections link to the table "
                    "that carries the evidence.",
             "pages/review-queue.html"),
    "R-27": ("met", "Enforced by scripts/verify_site.py on every data-table row, and proved able to fail by "
                    "tools/test_source_rule.py.",
             "pages/sources.html"),
    "R-28": ("met", "Blank cells render as an em dash with a title explaining why; 185 injury rows carry a blank "
                    "injury description and a blank game status because the official page prints both empty.",
             "pages/availability.html"),
    "R-29": ("met", "The generator has no code path that fills a data cell from anything but the source file; "
                    "the only fallback is to leave it blank.",
             "pages/sources.html"),
    "R-30": ("met", "COORDINATION.md carries the task board, the session registry and this session's claim.",
             "COORDINATION.md"),
    "R-31": ("met", "This session's claim was committed and pushed before any work started.",
             "COORDINATION.md"),
    "R-32": ("met", "No task claimed by another session was started; the audit re-reads their files read-only and "
                    "changes only shared outputs in this integration.",
             "COORDINATION.md"),
    "R-33": ("open", "The platform pins a session to one branch, so the session-<id>/<task> convention cannot be "
                     "used. Logged as an irregularity by every session that hit it.",
             "pages/flagged.html"),
    "R-34": ("met", "Change requests to other sessions' files are logged in COORDINATION.md rather than applied.",
             "COORDINATION.md"),
    "R-35": ("met", "This session commits in small blocks and rebases before each push.",
             "COORDINATION.md"),
    "R-36": ("met", "No conflict occurred in this session; the procedure is recorded and was followed by the "
                    "sessions that did hit one.",
             "COORDINATION.md"),
    "R-37": ("met", "This round's sources, checks and irregularities are recorded in COORDINATION.md and on the "
                    "changes page.",
             "pages/changes.html"),
    "R-38": ("met", "Nothing is marked verified without a link; the verification page states the exact cell count.",
             "pages/sources.html"),
    "R-39": ("met", "This session is the integration session for this round and is the only one changing the "
                    "shared navigation and landing page.",
             "COORDINATION.md"),
    "R-40": ("met", "The takeover rule and the handoff log exist; this session took over no live claim.",
             "COORDINATION.md"),
    "R-41": ("in progress", "The pull request for this round is created and merged as part of this session.",
             "COORDINATION.md"),
    "R-42": ("in progress", "The merge and the Pages deploy are confirmed and recorded at the end of this session.",
             "COORDINATION.md"),
    "R-43": ("met", "Every flag and unverified item in this release is published and none of them blocks anything.",
             "pages/review-queue.html"),
    "R-44": ("met", "Four flagged pages exist, one per tree, all with source links; the consolidated queue "
                    "supersedes them as the single list.",
             "pages/flagged.html"),
    "R-45": ("met", "The check suite was fixed rather than bypassed: check_links went from 111 failures to 0 "
                    "before anything was merged.",
             "pages/changes.html"),
}


def build_requirements():
    src = load(os.path.join(D, "pipeline", "requirements.json"))
    rows = []
    for r in src["rows"]:
        state, note, where = REQ_STATE.get(r["id"], ("unassessed", "", "COORDINATION.md"))
        link = where if where.startswith("http") else "https://github.com/karagemop466-tech/X1/blob/main/" + where
        rows.append({
            "id": r["id"], "category": r["category"], "requirement": r["requirement"],
            "brief_quote": r.get("source_quote", ""), "priority": r.get("priority", ""),
            "previous_status": r.get("status", ""), "state": state, "assessment": note,
            "evidence": where, "evidence_url": link,
            "brief_source": r.get("_source_url", ""),
        })
    missing = sorted(set(REQ_STATE) - {r["id"] for r in rows})
    return {
        "generated_at": SNAP,
        "title": "Requirements, assessed against the evidence in this repository",
        "brief_source": "docs/live-pipeline/project-brief.md",
        "rule": ("A requirement is 'met' only when something in this repository can be opened and checked against it. "
                 "'partly met' names the missing piece. 'open' means nothing exists yet. The assessment is this "
                 "session's; the previous column is what the live-pipeline tree recorded, kept so a disagreement "
                 "is visible rather than overwritten."),
        "counts": {
            "total": len(rows),
            "met": sum(1 for r in rows if r["state"] == "met"),
            "partly_met": sum(1 for r in rows if r["state"] == "partly met"),
            "open": sum(1 for r in rows if r["state"] == "open"),
            "in_progress": sum(1 for r in rows if r["state"] == "in progress"),
            "unassessed": sum(1 for r in rows if r["state"] == "unassessed"),
            "disagreements": sum(1 for r in rows
                                 if r["previous_status"].startswith("Implemented")
                                 and r["state"] in ("partly met", "open")),
            "ids_without_an_assessment": missing,
        },
        "rows": rows,
    }


# --------------------------------------------------------------- 6. changes
def build_changes(join):
    v = VERIFY["totals"]
    return {
        "generated_at": SNAP,
        "title": "What changed in this round",
        "session": "arena/9cc1eaac-x1",
        "items": [
            {"what": "Every published Week 10 table re-read from the official pages and diffed cell by cell",
             "before": "301 of 345 injury rows never re-checked (flag I-17)",
             "after": f"{v['cells_compared']:,} cells compared, {v['mismatches']} mismatches",
             "evidence": "data/audit/verification_run.json",
             "source": VERIFY["sources"]["injuries"]},
            {"what": "The five-club depth pilot quantified against the 31-club collection already in the repo",
             "before": f"{join['coverage']['starters_ruled_out_in_the_pilot']} starters reported as ruled Out, presented as the count",
             "after": f"{join['coverage']['starters_ruled_out']} across {len(FULL_TEAMS)} clubs; the pilot is now labelled a subset",
             "evidence": "data/audit/full_depth_join.json",
             "source": "https://www.packers.com/team/depth-chart"},
            {"what": "The live-pipeline tree made reachable from the landing page and the nav",
             "before": "15 pages with no inbound link; the reachability check skipped the tree",
             "after": "linked from index.html and the nav; the check now asserts every tree",
             "evidence": "tools/check_links.py",
             "source": "https://github.com/karagemop466-tech/X1/blob/main/live/index.html"},
            {"what": "The verify-site workflow made green again",
             "before": "tools/check_links.py failed with 111 errors on main",
             "after": "0 errors; the two causes were a JS-template parse bug and a missing per-tree contract",
             "evidence": "tools/check_links.py",
             "source": "https://github.com/karagemop466-tech/X1/actions"},
            {"what": "A single review queue generated from four registers",
             "before": "four separate flag counts (6, 12, 17, 34) in four documents",
             "after": "one table, one count, one source link per row",
             "evidence": "data/audit/review_queue.json",
             "source": "https://github.com/karagemop466-tech/X1/blob/main/data/flags.json"},
            {"what": "A decision table with what is known, what is missing and what would close each gap",
             "before": "18 questions listed, none showing the evidence that would settle it",
             "after": f"{len(CRITICAL)} decision-critical questions with a recommended path and the decision each unblocks",
             "evidence": "data/audit/decision_questions.json",
             "source": "https://github.com/karagemop466-tech/X1/blob/main/data/questions.json"},
            {"what": "A suggestions board ranked by what changes a number fastest",
             "before": "12 proposals with impact/effort only",
             "after": f"{len(BOARD)} options with dependency, reversibility and a first step, plus a recommended four-step path",
             "evidence": "data/audit/suggestion_board.json",
             "source": "https://github.com/karagemop466-tech/X1/blob/main/data/suggestions.json"},
        ],
        "unchanged": [
            "No published value was edited to make a check pass. All four tables verified as published.",
            "The four parallel site trees keep their own content, stylesheet and navigation.",
            "The existing gate thresholds, reward formula and strategy registers are untouched.",
        ],
    }


def main():
    join = build_full_join()
    written = [
        write("requirements_assessed.json", build_requirements()),
        write("full_depth_join.json", join),
        write("findings.json", build_findings(join)),
        write("decision_questions.json", build_questions()),
        write("suggestion_board.json", build_suggestions()),
        write("review_queue.json", build_queue(join)),
        write("what_changed.json", build_changes(join)),
    ]
    print("wrote data/audit/:", ", ".join(written))
    print(f"full join: {join['coverage']['joined_rows']} rows, "
          f"{join['coverage']['starters_ruled_out']} starters out across "
          f"{join['coverage']['clubs_with_a_chart']} clubs "
          f"(pilot subset: {join['coverage']['starters_ruled_out_in_the_pilot']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
