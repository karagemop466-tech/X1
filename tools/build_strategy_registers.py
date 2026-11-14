#!/usr/bin/env python3
"""T13-T17 — strategy registers (reproducible).

Writes:
- data/lines/leaderboard_split.json   (T13 signal vs staking)
- data/lines/replacement_depth.json   (T14 depth of the replacement, 2nd/3rd/4th string)
- data/lines/correlation_official.json (T15 official-only correlations with n per value)
- data/lines/demotion_gate.json       (T16 gate definition sending live strategies back to paper)
- data/lines/decisions_delta.json     (T17 question/decision register delta)
- data/lines/suggestions_delta.json   (T17 suggestions register delta)
"""
import csv
import json
import os
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAYLOAD = os.path.join(ROOT, "data/site/payload.json")
DEFIC = os.path.join(ROOT, "data/verify/deficiency_recomputed.json")
DEPTH = os.path.join(ROOT, "data/pipeline/depth_charts.json")
CORR = os.path.join(ROOT, "data/pipeline/correlations.json")
CORR_RPT = os.path.join(ROOT, "data/lines/correlation_report.csv")
LEAD = os.path.join(ROOT, "data/pipeline/leaderboard.json")
FEED = os.path.join(ROOT, "data/lines/results_feed.json")
OUTD = os.path.join(ROOT, "data/lines")

SNAP = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
NO_OFFICIAL_PRICES = ("No official NFL source publishes betting prices (F-06); "
                      "price-derived numbers are third-party research.")


def scrub(x):
    """Recursively replace NaN/inf with None so allow_nan=False JSON is clean."""
    if isinstance(x, float) and (x != x or x in (float("inf"), float("-inf"))):
        return None
    if isinstance(x, dict):
        return {k: scrub(v) for k, v in x.items()}
    if isinstance(x, list):
        return [scrub(v) for v in x]
    return x


def w(name, obj):
    path = os.path.join(OUTD, name)
    json.dump(scrub(obj), open(path, "w"), indent=1, allow_nan=False)
    print(f"wrote {path}")


def build_leaderboard_split(payload):
    rows = []
    luck_by = {l["strategy"]: l for l in payload["luck"]}
    for e in payload["leaderboard"]:
        key = e["key"]
        lk = luck_by.get(key, {})
        signal = {
            "bets_settled": e["bets"],
            "hit_rate": round(e["hit_rate"], 4) if e.get("hit_rate") is not None else None,
            "flat_stake_roi": round(e["roi"], 4) if e.get("roi") is not None else None,
            "flat_stake_profit_units": round(e["profit"], 3) if e.get("profit") is not None else None,
            "ci95": [round(e["ci_lo"], 4), round(e["ci_hi"], 4)] if e.get("ci_lo") is not None else None,
            "p_value_skill_le_0": round(e["p_value"], 4) if e.get("p_value") is not None else None,
            "roi_luck_removed": round(lk["clean_games"]["roi"], 4) if lk.get("clean_games") else None,
            "luck_profit_share": round(lk["luck_profit_share"], 3) if lk.get("luck_profit_share") is not None else None,
            "luck_rule": ("wins reaching 28-0 in 2026, cover after 28-0, or win with losing net yards "
                          "and turnover margin <= 0 are luck and excluded"),
            "stability_share_positive": e.get("stability", {}).get("share_positive"),
            "seasons": e.get("seasons"),
            "flats_only": True,
            "flats_note": "Every signal metric is flat-stake (1 unit per settled signal); staking is scored separately below.",
        }
        staking = {
            "staked_roi": None, "bankroll_growth": None, "max_drawdown": None,
            "stakes": [], "status": "no stakes recorded",
            "note": ("No strategy is live and none has ever been staked under recorded stake sizing; "
                     "staking metrics stay blank until real stakes exist. A lucky staking run can "
                     "never mask a bad signal because the two blocks are scored independently."),
        }
        rows.append({
            "key": key, "name": e["name"], "family": e.get("family"),
            "signal": signal, "staking": staking,
            "gates": e.get("gates", []), "failed_gates": e.get("failed_gates", []),
            "confidence": round(e["confidence"], 3) if e.get("confidence") is not None else None,
            "reward_units": round(e["reward"], 3) if e.get("reward") is not None else None,
            "flags": ["research dataset on fingerprinted mirror inputs (not official prices)"],
        })
    out = {
        "dataset": "leaderboard_split",
        "title": "Strategy leaderboard — signal block and staking block scored separately",
        "generated_at": SNAP,
        "source": {
            "url": "https://github.com/nflverse/nfldata",
            "label": "Research lab (code/pipeline_lab.py) over fingerprinted nflverse/nfldata; results feed 2026 official",
            "organization": "this repository + nflverse",
            "retrieved_at": SNAP,
            "official": False,
            "note": NO_OFFICIAL_PRICES,
        },
        "columns": [
            ("signal.flat_stake_roi", "number", "Flat 1-unit ROI — pure signal quality"),
            ("signal.roi_luck_removed", "number", "ROI after the recorded luck rule removes lucky wins"),
            ("signal.ci95", "list", "95% CI of flat ROI"),
            ("staking.staked_roi", "number|null", "ROI under recorded stake sizing — blank until stakes exist"),
        ],
        "rows": rows,
        "verification": {
            "rows": len(rows), "rows_verified": 0, "rows_flagged": len(rows),
            "unverified_cells": sum(1 for r in rows for k in ("staked_roi", "bankroll_growth", "max_drawdown")
                                    if r["staking"][k] is None),
            "flagged_reasons": [NO_OFFICIAL_PRICES,
                                "staking metrics blank: no stakes recorded yet (by design)"],
        },
        "note": ("Signal and staking are separated so a lucky staking run cannot mask a bad signal. "
                 "All current numbers are flat-stake signal metrics from the research dataset; the "
                 "staking block fills only from real recorded stakes."),
    }
    w("leaderboard_split.json", out)


