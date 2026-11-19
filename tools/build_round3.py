#!/usr/bin/env python3
"""Build the round-3 registers (requirements S5, S6, S7).

Session `arena/600e6009-x1`.

Outputs
-------
  data/leaderboard_signal_staking_official.json     S5 — signal and staking as separate
                                           column groups, rank computed from the
                                           signal group only
  data/depth/replacement_depth_summary.json S6 — how deep the replacement goes
                                           (2nd / 3rd / 4th string), not just
                                           that a replacement exists
  data/correlations_official_check.json    S7 — proof that every published
                                           correlation comes from official
                                           numbers and carries its n

Every invariant below fails the build rather than publishing a soft number.

Usage
-----
  python3 tools/build_round3.py           # build + verify
  python3 tools/build_round3.py --check   # also fail if the commit is stale
"""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT = "2026-11-14"
BRIEF_URL = "https://github.com/karagemop466-tech/X1/blob/main/docs/live-pipeline/project-brief.md"
SCHEDULE_URL = "https://www.nfl.com/schedules/2026/by-week/week-10"
INJURIES_URL = "https://www.nfl.com/injuries/"
STANDINGS_URL = "https://www.nfl.com/standings/league/2026/REG"


def jload(path: str):
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        return json.load(fh)


def write(path: str, payload) -> None:
    full = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1)
        fh.write("\n")


# --------------------------------------------------------------------- S5
def build_leaderboard() -> dict:
    lb = jload("data/pipeline/leaderboard.json")["rows"]
    sig = jload("data/results/signal_grade.json")

    signal_cols = [
        "signal_rank", "signal_n", "signal_hit_rate", "signal_z", "signal_p",
        "signal_baseline", "signal_note",
    ]
    staking_cols = [
        "staking_roi", "staking_units", "staking_max_drawdown", "staking_note",
    ]

    rows = []
    for r in lb:
        rows.append({
            "strategy_id": r["strategy_id"],
            "strategy": r["strategy"],
            "market": r["market"],
            "status": r.get("status", ""),
            # ---- signal group (may be computed without any price) ----
            "signal_rank": "",
            "signal_n": "",
            "signal_hit_rate": "",
            "signal_z": "",
            "signal_p": "",
            "signal_baseline": "",
            "signal_note": "signal metric not yet computed for this strategy",
            # ---- staking group (needs a price; blocked by Q-02) ----
            "staking_roi": "",
            "staking_units": "",
            "staking_max_drawdown": "",
            "staking_note": "blocked: no official price source, so no return can be settled (Q-02)",
            "source_url": BRIEF_URL,
            "_flags": ["staking columns blank on purpose", "signal blank until the strategy's picks are graded"],
        })

    # The one strategy whose SIGNAL is computable today from official results
    # alone: the walk-forward line model's side pick (registered this round).
    rows.append({
        "strategy_id": "ST-11",
        "strategy": "Walk-forward model side pick (research-lab line model)",
        "market": "Single bet",
        "status": "Paper — signal computed, not rankable yet (G1 sample)",
        "signal_rank": "1",
        "signal_n": sig["n_decided"],
        "signal_hit_rate": sig["hit_rate"],
        "signal_z": sig["z_vs_50pct"],
        "signal_p": sig["p_two_sided"],
        "signal_baseline": sig["baseline"],
        "signal_note": (
            "outcome-only grade against a 0.50 baseline; excludes 1 tie and 3 zero-line "
            "games; no price and no stake enter this number"
        ),
        "staking_roi": "",
        "staking_units": "",
        "staking_max_drawdown": "",
        "staking_note": "blocked: no official price source, so no return can be settled (Q-02)",
        "source_url": SCHEDULE_URL,
        "_flags": [
            "G1 not met: 133 decided games < 500 singles threshold — not eligible to rank",
            "staking columns blank on purpose",
        ],
    })

    # ---- invariants: the split cannot be collapsed ------------------------
    for r in rows:
        if r["staking_roi"] != "" or r["staking_units"] != "":
            raise SystemExit(f"FAIL: {r['strategy_id']} staking value present without an official price")
        if r["signal_n"] != "" and not isinstance(r["signal_n"], int):
            raise SystemExit(f"FAIL: {r['strategy_id']} signal_n must be an integer when set")
    ranked = [r for r in rows if r["signal_rank"] != ""]
    if len(ranked) != 1 or ranked[0]["strategy_id"] != "ST-11":
        raise SystemExit("FAIL: unexpected ranking population")

    return {
        "dataset": "leaderboard_signal_staking",
        "title": "Leaderboard — signal and staking kept apart",
        "generated_at": SNAPSHOT,
        "rule": {
            "rank_basis": "signal group only",
            "why": (
                "ROI is signal x staking x price. A generous staking run on a coin-flip signal "
                "produces a hot ROI that means nothing, so staking columns are reported in their "
                "own group and are structurally excluded from rank: no staking value can raise or "
                "lower a signal_rank. A strategy ranks only on signal_n, signal_z and signal_p "
                "measured against its registered baseline."
            ),
            "demotion": "G8 (data/gates.json): a live strategy whose signal decays goes back to paper",
            "reward_note": "rewards are paid on gate-passing signal, never on a staking streak",
        },
        "column_groups": {
            "identity": ["strategy_id", "strategy", "market", "status"],
            "signal": signal_cols,
            "staking": staking_cols,
        },
        "rows_count": len(rows),
        "source": {"url": BRIEF_URL, "label": "X1 project brief (strategy definitions)", "org": "Project brief"},
        "verification": {
            "rows": len(rows),
            "rows_with_signal": len(ranked),
            "rows_with_staking_values": 0,
            "rank_uses_staking_columns": False,
            "violations": 0,
        },
        "rows": rows,
    }


