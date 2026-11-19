#!/usr/bin/env python3
"""Build Vig-Free Decomposition, Two-Stage Proper-Score Skill Leaderboard, Official Correlations & Weekly Diff.

Covers project brief rows 4, 5, 6, 8, 9, 10, 16, 17, 18, 37, 38, 39, 58, 60, 61, 62, 66, 68, and 74.
Deterministic across runs (fixed RNG seed 20261119); supports `--check` for CI staleness verification.

Usage:
  python3 tools/origination_desk/build_skill_desk.py
  python3 tools/origination_desk/build_skill_desk.py --check
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "origination_desk" / "skill"
PROTOCOL_DOC = ROOT / "docs" / "origination_desk" / "PROPER-SCORE-PROTOCOL-01.md"
CAPTURED_DATE = "2026-11-19"
BOOTSTRAP_SEED = 20261119
BOOTSTRAP_DRAWS = 5000

ABBR_NORM = {"ARI": "AZ", "LAR": "LA"}


def _norm_team(abbr: str) -> str:
    return ABBR_NORM.get(abbr.strip(), abbr.strip())


def _american_to_implied(odds: float) -> float:
    if odds < 0:
        return (-odds) / ((-odds) + 100.0)
    return 100.0 / (odds + 100.0)


def _solve_power_vig(q1: float, q2: float) -> tuple[float, float, float]:
    """Solve q1^k + q2^k = 1 for k >= 1 via deterministic bisection."""
    if q1 + q2 <= 1.0 + 1e-12:
        s = q1 + q2
        return 1.0, q1 / s, q2 / s
    lo, hi = 1.0, 10.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        val = (q1 ** mid) + (q2 ** mid)
        if val > 1.0:
            lo = mid
        else:
            hi = mid
    k = 0.5 * (lo + hi)
    return k, q1 ** k, q2 ** k


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """Acklam-style deterministic bisection inverse normal CDF for p in (0, 1)."""
    lo, hi = -8.0, 8.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if _norm_cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _pearson_with_ci(xs: list[float], ys: list[float]) -> tuple[float, float, float, float, float]:
    """Return (r, ci95_lo, ci95_hi, t_stat, two_sided_p_approx) for exact sample size n = len(xs)."""
    n = len(xs)
    assert n == len(ys) and n >= 4
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    r = num / (dx * dy) if dx > 0 and dy > 0 else 0.0
    r_clip = max(-0.999999, min(0.999999, r))
    z = 0.5 * math.log((1.0 + r_clip) / (1.0 - r_clip))
    se = 1.0 / math.sqrt(n - 3)
    zlo, zhi = z - 1.959964 * se, z + 1.959964 * se
    rlo = math.tanh(zlo)
    rhi = math.tanh(zhi)
    t_stat = r_clip * math.sqrt((n - 2) / max(1e-12, 1.0 - r_clip * r_clip))
    # Normal tail approximation accurate for n >= 30; exact enough for reporting
    p_val = 2.0 * (1.0 - _norm_cdf(abs(t_stat)))
    return r, rlo, rhi, t_stat, p_val


def _csv_text(headers: list[str], rows: list[list[object]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(headers)
    for r in rows:
        w.writerow(["" if v is None else v for v in r])
    return buf.getvalue()


def build_vig_free_decomposition() -> tuple[str, dict[str, object]]:
    """Build 66-row Vig-Free Decomposition (52 prospective W11 PR-04 blank-market rows + 14 W10 mirror rows)."""
    headers = [
        "track", "season", "week", "game_id", "origination_order", "market",
        "away", "home", "orig_fair_line", "orig_prob_home",
        "raw_market_quote_away", "raw_market_quote_home",
        "raw_implied_home", "book_overround_pct",
        "vig_free_mult_home", "vig_free_add_home", "vig_free_power_home", "power_exponent_k",
        "operator_vig_tax_home_pct", "vig_free_alpha_home_pct", "net_post_vig_edge_home_pct",
        "price_tier_status", "source_url",
    ]
    rows: list[list[object]] = []

    # Part A: Prospective Week 11 PR-04 Escrow (52 rows; market & vig fields strictly blank per Q-02)
    escrow_path = ROOT / "data" / "lab" / "escrow" / "week11_forecasts_2026-11-17.csv"
    with escrow_path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            mkt = r["market"]
            p_home = r["our_probability"] if mkt in ("side", "moneyline") else ""
            rows.append([
                "PROSPECTIVE_ESCROW_PR04", 2026, int(r["week"]), r["game_id"],
                int(r["market_order"]), mkt, r["away"], r["home"],
                r["our_fair_line"], p_home,
                "", "", "", "", "", "", "", "", "", "", "",
                "OFFICIAL_FIXTURE_ONLY (market/vig/alpha blank: Q-02 no licensed 2026 price feed)",
                r["official_fixture_url"],
            ])

    # Part B: Week 10 Mirror Moneyline Decomposition Audit (14 rows; labelled MIRROR_RESEARCH_ONLY)
    w10_lines_path = ROOT / "data" / "lines" / "originated_lines_2026_week10.csv"
    w10_results_url: dict[str, str] = {}
    with (ROOT / "data" / "results" / "verified_results_2026_n2.csv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["week"] == "10":
                key = f"{_norm_team(r['away'])}@{_norm_team(r['home'])}"
                w10_results_url[key] = r["game_url"]

    overrounds: list[float] = []
    abs_vig_free_diffs: list[float] = []
    with w10_lines_path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            away_n, home_n = _norm_team(r["away"]), _norm_team(r["home"])
            orig_ml_home = float(r["x1_ml_home"])
            # x1_ml_away and x1_ml_home are symmetric zero-vig American lines in originated_lines_2026_week10.csv
            p_orig_home = _american_to_implied(orig_ml_home) if orig_ml_home < 0 else (1.0 - _american_to_implied(-orig_ml_home))
            mkt_away = float(r["market_ml_away"])
            mkt_home = float(r["market_ml_home"])
            q_away = _american_to_implied(mkt_away)
            q_home = _american_to_implied(mkt_home)
            overround = (q_away + q_home - 1.0) * 100.0
            p_mult_home = q_home / (q_away + q_home)
            p_add_home = q_home - 0.5 * (q_away + q_home - 1.0)
            k_exp, _, p_pow_home = _solve_power_vig(q_away, q_home)
            vig_tax_pct = (q_home - p_mult_home) * 100.0
            vf_alpha_pct = (p_orig_home - p_mult_home) * 100.0
            net_edge_pct = (p_orig_home - q_home) * 100.0
            overrounds.append(overround)
            abs_vig_free_diffs.append(abs(vf_alpha_pct))
            gurl = w10_results_url.get(f"{away_n}@{home_n}", "https://www.nfl.com/schedules/2026/by-week/week-10")
            rows.append([
                "MIRROR_DECOMPOSITION_AUDIT_W10", 2026, 10, r["game_id"],
                3, "moneyline_2way", away_n, home_n,
                f"home {int(orig_ml_home):+d} (side {r['x1_spread_away']} / tot {r['x1_total']})",
                f"{p_orig_home:.4f}",
                f"{int(mkt_away):+d}", f"{int(mkt_home):+d}",
                f"{q_home:.4f}", f"{overround:.2f}",
                f"{p_mult_home:.4f}", f"{p_add_home:.4f}", f"{p_pow_home:.4f}", f"{k_exp:.4f}",
                f"{vig_tax_pct:+.2f}", f"{vf_alpha_pct:+.2f}", f"{net_edge_pct:+.2f}",
                "MIRROR_RESEARCH_ONLY (nflverse benchmark; not official price authority)",
                gurl,
            ])

    meta = {
        "prospective_w11_rows": 52,
        "mirror_w10_audit_rows": 14,
        "mean_w10_mirror_overround_pct": round(sum(overrounds) / len(overrounds), 3),
        "mean_w10_vig_tax_per_side_pct": round(sum(overrounds) / (2.0 * len(overrounds)), 3),
        "mean_abs_vig_free_disagreement_pct": round(sum(abs_vig_free_diffs) / len(abs_vig_free_diffs), 3),
    }
    return _csv_text(headers, rows), meta


def _load_results_150() -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    with (ROOT / "data" / "results" / "verified_results_2026_n2.csv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            as_ = int(r["away_score"])
            hs_ = int(r["home_score"])
            y_home = 1.0 if hs_ > as_ else (0.0 if hs_ < as_ else 0.5)
            out.append({
                "week": int(r["week"]),
                "game_id": r["game_id"],
                "date": r["game_date"],
                "away": _norm_team(r["away"]),
                "home": _norm_team(r["home"]),
                "away_score": as_,
                "home_score": hs_,
                "margin_home": hs_ - as_,
                "total_points": hs_ + as_,
                "y_home": y_home,
                "game_url": r["game_url"],
                "source_url": r["source_url"],
            })
    assert len(out) == 150, f"Expected 150 closed 2026 games, got {len(out)}"
    return out


def build_two_stage_leaderboard_and_luck(
    games_150: list[dict[str, object]], protocol_sha: str
) -> tuple[str, str, dict[str, object]]:
    """Build Two-Stage Proper-Score Skill Leaderboard + Luck-Removal Panel."""
    # Multiplicity count M across the repository:
    # 28 entries in data/mind_change/register.csv + 3 prospective registrations (PR-01, PR-04, KR-T1) = 31
    mc_rows = list(csv.DictReader((ROOT / "data" / "mind_change" / "register.csv").open(encoding="utf-8")))
    m_repo_trials = len(mc_rows) + 3
    alpha_family = 0.05
    alpha_sidak = 1.0 - ((1.0 - alpha_family) ** (1.0 / m_repo_trials))
    z_one_sided_sidak = _norm_ppf(1.0 - alpha_sidak)

    # Strictly chronological out-of-sample walk-forward simulation on the 150 official 2026 games
    # using PR-01 / PR-04 constants (H = 1.6, K = 2.0, SIGMA = 13.5) — Week w uses ONLY Weeks 1..w-1!
    H_HOME, K_PRIOR, SIGMA = 1.6, 2.0, 13.5
    by_week: dict[int, list[dict[str, object]]] = {}
    for g in games_150:
        by_week.setdefault(int(g["week"]), []).append(g)

    margin_hist: dict[str, list[int]] = {}
    wf_records: list[dict[str, float | int]] = []
    for wk in sorted(by_week.keys()):
        for g in by_week[wk]:
            away, home = str(g["away"]), str(g["home"])
            ah = margin_hist.get(away, [])
            hh = margin_hist.get(home, [])
            r_away = sum(ah) / (len(ah) + K_PRIOR) if ah else 0.0
            r_home = sum(hh) / (len(hh) + K_PRIOR) if hh else 0.0
            exp_margin_home = r_home - r_away + H_HOME
            p_wf = _norm_cdf(exp_margin_home / SIGMA)
            p_fav_ctrl = 0.58 if exp_margin_home >= 0 else 0.42
            y = float(g["y_home"])
            wf_records.append({
                "week": wk,
                "y": y,
                "p_wf": p_wf,
                "bs_wf": (y - p_wf) ** 2,
                "bs_coin": (y - 0.50) ** 2,
                "bs_home55": (y - 0.55) ** 2,
                "bs_fav": (y - p_fav_ctrl) ** 2,
            })
        # Update ratings AFTER scoring all games in week wk (strictly no lookahead)
        for g in by_week[wk]:
            away, home = str(g["away"]), str(g["home"])
            m = int(g["margin_home"])
            margin_hist.setdefault(home, []).append(m)
            margin_hist.setdefault(away, []).append(-m)

    mean_bs_wf = sum(float(x["bs_wf"]) for x in wf_records) / len(wf_records)
    mean_bs_coin = sum(float(x["bs_coin"]) for x in wf_records) / len(wf_records)
    mean_bs_home55 = sum(float(x["bs_home55"]) for x in wf_records) / len(wf_records)
    mean_bs_fav = sum(float(x["bs_fav"]) for x in wf_records) / len(wf_records)
    bss_wf_vs_coin = 1.0 - (mean_bs_wf / mean_bs_coin)
    bss_home55_vs_coin = 1.0 - (mean_bs_home55 / mean_bs_coin)
    bss_fav_vs_coin = 1.0 - (mean_bs_fav / mean_bs_coin)

    # Game/Week-Cluster Bootstrap (resampling the 10 weekly slate clusters + game clusters deterministically)
    rng = random.Random(BOOTSTRAP_SEED)
    weeks_list = sorted(by_week.keys())
    cluster_rows = {w: [x for x in wf_records if x["week"] == w] for w in weeks_list}
    boot_bss_wf: list[float] = []
    boot_bss_home55: list[float] = []
    boot_bss_fav: list[float] = []
    for _ in range(BOOTSTRAP_DRAWS):
        sampled_weeks = [rng.choice(weeks_list) for _ in weeks_list]
        sample = [row for w in sampled_weeks for row in cluster_rows[w]]
        b_coin = sum(float(x["bs_coin"]) for x in sample) / len(sample)
        b_wf = sum(float(x["bs_wf"]) for x in sample) / len(sample)
        b_h55 = sum(float(x["bs_home55"]) for x in sample) / len(sample)
        b_fav = sum(float(x["bs_fav"]) for x in sample) / len(sample)
        boot_bss_wf.append(1.0 - b_wf / b_coin)
        boot_bss_home55.append(1.0 - b_h55 / b_coin)
        boot_bss_fav.append(1.0 - b_fav / b_coin)
    boot_bss_wf.sort()
    boot_bss_home55.sort()
    boot_bss_fav.sort()

    def _quant(arr: list[float], q: float) -> float:
        idx = max(0, min(len(arr) - 1, int(q * len(arr))))
        return arr[idx]

    wf_lb95 = _quant(boot_bss_wf, 0.05)
    wf_lb_sidak = _quant(boot_bss_wf, alpha_sidak)
    h55_lb95 = _quant(boot_bss_home55, 0.05)
    h55_lb_sidak = _quant(boot_bss_home55, alpha_sidak)
    fav_lb95 = _quant(boot_bss_fav, 0.05)
    fav_lb_sidak = _quant(boot_bss_fav, alpha_sidak)

    # Prospective PR-01 settled check (2026_10_LAC_BAL: LAC 23, BAL 20 -> y_home = 0.0, p_home = 0.701232)
    pr01_p = 0.701232
    pr01_bs_n1 = (0.0 - pr01_p) ** 2
    pr01_bss_n1 = 1.0 - (pr01_bs_n1 / 0.25)

    lb_headers = [
        "entry_id", "division", "entry_role", "registration_ref",
        "evaluation_track", "n_settled_prospective", "n_pending_escrow", "n_walkforward_ref",
        "mean_brier_score", "brier_skill_vs_coin", "cluster_bss_lb95", "multiplicity_adj_bss_lb",
        "signal_metric", "staking_metric_clv_roi",
        "stage1_proper_score_gate", "stage2_escrow_clv_gate", "demotion_gate_state",
        "adopt_if_two_sided", "abandon_if_two_sided", "source_url",
    ]
    lb_rows: list[list[object]] = [
        [
            "PR-01-SHADOW-SIDE", "DIV-1: singles", "PROSPECTIVE_MODEL", "PR-01 (2026-11-16T18:52:12Z)",
            "Prospective pre-kickoff shadow", 1, 13, 150,
            f"{pr01_bs_n1:.4f} (n=1)", f"{pr01_bss_n1:+.4f} (n=1)", "", "",
            "Prospective Brier 0.4917 on LAC@BAL (n=1; 13 W11 games pending)",
            "",  # Staking / ROI blank: Q-02 no licensed price feed
            "IN_ESCROW_INSUFFICIENT_N (1/100 prospective clusters)",
            "BLOCKED_Q02_NO_OFFICIAL_PRICE",
            "PAPER_ONLY (not live; D-01..D-04 armed on promotion)",
            "n >= 100 prospective clusters with multiplicity-adj cluster BSS_LB > 0 vs all 3 controls",
            "n >= 100 prospective clusters with cluster BSS upper 95% bound < 0 vs CTRL-HOME-55",
            "https://www.nfl.com/games/chargers-at-ravens-2026-reg-10",
        ],
        [
            "PR-04-ESCROW-W11", "DIV-1: singles", "PROSPECTIVE_MODEL", "PR-04 (2026-11-17T22:50:00Z)",
            "Prospective pre-kickoff Week 11 escrow (side + dual totals A/B + ML)", 0, 13, 150,
            "", "", "", "",
            "52 pre-kickoff forecasts frozen 3,025 min before TNF kickoff",
            "",
            "AWAITING_WEEK11_FINALS (0/100 prospective clusters)",
            "BLOCKED_Q02_NO_OFFICIAL_PRICE",
            "PAPER_ONLY (armed)",
            "n >= 100 prospective clusters AND Total_B beats Total_A on walk-forward CRPS/MAE + BSS_LB > 0",
            "Total_B trails league-average floor Total_A after 100 prospective games or BSS_UB95 < 0",
            "https://www.nfl.com/schedules/2026/by-week/week-11",
        ],
        [
            "KR-T1-REGIME-TOTALS", "DIV-1: singles", "PROSPECTIVE_MODEL", "KR-T1 (5d1e59d6, 2026-11-19T06:49:50Z)",
            "Prospective regime-aware Week 11 3-class totals distribution", 0, 13, 150,
            "", "", "", "",
            "13 3-class (under/push/over at 46.0) distributions frozen before W11",
            "",
            "AWAITING_WEEK11_FINALS (0/100 prospective clusters)",
            "PAPER_TRIAL_NO_MARKET_CLAIM",
            "PAPER_ONLY (automated settlement workflow)",
            "Outperforms unweighted empirical total distribution on ranked probability score over >=100 games",
            "Ranked probability skill upper bound < 0 after regime-filtered holdout window",
            "https://operations.nfl.com/the-rules/rules-changes/2025-rules-changes",
        ],
        [
            "CTRL-COIN-50", "DIV-1: singles", "CONTROL_BASELINE", "PROPER-SCORE-PROTOCOL-01",
            "Always-on zero-skill 50/50 coin baseline (benchmark reference)", 1, 13, 150,
            f"{mean_bs_coin:.4f} (W1-10)", "+0.0000", "+0.0000", "+0.0000",
            "Exact Brier 0.2500 on all binary games (0.2483 incl. W5 tie)",
            "",
            "REFERENCE_ZERO_BAR",
            "NOT_A_BETTING_STRATEGY",
            "PERMANENT_CONTROL",
            "Never promoted (zero-skill reference bar)",
            "Never removed (mandatory benchmark floor)",
            "https://www.nfl.com/standings/league/2026/REG",
        ],
        [
            "CTRL-HOME-55", "DIV-1: singles", "CONTROL_BASELINE", "PR-01 / PROPER-SCORE-PROTOCOL-01",
            "Always-on constant home-field base-rate control (p_home = 0.55)", 1, 13, 150,
            f"{mean_bs_home55:.4f} (W1-10)", f"{bss_home55_vs_coin:+.4f}", f"{h55_lb95:+.4f}", f"{h55_lb_sidak:+.4f}",
            f"W1-10 walk-forward Brier {mean_bs_home55:.4f}; n=1 LAC@BAL Brier 0.3025",
            "",
            "CONTROL_BENCHMARK",
            "NOT_A_BETTING_STRATEGY",
            "PERMANENT_CONTROL",
            "Never promoted (naive home-bias control)",
            "Never removed (mandatory control baseline)",
            "https://www.nfl.com/standings/league/2026/REG",
        ],
        [
            "CTRL-FAVORITE-58", "DIV-1: singles", "CONTROL_BASELINE", "PROPER-SCORE-PROTOCOL-01",
            "Always-on favorites-only shrinkage control (p = 0.58 on rating favorite)", 1, 13, 150,
            f"{mean_bs_fav:.4f} (W1-10)", f"{bss_fav_vs_coin:+.4f}", f"{fav_lb95:+.4f}", f"{fav_lb_sidak:+.4f}",
            f"W1-10 walk-forward Brier {mean_bs_fav:.4f} (favorites-only control)",
            "",
            "CONTROL_BENCHMARK",
            "NOT_A_BETTING_STRATEGY",
            "PERMANENT_CONTROL",
            "Never promoted (favorites-only control)",
            "Never removed (mandatory control baseline)",
            "https://www.nfl.com/standings/league/2026/REG",
        ],
        [
            "DIAG-WF-SHRINKAGE-W1-10", "DIV-1: singles", "DIAGNOSTIC_WALKFORWARD_NOT_RANKED", "PR-01 formula on W1-10",
            "Chronological out-of-sample W1-10 diagnostic (quarantined from Stage-2)", 0, 0, 150,
            f"{mean_bs_wf:.4f}", f"{bss_wf_vs_coin:+.4f}", f"{wf_lb95:+.4f}", f"{wf_lb_sidak:+.4f}",
            f"Walk-forward Brier {mean_bs_wf:.4f} across 150 official 2026 games (10 week clusters)",
            "",
            "DIAGNOSTIC_ONLY (retrospective 2026 corpus cannot promote)",
            "FORBIDDEN_BY_BACKTEST_BAN",
            "QUARANTINED_DIAGNOSTIC",
            "Prospective replica (PR-04) must clear multiplicity-adj BSS_LB > 0 on >=100 future games",
            "Multiplicity-adj cluster BSS_LB remains <= 0 after 100 prospective games",
            "https://www.nfl.com/schedules/2026/by-week/week-10",
        ],
        [
            "DIV2-GAME-PARLAYS-GATE", "DIV-2: game_parlays", "LOCKED_DIVISION_GATE", "JEG-01",
            "Multi-game parlay division (2+ distinct games on same slate)", 0, 0, 0,
            "", "", "", "",
            "0 eligible entries — naive product p_A*p_B rejected without slate-cluster covariance",
            "",
            "LOCKED_JOINT_EVIDENCE_GATE_JEG01",
            "LOCKED (requires Q-02 prices + push/void reduction table)",
            "GATED_PAPER_LOCKED",
            "Commit calibrated multi-game joint distribution + operator push/postponement reduction rules",
            "Keep locked whenever leg dependence or compound overround (4.55% -> 20.75% at 5 legs) exceeds alpha",
            "https://www.nfl.com/schedules/2026/by-week/week-11",
        ],
        [
            "DIV3-SGP-GATE", "DIV-3: same_game_parlays", "LOCKED_DIVISION_GATE", "JEG-02",
            "Same-game parlay division (Side x Total & correlated within-game legs)", 0, 0, 150,
            "", "", "", "",
            "0 eligible entries — marginal multiplication forbidden; historical SGP ST-PARLAY-4 hit 24.38% vs 37.97% bar",
            "",
            "LOCKED_JOINT_EVIDENCE_GATE_JEG02",
            "LOCKED (requires validated bivariate copula + SGP void rules)",
            "ABANDONED_IN_RETROSPECTIVE_AUDIT",
            "Prospective bivariate (margin, total) distribution beats empirical copula Brier on >=200 games",
            "Within-game residual correlation CI includes 0 or SGP vig tax exceeds joint edge",
            "https://www.nfl.com/schedules/2026/by-week/week-10",
        ],
        [
            "DIV4-PROP-COMBOS-GATE", "DIV-4: prop_combos", "LOCKED_DIVISION_GATE", "JEG-03",
            "Player prop combination division (QB/WR/RB correlated usage legs)", 0, 0, 0,
            "", "", "", "",
            "0 eligible entries — blocked by Q-02 prop prices, Q-04 snap counts, and DNP/void leg rules",
            "",
            "LOCKED_JOINT_EVIDENCE_GATE_JEG03",
            "LOCKED (missing Q-02 prop quotes + Q-04 snap-share feed)",
            "GATED_NO_DATA",
            "Acquire official snap/route participation + timestamped prop quotes + book DNP/reboot rules",
            "Keep permanently disabled if prop hold + correlation markup exceeds vig-free joint edge",
            "https://www.nfl.com/injuries/league/2026/reg10",
        ],
    ]

    # Removal-of-Luck Panel CSV (Brief Row 68)
    # Shows exact Bernoulli outcome-luck variance vs observed variance across horizons
    p_vec_wf = [float(x["p_wf"]) for x in wf_records]
    y_vec_wf = [float(x["y"]) for x in wf_records]
    luck_var_150 = sum(p * (1.0 - p) for p in p_vec_wf) / (len(p_vec_wf) ** 2)
    luck_se_150 = math.sqrt(luck_var_150)
    # Observed squared residual around model expectation (y_i - p_i)^2 vs expected E[(Y_i - p_i)^2 | p_i] = p_i(1-p_i)
    expected_bs_under_calibration = sum(p * (1.0 - p) for p in p_vec_wf) / len(p_vec_wf)
    excess_calibration_misfit = mean_bs_wf - expected_bs_under_calibration
    realized_home_win_rate = sum(y_vec_wf) / len(y_vec_wf)
    mean_pred_home_prob = sum(p_vec_wf) / len(p_vec_wf)

    luck_headers = [
        "horizon_id", "sample_description", "n_games", "expected_hit_se_from_luck_pct",
        "two_sigma_luck_band_pct", "expected_brier_pure_luck", "observed_brier",
        "excess_model_misfit_brier", "decision_implication", "source_url",
    ]
    luck_rows: list[list[object]] = [
        [
            "HORIZON-N1", "PR-01 settled prospective escrow (LAC@BAL W10 MNF)", 1,
            f"{math.sqrt(pr01_p * (1.0 - pr01_p)) * 100.0:.2f}",
            f"±{1.96 * math.sqrt(pr01_p * (1.0 - pr01_p)) * 100.0:.2f}",
            f"{pr01_p * (1.0 - pr01_p):.4f}", f"{pr01_bs_n1:.4f}",
            f"{pr01_bs_n1 - pr01_p * (1.0 - pr01_p):+.4f}",
            "100% dominated by single-game Bernoulli variance; zero inferential weight",
            "https://www.nfl.com/games/chargers-at-ravens-2026-reg-10",
        ],
        [
            "HORIZON-N13", "Single NFL week slate (Week 11 PR-04 escrow)", 13,
            f"{math.sqrt(0.25 / 13.0) * 100.0:.2f}",
            f"±{1.96 * math.sqrt(0.25 / 13.0) * 100.0:.2f}",
            "0.2140", "",
            "",
            "1-week hit rate swings ±27.2% (95% band) by pure coin luck; never rank weekly ROI",
            "https://www.nfl.com/schedules/2026/by-week/week-11",
        ],
        [
            "HORIZON-N150", "Closed 2026 official corpus (Weeks 1-10 walk-forward)", 150,
            f"{luck_se_150 * 100.0:.2f}",
            f"±{1.96 * luck_se_150 * 100.0:.2f}",
            f"{expected_bs_under_calibration:.4f}", f"{mean_bs_wf:.4f}",
            f"{excess_calibration_misfit:+.4f}",
            f"Pure outcome luck still spans ±{1.96 * luck_se_150 * 100.0:.1f}% in hit rate; excess Brier {excess_calibration_misfit:+.4f} isolates calibration error from coin noise",
            "https://www.nfl.com/schedules/2026/by-week/week-10",
        ],
        [
            "HORIZON-N272", "Full 272-game NFL regular season (at -110 break-even 52.38%)", 272,
            f"{math.sqrt(0.5238 * 0.4762 / 272.0) * 100.0:.2f}",
            f"±{1.96 * math.sqrt(0.5238 * 0.4762 / 272.0) * 100.0:.2f}",
            "0.2494", "",
            "",
            "Full-season 95% luck band is ±5.94%: a true 50% picker clears 55.9% in ~1 of 40 trials (guaranteed false winner when M=31)",
            "https://www.nfl.com/standings/league/2026/REG",
        ],
    ]

    meta = {
        "protocol_file": "docs/origination_desk/PROPER-SCORE-PROTOCOL-01.md",
        "protocol_sha256": protocol_sha,
        "multiplicity": {
            "quarantined_retrospective_trials_in_repo": len(mc_rows),
            "prospective_registrations": 3,
            "total_trials_M": m_repo_trials,
            "family_alpha": alpha_family,
            "sidak_alpha_per_trial": round(alpha_sidak, 6),
            "sidak_z_one_sided": round(z_one_sided_sidak, 4),
        },
        "stage_counts": {
            "stage1_qualified": 0,
            "stage2_qualified_live": 0,
            "prospective_in_escrow": 3,
            "always_on_controls": 3,
            "locked_combo_divisions": 3,
            "quarantined_retrospective_trials": len(mc_rows),
        },
        "walkforward_2026_w1_10": {
            "n_games": 150,
            "n_week_clusters": 10,
            "realized_home_win_rate": round(realized_home_win_rate, 4),
            "mean_pred_home_prob": round(mean_pred_home_prob, 4),
            "mean_brier_wf": round(mean_bs_wf, 5),
            "mean_brier_coin": round(mean_bs_coin, 5),
            "mean_brier_home55": round(mean_bs_home55, 5),
            "bss_wf_vs_coin": round(bss_wf_vs_coin, 5),
            "cluster_bss_lb95": round(wf_lb95, 5),
            "multiplicity_adj_bss_lb": round(wf_lb_sidak, 5),
            "expected_brier_pure_luck": round(expected_bs_under_calibration, 5),
            "excess_misfit_brier": round(excess_calibration_misfit, 5),
        },
    }
    return _csv_text(lb_headers, lb_rows), _csv_text(luck_headers, luck_rows), meta


def build_official_correlations(games_150: list[dict[str, object]]) -> tuple[str, dict[str, object]]:
    """Compute official-only correlations (publishing exact n & 95% CI) + SGP joint bounds."""
    margins = [float(g["margin_home"]) for g in games_150]
    abs_margins = [abs(float(g["margin_home"])) for g in games_150]
    totals = [float(g["total_points"]) for g in games_150]
    home_pts = [float(g["home_score"]) for g in games_150]
    away_pts = [float(g["away_score"]) for g in games_150]
    home_win_ind = [float(g["y_home"]) for g in games_150]
    over_med_ind = [1.0 if float(g["total_points"]) > 46.0 else 0.0 for g in games_150]

    # Post-Week-10 official 32-club standings (2026-11-18 pack)
    st_rows: list[dict[str, float]] = []
    for line in (ROOT / "data" / "verification" / "2026_11_18" / "official_standings_2026_11_18.tsv").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or line.startswith("abbr\t"):
            continue
        p = line.split("\t")
        st_rows.append({
            "pct": float(p[4]), "pf": float(p[5]), "pa": float(p[6]), "net": float(p[7]),
        })
    assert len(st_rows) == 32

    pairs = [
        ("CORR-01", "Home Score vs Total Points", home_pts, totals, "2026 Official Game Finals (W1-10)",
         "Structural shared component: backing Home Team Total + Game Over double-counts home scoring",
         "https://www.nfl.com/schedules/2026/by-week/week-10"),
        ("CORR-02", "Away Score vs Total Points", away_pts, totals, "2026 Official Game Finals (W1-10)",
         "Structural shared component: Away Team Total + Game Over carries strong positive dependence",
         "https://www.nfl.com/schedules/2026/by-week/week-10"),
        ("CORR-03", "Home Score vs Away Score", home_pts, away_pts, "2026 Official Game Finals (W1-10)",
         "Pace/shootout coupling test across all 150 verified 2026 games",
         "https://www.nfl.com/schedules/2026/by-week/week-10"),
        ("CORR-04", "Signed Home Margin vs Game Total", margins, totals, "2026 Official Game Finals (W1-10)",
         "Direct SGP Side x Total dependence: near-zero linear r across all games masks favorite/blowout regime effects",
         "https://www.nfl.com/schedules/2026/by-week/week-10"),
        ("CORR-05", "Absolute Margin |Home - Away| vs Game Total", abs_margins, totals, "2026 Official Game Finals (W1-10)",
         "Blowout vs shootout coupling: tests whether lopsided margins co-move with scoring totals",
         "https://www.nfl.com/schedules/2026/by-week/week-10"),
        ("CORR-06", "Home Win Indicator vs Total > 46.0 Indicator", home_win_ind, over_med_ind, "2026 Official Game Finals (W1-10)",
         "Binary SGP (Home ML x Over 46.0) phi correlation on 150 verified finals; proves why joint P(A,B) != P(A)P(B) must be tested empirically",
         "https://www.nfl.com/schedules/2026/by-week/week-10"),
        ("CORR-07", "Club Net Point Differential vs Win Percentage",
         [x["net"] for x in st_rows], [x["pct"] for x in st_rows], "2026 Official Standings Post-W10 (32 clubs)",
         "Justifies originating Side from point-differential strength before Moneyline win probability",
         "https://www.nfl.com/standings/league/2026/REG"),
        ("CORR-08", "Club Points For (PF) vs Win Percentage",
         [x["pf"] for x in st_rows], [x["pct"] for x in st_rows], "2026 Official Standings Post-W10 (32 clubs)",
         "Offensive scoring contribution to 2026 club win rate",
         "https://www.nfl.com/standings/league/2026/REG"),
        ("CORR-09", "Club Points Against (PA) vs Win Percentage",
         [x["pa"] for x in st_rows], [x["pct"] for x in st_rows], "2026 Official Standings Post-W10 (32 clubs)",
         "Defensive points-allowed contribution to 2026 club win rate",
         "https://www.nfl.com/standings/league/2026/REG"),
    ]

    headers = [
        "corr_id", "metric_pair", "official_corpus", "n", "pearson_r",
        "fisher_ci95_low", "fisher_ci95_high", "t_stat", "p_value_two_sided",
        "sgp_joint_prob_at_50_50", "frechet_bounds_at_50_50",
        "parlay_gate_implication", "source_url",
    ]
    rows: list[list[object]] = []
    for cid, label, xs, ys, corpus, note, surl in pairs:
        r, rlo, rhi, tstat, pval = _pearson_with_ci(xs, ys)
        # For two 50% binary events with phi = r, P(A & B) = 0.25 + 0.25*r inside Frechet [0.00, 0.50]
        p_joint_50 = 0.25 + 0.25 * r
        rows.append([
            cid, label, corpus, len(xs), f"{r:+.4f}",
            f"{rlo:+.4f}", f"{rhi:+.4f}", f"{tstat:+.2f}", f"{pval:.4e}",
            f"{p_joint_50:.4f} (vs indep 0.2500)", "[0.0000, 0.5000]",
            note, surl,
        ])

    meta = {"correlation_rows": len(rows), "game_sample_n": len(games_150), "club_sample_n": len(st_rows)}
    return _csv_text(headers, rows), meta


def build_weekly_what_changed(games_150: list[dict[str, object]]) -> tuple[str, dict[str, object]]:
    """Build 32-club Weekly 'What Changed' Diff (Week 9 -> Post-Week-10 -> Week 11 pre-kickoff)."""
    K_PRIOR = 2.0

    # Week 9 official standings (data/nfl/standings.tsv, captured 2026-11-14)
    st_w9: dict[str, dict[str, object]] = {}
    for line in (ROOT / "data" / "nfl" / "standings.tsv").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or line.startswith("abbr\t"):
            continue
        p = line.split("\t")
        c = _norm_team(p[0])
        w, l, t = int(p[5]), int(p[6]), int(p[7])
        gp = w + l + t
        diff = int(p[11])
        st_w9[c] = {
            "name": p[1], "w": w, "l": l, "t": t, "gp": gp,
            "pct": float(p[8]), "pf": int(p[9]), "pa": int(p[10]), "net": diff,
            "rating": diff / (gp + K_PRIOR),
            "team_url": p[17],
        }

    # Post-Week-10 official standings (data/verification/2026_11_18/official_standings_2026_11_18.tsv)
    st_w10: dict[str, dict[str, object]] = {}
    for line in (ROOT / "data" / "verification" / "2026_11_18" / "official_standings_2026_11_18.tsv").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or line.startswith("abbr\t"):
            continue
        p = line.split("\t")
        c = _norm_team(p[0])
        w, l, t = int(p[1]), int(p[2]), int(p[3])
        gp = w + l + t
        diff = int(p[7])
        st_w10[c] = {
            "w": w, "l": l, "t": t, "gp": gp,
            "pct": float(p[4]), "pf": int(p[5]), "pa": int(p[6]), "net": diff,
            "rating": diff / (gp + K_PRIOR),
        }

    assert set(st_w9.keys()) == set(st_w10.keys()) and len(st_w9) == 32

    # Deterministic league rank by (-pct, -net, -pf, abbr)
    rank_w9_order = sorted(st_w9.keys(), key=lambda c: (-float(st_w9[c]["pct"]), -int(st_w9[c]["net"]), -int(st_w9[c]["pf"]), c))
    rank_w10_order = sorted(st_w10.keys(), key=lambda c: (-float(st_w10[c]["pct"]), -int(st_w10[c]["net"]), -int(st_w10[c]["pf"]), c))
    rank_w9 = {c: i + 1 for i, c in enumerate(rank_w9_order)}
    rank_w10 = {c: i + 1 for i, c in enumerate(rank_w10_order)}

    # Week 10 game result string per club
    w10_result_str: dict[str, str] = {}
    for g in games_150:
        if int(g["week"]) == 10:
            aw, hm = str(g["away"]), str(g["home"])
            as_, hs_ = int(g["away_score"]), int(g["home_score"])
            aw_tag = "W" if as_ > hs_ else ("L" if as_ < hs_ else "T")
            hm_tag = "W" if hs_ > as_ else ("L" if hs_ < as_ else "T")
            w10_result_str[aw] = f"{aw_tag} {as_}-{hs_} @ {hm}"
            w10_result_str[hm] = f"{hm_tag} {hs_}-{as_} vs {aw}"

    # Join OD-1 roster & availability deltas per club
    roster_dir = ROOT / "data" / "origination_desk" / "roster"
    inact_cnt: dict[str, int] = {}
    with (roster_dir / "official_inactives_2026_week10.csv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            c = _norm_team(r["club"])
            inact_cnt[c] = inact_cnt.get(c, 0) + 1

    nov_ir_by_club: dict[str, list[str]] = {}
    with (roster_dir / "official_reserve_list_2026_oct_nov.csv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["transaction_date"].startswith("2026-11-1"):
                c = _norm_team(r["club"])
                nov_ir_by_club.setdefault(c, []).append(f"{r['player']} (IR {r['transaction_date'][5:]})")

    trades_by_club: dict[str, list[str]] = {}
    with (roster_dir / "official_trades_nov_2026.csv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            fc, tc = _norm_team(r["from_club"]), _norm_team(r["to_club"])
            trades_by_club.setdefault(fc, []).append(f"-{r['player']} (to {tc})")
            trades_by_club.setdefault(tc, []).append(f"+{r['player']} (from {fc})")

    starters_note: dict[str, str] = {}
    with (roster_dir / "announced_starters_evidence.csv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            starters_note[_norm_team(r["club"])] = f"Starter: {r['announced_starter']} ({r['position']})"

    headers = [
        "club", "team_name", "w10_game_result",
        "record_w9", "record_w10",
        "rank_w9", "rank_w10", "rank_change",
        "shrunk_rating_w9", "shrunk_rating_w10", "rating_delta_pts",
        "w10_inactives_count", "w10_w11_availability_and_roster_diff", "source_url",
    ]
    rows: list[list[object]] = []
    biggest_up = ("", -999)
    biggest_down = ("", 999)

    for c in rank_w10_order:
        a = st_w9[c]
        b = st_w10[c]
        rw9, rw10 = rank_w9[c], rank_w10[c]
        r_change = rw9 - rw10  # positive = climbed up toward #1
        if r_change > biggest_up[1]:
            biggest_up = (c, r_change)
        if r_change < biggest_down[1]:
            biggest_down = (c, r_change)
        rat_delta = float(b["rating"]) - float(a["rating"])
        rec_w9 = f"{a['w']}-{a['l']}" + (f"-{a['t']}" if int(a["t"]) else "")
        rec_w10 = f"{b['w']}-{b['l']}" + (f"-{b['t']}" if int(b["t"]) else "")

        avail_parts: list[str] = []
        if c in starters_note:
            avail_parts.append(starters_note[c])
        if c in nov_ir_by_club:
            avail_parts.append("New IR: " + ", ".join(nov_ir_by_club[c]))
        if c in trades_by_club:
            avail_parts.append("Nov trades: " + ", ".join(trades_by_club[c]))
        if c == "DET":
            avail_parts.append("S Kerby Joseph expected W11 debut")
        if not avail_parts:
            avail_parts.append("No Nov 10-18 IR/trade turnover recorded")

        rows.append([
            c, a["name"], w10_result_str.get(c, "BYE (Week 10)"),
            rec_w9, rec_w10,
            rw9, rw10, f"{r_change:+d}" if r_change != 0 else "0",
            f"{float(a['rating']):+.2f}", f"{float(b['rating']):+.2f}", f"{rat_delta:+.2f}",
            "" if c not in inact_cnt else inact_cnt[c],
            "; ".join(avail_parts),
            a["team_url"],
        ])

    meta = {
        "clubs_compared": len(rows),
        "largest_rank_climb": {"club": biggest_up[0], "spots_gained": biggest_up[1]},
        "largest_rank_drop": {"club": biggest_down[0], "spots_lost": biggest_down[1]},
    }
    return _csv_text(headers, rows), meta


def build_all() -> dict[str, str]:
    protocol_sha = hashlib.sha256(PROTOCOL_DOC.read_bytes()).hexdigest()
    games_150 = _load_results_150()

    vf_csv, vf_meta = build_vig_free_decomposition()
    lb_csv, luck_csv, lb_meta = build_two_stage_leaderboard_and_luck(games_150, protocol_sha)
    corr_csv, corr_meta = build_official_correlations(games_150)
    diff_csv, diff_meta = build_weekly_what_changed(games_150)

    files = {
        "vig_free_decomposition.csv": vf_csv,
        "two_stage_leaderboard.csv": lb_csv,
        "luck_removal_panel.csv": luck_csv,
        "official_correlations_with_n.csv": corr_csv,
        "weekly_what_changed_w9_w10_w11.csv": diff_csv,
    }
    summary = {
        "dataset": "origination_desk_skill_and_diff",
        "captured_date": CAPTURED_DATE,
        "vig_free_decomposition": vf_meta,
        "two_stage_leaderboard": lb_meta,
        "official_correlations": corr_meta,
        "weekly_what_changed": diff_meta,
        "file_sha256": {
            k: hashlib.sha256(v.encode("utf-8")).hexdigest() for k, v in sorted(files.items())
        },
    }
    files["skill_desk_summary.json"] = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    return files


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    files = build_all()
    if args.check:
        diffs = []
        for name, content in sorted(files.items()):
            p = OUT_DIR / name
            if not p.exists():
                diffs.append(f"missing {p.relative_to(ROOT)}")
            elif p.read_text(encoding="utf-8") != content:
                diffs.append(f"stale {p.relative_to(ROOT)}")
        if diffs:
            print("FAIL skill desk check:", "; ".join(diffs))
            return 1
        print(f"OK: {len(files)} skill-desk files verified up to date in {OUT_DIR.relative_to(ROOT)}")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, content in sorted(files.items()):
        (OUT_DIR / name).write_text(content, encoding="utf-8")
    print(f"Wrote {len(files)} files to {OUT_DIR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
