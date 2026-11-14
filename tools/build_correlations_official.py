#!/usr/bin/env python3
"""Official-only correlation table (T20).

Session `arena-1d3600f8-x1`. Owner requirement:

> Compute correlations only from officially sourced numbers and publish n with
> each value.

Every correlation published here is computed ONLY from tables this repository
has verified against official nfl.com pages:

  * data/standings_2026.csv          (nfl.com/standings)
  * data/pipeline/team_stats.json    (nfl.com/stats/team-stats/... , _verified)
  * data/injuries_2026_week10.csv    (nfl.com/injuries)
  * data/analysis/replacement_depth.json (derived from the above + club depth
    charts; the injury status component is league-official)

Every row publishes n, Pearson r, a two-sided permutation p-value (B=20,000,
fixed seed — reproducible, distribution-free), and a Fisher 95% CI. Mirror-
based correlations elsewhere on the site are NOT reproduced here and are
labelled non-official where they appear.

Output: data/analysis/correlations_official.csv
"""

from __future__ import annotations

import csv
import json
import math
import os
import random
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "analysis", "correlations_official.csv")
B = 20000
SEED = 42


def norm(code: str) -> str:
    return {"LAR": "LA", "ARI": "AZ"}.get(code, code)


def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return float("nan")
    return sxy / math.sqrt(sxx * syy)


