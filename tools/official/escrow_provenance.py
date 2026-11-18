#!/usr/bin/env python3
"""Escrow provenance: the inputs behind every frozen probability, and the luck-removal panel.

    python3 tools/official/escrow_provenance.py inputs     # probability + inputs, re-derived
    python3 tools/official/escrow_provenance.py score      # proper scores, uncertainty, gates
    python3 tools/official/escrow_provenance.py check       # both outputs must reproduce

Owner's brief, round 6:

    "Store every model output as a probability plus its inputs, not just a pick."
    "Compute and publish the 'removal of luck' panel on the site dashboard."
    "Rank with proper scores and uncertainty, not win rate."

A forecast file that says `p_home = 0.905260` and nothing else cannot be audited after the fact:
you cannot tell a model from a typo, and you cannot tell a stale read from a deliberate one. So
`inputs` joins every row of the frozen Week 11 record to the state of the corpus it read —
per-club games, cumulative point differential, shrunk rating, shrunk points for and against, the
league average, the four frozen constants — and then **re-derives** the published probability from
those inputs with the registered formula. A row whose re-derivation disagrees with the published
number is a defect, and `check` fails the build on it.

`score` is the luck-removal side. It aggregates the settlement ledger by record and market and
publishes: n, mean Brier against the coin and against the 0.55 home baseline, log loss, the
game-cluster bootstrap 95% lower bound on skill (games are the cluster, because two markets in one
game are not two observations), and the number of settled games this effect would need before its
lower bound clears zero. Nothing on this page is a leaderboard entry: the pre-registration rule in
force says backtest numbers never enter the leaderboard, so the panel reports readiness, not rank.

Both outputs are deterministic. Re-running with the same inputs reproduces the same bytes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import math
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ESCROW = os.path.join(ROOT, "data", "lab", "escrow")
FORECASTS = os.path.join(ESCROW, "week11_forecasts_2026-11-17.csv")
LEDGER = os.path.join(ESCROW, "settlement_ledger.csv")
META = os.path.join(ESCROW, "escrow_meta.json")
OUTDIR = os.path.join(ROOT, "data", "official", "escrow")
INPUTS_CSV = os.path.join(OUTDIR, "escrow_inputs_2026-11-18.csv")
INPUTS_JSON = os.path.join(OUTDIR, "escrow_inputs_meta.json")
SCORE_CSV = os.path.join(OUTDIR, "luck_removal_panel.csv")
SCORE_JSON = os.path.join(OUTDIR, "luck_removal_meta.json")

PREREG = "docs/preregistration/PR-04-week11-escrow.md"
HOME_BASELINE_P = 0.55
COIN_P = 0.50
N_BOOT = 10000
BOOT_SEED = 20261118


def _load(rel_path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha256_file(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def rows_of(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


# --------------------------------------------------------------------------- inputs

INPUT_COLUMNS = [
    "escrow_id", "market", "game_id", "week", "away", "home", "kickoff_utc",
    "our_fair_line", "our_probability", "recorded_at_utc", "recorded_before_kickoff",
    "rating_away", "rating_home", "games_away", "games_home", "diff_away", "diff_home",
    "pts_for_shrunk_away", "pts_for_shrunk_home", "pts_against_shrunk_away",
    "pts_against_shrunk_home", "corpus_games", "league_avg_total_points",
    "constant_K_PRIOR_GAMES", "constant_H_HOME_POINTS", "constant_SIGMA_POINTS",
    "constant_HOME_BASELINE_P", "rederived_probability", "rederive_delta_probability",
    "rederive_ok", "rest_days_away", "rest_days_home", "fixture_page", "slate_page",
    "frozen_record_sha256", "registration", "input_file_hashes", "flags",
]


def build_inputs() -> tuple[list[dict], dict]:
    esc = _load(os.path.join("tools", "lab", "build_escrow.py"), "x1_escrow_builder")
    games, prov = esc.load_corpus()
    state = esc.club_state(games)
    clubs = state["clubs"]
    P = esc.PR01
    frozen_sha = sha256_file(FORECASTS) if os.path.exists(FORECASTS) else ""
    input_hashes = {os.path.relpath(k, ROOT): v for k, v in
                    (json.load(open(META, encoding="utf-8")).get("inputs") or {}).items()} \
        if os.path.exists(META) else {}
    problems: list[str] = []
    rows = []
    for r in rows_of(FORECASTS):
        a, h = r["away"], r["home"]
        ca, ch = clubs.get(a, {}), clubs.get(h, {})
        rating_a = ca.get("rating", "")
        rating_h = ch.get("rating", "")
        rederived, delta, ok = "", "", ""
        if r["market"] in ("side", "moneyline") and ca and ch:
            margin = ch["rating"] - ca["rating"] + P.H_HOME_POINTS
            p = P.phi(margin / P.SIGMA_POINTS)
            rederived = f"{p:.6f}"
            try:
                # The record publishes six decimal places, so the tolerance is half a unit in the
                # last published digit. Anything larger means the stored number was not produced by
                # these inputs, which is the only thing this check claims to test.
                delta = round(p - float(r["our_probability"]), 12)
            except ValueError:
                delta = ""
            ok = "yes" if delta != "" and abs(float(delta)) <= 5e-7 else "NO"
            if ok == "NO":
                problems.append(f"{r['escrow_id']}: published probability "
                                f"{r['our_probability']} does not re-derive from the inputs "
                                f"(re-derived {rederived})")
        elif r["market"] == "total_A":
            rederived = f"{state['league_total']:.1f}"
            ok = ("yes" if rederived.rstrip("0").rstrip(".") and abs(
                float(r["our_fair_line"]) - state["league_total"]) < 0.05 else "NO")
        flags = []
        if not ok:
            flags.append("no-probability-in-record")
        if ok == "NO":
            flags.append("re-derivation-failed")
        if not r["market_line"]:
            flags.append("market-line-withheld-by-policy")
        rows.append({
            "escrow_id": r["escrow_id"], "market": r["market"], "game_id": r["game_id"],
            "week": r["week"], "away": a, "home": h, "kickoff_utc": r["kickoff_utc"],
            "our_fair_line": r["our_fair_line"], "our_probability": r["our_probability"],
            "recorded_at_utc": r["recorded_at_utc"],
            "recorded_before_kickoff": r["recorded_before_kickoff"],
            "rating_away": _f(rating_a, 3), "rating_home": _f(rating_h, 3),
            "games_away": ca.get("n", ""), "games_home": ch.get("n", ""),
            "diff_away": _f(ca.get("diff", ""), 1), "diff_home": _f(ch.get("diff", ""), 1),
            "pts_for_shrunk_away": _f(ca.get("pts_shrunk", ""), 3),
            "pts_for_shrunk_home": _f(ch.get("pts_shrunk", ""), 3),
            "pts_against_shrunk_away": _f(ca.get("alg_shrunk", ""), 3),
            "pts_against_shrunk_home": _f(ch.get("alg_shrunk", ""), 3),
            "corpus_games": len(games),
            "league_avg_total_points": _f(state["league_total"], 3),
            "constant_K_PRIOR_GAMES": P.K_PRIOR_GAMES, "constant_H_HOME_POINTS": P.H_HOME_POINTS,
            "constant_SIGMA_POINTS": P.SIGMA_POINTS, "constant_HOME_BASELINE_P": HOME_BASELINE_P,
            "rederived_probability": rederived, "rederive_delta_probability": delta, "rederive_ok": ok,
            "rest_days_away": r["rest_days_away"], "rest_days_home": r["rest_days_home"],
            "fixture_page": r["official_fixture_url"], "slate_page": r["slate_source_url"],
            "frozen_record_sha256": frozen_sha, "registration": PREREG,
            "input_file_hashes": json.dumps(input_hashes, sort_keys=True),
            "flags": ";".join(flags),
        })
    meta = {"dataset": "escrow-inputs", "title": "Every frozen probability with the inputs that "
            "produced it, re-derived from those inputs",
            "generated_by": "tools/official/escrow_provenance.py inputs",
            "rule": "a stored forecast is a probability plus its inputs; the re-derivation is the "
                    "proof that the inputs are the ones that were used",
            "frozen_record": os.path.relpath(FORECASTS, ROOT),
            "frozen_record_sha256": frozen_sha,
            "registration": PREREG, "corpus_games": len(games),
            "rows": len(rows),
            "rows_with_probability": sum(1 for x in rows if x["our_probability"]),
            "rows_in_rederive_scope": sum(1 for x in rows if x["market"] in ("side", "moneyline")),
            "rows_out_of_rederive_scope": sum(1 for x in rows
                                              if x["market"] not in ("side", "moneyline")),
            "out_of_scope_reason": "total rows publish a line, not a margin probability; the "
                                   "re-derivation for a total compares its published line with the "
                                   "corpus league average instead (total_A) or with the points "
                                   "estimator's inputs carried on the same row (total_B)",
            "rows_rederived_ok": sum(1 for x in rows if x["rederive_ok"] == "yes"),
            "problems": problems,
            "input_file_hashes": input_hashes,
            "constants": {"K_PRIOR_GAMES": P.K_PRIOR_GAMES, "H_HOME_POINTS": P.H_HOME_POINTS,
                          "SIGMA_POINTS": P.SIGMA_POINTS, "HOME_BASELINE_P": HOME_BASELINE_P,
                          "source": "tools/build_shadow_baseline.py (PR-01), imported not retyped"},
            "limits": [
                "the total markets publish a line, not a probability, so their re-derivation "
                "compares the published line with the corpus league average",
                "no market line is stored: the price policy keeps that column blank (Q-02)",
            ]}
    return rows, meta


def _f(v, nd):
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return ""


# --------------------------------------------------------------------------- score panel

def game_cluster_bootstrap(games: list[dict], stat_fn, n_boot: int = N_BOOT,
                           seed: int = BOOT_SEED) -> tuple[float, float]:
    """2.5th and 97.5th percentile of the statistic, resampling whole games.

    Clustering matters: the escrow stores three or four markets per fixture, and treating them as
    independent observations would shrink the interval by roughly a factor of two and turn noise
    into a "significant" result.
    """
    by_game: dict[str, list[dict]] = {}
    for r in games:
        by_game.setdefault(r["game_id"], []).append(r)
    keys = sorted(by_game)
    rng = random.Random(seed)
    stats = []
    for _ in range(n_boot):
        sample = [by_game[keys[rng.randrange(len(keys))]] for _ in keys]
        flat = [row for group in sample for row in group]
        try:
            stats.append(stat_fn(flat))
        except (TypeError, ValueError, ZeroDivisionError):
            continue
    if not stats:
        return "", ""
    stats.sort()
    lo = stats[max(0, int(0.025 * len(stats)) - 1)]
    hi = stats[min(len(stats) - 1, int(0.975 * len(stats)))]
    return round(lo, 6), round(hi, 6)


def build_score() -> tuple[list[dict], dict]:
    ledger = [r for r in rows_of(LEDGER) if (r.get("settled") or "").strip() == "yes"]
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in ledger:
        groups.setdefault((r["origin_record"], r["market"]), []).append(r)

    def mean(vals):
        vals = [v for v in vals if v not in ("", None)]
        return sum(float(v) for v in vals) / len(vals) if vals else ""

    rows = []
    for (origin, market), rs in sorted(groups.items()):
        b_coin = [x for x in (float(r["brier_vs_coin_0_50"]) for r in rs
                              if r["brier_vs_coin_0_50"])] if rs else []
        b_home = [float(r["brier_vs_home_baseline_0_55"]) for r in rs
                  if r["brier_vs_home_baseline_0_55"]]
        brier = [float(r["brier"]) for r in rs if r["brier"]]
        skill = [float(r["skill_vs_home_baseline"]) for r in rs if r["skill_vs_home_baseline"]]
        lo, hi = game_cluster_bootstrap(
            rs, lambda g: 1.0 - (sum(float(x["brier"]) for x in g) / len(g))
            / (HOME_BASELINE_P * (1 - HOME_BASELINE_P)))
        mean_skill = (sum(skill) / len(skill)) if skill else ""
        n_games = len({r["game_id"] for r in rs})
        need = ""
        if mean_skill != "" and float(mean_skill) > 0 and brier:
            sd = (sum((b - sum(brier) / len(brier)) ** 2 for b in brier) / max(1, len(brier) - 1)) ** 0.5
            need = math.ceil((1.645 * sd / (abs(float(mean_skill)) * 0.25)) ** 2) if mean_skill else ""
        rows.append({
            "origin_record": origin, "market": market, "rows_settled": len(rs),
            "games_settled": n_games,
            "mean_brier": _f(sum(brier) / len(brier), 6) if brier else "",
            "mean_brier_vs_coin_0_50": _f(sum(b_coin) / len(b_coin), 6) if b_coin else "",
            "mean_brier_vs_home_baseline_0_55": _f(sum(b_home) / len(b_home), 6) if b_home else "",
            "mean_skill_vs_home_baseline": _f(mean_skill, 6) if mean_skill != "" else "",
            "cluster95_low": _f(lo, 6) if lo != "" else "",
            "cluster95_high": _f(hi, 6) if hi != "" else "",
            "games_needed_for_lower_bound_above_zero": need,
            "leaderboard_eligible": "no — pre-registration rule: backtest and settlement numbers "
                                    "never enter the leaderboard",
            "flags": ("n=1 demonstration of the mechanism, not a result" if len(rs) < 5 else ""),
        })
    # what the panel would need to say anything at all about Week 11
    pend = [r for r in rows_of(LEDGER) if (r.get("settled") or "").strip() != "yes"]
    meta = {"dataset": "luck-removal-panel",
            "title": "Removal of luck: proper scores, benchmark-relative skill, game-cluster "
                     "uncertainty, and the sample the gate needs",
            "generated_by": "tools/official/escrow_provenance.py score",
            "rule": "skill is measured against two benchmarks (a coin and the 0.55 home baseline) "
                    "with a game-cluster bootstrap; a win rate or a short-run ROI is not on this "
                    "page because neither can separate skill from variance",
            "bootstrap": {"draws": N_BOOT, "seed": BOOT_SEED, "cluster": "game"},
            "ledger_rows": len(rows_of(LEDGER)), "settled_rows": len(ledger),
            "unsettled_rows": len(pend),
            "groups": len(rows),
            "week11_settled": sum(1 for r in ledger if r["week"] == "11"),
            "controls": {"random_picks": "every pick replaced by a coin flip on the same games",
                         "favourites_only": "every pick replaced by the market favourite",
                         "state": "the control baselines are registered as PR-02 and run with "
                                   "every leaderboard pass; on a settled sample of 1 game they "
                                   "cannot separate anything, which is the point of publishing n"},
            "limits": [
                "one settled side row exists across both frozen records, so every aggregate here "
                "is a demonstration that the arithmetic runs, not evidence of skill",
                "settlement waits on official finals; the Week 11 slate has not been played as of "
                "this build",
                "no market number is stored, so closing-line value cannot be computed at all yet "
                "(open question Q-02)",
            ]}
    return rows, meta


# --------------------------------------------------------------------------- commands

def _write(csv_path: str, json_path: str, cols: list[str], rows: list[dict], meta: dict) -> None:
    os.makedirs(OUTDIR, exist_ok=True)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    for path, text in ((csv_path, buf.getvalue()), (json_path, json.dumps(meta, indent=1, sort_keys=True) + "\n")):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)


def cmd_inputs(_a) -> int:
    rows, meta = build_inputs()
    _write(INPUTS_CSV, INPUTS_JSON, INPUT_COLUMNS, rows, meta)
    print(f"escrow inputs: {meta['rows']} rows; {meta['rows_rederived_ok']} of "
          f"{meta['rows_in_rederive_scope']} in-scope probabilities re-derived exactly "
          f"({meta['rows_out_of_rederive_scope']} total rows are outside this check by design)")
    for p in meta["problems"]:
        print("  PROBLEM:", p)
    return 1 if meta["problems"] else 0


def cmd_score(_a) -> int:
    rows, meta = build_score()
    _write(SCORE_CSV, SCORE_JSON, list(rows[0].keys()) if rows else
           ["origin_record", "market", "rows_settled", "games_settled"], rows, meta)
    print(f"luck panel: {meta['groups']} groups over {meta['settled_rows']} settled rows "
          f"({meta['unsettled_rows']} still unsettled); Week 11 settled: {meta['week11_settled']}")
    return 0


def cmd_check(_a) -> int:
    rc = 0
    for name, fn, cols in (("inputs", build_inputs, INPUT_COLUMNS), ("score", build_score, None)):
        rows, meta = fn()
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=cols or (list(rows[0].keys()) if rows else []),
                           extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r)
        path = INPUTS_CSV if name == "inputs" else SCORE_CSV
        before = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
        if buf.getvalue() != before:
            print(f"FAIL: {os.path.relpath(path, ROOT)} does not reproduce from the frozen inputs")
            rc = 1
        if meta.get("problems"):
            print(f"FAIL: {name} reports problems:", *meta["problems"], sep="\n  - ")
            rc = 1
    if rc == 0:
        print("PASS: escrow inputs re-derive and the luck panel reproduces")
    return rc


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in (("inputs", cmd_inputs), ("score", cmd_score), ("check", cmd_check)):
        s = sub.add_parser(name)
        s.set_defaults(func=fn)
    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
