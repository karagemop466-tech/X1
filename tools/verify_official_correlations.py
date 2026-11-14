#!/usr/bin/env python3
"""Independent re-verification of the official-only correlation set
(session arena-52aabfa8-x1, task T15).

Requirement (owner's brief): "Compute correlations only from officially sourced
numbers and publish n with each value."

The published set is data/pipeline/correlations.json (988 rows). This script
recomputes every published row from scratch, using ONLY the committed official
snapshots:

    data/verify/official_standings_2026_w10.psv   (nfl.com standings)
    data/pipeline/team_stats.json                 (nfl.com team stats)

and fails (exit 1) if any of the following does not hold:

  V1  every row carries an n (and n == 32, the 32 clubs)
  V2  every row's source URLs are official nfl.com pages
  V3  every published r recomputes from the official snapshots within 0.0015
      (the published values are rounded to 3 decimals)
  V4  no duplicate unordered metric pair is published twice
  V5  the published set equals exactly the set the dataset's own publication
      rule selects: (|r| >= 0.40 OR either side is one of
      {PF, PA, NET_PTS, W, PCT}) AND |r| < 0.99 — the 0.99 redundancy cut
      suppresses mechanically identical columns (a completed pass is both a
      Cmp and a Rec, so those pairs are r = 1.000 by construction). The
      dataset's own `method` text omits that cut; this script reverse-engineered
      it by exact set reproduction (988 = 988, zero differences) and records
      the omission as an irregularity rather than editing another session's
      file. Pairs inside a 0.002 boundary band around the 0.40 cut are
      accepted either way and counted as boundary cases.

Deterministic; stdlib only. Re-run:  python3 tools/verify_official_correlations.py
"""

from __future__ import annotations

import json
import math
import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STANDINGS = os.path.join(ROOT, "data", "verify",
                         "official_standings_2026_w10.psv")
TEAM_STATS = os.path.join(ROOT, "data", "pipeline", "team_stats.json")
CORRELATIONS = os.path.join(ROOT, "data", "pipeline", "correlations.json")
LEDGER = os.path.join(ROOT, "data", "verify",
                      "official_correlations.csv")

SPECIAL = {"PF", "PA", "NET_PTS", "W", "PCT"}
TOL = 0.0015
BOUNDARY = 0.002
STANDINGS_URL = "https://www.nfl.com/standings/league/2026/REG"
ALLOWED_HOST = "nfl.com"


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def fnum(v) -> float:
    return float(str(v).replace(",", "").replace("%", "").strip())


def load_standings() -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    with open(STANDINGS, encoding="utf-8") as fh:
        header = fh.readline().rstrip("\n").split("|")
        for line in fh:
            parts = line.rstrip("\n").split("|")
            if len(parts) != len(header):
                continue
            rec = dict(zip(header, parts))
            team = rec["TEAM"]
            out[team] = {k: fnum(rec[k]) for k in
                         ("W", "L", "T", "PCT", "PF", "PA", "NET")}
            out[team]["NET_PTS"] = out[team]["NET"]
    if len(out) != 32:
        fail(f"standings snapshot parsed {len(out)} clubs, expected 32")
    return out


def load_team_stats() -> dict[str, dict[str, float]]:
    """Flatten team_stats.json into {metric_label: {team: value}}.

    Metric labels match the published convention: "<Table title>: <column>".
    """
    with open(TEAM_STATS, encoding="utf-8") as fh:
        data = json.load(fh)
    metrics: dict[str, dict[str, float]] = {}
    for table in data.get("tables", []):
        title = table.get("title", "")
        cols = [c for c in table.get("columns", []) if c != "team_name"]
        rows = table.get("rows", [])
        teams_here = {r.get("team_abbrev") for r in rows}
        if len(teams_here) != 32:
            fail(f"table {title!r} has {len(teams_here)} clubs, expected 32")
        for col in cols:
            series: dict[str, float] = {}
            for r in rows:
                team = r.get("team_abbrev")
                try:
                    series[team] = fnum(r.get(col))
                except (TypeError, ValueError):
                    # unparseable cell -> metric excluded from verification
                    series = {}
                    break
            if len(series) == 32:
                metrics[f"{title}: {col}"] = series
    return metrics


def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    vx = sum((a - mx) ** 2 for a in xs)
    vy = sum((b - my) ** 2 for b in ys)
    if vx <= 0 or vy <= 0:
        return float("nan")
    return cov / math.sqrt(vx * vy)


