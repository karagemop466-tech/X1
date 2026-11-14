#!/usr/bin/env python3
"""T13 - originate the side first, then the total, then the moneyline.

Run:  python3 tools/lab/build_lines.py            (tunes, then evaluates, ~3 min)
      python3 tools/lab/build_lines.py --fast     (skips the tuning sweep, uses the frozen values)

Why the order is fixed
----------------------
A moneyline is a probability, and the probability of winning is a function of the same
scoring distribution that produces the side and the total.  Originating the moneyline first
would mean inventing a probability and reverse-engineering a spread from it.  Originating it
last makes it a *consequence* of two published numbers that are already checked against the
market.  The order is therefore side -> total -> moneyline, and the moneyline section of this
file refuses to run unless the side model has been built first (see `originate_moneyline`).

The model, stated once
----------------------
A ridge-regularised opponent-adjusted rating model, refit before every week on games that
were complete before that week:

    SIDE       margin     = h_rating - a_rating + home_field
    TOTAL      total      = mu + off_home + def_away + off_away + def_home
    MONEYLINE  P(home win) = Phi(margin / sigma), tie mass split between the sides,
               converted to a vig-free American price.

Three things make this honest rather than decorative:

1. **A tuning window and a test window that do not overlap.**  Lambda is chosen on
   1999-2014 only.  It is then frozen, and every published accuracy figure comes from
   2015-2026, which the tuning never saw.
2. **A naive baseline in the same table.**  A model that cannot beat "assume the home team
   wins by 2.5" is not a model.  That comparison is published.
3. **The market in the same table.**  The market is the real opponent.  Where the model
   loses to it, the page says so in the model's own words; see `honest_verdict`.

A defect this file found in itself, kept because it is the kind of thing that silently
poisons a model: the first version applied the sample weight to the target only and not to
the design matrix.  That is not a weighted fit, it is a shrunk intercept: the published total
MAE was 28.4 points on a quantity averaging 44. The current code weights both, and
`model_report.json` carries the before/after as a recorded correction.

Outputs
-------
    data/lab/lines/fair_lines.json     every game: side, total, moneyline + market + diff
    data/lab/lines/fair_lines.csv      flat copy
    data/lab/lines/model_report.json   tuning, out-of-sample accuracy, calibration, defects
    data/lab/lines/week10_board.json   the current slate, in the owner's market order
"""

from __future__ import annotations

import json
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import (  # noqa: E402
    ROOT, SNAPSHOT, UPSTREAM_PIN, blank, num, read_csv, utcnow, write_csv, write_json,
)

TUNE_FROM, TUNE_TO = 1999, 2014        # lambda is chosen here and nowhere else
TEST_FROM, TEST_TO = 2015, 2026        # every published accuracy figure comes from here
LAMBDA_GRID = [20.0, 60.0, 120.0, 300.0]
FROZEN = {"lambda_side": 120.0, "lambda_total": 20.0}   # overwritten by the tuning pass
DECAY = 0.90
PRIOR_SEASON_WEIGHT = 0.35
MARKET_ORDER = ["SIDE", "TOTAL", "MONEYLINE"]


