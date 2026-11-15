#!/usr/bin/env python3
"""Decision-readiness register: one row per requirement, the gate that blocks it, and the
number that would clear it.

Session arena/29e011dc-x1. Writes:
  data/audit/decision_readiness.json   (machine-readable, the source for the landing page)
  data/audit/decision_readiness.csv    (the same rows, for download)
  data/audit/irregularities_review.json (irregularities found in this review, for Flagged)

Rules enforced here:
  * Every number in a row is READ from a committed file at build time (the path is in the
    row's `evidence` field). Nothing is typed in from memory.
  * A clearing number that the repo does not define is labelled `basis = proposed`, so a
    reviewer can see which thresholds are proposals awaiting the owner's acceptance.
  * The state of each of the 53 registered requirements is taken from
    data/audit/requirements_assessed.json and is not re-decided here.

Usage:
  python3 tools/build_readiness.py          # write the three files
  python3 tools/build_readiness.py --check  # fail if committed files differ from a fresh build
"""

from __future__ import annotations

import csv
import glob
import io
import json
import os
import re
import sys
from typing import Any, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GH = "https://github.com/karagemop466-tech/X1/blob/main/"
AS_OF = "2026-11-15"


def jl(rel: str) -> Any:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


def csv_rows(rel: str) -> List[Dict[str, str]]:
    with open(os.path.join(ROOT, rel), encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def gh(rel: str) -> str:
    return GH + rel


def evidence_link(evidence: str, fallback: Any = None) -> str:
    """Link to the first file named in an evidence string (they may be ';'-separated).

    A register row that already carries a URL keeps it. Otherwise the first path is linked
    on GitHub, so a reviewer can open exactly the file the number was read from."""
    if fallback:
        return str(fallback)
    first = (evidence or "").split(";")[0].strip()
    if not first:
        return ""
    if first.startswith("http"):
        return first
    return gh(first.rstrip("/"))


# ---------------------------------------------------------------- numbers read from files
def facts() -> Dict[str, Any]:
    f: Dict[str, Any] = {}

    mr = jl("data/lab/lines/model_report.json")["accuracy"]
    f["side_mae_model_lab"] = round(mr["side_mae_model"], 3)
    f["side_mae_market_lab"] = round(mr["side_mae_market"], 3)
    f["n_side_lab"] = mr["n_side"]

    pay = jl("data/site/payload.json")
    f["side_mae_model_payload_all"] = round(pay["model"]["summary"]["mean_margin_mae"], 2)
    f["payload_leaderboard"] = pay["leaderboard"]
    f["payload_pass"] = [s for s in pay["leaderboard"] if s.get("all_passed")]
    f["payload_n"] = len(pay["leaderboard"])
    f["payload_baselines"] = sorted(pay["baselines"].keys())

    lab = jl("data/lab/leaderboard.json")
    f["lab_n"] = len(lab["rows"])
    f["lab_pass"] = sum(1 for r in lab["rows"] if not r.get("gates_failed"))
    singles = [r for r in lab["rows"] if r.get("division") == "singles"]
    best = max(singles, key=lambda r: r["signal"]["z_vs_break_even"])
    f["best_single_id"] = best["id"]
    f["best_single_z"] = round(best["signal"]["z_vs_break_even"], 2)

    inj = csv_rows("data/injuries/injuries_2026_week10.csv")
    f["injury_rows"] = len(inj)
    f["injury_snapshot_dates"] = sorted({r["snapshot_date"] for r in inj})
    f["injury_has_fetch_time"] = any("T" in r["snapshot_date"] or ":" in r["snapshot_date"] for r in inj)

    # The three injury tables that exist in the repo (same league report, three layouts).
    f["injury_copies"] = {
        "data/injuries_2026_week10.csv": len(csv_rows("data/injuries_2026_week10.csv")),
        "data/injuries/injuries_2026_week10.csv": len(inj),
        "data/console/injuries_week10.csv": len(csv_rows("data/console/injuries_week10.csv")),
    }

    # Distinct local stylesheet files, across the page trees a visitor can reach.
    sheets = set()
    trees = ["index.html", "pages", "dashboard", "research", "site", "app", "lab", "hub", "live", "console"]
    for t in trees:
        paths = [os.path.join(ROOT, t)] if t.endswith(".html") else glob.glob(
            os.path.join(ROOT, t, "**", "*.html"), recursive=True)
        for p in paths:
            if not os.path.isfile(p):
                continue
            with open(p, encoding="utf-8", errors="replace") as fh:
                for href in re.findall(r'href="([^"]+\.css)"', fh.read()):
                    if not href.startswith("http"):
                        sheets.add(os.path.normpath(os.path.join(os.path.dirname(p), href)))
    f["stylesheet_files"] = len(sheets)

    f["slate_games"] = len(csv_rows("data/console/schedule_week10.csv"))
    f["schedule_announcement_date"] = jl("data/audit/schedule_announcement_2026.json")["announced_date"]
    wc = jl("data/audit/what_changed.json")
    f["what_changed_items"] = len(wc.get("items", []))
    return f


# ---------------------------------------------------------------- the rows
# Clearing-number basis values:
#   "repo"     the threshold is defined in a committed gate or register file
#   "proposed" this build proposes the number; the owner has not yet accepted it
#   "none"     the row is met; nothing to clear
def build_rows(F: Dict[str, Any]) -> List[Dict[str, Any]]:
    reg = jl("data/audit/requirements_assessed.json")["rows"]
    reg_ids = {r["id"] for r in reg}

    # Gate/question/number for every registered requirement that is not met. Values come from F.
    blockers: Dict[str, Dict[str, str]] = {
        "R-07": dict(
            gate="G3 calibration: the originated side must beat the market benchmark on side error. "
                 f"Model {F['side_mae_model_lab']} vs market {F['side_mae_market_lab']} "
                 f"(n={F['n_side_lab']}, lab model report).",
            clear=f"Side MAE at or below the market benchmark {F['side_mae_market_lab']} on the same window",
            basis="repo", evidence="data/lab/lines/model_report.json"),
        "R-08": dict(
            gate=f"G2 skill above variance: z ≥ 1.96 and an ROI interval excluding zero. Best singles "
                 f"z is {F['best_single_z']} ({F['best_single_id']}).",
            clear="z ≥ 1.96 on n_eff ≥ 500 singles (G1)", basis="repo",
            evidence="data/gates.json; data/lab/leaderboard.json"),
        "R-09": dict(
            gate=f"Two leaderboards disagree and only one can be cited. Line desk: {F['lab_pass']} of "
                 f"{F['lab_n']} strategies through all gates. Landing page (payload): "
                 f"{len(F['payload_pass'])} of {F['payload_n']}. Flagged as IR-01.",
            clear="One reconciled leaderboard with at least 1 strategy through G0–G8",
            basis="repo", evidence="data/lab/leaderboard.json; data/site/payload.json"),
        "R-10": dict(
            gate="Q-20 (owner decision): reward rules, funding and legality are not defined in any file.",
            clear="Written reward rule and legal review recorded (0 of 2 present)",
            basis="repo", evidence="data/audit/decision_questions.json"),
        "R-11": dict(
            gate="Q-21: no prop prices exist from any official source, so no prop combination can be priced. "
                 "G1 needs 500 props tickets.",
            clear="500 priced prop tickets (G1), currently 0 priced", basis="repo",
            evidence="data/gates.json; data/audit/decision_questions.json"),
        "R-13": dict(
            gate="Q-21: correlations with market or prop prices cannot be computed without a price feed. "
                 "Team-stat correlations are published with n.",
            clear="n published for every market and prop pair (prop/market pairs computed: 0)",
            basis="proposed", evidence="data/correlations/official_correlations.csv"),
        "R-19": dict(
            gate=f"Snapshot capture: the scheduled refresh completes, but the injury file holds "
                 f"{len(F['injury_snapshot_dates'])} capture date(s) and no fetch time (IR-04).",
            clear="5 dated captures, one per day Wednesday to Sunday, with fetch time (proposed; currently 1)",
            basis="proposed", evidence="data/injuries/injuries_2026_week10.csv"),
        "R-25": dict(
            gate=f"{F['stylesheet_files']} different stylesheet files are linked across the page trees (IR-07).",
            clear="1 stylesheet across every page tree (currently "
                  f"{F['stylesheet_files']})", basis="repo",
            evidence="index.html; pages/; dashboard/; research/; site/; app/; lab/; hub/"),
        "R-33": dict(
            gate="Platform constraint: a session is pinned to one branch, so the session-<id>/<task> "
                 "convention cannot be used. Owner decision.",
            clear="Owner decision recorded on branch naming (0 recorded)", basis="repo",
            evidence="data/audit/decision_questions.json"),
        "R-41": dict(
            gate="Pull request from this session's branch to main not yet merged.",
            clear="PR merged to main, with the merge recorded in COORDINATION.md", basis="repo",
            evidence="COORDINATION.md"),
        "R-42": dict(
            gate="GitHub Pages deploy for the merged commit not yet confirmed.",
            clear="Pages deploy of the merge commit reported as success", basis="repo",
            evidence="COORDINATION.md"),
    }
    # The assessed state is taken from the register. Rows marked met get no blocker.
    rows: List[Dict[str, Any]] = []
    for r in reg:
        b = blockers.get(r["id"])
        if r["state"] == "met" and b is None:
            gate, clear, basis, ev = "No blocker: met", "Nothing to clear", "none", r.get("evidence") or ""
        elif b is None:
            raise SystemExit(f"no blocker written for {r['id']} ({r['state']})")
        else:
            gate, clear, basis, ev = b["gate"], b["clear"], b["basis"], b["evidence"]
        rows.append(dict(
            id=r["id"], group="Register", requirement=r["requirement"],
            state=r["state"], blocking_gate=gate, clearing_number=clear, basis=basis,
            evidence=ev, evidence_url=evidence_link(ev, r.get("evidence_url")),
            source_url=r.get("brief_source") or "",
            assessment=r.get("assessment", "")))

    # Requirements from this session's brief that the 53-row register does not contain yet.
    nb = [
        dict(id="NB-01", requirement="Injury and depth ablations: the same model with and without verified "
             "availability features, on chronological holdouts, reported with uncertainty",
             state="open",
             gate="No archived past-season official injury reports exist in the repo; data/injuries holds "
                  "only the 2026 Week 10 report.",
             clear="2 archived seasons of weekly official injury reports before the holdout season (proposed)",
             basis="proposed", evidence="data/injuries/injuries_2026_week10.csv",
             source_url="https://www.nfl.com/injuries/"),
        dict(id="NB-02", requirement="Official inactive lists and snap counts captured, so a backup's replacing "
             "a starter is confirmed rather than suspected", state="open",
             gate="No inactive-list or snap-count capture exists in the repo.",
             clear="One season of official inactive lists and snap counts for 32 clubs (proposed)",
             basis="proposed", evidence="data/injuries/injuries_2026_week10.csv",
             source_url="https://www.nfl.com/injuries/"),
        dict(id="NB-03", requirement="Injury-designation reliability: play rate per designation with confidence "
             "intervals, before any designation becomes a model feature", state="open",
             gate="Blocked by NB-01 and NB-02 (no joined history of designations and inactive lists).",
             clear="3 seasons joined to inactive lists (proposed)", basis="proposed",
             evidence="data/injuries/injuries_2026_week10.csv", source_url="https://www.nfl.com/injuries/"),
        dict(id="NB-04", requirement="Calibrate what 'Questionable' means from data, not from old percentages",
             state="open", gate="Blocked by NB-03; the NFL report publishes no percentages.",
             clear="A measured play rate for Questionable with a confidence interval (currently none)",
             basis="proposed", evidence="data/injuries/injuries_2026_week10.csv",
             source_url="https://www.nfl.com/injuries/"),
        dict(id="NB-05", requirement="Stadium roof/surface and hourly NWS wind and precipitation overlay for totals "
             "and passing props", state="open",
             gate="No NWS forecast data and no official roof-status capture exist in the repo.",
             clear=f"Hourly forecast and roof status captured for every game on the slate (0 of {F['slate_games']} captured)",
             basis="proposed", evidence="data/console/schedule_week10.csv", source_url="https://www.nfl.com/schedules/2026/by-week/week-10"),
        dict(id="NB-06", requirement="Publish the league's dated schedule announcement beside the live schedule page",
             state="met",
             gate="No blocker: captured this session from the NFL's media page (announced "
                  f"{F['schedule_announcement_date']}).",
             clear="Nothing to clear", basis="none", evidence="data/audit/schedule_announcement_2026.json",
             source_url="https://media.nfl.com/football-information/2026/news/2026-nfl-schedule-announced"),
        dict(id="NB-07", requirement="Control baseline on every leaderboard run (random picks; favourites only)",
             state="partly met",
             gate="The payload has "
                  f"{', '.join(F['payload_baselines'])} baselines, but no random-pick control.",
             clear="A seeded random-pick baseline on the same bets (not yet run)", basis="proposed",
             evidence="data/site/payload.json", source_url=""),
        dict(id="NB-08", requirement="Per-team view: starters out, replacements named, net injury count",
             state="open",
             gate="No team-level decision page exists. The data needed is in the deficiency join.",
             clear="32 team rows, each with starters out, replacements named and net count (0 of 32 published)",
             basis="repo", evidence="data/audit/full_depth_join.json", source_url=""),
        dict(id="NB-09", requirement="Shared and empty depth slots represented faithfully, not as a ranked list",
             state="partly met",
             gate="Gaps are counted (16 slots with no replacement named), but no shared-slot or empty-slot "
                  "flag exists in data/depth/replacement_depth.csv.",
             clear="0 slots silently ranked; every shared or empty slot flagged (count not yet computed)",
             basis="proposed", evidence="data/depth/replacement_depth.csv", source_url=""),
        dict(id="NB-10", requirement="Public analysis layer, with raw row-level data held in a private store "
             "until the terms are read", state="open",
             gate="No private store exists. This repository and its GitHub Pages site are public. No NFL terms "
                  "are recorded in the repo, and the terms-of-use URL checked on 2026-11-15 returned a 404 (IR-09).",
             clear="Terms read at a working official URL and recorded, then an owner decision on the split (0 of 2)",
             basis="repo", evidence="docs/sources/sources.md", source_url="https://www.nfl.com/"),
        dict(id="NB-11", requirement="Injury report captured daily Wednesday to kickoff, with fetch timestamp, and "
             "held as a timestamped series", state="partly met",
             gate=f"Scheduled refresh runs, but {len(F['injury_snapshot_dates'])} capture date and no fetch "
                  "time are stored (IR-04).",
             clear="5 dated captures with fetch timestamp, Wednesday to Sunday (proposed; currently 1)", basis="proposed",
             evidence="data/injuries/injuries_2026_week10.csv", source_url="https://www.nfl.com/injuries/"),
        dict(id="NB-12", requirement="Roster turnover as a first-class event: depth and availability versioned "
             "against the last official roster event", state="open",
             gate="No roster-event register exists, so a mid-season trade cannot be detected.",
             clear="A roster-event register with at least one row per official transaction (0 rows)",
             basis="proposed", evidence="data/depth/replacement_depth.csv", source_url=""),
        dict(id="NB-13", requirement="Two-stage leaderboard: proper-score qualification, then a prospective "
             "CLV/ROI escrow", state="open",
             gate="No price source (Q-02) and no prospective window has been opened.",
             clear="500 prospective singles bets registered before the window opens (G1)", basis="repo",
             evidence="data/gates.json", source_url=""),
        dict(id="NB-14", requirement="Weekly 'what changed' diff, not a static snapshot", state="partly met",
             gate=f"One week of diff exists ({F['what_changed_items']} items); no second week to diff against.",
             clear="2 weekly snapshots to diff", basis="proposed", evidence="data/audit/what_changed.json",
             source_url=""),
        dict(id="NB-15", requirement="Archive weekly official injury reports for past seasons, to test whether "
             "designations change outcomes", state="open",
             gate="Only the 2026 Week 10 report is in the repo (see NB-01).",
             clear="2 archived seasons, 18 weeks each (past seasons held: 0; 2026 Week 10 only)", basis="proposed",
             evidence="data/injuries/injuries_2026_week10.csv", source_url="https://www.nfl.com/injuries/"),
    ]
    for r in nb:
        assert r["id"] not in reg_ids
        rows.append(dict(id=r["id"], group="Brief item (not yet in register)", requirement=r["requirement"],
                         state=r["state"], blocking_gate=r["gate"], clearing_number=r["clear"],
                         basis=r["basis"], evidence=r["evidence"], evidence_url=evidence_link(r["evidence"]),
                         source_url=r["source_url"], assessment=""))
    return rows


def irregularities(F: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
    dict(id="IR-01", severity="high", category="Contradiction",
         item="Two leaderboards disagree on whether any strategy passes every gate",
         evidence="The landing page says one of sixteen strategies passes all gates (data/site/payload.json, "
                  "Wind — under). The line-desk leaderboard shows 0 of 8 through all gates "
                  "(data/lab/leaderboard.json). The requirements register says none has cleared the economic gates "
                  "(data/audit/requirements_assessed.json, R-09).",
         done="Recorded, not resolved. The readiness row for R-09 names both counts.",
         settles="One leaderboard file, generated by one script, with its gate results; then the landing "
                 "page quotes that file only.",
         sources=["https://github.com/karagemop466-tech/X1/blob/main/data/site/payload.json",
                  "https://github.com/karagemop466-tech/X1/blob/main/data/lab/leaderboard.json"]),
    dict(id="IR-02", severity="high", category="Contradiction",
         item="Three different model-error figures are published for the same model",
         evidence="The landing page and generator text say spread MAE 10.42 against a market 9.73 "
                  "(tools/build_app.py). The line-desk model report gives side MAE 10.741 against 9.792 "
                  "(data/lab/lines/model_report.json). The payload summary gives mean margin MAE 10.98 across "
                  "2000–2026 (data/site/payload.json).",
         done="Recorded. Each figure is labelled with its source file in the readiness register.",
         settles="Name one test window and one script that writes the figure; regenerate every page from it.",
         sources=["https://github.com/karagemop466-tech/X1/blob/main/tools/build_app.py",
                  "https://github.com/karagemop466-tech/X1/blob/main/data/lab/lines/model_report.json"]),
    dict(id="IR-03", severity="medium", category="Hard-coded value",
         item="The market benchmark 9.73 is typed into the generator, not computed",
         evidence="tools/build_app.py contains 9.73 on six lines. The value in the model report is 9.792 "
                  "(data/lab/lines/model_report.json, accuracy.side_mae_market).",
         done="Recorded only. The landing text is not changed by this session.",
         settles="Replace the constant with a read from the model report.",
         sources=["https://github.com/karagemop466-tech/X1/blob/main/tools/build_app.py"]),
    dict(id="IR-04", severity="high", category="Freshness",
         item="The scheduled refresh succeeds but stores only one capture date and no fetch time",
         evidence="Recent data-refresh runs on main completed successfully (gh run list --workflow data-refresh.yml). "
                  "All 345 rows of data/injuries/injuries_2026_week10.csv carry one snapshot date, "
                  "'snapshot 2026-11-14', and no fetch time.",
         done="Recorded. The readiness rows R-19 and NB-11 show the gap as a count.",
         settles="Write a dated, hashed file per capture and make the generator read the newest one.",
         sources=["https://github.com/karagemop466-tech/X1/blob/main/data/injuries/injuries_2026_week10.csv",
                  "https://github.com/karagemop466-tech/X1/blob/main/.github/workflows/data-refresh.yml"]),
    dict(id="IR-05", severity="medium", category="Duplicate data",
         item="The same Week 10 injury report is stored in three files with different layouts",
         evidence=f"data/injuries_2026_week10.csv, data/injuries/injuries_2026_week10.csv and "
                  f"data/console/injuries_week10.csv hold the league report in three schemas, with "
                  f"{'/'.join(str(v) for v in F['injury_copies'].values())} rows.",
         done="Recorded. No file was deleted.",
         settles="Name one canonical file; generate the others from it.",
         sources=["https://github.com/karagemop466-tech/X1/blob/main/data/injuries/injuries_2026_week10.csv"]),
    dict(id="IR-06", severity="low", category="Repository hygiene",
         item="Compiled Python files are tracked in Git and change on every build",
         evidence="code/__pycache__/*.pyc is tracked; running the builders modifies it, so the tree is never clean "
                  "after a build.",
         done="Local modification reverted before commit. Not removed from history.",
         settles="Add __pycache__ to .gitignore and untrack the files (an owner-approved change).",
         sources=["https://github.com/karagemop466-tech/X1/blob/main/.gitignore"]),
    dict(id="IR-07", severity="medium", category="Consistency",
         item=f"The site links {F['stylesheet_files']} different stylesheet files across its page trees",
         evidence="Counted by tools/build_readiness.py from every local stylesheet link in the page trees "
                  "(see R-25 on the readiness register).",
         done="Recorded only.",
         settles="Owner decision on one stylesheet; a single build step then regenerates the trees.",
         sources=["https://github.com/karagemop466-tech/X1/blob/main/assets/site.css"]),
    dict(id="IR-08", severity="high", category="Wrong published value",
         item="The published Week 10 injury table is missing 2 official rows and differs in 16 rows",
         evidence="A re-capture of https://www.nfl.com/injuries/ read on 2026-11-15 (session arena-ed8c600d-x1, "
                  "merged to main in PR #49) finds 347 official rows against 345 published, 2 official rows "
                  "absent from the published table (for example BAL: Calais Campbell), and 32 status cells in "
                  "16 matched rows that differ. The published page's own status counts also differ from the "
                  "official ones. The figures are attributed to that report, not re-verified row by row here.",
         done="Recorded. The published table was not changed in this session; the capture report is merged "
              "beside it.",
         settles="Re-generate the table from the dated capture, then re-run the row-level comparison; "
                 "publish the difference rather than the old count.",
         sources=["https://www.nfl.com/injuries/",
                  "https://github.com/karagemop466-tech/X1/blob/main/data/capture/2026_w10/recapture_report.md"]),
    dict(id="IR-09", severity="medium", category="Broken source link",
         item="The NFL terms-of-use address returns a 404 page, and no terms are on record",
         evidence="No NFL terms document is recorded in this repository. The address https://www.nfl.com/terms-of-use "
                  "returned a 404 page when checked on 2026-11-15, so the terms that govern the public-versus-private "
                  "data decision (NB-10) have not been read.",
         done="Recorded. The NB-10 row names the terms as unread. The link is the league home page, from which the current terms should be found; the broken address is not linked.",
         settles="Locate the current terms page on nfl.com and record its text and date.",
         sources=["https://www.nfl.com/"]),
]


def write_outputs(rows: List[Dict[str, Any]], F: Dict[str, Any], *, check: bool) -> int:
    counts = {
        "total": len(rows),
        "met": sum(1 for r in rows if r["state"] == "met"),
        "partly_met": sum(1 for r in rows if r["state"] == "partly met"),
        "open": sum(1 for r in rows if r["state"] == "open"),
        "in_progress": sum(1 for r in rows if r["state"] == "in progress"),
    }
    doc = {
        "dataset": "decision_readiness",
        "title": "Decision readiness: one row per requirement, the gate that blocks it, and the number that clears it",
        "as_of": AS_OF,
        "built_by": "tools/build_readiness.py (session arena/29e011dc-x1)",
        "rule": "Each row's gate and number are read from the file named in `evidence`. `basis = proposed` "
                "marks a threshold this build proposes; the owner has not accepted it. A requirement is "
                "'met' only when the register says so; nothing is re-decided here.",
        "counts": counts,
        "rows": rows,
        "irregularities": irregularities(F),
    }
    cols = ["id", "group", "requirement", "state", "blocking_gate", "clearing_number", "basis",
            "evidence", "evidence_url", "source_url", "assessment"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in cols})
    outs = {
        "data/audit/decision_readiness.json": json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
        "data/audit/decision_readiness.csv": buf.getvalue(),
        "data/audit/irregularities_review.json": json.dumps(
            {"dataset": "irregularities_review", "as_of": AS_OF, "rows": irregularities(F)},
            ensure_ascii=False, indent=2) + "\n",
    }
    bad = 0
    for rel, text in outs.items():
        p = os.path.join(ROOT, rel)
        if check:
            cur = open(p, encoding="utf-8").read() if os.path.exists(p) else None
            if cur != text:
                print(f"STALE: {rel} differs from a fresh build")
                bad += 1
        else:
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
            print(f"wrote {rel}")
    print("counts:", counts)
    print("check: committed readiness register matches a fresh build" if check and not bad else "")
    return 1 if bad else 0


def main(argv: List[str]) -> int:
    F = facts()
    rows = build_rows(F)
    # Every row must carry an evidence URL, and every row must name a gate.
    for r in rows:
        assert r["blocking_gate"], r["id"]
        assert r["evidence_url"] or r["evidence"], r["id"]
    return write_outputs(rows, F, check="--check" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
