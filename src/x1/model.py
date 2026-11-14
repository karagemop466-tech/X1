"""Originated lines.

A two-part Poisson model predicts each team's points for every game:

    points ~ C(team) + C(opponent) + elo_diff + rest_diff + is_home

* ``C(team)``   -> attack rating (how many points this team scores)
* ``C(opponent)``-> defence rating (how many points this team concedes)
* ``elo_diff``  -> pre-game Elo difference (team perspective), already carries
                   the constant home-field advantage
* ``rest_diff`` -> extra days of rest (team perspective)
* ``is_home``   -> home-field bonus for the scoring level

The model is fitted **walk-forward**: for every season *s* the training set is
"all games strictly before *s*", so no game is ever scored by a model that has
already seen it.  The originated spread is ``lambda_home - lambda_away`` and the
originated total is ``lambda_home + lambda_away``, both rounded to half points.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import statsmodels.api as sm

from . import config


@dataclass
class LineModel:
    frame: pd.DataFrame                 # games with originated lines attached
    feature_columns: List[str]
    team_codes: List[str]
    season_diagnostics: pd.DataFrame    # per-season fit diagnostics


def _encode(rows: pd.DataFrame, col: str, levels: List[str]) -> np.ndarray:
    """One-hot columns for a categorical column (reference level omitted)."""
    idx_map = {t: i for i, t in enumerate(levels)}
    n = len(rows)
    out = np.zeros((n, len(levels)))
    idx = rows[col].map(idx_map).fillna(-1).astype(int).values
    valid = idx >= 0
    out[np.where(valid)[0], idx[valid]] = 1.0
    return out


def _design_matrix(
    rows: pd.DataFrame,
    attack_levels: List[str],
    defence_levels: List[str],
) -> Tuple[np.ndarray, List[str]]:
    """Build the Poisson design matrix.

    Identification: the model is ``mu + ATK[team] + DEF[opponent] + ...``.
    On the observed (scoring team, opponent) pairs the space of additive
    functions has dimension ``2T - 1``: the potentials are only identified up
    to a constant, and the intercept absorbs that constant.  A design with an
    intercept and one full dummy block per factor therefore has ``2T`` columns
    for a ``2T - 1`` dimensional model space and is rank deficient by exactly
    one - which is what the raw dummy blocks produced.

    The matrix below uses an intercept and *treatment coding* on **both**
    blocks with the same reference team, giving ``1 + (T-1) + (T-1) = 2T - 1``
    columns.  That is the minimal, exactly identified parameterisation of the
    same additive model, and the rank is asserted before every fit.
    """
    n = len(rows)
    atk = _encode(rows, "team", attack_levels)
    dfn = _encode(rows, "opponent", defence_levels)
    extra = np.column_stack(
        [
            rows["elo_diff_team"].values.astype(float),
            rows["rest_diff_team"].values.astype(float),
            rows["is_home"].values.astype(float),
        ]
    )
    columns = (
        ["intercept"]
        + [f"atk_{t}" for t in attack_levels]
        + [f"def_{t}" for t in defence_levels]
        + ["elo_diff_team", "rest_diff_team", "is_home"]
    )
    return np.hstack([np.ones((n, 1)), atk, dfn, extra]), columns


def _stack_games(games: pd.DataFrame) -> pd.DataFrame:
    """Turn game rows into team-game rows (one per scoring team)."""
    played = games[games["home_score"].notna()].copy()
    home_rows = pd.DataFrame(
        {
            "season": played["season"],
            "team": played["home_team"],
            "opponent": played["away_team"],
            "points": played["home_score"].astype(float),
            "elo_diff_team": played["elo_diff_home"].astype(float),
            "rest_diff_team": played["rest_diff"].astype(float),
            "is_home": 1.0,
            "game_id": played["game_id"],
        }
    )
    away_rows = pd.DataFrame(
        {
            "season": played["season"],
            "team": played["away_team"],
            "opponent": played["home_team"],
            "points": played["away_score"].astype(float),
            "elo_diff_team": -played["elo_diff_home"].astype(float),
            "rest_diff_team": -played["rest_diff"].astype(float),
            "is_home": 0.0,
            "game_id": played["game_id"],
        }
    )
    return pd.concat([home_rows, away_rows], ignore_index=True)


def _recency_weights(seasons: pd.Series, half_life: float) -> np.ndarray:
    """Exponential weight by how recently the season occurred."""
    max_season = seasons.max()
    age = (max_season - seasons).astype(float).values
    return np.power(0.5, age / max(half_life, 1e-9))


def fit_line_model(games: pd.DataFrame) -> LineModel:
    team_codes = sorted(set(games["away_team"]) | set(games["home_team"]))
    stacked = _stack_games(games)

    preds = pd.DataFrame(
        {
            "game_id": games["game_id"],
            "lambda_home": np.nan,
            "lambda_away": np.nan,
            "fit_season": np.nan,
        }
    )
    idx_by_game = {gid: i for i, gid in enumerate(games["game_id"])}

    diagnostics: List[Dict] = []
    all_seasons = sorted(stacked["season"].unique())
    last_columns: List[str] = []

    for season in all_seasons:
        train = stacked[stacked["season"] < season]
        target = stacked[stacked["season"] == season]
        if train["game_id"].nunique() < 200 or len(target) == 0:
            continue
        w = _recency_weights(train["season"], 8.0)  # ~8 season half-life

        # Levels present in the training window only, so no column is empty.
        attack_all = sorted(set(train["team"]))
        defence_all = sorted(set(train["opponent"]))
        # The reference team must appear on both sides of the design so that
        # the treatment-coded parameterisation stays exactly identified.
        both = sorted(set(attack_all) & set(defence_all))
        counts = train["team"].value_counts()
        reference = counts.index[0] if len(counts) else (both[0] if both else attack_all[0])
        if reference not in both:
            reference = both[0] if both else reference
        attack_levels = [t for t in attack_all if t != reference]
        defence_levels = [t for t in defence_all if t != reference]

        X, columns = _design_matrix(train, attack_levels, defence_levels)
        last_columns = columns
        y = train["points"].values.astype(float)
        rank = np.linalg.matrix_rank(X)
        if rank < X.shape[1]:  # pragma: no cover - defensive
            diagnostics.append({
                "season": int(season),
                "status": f"skipped: design matrix rank {rank} of {X.shape[1]} columns",
            })
            continue
        try:
            model = sm.GLM(y, X, family=sm.families.Poisson(), freq_weights=w)
            result = model.fit(maxiter=200, disp=0)
        except Exception as exc:  # pragma: no cover - defensive
            diagnostics.append({"season": int(season), "status": f"failed: {exc}"})
            continue

        # Explicit prediction so that teams unseen in training (a franchise's
        # first season) fall back to the league-average rating instead of
        # silently receiving the reference team's rating.
        params = result.params
        n_atk = len(attack_levels)
        n_def = len(defence_levels)
        intercept = float(params[0])
        atk_coef = {t: 0.0 for t in attack_all}
        for i, t in enumerate(attack_levels):
            atk_coef[t] = float(params[1 + i])
        def_coef = {t: 0.0 for t in defence_all}
        for i, t in enumerate(defence_levels):
            def_coef[t] = float(params[1 + n_atk + i])
        beta = params[1 + n_atk + n_def:]
        atk_mean = float(np.mean(list(atk_coef.values())))
        def_mean = float(np.mean(list(def_coef.values())))

        lin = (
            intercept
            + np.array([atk_coef.get(t, atk_mean) for t in target["team"]])
            + np.array([def_coef.get(t, def_mean) for t in target["opponent"]])
            + beta[0] * target["elo_diff_team"].values.astype(float)
            + beta[1] * target["rest_diff_team"].values.astype(float)
            + beta[2] * target["is_home"].values.astype(float)
        )
        mu = np.exp(lin)
        target = target.copy()
        target["mu"] = mu
        for gid, grp in target.groupby("game_id"):
            i = idx_by_game[gid]
            home_mu = grp.loc[grp["is_home"] == 1.0, "mu"]
            away_mu = grp.loc[grp["is_home"] == 0.0, "mu"]
            if len(home_mu) and len(away_mu):
                preds.loc[i, "lambda_home"] = float(home_mu.iloc[0])
                preds.loc[i, "lambda_away"] = float(away_mu.iloc[0])
                preds.loc[i, "fit_season"] = season

        scored = preds[(preds["fit_season"] == season) & preds["lambda_home"].notna()]
        if len(scored):
            merged = games.set_index("game_id").loc[scored["game_id"].values]
            pred_margin = (scored["lambda_home"].values - scored["lambda_away"].values)
            pred_total = (scored["lambda_home"].values + scored["lambda_away"].values)
            act_margin = merged["margin"].values.astype(float)
            act_total = merged["total_points"].values.astype(float)
            diagnostics.append(
                {
                    "season": int(season),
                    "status": "ok",
                    "n_games": int(len(scored)),
                    "margin_mae": float(np.mean(np.abs(pred_margin - act_margin))),
                    "margin_rmse": float(np.sqrt(np.mean((pred_margin - act_margin) ** 2))),
                    "total_mae": float(np.mean(np.abs(pred_total - act_total))),
                    "total_rmse": float(np.sqrt(np.mean((pred_total - act_total) ** 2))),
                    "margin_bias": float(np.mean(pred_margin - act_margin)),
                    "total_bias": float(np.mean(pred_total - act_total)),
                }
            )

    out = games.merge(preds, on="game_id", how="left")
    out["model_spread_raw"] = out["lambda_home"] - out["lambda_away"]
    out["model_total_raw"] = out["lambda_home"] + out["lambda_away"]
    out["model_spread"] = out["model_spread_raw"].round(1).apply(lambda v: round(v * 2) / 2 if pd.notna(v) else np.nan)
    out["model_total"] = out["model_total_raw"].round(1).apply(lambda v: round(v * 2) / 2 if pd.notna(v) else np.nan)
    # Home win probability from a normal approximation to the difference of
    # two Poisson means.
    var = out["lambda_home"] + out["lambda_away"]
    out["model_home_win_prob"] = [
        0.5 + 0.5 * float(np.vectorize(_erf)((m / np.sqrt(v)) / np.sqrt(2)))
        if pd.notna(m) and pd.notna(v) and v and v > 0
        else np.nan
        for m, v in zip(out["model_spread_raw"], var)
    ]
    out["spread_delta"] = out["model_spread"] - out["market_spread"]
    out["total_delta"] = out["model_total"] - out["market_total"]

    diag = pd.DataFrame(diagnostics)
    return LineModel(
        frame=out,
        feature_columns=last_columns,
        team_codes=team_codes,
        season_diagnostics=diag,
    )


def _erf(x: float) -> float:
    import math

    return math.erf(x)


def model_summary(model: LineModel) -> Dict:
    df = model.frame
    diag = model.season_diagnostics
    ok = diag[diag["status"] == "ok"] if len(diag) else diag
    summary = {
        "n_games_scored": int(df["model_spread"].notna().sum()),
        "first_season": int(ok["season"].min()) if len(ok) else None,
        "last_season": int(ok["season"].max()) if len(ok) else None,
        "mean_margin_mae": float(ok["margin_mae"].mean()) if len(ok) else None,
        "mean_total_mae": float(ok["total_mae"].mean()) if len(ok) else None,
        "seasons": ok.to_dict("records") if len(ok) else [],
    }
    return summary


def compare_to_market(model: LineModel, seasons: Optional[List[int]] = None) -> Dict:
    """How does the originated line compare with the market line?"""
    df = model.frame
    sel = df[df["model_spread"].notna() & df["market_spread"].notna()]
    if seasons:
        sel = sel[sel["season"].isin(seasons)]
    if sel.empty:
        return {}
    model_err = (sel["model_spread"] - sel["margin"]).abs()
    market_err = (sel["market_spread"] - sel["margin"]).abs()
    model_total_err = (sel["model_total"] - sel["total_points"]).abs()
    market_total_err = (sel["market_total"] - sel["total_points"]).abs()
    return {
        "n": int(len(sel)),
        "spread_mae_model": float(model_err.mean()),
        "spread_mae_market": float(market_err.mean()),
        "spread_rmse_model": float(np.sqrt(np.mean((sel["model_spread"] - sel["margin"]) ** 2))),
        "spread_rmse_market": float(np.sqrt(np.mean((sel["market_spread"] - sel["margin"]) ** 2))),
        "total_mae_model": float(model_total_err.mean()),
        "total_mae_market": float(market_total_err.mean()),
        "total_rmse_model": float(np.sqrt(np.mean((sel["model_total"] - sel["total_points"]) ** 2))),
        "total_rmse_market": float(np.sqrt(np.mean((sel["market_total"] - sel["total_points"]) ** 2))),
        "delta_mean": float(sel["spread_delta"].mean()),
        "delta_std": float(sel["spread_delta"].std()),
        "delta_abs_mean": float(sel["spread_delta"].abs().mean()),
    }