def build_replacement_depth(defic, depth_charts):
    chart = depth_charts["rows"]
    by_pos = {}
    for r in chart:
        by_pos.setdefault((r["team_abbrev"], r["unit"], r["position"]), []).append(r)
    for v in by_pos.values():
        v.sort(key=lambda r: r["depth"])

    rows = []
    for r in defic["rows"]:
        if (r.get("severity") or 0) < 1:
            continue  # healthy starter — no deficiency to record
        depth = r.get("replacement_depth")
        chart_rows = by_pos.get((r["team_abbrev"], r["unit"], r["position"]), [])
        repl = r.get("replacement")
        if depth is None and repl:
            for cr in chart_rows:
                if cr["player"] == repl:
                    depth = cr["depth"]
                    break
        rows.append({
            "team": r["team_abbrev"], "unit": r["unit"], "position": r["position"],
            "starter": r["starter"], "starter_status": r.get("starter_game_status"),
            "replacement": repl,
            "replacement_depth": depth,
            "depth_label": (f"{depth}{'th' if depth not in (2,3) else ('nd' if depth == 2 else 'rd')} string"
                            if depth else None),
            "depth_drop": (depth - 1) if depth else None,
            "severity": r.get("severity"),
            "source_depth_chart": r.get("source_depth_chart"),
            "source_injury": r.get("source_injury"),
            "flags": (["no replacement listed on club depth chart — blank, not inferred"]
                      if depth is None else
                      ["depth order read exactly as the club prints it"]),
        })

    def rollup(unit):
        c = {}
        for r in rows:
            if unit and r["unit"] != unit:
                continue
            k = r["depth_label"] or "not listed"
            c[k] = c.get(k, 0) + 1
        return c

    out = {
        "dataset": "replacement_depth",
        "title": "Replacement depth — 2nd/3rd/4th-string replacements tracked by position",
        "generated_at": SNAP,
        "source": {
            "url": "https://www.nfl.com/teams/",
            "label": "Official club depth charts + official injury reports (Week 10, 2026-11-14)",
            "organization": "NFL clubs (depth charts) + NFL (injury reports)",
            "retrieved_at": SNAP,
            "official": True,
            "note": "Depth order is read left to right exactly as each club prints its chart.",
        },
        "columns": [
            ("replacement_depth", "int|null", "2, 3 or 4 = club-printed string of the replacement; blank when the club chart lists none"),
            ("depth_drop", "int|null", "Strings dropped from starter to replacement"),
            ("severity", "int", "1 = Questionable, 2 = Doubtful, 3 = Out (official game status)"),
        ],
        "rows": rows,
        "rollup_by_unit": {"Defense": rollup("Defense"), "Offense": rollup("Offense"),
                           "Special Teams": rollup("Special Teams")},
        "verification": {
            "rows": len(rows),
            "rows_verified": sum(1 for r in rows if r["replacement_depth"] is not None),
            "rows_flagged": sum(1 for r in rows if r["replacement_depth"] is None),
            "unverified_cells": sum(1 for r in rows if r["replacement_depth"] is None),
            "flagged_reasons": ["club chart lists no replacement at the position (HOU charts unparseable — F-03)"],
        },
        "note": ("Every deficiency records the DEPTH of the replacement (2nd/3rd/4th string), not "
                 "merely that a replacement happened. Where the club chart is unparseable (Houston, "
                 "F-03) the depth stays blank and is published on the flagged-for-review page."),
    }
    w("replacement_depth.json", out)


