"""Correlation and luck analysis.

Two questions are answered here:

1. *Which strategies duplicate each other?* - pairwise Pearson/Spearman
   correlation of per-bet profit streams on the games the two strategies have
   in common.
2. *How much of a strategy's result is luck?* - the same strategy is re-scored
   after removing one-score games (margin <= 8) and blowouts (margin >= 25),
   and the share of profit that came from those games is reported.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def _pivot(bets: pd.DataFrame) -> pd.Series:
    if bets is None or len(bets) == 0:
        return pd.Series(dtype=float)
    return bets.groupby("game_id")["profit"].sum()


def strategy_correlations(bets_by_strategy: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Pearson correlation matrix of strategy profit streams (shared games)."""
    pivots = {k: _pivot(v) for k, v in bets_by_strategy.items() if v is not None and len(v)}
    if not pivots:
        return pd.DataFrame()
    frame = pd.concat(pivots, axis=1).fillna(0.0)
    return frame.corr(method="pearson")


def strategy_spearman(bets_by_strategy: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    pivots = {k: _pivot(v) for k, v in bets_by_strategy.items() if v is not None and len(v)}
    if not pivots:
        return pd.DataFrame()
    frame = pd.concat(pivots, axis=1).fillna(0.0)
    return frame.corr(method="spearman")


def pairwise_detail(bets_by_strategy: Dict[str, pd.DataFrame]) -> List[Dict]:
    corr = strategy_correlations(bets_by_strategy)
    if corr.empty:
        return []
    rows: List[Dict] = []
    keys = list(corr.columns)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            shared = len(
                set(_pivot(bets_by_strategy[a]).index) & set(_pivot(bets_by_strategy[b]).index)
            )
            rows.append({
                "strategy_a": a,
                "strategy_b": b,
                "correlation": float(corr.loc[a, b]),
                "shared_games": int(shared),
            })
    rows.sort(key=lambda r: -abs(r["correlation"]))
    return rows


def luck_analysis(bets: pd.DataFrame, games: pd.DataFrame) -> Dict:
    """Split a strategy's result into 'luck games' and 'clean games'."""
    if bets is None or len(bets) == 0:
        return {}
    merged = bets.merge(
        games[["game_id", "margin", "total_points"]], on="game_id", how="left", suffixes=("", "_g")
    )
    margin = merged["margin_g"] if "margin_g" in merged.columns else merged["margin"]
    one_score = margin.abs() <= 8
    blowout = margin.abs() >= 25
    luck = one_score | blowout
    clean = ~luck

    def stats(sub: pd.DataFrame) -> Dict:
        if len(sub) == 0:
            return {"n": 0, "roi": float("nan"), "profit": 0.0}
        return {
            "n": int(len(sub)),
            "roi": float(sub["profit"].mean()),
            "profit": float(sub["profit"].sum()),
        }

    full = stats(merged)
    luck_stats = stats(merged[luck])
    clean_stats = stats(merged[clean])
    one_score_stats = stats(merged[one_score])
    blowout_stats = stats(merged[blowout])

    luck_profit_share = (
        luck_stats["profit"] / full["profit"] if abs(full["profit"]) > 1e-9 else float("nan")
    )
    return {
        "full": full,
        "luck_games": luck_stats,
        "clean_games": clean_stats,
        "one_score_games": one_score_stats,
        "blowout_games": blowout_stats,
        "luck_profit_share": luck_profit_share,
        "roi_drop_when_luck_removed": (
            full["roi"] - clean_stats["roi"] if np.isfinite(full["roi"]) and np.isfinite(clean_stats["roi"]) else float("nan")
        ),
    }


def prop_correlations(player_stats: pd.DataFrame, season_from: int = 2016) -> Dict:
    """Correlation between player-prop families inside the same game.

    Uses weekly player stats; only games where both families are present are
    used for each pair, and the number of paired observations is reported.
    """
    out: Dict = {}
    df = player_stats.copy()
    df = df[(df["season"] >= season_from) & (df["season_type"] == "REG")]

    def series(frame: pd.DataFrame, col: str) -> pd.Series:
        return frame.set_index(["game_id", "player_id"])[col]

    pairs = [
        ("passing_yards", "receiving_yards", "QB passing yards vs WR/TE receiving yards"),
        ("passing_yards", "rushing_yards", "QB passing yards vs RB rushing yards"),
        ("rushing_yards", "receiving_yards", "RB rushing yards vs receiving yards"),
        ("receptions", "receiving_yards", "Receptions vs receiving yards"),
        ("targets", "receiving_yards", "Targets vs receiving yards"),
    ]
    rows: List[Dict] = []
    for a, b, label in pairs:
        sub = df[df[a].notna() & df[b].notna()]
        if len(sub) < 30:
            continue
        # keep one row per player-game
        sub = sub.drop_duplicates(subset=["game_id", "player_id"])
        if a == "passing_yards" and b == "receiving_yards":
            # different players: correlate team totals per game
            agg = sub.groupby("game_id").agg(
                qb_pass=("passing_yards", "sum"), rec=("receiving_yards", "sum")
            )
            corr = float(agg["qb_pass"].corr(agg["rec"]))
            n = int(len(agg))
        else:
            piv = sub.set_index(["game_id", "player_id"])[[a, b]]
            corr = float(piv[a].corr(piv[b]))
            n = int(len(piv))
        rows.append({
            "pair": label,
            "stat_a": a,
            "stat_b": b,
            "correlation": corr,
            "observations": n,
            "seasons": f"{int(df['season'].min())}-{int(df['season'].max())}",
        })
    out["pairs"] = rows
    return out


def parlay_math(correlation: float, leg_hit_rate: float, price: float = 0.9091) -> Dict:
    """Break-even maths for a two-leg parlay built from correlated legs.

    ``leg_hit_rate`` is the hit rate of one leg, ``correlation`` the Pearson
    correlation between the two legs, ``price`` the net profit of a winning
    single leg at -110 (0.9091).  Returns the probability that both legs hit,
    the break-even hit rate for each leg, and whether the pair clears it.
    """
    p = leg_hit_rate
    joint = p * p + correlation * p * (1 - p)
    decimal = (1 + price) ** 2
    breakeven_joint = 1.0 / decimal
    breakeven_leg = float(np.sqrt(max(breakeven_joint, 0.0)))
    return {
        "leg_hit_rate": p,
        "correlation": correlation,
        "joint_hit_rate": joint,
        "parlay_decimal_odds": decimal,
        "breakeven_joint_hit_rate": breakeven_joint,
        "breakeven_leg_hit_rate": breakeven_leg,
        "edge": joint - breakeven_joint,
        "profitable": joint > breakeven_joint,
    }
