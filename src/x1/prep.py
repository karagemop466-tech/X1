"""Game-level preparation: normalisation, walk-forward Elo, feature builder.

Everything in this module is strictly chronological: a row for game *g* may only
use information available strictly before kickoff of *g*.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from . import config


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------
def load_games() -> pd.DataFrame:
    games = pd.read_csv(config.RAW_DIR / "games.csv")
    games = games[games["game_type"].isin(["REG", "WC", "DIV", "CON", "SB"])].copy()
    games["gameday"] = pd.to_datetime(games["gameday"], errors="coerce")
    games = games.sort_values(["season", "gameday", "game_id"]).reset_index(drop=True)

    # Canonical short codes used everywhere else in the project.
    games["away_team"] = games["away_team"].replace({"LA": "LAR", "LA ": "LAR"})
    games["home_team"] = games["home_team"].replace({"LA": "LAR", "LA ": "LAR"})

    games["is_playoff"] = (games["game_type"] != "REG").astype(int)
    games["margin"] = games["home_score"] - games["away_score"]
    games["total_points"] = games["home_score"] + games["away_score"]
    games["home_win"] = np.where(
        games["margin"] > 0, 1.0, np.where(games["margin"] < 0, 0.0, 0.5)
    )
    games["neutral_site"] = (games["location"].astype(str).str.lower() == "neutral").astype(int)

    # Rest days (games.csv already carries away_rest / home_rest).
    for col in ("away_rest", "home_rest"):
        games[col] = pd.to_numeric(games[col], errors="coerce")
    games["rest_diff"] = games["home_rest"] - games["away_rest"]

    # Market line helpers.
    # `spread_line` is expressed from the HOME team's perspective (positive =
    # home favoured), which the mirror documents in DATASETS.md.
    games["market_spread"] = pd.to_numeric(games["spread_line"], errors="coerce")
    games["market_total"] = pd.to_numeric(games["total_line"], errors="coerce")
    games["home_covers"] = np.where(
        games["margin"] > games["market_spread"], 1.0,
        np.where(games["margin"] == games["market_spread"], 0.5, 0.0),
    )
    games["over"] = np.where(
        games["total_points"] > games["market_total"], 1.0,
        np.where(games["total_points"] == games["market_total"], 0.5, 0.0),
    )
    return games


# --------------------------------------------------------------------------
# Elo
# --------------------------------------------------------------------------
@dataclass
class EloResult:
    games: pd.DataFrame
    ratings: Dict[str, float]


def _mov_multiplier(margin: float) -> float:
    """538-style margin-of-victory multiplier: big wins count for more."""
    return ((abs(margin) + 3.0) ** 0.8)


def walk_forward_elo(games: pd.DataFrame) -> EloResult:
    """Add pre-game Elo to every row.

    K-factor (transparent variant, documented on the site):
        K = K_BASE * MOV_multiplier / (7.5 + 2 * |pre-game Elo diff| / 400)

    Home field advantage is a constant Elo-point bonus for the home team.
    Between seasons ratings regress 25% back toward the league mean.
    """
    ratings: Dict[str, float] = {}
    out_elo_home = np.full(len(games), np.nan)
    out_elo_away = np.full(len(games), np.nan)
    out_exp_home = np.full(len(games), np.nan)

    rows = games.to_dict("records")
    current_season = None
    for i, row in enumerate(rows):
        season = row["season"]
        if season != current_season:
            if current_season is not None:
                mean = config.ELO_INIT
                ratings = {
                    t: mean + (1 - config.ELO_SEASON_REVERSION) * (r - mean)
                    for t, r in ratings.items()
                }
            current_season = season
        home, away = row["home_team"], row["away_team"]
        eh = ratings.get(home, config.ELO_INIT)
        ea = ratings.get(away, config.ELO_INIT)
        diff = eh - ea + config.ELO_HFA
        expected_home = 1.0 / (1.0 + 10 ** (-diff / 400.0))
        out_elo_home[i] = eh
        out_elo_away[i] = ea
        out_exp_home[i] = expected_home

        played = (
            row.get("home_score") is not None
            and not pd.isna(row.get("home_score"))
            and row.get("game_type") in ("REG", "WC", "DIV", "CON", "SB")
        )
        if not played:
            continue
        margin = row["margin"]
        actual = row["home_win"]
        k = (
            config.ELO_K_BASE
            * _mov_multiplier(margin)
            / (7.5 + 2.0 * abs(diff) / 400.0)
        )
        delta = k * (actual - expected_home)
        ratings[home] = eh + delta
        ratings[away] = ea - delta

    games = games.copy()
    games["elo_home_pre"] = out_elo_home
    games["elo_away_pre"] = out_elo_away
    games["elo_diff_home"] = out_elo_home - out_elo_away
    games["elo_expected_home"] = out_exp_home
    return EloResult(games=games, ratings=ratings)


# --------------------------------------------------------------------------
# Feature builder
# --------------------------------------------------------------------------
def build_features(games: pd.DataFrame) -> pd.DataFrame:
    """Game features used by the originated-line model and the strategies."""
    df = games.copy()

    # Team-level rolling points, opponent adjusted, exponentially decayed.
    df = _add_team_scoring_features(df)

    df["is_dome"] = df["roof"].astype(str).isin(["dome", "closed"]).astype(float)
    df["temp_f"] = pd.to_numeric(df["temp"], errors="coerce")
    df["wind_mph"] = pd.to_numeric(df["wind"], errors="coerce")
    df["is_primetime"] = df["gametime"].astype(str).isin(["20:20", "20:25", "21:00", "16:15", "13:00"]).astype(float)
    return df


def _exp_weight_half_life(n: int, half_life: float) -> np.ndarray:
    if n <= 0:
        return np.array([])
    age = np.arange(n - 1, -1, -1)
    return np.power(0.5, age / half_life)


def _add_team_scoring_features(df: pd.DataFrame) -> pd.DataFrame:
    """Attach decayed points-scored / points-allowed ratings per team.

    For every game we compute, from *prior games only*, each team's
    exponentially weighted points scored and points allowed.  These become
    offence / defence style covariates for diagnostics and for the strategy
    feature set.
    """
    teams = sorted(set(df["away_team"]) | set(df["home_team"]))
    # history[team] -> list of (points_for, points_against) from prior games
    history: Dict[str, List[Tuple[float, float]]] = {t: [] for t in teams}
    home_scored = np.full(len(df), np.nan)
    home_allowed = np.full(len(df), np.nan)
    away_scored = np.full(len(df), np.nan)
    away_allowed = np.full(len(df), np.nan)

    for i, row in enumerate(df.to_dict("records")):
        h, a = row["home_team"], row["away_team"]

        def _rating(team: str) -> Tuple[float, float]:
            hist = history[team]
            if not hist:
                return (float("nan"), float("nan"))
            w = _exp_weight_half_life(len(hist), config.RECENCY_HALF_LIFE_GAMES)
            pf = np.array([x[0] for x in hist])
            pa = np.array([x[1] for x in hist])
            return (float(np.average(pf, weights=w)), float(np.average(pa, weights=w)))

        hs, ha = _rating(h)
        as_, aa = _rating(a)
        home_scored[i], home_allowed[i], away_scored[i], away_allowed[i] = hs, ha, as_, aa

        # store this game's scores for future games
        if not pd.isna(row["home_score"]):
            history[h].append((float(row["home_score"]), float(row["away_score"])))
            history[a].append((float(row["away_score"]), float(row["home_score"])))

    df["home_pts_scored_pre"] = home_scored
    df["home_pts_allowed_pre"] = home_allowed
    df["away_pts_scored_pre"] = away_scored
    df["away_pts_allowed_pre"] = away_allowed
    return df


def league_mean_total(games: pd.DataFrame, upto_season: int) -> float:
    sel = games[(games["season"] <= upto_season) & games["total_points"].notna()]
    return float(sel["total_points"].mean())


def round_to_half(x: float) -> float:
    """Round a projection to the nearest half point (market convention)."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return float("nan")
    return round(x * 2.0) / 2.0
