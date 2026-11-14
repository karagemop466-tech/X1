"""Player-prop modelling and prop-combo correlation.

Market prop lines are not published by the league, so this module does three
things that *are* possible with verified data:

1. builds an originated prop line for every player-game (rolling mean of the
   player's own recent production),
2. measures the hit rate and the dispersion around that originated line,
3. measures the correlation between prop families inside the same game, which
   is the number that decides whether a two-leg prop combo is worth building.

Prop families are separated by position group - a quarterback's passing yards
and a wide receiver's receiving yards are different props and must not be
pooled with the zero rows that other positions carry.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from . import config

# position group -> prop family
FAMILY_POSITION = {
    "passing_yards": {"QB"},
    "rushing_yards": {"RB"},
    "receiving_yards": {"WR", "TE"},
    "receptions": {"WR", "TE"},
}


def load_player_stats() -> pd.DataFrame:
    df = pd.read_parquet(config.RAW_DIR / "player_stats_weekly_archive.parquet")
    df = df[df["season_type"] == "REG"].copy()
    if "game_id" not in df.columns:
        # The weekly archive keys games by season / week / team.
        df["game_id"] = (
            df["season"].astype(str) + "_" + df["week"].astype(str) + "_" + df["recent_team"].astype(str)
        )
    df = df.sort_values(["player_id", "season", "week"]).reset_index(drop=True)
    return df


def load_player_stats_2026() -> pd.DataFrame:
    """2026 weekly player stats (separate file, carries a real game id)."""
    df = pd.read_csv(config.RAW_DIR / "player_week_stats_2026.csv")
    df = df[df["season_type"] == "REG"].copy()
    df = df.rename(columns={"team": "recent_team"})
    df["player_display_name"] = df.get("player_display_name", df.get("player_name"))
    df["position_group"] = df.get("position_group", df.get("position"))
    return df


def _projection(series: pd.Series, window: int) -> pd.Series:
    """Rolling mean of the *previous* ``window`` observations (no leakage)."""
    return series.shift(1).rolling(window, min_periods=3).mean()


def _family_frame(stats: pd.DataFrame, stat: str) -> pd.DataFrame:
    positions = FAMILY_POSITION.get(stat, set())
    df = stats[stats["position_group"].isin(positions)].copy()
    df = df.dropna(subset=[stat])
    df = df.sort_values(["player_id", "season", "week"])
    return df


def build_prop_model(stats: pd.DataFrame, stat: str = "receiving_yards") -> pd.DataFrame:
    """Originated prop line per player-game for one prop family.

    The projection is built on *league-relative* production (a player's output
    divided by the league average for that week).  Without that adjustment the
    rolling mean carries the well-known late-season scoring decline and the
    model systematically over-states production.
    """
    df = _family_frame(stats, stat)
    if df.empty:
        return df
    league = df.groupby(["season", "week"])[stat].transform("mean")
    df["relative"] = df[stat] / league.replace(0, np.nan)
    df = df.sort_values(["player_id", "season", "week"])
    df["relative_projection"] = df.groupby("player_id")["relative"].transform(
        lambda s: _projection(s, config.PROP_ROLLING_WINDOW)
    )
    df = df.dropna(subset=["relative_projection"])
    df["projection"] = df["relative_projection"] * league
    df["line"] = (df["projection"] * 2).round() / 2
    df["actual"] = df[stat]
    df["over_hit"] = (df["actual"] > df["line"]).astype(float)
    df["under_hit"] = 1.0 - df["over_hit"]
    df["error"] = df["actual"] - df["projection"]
    return df


def prop_family_stats(stats: pd.DataFrame, season_from: int = 2010) -> List[Dict]:
    rows: List[Dict] = []
    for stat, label in (
        ("passing_yards", "QB passing yards"),
        ("rushing_yards", "RB rushing yards"),
        ("receiving_yards", "WR/TE receiving yards"),
        ("receptions", "WR/TE receptions"),
    ):
        if stat not in stats.columns:
            continue
        model = build_prop_model(stats[stats["season"] >= season_from], stat)
        if len(model) < config.PROP_MIN_SAMPLE:
            continue
        recent = model[model["season"] >= 2021]
        # Calibrate the line so that it splits the modelled distribution
        # 50/50: the offset is the median error measured on the calibration
        # window (seasons <= 2020) and is then applied to later seasons.
        calibration = model[model["season"] <= 2020]
        offset = float(calibration["error"].median()) if len(calibration) else 0.0
        model["calibrated_line"] = ((model["projection"] + offset) * 2).round() / 2
        model["calibrated_hit"] = (model["actual"] > model["calibrated_line"]).astype(float)
        eval_rows = model[model["season"] >= 2021]
        rows.append({
            "stat": stat,
            "label": label,
            "position_group": "/".join(sorted(FAMILY_POSITION[stat])),
            "player_games": int(len(model)),
            "player_games_recent": int(len(recent)),
            "seasons": f"{int(model['season'].min())}-{int(model['season'].max())}",
            "hit_rate_at_model_line": float(model["over_hit"].mean()),
            "hit_rate_recent": float(recent["over_hit"].mean()) if len(recent) else None,
            "calibration_offset": offset,
            "calibrated_hit_rate_eval": float(eval_rows["calibrated_hit"].mean()) if len(eval_rows) else None,
            "calibrated_hit_rate_all": float(model["calibrated_hit"].mean()),
            "eval_player_games": int(len(eval_rows)),
            "error_median": float(model["error"].median()),
            "mean_error": float(model["error"].mean()),
            "std_error": float(model["error"].std()),
            "mean_actual": float(model["actual"].mean()),
            "mean_line": float(model["line"].mean()),
            "std_actual": float(model["actual"].std()),
        })
    return rows


def same_game_prop_correlations(stats: pd.DataFrame, season_from: int = 2016) -> Dict[str, Dict[str, float]]:
    """Correlation between prop families computed across the players of one game.

    Each family is summed over its own position group, so a quarterback's
    passing yards are compared with *receivers'* receiving yards rather than
    with the same team's total including the quarterback's own zero rows.
    """
    df = stats[stats["season"] >= season_from].copy()
    df = df.drop_duplicates(subset=["game_id", "player_id"])
    out: Dict[str, Dict[str, float]] = {}
    combos = [
        ("passing_yards", "receiving_yards", "QB passing yards vs WR/TE receiving yards"),
        ("passing_yards", "rushing_yards", "QB passing yards vs RB rushing yards"),
        ("rushing_yards", "receiving_yards", "RB rushing yards vs WR/TE receiving yards"),
        ("rushing_yards", "receptions", "RB rushing yards vs WR/TE receptions"),
        ("receiving_yards", "receptions", "WR/TE receiving yards vs receptions"),
    ]
    for a, b, label in combos:
        if a not in df.columns or b not in df.columns:
            continue
        fa = _family_frame(df, a)
        fb = _family_frame(df, b)
        ga = fa.groupby("game_id")[a].sum().rename("a")
        gb = fb.groupby("game_id")[b].sum().rename("b")
        joined = pd.concat([ga, gb], axis=1).dropna()
        if len(joined) < 100:
            continue
        out[label] = {
            "correlation": float(joined["a"].corr(joined["b"])),
            "observations": int(len(joined)),
            "scope": "game-level family totals",
        }
    return out


def player_level_correlation(stats: pd.DataFrame, a: str, b: str, season_from: int = 2016) -> Dict:
    """Correlation between two prop families for the *same* player."""
    df = stats[(stats["season"] >= season_from) & df[a].notna() & df[b].notna()]
    df = df.drop_duplicates(subset=["game_id", "player_id"])
    if len(df) < 100:
        return {"correlation": float("nan"), "observations": int(len(df))}
    return {
        "correlation": float(df[a].corr(df[b])),
        "observations": int(len(df)),
        "scope": "same player, same game",
    }


def prop_combo_break_even(correlations: Dict[str, Dict[str, float]], leg_hit_rate: float = 0.53) -> List[Dict]:
    """Turn each correlation into a two-leg parlay break-even assessment."""
    from .correlation import parlay_math

    rows: List[Dict] = []
    for label, info in correlations.items():
        maths = parlay_math(info["correlation"], leg_hit_rate)
        rows.append({
            "combo": label,
            "correlation": info["correlation"],
            "observations": info["observations"],
            "scope": info.get("scope", ""),
            "leg_hit_rate": leg_hit_rate,
            "joint_hit_rate": maths["joint_hit_rate"],
            "parlay_decimal_odds": maths["parlay_decimal_odds"],
            "breakeven_leg_hit_rate": maths["breakeven_leg_hit_rate"],
            "edge_vs_breakeven": maths["edge"],
            "profitable": maths["profitable"],
        })
    rows.sort(key=lambda r: -r["edge_vs_breakeven"])
    return rows


def current_week_prop_lines(stats_2026: pd.DataFrame, week: Optional[int] = None, limit: int = 12) -> List[Dict]:
    """Originated prop lines for the latest published week, with the result."""
    rows: List[Dict] = []
    if week is None:
        week = int(stats_2026["week"].max()) if len(stats_2026) else 0
    for stat, label in (
        ("passing_yards", "Passing yards"),
        ("rushing_yards", "Rushing yards"),
        ("receiving_yards", "Receiving yards"),
        ("receptions", "Receptions"),
    ):
        if stat not in stats_2026.columns:
            continue
        model = build_prop_model(stats_2026, stat)
        if model.empty:
            continue
        model = model[model["week"] == week]
        if model.empty:
            continue
        model = model.sort_values("actual", ascending=False).head(limit)
        for _, r in model.iterrows():
            rows.append({
                "week": int(week),
                "player": r.get("player_display_name"),
                "team": r.get("recent_team"),
                "opponent": r.get("opponent_team"),
                "prop": label,
                "model_line": float(r["line"]),
                "actual": float(r["actual"]),
                "result": "over" if r["over_hit"] > 0.5 else "under",
            })
    return rows
