"""Correlation and joint-probability engine.

Parlays and player-prop combinations are where naive modelling fails hardest.
Two legs that both "look" like 60% plays are not a 36% parlay if the legs are
positively correlated - and they are not a 36% parlay if they are negatively
correlated either. The engine here computes the dependence explicitly and
refuses to produce a joint probability when the dependence is unmeasured.

What is computed
----------------
* Pearson and Spearman correlations between *event outcomes* derived from
  official game data (for example: does a team that wins the coin toss also
  score more, do two quarterbacks on the same game correlate, does a team's
  total correlate with its opponent's total).
* Fisher z confidence intervals, so a correlation estimated from a handful of
  games is visibly distinguishable from a stable one.
* Joint probability for a two-leg parlay using the Gaussian copula implied by
  the measured correlation, with the independent case shown alongside for
  comparison.

What is deliberately not computed
---------------------------------
Correlation between *strategies* and *market prices* cannot be computed from
official NFL data alone: it needs a licensed, timestamped odds history. Those
entries are emitted as ``unmeasured`` with the reason recorded, and the
verification step flags them for review. Inventing a correlation value would
defeat the purpose of the exercise.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:  # numpy is available in CI but the module degrades gracefully without it
    import numpy as _np
except ImportError:  # pragma: no cover
    _np = None


# ---------------------------------------------------------------------------
# correlation primitives
# ---------------------------------------------------------------------------
def _clean_pairs(xs: Sequence[Any], ys: Sequence[Any]) -> List[Tuple[float, float]]:
    pairs: List[Tuple[float, float]] = []
    for x, y in zip(xs, ys):
        try:
            fx = float(x)
            fy = float(y)
        except (TypeError, ValueError):
            continue
        if math.isnan(fx) or math.isnan(fy):
            continue
        pairs.append((fx, fy))
    return pairs


def pearson(xs: Sequence[Any], ys: Sequence[Any]) -> Optional[float]:
    """Pearson product-moment correlation, or ``None`` if undefined."""
    pairs = _clean_pairs(xs, ys)
    n = len(pairs)
    if n < 3:
        return None
    if _np is not None:
        arr = _np.asarray(pairs, dtype=float)
        if _np.std(arr[:, 0]) == 0 or _np.std(arr[:, 1]) == 0:
            return None
        return float(_np.corrcoef(arr[:, 0], arr[:, 1])[0, 1])
    mean_x = sum(p[0] for p in pairs) / n
    mean_y = sum(p[1] for p in pairs) / n
    cov = sum((p[0] - mean_x) * (p[1] - mean_y) for p in pairs)
    var_x = sum((p[0] - mean_x) ** 2 for p in pairs)
    var_y = sum((p[1] - mean_y) ** 2 for p in pairs)
    if var_x <= 0 or var_y <= 0:
        return None
    return cov / math.sqrt(var_x * var_y)


def _rank(values: Sequence[float]) -> List[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(order):
        stop = index
        while stop + 1 < len(order) and values[order[stop + 1]] == values[order[index]]:
            stop += 1
        average = (index + stop) / 2.0 + 1.0
        for position in range(index, stop + 1):
            ranks[order[position]] = average
        index = stop + 1
    return ranks


def spearman(xs: Sequence[Any], ys: Sequence[Any]) -> Optional[float]:
    """Spearman rank correlation, or ``None`` if undefined."""
    pairs = _clean_pairs(xs, ys)
    if len(pairs) < 3:
        return None
    rx = _rank([p[0] for p in pairs])
    ry = _rank([p[1] for p in pairs])
    return pearson(rx, ry)


def fisher_z_confidence(
    r: Optional[float], n: int, confidence: float = 0.95
) -> Tuple[Optional[float], Optional[float]]:
    """Confidence interval for a correlation using the Fisher z transform."""
    if r is None or n < 4 or abs(r) >= 1.0:
        return (None, None)
    z = 0.5 * math.log((1 + r) / (1 - r))
    se = 1.0 / math.sqrt(n - 3)
    # Normal quantile for the requested two-sided confidence level.
    zcrit = _normal_quantile(1 - (1 - confidence) / 2)
    low = math.tanh(z - zcrit * se)
    high = math.tanh(z + zcrit * se)
    return (low, high)


def _normal_quantile(p: float) -> float:
    """Inverse standard normal CDF (Acklam's rational approximation)."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00]
    p_low = 0.02425
    if p < p_low:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p <= 1 - p_low:
        q = p - 0.5
        r = q * q
        return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (
            ((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
        (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)


# ---------------------------------------------------------------------------
# joint probability
# ---------------------------------------------------------------------------
@dataclass
class JointProbability:
    """The joint probability of two binary events."""

    p_a: float
    p_b: float
    correlation: Optional[float]
    joint: Optional[float]
    independent_joint: float
    n_observations: int
    confidence_low: Optional[float] = None
    confidence_high: Optional[float] = None
    method: str = "gaussian-copula"
    status: str = "measured"
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "p_a": self.p_a,
            "p_b": self.p_b,
            "correlation": self.correlation,
            "joint_probability": self.joint,
            "independent_joint_probability": self.independent_joint,
            "n_observations": self.n_observations,
            "correlation_ci_low": self.confidence_low,
            "correlation_ci_high": self.confidence_high,
            "method": self.method,
            "status": self.status,
            "note": self.note,
        }


def bivariate_normal_joint(p_a: float, p_b: float, rho: float) -> Optional[float]:
    """P(X<=a, Y<=b) for a standard bivariate normal with correlation ``rho``."""
    if _np is None:
        return None
    a = _normal_quantile(p_a)
    b = _normal_quantile(p_b)
    if rho <= -0.999:
        return max(0.0, min(p_a, p_b))
    if rho >= 0.999:
        return min(1.0, p_a + p_b - max(0.0, (p_a + p_b - 1.0)))
    from math import exp, pi, sqrt

    denom = 1 - rho * rho
    if denom <= 0:
        return None

    def phi(x: float) -> float:
        return exp(-0.5 * x * x) / sqrt(2 * pi)

    def cdf(x: float) -> float:
        return 0.5 * (1 + math.erf(x / sqrt(2)))

    # Numerical integration over the conditional form.
    lo, hi = -8.0, 8.0
    steps = 2000
    h = (hi - lo) / steps
    total = 0.0
    for index in range(steps + 1):
        y = lo + index * h
        weight = 1.0 if index in (0, steps) else (4.0 if index % 2 else 2.0)
        conditional = cdf((b - rho * y) / sqrt(denom))
        total += weight * phi(y) * conditional
    return total * h / 3.0


def joint_probability(
    p_a: float,
    p_b: float,
    rho: Optional[float],
    n_observations: int,
    confidence: float = 0.95,
) -> JointProbability:
    """Joint probability of two legs, with the dependence made explicit."""
    independent = p_a * p_b
    if rho is None:
        return JointProbability(
            p_a=p_a,
            p_b=p_b,
            correlation=None,
            joint=None,
            independent_joint=independent,
            n_observations=n_observations,
            status="unmeasured",
            note=(
                "Dependence between the two legs is unmeasured. The independent "
                "product is shown for reference only and must not be used as a "
                "pricing or staking input."
            ),
        )
    low, high = fisher_z_confidence(rho, n_observations, confidence)
    joint = bivariate_normal_joint(p_a, p_b, rho)
    note = ""
    if n_observations < 30:
        note = (
            f"Correlation estimated from {n_observations} observations. Treat the "
            "point estimate as provisional; the interval spans "
            f"[{low:.2f}, {high:.2f}]." if low is not None else
            f"Correlation estimated from only {n_observations} observations."
        )
    return JointProbability(
        p_a=p_a,
        p_b=p_b,
        correlation=rho,
        joint=joint,
        independent_joint=independent,
        n_observations=n_observations,
        confidence_low=low,
        confidence_high=high,
        note=note,
    )


# ---------------------------------------------------------------------------
# correlation matrix over official game data
# ---------------------------------------------------------------------------
@dataclass
class CorrelationEntry:
    """One measured (or explicitly unmeasured) correlation."""

    id: str
    label: str
    scope: str
    metric: str
    value: Optional[float] = None
    n: int = 0
    ci_low: Optional[float] = None
    ci_high: Optional[float] = None
    status: str = "measured"
    note: str = ""
    source_url: Optional[str] = None
    source_label: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "scope": self.scope,
            "metric": self.metric,
            "value": self.value,
            "n": self.n,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "status": self.status,
            "note": self.note,
            "source_url": self.source_url,
            "source_label": self.source_label,
        }


def correlation_matrix(
    games: List[Dict[str, Any]],
    measures: Dict[str, List[Any]],
    *,
    source_url: str,
    source_label: str,
) -> List[Dict[str, Any]]:
    """Correlate game-level measures derived from official game books."""
    results: List[Dict[str, Any]] = []
    keys = list(measures.keys())
    for i, key_a in enumerate(keys):
        for key_b in keys[i + 1 :]:
            xs = measures[key_a]
            ys = measures[key_b]
            n = min(len(xs), len(ys))
            r = pearson(xs[:n], ys[:n])
            rho = spearman(xs[:n], ys[:n])
            low, high = fisher_z_confidence(r, n)
            results.append(
                CorrelationEntry(
                    id=f"{key_a}__vs__{key_b}",
                    label=f"{key_a.replace('_', ' ')} vs {key_b.replace('_', ' ')}",
                    scope="game",
                    metric="pearson",
                    value=r,
                    n=n,
                    ci_low=low,
                    ci_high=high,
                    status="measured" if r is not None else "insufficient_data",
                    note=(
                        f"Spearman rank correlation {rho:.3f}."
                        if rho is not None
                        else "Rank correlation unavailable."
                    ),
                    source_url=source_url,
                    source_label=source_label,
                ).to_dict()
            )
    return results


def unmeasured_correlations(
    specs: List[Dict[str, str]], source_url: str, source_label: str
) -> List[Dict[str, Any]]:
    """Record correlations that cannot be measured from official data alone.

    These are reported as unverified rather than guessed.
    """
    return [
        CorrelationEntry(
            id=spec["id"],
            label=spec["label"],
            scope=spec.get("scope", "strategy"),
            metric=spec.get("metric", "pearson"),
            value=None,
            n=0,
            status="unmeasured",
            note=spec.get("note", ""),
            source_url=source_url,
            source_label=source_label,
        ).to_dict()
        for spec in specs
    ]