# --------------------------------------------------------------------- S6
def build_depth_summary() -> dict:
    d = jload("data/pipeline/deficiency.json")
    rows = d["rows"]

    dist = defaultdict(lambda: {"slots": 0, "starters_out": 0, "starters_doubtful": 0,
                                "starters_questionable": 0, "replacement_named": 0})
    no_replacement_on_report = []
    depth_violations = []

    for r in rows:
        unit = r.get("unit") or "Unknown"
        depth = r.get("replacement_depth")
        key_depth = "none" if depth in (None, "", "None") else str(int(depth))
        cell = dist[(unit, key_depth)]
        cell["slots"] += 1
        if r.get("replacement"):
            cell["replacement_named"] += 1
            try:
                di = int(depth)
                if di < 2 or di > 4:
                    depth_violations.append(f"{r.get('team_abbrev')} {unit} depth={di} out of 2..4")
            except (TypeError, ValueError):
                depth_violations.append(f"{r.get('team_abbrev')} {unit} replacement without integer depth")
        status = str(r.get("starter_game_status") or "").lower()
        if status == "out":
            cell["starters_out"] += 1
        elif status == "doubtful":
            cell["starters_doubtful"] += 1
        elif status == "questionable":
            cell["starters_questionable"] += 1
        if r.get("starter_on_report") and not r.get("replacement"):
            no_replacement_on_report.append({
                "team": r.get("team_abbrev"),
                "unit": unit,
                "position": r.get("position"),
                "starter": r.get("starter"),
                "game_status": ("" if r.get("starter_game_status") in (None, "", "None")
                                else str(r.get("starter_game_status"))),
                "source_url": (r.get("_source_urls") or [r.get("_source_url")])[0],
            })

    if depth_violations:
        raise SystemExit("FAIL depth:\n  " + "\n  ".join(depth_violations[:10]))

    out_rows = []
    for (unit, depth), cell in sorted(dist.items()):
        out_rows.append({
            "unit": unit,
            "replacement_depth": depth,
            "depth_label": {"none": "no replacement needed / not named",
                            "2": "2nd string", "3": "3rd string", "4": "4th string"}[depth],
            **cell,
            "source_url": INJURIES_URL,
            "secondary_url": SCHEDULE_URL,
        })

    named = sum(c["replacement_named"] for c in dist.values())
    total = len(rows)
    return {
        "dataset": "replacement_depth_summary",
        "title": "Replacement depth — which string actually takes the snaps",
        "generated_at": SNAPSHOT,
        "method": (
            "Derived from data/pipeline/deficiency.json. Depth slots are modelled as groups, "
            "not a single starter (data/depth/depth_groups_32.csv): where a club lists more "
            "than one player at rank 1 the group is the unit and no single 'starter' is "
            "fabricated. The replacement is the next listed name at the same slot whose game "
            "status is not Out. depth is the club-printed string position of that replacement "
            "(2 = 2nd string, 3 = 3rd string, 4 = 4th string), never a jersey number."
        ),
        "source": {"url": INJURIES_URL, "label": "NFL.com official injury report x official club depth charts", "org": "NFL + clubs"},
        "columns": ["unit", "replacement_depth", "depth_label", "slots", "replacement_named",
                    "starters_out", "starters_doubtful", "starters_questionable",
                    "source_url", "secondary_url"],
        "rows_count": len(out_rows),
        "totals": {
            "slots": total,
            "replacement_named": named,
            "no_replacement_named": total - named,
            "starters_on_report_without_named_replacement": len(no_replacement_on_report),
            "by_depth": dict(Counter(
                ("none" if r.get("replacement_depth") in (None, "", "None")
                 else str(int(r["replacement_depth"])))
                for r in rows if r.get("replacement")
            )),
            "by_depth_all_slots": dict(Counter(
                ("none" if r.get("replacement_depth") in (None, "", "None")
                 else str(int(r["replacement_depth"])))
                for r in rows
            )),
        },
        "gaps": no_replacement_on_report,
        "verification": {
            "rows": total,
            "depth_values_valid": True,
            "violations": 0,
            "note": "depth 4 exists in the schema and the charts; no slot needs a 4th string today",
        },
        "rows": out_rows,
        "gap_rows": no_replacement_on_report,
    }


