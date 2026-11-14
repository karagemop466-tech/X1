"""Walk-forward evaluation of the strategy library.

For every evaluation season the parameter set of each strategy is re-selected
using only games that finished in earlier seasons, then applied to the
evaluation season.  This keeps the backtest honest: no season ever influences
the parameters used inside itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from . import config
from .strategies import Strategy

MIN_TRAIN_BETS = 100
FIRST_EVAL_SEASON = 2015


@dataclass
class StrategyResult:
    strategy: Strategy
    bets: pd.DataFrame
    param_history: List[Dict]
    param_bets: Dict[str, pd.DataFrame]
    grid: List[Dict]

    @property
    def key(self) -> str:
        return self.strategy.key


def _param_label(params: Dict) -> str:
    return ",".join(f"{k}={v}" for k, v in sorted(params.items())) if params else "default"


def _fingerprint(frame: pd.DataFrame) -> str:
    import hashlib

    cols = ["game_id", "season", "week", "home_score", "away_score", "market_spread", "market_total"]
    payload = frame[cols].to_csv(index=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def evaluate_strategy(
    strategy: Strategy,
    frame: pd.DataFrame,
    first_eval_season: int = FIRST_EVAL_SEASON,
    use_cache: bool = True,
) -> StrategyResult:
    grid = strategy.param_grid or [strategy.default_params or {}]
    fp = _fingerprint(frame)
    cache_dir = config.DATA_DIR / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    param_bets: Dict[str, pd.DataFrame] = {}
    for params in grid:
        label = _param_label(params)
        cache_file = cache_dir / f"{strategy.key}__{label.replace('/', '_').replace('=', '-').replace(',', '_')}__{fp}.parquet"
        if use_cache and cache_file.exists():
            df = pd.read_parquet(cache_file)
        else:
            rows = strategy.generate(frame, params)
            df = pd.DataFrame(rows)
            if df.empty:
                df = pd.DataFrame(
                    columns=[
                        "game_id", "season", "week", "gameday", "market", "side", "line",
                        "odds", "outcome", "profit", "strategy", "away_team", "home_team",
                    ]
                )
            try:
                df.to_parquet(cache_file, index=False)
            except Exception:  # pragma: no cover - cache is best effort
                pass
        param_bets[label] = df

    seasons = sorted(set(frame["season"].unique()))
    all_bets: List[pd.DataFrame] = []
    history: List[Dict] = []

    for season in seasons:
        if season < first_eval_season:
            continue
        best_label, best_score, best_roi = None, -np.inf, float("nan")
        for label, bets in param_bets.items():
            tb = bets[bets["season"] < season] if len(bets) else bets
            if len(tb) < MIN_TRAIN_BETS:
                continue
            profits = tb["profit"].values.astype(float)
            r = float(profits.mean())
            std = float(profits.std(ddof=1)) if len(profits) > 1 else 0.0
            # Risk-adjusted selection: a t-like score so that a high ROI on a
            # handful of bets cannot beat a steadier signal with more evidence.
            if std <= 1e-12:
                score = np.inf if r > 0 else -np.inf
            else:
                score = r / (std / np.sqrt(len(profits)))
            if score > best_score or (score == best_score and best_label is not None
                                      and len(tb) > len(param_bets[best_label])):
                best_score, best_label, best_roi = score, label, r
        if best_label is None:
            best_label = _param_label(grid[0])
            best_roi = float("nan")
        eval_bets = param_bets[best_label]
        eval_bets = eval_bets[eval_bets["season"] == season]
        if len(eval_bets):
            all_bets.append(eval_bets)
        history.append({
            "season": int(season),
            "selected_params": best_label,
            "train_roi": None if not np.isfinite(best_roi) else round(float(best_roi), 5),
            "bets": int(len(eval_bets)),
        })

    bets = pd.concat(all_bets, ignore_index=True) if all_bets else pd.DataFrame()
    return StrategyResult(
        strategy=strategy,
        bets=bets,
        param_history=history,
        param_bets=param_bets,
        grid=grid,
    )


def stability(result: StrategyResult) -> Dict:
    """Share of neighbouring parameter values that stay profitable OOS."""
    if len(result.grid) < 2:
        return {
            "share_positive": float("nan"),
            "detail": "Single-parameter strategy - no neighbouring variants to test.",
        }
    labels = [_param_label(p) for p in result.grid]
    chosen = [h["selected_params"] for h in result.param_history]
    if not chosen:
        return {"share_positive": float("nan"), "detail": "No walk-forward history."}

    from collections import Counter

    modal = Counter(chosen).most_common(1)[0][0]
    if modal not in labels:
        return {"share_positive": float("nan"), "detail": "Selected parameter not in the grid."}
    idx = labels.index(modal)
    neighbours = []
    if idx - 1 >= 0:
        neighbours.append(labels[idx - 1])
    if idx + 1 < len(labels):
        neighbours.append(labels[idx + 1])

    oos_seasons = {h["season"] for h in result.param_history}
    positive = 0
    detail_parts = []
    for label in neighbours:
        bets = result.param_bets.get(label)
        if bets is None or not len(bets):
            continue
        sub = bets[bets["season"].isin(oos_seasons)]
        if not len(sub):
            continue
        r = float(sub["profit"].mean())
        detail_parts.append(f"{label}: {r * 100:+.2f}%")
        if r > 0:
            positive += 1
    share = positive / len(neighbours) if neighbours else float("nan")
    return {
        "share_positive": share,
        "detail": "Neighbouring parameter values on the same out-of-sample window - "
        + ("; ".join(detail_parts) if detail_parts else "no neighbours evaluated"),
    }


def sensitivity_table(result: StrategyResult) -> List[Dict]:
    """ROI of every parameter value over the out-of-sample window."""
    oos_seasons = {h["season"] for h in result.param_history}
    rows = []
    for label, bets in result.param_bets.items():
        if bets is None or not len(bets):
            rows.append({"params": label, "bets": 0, "roi": None, "hit_rate": None})
            continue
        sub = bets[bets["season"].isin(oos_seasons)]
        if not len(sub):
            rows.append({"params": label, "bets": 0, "roi": None, "hit_rate": None})
            continue
        rows.append({
            "params": label,
            "bets": int(len(sub)),
            "roi": float(sub["profit"].mean()),
            "hit_rate": float((sub["outcome"] > 0.5).mean()),
        })
    return rows
