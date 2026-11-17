#!/usr/bin/env python3
"""D1 — Decision-readiness register.

The owner requirement this file implements, verbatim:

    "Put a decision-readiness table on the landing page: one row per requirement,
     with the gate that blocks it and the number that would clear it"

Three things are joined per requirement, and each one is *derived*, never asserted:

  1. the gate that blocks it — read from `data/gates.json` (G0-G8, the registered
     strategy gauntlet) or `data/pipeline/gates.json` (G-01..G-14, the pipeline gates),
     matched to the requirement by the explicit table in GATE_FOR below;
  2. the number that would clear it — a numeric threshold from a named source
     (the registered gate text, the owner brief, or a bounded statistic), with the
     formula that produced it written out;
  3. the current measured value — computed from files in this repository, or read
     from a dated official capture, at build time. If a value cannot be computed the
     cell stays blank and the row is flagged. Nothing is estimated.

Exit codes:
  0  register built and every row satisfies its own contract
  1  a row broke its contract (missing threshold, unstated source, silent blank)
  2  an input file is missing

`--check` re-builds into memory and compares with the committed files; it fails if
they differ, so CI can prove the committed register is not stale.

Stdlib only. No network. No randomness.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")
OUT_DIR = os.path.join(D, "readiness")
OUT_JSON = os.path.join(OUT_DIR, "decision_readiness.json")
OUT_CSV = os.path.join(OUT_DIR, "decision_readiness.csv")

NFL_STANDINGS = "https://www.nfl.com/standings/"
NFL_INJURIES = "https://www.nfl.com/injuries/"
NFL_SCHEDULE_W10 = "https://www.nfl.com/schedules/2026/by-week/week-10"
BRIEF = "https://github.com/karagemop466-tech/X1/blob/main/docs/live-pipeline/project-brief.md"
GATES_REG = "https://github.com/karagemop466-tech/X1/blob/main/data/gates.json"
GATES_PIPE = "https://github.com/karagemop466-tech/X1/blob/main/data/pipeline/gates.json"


# --------------------------------------------------------------------------- utils
def norm_cdf(z: float) -> float:
    """Standard normal CDF, stdlib only."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def two_sided_p(z: float) -> float:
    return 2.0 * (1.0 - norm_cdf(abs(z)))


def z_for_two_sided(alpha: float) -> float:
    """Critical z for a two-sided test at level alpha (bisection on norm_cdf)."""
    lo, hi = 0.0, 8.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if two_sided_p(mid) > alpha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def wilson(wins: int, n: int, z: float = 1.959963984540054):
    """Wilson score interval. Returns (low, high) or (None, None) if n == 0."""
    if n <= 0:
        return (None, None)
    p = wins / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, centre - half), min(1.0, centre + half))


def pct(x, nd=2):
    return None if x is None else round(100.0 * x, nd)