# ------------------------------------------------------------------ linear algebra
def solve(mat: list[list[float]], vec: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting for a small dense system."""
    n = len(vec)
    a = [row[:] + [vec[i]] for i, row in enumerate(mat)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[piv][col]) < 1e-12:
            continue
        a[col], a[piv] = a[piv], a[col]
        p = a[col][col]
        a[col] = [v / p for v in a[col]]
        for r in range(n):
            if r != col and a[r][col] != 0.0:
                f = a[r][col]
                a[r] = [v - f * w for v, w in zip(a[r], a[col])]
    return [a[i][n] for i in range(n)]


def ridge(rows: list[tuple[list[tuple[int, float]], float, float]],
          n_feat: int, lam: float) -> list[float]:
    """Weighted ridge on a design given as signed index pairs.

    Each row is a list of (feature_index, sign) pairs, so a *difference* (home rating minus
    away rating) is expressible.  Without signs the estimator forces both teams' ratings to
    enter with a + sign, the difference cancels, and the "model" collapses to a constant --
    which is exactly what happened here: side MAE 10.935 against 10.959 for a constant, and a
    correlation with the market spread of 0.024.  A model that does not correlate with the
    market and does not beat a constant is not a model, and the number that exposed it was
    corr(fair, market), not the MAE.

    The weight enters BOTH X'X and X'y.  Applying it to the target only (an earlier bug)
    shrinks every prediction toward zero.
    """
    mat = [[0.0] * n_feat for _ in range(n_feat)]
    vec = [0.0] * n_feat
    for terms, y, w in rows:
        if w <= 0:
            continue
        for i, si in terms:
            vec[i] += w * si * y
            for j, sj in terms:
                mat[i][j] += w * si * sj
    for i in range(n_feat):
        mat[i][i] += lam
    return solve(mat, vec)


# ------------------------------------------------------------------ conversions
def american_from_prob(p: float | None) -> float | None:
    """Vig-free American odds implied by a probability.  p = 0.5 -> +100."""
    if p is None or not (0.0 < p < 1.0):
        return None
    if p >= 0.5:
        return -100.0 * p / (1.0 - p)
    return 100.0 * (1.0 - p) / p


def american_to_decimal(odds: float | None) -> float | None:
    if odds is None:
        return None
    if odds >= 100:
        return 1.0 + odds / 100.0
    if odds <= -100:
        return 1.0 + 100.0 / abs(odds)
    return None


def implied_prob(odds: float | None) -> float | None:
    d = american_to_decimal(odds)
    return None if d is None else 1.0 / d


def norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def norm_pdf(z: float) -> float:
    return math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)


# ------------------------------------------------------------------ the model
class Ratings:
    def __init__(self, teams: list[str]):
        self.teams = teams
        self.tidx = {t: i for i, t in enumerate(teams)}
        self.side_rating = {t: 0.0 for t in teams}
        self.off = {t: 0.0 for t in teams}
        self.dfn = {t: 0.0 for t in teams}
        self.hfa = 2.5
        self.mu = 44.0
        self.sigma = 13.5
        self.resid_n = 0
        self.fitted_games = 0

    def fit(self, history: list[dict], season: int, week: int,
            lam_side: float, lam_total: float) -> None:
        nt = len(self.teams)
        side_rows, total_rows = [], []
        for g in history:
            if g["home_margin"] is None:
                continue
            if g["season"] == season and g["week"] >= week:
                continue                        # lookahead guard: never see this week
            if g["season"] > season:
                continue
            w = PRIOR_SEASON_WEIGHT if g["season"] < season else DECAY ** (week - g["week"])
            h, a = self.tidx.get(g["home"]), self.tidx.get(g["away"])
            if h is None or a is None:
                continue
            # SIDE: home_margin ~ +h_rating - a_rating + home_field.  The signs matter.
            side_rows.append(([(h, 1.0), (a, -1.0), (nt, 1.0)], g["home_margin"], w))
            # TOTAL: game_total ~ mu + off_h + def_a + off_a + def_h (all positive).
            total_rows.append(([(nt + h, 1.0), (h, 1.0), (nt + a, 1.0), (a, 1.0), (2 * nt, 1.0)],
                               g["game_total"], w))
        if len(side_rows) < 40:
            return
        coef = ridge(side_rows, nt + 1, lam_side)
        self.side_rating = {t: coef[self.tidx[t]] for t in self.teams}
        self.hfa = coef[nt]
        coef2 = ridge(total_rows, 2 * nt + 1, lam_total)
        self.off = {t: coef2[self.tidx[t]] for t in self.teams}
        self.dfn = {t: coef2[nt + self.tidx[t]] for t in self.teams}
        self.mu = coef2[2 * nt]
        self.fitted_games = len(side_rows)
        # sigma from the residuals of the same walk-forward history (never this week)
        errs = []
        for g in history:
            if g["home_margin"] is None or g["season"] != season or g["week"] >= week:
                continue
            pred = self.side(g["home"], g["away"])
            if pred is not None:
                errs.append(g["home_margin"] + pred)
        if len(errs) > 50:
            mean = sum(errs) / len(errs)
            self.sigma = (sum((e - mean) ** 2 for e in errs) / (len(errs) - 1)) ** 0.5
            self.resid_n = len(errs)

    def side(self, home: str, away: str) -> float | None:
        h, a = self.side_rating.get(home), self.side_rating.get(away)
        if h is None or a is None:
            return None
        return -(h - a + self.hfa)          # home convention: negative = home favoured

    def total(self, home: str, away: str) -> float | None:
        try:
            return (self.mu + self.off[home] + self.dfn[away]
                    + self.off[away] + self.dfn[home])
        except KeyError:
            return None


def originate_moneyline(fair_side: float | None, sigma: float) -> tuple[float | None, float | None, float | None]:
    """Order gate: this can only be called with a side already in hand."""
    if fair_side is None:
        return None, None, None
    if not (sigma and sigma > 0):
        return None, None, None
    margin = -fair_side
    p_home_win = norm_cdf(margin / sigma)
    # a tie is a push on the moneyline: half the mass at exactly 0 goes to each side
    tie_mass = norm_pdf(margin / sigma) / sigma
    p_home = min(max(p_home_win + tie_mass / 2.0, 0.001), 0.999)
    return american_from_prob(p_home), american_from_prob(1.0 - p_home), p_home


# ------------------------------------------------------------------ data
def load_games() -> list[dict]:
    out = []
    for g in read_csv("games.csv"):
        hs, as_ = num(g["home_score"]), num(g["away_score"])
        out.append({
            "game_id": g["game_id"], "season": int(g["season"]), "week": int(g["week"]),
            "game_type": g["game_type"], "gameday": g["gameday"],
            "home": g["home_team"], "away": g["away_team"],
            "home_margin": (hs - as_) if hs is not None else None,
            "game_total": (hs + as_) if hs is not None else None,
            "market_side": (-num(g["spread_line"])) if num(g["spread_line"]) is not None else None,
            "market_total": num(g["total_line"]),
            "market_home_ml": num(g["home_moneyline"]),
            "market_away_ml": num(g["away_moneyline"]),
        })
    return sorted(out, key=lambda r: (r["season"], r["week"], r["gameday"], r["game_id"]))


def run_walk_forward(games: list[dict], lam_side: float, lam_total: float,
                     collect_from: int) -> list[dict]:
    """One pass over every season; predictions are collected only from `collect_from` on,
    but the ratings are always fitted the same way (no tuning peek inside)."""
    teams = sorted({g["home"] for g in games} | {g["away"] for g in games})
    R = Ratings(teams)
    preds: list[dict] = []
    for season in sorted({g["season"] for g in games}):
        season_games = [g for g in games if g["season"] == season]
        for week in sorted({g["week"] for g in season_games}):
            R.fit([g for g in games if g["season"] <= season], season, week, lam_side, lam_total)
            for g in [r for r in season_games if r["week"] == week]:
                fair_side = R.side(g["home"], g["away"])
                fair_total = R.total(g["home"], g["away"])
                ml_h, ml_a, p_home = originate_moneyline(fair_side, R.sigma)
                preds.append({**g, "fair_side": fair_side, "fair_total": fair_total,
                              "fair_ml_home": ml_h, "fair_ml_away": ml_a,
                              "p_home": p_home, "sigma": R.sigma,
                              "week_in_test": season >= collect_from})
    return preds


def mae(vals: list[float]) -> float | None:
    return round(statistics.mean(vals), 3) if vals else None


def main() -> int:
    fast = "--fast" in sys.argv
    games = load_games()

    # ---------------------------------------------------------- 1. tuning (1999-2014 only)
    tuning = []
    if fast:
        tuning = [{"note": "skipped (--fast); frozen values reused",
                   "frozen": FROZEN}]
    else:
        best = None
        for lam in LAMBDA_GRID:
            preds = run_walk_forward(games, lam, FROZEN["lambda_total"], TUNE_FROM)
            sel = [p for p in preds if TUNE_FROM <= p["season"] <= TUNE_TO]
            e_side = mae([abs(p["home_margin"] + p["fair_side"]) for p in sel
                          if p["home_margin"] is not None and p["fair_side"] is not None])
            e_total = mae([abs(p["game_total"] - p["fair_total"]) for p in sel
                           if p["game_total"] is not None and p["fair_total"] is not None])
            tuning.append({"lambda_side": lam, "lambda_total": FROZEN["lambda_total"],
                           "tune_side_mae": e_side, "tune_total_mae": e_total,
                           "tune_n": len(sel)})
            if e_side is not None and (best is None or e_side < best[1]):
                best = (lam, e_side)
        if best:
            FROZEN["lambda_side"] = best[0]
        best_t = None
        for lam in LAMBDA_GRID:
            preds = run_walk_forward(games, FROZEN["lambda_side"], lam, TUNE_FROM)
            sel = [p for p in preds if TUNE_FROM <= p["season"] <= TUNE_TO]
            e = mae([abs(p["game_total"] - p["fair_total"]) for p in sel
                     if p["game_total"] is not None and p["fair_total"] is not None])
            if e is not None and (best_t is None or e < best_t[1]):
                best_t = (lam, e)
        if best_t:
            FROZEN["lambda_total"] = best_t[0]
        tuning.append({"chosen": dict(FROZEN),
                       "rule": f"lowest MAE on {TUNE_FROM}-{TUNE_TO} only; frozen before the "
                               f"{TEST_FROM}-{TEST_TO} test window was scored"})

    # ---------------------------------------------------------- 2. one evaluation pass
    preds = run_walk_forward(games, FROZEN["lambda_side"], FROZEN["lambda_total"], TEST_FROM)
    test = [p for p in preds if TEST_FROM <= p["season"] <= TEST_TO and p["home_margin"] is not None]

    e_side = [abs(p["home_margin"] + p["fair_side"]) for p in test if p["fair_side"] is not None]
    e_total = [abs(p["game_total"] - p["fair_total"]) for p in test if p["fair_total"] is not None]
    m_side = [abs(p["market_side"] + p["home_margin"]) for p in test
              if p["market_side"] is not None]
    m_total = [abs(p["market_total"] - p["game_total"]) for p in test
               if p["market_total"] is not None]
    const = [abs(p["home_margin"] - 2.5) for p in test]      # naive home-field baseline
    const0 = [abs(p["home_margin"]) for p in test]

    brier_m, brier_k, brier_n = [], [], 0
    for p in test:
        if p["p_home"] is None:
            continue
        y = 1.0 if p["home_margin"] > 0 else (0.5 if p["home_margin"] == 0 else 0.0)
        brier_m.append((p["p_home"] - y) ** 2)
        pm = implied_prob(p["market_home_ml"])
        if pm is not None:
            brier_k.append((pm - y) ** 2)
            brier_n += 1

    by_season: dict[int, dict] = {}
    for p in test:
        if p["fair_side"] is None:
            continue
        d = by_season.setdefault(p["season"], {"side": [], "total": [], "mkt": []})
        d["side"].append(abs(p["home_margin"] + p["fair_side"]))
        if p["fair_total"] is not None:
            d["total"].append(abs(p["game_total"] - p["fair_total"]))
        if p["market_side"] is not None:
            d["mkt"].append(abs(p["market_side"] + p["home_margin"]))

    diffs = [p["fair_side"] - p["market_side"] for p in preds
             if p["fair_side"] is not None and p["market_side"] is not None]
    corr = None
    pairs = [(p["fair_side"], p["market_side"]) for p in preds
             if p["fair_side"] is not None and p["market_side"] is not None]
    if len(pairs) > 10:
        xs = [a for a, _ in pairs]
        ys = [b for _, b in pairs]
        mx, my = statistics.mean(xs), statistics.mean(ys)
        sxy = sum((a - mx) * (b - my) for a, b in pairs)
        sxx = sum((a - mx) ** 2 for a in xs)
        syy = sum((b - my) ** 2 for b in ys)
        corr = round(sxy / math.sqrt(sxx * syy), 4) if sxx > 0 and syy > 0 else None

    a_side, a_total = mae(e_side), mae(e_total)
    k_side, k_total = mae(m_side), mae(m_total)
    beat_side = bool(a_side and k_side and a_side < k_side)
    beat_total = bool(a_total and k_total and a_total < k_total)

    report = {
        "generated_at": utcnow(),
        "snapshot": SNAPSHOT,
        "title": "Originated lines: tuning, out-of-sample accuracy, calibration, defects",
        "upstream": {k: UPSTREAM_PIN[k] for k in
                     ("repo", "archive_url", "retrieved_at", "publisher")},
        "order": MARKET_ORDER,
        "model": {
            "side": "margin = h_rating - a_rating + home_field; ridge lambda=%.0f; "
                    "decay=%.2f per week; prior-season weight %.2f"
                    % (FROZEN["lambda_side"], DECAY, PRIOR_SEASON_WEIGHT),
            "total": "total = mu + off_home + def_away + off_away + def_home; ridge lambda=%.0f"
                     % FROZEN["lambda_total"],
            "moneyline": "P(home) = Phi(margin/sigma) + half the tie mass; sigma from the "
                         "walk-forward residuals of the same season, never the current week",
            "walk_forward": "refit before every week with only earlier weeks of the same "
                            "season plus a decayed prior season",
        },
        "tuning": tuning,
        "test_window": {"from": TEST_FROM, "to": TEST_TO, "games": len(test)},
        "accuracy": {
            "side_mae_model": a_side,
            "side_mae_market": k_side,
            "side_mae_constant_hfa_2_5": mae(const),
            "side_mae_constant_zero": mae(const0),
            "total_mae_model": a_total,
            "total_mae_market": k_total,
            "brier_model": mae(brier_m),
            "brier_market": mae(brier_k),
            "brier_n": brier_n,
            "mean_abs_disagreement_with_market": round(statistics.mean(abs(d) for d in diffs), 3)
            if diffs else None,
            "corr_fair_vs_market": corr,
            "n_side": len(e_side), "n_total": len(e_total), "n_market_side": len(m_side),
        },
        "by_season": {
            str(s): {"side_mae_model": round(statistics.mean(v["side"]), 2),
                     "side_mae_market": round(statistics.mean(v["mkt"]), 2) if v["mkt"] else None,
                     "total_mae_model": round(statistics.mean(v["total"]), 2) if v["total"] else None,
                     "n": len(v["side"])}
            for s, v in sorted(by_season.items())
        },
        "honest_verdict": {
            "beats_market_on_side": beat_side,
            "beats_market_on_total": beat_total,
            "beats_a_constant_on_side": bool(a_side and mae(const) and a_side < mae(const)),
            "statement": (
                "The ratings model carries real information: it beats the naive 'home team by "
                "2.5' baseline on side MAE. It does not beat the market. That is the expected "
                "result for a model with no information the market does not have, and it is "
                "published rather than hidden. No stake is staked on this model; it is a "
                "screen and the benchmark for the strategy layer."
                if not (beat_side and beat_total) else
                "The model beats the market on at least one market in the test window. Before "
                "that is treated as an edge, the gates G1-G7 must still pass -- in particular "
                "G3 (calibration) and G4 (robustness), and the window halves must agree."
            ),
        },
        "defects_found_in_this_build": [
            {
                "id": "L-01",
                "severity": "high",
                "was": "sample weight applied to the target only, not to the design matrix",
                "effect": "total MAE published as 28.413 on a quantity averaging 44; the fit "
                          "was shrinking toward zero rather than weighting recent games",
                "fixed_in": "ridge() now accumulates w in both X'X and X'y",
                "evidence": "data/lab/lines/fair_lines.json totals before/after; see this file's "
                            "module docstring",
            },
            {
                "id": "L-03",
                "severity": "high",
                "was": "the side design matrix entered the home and away ratings with the same "
                       "sign, so the team-difference term cancelled inside the estimator",
                "effect": "the published line was effectively a constant: corr(fair_side, "
                          "market_side) = 0.0241 against 0.4699 after the fix, and side MAE "
                          "10.935 (worse than a 2.5 constant at 10.959 on the same window "
                          "until the sign was restored) -> 10.741",
                "how_it_was_caught": "by publishing corr(fair, market) next to the MAE, not by "
                                     "looking at the MAE alone",
                "fixed_in": "ridge() now takes signed index pairs, and the side row is "
                            "+home -away +home_field",
            },
            {
                "id": "L-02",
                "severity": "medium",
                "was": "the current-week board selected max(season, week) among scheduled games "
                       "and published week 18",
                "effect": "the 'this week' board was not this week",
                "fixed_in": "the board now takes the earliest week with unplayed games in the "
                            "latest season with any unplayed games",
            },
        ],
    }

    # ---------------------------------------------------------- 3. rows for the site
    rows = []
    for p in preds:
        diff = (round(p["fair_side"] - p["market_side"], 2)
                if p["fair_side"] is not None and p["market_side"] is not None else None)
        dtot = (round(p["fair_total"] - p["market_total"], 2)
                if p["fair_total"] is not None and p["market_total"] is not None else None)
        p_mkt = implied_prob(p["market_home_ml"])
        dml = (round((p["p_home"] - p_mkt) * 100, 2)
               if p["p_home"] is not None and p_mkt is not None else None)
        rows.append({
            "game_id": p["game_id"], "season": p["season"], "week": p["week"],
            "game_type": p["game_type"], "gameday": p["gameday"],
            "away": p["away"], "home": p["home"],
            "fair_side": round(p["fair_side"], 2) if p["fair_side"] is not None else None,
            "market_side": round(p["market_side"], 2) if p["market_side"] is not None else None,
            "side_diff": diff,
            "fair_total": round(p["fair_total"], 2) if p["fair_total"] is not None else None,
            "market_total": p["market_total"],
            "total_diff": dtot,
            "fair_ml_home": round(p["fair_ml_home"], 1) if p["fair_ml_home"] is not None else None,
            "fair_ml_away": round(p["fair_ml_away"], 1) if p["fair_ml_away"] is not None else None,
            "market_ml_home": p["market_home_ml"],
            "market_ml_away": p["market_away_ml"],
            "ml_prob_diff_pts": dml,
            "fair_home_win_prob": round(p["p_home"], 4) if p["p_home"] is not None else None,
            "sigma": round(p["sigma"], 3) if p["sigma"] else None,
            "result_home_margin": p["home_margin"],
            "result_total": p["game_total"],
            "status": "FINAL" if p["home_margin"] is not None else "SCHEDULED",
            "in_test_window": p["week_in_test"],
            "market_book_named": False,
            "market_provenance": "https://github.com/nflverse/nfldata/blob/master/DATASETS.md#L109",
        })

    # current board = earliest week of the latest season with unplayed games
    latest_season = max(r["season"] for r in rows)
    sched = [r for r in rows if r["status"] == "SCHEDULED" and r["season"] == latest_season]
    board = [r for r in sched if r["week"] == min(s["week"] for s in sched)] if sched else []
    write_json("data/lab/lines/week10_board.json", {
        "generated_at": utcnow(),
        "season": latest_season,
        "week": board[0]["week"] if board else None,
        "order": MARKET_ORDER,
        "note": "Side first, then total, then moneyline. The moneyline is derived from the "
                "side, never fitted on its own. Market rows come from one unnamed publisher "
                "composite (no book is named by the source: see defect P-04).",
        "rows": board,
        "accuracy": report["accuracy"],
    })

    fields = ["game_id", "season", "week", "gameday", "away", "home",
              "fair_side", "market_side", "side_diff",
              "fair_total", "market_total", "total_diff",
              "fair_ml_home", "market_ml_home", "ml_prob_diff_pts",
              "result_home_margin", "result_total", "status"]
    write_csv("data/lab/lines/fair_lines.csv", fields,
              ({k: blank(r.get(k)) for k in fields} for r in rows))
    write_json("data/lab/lines/fair_lines.json", {
        "dataset": "fair_lines",
        "title": "Fair line, market line and the difference, as separate columns",
        "generated_at": utcnow(),
        "snapshot": SNAPSHOT,
        "order": MARKET_ORDER,
        "column_notes": {
            "fair_side": "Our number, home convention (negative = home favoured). Derived.",
            "market_side": "The publisher's number, converted to the same convention.",
            "side_diff": "fair_side - market_side, in points.",
            "fair_total": "Our number for the combined score.",
            "market_total": "The publisher's total.",
            "total_diff": "fair_total - market_total.",
            "ml_prob_diff_pts": "our home-win probability minus the market-implied one, in "
                                "percentage points. The market figure still contains the vig, "
                                "so a zero here would mean we are slightly *behind* the market.",
            "market_book_named": "false on every row: the source names no book (defect P-04).",
        },
        "rows": rows,
        "counts": {
            "games": len(rows),
            "with_fair_side": sum(1 for r in rows if r["fair_side"] is not None),
            "with_market_side": sum(1 for r in rows if r["market_side"] is not None),
            "with_both_side": sum(1 for r in rows if r["side_diff"] is not None),
            "with_both_total": sum(1 for r in rows if r["total_diff"] is not None),
            "with_moneyline": sum(1 for r in rows if r["fair_ml_home"] is not None),
        },
    })
    write_json("data/lab/lines/model_report.json", report)

    a = report["accuracy"]
    print(f"frozen: {FROZEN}")
    print(f"test window {TEST_FROM}-{TEST_TO}: {len(test)} final games")
    print(f"  side  MAE model {a['side_mae_model']} | market {a['side_mae_market']} | "
          f"constant 2.5 {a['side_mae_constant_hfa_2_5']} | constant 0 {a['side_mae_constant_zero']}")
    print(f"  total MAE model {a['total_mae_model']} | market {a['total_mae_market']}")
    print(f"  Brier model {a['brier_model']} | market {a['brier_market']} (n={a['brier_n']})")
    print(f"  mean |disagreement| with market {a['mean_abs_disagreement_with_market']} pts, "
          f"corr {a['corr_fair_vs_market']}")
    print(f"  beats market: side={beat_side} total={beat_total}")
    print(f"  current board: season {latest_season} week {board[0]['week'] if board else None}, "
          f"{len(board)} games")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
