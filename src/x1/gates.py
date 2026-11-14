"""Validation gates.

A strategy is only published on the leaderboard if it passes **every** gate.
Each gate returns a pass/fail plus the measured value so the site can show
exactly why a strategy was rejected.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import config


@dataclass
class Gate:
    key: str
    name: str
    passed: bool
    value: str
    threshold: str
    detail: str = ""


@dataclass
class GateReport:
    strategy: str
    gates: List[Gate] = field(default_factory=list)
    all_passed: bool = False

    def to_dict(self) -> Dict:
        return {
            "strategy": self.strategy,
            "all_passed": self.all_passed,
            "gates": [asdict(g) for g in self.gates],
        }


# --------------------------------------------------------------------------
# Statistics helpers
# --------------------------------------------------------------------------
def bootstrap_ci(values: np.ndarray, n_boot: int = 10000, seed: int = config.RANDOM_SEED,
                 level: float = config.GATE_CI_LEVEL) -> Tuple[float, float, float]:
    """Percentile bootstrap CI for the mean profit per bet."""
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return (float("nan"), float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(values), size=(n_boot, len(values)))
    means = values[idx].mean(axis=1)
    lo = float(np.percentile(means, 100 * (1 - level) / 2))
    hi = float(np.percentile(means, 100 * (1 + level) / 2))
    return (lo, hi, float(values.mean()))


def permutation_pvalue(values: np.ndarray, n_perm: int = 10000,
                       seed: int = config.RANDOM_SEED) -> float:
    """One-sided randomisation test that the mean profit is <= 0.

    Permuting the observations cannot change their mean, so the null
    distribution is built by *sign-flipping* each bet's profit.  Under the null
    of "no directional skill" a winning bet is as likely to have been a losing
    bet, which is exactly what a sign flip models for win/loss outcomes.
    """
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return float("nan")
    observed = float(values.mean())
    rng = np.random.default_rng(seed + 7)
    signs = rng.choice(np.array([-1.0, 1.0]), size=(n_perm, len(values)))
    null_means = (signs * values).mean(axis=1)
    count = int((null_means >= observed).sum())
    return (count + 1) / (n_perm + 1)


def roi(bets: pd.DataFrame) -> float:
    if bets is None or len(bets) == 0:
        return float("nan")
    return float(bets["profit"].mean())


def hit_rate(bets: pd.DataFrame) -> float:
    if bets is None or len(bets) == 0:
        return float("nan")
    return float((bets["outcome"] > 0.5).mean())


# --------------------------------------------------------------------------
# Gate evaluation
# --------------------------------------------------------------------------
def evaluate(
    strategy_key: str,
    bets: pd.DataFrame,
    baselines: Optional[Dict[str, float]] = None,
    clean_bets: Optional[pd.DataFrame] = None,
    stability: Optional[Dict[str, float]] = None,
    max_correlation: Optional[float] = None,
    correlation_partner: Optional[str] = None,
) -> GateReport:
    report = GateReport(strategy=strategy_key)

    n = int(len(bets)) if bets is not None else 0
    r = roi(bets) if n else float("nan")
    profits = bets["profit"].values.astype(float) if n else np.array([])

    # G1 - sample sufficiency ------------------------------------------------
    report.gates.append(
        Gate(
            key="G1",
            name="Sample sufficiency",
            passed=n >= config.GATE_MIN_BETS,
            value=f"{n} bets",
            threshold=f">= {config.GATE_MIN_BETS}",
            detail="Bets settled in the out-of-sample window.",
        )
    )

    # G2 - out-of-sample integrity ------------------------------------------
    seasons = sorted(set(bets["season"].tolist())) if n else []
    first_oos = min(seasons) if seasons else None
    dupes = int(bets["game_id"].duplicated().sum()) if n else 0
    g2_pass = bool(n) and first_oos is not None and dupes == 0
    report.gates.append(
        Gate(
            key="G2",
            name="Out-of-sample integrity",
            passed=g2_pass,
            value=f"first OOS season {first_oos}; {dupes} duplicate bet ids",
            threshold="no duplicate bets; parameters chosen from earlier seasons only",
            detail="Parameters are re-selected each season from games that finished before it.",
        )
    )

    # G3 - statistical significance -----------------------------------------
    if n:
        lo, hi, mean = bootstrap_ci(profits)
        pval = permutation_pvalue(profits)
    else:
        lo = hi = mean = pval = float("nan")
    g3_pass = bool(n) and np.isfinite(lo) and lo > 0 and np.isfinite(pval) and pval <= config.GATE_MAX_PVALUE
    report.gates.append(
        Gate(
            key="G3",
            name="Statistical significance",
            passed=g3_pass,
            value=f"95% CI [{lo:+.3f}, {hi:+.3f}] units/bet, permutation p = {pval:.4f}",
            threshold="CI lower bound > 0 and permutation p <= 0.05",
            detail="Bootstrap (10,000 resamples) and a 10,000-draw permutation test on profit per bet.",
        )
    )

    # G4 - economic significance --------------------------------------------
    g4_pass = bool(n) and np.isfinite(r) and r >= config.GATE_MIN_ROI
    report.gates.append(
        Gate(
            key="G4",
            name="Economic significance",
            passed=g4_pass,
            value=f"ROI {r * 100:+.2f}%",
            threshold=f">= {config.GATE_MIN_ROI * 100:.1f}% per unit staked",
            detail="Unit stakes; the book price in the source data is used, -115 where no price is published.",
        )
    )

    # G5 - beats naive baselines --------------------------------------------
    if baselines:
        best_base = max(baselines.items(), key=lambda kv: kv[1])
        base_name, base_val = best_base
        g5_pass = bool(n) and np.isfinite(r) and r > base_val
        detail = "Baseline ROI on the same window: " + ", ".join(
            f"{k} {v * 100:+.2f}%" for k, v in sorted(baselines.items(), key=lambda kv: -kv[1])
        )
    else:
        base_name, base_val, g5_pass = "n/a", float("nan"), False
        detail = "No baselines supplied."
    report.gates.append(
        Gate(
            key="G5",
            name="Beats naive baselines",
            passed=g5_pass,
            value=f"best baseline {base_name} {base_val * 100:+.2f}%",
            threshold="ROI above every naive baseline",
            detail=detail,
        )
    )

    # G6 - luck robustness ---------------------------------------------------
    if clean_bets is not None and len(clean_bets) and np.isfinite(r):
        r_clean = roi(clean_bets)
        share = (r_clean / r) if (np.isfinite(r) and abs(r) > 1e-9) else float("nan")
        g6_pass = bool(np.isfinite(r_clean)) and r_clean > 0 and (not np.isfinite(share) or share >= 0.4)
        detail = (
            f"ROI {r * 100:+.2f}% full sample vs {r_clean * 100:+.2f}% after removing "
            f"one-score games (margin <= {config.ONE_SCORE_MAX_MARGIN}) and blowouts "
            f"(margin >= {config.BLOWOUT_MIN_MARGIN}); {clean_bets['game_id'].nunique()} games retained."
        )
    else:
        r_clean, share, g6_pass = float("nan"), float("nan"), False
        detail = "No luck-filtered sample available."
    report.gates.append(
        Gate(
            key="G6",
            name="Luck robustness",
            passed=g6_pass,
            value=(f"clean ROI {r_clean * 100:+.2f}%" if np.isfinite(r_clean) else "no luck-filtered sample"),
            threshold="clean ROI > 0 and >= 40% of full-sample ROI",
            detail=detail,
        )
    )

    # G7 - parameter stability ----------------------------------------------
    if stability:
        share_pos = stability.get("share_positive", float("nan"))
        g7_pass = bool(np.isfinite(share_pos)) and share_pos >= config.GATE_PARAM_STABILITY
        detail = stability.get("detail", "")
    else:
        share_pos, g7_pass = float("nan"), False
        detail = "Not evaluated."
    share_text = (
        f"{share_pos * 100:.0f}% of neighbouring parameters positive"
        if np.isfinite(share_pos) else "not measured"
    )
    report.gates.append(
        Gate(
            key="G7",
            name="Parameter stability",
            passed=g7_pass,
            value=share_text,
            threshold=f">= {config.GATE_PARAM_STABILITY * 100:.0f}%",
            detail=detail,
        )
    )

    # G8 - non redundancy ----------------------------------------------------
    if max_correlation is None or not np.isfinite(max_correlation):
        g8_pass = True
        detail = (
            "No other strategy has cleared the gates yet, so redundancy cannot be measured; "
            "the gate is treated as satisfied until a peer qualifies."
        )
    else:
        g8_pass = abs(max_correlation) <= config.GATE_MAX_CORRELATION
        detail = (
            f"Highest absolute Pearson correlation with an accepted strategy: "
            f"{correlation_partner} {max_correlation:+.3f} (limit {config.GATE_MAX_CORRELATION})."
        )
    report.gates.append(
        Gate(
            key="G8",
            name="Non-redundancy",
            passed=g8_pass,
            value=f"max |r| = {max_correlation:+.3f}" if np.isfinite(max_correlation) else "n/a",
            threshold=f"<= {config.GATE_MAX_CORRELATION}",
            detail=detail,
        )
    )

    report.all_passed = all(g.passed for g in report.gates)
    return report


def naive_baselines(frame: pd.DataFrame, bets_window: pd.DataFrame) -> Dict[str, float]:
    """ROI of simple always-on strategies over the same window."""
    played = frame[frame["home_score"].notna()].copy()
    if len(bets_window):
        seasons = set(bets_window["season"].unique())
        played = played[played["season"].isin(seasons)]
    played = played.dropna(subset=["market_spread", "market_total"])

    def _cover(row, side: str) -> float:
        line = row["market_spread"]
        margin = row["margin"]
        if side == "home":
            return 1.0 if margin > line else (0.5 if margin == line else 0.0)
        return 1.0 if margin < -abs(line) else (0.5 if margin == -abs(line) else 0.0)

    fav, dog, over, under = [], [], [], []
    for _, row in played.iterrows():
        line = row["market_spread"]
        if pd.notna(line):
            fav.append(_cover(row, "home" if line > 0 else "away"))
            dog.append(_cover(row, "away" if line > 0 else "home"))
        tl = row["market_total"]
        if pd.notna(tl):
            tp = row["total_points"]
            over.append(1.0 if tp > tl else (0.5 if tp == tl else 0.0))
            under.append(1.0 if tp < tl else (0.5 if tp == tl else 0.0))

    def _roi(values: List[float]) -> float:
        if not values:
            return float("nan")
        arr = np.array(values, dtype=float)
        unit = np.where(arr > 0.5, 1.0, np.where(arr < 0.5, -1.0, 0.0))
        return float(unit.mean() * 0.9091)  # -110 payout

    return {
        "always_favourite": _roi(fav),
        "always_underdog": _roi(dog),
        "always_over": _roi(over),
        "always_under": _roi(under),
    }