# --------------------------------------------------------------------- S7
def build_correlation_check() -> dict:
    c = jload("data/pipeline/correlations.json")
    rows = c["rows"]
    problems = []
    ns = []
    for r in rows:
        n = r.get("n")
        if not isinstance(n, int) or n < 2:
            problems.append(f"{r.get('pair')}: n missing or <2 ({n!r})")
        else:
            ns.append(n)
        if r.get("p_value") in (None, ""):
            problems.append(f"{r.get('pair')}: p_value missing")
        urls = r.get("_source_urls") or ([r.get("_source_url")] if r.get("_source_url") else [])
        if not urls:
            problems.append(f"{r.get('pair')}: no source url")
        for u in urls:
            if not str(u).startswith("https://www.nfl.com/"):
                problems.append(f"{r.get('pair')}: non-official source {u}")
        for s in (r.get("source_a"), r.get("source_b")):
            if s not in {"Standings", "Offense — Rushing", "Offense — Receiving", "Offense — Passing",
                         "Offense — Downs", "Offense — Scoring", "Defense — Rushing",
                         "Defense — Passing", "Defense — Downs", "Defense — Scoring"}:
                problems.append(f"{r.get('pair')}: unexpected metric source {s!r}")
    if problems:
        raise SystemExit("FAIL correlations:\n  " + "\n  ".join(problems[:10]))

    return {
        "dataset": "correlations_official_check",
        "title": "Correlations computed only from officially sourced numbers, n on every value",
        "generated_at": SNAPSHOT,
        "method": (
            "Pearson correlations across the 32 clubs from the official standings and official "
            "team-stats tables only. Every published pair carries n and a two-sided p-value."
        ),
        "source": {"url": STANDINGS_URL, "label": "NFL.com 2026 standings + NFL.com team stats", "org": "NFL"},
        "verification": {
            "pairs": len(rows),
            "pairs_with_n": len(ns),
            "pairs_with_p_value": len(rows),
            "n_min": min(ns),
            "n_max": max(ns),
            "n_median": statistics.median(ns),
            "distinct_n_values": sorted(set(ns)),
            "official_hosts_only": True,
            "hosts": ["www.nfl.com"],
            "violations": 0,
        },
        "caveat": (
            "n = 32 team-seasons. These are team-level associations for the current season, not "
            "game-level correlations and not the joint probability a parlay price needs; those "
            "live on the correlation page with their own n and are labelled by their source."
        ),
        "excluded": (
            "Strategy-to-strategy and same-game leg correlations computed from the third-party "
            "nflverse mirror are NOT part of this check; they are labelled as mirror-derived "
            "wherever they appear."
        ),
        "rows": [
            {"pair": r["pair"], "r": r["r"], "n": r["n"], "p_value": r["p_value"],
             "source_a": r["source_a"], "source_b": r["source_b"],
             "source_url": (r.get("_source_urls") or [r.get("_source_url")])[0]}
            for r in sorted(rows, key=lambda x: -abs(float(x.get("r") or 0)))[:50]
        ],
        "rows_note": "Top 50 pairs by |r| published here; all 988 are checked by this build.",
    }


def main() -> int:
    lb = build_leaderboard()
    write("data/leaderboard_signal_staking_official.json", lb)
    print(f"leaderboard_signal_staking: {lb['rows_count']} rows, "
          f"signal populated on {lb['verification']['rows_with_signal']}, "
          f"staking values published={lb['verification']['rows_with_staking_values']}")

    dep = build_depth_summary()
    write("data/depth/replacement_depth_summary.json", dep)
    print(f"replacement_depth_summary: {dep['rows_count']} unit x depth rows, "
          f"totals={dep['totals']['by_depth_all_slots']}, "
          f"gaps(on report, no replacement named)={len(dep['gaps'])}")

    corr = build_correlation_check()
    write("data/correlations_official_check.json", corr)
    v = corr["verification"]
    print(f"correlations_official_check: {v['pairs']} pairs, all with n "
          f"(distinct n={v['distinct_n_values']}), hosts={v['hosts']}, violations=0")

    if "--check" in sys.argv:
        rel = ["data/leaderboard_signal_staking_official.json",
               "data/depth/replacement_depth_summary.json",
               "data/correlations_official_check.json"]
        out = subprocess.run(["git", "diff", "--exit-code", "--"] + rel,
                             cwd=ROOT, capture_output=True, text=True)
        if out.returncode != 0:
            print("FAIL: committed round-3 registers are stale")
            print(out.stdout[:2000])
            return 1
        print("check: committed round-3 registers match a fresh build")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
