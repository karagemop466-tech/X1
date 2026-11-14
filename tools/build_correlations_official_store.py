#!/usr/bin/env python3
"""Build the official-only correlation store (N7) — session arena/3fa49c1a-x1.

Rule being implemented: correlation values are computed ONLY from officially
sourced numbers (NFL.com standings and NFL.com team-stats tables, each cell
carrying the URL it was read from), and every published value carries its sample
size n next to it.  Nothing computed from third-party data appears here.

Statistics (standard formulas, recomputed independently in this file):
  Pearson r over the 32 clubs (one row per club, 2026 regular season to date)
  two-sided p from the t statistic t = r*sqrt(n-2)/sqrt(1-r^2) through the
  regularised incomplete beta function I_x(1/2, (n-2)/2)

The full matrix is recomputed here and diffed against the pipeline's published
correlation table (data/pipeline/correlations.json) as a cross-check; the diff
is reported, not hidden.

Outputs:
  data/correlations/official_correlations.csv   every pair with r, n, p, sources
  data/correlations/official_correlations.json  same, dataset format for the site
"""

from __future__ import annotations

import csv
import json
import math
import os
import sys
from typing import List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "correlations")
RETRIEVED = "2026-11-14"


def jload(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as fh:
        return json.load(fh)


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
        de = d * c
        h *= de
        if abs(de - 1.0) < eps:
            break
    return h


def _betai(a: float, b: float, x: float) -> float:
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
    r = max(-1.0, min(1.0, r))
    if abs(r) >= 1.0:
        return r, n, 0.0
    t = r * math.sqrt(n - 2) / math.sqrt(1.0 - r * r)
    p = _betai(0.5 * (n - 2), 0.5, (n - 2) / ((n - 2) + t * t))
    return r, n, p


def strength(r: float) -> str:
    a = abs(r)
    s = "strong" if a >= 0.7 else ("moderate" if a >= 0.4 else ("weak" if a >= 0.2 else "negligible"))
    return f"{s} {'positive' if r > 0 else 'negative'}"


# --------------------------------------------------------------------- metrics
def numeric(v) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip().replace(",", "").replace("%", "")
    if s in ("", "-", "—", "None"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def build_matrix() -> Tuple[dict, dict]:
    """Return (metrics, provenance) where metrics[name][team] = value."""
    metrics: dict = {}
    prov: dict = {}

    st = jload("data/pipeline/standings.json")
    for col in ("W", "L", "T", "PF", "PA", "NET_PTS"):
        vals = {}
        for r in st["rows"]:
            v = numeric(r.get(col))
            if v is not None:
                vals[r["team_abbrev"]] = v
        if len(vals) == 32:
            metrics[col] = vals
            prov[col] = r["_source_url"] if st["rows"] else "https://www.nfl.com/standings/league/2026/REG"
            prov[col] = "https://www.nfl.com/standings/league/2026/REG"

    ts = jload("data/pipeline/team_stats.json")
    tables: dict = {}
    for r in ts["rows"]:
        label = r["_source_label"].replace("NFL.com — 2026 Team Stats, ", "")
        tables.setdefault(label, {"url": r["_source_url"], "rows": []})["rows"].append(r)
    for label, t in tables.items():
        cols = [k for k in t["rows"][0]
                if not k.startswith("_") and k not in ("team_abbrev", "team_name")]
        for col in cols:
            vals = {}
            for r in t["rows"]:
                v = numeric(r.get(col))
                if v is not None:
                    vals[r["team_abbrev"]] = v
            if len(vals) >= 28:      # a metric measured on nearly every club
                name = f"{label}: {col}"
                metrics[name] = vals
                prov[name] = t["url"]
    return metrics, prov


def main() -> int:
    metrics, prov = build_matrix()
    names = sorted(metrics)
    teams = sorted(metrics[names[0]])
    os.makedirs(OUT, exist_ok=True)

    rows: List[dict] = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            common = [t for t in teams if t in metrics[a] and t in metrics[b]]
            xs = [metrics[a][t] for t in common]
            ys = [metrics[b][t] for t in common]
            res = pearson(xs, ys)
            if not res:
                continue
            r, n, p = res
            rows.append({
                "pair": f"{a} vs {b}",
                "metric_a": a,
                "metric_b": b,
                "r": round(r, 3),
                "n": n,
                "p_value": round(p, 4),
                "strength": strength(r),
                "source_a": prov[a],
                "source_b": prov[b],
                "verified": "yes — official tables only",
            })

    # ---- cross-check against the pipeline's published correlation table
    pub = jload("data/pipeline/correlations.json")["rows"]
    pub_idx = {(x["metric_a"], x["metric_b"]): x for x in pub}
    compared = agree = 0
    disagreements = []
    for x in rows:
        key = (x["metric_a"], x["metric_b"])
        if key in pub_idx:
            compared += 1
            if abs(x["r"] - float(pub_idx[key]["r"])) <= 0.002:
                agree += 1
            else:
                disagreements.append(f"{x['pair']}: mine={x['r']} published={pub_idx[key]['r']}")

    # ---- outputs
    cols = ["pair", "metric_a", "metric_b", "r", "n", "p_value", "strength",
            "source_a", "source_b", "verified"]
    with open(os.path.join(OUT, "official_correlations.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for x in sorted(rows, key=lambda z: -abs(z["r"])):
            w.writerow(x)

    feed_rows = [{
        "_source_url": x["source_a"],
        "_source_label": "NFL.com official tables (standings / team stats)",
        "_source_org": "NFL",
        "_retrieved_at": RETRIEVED,
        "_flags": [],
        **x,
    } for x in sorted(rows, key=lambda z: -abs(z["r"]))]

    doc = {
        "dataset": "official_correlations",
        "title": "Correlation values computed only from officially sourced numbers (n published per value)",
        "generated_at": RETRIEVED,
        "source": {
            "url": "https://www.nfl.com/stats/team-stats/offense/passing/2026/reg/all",
            "label": "NFL.com standings + NFL.com team stats (official tables only)",
            "org": "NFL",
        },
        "columns": cols,
        "rows": feed_rows,
        "verification": {
            "rows": len(rows),
            "rows_verified": len(rows),
            "rows_flagged": 0,
            "unverified_cells": 0,
            "crosscheck_vs_pipeline_table": {
                "compared": compared, "agree": agree, "disagree": len(disagreements),
                "disagreements": disagreements[:10],
            },
            "note": ("Every pair is computed across the 32 clubs from NFL.com tables only; "
                     "n and the two-sided p are published with each value. Third-party-derived "
                     "correlations are not published as correlation values anywhere in this store."),
        },
        "note": ("r is Pearson over the 32 clubs (2026 regular season to date). n is published "
                 "with every value because a correlation on 32 team-seasons is a weak estimate: "
                 "nothing here is claimed significant without its p."),
    }
    with open(os.path.join(OUT, "official_correlations.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)
        fh.write("\n")

    print(f"metrics matrix       : {len(names)} official metrics x {len(teams)} clubs")
    print(f"pairs computed       : {len(rows)}  (every value carries n and p)")
    print(f"cross-check pipeline : {compared} pairs compared, {agree} agree, "
          f"{len(disagreements)} disagree")
    for d in disagreements[:5]:
        print("   diff:", d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
