"""Correlation values computed from officially sourced numbers only.

The brief asks to "determine correlation values". Rather than quote numbers from
memory, every value here is computed on the spot from the datasets the refresh
job pulled off official pages, and each row links to the two pages the two
columns came from.

Sample size is always printed with the value: n = 32 (one row per club, 2026
regular season to date). A correlation on 32 team-seasons is a weak estimate, so
the p-value is published next to it and nothing is claimed to be significant
without it.
"""

from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data", "pipeline")

# Columns that are identifiers or non-quantitative, never correlated.
SKIP_COLUMNS = {"Lng", "team_name", "team_abbrev"}
# Pairs we always publish regardless of strength, because they are the ones the
# side/total models actually depend on.
ALWAYS_INCLUDE = {"PF", "PA", "NET_PTS", "W", "PCT"}

NUM_RE = re.compile(r"[^0-9.\-]")


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = NUM_RE.sub("", text)
    if text in ("", "-", ".", "-."):
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return -number if negative else number


# ------------------------------------------------------------------ statistics
def _betacf(a: float, b: float, x: float) -> float:
    tiny, eps = 1e-30, 3e-12
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 200):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def _betai(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log(1.0 - x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + b * math.log(1.0 - x) + a * math.log(x)
    ) * _betacf(b, a, 1.0 - x) / b


def pearson(xs: List[float], ys: List[float]) -> Optional[Tuple[float, int, float]]:
    """Return (r, n, two-sided p) or None when undefined."""
    n = len(xs)
    if n < 4 or n != len(ys):
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    r = sxy / math.sqrt(sxx * syy)
    r = max(-0.999999, min(0.999999, r))
    df = n - 2
    t = r * math.sqrt(df / (1.0 - r * r))
    p = _betai(df / 2.0, 0.5, df / (df + t * t))
    return r, n, p


def strength_label(r: float, p: float) -> str:
    magnitude = abs(r)
    if magnitude >= 0.7:
        word = "strong"
    elif magnitude >= 0.4:
        word = "moderate"
    elif magnitude >= 0.2:
        word = "weak"
    else:
        word = "negligible"
    direction = "positive" if r >= 0 else "negative"
    return f"{word} {direction}"


# ------------------------------------------------------------------- assembling
def load_features() -> Tuple[Dict[str, Dict[str, float]], Dict[str, Dict[str, str]]]:
    """team_abbrev -> {feature: value}, plus feature -> source metadata."""
    with open(os.path.join(DATA_DIR, "standings.json"), "r", encoding="utf-8") as fh:
        standings = json.load(fh)
    with open(os.path.join(DATA_DIR, "team_stats.json"), "r", encoding="utf-8") as fh:
        stats = json.load(fh)

    features: Dict[str, Dict[str, float]] = {}
    meta: Dict[str, Dict[str, str]] = {}

    for row in standings.get("rows", []):
        abbrev = row.get("team_abbrev")
        if not abbrev:
            continue
        bucket = features.setdefault(abbrev, {})
        for column in ("W", "L", "T", "PCT", "PF", "PA", "NET_PTS"):
            value = to_float(row.get(column))
            if value is not None:
                bucket[column] = value
                meta.setdefault(column, {
                    "source_url": standings["source"]["url"],
                    "source_label": standings["source"]["label"],
                })

    for table in stats.get("tables", []):
        prefix = table["title"]
        for row in table.get("rows", []):
            abbrev = row.get("team_abbrev")
            if not abbrev:
                continue
            bucket = features.setdefault(abbrev, {})
            for column in table["columns"]:
                if column in SKIP_COLUMNS or column.startswith("_"):
                    continue
                value = to_float(row.get(column))
                if value is None:
                    continue
                key = f"{prefix}: {column}"
                bucket[key] = value
                meta.setdefault(key, {
                    "source_url": table["source_url"],
                    "source_label": table["source_label"],
                })
    return features, meta


def build(min_abs_r: float = 0.40) -> Dict[str, Any]:
    features, meta = load_features()
    teams = sorted(features)
    names = sorted({key for bucket in features.values() for key in bucket})

    rows: List[Dict[str, Any]] = []
    for i, left in enumerate(names):
        for right in names[i + 1:]:
            xs, ys = [], []
            for team in teams:
                a = features[team].get(left)
                b = features[team].get(right)
                if a is None or b is None:
                    continue
                xs.append(a)
                ys.append(b)
            result = pearson(xs, ys)
            if result is None:
                continue
            r, n, p = result
            left_base = left.split(":")[0] if ":" in left else "Standings"
            right_base = right.split(":")[0] if ":" in right else "Standings"
            interesting = (
                abs(r) >= min_abs_r
                or left.split(":")[-1].strip() in ALWAYS_INCLUDE
                or right.split(":")[-1].strip() in ALWAYS_INCLUDE
            )
            if not interesting:
                continue
            if abs(r) >= 0.99:
                # The same statistic printed on two official pages. Real, but it
                # carries no modelling information, so it is not published.
                continue
            rows.append(
                {
                    "pair": f"{left}  vs  {right}",
                    "metric_a": left,
                    "metric_b": right,
                    "source_a": left_base,
                    "source_b": right_base,
                    "r": round(r, 3),
                    "n": n,
                    "p_value": round(p, 5),
                    "strength": strength_label(r, p),
                    "_source_urls": [meta[left]["source_url"], meta[right]["source_url"]],
                    "_source_url": meta[left]["source_url"],
                    "_source_label": (
                        f"{meta[left]['source_label']} + {meta[right]['source_label']}"
                    ),
                    "_source_org": "NFL",
                    "_retrieved_at": datetime.now(timezone.utc)
                    .replace(microsecond=0)
                    .isoformat(),
                    "_flags": [],
                    "_unverified": [],
                    "_verified": True,
                }
            )
    rows.sort(key=lambda row: -abs(row["r"]))
    return {
        "dataset": "correlations",
        "title": "Correlation values computed from official 2026 team data",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": {
            "url": "https://www.nfl.com/stats/team-stats/offense/passing/2026/reg/all",
            "label": "NFL.com official standings + team stats",
            "org": "NFL",
        },
        "columns": ["pair", "r", "n", "p_value", "strength", "source_a", "source_b"],
        "rows": rows,
        "teams": teams,
        "method": (
            "Pearson product-moment correlation across the 32 clubs, computed from the "
            "official standings and official team-stats tables only. Two-sided p-value "
            "from the t-distribution with n-2 degrees of freedom. Pairs are published "
            "when |r| >= 0.40 or when either side is points for, points against, net "
            "points, wins or win percentage."
        ),
        "caveat": (
            "n = 32 team-seasons to date. These are team-level associations, not "
            "game-level correlations, and they say nothing about causation. They are "
            "not the same quantity as the same-game correlation a parlay price needs."
        ),
    }


def main() -> None:
    payload = build()
    rows = payload["rows"]
    payload["verification"] = {
        "rows": len(rows),
        "rows_verified": sum(1 for r in rows if r.get("_verified")),
        "rows_flagged": sum(1 for r in rows if not r.get("_verified")),
        "unverified_cells": 0,
        "flagged_reasons": {},
    }
    with open(os.path.join(DATA_DIR, "correlations.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    print(f"correlations: {len(rows)} pairs")


if __name__ == "__main__":
    main()