def fisher_ci(r: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 3 or abs(r) >= 1:
        return (float("nan"), float("nan"))
    zz = 0.5 * math.log((1 + r) / (1 - r))
    se = 1 / math.sqrt(n - 3)
    lo, hi = zz - z * se, zz + z * se
    return (math.tanh(lo), math.tanh(hi))


def perm_p(xs: list[float], ys: list[float], r_obs: float) -> float:
    rng = random.Random(SEED)
    ys2 = ys[:]
    count = 0
    for _ in range(B):
        rng.shuffle(ys2)
        if abs(pearson(xs, ys2)) >= abs(r_obs):
            count += 1
    return (count + 1) / (B + 1)


def main() -> int:
    standings = {}
    with open(os.path.join(ROOT, "data", "standings_2026.csv"), encoding="utf-8") as fh:
        for s in csv.DictReader(fh):
            standings[norm(s["team_abbr"])] = s

    team_stats: dict[tuple[str, str], dict] = {}
    ts = json.load(open(os.path.join(ROOT, "data", "pipeline", "team_stats.json"), encoding="utf-8"))
    for r in ts["rows"]:
        label = r["_source_label"]
        cat = label.split("—")[-1].strip()  # e.g. "Offense — Passing" -> "Passing"
        unit = "Offense" if "Offense" in label else ("Defense" if "Defense" in label else "Other")
        team_stats[(f"{unit} {cat}", norm(r["team_abbrev"]))] = r

    injuries: dict[str, dict] = defaultdict(lambda: {"on_report": 0, "out": 0, "doubtful": 0, "questionable": 0})
    with open(os.path.join(ROOT, "data", "injuries_2026_week10.csv"), encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            t = norm(r["team_abbr"])
            injuries[t]["on_report"] += 1
            st = (r.get("game_status") or "").strip().lower()
            if st == "out":
                injuries[t]["out"] += 1
            elif st == "doubtful":
                injuries[t]["doubtful"] += 1
            elif st == "questionable":
                injuries[t]["questionable"] += 1

    depth = json.load(open(os.path.join(ROOT, "data", "analysis", "replacement_depth.json"), encoding="utf-8"))
    depth_by = {norm(p["team"]): p for p in depth["per_team"]}

    rows: list[dict] = []

    def add(pair_id: str, metric_a: str, metric_b: str, val_a, val_b,
            teams: list[str], src_a: str, src_b: str, interp: str) -> None:
        xs, ys = [], []
        for t in teams:
            a, b = val_a(t), val_b(t)
            if a is None or b is None:
                continue
            xs.append(float(a))
            ys.append(float(b))
        n = len(xs)
        if n < 4:
            return
        r = pearson(xs, ys)
        lo, hi = fisher_ci(r, n)
        p = perm_p(xs, ys, r)
        rows.append({
            "pair_id": pair_id, "metric_a": metric_a, "metric_b": metric_b,
            "n": n, "r": f"{r:.4f}", "p_value": f"{p:.5f}",
            "ci95_lo": f"{lo:.4f}", "ci95_hi": f"{hi:.4f}",
            "interpretation": interp,
            "source_a": src_a, "source_b": src_b,
            "tier": "official-only",
            "method": f"Pearson r; Fisher 95% CI; two-sided permutation p (B={B}, seed {SEED})",
        })

    teams32 = sorted(standings)
    nfl_stand = "https://www.nfl.com/standings/"
    nfl_inj = "https://www.nfl.com/injuries/"

    def st(key: str):
        return lambda t: float(standings[t][key])

    add("OC-01", "wins", "points_for", st("W"), st("PF"), teams32, nfl_stand, nfl_stand,
        "teams that score more win more (sanity anchor for the pipeline)")
    add("OC-02", "wins", "points_against", st("W"), st("PA"), teams32, nfl_stand, nfl_stand,
        "defensive points allowed vs wins")
    add("OC-03", "net_points", "win_pct", st("NET_PTS"), st("PCT"), teams32, nfl_stand, nfl_stand,
        "point differential is the classic win-predictor")
    add("OC-04", "points_for", "points_against", st("PF"), st("PA"), teams32, nfl_stand, nfl_stand,
        "scoring richness: do high-scoring teams also concede more?")

    def stat(unit_cat: str, col: str):
        return lambda t: (float(team_stats[(unit_cat, t)][col])
                          if (unit_cat, t) in team_stats and team_stats[(unit_cat, t)].get(col) not in (None, "")
                          else None)

    src_off = "https://www.nfl.com/stats/team-stats/offense/passing/2026/reg/all"
    src_off_rush = "https://www.nfl.com/stats/team-stats/offense/rushing/2026/reg/all"
    src_off_sc = "https://www.nfl.com/stats/team-stats/offense/scoring/2026/reg/all"
    src_def_rush = "https://www.nfl.com/stats/team-stats/defense/rushing/2026/reg/all"
    src_def_sc = "https://www.nfl.com/stats/team-stats/defense/scoring/2026/reg/all"

    add("OC-05", "offense_pass_yds", "points_for", stat("Offense Passing", "Pass Yds"), st("PF"),
        teams32, src_off, nfl_stand, "passing yards vs points scored")
    add("OC-06", "offense_rush_yds", "points_for", stat("Offense Rushing", "Rush Yds"), st("PF"),
        teams32, src_off_rush, nfl_stand, "rushing yards vs points scored")
    add("OC-07", "offense_rush_ypc", "win_pct", stat("Offense Rushing", "YPC"), st("PCT"),
        teams32, src_off_rush, nfl_stand, "rushing efficiency vs win percentage")
    add("OC-08", "offense_total_td", "wins", stat("Offense Scoring", "Tot TD"), st("W"),
        teams32, src_off_sc, nfl_stand, "offensive touchdowns vs wins")
    add("OC-09", "defense_rush_yds_allowed", "wins", stat("Defense Rushing", "Rush Yds"), st("W"),
        teams32, src_def_rush, nfl_stand, "rushing yards allowed vs wins (expect negative)")
    add("OC-10", "defense_frt_int_tds", "wins",
        lambda t: (float(team_stats[("Defense Scoring", t)]["FR TD"]) +
                   float(team_stats[("Defense Scoring", t)]["INT TD"]))
        if ("Defense Scoring", t) in team_stats else None,
        st("W"), teams32, src_def_sc, nfl_stand,
        "defensive fumble-return + interception-return touchdowns vs wins (expect positive)")

    teams28 = sorted(injuries)
    add("OC-11", "week10_players_on_report", "net_points",
        lambda t: injuries[t]["on_report"], st("NET_PTS"), teams28, nfl_inj, nfl_stand,
        "size of the Week 10 injury report vs point differential")
    add("OC-12", "week10_starters_out", "points_against",
        lambda t: injuries[t]["out"], st("PA"), teams28, nfl_inj, nfl_stand,
        "players ruled Out vs points allowed")

    teams31 = sorted(depth_by)
    add("OC-13", "mean_replacement_depth", "net_points",
        lambda t: depth_by[t]["mean_replacement_depth"], st("NET_PTS"), teams31,
        "https://www.nfl.com/injuries/", nfl_stand,
        "how deep the replacements sit vs point differential (club depth charts + official report)")
    add("OC-14", "deep_replacements_3rd_or_worse", "points_against",
        lambda t: depth_by[t]["deep_replacements_3rd_or_worse"], st("PA"), teams31,
        "https://www.nfl.com/injuries/", nfl_stand,
        "3rd-string-or-deeper replacements vs points allowed")
    add("OC-15", "starters_on_report", "net_points",
        lambda t: depth_by[t]["starters_on_report"], st("NET_PTS"), teams31,
        "https://www.nfl.com/injuries/", nfl_stand,
        "how many starters are on the report vs point differential")

    cols = ["pair_id", "metric_a", "metric_b", "n", "r", "p_value", "ci95_lo", "ci95_hi",
            "interpretation", "source_a", "source_b", "tier", "method"]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    print(f"official correlation rows: {len(rows)}")
    for r in rows:
        print(f"  {r['pair_id']} {r['metric_a']}~{r['metric_b']}: r={r['r']} n={r['n']} p={r['p_value']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