def build_correlation_official(payload):
    corr = json.load(open(CORR))
    official_rows = corr["rows"]
    for r in official_rows:
        r.setdefault("flags", [])
    # research rows: pairwise (n=shared_games), same-game/cross-game (n recorded)
    pairwise = []
    for p in payload["correlations"]["pairwise"]:
        pairwise.append({
            "strategy_a": p["strategy_a"], "strategy_b": p["strategy_b"],
            "value": round(p["correlation"], 4), "n": p["shared_games"],
            "unit": "strategy P&L correlation (research dataset)",
            "flags": ["third-party research dataset", "not decision-usable"],
        })
    same_game = []
    for r in csv.DictReader(open(CORR_RPT, newline="")):
        same_game.append({
            "metric": r["metric"], "value": r["value"], "n": r["n"],
            "detail": r["ci_or_detail"],
            "flags": ["third-party research dataset (fingerprinted mirror)", "not decision-usable"],
        })
    matrix = payload["correlations"]["matrix"]
    matrix_rows = []
    names = list(matrix.keys())
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            matrix_rows.append({
                "strategy_a": a, "strategy_b": b,
                "value": round(matrix[a][b], 4), "n": None,
                "n_status": "not recorded in source payload",
                "flags": ["per-cell n not recorded in source", "suppressed from decisions"],
            })
    out = {
        "dataset": "correlation_official",
        "title": "Correlations — official numbers first; every value published with n",
        "generated_at": SNAP,
        "source": {
            "url": "https://www.nfl.com/stats/season-stats",
            "label": "Official NFL regular-season stats + standings (2026, through Week 9)",
            "organization": "National Football League",
            "retrieved_at": SNAP,
            "official": True,
            "note": "Official team-level correlations are the only decision-usable set. "
                    + NO_OFFICIAL_PRICES,
        },
        "columns": [
            ("value", "number", "Correlation value"),
            ("n", "int|null", "Sample size behind the value — published with every value; null = source recorded none"),
            ("flags", "list", "Provenance flags; 'not decision-usable' marks research-only rows"),
        ],
        "official": {
            "rows": official_rows,
            "count": len(official_rows),
            "note": ("Team-level correlations computed from official per-game numbers only "
                     "(nfl.com season stats). Every row carries n (weeks 1-8 complete-week cells). "
                     "WAS 3-5-1 and NYG 5-3-1 are carry-over cells shared with 2025 records — "
                     "flagged, not filled."),
        },
        "research": {
            "pairwise_strategy": pairwise,
            "same_game_cross_game_prop": same_game,
            "matrix": matrix_rows,
            "note": ("Computed from the fingerprinted nflverse/nfldata mirror and research P&L — "
                     "third-party. Retained for steering only; never cited in live decisions."),
        },
        "verification": {
            "rows": len(official_rows) + len(pairwise) + len(same_game) + len(matrix_rows),
            "rows_verified": len(official_rows),
            "rows_flagged": len(pairwise) + len(same_game) + len(matrix_rows),
            "unverified_cells": len(matrix_rows),
            "flagged_reasons": [NO_OFFICIAL_PRICES,
                                "matrix cells carry no per-cell n in the source payload"],
        },
        "note": ("Requirement: correlations computed only from officially sourced numbers, with n "
                 "published next to each value. The official block satisfies both. Research blocks "
                 "publish their n where the source recorded one; where it did not, the cell shows "
                 "n = not recorded and is suppressed from decisions rather than published bare."),
    }
    w("correlation_official.json", out)