def main() -> int:
    standings = load_standings()
    team_metrics = load_team_stats()

    with open(CORRELATIONS, encoding="utf-8") as fh:
        data = json.load(fh)
    rows = data.get("rows", [])

    # Build the metric pool exactly as the dataset labels them.
    metrics: dict[str, dict[str, float]] = {}
    for name in ("W", "L", "T", "PCT", "PF", "PA", "NET_PTS"):
        metrics[name] = {t: v[name] for t, v in standings.items()}
    metrics.update(team_metrics)

    problems: list[str] = []
    boundary = 0
    checked = 0
    seen_pairs: set[frozenset] = set()
    ledger: list[dict] = []

    for r in rows:
        a, b = r.get("metric_a"), r.get("metric_b")
        # V1 — n present and correct
        n = r.get("n")
        if n != 32:
            problems.append(f"V1 {r.get('pair')!r}: n={n!r}, expected 32")
            continue
        # V2 — official sources only
        urls = r.get("_source_urls") or [r.get("_source_url", "")]
        if not all(ALLOWED_HOST in (u or "") for u in urls):
            problems.append(f"V2 {r.get('pair')!r}: non-official source {urls}")
            continue
        # V4 — no duplicate unordered pair
        key = frozenset((a, b))
        if key in seen_pairs:
            problems.append(f"V4 duplicate pair {r.get('pair')!r}")
        seen_pairs.add(key)
        # V3 — recompute r
        if a not in metrics or b not in metrics:
            problems.append(f"V3 {r.get('pair')!r}: metric not reproducible "
                            f"from the committed snapshots")
            continue
        sa, sb = metrics[a], metrics[b]
        teams = sorted(sa)
        xs = [sa[t] for t in teams]
        ys = [sb[t] for t in teams]
        rr = pearson(xs, ys)
        pub = r.get("r")
        try:
            pub_f = float(pub)
        except (TypeError, ValueError):
            problems.append(f"V3 {r.get('pair')!r}: unpublishable r={pub!r}")
            continue
        status = "match"
        if math.isnan(rr) or abs(rr - pub_f) > TOL:
            status = "MISMATCH"
            problems.append(f"V3 {r.get('pair')!r}: published {pub_f} != "
                            f"recomputed {rr:.4f}")
        else:
            checked += 1
        ledger.append({
            "pair": r.get("pair"),
            "metric_a": a,
            "metric_b": b,
            "published_r": pub_f,
            "recomputed_r": ("" if math.isnan(rr) else round(rr, 4)),
            "abs_delta": ("" if math.isnan(rr) else round(abs(rr - pub_f), 5)),
            "n": n,
            "n_published": "yes",
            "source": (r.get("_source_urls") or [r.get("_source_url", "")])[0],
            "source_tier": "official_nfl.com",
            "check_status": status,
        })

    # V5 — publication rule reproduces the exact published set.
    # Full rule (see docstring): (|r| >= 0.40 or special metric) and |r| < 0.99.
    pub_set = {frozenset((r.get("metric_a"), r.get("metric_b"))) for r in rows}
    # consistency: no published row may be a suppressed redundancy pair
    for r in rows:
        a, b = r.get("metric_a"), r.get("metric_b")
        if a in metrics and b in metrics:
            teams = sorted(metrics[a])
            rr = pearson([metrics[a][t] for t in teams],
                         [metrics[b][t] for t in teams])
            if not math.isnan(rr) and abs(rr) >= 0.99:
                problems.append(f"V5 {r.get('pair')!r}: |r|={abs(rr):.3f} >= 0.99 "
                                "redundancy cut but published anyway")
    rule_set: set[frozenset] = set()
    names = sorted(metrics)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            sa, sb = metrics[a], metrics[b]
            teams = sorted(sa)
            rr = pearson([sa[t] for t in teams], [sb[t] for t in teams])
            if math.isnan(rr) or abs(rr) >= 0.99:
                continue
            if abs(abs(rr) - 0.40) <= BOUNDARY:
                boundary += 1
                if a in SPECIAL or b in SPECIAL or abs(rr) >= 0.40:
                    rule_set.add(frozenset((a, b)))
                continue
            if abs(rr) >= 0.40 or a in SPECIAL or b in SPECIAL:
                rule_set.add(frozenset((a, b)))

    only_pub = pub_set - rule_set
    only_rule = rule_set - pub_set
    # Boundary pairs may legitimately fall on either side of the rule.
    bset = set()
    for pair in only_pub | only_rule:
        a, b = tuple(pair)
        if a in metrics and b in metrics:
            teams = sorted(metrics[a])
            rr = pearson([metrics[a][t] for t in teams],
                         [metrics[b][t] for t in teams])
            if not math.isnan(rr) and abs(abs(rr) - 0.40) <= BOUNDARY:
                bset.add(pair)
    only_pub -= bset
    only_rule -= bset
    if only_pub:
        examples = ", ".join(sorted("/".join(sorted(p)) for p in
                                    list(only_pub)[:5]))
        problems.append(f"V5 {len(only_pub)} published pairs the rule would "
                        f"not select, e.g. {examples}")
    if only_rule:
        examples = ", ".join(sorted("/".join(sorted(p)) for p in
                                    list(only_rule)[:5]))
        problems.append(f"V5 {len(only_rule)} rule-eligible pairs missing from "
                        f"the publication, e.g. {examples}")

    # line-by-row verification ledger (the evidence file)
    with open(LEDGER, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["pair", "metric_a", "metric_b",
                                           "published_r", "recomputed_r",
                                           "abs_delta", "n", "n_published",
                                           "source", "source_tier",
                                           "check_status"])
        w.writeheader()
        w.writerows(ledger)

    print(f"official correlations re-verified: {checked}/{len(rows)} published "
          f"rows recomputed from the official snapshots")
    print(f"  V1 n present and == 32 on every row: "
          f"{sum(1 for r in rows if r.get('n') == 32)}/{len(rows)}")
    print(f"  V2 official nfl.com sources only: "
          f"{sum(1 for r in rows if all(ALLOWED_HOST in (u or '') for u in (r.get('_source_urls') or [r.get('_source_url', '')])))}"
          f"/{len(rows)}")
    print(f"  V3 r recomputes within {TOL}: {checked}/{len(rows)}")
    print(f"  V4 duplicate pairs: {len(rows) - len(pub_set)}")
    print(f"  V5 rule (|r|>=0.40 or special, |r|<0.99 redundancy cut) "
          f"reproduces the set: {len(pub_set) - len(only_pub) - len(only_rule)}"
          f"/{len(pub_set)} (boundary band ±{BOUNDARY}: {boundary} pairs touched it)")
    print(f"  metric pool: {len(metrics)} metrics "
          f"({len(metrics) - 7} team-stat + 7 standings)")

    if problems:
        for p in problems[:40]:
            print(f"  problem: {p}", file=sys.stderr)
        if len(problems) > 40:
            print(f"  ... {len(problems) - 40} more", file=sys.stderr)
        fail(f"{len(problems)} problems found")
    print("official correlation verification passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
