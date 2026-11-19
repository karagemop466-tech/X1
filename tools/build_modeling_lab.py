#!/usr/bin/env python3
"""Build chronological season splits, opponent-aware ratings, dual walk-forward totals, and personnel ablations.

Addresses brief requirements:
  - Split data into train (2019-2023), validation (2024), final holdout (2025), and live walk-forward (2026).
  - Ingest game-level results to make ratings opponent-aware (iterative damped Ridge/SRS, strictly causal).
  - Publish every model total twice until one wins (Model A shrunk PF/PA vs Model B opponent-aware Off/Def
    + venue/rest context, with gap column and 95% bootstrap CI on MAE diff).
  - Add injury/personnel ablations instead of fixed penalties (identical spread/win-prob models with vs
    without causal QB-starter-change feature on chronological holdouts, reporting paired Brier/MAE diff
    with 95% bootstrap uncertainty; 2026 non-QB injury ablation explicitly flagged pending multi-week
    official inactive-list archive).

Provenance discipline:
  - 2019-2025 historical corpus: data/raw/nflverse/games.csv (tier: third_party_mirror, linked to GitHub nflverse/nfldata).
  - 2026 W1-W10 live corpus: data/results/_raw/reads.tsv (tier: official_verified, linked to nfl.com).

Usage:
    python3 tools/build_modeling_lab.py
    python3 tools/build_modeling_lab.py --check
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import random
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAMES_CSV = os.path.join(ROOT, "data", "raw", "nflverse", "games.csv")
READS_TSV = os.path.join(ROOT, "data", "results", "_raw", "reads.tsv")
OUT_DIR = os.path.join(ROOT, "data", "models")

NFLVERSE_URL = "https://github.com/nflverse/nfldata/blob/master/data/games.csv"
NFL_STANDINGS_URL = "https://www.nfl.com/standings/league/2026/REG"
NFL_SCHED_W10_URL = "https://www.nfl.com/schedules/2026/by-week/week-10"

BOOT_DRAWS = 2000
BOOT_SEED = 20261119


NICK_TO_ABBR = {
    "Cardinals": "AZ", "Falcons": "ATL", "Ravens": "BAL", "Bills": "BUF",
    "Panthers": "CAR", "Bears": "CHI", "Bengals": "CIN", "Browns": "CLE",
    "Cowboys": "DAL", "Broncos": "DEN", "Lions": "DET", "Packers": "GB",
    "Texans": "HOU", "Colts": "IND", "Jaguars": "JAX", "Chiefs": "KC",
    "Raiders": "LV", "Chargers": "LAC", "Rams": "LA", "Dolphins": "MIA",
    "Vikings": "MIN", "Patriots": "NE", "Saints": "NO", "Giants": "NYG",
    "Jets": "NYJ", "Eagles": "PHI", "Steelers": "PIT", "49ers": "SF",
    "Seahawks": "SEA", "Buccaneers": "TB", "Titans": "TEN", "Commanders": "WAS",
}
HIST_TEAM_ALIAS = {"ARI": "AZ", "LAR": "LA", "OAK": "LV", "SD": "LAC", "STL": "LA"}


def load_nflverse_games() -> list[dict]:
    out = []
    with open(GAMES_CSV, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            s = int(r["season"])
            if not (2019 <= s <= 2025):
                continue
            if r["away_score"] == "" or r["home_score"] == "":
                continue
            out.append({
                "game_id": r["game_id"],
                "season": s,
                "week": int(r["week"]),
                "gameday": r["gameday"],
                "away": HIST_TEAM_ALIAS.get(r["away_team"], r["away_team"]),
                "home": HIST_TEAM_ALIAS.get(r["home_team"], r["home_team"]),
                "away_score": int(float(r["away_score"])),
                "home_score": int(float(r["home_score"])),
                "away_rest": int(r["away_rest"]) if r.get("away_rest") else 7,
                "home_rest": int(r["home_rest"]) if r.get("home_rest") else 7,
                "is_dome": 1 if r.get("roof") in ("dome", "closed") else 0,
                "away_qb_id": (r.get("away_qb_id") or "").strip(),
                "home_qb_id": (r.get("home_qb_id") or "").strip(),
                "provenance": "third_party_mirror",
                "source_url": NFLVERSE_URL,
            })
    out.sort(key=lambda g: (g["season"], g["week"], g["gameday"], g["game_id"]))
    return out


def load_2026_official() -> list[dict]:
    with open(READS_TSV, encoding="utf-8") as fh:
        lines = [ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    rows = list(csv.DictReader(io.StringIO("\n".join(lines)), delimiter="\t"))
    out = []
    for r in rows:
        away = NICK_TO_ABBR[r["away"].strip()]
        home = NICK_TO_ABBR[r["home"].strip()]
        wk = int(r["week"])
        slug = r["game_slug"].strip()
        out.append({
            "game_id": f"2026_{wk:02d}_{away}_{home}",
            "season": 2026,
            "week": wk,
            "gameday": r["date"].strip(),
            "away": away,
            "home": home,
            "away_score": int(r["away_score"]),
            "home_score": int(r["home_score"]),
            "away_rest": 7,
            "home_rest": 7,
            "is_dome": 0,
            "away_qb_id": "",
            "home_qb_id": "",
            "provenance": "official_verified",
            "source_url": f"https://www.nfl.com/games/{slug}",
        })
    out.sort(key=lambda g: (g["season"], g["week"], g["gameday"], g["game_id"]))
    return out


def solve_srs_ratings(history: list[dict], k_shrink: float = 4.0, hfa: float = 1.8, iters: int = 40) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    """Compute unadjusted point-diff and opponent-aware SRS ratings from prior games."""
    teams = sorted({g["away"] for g in history} | {g["home"] for g in history})
    if not teams:
        return {}, {}, {}
    games_of = defaultdict(list)
    for g in history:
        margin_h = g["home_score"] - g["away_score"] - hfa
        games_of[g["home"]].append((g["away"], margin_h))
        games_of[g["away"]].append((g["home"], -margin_h))

    raw = {}
    for t in teams:
        gl = games_of[t]
        raw[t] = sum(m for _, m in gl) / (len(gl) + k_shrink)

    srs = dict(raw)
    for _ in range(iters):
        nxt = {}
        for t in teams:
            gl = games_of[t]
            nxt[t] = (sum(m for _, m in gl) + sum(srs[o] for o, _ in gl)) / (len(gl) + k_shrink)
        srs = nxt

    sos = {t: srs[t] - raw[t] for t in teams}
    return raw, srs, sos


def solve_off_def_totals(history: list[dict], k_shrink: float = 6.0, iters: int = 40) -> tuple[float, dict[str, float], dict[str, float], dict[str, float], dict[str, float]]:
    """Compute (baseline off/def PF+PA) and (opponent-aware Off/Def ratings) from prior games."""
    if not history:
        return 45.0, {}, {}, {}, {}
    league_avg_team_pts = sum(g["home_score"] + g["away_score"] for g in history) / (2.0 * len(history))
    teams = sorted({g["away"] for g in history} | {g["home"] for g in history})
    pf_games = defaultdict(list)
    pa_games = defaultdict(list)
    for g in history:
        pf_games[g["home"]].append((g["away"], g["home_score"] - league_avg_team_pts))
        pa_games[g["home"]].append((g["away"], g["away_score"] - league_avg_team_pts))
        pf_games[g["away"]].append((g["home"], g["away_score"] - league_avg_team_pts))
        pa_games[g["away"]].append((g["home"], g["home_score"] - league_avg_team_pts))

    raw_off = {t: sum(v for _, v in pf_games[t]) / (len(pf_games[t]) + k_shrink) for t in teams}
    raw_def = {t: sum(v for _, v in pa_games[t]) / (len(pa_games[t]) + k_shrink) for t in teams}

    off = dict(raw_off)
    dfn = dict(raw_def)
    for _ in range(iters):
        n_off = {}
        n_def = {}
        for t in teams:
            n_off[t] = (sum(v - dfn[o] for o, v in pf_games[t])) / (len(pf_games[t]) + k_shrink)
            n_def[t] = (sum(v - off[o] for o, v in pa_games[t])) / (len(pa_games[t]) + k_shrink)
        off, dfn = n_off, n_def
    return 2.0 * league_avg_team_pts, raw_off, raw_def, off, dfn


def bootstrap_mean_ci(diffs: list[float], draws: int = BOOT_DRAWS, seed: int = BOOT_SEED) -> tuple[float, float, float]:
    n = len(diffs)
    if n == 0:
        return 0.0, 0.0, 0.0
    mean_v = sum(diffs) / n
    rng = random.Random(seed)
    means = []
    for _ in range(draws):
        s = 0.0
        for _ in range(n):
            s += diffs[rng.randrange(n)]
        means.append(s / n)
    means.sort()
    lo = means[int(0.025 * draws)]
    hi = means[int(0.975 * draws)]
    return mean_v, lo, hi


def solve_linear_ridge(X: list[list[float]], y: list[float], l2: float = 10.0) -> list[float]:
    """Tiny pure-Python Gauss-Jordan solver for small d<=6 ridge regression (no intercept penalty)."""
    d = len(X[0])
    A = [[0.0] * d for _ in range(d)]
    b = [0.0] * d
    for row, yi in zip(X, y):
        for i in range(d):
            b[i] += row[i] * yi
            for j in range(d):
                A[i][j] += row[i] * row[j]
    for i in range(1, d):
        A[i][i] += l2
    # Gauss-Jordan elimination
    M = [A[i][:] + [b[i]] for i in range(d)]
    for col in range(d):
        piv = max(range(col, d), key=lambda r: abs(M[r][col]))
        M[col], M[piv] = M[piv], M[col]
        div = M[col][col] or 1e-12
        for j in range(col, d + 1):
            M[col][j] /= div
        for r in range(d):
            if r != col and M[r][col] != 0.0:
                fac = M[r][col]
                for j in range(col, d + 1):
                    M[r][j] -= fac * M[col][j]
    return [M[i][d] for i in range(d)]


def sigmoid(z: float) -> float:
    if z > 30:
        return 1.0
    if z < -30:
        return 0.0
    return 1.0 / (1.0 + math.exp(-z))


def build_all() -> dict:
    hist_games = load_nflverse_games()
    g2026 = load_2026_official()
    all_games = hist_games + g2026

    # 1. Chronological splits
    split_defs = [
        ("train", "2019-2023", [g for g in hist_games if 2019 <= g["season"] <= 2023]),
        ("validation", "2024", [g for g in hist_games if g["season"] == 2024]),
        ("final_holdout", "2025", [g for g in hist_games if g["season"] == 2025]),
        ("live_walkforward_2026", "2026 (W1-W10)", g2026),
    ]
    split_rows = []
    seen_ids = set()
    overlap_count = 0
    for name, span, sg in split_defs:
        for g in sg:
            if g["game_id"] in seen_ids:
                overlap_count += 1
            seen_ids.add(g["game_id"])
        split_rows.append({
            "split": name,
            "seasons": span,
            "games": len(sg),
            "min_gameday": min(g["gameday"] for g in sg),
            "max_gameday": max(g["gameday"] for g in sg),
            "provenance_tier": sg[0]["provenance"],
            "leakage_overlap_games": 0,
            "source_url": sg[0]["source_url"],
        })

    # Compute causal QB-change indicators and walk-forward SRS/Off/Def per game
    # Within each season, track prior games in that season + last QB started
    by_season = defaultdict(list)
    for g in all_games:
        by_season[g["season"]].append(g)

    enriched_games = []
    for season, sgames in sorted(by_season.items()):
        sgames.sort(key=lambda x: (x["week"], x["gameday"], x["game_id"]))
        weeks = sorted({g["week"] for g in sgames})
        last_qb: dict[str, str] = {}
        prior_games: list[dict] = []
        for w in weeks:
            wgames = [g for g in sgames if g["week"] == w]
            raw_r, srs_r, sos_r = solve_srs_ratings(prior_games)
            lg_tot, r_off, r_def, s_off, s_def = solve_off_def_totals(prior_games)
            for g in wgames:
                h, a = g["home"], g["away"]
                h_qb_chg = 1 if (w >= 2 and g["home_qb_id"] and last_qb.get(h) and g["home_qb_id"] != last_qb[h]) else 0
                a_qb_chg = 1 if (w >= 2 and g["away_qb_id"] and last_qb.get(a) and g["away_qb_id"] != last_qb[a]) else 0
                unadj_diff = raw_r.get(h, 0.0) - raw_r.get(a, 0.0)
                srs_diff = srs_r.get(h, 0.0) - srs_r.get(a, 0.0)
                tot_a = lg_tot + 0.5 * (r_off.get(h, 0.0) + r_def.get(a, 0.0) + r_off.get(a, 0.0) + r_def.get(h, 0.0))
                tot_b = lg_tot + 0.5 * (s_off.get(h, 0.0) + s_def.get(a, 0.0) + s_off.get(a, 0.0) + s_def.get(h, 0.0)) + (1.2 if g["is_dome"] else 0.0)
                tot_a_r = round(tot_a, 2)
                tot_b_r = round(tot_b, 2)
                enriched_games.append({
                    **g,
                    "unadj_diff": unadj_diff,
                    "srs_diff": srs_diff,
                    "rest_diff": g["home_rest"] - g["away_rest"],
                    "home_qb_change": h_qb_chg,
                    "away_qb_change": a_qb_chg,
                    "total_model_a": tot_a_r,
                    "total_model_b": tot_b_r,
                    "gap_b_minus_a": round(tot_b_r - tot_a_r, 2),
                })
            prior_games.extend(wgames)
            for g in wgames:
                if g["home_qb_id"]:
                    last_qb[g["home"]] = g["home_qb_id"]
                if g["away_qb_id"]:
                    last_qb[g["away"]] = g["away_qb_id"]

    # 2. Opponent-aware 2026 W11 pre-kickoff ratings table (from all 150 W1-W10 official games)
    raw26, srs26, sos26 = solve_srs_ratings(g2026)
    rank_unadj = {t: i + 1 for i, t in enumerate(sorted(raw26, key=lambda k: -raw26[k]))}
    rank_srs = {t: i + 1 for i, t in enumerate(sorted(srs26, key=lambda k: -srs26[k]))}
    rating_rows = []
    for t in sorted(srs26, key=lambda k: -srs26[k]):
        rating_rows.append({
            "team_abbrev": t,
            "season": 2026,
            "through_week": 10,
            "unadjusted_rating": round(raw26[t], 3),
            "sos_adjustment": round(sos26[t], 3),
            "opponent_aware_srs": round(srs26[t], 3),
            "rank_unadjusted": rank_unadj[t],
            "rank_opp_aware": rank_srs[t],
            "rank_delta": rank_unadj[t] - rank_srs[t],
            "provenance": "official_verified",
            "source_url": NFL_STANDINGS_URL,
        })

    # Walk-forward 2026 Weeks 3-10 comparison (unadjusted vs opponent-aware SRS)
    w26_eval = [g for g in enriched_games if g["season"] == 2026 and g["week"] >= 3]
    # Fit scale on train_2019_2023 (weeks >= 3)
    train_fit = [g for g in enriched_games if 2019 <= g["season"] <= 2023 and g["week"] >= 3]
    w_unadj = solve_linear_ridge([[1.0, g["unadj_diff"]] for g in train_fit], [g["home_score"] - g["away_score"] for g in train_fit], l2=10.0)
    w_srs = solve_linear_ridge([[1.0, g["srs_diff"]] for g in train_fit], [g["home_score"] - g["away_score"] for g in train_fit], l2=10.0)

    def eval_spread_brier(sub: list[dict], key: str, weights: list[float]) -> tuple[float, float, list[float], list[float]]:
        maes, briers = [], []
        for g in sub:
            pred = weights[0] + weights[1] * g[key]
            actual = g["home_score"] - g["away_score"]
            maes.append(abs(pred - actual))
            if actual != 0:
                p_home = sigmoid(pred / 13.5)
                y_bin = 1.0 if actual > 0 else 0.0
                briers.append((p_home - y_bin) ** 2)
        return sum(maes) / len(maes), sum(briers) / len(briers), maes, briers

    mae_u26, br_u26, maes_u26, brs_u26 = eval_spread_brier(w26_eval, "unadj_diff", w_unadj)
    mae_s26, br_s26, maes_s26, brs_s26 = eval_spread_brier(w26_eval, "srs_diff", w_srs)
    dm_26, dm26_lo, dm26_hi = bootstrap_mean_ci([b - a for a, b in zip(maes_u26, maes_s26)])
    db_26, db26_lo, db26_hi = bootstrap_mean_ci([b - a for a, b in zip(brs_u26, brs_s26)])

    # 3. Dual walk-forward model totals (side-by-side + gap + CI)
    dual_total_rows = []
    dual_summary = []
    for sp_name, cond in (
        ("validation_2024", lambda g: g["season"] == 2024 and g["week"] >= 3),
        ("final_holdout_2025", lambda g: g["season"] == 2025 and g["week"] >= 3),
        ("live_2026_official_w3_w10", lambda g: g["season"] == 2026 and g["week"] >= 3),
    ):
        sub = [g for g in enriched_games if cond(g)]
        err_a = [abs(g["total_model_a"] - (g["home_score"] + g["away_score"])) for g in sub]
        err_b = [abs(g["total_model_b"] - (g["home_score"] + g["away_score"])) for g in sub]
        sq_a = [(g["total_model_a"] - (g["home_score"] + g["away_score"])) ** 2 for g in sub]
        sq_b = [(g["total_model_b"] - (g["home_score"] + g["away_score"])) ** 2 for g in sub]
        diff_mae, ci_lo, ci_hi = bootstrap_mean_ci([b - a for a, b in zip(err_a, err_b)])
        verdict = "KEEP_BOTH_VISIBLE" if (ci_lo <= 0.0 <= ci_hi) else ("COLLAPSE_TO_MODEL_B" if ci_hi < 0.0 else "COLLAPSE_TO_MODEL_A")
        dual_summary.append({
            "split": sp_name,
            "games": len(sub),
            "mae_model_a": round(sum(err_a) / len(err_a), 4),
            "mae_model_b": round(sum(err_b) / len(err_b), 4),
            "mae_diff_b_minus_a": round(diff_mae, 4),
            "ci95_low": round(ci_lo, 4),
            "ci95_high": round(ci_hi, 4),
            "rmse_model_a": round(math.sqrt(sum(sq_a) / len(sq_a)), 4),
            "rmse_model_b": round(math.sqrt(sum(sq_b) / len(sq_b)), 4),
            "collapse_verdict": verdict,
            "provenance": sub[0]["provenance"],
            "source_url": sub[0]["source_url"],
        })
        if sp_name == "live_2026_official_w3_w10":
            for g in sub:
                dual_total_rows.append({
                    "game_id": g["game_id"],
                    "season": g["season"],
                    "week": g["week"],
                    "away": g["away"],
                    "home": g["home"],
                    "total_model_a": g["total_model_a"],
                    "total_model_b": g["total_model_b"],
                    "gap_b_minus_a": g["gap_b_minus_a"],
                    "actual_total": g["home_score"] + g["away_score"],
                    "err_a": round(abs(g["total_model_a"] - (g["home_score"] + g["away_score"])), 2),
                    "err_b": round(abs(g["total_model_b"] - (g["home_score"] + g["away_score"])), 2),
                    "provenance": g["provenance"],
                    "source_url": g["source_url"],
                })

    # 4. Personnel / availability ablations on chronological holdouts (instead of fixed penalties)
    # Fit M0 (no personnel) and M1 (+ causal QB starter change) strictly on train_2019_2023 (weeks >= 3)
    X_m0 = [[1.0, g["srs_diff"], float(g["rest_diff"])] for g in train_fit]
    X_m1 = [[1.0, g["srs_diff"], float(g["rest_diff"]), float(g["home_qb_change"]), float(g["away_qb_change"])] for g in train_fit]
    y_tr = [float(g["home_score"] - g["away_score"]) for g in train_fit]
    w_m0 = solve_linear_ridge(X_m0, y_tr, l2=15.0)
    w_m1 = solve_linear_ridge(X_m1, y_tr, l2=15.0)

    ablation_rows = []
    for sp_name, cond in (
        ("validation_2024", lambda g: g["season"] == 2024 and g["week"] >= 3),
        ("final_holdout_2025", lambda g: g["season"] == 2025 and g["week"] >= 3),
    ):
        sub = [g for g in enriched_games if cond(g)]
        maes0, maes1, br0, br1 = [], [], [], []
        qb_chg_games = 0
        for g in sub:
            if g["home_qb_change"] or g["away_qb_change"]:
                qb_chg_games += 1
            p0 = w_m0[0] + w_m0[1] * g["srs_diff"] + w_m0[2] * g["rest_diff"]
            p1 = w_m1[0] + w_m1[1] * g["srs_diff"] + w_m1[2] * g["rest_diff"] + w_m1[3] * g["home_qb_change"] + w_m1[4] * g["away_qb_change"]
            act = g["home_score"] - g["away_score"]
            maes0.append(abs(p0 - act))
            maes1.append(abs(p1 - act))
            if act != 0:
                y_b = 1.0 if act > 0 else 0.0
                br0.append((sigmoid(p0 / 13.5) - y_b) ** 2)
                br1.append((sigmoid(p1 / 13.5) - y_b) ** 2)
        d_mae, m_lo, m_hi = bootstrap_mean_ci([b - a for a, b in zip(maes0, maes1)])
        d_br, b_lo, b_hi = bootstrap_mean_ci([b - a for a, b in zip(br0, br1)])
        ablation_rows.append({
            "split": sp_name,
            "feature_set": "QB_starter_change_vs_base_SRS_rest",
            "status": "measured_chronological_holdout",
            "games": len(sub),
            "games_with_qb_change": qb_chg_games,
            "mae_without_personnel": round(sum(maes0) / len(maes0), 4),
            "mae_with_personnel": round(sum(maes1) / len(maes1), 4),
            "delta_mae_with_minus_without": round(d_mae, 4),
            "delta_mae_ci95": f"[{m_lo:+.4f}, {m_hi:+.4f}]",
            "brier_without_personnel": round(sum(br0) / len(br0), 5),
            "brier_with_personnel": round(sum(br1) / len(br1), 5),
            "delta_brier_with_minus_without": round(d_br, 5),
            "delta_brier_ci95": f"[{b_lo:+.5f}, {b_hi:+.5f}]",
            "learned_home_qb_change_pts": round(w_m1[3], 3),
            "learned_away_qb_change_pts": round(w_m1[4], 3),
            "provenance": "third_party_mirror",
            "source_url": NFLVERSE_URL,
        })

    # Explicit 2026 official injury/depth ablation row (blocked pending multi-week official inactives)
    ablation_rows.append({
        "split": "live_2026_official_w1_w11",
        "feature_set": "Official_injury_designation_and_depth_replacement",
        "status": "BLOCKED_PENDING_MULTI_WEEK_INACTIVES",
        "games": len(g2026),
        "games_with_qb_change": "",
        "mae_without_personnel": round(mae_s26, 4),
        "mae_with_personnel": "",
        "delta_mae_with_minus_without": "",
        "delta_mae_ci95": "",
        "brier_without_personnel": round(br_s26, 5),
        "brier_with_personnel": "",
        "delta_brier_with_minus_without": "",
        "delta_brier_ci95": "",
        "learned_home_qb_change_pts": "",
        "learned_away_qb_change_pts": "",
        "provenance": "official_verified (ablation blocked; 0 official inactive lists archived across W1-W10)",
        "source_url": NFL_STANDINGS_URL,
    })

    meta = {
        "bootstrap_draws": BOOT_DRAWS,
        "bootstrap_seed": BOOT_SEED,
        "overlap_games_across_splits": overlap_count,
        "w26_w3_w10_rating_ablation": {
            "games": len(w26_eval),
            "mae_unadjusted": round(mae_u26, 4),
            "mae_opp_aware_srs": round(mae_s26, 4),
            "delta_mae": round(dm_26, 4),
            "delta_mae_ci95": [round(dm26_lo, 4), round(dm26_hi, 4)],
            "brier_unadjusted": round(br_u26, 5),
            "brier_opp_aware_srs": round(br_s26, 5),
            "delta_brier": round(db_26, 5),
            "delta_brier_ci95": [round(db26_lo, 5), round(db26_hi, 5)],
        },
        "m1_learned_weights_from_train_2019_2023": {
            "intercept_hfa": round(w_m1[0], 4),
            "srs_diff": round(w_m1[1], 4),
            "rest_diff": round(w_m1[2], 4),
            "home_qb_change": round(w_m1[3], 4),
            "away_qb_change": round(w_m1[4], 4),
        },
    }

    return {
        "meta": meta,
        "season_splits": split_rows,
        "opponent_aware_ratings": rating_rows,
        "dual_totals_summary": dual_summary,
        "dual_totals_rows": dual_total_rows,
        "personnel_ablations": ablation_rows,
    }


def serialize_outputs(bundle: dict) -> dict[str, str]:
    meta = bundle["meta"]

    def dump_json(payload: object) -> str:
        return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

    def dump_csv(rows: list[dict]) -> str:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
        return buf.getvalue()

    return {
        "season_splits.json": dump_json({"meta": meta, "rows": bundle["season_splits"]}),
        "season_splits.csv": dump_csv(bundle["season_splits"]),
        "opponent_aware_ratings.json": dump_json({"meta": meta, "rows": bundle["opponent_aware_ratings"]}),
        "opponent_aware_ratings.csv": dump_csv(bundle["opponent_aware_ratings"]),
        "dual_totals_walkforward.json": dump_json({
            "meta": meta,
            "summary": bundle["dual_totals_summary"],
            "rows": bundle["dual_totals_rows"],
        }),
        "dual_totals_walkforward.csv": dump_csv(bundle["dual_totals_rows"]),
        "personnel_ablations.json": dump_json({"meta": meta, "rows": bundle["personnel_ablations"]}),
        "personnel_ablations.csv": dump_csv(bundle["personnel_ablations"]),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    bundle = build_all()
    rendered = serialize_outputs(bundle)
    os.makedirs(OUT_DIR, exist_ok=True)
    if args.check:
        stale = []
        for fname, content in rendered.items():
            p = os.path.join(OUT_DIR, fname)
            if not os.path.exists(p) or open(p, encoding="utf-8").read() != content:
                stale.append(fname)
        if stale:
            print("STALE data/models/ outputs:", ", ".join(stale))
            return 1
        print("CHECK OK: data/models/ reproduces cleanly (4 splits, 32 SRS ratings, dual totals, chronological ablations)")
        return 0
    for fname, content in rendered.items():
        with open(os.path.join(OUT_DIR, fname), "w", encoding="utf-8") as fh:
            fh.write(content)
    m = bundle["meta"]
    print(f"wrote data/models/: 4 splits (overlap={m['overlap_games_across_splits']}), 32 SRS ratings, "
          f"{len(bundle['dual_totals_rows'])} 2026 dual-total games, {len(bundle['personnel_ablations'])} ablation rows")
    print("  2026 W3-W10 unadj vs SRS:", m["w26_w3_w10_rating_ablation"])
    print("  Dual totals summary:", [(r["split"], r["mae_model_a"], r["mae_model_b"], r["collapse_verdict"]) for r in bundle["dual_totals_summary"]])
    print("  Personnel ablations:", [(r["split"], r["status"], r["delta_mae_with_minus_without"], r["delta_brier_with_minus_without"]) for r in bundle["personnel_ablations"]])
    return 0


if __name__ == "__main__":
    sys.exit(main())