def build_demotion_gate():
    out = {
        "dataset": "demotion_gate",
        "title": "Demotion gate — a live strategy goes back to paper when any trigger fires",
        "generated_at": SNAP,
        "gate_id": "G-13",
        "scope": "every strategy with live (real-stake) status",
        "status": "pre-registered and armed; no strategy is live yet",
        "triggers": [
            {"id": "D-1", "name": "Skill reversal",
             "rule": "after >= 30 settled live signals: flat-stake live ROI < -5% AND one-sided t-test p < 0.10 that skill <= 0",
             "rationale": "flat-stake measure stops staking luck from hiding signal decay", "n_min": 30},
            {"id": "D-2", "name": "Closing-line collapse",
             "rule": "mean closing-line value < 0 over the last 50 settled live signals",
             "rationale": "beating the close is the least noisy skill marker",
             "n_min": 50, "blocked": "requires opening prices — Q-02 open"},
            {"id": "D-3", "name": "Drawdown",
             "rule": "flat-stake bankroll drawdown > 25% from peak over any rolling 50 settled signals",
             "rationale": "tail risk the CI does not show"},
            {"id": "D-4", "name": "Source integrity breach",
             "rule": "any week in which > 10% of the strategy's input rows lose official sourcing (gate G-01 breach)",
             "rationale": "data integrity is a single source of truth", "n_min": 1},
        ],
        "process": {
            "on_fire": ["strategy status set to paper (from live)", "stakes voided at next settle",
                        "entry on the What changed page + flagged-for-review if disputed",
                        "re-qualification: 4 weeks AND >= 30 paper signals at flat stake beating 0 ROI with CI covering nothing worse than -5%"],
            "authority": "pipeline gates job (data/pipeline/gates.json) — owner notified, veto via repository issue",
        },
        "threshold_provenance": ("Thresholds are defaults pre-registered by this session per the owner "
                                 "instruction 'define a demotion gate that sends a live strategy back to "
                                 "paper'; numeric values are proposals on the suggestion board (S-20) and "
                                 "may be amended before any strategy goes live. Blank is never filled: "
                                 "triggers needing missing inputs (D-2) stay flagged until the input exists."),
        "current_evaluation": [],
        "verification": {"rows": 4, "rows_verified": 4, "rows_flagged": 1, "unverified_cells": 0,
                         "flagged_reasons": ["D-2 blocked until opening prices are sourced (Q-02)"]},
    }
    w("demotion_gate.json", out)