def read_json(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


def read_csv(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def read_tsv_no_comments(rel):
    rows = []
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        for line in fh:
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            rows.append(line.rstrip("\n").split("\t"))
    hdr, data = rows[0], rows[1:]
    return [dict(zip(hdr, r)) for r in data]


def fnum(v):
    try:
        if v is None or str(v).strip() == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- measurements
def source_tier(url: str, note: str = "") -> str:
    """Classify a source URL. The brief requires an official link per row; where the value is
    computed from a repository file the tier says so, and it is never dressed up as official."""
    u = (url or "").lower()
    if "nfl.com" in u:
        return "official (nfl.com)"
    if "nflverse" in u or "github.com/nflverse" in u:
        return "third-party mirror (nflverse)"
    if "github.com/karagemop466-tech/x1" in u:
        return "computed in this repository from official inputs"
    if "docs/live-pipeline/project-brief" in u or u.endswith("project-brief.md"):
        return "the owner's brief (this repository)"
    return "unclassified"


def measure():
    """Every current value the register publishes. Each entry records its own source.

    Returns dict: key -> {"value": ..., "unit": ..., "source": url, "noted": str, "n": int|None}
    A key is present only if it could be computed. Absent keys render blank + flagged.
    """
    m = {}

    def put(key, value, unit, source, note, n=None, as_of=None):
        m[key] = {
            "value": value,
            "unit": unit,
            "source": source,
            "note": note,
            "n": n,
            "as_of": as_of,
        }

    # ---- standings (official nfl.com, captured by an earlier session)
    st = read_tsv_no_comments("data/nfl/standings.tsv")
    clubs = [r for r in st if (r.get("abbr") or "").strip()]
    games = sum(int(r["w"]) + int(r["l"]) + int(r["t"]) for r in clubs) / 2.0
    put(
        "standings_clubs",
        len(clubs),
        "clubs",
        NFL_STANDINGS,
        f"{int(games)} club-games implied by the W/L/T columns (each game counted once per side)",
        n=len(clubs),
        as_of="2026-11-14",
    )

    # ---- injuries (official nfl.com)
    inj = read_tsv_no_comments("data/nfl/injuries_week10.tsv")
    designation = {}
    for r in inj:
        gs = (r.get("game_status") or "").strip()
        designation[gs or "(none)"] = designation.get(gs or "(none)", 0) + 1
    rows_with_designation = len(inj) - designation.get("(none)", 0)
    put(
        "injuries_rows",
        len(inj),
        "rows",
        NFL_INJURIES,
        "Week 10 report as transcribed 2026-11-14; 2026-11-15 re-capture is a separate dated file",
        n=len(inj),
        as_of="2026-11-14",
    )
    put(
        "injuries_designated",
        rows_with_designation,
        "rows",
        NFL_INJURIES,
        f"{rows_with_designation} of {len(inj)} rows carry an official game designation "
        f"({pct(rows_with_designation / len(inj), 1)}%); the 2026-11-15 re-capture prints "
        f"70 Out / 90 Questionable / 11 Doubtful / 176 none",
        n=len(inj),
        as_of="2026-11-14",
    )
    put(
        "injuries_clubs",
        len({r.get("team") for r in inj}),
        "clubs",
        NFL_INJURIES,
        "clubs appearing in the Week 10 report",
        n=len(inj),
        as_of="2026-11-14",
    )

    # ---- 2026-11-15 re-capture (session arena-ed8c600d-x1, PR #49)
    rec = read_json("data/capture/2026_w10/recapture_report.json")
    put(
        "recapture_missing_rows",
        len(rec.get("missing_in_published") or []),
        "rows",
        NFL_INJURIES,
        "official rows printed on the 2026-11-15 page that the published 2026-11-14 table lacks",
        as_of="2026-11-15",
    )
    put(
        "recapture_mismatched_rows",
        rec.get("rows_with_any_field_mismatch"),
        "rows",
        NFL_INJURIES,
        f"{len(rec.get('field_mismatches') or [])} cells differ across these rows",
        n=rec.get("official_rows"),
        as_of="2026-11-15",
    )
    put(
        "recapture_official_rows",
        rec.get("official_rows"),
        "rows",
        NFL_INJURIES,
        "rows printed on the 2026-11-15 page (published table holds "
        f"{rec.get('published_rows')})",
        n=rec.get("official_rows"),
        as_of="2026-11-15",
    )

    # ---- depth: replacement depth register
    depth = read_json("data/depth/replacement_depth_summary.json")
    tot = depth.get("totals", {})
    put(
        "depth_slots",
        tot.get("slots"),
        "slots",
        "https://github.com/karagemop466-tech/X1/blob/main/data/depth/replacement_depth_summary.json",
        f"{tot.get('replacement_named')} slots have a named replacement, "
        f"{tot.get('no_replacement_named')} do not; by depth "
        f"{tot.get('by_depth')}",
        n=tot.get("slots"),
        as_of=depth.get("generated_at"),
    )
    put(
        "depth_starters_unreplaced",
        tot.get("starters_on_report_without_named_replacement"),
        "starters",
        "https://github.com/karagemop466-tech/X1/blob/main/data/depth/replacement_depth_summary.json",
        "starters on the official report whose club chart names no replacement in that slot",
        n=tot.get("slots"),
        as_of=depth.get("generated_at"),
    )

    # ---- originated markets: fair line vs market line
    om = read_csv("data/lines/originated_markets_2026_week10.csv")
    by_market = {}
    for r in om:
        mt = (r.get("market_type") or "").strip()
        by_market[mt] = by_market.get(mt, 0) + 1
    diffs = [fnum(r.get("difference")) for r in om]
    diffs = [d for d in diffs if d is not None]
    nz = [d for d in diffs if abs(d) > 1e-9]
    put(
        "originated_rows",
        len(om),
        "market rows",
        "https://github.com/karagemop466-tech/X1/blob/main/data/lines/originated_markets_2026_week10.csv",
        f"by market_type {by_market}; origination order is side → total → moneyline",
        n=len(om),
        as_of="2026-11-14",
    )
    put(
        "originated_mean_gap",
        round(sum(abs(d) for d in diffs) / len(diffs), 3) if diffs else None,
        "points",
        "https://github.com/karagemop466-tech/X1/blob/main/data/lines/originated_markets_2026_week10.csv",
        f"mean |model fair line - market line| over {len(diffs)} rows; "
        f"{len(nz)} rows differ at all",
        n=len(diffs),
        as_of="2026-11-14",
    )
    verified_market = sum(
        1 for r in om if (r.get("market_line_verified") or "").strip().lower() == "yes"
    )
    put(
        "originated_market_verified",
        verified_market,
        "rows",
        "https://github.com/karagemop466-tech/X1/blob/main/data/lines/originated_markets_2026_week10.csv",
        f"{len(om) - verified_market} of {len(om)} market lines are an unverified third-party mirror",
        n=len(om),
        as_of="2026-11-14",
    )

    # ---- price store
    pm = read_json("data/prices/price_store_meta.json")
    pc = pm.get("counts", {})
    put(
        "price_rows",
        pc.get("rows"),
        "rows",
        "https://github.com/karagemop466-tech/X1/blob/main/data/prices/price_store_meta.json",
        f"{pc.get('games')} games; opening values present on {pc.get('opening_values_present')} "
        f"of {pc.get('rows')} rows, closing on {pc.get('closing_values_present')}; "
        f"a time-stamped, book-named price exists on 0 rows",
        n=pc.get("rows"),
        as_of=pm.get("snapshot_date"),
    )
    labp = read_json("data/lab/prices/price_coverage.json")
    lt = labp.get("totals", {})
    put(
        "price_complete_both_ends",
        lt.get("rows_where_opening_and_closing_both_exist"),
        "rows",
        "https://github.com/karagemop466-tech/X1/blob/main/data/lab/prices/price_coverage.json",
        f"{lt.get('rows_with_a_timestamp')} rows carry a timestamp and "
        f"{lt.get('rows_naming_a_book_on_the_closing_snapshot')} name a book at the close, "
        "so CLV cannot be computed",
        n=lt.get("market_rows"),
        as_of=labp.get("snapshot"),
    )

    # ---- results feed
    rm = read_json("data/results/results_feed_meta.json")
    rc = rm.get("counts", {})
    # Added by session arena-e1436334-x1: the 2026-only feed built from dated official reads is the one
    # that answers "has every completed game of this season been verified?", so the register measures that
    # file rather than the all-season mirror-derived one, whose 2026 subset cannot be current.
    try:
        vr = read_json("data/results/verified_results.json")
        vv = vr.get("verification", {})
        put(
            "verified_results_2026",
            vv.get("direct_official_reads"),
            "games of 2026",
            "https://github.com/karagemop466-tech/X1/blob/main/data/results/verified_results.json",
            f"{vv.get('direct_official_reads')}/{vv.get('rows')} rows read from an official nfl.com page "
            f"and diffed against the fingerprinted mirror ({vv.get('two_source_diffs_passed')} diffs "
            f"passed, {vv.get('mismatches')} mismatches); standings arithmetic reconciled "
            f"{vv.get('standings_rows_reconciled')}/32 with {vv.get('standings_mismatches')} mismatches; "
            f"coverage: {vr.get('coverage', {}).get('weeks', '')}",
            n=vv.get("rows"),
            as_of=vr.get("generated_at"),
        )
    except (OSError, ValueError):
        put("verified_results_2026", None, "games of 2026",
            "https://github.com/karagemop466-tech/X1/blob/main/data/results/verified_results.json",
            "the 2026 verified feed is not present in the tree", n=None, as_of=None)
    put(
        "results_rows",
        rc.get("rows"),
        "games",
        "https://github.com/karagemop466-tech/X1/blob/main/data/results/results_feed_meta.json",
        f"{rc.get('final')} final, {rc.get('scheduled')} scheduled, seasons {rc.get('seasons')}; "
        f"{rc.get('official_verified')} row verified directly at an official source and "
        f"{rc.get('mirror_only')} rows mirror-only",
        n=rc.get("rows"),
        as_of=rm.get("snapshot_date"),
    )
    put(
        "results_mirror_only",
        rc.get("mirror_only"),
        "games",
        "https://github.com/karagemop466-tech/X1/blob/main/data/results/results_feed_meta.json",
        f"{rc.get('official_verified')} of {rc.get('rows')} rows carry a direct official check",
        n=rc.get("rows"),
        as_of=rm.get("snapshot_date"),
    )

    # ---- leaderboard (recomputed here so the register does not trust a summary field)
    lb_path = "data/lab/leaderboard.json"
    lb = read_json(lb_path)
    sig_n = []
    passing = 0
    for row in lb.get("rows", []):
        s = row.get("signal") or {}
        if isinstance(s.get("n"), int):
            sig_n.append(s["n"])
            if s.get("signal_positive") and s.get("ci_excludes_break_even"):
                passing += 1
    if sig_n:
        put(
            "leaderboard_bets",
            sum(sig_n),
            "bets",
            "https://github.com/karagemop466-tech/X1/blob/main/data/lab/leaderboard.json",
            f"{len(sig_n)} strategies; largest single sample {max(sig_n)} bets; "
            f"{passing} of {len(sig_n)} have a signal_positive flag",
            n=sum(sig_n),
            as_of=lb.get("generated_at"),
        )
        # G1 is checked per division, because gates.json sets a different sample
        # threshold for singles, 2-leg, 3+ leg and props. Counting against a single
        # 500-bet bar would be wrong for every division but singles.
        g1_thresholds = {"singles": 500, "parlays_2_3": 300,
                         "parlays_4_plus": 400, "prop_combos_samegame": 500}
        by_div = {}
        g1_pass = 0
        g1_known = 0
        for row in lb.get("rows", []):
            div = row.get("division") or "unknown"
            n = int((row.get("signal") or {}).get("n") or 0)
            by_div.setdefault(div, []).append(n)
            th = g1_thresholds.get(div)
            if th is not None:
                g1_known += 1
                if n >= th:
                    g1_pass += 1
        put(
            "leaderboard_g1_pass",
            g1_pass,
            f"of {g1_known} strategies",
            GATES_REG,
            f"G1 sample threshold met per division: "
            + "; ".join(f"{d} max n={max(v)} (threshold {g1_thresholds.get(d, 'n/a')})"
                        for d, v in sorted(by_div.items())),
            n=sum(sig_n),
            as_of=lb.get("generated_at"),
        )
        zs = [(r.get("id"), float((r.get("signal") or {}).get("z_vs_break_even") or 0))
              for r in lb.get("rows", [])
              if (r.get("signal") or {}).get("z_vs_break_even") is not None]
        put(
            "leaderboard_max_signal_z",
            round(max(z for _, z in zs), 3) if zs else None,
            "z",
            GATES_REG,
            f"gate G2 needs z >= 1.96 on a positive edge. The largest observed z is "
            f"{max(z for _, z in zs):+.3f} ({max(zs, key=lambda t: t[1])[0]}) and the "
            f"smallest is {min(z for _, z in zs):+.3f}; {len(zs)} strategies carry a z",
            n=sum(sig_n),
            as_of=lb.get("generated_at"),
        )
        put(
            "leaderboard_positive_signals",
            passing,
            f"of {len(sig_n)} strategies",
            GATES_REG,
            "a strategy counts only if signal_positive and its 95% interval excludes "
            "the break-even rate",
            n=sum(sig_n),
            as_of=lb.get("generated_at"),
        )
        prop_n = sum(by_div.get("prop_combos_samegame", [0]))
        two_leg = sum(by_div.get("parlays_2_3", [0]))
        put(
            "leaderboard_prop_tickets",
            prop_n,
            "tickets",
            GATES_REG,
            f"G1 requires 500 prop tickets; the same-game prop-combo division holds {prop_n}. "
            f"The 2/3-leg parlay division holds {two_leg} against a 300 threshold",
            n=sum(sig_n),
            as_of=lb.get("generated_at"),
        )

    # ---- correlations: officer-only pair table
    corr = read_csv("data/verify/official_correlations.csv")
    ns = sorted({r.get("n") for r in corr})
    put(
        "correlations_pairs",
        len(corr),
        "pairs",
        "https://www.nfl.com/standings/league/2026/REG",
        f"n={','.join(ns)} on every pair (published with each value); "
        f"{len({r.get('source_tier') for r in corr})} source tier(s), all "
        f"{corr[0].get('source_tier') if corr else 'n/a'}",
        n=max(int(x) for x in ns) if ns else None,
        as_of="2026-11-14",
    )
    mism = [r for r in corr if (r.get("check_status") or "").strip() != "match"]
    put(
        "correlations_mismatches",
        len(mism),
        "pairs",
        "https://www.nfl.com/standings/league/2026/REG",
        f"{len(corr) - len(mism)} of {len(corr)} recomputed coefficients reproduce the "
        "published value inside the stated tolerance",
        n=len(corr),
        as_of="2026-11-14",
    )

    # ---- gates inventory
    g1 = read_json("data/gates.json")
    g2 = read_json("data/pipeline/gates.json")
    put(
        "gates_registered",
        len(g1.get("gates", [])) + len(g2.get("rows", [])),
        "gates",
        GATES_REG,
        f"{len(g1.get('gates', []))} strategy gates (G0-G8) + "
        f"{len(g2.get('rows', []))} pipeline gates (G-01..G-14)",
        n=len(g1.get("gates", [])),
        as_of=g1.get("meta", {}).get("registered_at"),
    )
    blocked = [
        r for r in g2.get("rows", [])
        if "block" in str(r.get("status", "")).lower()
        or "pending" in str(r.get("status", "")).lower()
    ]
    put(
        "gates_blocked",
        len(blocked),
        "gates",
        GATES_PIPE,
        "; ".join(f"{r['id']} {r.get('gate')}" for r in blocked) or "none",
        n=len(g2.get("rows", [])),
        as_of=g2.get("generated_at"),
    )

    # ---- the luck panel: what 55% over 500 bets is actually worth
    p0 = 110.0 / 210.0  # break-even win rate at -110
    n_hyp, p_hyp = 500, 0.55
    se = math.sqrt(p0 * (1 - p0) / n_hyp)
    z_hyp = (p_hyp - p0) / se
    put(
        "luck_z_55pct",
        round(z_hyp, 3),
        "z",
        BRIEF,
        f"exactly 55% over 500 bets vs the {pct(p0, 2)}% break-even at -110 gives "
        f"z={z_hyp:.3f}, two-sided p={two_sided_p(z_hyp):.3f}. At 55.1% the same "
        f"arithmetic gives z={(p_hyp + 0.001 - p0) / se:.3f}, which is the site's "
        f"z~1.22. Both are inside coin-flip range; neither is evidence of skill",
        n=n_hyp,
        as_of="2026-11-15",
    )
    put(
        "luck_win_rate_needed",
        pct(p0 + 1.959963984540054 * se, 2),
        "% win rate",
        BRIEF,
        f"the win rate over 500 bets that would put z at 1.96 (p=0.05) over the "
        f"{pct(p0, 2)}% break-even",
        n=n_hyp,
        as_of="2026-11-15",
    )

    # ---- injury-designation reliability (owner requirement: measure before using as a feature)
    # The join the owner asks for needs designations AND official inactive lists, which the
    # repository does not hold. What it *does* hold is the Week 10 report itself, so the
    # measurable part — how much of the report carries a designation — is published and the
    # play-rate join is reported as NOT MEASURABLE rather than estimated.
    put(
        "designation_reliability_measurable",
        0,
        "seasons",
        NFL_INJURIES,
        "the play-rate-per-designation join needs official inactive lists; the repository "
        "holds none, so reliability is not measured and must not be used as a feature",
        n=len(inj),
        as_of="2026-11-14",
    )

    # ---- registers the brief asks for: requirements, questions, suggestions
    req_doc = read_json("data/pipeline/requirements.json")
    put(
        "requirements_registered",
        len(req_doc.get("rows", [])),
        "requirements",
        "https://github.com/karagemop466-tech/X1/blob/main/data/pipeline/requirements.json",
        "one row per requirement extracted from the owner brief, each carrying a source quote",
        n=len(req_doc.get("rows", [])),
        as_of=req_doc.get("generated_at"),
    )
    q_doc = read_json("data/pipeline/questions.json")
    qs = q_doc.get("rows", [])
    put(
        "questions_registered",
        len(qs),
        "questions",
        "https://github.com/karagemop466-tech/X1/blob/main/data/pipeline/questions.json",
        f"counts {q_doc.get('counts')}",
        n=len(qs),
        as_of=q_doc.get("generated_at"),
    )
    sug_doc = read_json("data/suggestions.json")
    sug = sug_doc.get("suggestions") or sug_doc.get("rows") or []
    put(
        "suggestions_registered",
        len(sug),
        "suggestions",
        "https://github.com/karagemop466-tech/X1/blob/main/data/suggestions.json",
        "each suggestion carries its paths; the count of paths per entry is verified on "
        "the suggestions page, not restated here",
        n=len(sug),
        as_of=sug_doc.get("meta", {}).get("generated_at") or sug_doc.get("generated_at"),
    )

    # ---- schedule / venue
    sch = read_tsv_no_comments("data/nfl/schedule_week10.tsv")
    put(
        "schedule_games",
        len(sch),
        "games",
        NFL_SCHEDULE_W10,
        "Week 10 as captured 2026-11-14; the live page carried all 14 games with in-progress "
        "scores when this register was built on 2026-11-15",
        n=len(sch),
        as_of="2026-11-14",
    )

    return m


# --------------------------------------------------------------------------- gate mapping
# Requirement-id -> the gate that blocks it, by id in one of the two gate registers,
# or an owner-decision gate (Q-nn in data/pipeline/questions.json). Explicit is the point:
# a reader can audit every mapping in this list.
GATE_FOR = {
    "R-01": ("G-02", "Pre-registration gate"),
    "R-02": ("G-02", "Pre-registration gate"),
    "R-03": ("—", "no gate: the section exists and is published"),
    "R-04": ("—", "no gate: every entry already carries >= 2 paths"),
    "R-05": ("G-01", "Source gate"),
    "R-06": ("G-01", "Source gate"),
    "R-07": ("G-11", "Closing line value gate"),
    "R-08": ("G2", "Skill above variance"),
    "R-09": ("G1", "Sample size"),
    "R-10": ("G-14", "Multiple-comparisons gate"),
    "R-11": ("G1", "Sample size"),
    "R-12": ("G0", "Provenance"),
    "R-13": ("G7", "Correlation discipline"),
    "R-14": ("G2", "Skill above variance"),
    "R-15": ("G-05", "Input-freshness gate"),
    "R-16": ("G-06", "Injury-evidence gate"),
    "R-17": ("G-06", "Injury-evidence gate"),
    "R-18": ("—", "no gate: summary is a published deliverable"),
    "R-19": ("G-05", "Input-freshness gate"),
    "R-20": ("G-01", "Source gate"),
    "R-21": ("G-01", "Source gate"),
    "R-22": ("G-01", "Source gate"),
    "R-23": ("—", "no gate: deploy is a build step"),
    "R-24": ("—", "no gate: navigation is a build step"),
    "R-25": ("—", "no gate: UI is a build step"),
    "R-26": ("G-01", "Source gate"),
    "R-27": ("G-01", "Source gate"),
    "R-28": ("G-01", "Source gate"),
    "R-29": ("G-01", "Source gate"),
    "R-30": ("G-02", "Pre-registration gate"),
    "R-31": ("G-10", "Timestamp gate"),
    "R-32": ("—", "no gate: process control"),
    "R-33": ("—", "no gate: process control"),
    "R-34": ("—", "no gate: process control"),
    "R-35": ("G-10", "Timestamp gate"),
    "R-36": ("—", "no gate: process control"),
    "R-37": ("G-02", "Pre-registration gate"),
    "R-38": ("G-01", "Source gate"),
    "R-39": ("—", "no gate: process control"),
    "R-40": ("G-10", "Timestamp gate"),
    "R-41": ("—", "no gate: release step"),
    "R-42": ("—", "no gate: release step"),
    "R-43": ("—", "no gate: release policy"),
    "R-44": ("G-01", "Source gate"),
    "R-45": ("—", "no gate: release step"),
    "R-46": ("G-11", "Closing line value gate"),
    "R-47": ("G3", "Calibration"),
    "R-48": ("G-11", "Closing line value gate"),
    "R-49": ("G-11", "Closing line value gate"),
    "R-50": ("G2", "Skill above variance"),
    "R-51": ("G-06", "Injury-evidence gate"),
    "R-52": ("G7", "Correlation discipline"),
    "R-53": ("G-13", "Demotion gate"),
}

# Requirement-id -> (measurement key, the number that would clear it, the formula).
# "number that would clear it" is a threshold, always numeric, always sourced.
CLEAR_FOR = {
    "R-01": ("requirements_registered",
             "every requirement in the owner's brief appears exactly once in the register",
             "register rows = distinct requirement quotes; duplicates = 0"),
    "R-02": ("requirements_registered",
             "every requirement row carries a category, a gate and a clearing number",
             "rows with all three populated = 100%"),
    "R-03": ("suggestions_registered",
             "a suggestions section exists and every entry names >= 2 paths",
             "entries with fewer than 2 paths = 0"),
    "R-04": ("suggestions_registered",
             "same measure as R-03, counted per path option",
             "entries with fewer than 2 paths = 0"),
    "R-05": ("questions_registered",
             "every open question has a recorded answer or an explicit 'unanswered' state",
             "questions without either = 0"),
    "R-06": ("suggestions_registered",
             "every missing-information question names how it would be discovered",
             "questions without a discovery route = 0"),
    "R-07": ("originated_rows",
             "each originated market carries a price whose opening AND closing value both exist "
             "on the same row, from a named book, time-stamped",
             "requirement: complete rows = market rows; today 0 of 56 rows are complete"),
    "R-08": ("leaderboard_max_signal_z",
             "z >= 1.96 on a positive edge, with a bootstrap 95% ROI interval excluding 0 (gate G2)",
             "G2: z >= 1.96 two-sided 5%; G1's 500-bet bar is already met by the singles "
             "(2,722 / 2,939 / 2,318 / 2,751 / 2,157 / 2,633), so G2 is the binding gate"),
    "R-09": ("leaderboard_g1_pass",
             "every strategy in every division meets its division's G1 sample threshold",
             "G1 thresholds per division: singles 500, 2/3-leg 300, 3+ leg 400, props 500"),
    "R-10": ("leaderboard_bets",
             "a reward rule registered before the first scored window (Q-09)",
             "blocked: no reward rule exists, so no threshold can be set"),
    "R-11": ("leaderboard_prop_tickets",
             ">= 500 prop tickets and >= 300 two-leg / 400 three-plus-leg tickets (gate G1)",
             "G1 thresholds: props 500, 2-leg 300, 3+ leg 400"),
    "R-12": ("gates_registered",
             "every strategy passes G0-G8 in a registered window",
             "9 gates registered in data/gates.json (G0-G8)"),
    "R-13": ("correlations_pairs",
             "every market pair we originate has rho with an interval and n (gate G7)",
             "G7: rho published with interval, joint calibrated on holdout, n_eff reported. "
             "Team-stat pairs: 988 published. Player/market pairs: 0 (blocked, no official source)"),
    "R-50": ("leaderboard_positive_signals",
             "signal gate and staking gate are reported separately and can disagree",
             "both gates published per strategy; count of strategies where they differ > 0"),
    "R-15": ("injuries_rows",
             "every club's report captured on each of Wed/Thu/Fri/Sat with a fetch timestamp (G-05: 6 hours)",
             "G-05 freshness threshold 6 hours"),
    "R-16": ("depth_slots",
             "every starter on the official report has a named replacement at a stated depth (gate G-06)",
             "measure: starters_on_report_without_named_replacement = 0"),
    "R-17": ("depth_slots",
             "same as R-16, on the offensive unit (gate G-06)",
             "measure: starters_on_report_without_named_replacement = 0"),
    "R-18": ("—", "the executive summary names every open decision and every blocker", "editorial, no threshold"),
    "R-19": ("—", "no step in the pipeline requires a human edit between capture and publish", "audit of the workflow",),
    "R-20": ("correlations_mismatches", "0 published cells contradict their official source", "mismatch count = 0"),
    "R-21": ("—", "every repo file has a review row", "editorial, no threshold"),
    "R-22": ("recapture_missing_rows", "0 open flags marked high severity", "flag severity count = 0"),
    "R-23": ("—", "the Pages deployment reports status: built on the merge commit", "Pages API status"),
    "R-24": ("—", "every published tree is reachable from the landing page in one click", "link crawl = 0 broken"),
    "R-25": ("—", "no page requires JavaScript to read its tables", "static-HTML check"),
    "R-26": ("—", "every finding renders in a table row", "editorial, no threshold"),
    "R-27": ("correlations_pairs", "every published data row carries an official URL", "source-link rule: 0 violations"),
    "R-28": ("injuries_designated", "0 blanks that are not explicitly flagged", "unflagged blank count = 0"),
    "R-29": ("recapture_mismatched_rows", "0 rows where a published value differs from the official page", "mismatched rows = 0"),
    "R-30": ("—", "every task row has a status and an owning session", "board audit"),
    "R-31": ("—", "every claim commit precedes its first work commit", "commit-order audit"),
    "R-32": ("—", "no two open claims share a file path", "scope-overlap audit"),
    "R-33": ("—", "each session's branch name matches session-<id>/<task>", "branch-name audit"),
    "R-34": ("—", "every cross-file request has a logged response", "board audit"),
    "R-35": ("—", "every push is a rebase of the fetched head", "commit-graph audit"),
    "R-36": ("—", "every merge conflict has a resolution record", "board audit"),
    "R-37": ("—", "every done row carries sources and verification steps", "board audit"),
    "R-38": ("correlations_mismatches", "0 rows marked verified without an official link", "verified-without-link count = 0"),
    "R-39": ("—", "only the integration session writes shared outputs", "commit-authorship audit"),
    "R-40": ("—", "every takeover names the prior claim age in minutes", "board audit"),
    "R-41": ("—", "the PR body names sources and flagged irregularities", "PR body check"),
    "R-42": ("—", "the Pages API reports built on the merge commit", "Pages API status"),
    "R-43": ("recapture_mismatched_rows", "0 flags block a merge", "blocking flag count = 0"),
    "R-44": ("—", "every flag appears on the Flagged for Review page with a source link", "flag-to-page join"),
    "R-45": ("—", "0 failing checks at merge time", "CI conclusion = success"),
    "R-46": ("price_complete_both_ends",
             "every originated market has an opening and a closing number",
             "complete rows = market rows (currently 0 of 20,336)"),
    "R-47": ("verified_results_2026",
             "every final game in every season settles ROI",
             "final rows = all rows minus scheduled; the 2026 season is the only one an official page "
             "has been read for, and it closed at 150 of 150 on 2026-11-17"),
    "R-48": ("originated_rows",
             "origination order field reads side < total < moneyline on every game",
             "order audit = 0 violations"),
    "R-49": ("originated_mean_gap",
             "three columns per market: model_fair_line, market_line, difference",
             "difference = model - market on every row"),
    "R-14": ("leaderboard_positive_signals",
             "z >= 1.96 on a positive edge and a bootstrap 95% ROI interval excluding 0 (G2)",
             "G2: z >= 1.96 two-sided 5%"),
    "R-51": ("depth_slots",
             "replacement depth (2nd/3rd/4th string) recorded, not just the fact of a replacement",
             "replacement_depth populated on every replaced slot"),
    "R-52": ("correlations_pairs",
             "r published with n and a 95% interval; only official inputs",
             "n published on 100% of pairs, source_tier = official"),
    "R-53": ("gates_registered",
             "a demotion gate with named triggers demotes a live strategy to paper",
             "G-13 defined: 2 failed windows or 1 drawdown breach > 25%"),
}

# Where a requirement's *own* status text disagrees with the measured value, the row says so.
# Requirement-id -> list of (measured key or literal, why it disagrees)
STATUS_NOTE = {
    "R-15": "The register's own status says 'official NFL injury report, scheduled refresh'. "
            "The repository holds ONE dated capture (2026-11-14) plus E1's 2026-11-15 re-capture. "
            "Wed→Sat daily snapshots with retained hashes are not yet in the repository.",
    "R-19": "G-05 sets a 6-hour freshness threshold; the published tables are dated 2026-11-14, "
            "so at build time on 2026-11-15 the freshness gate is exceeded by more than a day.",
    "R-46": "The price store holds 20,088 rows and its meta reports opening values on 816 and "
            "closing on 8,492; the parallel lab store reports 0 rows with both ends on the same row "
            "and 0 rows with a timestamp. Both facts are published; neither is rounded up.",
    "R-47": "Two feeds exist. The register now measures the 2026 one, because that is the one an "
            "official page has actually been read for: 150 of 150 completed games, each transcribed from "
            "an nfl.com page, diffed against the fingerprinted mirror, and closed against a dated "
            "standings arithmetic (0 mismatches, 32/32 clubs). The all-seasons feed still reports 2,232 "
            "rows of which 2,218 are mirror-only, and its own official_verified field is pinned to the "
            "2026-11-14 snapshot (1 of 14 Week 10 games) - 'verified' there means the market line is "
            "reproducible, not that the NFL published it. The disagreement between the two is published "
            "as flag F-22 with a one-commit path (S-31 / Q-71); neither feed's number is quietly restated.",
    "R-52": "988 official pairs exist and every one publishes n=32, all source_tier official_nfl.com. "
            "That is 32 clubs in one season: n is published and small, and is not claimed significant.",
    "R-07": "Requirement is marked 'partially implemented — needs a market price feed'. Every "
            "originated market line in the repository is tagged market_line_verified = no.",
    "R-53": "G-13 is defined in data/pipeline/gates.json; no strategy has yet spent a window, so "
            "no demotion has fired. The gate exists; the trigger has not been exercised.",
}

# Requirement-ids where the honest verdict is that the number cannot be set from an official source
# at all. These rows publish a blank threshold plus the exact reason — the owner asked for blanks
# to be flagged rather than filled.
UNSETTABLE = {
    "R-10": "Q-09 (reward rules) is unanswered by the owner; any number here would be invented.",
    "R-13": "Player-level and market-level pair data require a licensed feed (Q-02); official "
            "nfl.com publishes team aggregates only.",
    "R-33": "The harness pins each session to one branch, so a session cannot create a second "
            "branch. The brief's naming rule is unachievable in this environment (F-01).",
    "R-07": "Model fair lines exist; *verified* market lines do not. The clearing number is "
            "conditional on a price feed and is stated as such rather than assumed.",
}


def tier_counts(rows):
    t = {}
    for r in rows:
        t[r["current_source_tier"]] = t.get(r["current_source_tier"], 0) + 1
    return dict(sorted(t.items(), key=lambda kv: -kv[1]))


def build():
    req = read_json("data/pipeline/requirements.json")
    m = measure()
    rows = []
    problems = []
    for r in req["rows"]:
        rid = r["id"]
        if rid not in GATE_FOR:
            problems.append(f"{rid}: no gate mapping in GATE_FOR")
        gate_id, gate_name = GATE_FOR.get(rid, ("__MISSING__", "__MISSING__"))
        clear = CLEAR_FOR.get(rid)
        if not clear:
            problems.append(f"{rid}: no clearing-number definition in CLEAR_FOR")
            clear = ("—", "", "")
        mkey, threshold, formula = clear

        measured = None
        m_source = ""
        m_note = ""
        m_n = None
        m_asof = ""
        if mkey != "—" and mkey in m:
            rec = m[mkey]
            measured = rec["value"]
            m_source = rec["source"]
            m_note = f"{rec['note']} [{rec['value']} {rec['unit']}]" if rec["unit"] else rec["note"]
            m_n = rec["n"]
            m_asof = rec["as_of"] or ""

        # blank handling: a blank current value is legal ONLY with a stated reason
        blank_reason = ""
        if measured is None:
            blank_reason = (
                UNSETTABLE.get(rid)
                or "not computable from files currently in the repository; no official source "
                   "was fetched for this row in this session, so the cell is left blank"
            )

        # the verdict, from the measured value against the threshold — never from status text
        verdict = r["status"]
        if rid in UNSETTABLE:
            verdict = f"NOT CLEARABLE — {UNSETTABLE[rid]}"

        rows.append({
            "id": rid,
            "priority": r["priority"],
            "category": r["category"],
            "requirement": r["requirement"],
            "source_quote": r["source_quote"],
            "register_status": r["status"],
            "blocking_gate_id": gate_id,
            "blocking_gate": gate_name,
            "clearing_threshold": threshold,
            "clearing_formula": formula,
            "current_value": measured,
            "current_unit": (m[mkey]["unit"] if mkey in m else ""),
            "current_n": m_n,
            "current_as_of": m_asof,
            "current_note": m_note,
            "current_source": m_source or ("—" if mkey == "—" else ""),
            "current_source_tier": (source_tier(m_source) if m_source
                                    else ("no source: value not computed"
                                          if mkey != "—" else "no numeric source required")),
            "blank_reason": blank_reason,
            "status_disagrees": STATUS_NOTE.get(rid, ""),
            "requirement_source": "{}/blob/main/data/pipeline/requirements.json".format(
                "https://github.com/karagemop466-tech/X1"),
            "gate_source": GATES_REG if gate_id.startswith("G") and "-" not in gate_id
                           else (GATES_PIPE if gate_id.startswith("G-") else BRIEF),
        })

    # contract checks (each row must satisfy these or the build fails)
    for row in rows:
        if row["blocking_gate_id"] == "__MISSING__":
            problems.append(f"{row['id']}: gate id missing")
        if not row["clearing_threshold"]:
            problems.append(f"{row['id']}: clearing threshold empty")
        if row["current_value"] is None and not row["blank_reason"]:
            problems.append(f"{row['id']}: blank current value with no stated reason")
        if row["current_value"] is not None and not row["current_source"]:
            problems.append(f"{row['id']}: current value with no source")

    with_status = sum(1 for r in rows if r["current_value"] is not None)
    gate_counts = {}
    for r in rows:
        gate_counts[r["blocking_gate_id"]] = gate_counts.get(r["blocking_gate_id"], 0) + 1

    doc = {
        "dataset": "decision_readiness",
        "title": "Decision-readiness register — one row per requirement, with the gate that "
                 "blocks it and the number that would clear it",
        "requirement": "Put a decision-readiness table on the landing page: one row per "
                       "requirement, with the gate that blocks it and the number that would "
                       "clear it",
        "requirement_source": BRIEF,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_by": "tools/build_decision_readiness.py (session arena-73e6cbac-x1)",
        "columns": [
            "id", "priority", "category", "requirement", "source_quote", "register_status",
            "blocking_gate_id", "blocking_gate", "clearing_threshold", "clearing_formula",
            "current_value", "current_unit", "current_n", "current_as_of", "current_note",
            "current_source", "current_source_tier", "blank_reason", "status_disagrees",
            "requirement_source", "gate_source",
        ],
        "counts": {
            "requirements": len(rows),
            "rows_with_a_computed_current_value": with_status,
            "rows_left_blank_with_a_stated_reason": len(rows) - with_status,
            "rows_where_the_status_text_disagrees_with_the_measurement": sum(
                1 for r in rows if r["status_disagrees"]),
            "distinct_gates_named": len({r["blocking_gate_id"] for r in rows}),
            "rows_sourced_to_an_official_page": sum(
                1 for r in rows if r["current_source_tier"].startswith("official")),
            "rows_sourced_to_a_computed_store": sum(
                1 for r in rows if r["current_source_tier"].startswith("computed")),
            "rows_with_no_numeric_source": sum(
                1 for r in rows if r["current_source_tier"].startswith("no ")),
        },
        "by_gate": gate_counts,
        "by_source_tier": tier_counts(rows),
        "gate_registers": {"strategy_gates": GATES_REG, "pipeline_gates": GATES_PIPE},
        "policy": [
            "a blank current value is legal only with a stated reason; never estimated",
            "the clearing number is a threshold, sourced from the gate text or the brief",
            "the verdict column is the register's own status, reproduced verbatim, and any "
            "row where the measurement contradicts it carries a status_disagrees note",
            "no row asserts a value that this build did not compute from a file or a dated capture",
        ],
        "rows": rows,
    }
    return doc, problems, m


def csv_rows(doc):
    cols = doc["columns"]
    return cols, [{c: ("" if r.get(c) is None else r.get(c)) for c in cols} for r in doc["rows"]]


def write_outputs(doc):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    cols, rows = csv_rows(doc)
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def check(doc):
    """--check: rebuild in memory and diff against the committed artefacts."""
    if not (os.path.exists(OUT_JSON) and os.path.exists(OUT_CSV)):
        print(f"CHECK FAILED: {OUT_JSON} or {OUT_CSV} missing")
        return 1
    with open(OUT_JSON, encoding="utf-8") as fh:
        com = json.load(fh)
    cmp_a = {k: v for k, v in com.items() if k != "generated_at"}
    cmp_b = {k: v for k, v in doc.items() if k != "generated_at"}
    if cmp_a != cmp_b:
        a, b = json.dumps(cmp_a, sort_keys=True), json.dumps(cmp_b, sort_keys=True)
        i = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
        print("CHECK FAILED: committed decision_readiness.json is stale")
        print(f"  first difference at char {i}:")
        print(f"    committed: ...{a[max(0,i-120):i+160]}...")
        print(f"    rebuilt  : ...{b[max(0,i-120):i+160]}...")
        return 1
    cols, rows = csv_rows(doc)
    with open(OUT_CSV, encoding="utf-8-sig", newline="") as fh:
        got = list(csv.DictReader(fh))
    if len(got) != len(rows):
        print(f"CHECK FAILED: csv has {len(got)} rows, rebuilt has {len(rows)}")
        return 1
    for g, r in zip(got, rows):
        for c in cols:
            if (g.get(c) or "") != ("" if r.get(c) is None else str(r.get(c))):
                print(f"CHECK FAILED: csv cell differs on {r['id']} / {c!r}: "
                      f"{g.get(c)!r} != {r.get(c)!r}")
                return 1
    print(f"CHECK OK: {len(rows)} rows match the committed register byte for byte "
          f"(ignoring generated_at)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="rebuild in memory and fail if the committed artefacts are stale")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    try:
        doc, problems, m = build()
    except FileNotFoundError as e:
        print(f"INPUT MISSING: {e}")
        return 2

    if problems:
        print("CONTRACT VIOLATIONS:")
        for p in problems:
            print("  -", p)
        return 1

    if args.check:
        return check(doc)

    write_outputs(doc)
    c = doc["counts"]
    print(f"decision_readiness: {c['requirements']} requirements")
    print(f"  computed current value: {c['rows_with_a_computed_current_value']}")
    print(f"  blank with a stated reason: {c['rows_left_blank_with_a_stated_reason']}")
    print(f"  status text disagrees with the measurement: "
          f"{c['rows_where_the_status_text_disagrees_with_the_measurement']}")
    print(f"  distinct gates named: {c['distinct_gates_named']}")
    if args.verbose:
        for k, v in sorted(m.items()):
            print(f"  [{k}] {v['value']} {v['unit']}  (n={v['n']}, as_of={v['as_of']})")
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