def build_decisions_delta():
    out = {
        "dataset": "decisions_delta",
        "title": "Questions, information and answers — delta for the decision register",
        "generated_at": SNAP,
        "delta_of": "data/pipeline/questions.json (T05)",
        "updates": [
            {"id": "Q-02", "status": "partially answered",
             "answer_now": ("What counts as 'the market' is decided pragmatically: the fingerprinted "
                            "nflverse/nfldata bookmaker line, labelled third-party on every row "
                            "(F-06). Opening vs closing is now recorded in the price-snapshot store."),
             "still_missing": "An official or licensed odds feed, and any source of opening numbers for 2026 games.",
             "unblocks": "CLV measurement and demotion trigger D-2 stay blocked; everything else moves.",
             "source_urls": ["https://github.com/nflverse/nfldata/blob/master/data/games.csv"]},
            {"id": "Q-04", "status": "answered",
             "answer_now": ("What counts as a settled result: the official score from nfl.com score "
                            "pages, Game Center box scores or official Game Book PDFs, transcribed "
                            "line by line and double-entry checked against the mirror "
                            "(137/137 matched)."),
             "still_missing": "nothing for results; weeks 10-18 settle week by week as played.",
             "unblocks": "backtests and ROI are computable at row level (data/lines/results_feed.json).",
             "source_urls": ["https://www.nfl.com/scores"]},
            {"id": "Q-26", "status": "answer proposed",
             "answer_now": ("Demotion thresholds are pre-registered in data/lines/demotion_gate.json "
                            "(G-13: skill reversal, CLV collapse, drawdown, source breach)."),
             "still_missing": "owner confirmation of the numeric thresholds (S-20 on the suggestion board).",
             "unblocks": "strategies can go live without leaving the demotion path undefined.",
             "source_urls": ["https://github.com/karagemop466-tech/X1/blob/main/data/lines/demotion_gate.json"]},
        ],
        "new_questions": [
            {"id": "Q-31", "question": "Should the project pay for a licensed odds feed (opening + closing) or stay on free third-party snapshots?",
             "known": "Free sources give one unlabelled market line and no official prices (F-06).",
             "unknown": "Budget and legality of redistribution in this repository.",
             "how_to_find": "owner decision; survey on the suggestion board (S-21).",
             "decision_unblocked": "CLV, D-2 trigger, price provenance at tier 'official-adjacent'."},
            {"id": "Q-32", "question": "Reconstruct per-cell n for the 16x16 strategy correlation matrix from bet logs, or keep the matrix suppressed from decisions?",
             "known": "The research payload records r per cell but n only for top pairs.",
             "unknown": "Whether the lab's per-bet logs are sufficient to rebuild n.",
             "how_to_find": "extend code/pipeline_lab.py to export shared_games per cell (S-22).",
             "decision_unblocked": "Matrix returns to decision use with n on every cell."},
            {"id": "Q-33", "question": "Should competition rewards stay in the cleared unit (win contribution) or convert to something tangible?",
             "known": "Owners set rewards as win-contribution units; roadmap D-3 already flags funds conversion as blocked by licensing.",
             "unknown": "Whether any prize funding exists outside the unit.",
             "how_to_find": "owner answer recorded in decisions_decided.json when it arrives.",
             "decision_unblocked": "Reward announcement wording on the leaderboard."},
        ],
        "verification": {"rows": 3 + 3, "rows_verified": 3, "rows_flagged": 3, "unverified_cells": 3,
                         "flagged_reasons": ["new questions carry unknowns; answers recorded as proposals only"]},
        "note": ("Answers are recorded only where evidence exists in this repository or on the linked "
                 "pages; nothing is inferred. Proposed answers await owner confirmation and are "
                 "visible on the flagged-for-review page meanwhile."),
    }
    w("decisions_delta.json", out)


def build_suggestions_delta():
    out = {
        "dataset": "suggestions_delta",
        "title": "Suggestions register — site and decision-making improvements, best path chosen before building",
        "generated_at": SNAP,
        "delta_of": "data/pipeline/suggestions.json (T05)",
        "suggestions": [
            {
                "id": "S-10", "topic": "price_provenance",
                "title": "Show price tier and opening/closing status on every market row",
                "problem": "Readers cannot tell official numbers from bookmaker numbers at row level.",
                "options": [
                    {"path": "A", "label": "Row-level tier chips + snapshot columns", "tradeoff": "moderate build, permanent clarity"},
                    {"path": "B", "label": "Section footers only (status quo)", "tradeoff": "cheap, keeps the ambiguity that the user flagged"},
                    {"path": "C", "label": "Drop market numbers entirely", "tradeoff": "max honesty, kills the benchmark"},
                ],
                "recommended": "A",
                "why": "The brief demands per-row sources and flags; a footer is not a source link.",
                "status": "accepted (implemented T18)",
                "owner_decision_needed": False,
            },
            {
                "id": "S-11", "topic": "leaderboard",
                "title": "Publish signal and staking as two scored blocks with luck-removed ROI",
                "problem": "A lucky staking run can mask a bad signal when ROI is one number.",
                "options": [
                    {"path": "A", "label": "Two blocks: flat-stake signal metrics + staking metrics, luck rule applied to signal", "tradeoff": "more columns, no deception"},
                    {"path": "B", "label": "Single ROI column with footnoted luck note", "tradeoff": "compact, deceptive under variance"},
                    {"path": "C", "label": "Hide ROI until n > 200", "tradeoff": "honest but empty board"},
                ],
                "recommended": "A",
                "why": "Directly what the user asked for; luck rule already defined (28-0 etc.) and now applied to the signal block.",
                "status": "accepted (implemented T18)",
                "owner_decision_needed": False,
            },
            {
                "id": "S-12", "topic": "correlations",
                "title": "Decision-usable correlation set = official numbers only, n on every value",
                "problem": "Mirror-derived correlations were mixed into the same page as official ones.",
                "options": [
                    {"path": "A", "label": "Official block first with n; research blocks flagged and suppressed from decisions", "tradeoff": "clear rule, some numbers demoted"},
                    {"path": "B", "label": "Merge all, flag inline", "tradeoff": "easy to misread in a hurry"},
                    {"path": "C", "label": "Publish official only, delete research", "tradeoff": "loses steering value"},
                ],
                "recommended": "A",
                "why": "Requirement is explicit: compute from official numbers, publish n; research stays useful but never decides.",
                "status": "accepted (implemented T18)",
                "owner_decision_needed": False,
            },
            {
                "id": "S-13", "topic": "depth",
                "title": "Track replacement depth (2nd/3rd/4th string) on every deficiency row and in rollups",
                "problem": "The register said a replacement exists but not how deep the drop was.",
                "options": [
                    {"path": "A", "label": "depth column + depth_label + per-unit rollups", "tradeoff": "small build, answers the question asked"},
                    {"path": "B", "label": "Narrative paragraph", "tradeoff": "unverifiable prose"},
                ],
                "recommended": "A", "why": "The user asked for the depth itself, tracked, not prose.",
                "status": "accepted (implemented T18)", "owner_decision_needed": False,
            },
            {
                "id": "S-14", "topic": "origination",
                "title": "Fix origination order side -> total -> moneyline and publish fair/market/difference as three columns",
                "problem": "Edges were mixed with model lines in single wide columns.",
                "options": [
                    {"path": "A", "label": "Origination ledger with explicit order + three columns", "tradeoff": "new small dataset"},
                    {"path": "B", "label": "Widen the originated_lines CSV", "tradeoff": "history breaks"},
                ],
                "recommended": "A", "why": "Keeps the existing CSV stable and gives the brief exactly the requested shape.",
                "status": "accepted (implemented T18)", "owner_decision_needed": False,
            },
            {
                "id": "S-20", "topic": "demotion_gate",
                "title": "Confirm or amend the pre-registered demotion thresholds (G-13)",
                "problem": "Thresholds were pre-registered as defaults; the owner should confirm before any strategy goes live.",
                "options": [
                    {"path": "A", "label": "Confirm defaults (D-1..D-4 as registered)", "tradeoff": "fast"},
                    {"path": "B", "label": "Tighten (e.g. D-1 n_min 50, D-3 drawdown 15%)", "tradeoff": "more churn, safer"},
                    {"path": "C", "label": "Owner supplies custom thresholds", "tradeoff": "waits on owner"},
                ],
                "recommended": "A", "why": "Defaults are conservative and pre-registered before any live result exists.",
                "status": "proposed", "owner_decision_needed": True,
            },
            {
                "id": "S-21", "topic": "price_feed",
                "title": "Decide on a licensed odds feed vs free snapshots (Q-31)",
                "problem": "No official price source exists; CLV and trigger D-2 need opening numbers.",
                "options": [
                    {"path": "A", "label": "Stay on free fingerprinted snapshots, keep F-06 flags", "tradeoff": "free, permanently tiered as third-party"},
                    {"path": "B", "label": "Budget a licensed feed", "tradeoff": "cost + redistribution rules"},
                    {"path": "C", "label": "Collect own snapshots going forward (weekly opening/close capture)", "tradeoff": "labor, builds the snapshot store honestly over time"},
                ],
                "recommended": "C with A as fallback",
                "why": "Self-collected weekly snapshots fill the opening/closing store without licensing questions.",
                "status": "proposed", "owner_decision_needed": True,
            },
        ],
        "verification": {"rows": 7, "rows_verified": 5, "rows_flagged": 2, "unverified_cells": 0,
                         "flagged_reasons": ["S-20 and S-21 await owner decision"]},
        "note": ("Each suggestion lists 2-3 paths with tradeoffs and one recommended path before "
                 "anything is implemented; implemented ones record status. The review board is the "
                 "GitHub repository Issues + Pull requests."),
    }
    w("suggestions_delta.json", out)


def main():
    payload = json.load(open(PAYLOAD))
    defic = json.load(open(DEFIC))
    depth_charts = json.load(open(DEPTH))
    build_leaderboard_split(payload)
    build_replacement_depth(defic, depth_charts)
    build_correlation_official(payload)
    build_demotion_gate()
    build_decisions_delta()
    build_suggestions_delta()


if __name__ == "__main__":
    main()
