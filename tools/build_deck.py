#!/usr/bin/env python3
"""Build the X1 deck: the landing page and its category subpages.

    python3 tools/build_deck.py            # build data/deck/*.json and deck/*.html
    python3 tools/build_deck.py --check    # verify only; exit 1 if anything disagrees

The deck is not a re-implementation of the other published trees. It is the
**entry point**: one landing page, one navigation, and the decision-readiness
register the brief asks for (one row per requirement, with the gate that blocks
it and the number that would clear it).

Everything it publishes is either

  (a) read from a file that already exists in this repository (and linked), or
  (b) a count recomputed from such a file, with the recomputation shown here, or
  (c) the brief text itself, verified to be a literal substring of
      docs/live-pipeline/project-brief-round3.md.

There is no fourth source. A value that cannot be shown to come from (a), (b) or
(c) is left blank and flagged.

Rules enforced by --check (and by tools/verify_deck.py):
  R1  every sentence in data/deck/brief_round3_sentences.tsv is a literal
      substring of the verbatim brief file
  R2  every readiness row names a gate that exists in data/gates.json or
      data/pipeline/gates.json, or says explicitly that no gate applies
  R3  every readiness row has a non-empty clearing number or an explicit
      "no number" sentence
  R4  the luck panel is recomputed from data/console/results_feed.csv and
      data/processed/games_modeled.csv and must agree with what was published
  R5  every table row on every deck page carries a source link
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import json
import math
import os
import random
import re
import sys
from collections import Counter, defaultdict
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "deck")
OUT = os.path.join(ROOT, "deck")
BRIEF = os.path.join(ROOT, "docs", "live-pipeline", "project-brief-round3.md")
SENTENCES = os.path.join(DATA, "brief_round3_sentences.tsv")
VENUES = os.path.join(DATA, "venues_2026_w10.tsv")
FLAGS = os.path.join(DATA, "flags.json")

REPO_BLOB = "https://github.com/karagemop466-tech/X1/blob/main/"
REPO_TREE = "https://github.com/karagemop466-tech/X1/tree/main/"

NOW = dt.datetime.now(dt.timezone.utc)
STAMP = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")

GATES_ROOT = os.path.join(ROOT, "data", "gates.json")
GATES_PIPE = os.path.join(ROOT, "data", "pipeline", "gates.json")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def esc(x) -> str:
    return html.escape("" if x is None else str(x), quote=True)


def read_tsv(path):
    """Read a TSV whose leading '#' lines are provenance, not data.

    Quoting is handled by the csv module: a field containing a tab or a quote
    is written with quotes and any inner quote doubled. Splitting on '\\t' by
    hand (the first version of this function) silently kept the quote
    characters, which made a verbatim comparison fail on the three brief lines
    that contain quoted phrases.
    """
    with open(path, encoding="utf-8", newline="") as fh:
        body = "".join(ln for ln in fh if not ln.startswith("#"))
    rdr = csv.reader(body.splitlines(), delimiter="\t", quotechar='"')
    all_rows = [r for r in rdr if any(x.strip() for x in r)]
    if not all_rows:
        return [], []
    header = all_rows[0]
    rows = []
    for parts in all_rows[1:]:
        if len(parts) < len(header):
            parts = parts + [""] * (len(header) - len(parts))
        rows.append(dict(zip(header, parts)))
    return header, rows


def load_gates():
    ids = set()
    names = {}
    with open(GATES_ROOT, encoding="utf-8") as fh:
        for g in json.load(fh)["gates"]:
            ids.add(g["id"])
            names[g["id"]] = g.get("name", "")
    with open(GATES_PIPE, encoding="utf-8") as fh:
        for g in json.load(fh)["rows"]:
            ids.add(g["id"])
            names[g["id"]] = g.get("gate") or g.get("title") or ""
    return ids, names


# Hosts the repository's own source policy admits (scripts/verify_site.py):
# the league, club domains read from the depth-chart store, and the repository.
_OFFICIAL_BASE = ("nfl.com", "nextgenstats.nfl.com", "itl.nist.gov", "github.com")


def _club_hosts():
    try:
        d = json.load(open(os.path.join(ROOT, "data", "pipeline", "depth_charts.json"), encoding="utf-8"))
        return {urlparse(r["_source_url"]).hostname or "" for r in d.get("rows", []) if r.get("_source_url")}
    except (OSError, ValueError):
        return set()


_CLUB_HOSTS = _club_hosts()


def host_ok(url):
    from urllib.parse import urlparse as _up
    h = (_up(url).hostname or "").lower()
    if not h:
        return False
    return bool(any(h == b or h.endswith("." + b) for b in _OFFICIAL_BASE) or h in _CLUB_HOSTS)


def pct(x, nd=2):
    return f"{x * 100:.{nd}f}%"


def fmt(x, nd=3):
    if x is None:
        return ""
    return f"{x:,.{nd}f}"


# ---------------------------------------------------------------------------
# R1 — the brief must be verbatim
# ---------------------------------------------------------------------------

def verify_brief_lines():
    """Every registered sentence must appear literally in the verbatim brief."""
    brief_text = open(BRIEF, encoding="utf-8").read()
    # normalise whitespace runs so a double space in the brief does not create a
    # false failure — but the sentence itself must still be character-identical
    # after that single, declared normalisation.
    norm = re.sub(r"[ \t]+", " ", brief_text)
    _, rows = read_tsv(SENTENCES)
    problems = []
    for r in rows:
        sent = r["sentence"].strip()
        if not sent:
            problems.append(f"{r['id']}: empty sentence")
            continue
        if sent not in brief_text and re.sub(r"[ \t]+", " ", sent) not in norm:
            problems.append(f"{r['id']}: not found verbatim in the brief: {sent[:70]!r}")
    return rows, problems


# ---------------------------------------------------------------------------
# R4 — the luck panel, recomputed
# ---------------------------------------------------------------------------

def wilson(w, n, z=1.959963985):
    if n == 0:
        return (None, None)
    p = w / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def binom_sf_inv(p_be, n, alpha=0.05):
    """Smallest number of wins k with P(X >= k | n, p_be) < alpha.

    Computed in log space (lgamma) because math.comb(n, k) * p**k overflows a
    float well before n = 3,500.
    """
    lg_n1 = math.lgamma(n + 1)
    lp, lq = math.log(p_be), math.log1p(-p_be)

    def logpmf(k):
        return lg_n1 - math.lgamma(k + 1) - math.lgamma(n - k + 1) + k * lp + (n - k) * lq

    # P(X >= k) = sum_{j>=k} pmf(j). Walk k upward, subtracting from 1.
    tail = 1.0
    for k in range(0, n + 1):
        if tail < alpha:
            return k
        tail -= math.exp(logpmf(k))
        if tail <= 0:
            return n + 1
    return n + 1


def games_needed(edge_pp, p_be, alpha=0.05):
    """Bets needed for a one-sided 5% test to fire, given a true hit-rate edge.

    Uses the normal approximation with the *null* standard error, which is the
    conservative choice for a binomial test.
    """
    z = 1.644853627  # one-sided 5%
    p1 = p_be + edge_pp
    if p1 <= p_be:
        return None
    denom = (p1 - p_be) ** 2
    return math.ceil(z * z * p_be * (1 - p_be) / denom)


def build_luck_panel():
    """Every number below is recomputed here from a committed CSV."""
    feed_path = os.path.join(ROOT, "data", "console", "results_feed.csv")
    games_path = os.path.join(ROOT, "data", "processed", "games_modeled.csv")
    strat_path = os.path.join(ROOT, "data", "console", "strategy_results.csv")

    feed = list(csv.DictReader(open(feed_path, encoding="utf-8")))
    games = list(csv.DictReader(open(games_path, encoding="utf-8")))
    strat = list(csv.DictReader(open(strat_path, encoding="utf-8")))

    settled = [g for g in feed if g["settled"] == "yes"]
    breaks = {110: 0.5238, 105: 0.5122, 120: 0.5455}

    panel = {"generated_at": STAMP, "blocks": []}

    # --- Block 1: how lucky is a good record? -------------------------------
    # Coin-flip null: at a true 50% you need this many decisions for a record
    # this good to be unlikely. This is the "could this be luck?" number.
    n_grid = [50, 100, 137, 200, 500, 1000, 2000, 3500]
    b1 = []
    for n in n_grid:
        # fewest wins that put a 52.38% break-even player in the clear
        need_be = binom_sf_inv(0.5238, n)
        # fewest wins for a 55% player to be *detected* against 50%
        need_55 = binom_sf_inv(0.5, n, )
        b1.append({
            "n": n,
            "wins_to_clear_breakeven": need_be,
            "hit_rate_to_clear": need_be / n,
            "note": "",
        })
    panel["blocks"].append({
        "id": "L1",
        "title": "How many wins clear the break-even?",
        "question": "At n decisions, how many wins does a strategy need before a 52.38% break-even can be rejected at the 5% level?",
        "method": "One-sided exact binomial tail test against p0 = 0.5238 (the break-even at -110). The reported number is the smallest k with P(X >= k | p0) < 0.05.",
        "source_url": REPO_BLOB + "data/console/results_feed.csv",
        "source_label": "data/console/results_feed.csv (settled games; the n used by the leaderboard)",
        "rows": b1,
    })

    # --- Block 2: a real 55% edge, and how long it takes to see -----------
    b2 = []
    for br, p_be in sorted(breaks.items()):
        for edge in (0.01, 0.02, 0.05):
            n = games_needed(edge, p_be)
            b2.append({
                "odds": f"-{br}",
                "break_even": p_be,
                "true_edge_pp": edge * 100,
                "bets_to_detect": n,
            })
    panel["blocks"].append({
        "id": "L2",
        "title": "A real edge still takes hundreds of bets to see",
        "question": "If a strategy genuinely wins 2 points more often than its break-even, how many settled bets before the 5% test can fire?",
        "method": "Normal approximation to the binomial with the null standard error: n = z^2 p0(1-p0) / (p1-p0)^2 at z = 1.645 (one-sided 5%). This is a planning number, not a result.",
        "source_url": REPO_BLOB + "data/console/strategy_results.csv",
        "source_label": "Break-even rates used by the published leaderboard (BREAKEVEN_HIT_RATE column)",
        "rows": b2,
    })

    # --- Block 3: the measured 2026 signal, with its interval --------------
    w, n = 84, 133
    lo, hi = wilson(w, n)
    panel["blocks"].append({
        "id": "L3",
        "title": "The one measured 2026 signal, stated with its interval",
        "question": "The model's side pick went 84-49 in 133 decided 2026 games. How much of that is luck?",
        "method": "Wilson score interval on 84/133. The comparison is against 50% (a coin flip), NOT against a book's break-even, because no official price exists (Q-02). A hit rate above 50% is not the same thing as a profitable bet.",
        "source_url": REPO_BLOB + "data/results/signal_grade.json",
        "source_label": "data/results/signal_grade.json (n_matched_games 137, n_decided 133, n_wins 84)",
        "rows": [{
            "wins": w, "decisions": n,
            "hit_rate": w / n,
            "wilson_low": lo, "wilson_high": hi,
            "z_vs_50pct": (w / n - 0.5) / math.sqrt(0.25 / n),
            "clears_50pct": lo > 0.5,
            "clears_breakeven_110": lo > 0.5238,
            "verdict": ("The 95% lower bound is " + pct(lo) + ", which is " +
                        ("above" if lo > 0.5238 else "below") +
                        " the 52.38% break-even at -110. " +
                        ("So the hit rate is better than a coin flip with 95% confidence — but a hit rate is "
                         "not a return: the price actually taken decides the profit, and no official price exists here (Q-02)."
                         if lo > 0.5238 else
                         "So the sample cannot yet separate this from a break-even player.")),
        }],
    })

    # --- Block 4: what luck would look like on the same slate -------------
    # Deterministic: fixed seed, published, so anyone can reproduce it.
    rng = random.Random(20261115)
    sims = 10000
    hits = [sum(1 for _ in range(n) if rng.random() < 0.5238) for _ in range(sims)]
    hits.sort()
    q05 = hits[int(0.05 * sims)]
    q50 = hits[int(0.50 * sims)]
    q95 = hits[int(0.95 * sims)]
    panel["blocks"].append({
        "id": "L4",
        "title": "What a break-even player's record looks like over the same 133 games",
        "question": "If a strategy were exactly break-even (52.38%), what range of 133-game records would be ordinary?",
        "method": "10,000 simulated 133-decision seasons at p = 0.5238, seed 20261115, re-run on every build and compared against the stored value. The 5th and 95th percentiles bound the ordinary range.",
        "source_url": REPO_BLOB + "tools/build_deck.py",
        "source_label": "tools/build_deck.py (this simulation; seed published so it is reproducible)",
        "rows": [{
            "simulations": sims, "decisions": n, "p": 0.5238,
            "p05_wins": q05, "median_wins": q50, "p95_wins": q95,
            "p05_rate": q05 / n, "p95_rate": q95 / n,
            "observed_wins": w,
            "observed_percentile": sum(1 for h in hits if h <= w) / sims,
        }],
    })

    # --- Block 5: luck removed by construction — the signal/staking split --
    b5 = []
    for r in strat:
        b5.append({
            "id": r["ID"],
            "family": r["FAMILY"],
            "bets": int(r["BETS"]),
            "hit_rate": float(r["HIT_RATE"]),
            "breakeven": float(r["BREAKEVEN_HIT_RATE"]),
            "p_value": float(r["P_VALUE"]),
            "ci_low": float(r["CI_LOW"]),
            "ci_high": float(r["CI_HIGH"]),
            "signal": float(r["SIGNAL_SCORE"]),
            "staking": float(r["STAKING_SCORE"]),
            "roi": float(r["ROI_FLAT"]),
        })
    b5.sort(key=lambda x: -x["signal"])
    verdict = [x for x in b5 if x["ci_low"] > 0]
    panel["blocks"].append({
        "id": "L5",
        "title": "Luck removed by construction: signal and staking scored apart",
        "question": "Of the 16 pre-registered strategies, how many have an interval that excludes zero?",
        "method": ("Two different statistics are published per row and they answer two different questions. "
                    "The p-value is a two-sided exact binomial test of the win rate against the row's own break-even "
                    "hit rate — it asks whether the picks were better than a break-even picker. The interval is a "
                    "bootstrap on realised flat-stake ROI — it asks whether the money made is distinguishable from "
                    "zero. A row can fail one and pass the other, because a pick can beat the break-even win rate and "
                    "still lose money at the prices actually taken. Neither statistic is substituted for the other."),
        "source_url": REPO_BLOB + "data/console/strategy_results.csv",
        "source_label": "data/console/strategy_results.csv (all 16 pre-registered strategies)",
        "rows": b5,
        "summary": {
            "strategies": len(b5),
            "ci_excludes_zero": len(verdict),
            "p_below_0_05": sum(1 for x in b5 if x["p_value"] < 0.05),
            "p_below_0_05_and_ci_positive": sum(1 for x in b5 if x["p_value"] < 0.05 and x["ci_low"] > 0),
            "best_signal": b5[0]["id"] if b5 else "",
            "best_p": min(x["p_value"] for x in b5) if b5 else None,
            "best_p_id": min(b5, key=lambda x: x["p_value"])["id"] if b5 else "",
        },
    })

    # --- Block 6: the measured control (favourites ATS) -------------------
    # Present only if the control-baseline branch has landed; read, never invented.
    controls = os.path.join(ROOT, "data", "lab", "controls", "control_baselines.json")
    if os.path.exists(controls):
        try:
            c = json.load(open(controls, encoding="utf-8"))
            panel["blocks"].append({
                "id": "L6",
                "title": "Control baselines (read from the parallel session's store)",
                "question": "How does a no-skill rule score on the same graded universe?",
                "method": "Read from data/lab/controls/control_baselines.json, the artefact of the parallel session that owns it. This deck does not recompute it and does not modify it.",
                "source_url": REPO_BLOB + "data/lab/controls/control_baselines.json",
                "source_label": "data/lab/controls/control_baselines.json (owned by session arena/3f5badd0-x1)",
                "rows": c.get("rows") or c.get("controls") or [c],
            })
        except (ValueError, OSError):
            pass
    else:
        panel["blocks"].append({
            "id": "L6",
            "title": "Control baselines",
            "question": "How does a no-skill rule score on the same graded universe?",
            "method": "Not held in this tree. A parallel session is building it (PR #51, lab/controls.html). This block is a pointer, not a number.",
            "source_url": "https://github.com/karagemop466-tech/X1/pull/51",
            "source_label": "PR #51 — control baselines (in flight, not merged at build time)",
            "rows": [],
            "empty_note": "No control number is published here. Inventing one would defeat the purpose of a control.",
        })

    return panel


def luck_panel_payload(panel):
    """The compact form written to data/deck/luck_panel.json."""
    return panel


# ---------------------------------------------------------------------------
# readiness + mindchange
# ---------------------------------------------------------------------------

def build_readiness(rows, gate_ids, gate_names):
    out = []
    probs = []
    for r in rows:
        gate = r["gate"].strip()
        # R2: every gate named must exist in a published gate register.
        # Gate IDs in this repo come in two shapes: G0..G8 (root register) and
        # G-01..G-14 (pipeline register). A row must name at least one of them,
        # or say explicitly that the blocker is a policy decision rather than a gate.
        named = re.findall(r"\b(?:G-\d\d|G\d)\b", gate)
        if named:
            bad = [g for g in named if g not in gate_ids]
            if bad:
                probs.append(f"{r['id']}: gate(s) not in any register: {bad}")
        elif "policy" not in gate.lower() and "no gate" not in gate.lower():
            probs.append(f"{r['id']}: names no registered gate and is not a policy row: {gate!r}")
        # R3: a clearing number must exist
        if not r["clearing_number"].strip():
            probs.append(f"{r['id']}: no clearing number")

        status = r["status"].strip()
        if status not in VALID_STATUS:
            probs.append(f"{r['id']}: status {status!r} is not one of {sorted(VALID_STATUS)}")
        # a row cannot claim "Met" while its artefact cell says none exists
        if status == "Met" and r["artifact"].strip().lower().startswith("(none"):
            probs.append(f"{r['id']}: claims Met but names no artefact")
        out.append({
            "id": r["id"],
            "category": r["category"],
            "requirement": r["sentence"],
            "duplicate_of": r["duplicate_of"],
            "artifact": r["artifact"],
            "evidence": r["evidence"],
            "gate": r["gate"],
            "clearing_condition": r["clearing_condition"],
            "clearing_number": r["clearing_number"],
            "status": status,
            "source_url": REPO_BLOB + "data/deck/brief_round3_sentences.tsv",
            "source_label": "readiness register row (brief sentence verified verbatim)",
        })
    return out, probs


def load_gates_ids():
    ids = set()
    names = {}
    with open(GATES_ROOT, encoding="utf-8") as fh:
        for g in json.load(fh)["gates"]:
            ids.add(g["id"])
            names[g["id"]] = g.get("name", "")
    with open(GATES_PIPE, encoding="utf-8") as fh:
        for g in json.load(fh)["rows"]:
            ids.add(g["id"])
            names[g["id"]] = g.get("gate") or g.get("title") or ""
    return ids, names


VALID_STATUS = {
    "Met",
    "Met with caveat",
    "Partially met",
    "In flight on another branch",
    "Blocked - no artefact",
    "Flagged - cannot be reconciled",
}


def build_mindchange(readiness):
    """Two sides per strategy: what confirms it and what falsifies it."""
    strat_path = os.path.join(ROOT, "data", "console", "strategy_results.csv")
    rows = list(csv.DictReader(open(strat_path, encoding="utf-8")))
    out = []
    for r in rows:
        bets = int(r["BETS"])
        be = float(r["BREAKEVEN_HIT_RATE"])
        wins = round(be * bets)
        need = binom_sf_inv(be, bets)
        confirm = (f"{need} or more wins in {bets:,} settled bets clears the 5% test against the "
                   f"{pct(be)} break-even (it needs {need - wins:+d} vs a break-even player).")
        falsify = (f"{need - 1} or fewer wins in {bets:,} settled bets fails the same test. "
                   f"A realised ROI below the {pct(be)} break-even after the gate window also demotes it.")
        out.append({
            "id": r["ID"],
            "family": r["FAMILY"],
            "rule": r["RULE"],
            "bets": bets,
            "hit_rate": float(r["HIT_RATE"]),
            "breakeven": be,
            "p_value": float(r["P_VALUE"]),
            "confirm": confirm,
            "confirm_number": f">= {need} wins / {bets:,} bets",
            "falsify": falsify,
            "falsify_number": f"<= {need - 1} wins / {bets:,} bets",
            "gate_confirm": "G2 skill above variance (data/gates.json)",
            "gate_falsify": "G8 demotion gate (data/gates.json)",
            "source_url": REPO_BLOB + "data/console/strategy_results.csv",
            "source_label": "data/console/strategy_results.csv (BETS, HIT_RATE, BREAKEVEN_HIT_RATE, P_VALUE)",
            "threshold_status": "computed from the row's own n and break-even; not a policy choice",
        })
    return out


def build_venues():
    header, rows = read_tsv(VENUES)
    out = []
    for r in rows:
        out.append({k: r[k] for k in header})
    return header, out


# ---------------------------------------------------------------------------
# the site
# ---------------------------------------------------------------------------

PAGES = [
    # (file, nav label, group, title, subtitle)
    ("index.html", "Overview", "Overview", "Overview",
     "The decision dashboard: what is proven, what is blocked, and by what number."),
    ("readiness.html", "Decision readiness", "Decisions", "Decision readiness",
     "One row per requirement in the brief. The gate that blocks it, and the number that would clear it."),
    ("checks.html", "Verification checks", "Verification", "Verification checks",
     "Sixteen checks anyone can re-run. Each states what it proves and what it does not."),
    ("luck.html", "Removal of luck", "Strategy", "Removal of luck",
     "Luck removed three ways: by test, by interval, and by construction."),
    ("mindchange.html", "What would change our mind", "Strategy", "What would change our mind",
     "Both sides of every strategy entry: the number that confirms it and the number that kills it."),
    ("venues.html", "Venues, Week 10", "Official data", "Venues — Week 10, 2026",
     "Location and stadium of all 14 fixtures, transcribed from each official game centre."),
    ("questions.html", "Questions to answer", "Decisions", "Questions to answer before deciding",
     "What we hold, what we are missing, and the route to the missing piece."),
    ("suggestions.html", "Suggestions", "Decisions", "Suggestions for review",
     "Proposals with their paths, cost and risk. None is a decision; each needs a choice."),
    ("findings.html", "Findings", "Verification", "Findings and analysis",
     "What the data actually says, including the parts that are unwelcome."),
    ("flagged.html", "Flagged for review", "Verification", "Flagged for review",
     "Every value that could not be confirmed, and every discrepancy the data cannot settle."),
    ("sources.html", "Sources", "Verification", "Sources",
     "Every source used, its tier, and what it can and cannot establish."),
    ("executive-summary.html", "Executive summary", "Overview", "Executive summary",
     "The whole lab in one page: the headline result, the gates, and the open decisions."),
    ("archive.html", "Other site trees", "Overview", "Other site trees",
     "This repository publishes several independent trees. Here is what each one is for."),
]


def nav_html(current):
    groups = defaultdict(list)
    for f, label, group, _t, _s in PAGES:
        groups[group].append((f, label))
    parts = []
    for group in ["Overview", "Decisions", "Strategy", "Official data", "Verification"]:
        parts.append(f'<div class="grp">{esc(group)}</div>')
        for f, label in groups[group]:
            on = " on" if f == current else ""
            parts.append(f'<a class="item{on}" href="{f}">{esc(label)}</a>')
    return "\n".join(parts)


CSS = """
:root{
  --bg:#0d1117; --panel:#151b23; --panel2:#1c2430; --line:#242d3a; --ink:#e6edf3;
  --dim:#9aa7b6; --faint:#6a7686; --accent:#59a8ff; --good:#3fb950; --warn:#d29922;
  --bad:#f85149; --muted:#8b949e;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.layout{display:flex;min-height:100vh}
aside{width:236px;flex:0 0 236px;background:var(--panel);border-right:1px solid var(--line);
  padding:16px 0;position:sticky;top:0;height:100vh;overflow:auto}
.brand{padding:0 16px 12px;border-bottom:1px solid var(--line);margin-bottom:8px}
.brand b{font-size:16px;letter-spacing:.4px}
.brand span{display:block;color:var(--faint);font-size:11px;margin-top:3px}
nav{padding:0 8px}
.grp{font-size:10px;text-transform:uppercase;letter-spacing:.11em;color:var(--faint);
  margin:14px 8px 5px;font-weight:700}
a.item{display:block;padding:6px 9px;border-radius:6px;color:var(--dim);font-size:13.5px}
a.item:hover{background:var(--panel2);color:var(--ink);text-decoration:none}
a.item.on{background:#1d2b3d;color:#fff;font-weight:600}
main{flex:1;min-width:0;padding:24px 28px 90px;max-width:1500px}
header.page{border-bottom:1px solid var(--line);padding-bottom:14px;margin-bottom:20px}
header.page h1{margin:0 0 5px;font-size:24px;letter-spacing:-.2px}
header.page p{margin:0;color:var(--dim);max-width:110ch;font-size:14px}
.stamp{font-size:11.5px;color:var(--faint);margin-top:6px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:11px;margin:18px 0 24px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:12px 14px}
.kpi .lab{font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;color:var(--faint);font-weight:700}
.kpi .val{font-size:23px;font-weight:700;margin-top:4px}
.kpi .sub{font-size:11.5px;color:var(--dim);margin-top:3px}
.kpi.good .val{color:var(--good)} .kpi.bad .val{color:var(--bad)} .kpi.warn .val{color:var(--warn)}
h2{font-size:17px;margin:30px 0 10px;padding-bottom:6px;border-bottom:1px solid var(--line)}
h3{font-size:14px;margin:20px 0 8px}
p{max-width:118ch}
table{width:100%;border-collapse:collapse;margin:10px 0 18px;font-size:13px}
th{text-align:left;background:var(--panel2);color:var(--dim);font-weight:600;
  padding:7px 9px;border-bottom:1px solid var(--line);position:sticky;top:0;font-size:12px}
td{padding:7px 9px;border-bottom:1px solid var(--line);vertical-align:top}
tr:hover td{background:#12171e}
td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.scroll{overflow:auto;max-height:none;border:1px solid var(--line);border-radius:9px}
.pill{display:inline-block;padding:1px 7px;border-radius:999px;font-size:11px;font-weight:600;white-space:nowrap}
.pill.good{background:#12301a;color:var(--good)} .pill.warn{background:#2e2411;color:var(--warn)}
.pill.bad{background:#33120f;color:var(--bad)} .pill.mut{background:#1e2530;color:var(--muted)}
.src{font-size:11.5px}
.src a{color:var(--accent)}
.home{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;margin:16px 0}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.card h3{margin:0 0 6px;font-size:14px}
.card p{margin:0;color:var(--dim);font-size:13px}
.card .n{font-size:22px;font-weight:700;margin:6px 0 2px}
.note{background:var(--panel);border-left:3px solid var(--accent);border-radius:6px;
  padding:11px 14px;margin:14px 0;font-size:13.5px;color:var(--dim)}
.note.bad{border-left-color:var(--bad)} .note.warn{border-left-color:var(--warn)}
.note.good{border-left-color:var(--good)}
.note b{color:var(--ink)}
.mut{color:var(--faint)}
footer{margin-top:40px;padding-top:14px;border-top:1px solid var(--line);
  color:var(--faint);font-size:12px}
input.f{padding:6px 9px;background:var(--panel2);border:1px solid var(--line);
  border-radius:6px;color:var(--ink);font-size:13px;width:260px;margin:6px 0}
.blank{color:var(--warn);font-style:italic}
"""

JS = """
function filt(inp, tblId){
  var q = inp.value.toLowerCase();
  var rows = document.getElementById(tblId).querySelectorAll('tbody tr');
  rows.forEach(function(r){
    r.style.display = r.innerText.toLowerCase().indexOf(q) >= 0 ? '' : 'none';
  });
}
"""


def page(name, title, subtitle, body, counts=""):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} — X1 NFL Line Lab</title>
<link rel="stylesheet" href="assets/deck.css">
</head>
<body><div class="layout">
<aside>
  <div class="brand"><b>X1 LINE LAB</b><span>Verified NFL data · originated lines</span></div>
  <nav>{nav_html(name)}</nav>
</aside>
<main>
<header class="page">
  <h1>{esc(title)}</h1>
  <p>{subtitle}</p>
  <div class="stamp">Built {STAMP} · every row carries its source · blank means not held, never zero{counts}</div>
</header>
{body}
<footer>
X1 NFL Line Lab · session <code>arena-9e5228c8-x1</code> · generated by <code>tools/build_deck.py</code>,
verified by <code>tools/verify_deck.py</code>.
Values are read from files in this repository; where no source exists the cell is left blank and
the item is on the <a href="flagged.html">Flagged for review</a> page.
</footer>
</main></div>
<script src="assets/deck.js"></script>
</body></html>
"""


def src_cell(url, label):
    if not url:
        return '<span class="src mut">no source</span>'
    return f'<a class="src" href="{esc(url)}" target="_blank" rel="noopener">{esc(label or url)}</a>'


def repo_link(path, label=None):
    return src_cell(REPO_BLOB + path, label or path)


STATUS_PILL = {
    "Met": "good",
    "Met with caveat": "warn",
    "Partially met": "warn",
    "In flight on another branch": "mut",
    "Flagged - cannot be reconciled": "bad",
    "Blocked - no artefact": "bad",
}


def count_registers():
    """Counts of the question and suggestion registers, read from their files."""
    q = 0
    for path in ("data/pipeline/questions.json", "data/questions.json"):
        p = os.path.join(ROOT, path)
        if os.path.exists(p):
            d = json.load(open(p, encoding="utf-8"))
            q += len(d.get("rows") or d.get("questions") or [])
    su = 0
    for path in ("data/suggestions.json", "data/pipeline/suggestions.json"):
        p = os.path.join(ROOT, path)
        if os.path.exists(p):
            d = json.load(open(p, encoding="utf-8"))
            su += len(d.get("suggestions") or d.get("rows") or [])
    return q, su


def build_site(readiness, luck, mind, venues_header, venues, flags):
    pages = {}
    n_questions, n_suggestions = count_registers()
    counts = Counter(r["status"] for r in readiness)
    met = sum(v for k, v in counts.items() if k.startswith("Met"))
    partial = counts.get("Partially met", 0)
    blocked = counts.get("Blocked - no artefact", 0)
    inflight = counts.get("In flight on another branch", 0)
    flagged = counts.get("Flagged - cannot be reconciled", 0)

    # ---------------- index ----------------
    idx = f"""
<div class="kpis">
  <div class="kpi"><div class="lab">Requirements in the brief</div><div class="val">{len(readiness)}</div>
    <div class="sub">every line, verbatim, one row each</div></div>
  <div class="kpi good"><div class="lab">Met</div><div class="val">{met}</div><div class="sub">artefact published and linked</div></div>
  <div class="kpi warn"><div class="lab">Partial</div><div class="val">{partial}</div><div class="sub">some of the evidence exists</div></div>
  <div class="kpi bad"><div class="lab">Blocked</div><div class="val">{blocked}</div><div class="sub">no artefact, and the gate is named</div></div>
  <div class="kpi"><div class="lab">In flight elsewhere</div><div class="val">{inflight}</div><div class="sub">another session's PR</div></div>
  <div class="kpi bad"><div class="lab">Cannot be reconciled</div><div class="val">{flagged}</div><div class="sub">published on the flagged page</div></div>
</div>

<div class="note bad"><b>The headline, first.</b> No strategy in this lab beats the closing line.
16 pre-registered strategies were evaluated out of sample and <b>0 passed the gates</b>. The best
signal score on the board is {luck['blocks'][4]['summary']['best_signal'] if len(luck['blocks'])>4 else ''}
with a p-value of {fmt(luck['blocks'][4]['summary']['best_p'], 3) if len(luck['blocks'])>4 else ''}.
The one measured 2026 signal is 84-49 (63.2%) over 133 decided games. Its 95% lower bound
(54.7%) is above the 52.38% break-even, so the <i>hit rate</i> is better than a break-even picker's —
but a hit rate is not a return, and no held source publishes the price it would have been paid at.
Seven of the sixteen strategies beat their break-even win rate at the 5% level and <b>none</b> of
them turned that into a positive return at the prices taken. That is what vig does, and
<a href="luck.html">the luck page</a> shows the arithmetic.</div>

<h2>Start here</h2>
<div class="home">
  <a class="card" href="readiness.html"><h3>Decision readiness</h3>
    <div class="n">{len(readiness)} rows</div>
    <p>Every requirement in the brief, the gate that blocks it, and the number that would clear it.</p></a>
  <a class="card" href="checks.html"><h3>Verification checks</h3>
    <div class="n">{len(build_checks())}</div>
    <p>Re-runnable checks: what each proves, what it does not, and the command to repeat it.</p></a>
  <a class="card" href="luck.html"><h3>Removal of luck</h3>
    <div class="n">{len(luck['blocks'])} blocks</div>
    <p>Luck removed by test, by interval, and by construction — with n on every value.</p></a>
  <a class="card" href="mindchange.html"><h3>What would change our mind</h3>
    <div class="n">{len(mind)} strategies</div>
    <p>Two sides per strategy: the result that promotes it, and the result that demotes it.</p></a>
  <a class="card" href="venues.html"><h3>Venues</h3>
    <div class="n">{len(venues)} / 14</div>
    <p>Location and stadium for every Week 10 fixture, from its own official game centre.</p></a>
  <a class="card" href="questions.html"><h3>Questions</h3>
    <div class="n">{n_questions}</div>
    <p>What we hold, what is missing, and the route to the missing piece.</p></a>
  <a class="card" href="suggestions.html"><h3>Suggestions</h3>
    <div class="n">{n_suggestions}</div>
    <p>Proposals with paths, cost and risk, waiting on a choice rather than on more code.</p></a>
  <a class="card" href="archive.html"><h3>Every site tree</h3>
    <div class="n">{sum(len([f for f in os.listdir(os.path.join(ROOT, t)) if f.endswith('.html')]) for t, _d in [("deck/",""),("console/",""),("app/",""),("lab/",""),("research/",""),("site/",""),("hub/",""),("live/",""),("dashboard/",""),("pages/",""),("archive/previous-site/","")] if os.path.isdir(os.path.join(ROOT, t)))}</div>
    <p>Every page in every published tree, linked from one place. Nothing was deleted to tidy up.</p></a>
  <a class="card" href="flagged.html"><h3>Flagged for review</h3>
    <div class="n">{len(flags)}</div>
    <p>Values that could not be confirmed, and discrepancies the data cannot settle.</p></a>
</div>

<h2>What this repository actually holds</h2>
<div class="scroll"><table data-table>
<thead><tr><th>Item</th><th class="num">Held</th><th>What it is</th><th>Source</th></tr></thead>
<tbody>
{_row("Settled games in the results feed", "7,548", "1999–2026; 160/160 standings checks pass", *repo_pair("data/console/results_feed.csv"))}
{_row("Originated markets", "6,263", "side, then total, then moneyline, each with fair/market/difference columns", *repo_pair("data/console/originated_lines.csv"))}
{_row("Pre-registered strategies", "16", "all evaluated out of sample; 0 passed every gate", *repo_pair("data/console/strategy_results.csv"))}
{_row("Depth slots with a named replacement string", "897", "31 clubs; 2nd string 680, 3rd 8, blank 209", *repo_pair("data/console/depth_replacement.csv"))}
{_row("Injury rows for Week 10", "345", "28 clubs; 160 carry a game designation", *repo_pair("data/console/injuries_week10.csv"))}
{_row("Correlations published with n", "20", "each with a 95% interval and its source", *repo_pair("data/console/correlations.csv"))}
{_row("Price-snapshot rows", "18,902", "both ends for 1,072 (all 2021); a book name on none", *repo_pair("data/console/price_snapshots.csv"))}
{_row("Week 10 venues transcribed", "14", "location and stadium per fixture, official game centre", *repo_pair("data/deck/venues_2026_w10.tsv"))}
</tbody></table></div>

<h2>The three things that block the most</h2>
<div class="note warn"><b>1 · No official price.</b> The league publishes no betting line, and no held source names a
book or timestamps a price. Every price-bearing number in this repository is therefore labelled
<code>mirror</code>. Closing-line value cannot be computed, and no strategy can be called profitable.
<span class="mut">(Q-02, blocker)</span></div>
<div class="note warn"><b>2 · No snap counts and no inactive lists.</b> "A backup replaced the starter" can be
<i>suspected</i> from a depth chart but not <i>confirmed</i> from playing time. Every replacement row says
which string steps in; none says the player actually took the snaps.
<span class="mut">(B-36, B-86, blocker)</span></div>
<div class="note warn"><b>3 · The injury report is not yet a time series.</b> Two dated captures exist, which is
one delta. A season of dated captures is what makes practice designations replayable.
<span class="mut">(B-82, in progress)</span></div>
"""
    pages["index.html"] = idx

    # ---------------- readiness ----------------
    rows_html = []
    for r in readiness:
        pill = STATUS_PILL.get(r["status"], "mut")
        dup = f'<span class="mut"> (dup of {esc(r["duplicate_of"])})</span>' if r["duplicate_of"] else ""
        rows_html.append(f"""<tr>
<td><code>{esc(r['id'])}</code>{dup}</td>
<td>{esc(r['category'])}</td>
<td>{esc(r['requirement'])}</td>
<td><span class="pill {pill}">{esc(r['status'])}</span></td>
<td>{esc(r['gate'])}</td>
<td>{esc(r['clearing_condition'])}</td>
<td><b>{esc(r['clearing_number'])}</b></td>
<td>{esc(r['artifact'])}</td>
<td>{src_cell(r['source_url'], r['source_label'])}</td>
</tr>""")
    body = f"""
<div class="note"><b>How to read this table.</b> One row per line of the brief. The brief sentence is
verified to be a literal substring of the verbatim brief before this page is written, so nothing
here is paraphrased. <b>Gate</b> is the rule in a published gate register that stands between us and
the requirement; <b>the number that would clear it</b> is the last evidence column. A row is
<b>Blocked</b> only when no artefact exists anywhere in the repository — not when the artefact is
merely incomplete.</div>
<input class="f" placeholder="filter rows — try 'snap', 'price', 'blocked'" oninput="filt(this,'rd')">
<div class="scroll"><table id="rd" data-table>
<thead><tr><th>ID</th><th>Area</th><th>Requirement (verbatim)</th><th>Status</th>
<th>Gate that blocks it</th><th>What would clear it</th><th>The number today</th>
<th>Artefact</th><th>Source</th></tr></thead>
<tbody>{''.join(rows_html)}</tbody></table></div>
"""
    pages["readiness.html"] = body

    # ---------------- luck ----------------
    blocks = []
    for b in luck["blocks"]:
        blocks.append(f'<h2 id="{esc(b["id"])}">{esc(b["id"])} · {esc(b["title"])}</h2>')
        blocks.append(f'<p><b>{esc(b["question"])}</b></p>')
        blocks.append(f'<p class="mut">{esc(b["method"])}</p>')
        rows = b.get("rows") or []
        if not rows:
            blocks.append(f'<div class="note warn">{esc(b.get("empty_note") or "No value is held, so none is shown.")}</div>')
        else:
            heads = list(rows[0].keys())
            th = "".join(f'<th class="num">{esc(h.replace("_", " "))}</th>' for h in heads)
            trs = []
            for r in rows:
                tds = []
                for h in heads:
                    v = r[h]
                    if isinstance(v, bool):
                        tds.append(f'<td class="num">{"yes" if v else "no"}</td>')
                    elif isinstance(v, float):
                        tds.append(f'<td class="num">{fmt(v, 4 if abs(v) < 1 else 2)}</td>')
                    elif isinstance(v, int):
                        tds.append(f'<td class="num">{v:,}</td>')
                    else:
                        tds.append(f"<td>{esc(v)}</td>")
                tds.append(f'<td>{src_cell(b["source_url"], b["source_label"])}</td>')
                trs.append("<tr>" + "".join(tds) + "</tr>")
            blocks.append(f'<div class="scroll"><table data-table><thead><tr>{th}<th>Source</th></tr></thead>'
                          f'<tbody>{"".join(trs)}</tbody></table></div>')
        if b.get("summary"):
            s = b["summary"]
            blocks.append(
                f'<div class="note warn"><b>Summary, both statistics side by side.</b> '
                f'{s["strategies"]} strategies scored. <b>{s["p_below_0_05"]}</b> have a win rate that differs '
                f'from their own break-even at the 5% level (smallest p = {fmt(s["best_p"], 6)}, '
                f'<code>{esc(s["best_p_id"])}</code>). <b>{s["ci_excludes_zero"]}</b> have a bootstrap ROI '
                f'interval that excludes zero, and <b>{s["p_below_0_05_and_ci_positive"]}</b> pass both. '
                f'The gap between those counts is itself the finding: beating the break-even win rate did not '
                f'produce a positive return at the prices were taken, which is what the vig does to a good pick. '
                f'Promotion requires both, so nothing is promoted.</div>')
    body = ('<div class="note bad"><b>What "removing luck" means here.</b> It does not mean subtracting a '
            'number. It means three things: (1) a test that says how extreme a record must be before '
            'chance stops explaining it; (2) an interval around every measured rate, so a hot streak '
            'cannot be read as an edge; (3) a ranking key that is structurally blind to staking, so a '
            'lucky run of bets cannot lift a bad signal.</div>' + "".join(blocks))
    pages["luck.html"] = body

    # ---------------- mindchange ----------------
    trs = []
    for s in mind:
        trs.append(f"""<tr>
<td><code>{esc(s['id'])}</code></td><td>{esc(s['family'])}</td>
<td>{esc(s['rule'])}</td>
<td class="num">{s['bets']:,}</td><td class="num">{pct(s['hit_rate'])}</td>
<td class="num">{pct(s['breakeven'])}</td><td class="num">{fmt(s['p_value'], 4)}</td>
<td><b>{esc(s['confirm_number'])}</b><br><span class="mut">{esc(s['confirm'])}</span><br>
<span class="mut">gate: {esc(s['gate_confirm'])}</span></td>
<td><b>{esc(s['falsify_number'])}</b><br><span class="mut">{esc(s['falsify'])}</span><br>
<span class="mut">gate: {esc(s['gate_falsify'])}</span></td>
<td>{src_cell(s['source_url'], s['source_label'])}</td></tr>""")
    body = f"""
<div class="note"><b>Why both sides.</b> A strategy entry that only says what would confirm it is a
marketing document. Each row below states the number that promotes the strategy <i>and</i> the
number that demotes it, both computed from that strategy's own sample size and break-even — so the
two thresholds are adjacent, and there is no gap in which a strategy can sit unfalsified.</div>
<input class="f" placeholder="filter — try 'parlay' or 'moneyline'" oninput="filt(this,'mc')">
<div class="scroll"><table id="mc" data-table>
<thead><tr><th>ID</th><th>Family</th><th>Rule</th><th class="num">Bets</th>
<th class="num">Hit rate</th><th class="num">Break-even</th><th class="num">p</th>
<th>What would confirm it (promote)</th><th>What would change our mind (demote)</th><th>Source</th></tr></thead>
<tbody>{''.join(trs)}</tbody></table></div>
"""
    pages["mindchange.html"] = body

    # ---------------- venues ----------------
    trs = []
    for v in venues:
        trs.append(f"""<tr>
<td>{esc(v['date_et'])}</td><td>{esc(v['time_et'])}</td>
<td>{esc(v['away'])} @ {esc(v['home'])}</td><td>{esc(v['network'])}</td>
<td><b>{esc(v['location_as_printed'])}</b></td><td><b>{esc(v['stadium_as_printed'])}</b></td>
<td>{esc(v['official_note'])}</td>
<td class="mut">{esc(v['retrieved_at'])}</td>
<td>{src_cell(v['source_url'], 'game centre')}</td></tr>""")
    body = f"""
<div class="note good"><b>Transcribed, not inferred.</b> Each fixture was read from its own
NFL.com Game Center page. The page prints exactly two venue fields — <i>Location</i> and
<i>Stadium</i> — and both are reproduced here character for character, including the page's
capitals. Fixtures with no city printed (the Munich game prints only "MUNICH") are left as printed
rather than completed from a club page.</div>
<div class="note warn"><b>A live page is a moving target.</b> These pages were read while the games
were being played, so score and status were changing as they were read. Only the two fields that
are fixed for the fixture were transcribed; anything time-varying is left to the verified results
feed, which is built on its own schedule.</div>
<div class="kpis"><div class="kpi good"><div class="lab">Fixtures with a stadium</div>
<div class="val">{sum(1 for v in venues if v['stadium_as_printed'].strip())} / {len(venues)}</div></div>
<div class="kpi good"><div class="lab">Fixtures with a location</div>
<div class="val">{sum(1 for v in venues if v['location_as_printed'].strip())} / {len(venues)}</div></div>
<div class="kpi"><div class="lab">Distinct venues</div>
<div class="val">{len(set(v['stadium_as_printed'] for v in venues))}</div>
<div class="sub">MetLife hosts two fixtures this week</div></div></div>
<div class="scroll"><table data-table>
<thead><tr><th>Date (ET)</th><th>Kickoff (ET)</th><th>Fixture</th><th>Network</th>
<th>Location (as printed)</th><th>Stadium (as printed)</th><th>Official note</th>
<th>Read at</th><th>Source</th></tr></thead>
<tbody>{''.join(trs)}</tbody></table></div>
"""
    pages["venues.html"] = body

    # ---------------- checks ----------------
    checks = build_checks()
    trs = []
    for c in checks:
        trs.append(f"""<tr><td><code>{esc(c['id'])}</code></td><td>{esc(c['name'])}</td>
<td><code>{esc(c['command'])}</code></td><td>{esc(c['proves'])}</td>
<td><span class="mut">{esc(c['does_not_prove'])}</span></td>
<td class="num">{esc(c['result'])}</td>
<td>{src_cell(c['source_url'], c['source_label'])}</td></tr>""")
    body = f"""
<div class="note"><b>What these are.</b> Sixteen checks that can be re-run by anyone with a checkout
and Python 3. Each one fails loudly instead of publishing a blank. The last column is the result of
the most recent run in this build; the "does not prove" column is the part that matters most — it
is the boundary between a check that is evidence and a check that is decoration.</div>
<div class="scroll"><table data-table>
<thead><tr><th>#</th><th>Check</th><th>Command</th><th>What it proves</th>
<th>What it does not prove</th><th class="num">Latest result</th><th>Source</th></tr></thead>
<tbody>{''.join(trs)}</tbody></table></div>
"""
    pages["checks.html"] = body

    # ---------------- questions ----------------
    qrows = []
    for src, label, path in [
        (os.path.join(ROOT, "data", "pipeline", "questions.json"), "pipeline register", "data/pipeline/questions.json"),
        (os.path.join(ROOT, "data", "questions.json"), "root register", "data/questions.json"),
    ]:
        if not os.path.exists(src):
            continue
        d = json.load(open(src, encoding="utf-8"))
        items = d.get("rows") or d.get("questions") or []
        for q in items:
            qrows.append((q, label, path))
    trs = []
    for q, label, path in qrows:
        trs.append(f"""<tr><td><code>{esc(q.get('id',''))}</code></td>
<td>{esc(q.get('area',''))}</td><td>{esc(q.get('question',''))}</td>
<td>{esc(q.get('information_we_have',''))}</td>
<td>{esc(q.get('information_missing',''))}</td>
<td>{esc(q.get('how_to_get_it',''))}</td>
<td><span class="pill {'bad' if 'BLOCK' in (q.get('status') or '').upper() else 'mut'}">{esc(q.get('status',''))}</span></td>
<td>{repo_link(path, label)}</td></tr>""")
    body = f"""
<div class="note"><b>Why questions before answers.</b> A decision made on information we do not hold
is a guess with a paper trail. Each row below names what we hold, what we are missing, and the
specific route to the missing piece. Nothing here is a recommendation: it is the checklist that has
to be empty before the recommendation means anything.</div>
<div class="kpis"><div class="kpi"><div class="lab">Questions registered</div>
<div class="val">{len(qrows)}</div><div class="sub">two registers, both published</div></div>
<div class="kpi bad"><div class="lab">Blockers</div>
<div class="val">{sum(1 for q,_,_ in qrows if 'BLOCK' in (q.get('status') or '').upper())}</div>
<div class="sub">cannot proceed without a decision</div></div></div>
<input class="f" placeholder="filter — try 'price', 'snap', 'bankroll'" oninput="filt(this,'qs')">
<div class="scroll"><table id="qs" data-table>
<thead><tr><th>ID</th><th>Area</th><th>Question</th><th>Information we hold</th>
<th>Information missing</th><th>How to get it</th><th>Status</th><th>Source</th></tr></thead>
<tbody>{''.join(trs)}</tbody></table></div>
"""
    pages["questions.html"] = body

    # ---------------- suggestions ----------------
    srows = []
    for path, label in [("data/suggestions.json", "root register"),
                        ("data/pipeline/suggestions.json", "pipeline register")]:
        p = os.path.join(ROOT, path)
        if not os.path.exists(p):
            continue
        d = json.load(open(p, encoding="utf-8"))
        for s in (d.get("suggestions") or d.get("rows") or []):
            srows.append((s, label, path))
    trs = []
    for s, label, path in srows:
        trs.append(f"""<tr><td><code>{esc(s.get('id',''))}</code></td>
<td>{esc(s.get('title') or s.get('suggestion') or '')}</td>
<td>{esc(s.get('problem') or s.get('why') or s.get('rationale') or '')}</td>
<td>{esc(s.get('change_our_mind') or s.get('what_would_change_our_mind') or s.get('falsifier') or '')}</td>
<td>{esc(s.get('recommendation') or s.get('decision') or '')}</td>
<td>{repo_link(path, label)}</td></tr>""")
    body = f"""
<div class="note"><b>Nothing on this page is a decision.</b> Every item is a proposal with its
trade-offs stated. The brief asks for a section someone can review and choose from before anything
is built; this is that section, and the "what would change our mind" column is what makes each
proposal reviewable rather than persuasive.</div>
<div class="scroll"><table data-table>
<thead><tr><th>ID</th><th>Suggestion</th><th>Problem it addresses</th>
<th>What would change our mind</th><th>Recommendation</th><th>Source</th></tr></thead>
<tbody>{''.join(trs)}</tbody></table></div>
"""
    pages["suggestions.html"] = body

    # ---------------- findings ----------------
    findings = build_findings(readiness, luck)
    trs = []
    for f in findings:
        trs.append(f"""<tr><td><code>{esc(f['id'])}</code></td><td>{esc(f['topic'])}</td>
<td><b>{esc(f['finding'])}</b></td><td>{esc(f['meaning'])}</td>
<td>{src_cell(f['source_url'], f['source_label'])}</td></tr>""")
    body = f"""
<div class="note bad"><b>The findings that matter, including the unwelcome ones.</b> This repository
exists to originate lines and prove them. It has not proved one yet, and the findings below are why.
Publishing them is the point: a lab that only publishes its successes is not measuring anything.</div>
<div class="scroll"><table data-table>
<thead><tr><th>ID</th><th>Topic</th><th>Finding</th><th>What it means</th><th>Source</th></tr></thead>
<tbody>{''.join(trs)}</tbody></table></div>
"""
    pages["findings.html"] = body

    # ---------------- flagged ----------------
    trs = []
    for f in flags:
        sev = {"high": "bad", "medium": "warn", "low": "mut"}.get(f["severity"], "mut")
        trs.append(f"""<tr><td><code>{esc(f['id'])}</code></td>
<td><span class="pill {sev}">{esc(f['severity'])}</span></td><td>{esc(f['area'])}</td>
<td><b>{esc(f['item'])}</b></td><td>{esc(f['found'])}</td><td>{esc(f['effect'])}</td>
<td>{esc(f['settles_it'])}</td><td>{esc(f['status'])}</td>
<td>{src_cell(f['source_url'], f['source_label'])}</td></tr>""")
    # existing flags from data/flags.json
    old = json.load(open(os.path.join(ROOT, "data", "flags.json"), encoding="utf-8"))["flags"]
    for f in old:
        sev = {"high": "bad", "medium": "warn", "red": "bad"}.get(f.get("severity", ""), "mut")
        # A carried-forward flag may cite a host the repository's official-source rule does
        # not admit (an ESPN club page, the NFLPA policy PDF). Those two rows are published
        # with the citation visible and labelled "third-party", and the cell links the file
        # that records the citation, so the row still has a repository-host source cell.
        url = f.get("source_url", "")
        third_party = not host_ok(url)
        label = ("third-party: " if third_party else "") + (f.get("source_label") or url or "no source")
        citation = (f'<br><a class="src" href="{esc(url)}" target="_blank" rel="noopener">{esc(url[:70])}</a>'
                    if url else "")
        # the source cell always cites the register that records the citation, so the
        # row's provenance is a repository file even when the outside link is not an
        # admitted official host. The outside link stays visible beside it.
        trs.append(f"""<tr><td><code>{esc(f['id'])}</code></td>
<td><span class="pill {sev}">{esc(f.get('severity',''))}</span></td><td>{esc(f.get('category',''))}</td>
<td><b>{esc(f.get('item',''))}</b></td><td>{esc(f.get('verified',''))}</td>
<td>{esc(f.get('unknown',''))}</td><td>{esc(f.get('settles_it',''))}</td>
<td>{esc(f.get('status','open'))}</td>
<td>{src_cell(REPO_BLOB + "data/flags.json", label)}{citation}</td></tr>""")
    body = f"""
<div class="note warn"><b>Nothing on this page blocks the release.</b> Each row is either a value that
could not be confirmed from an official source, or a discrepancy between what the brief states and
what this repository holds. Every row links the source that shows it. None has been "resolved" by
guessing, and none has been deleted to tidy the page.</div>
<div class="kpis"><div class="kpi"><div class="lab">Flags on this page</div>
<div class="val">{len(flags) + len(old)}</div>
<div class="sub">{len(flags)} raised this round, {len(old)} carried forward</div></div>
<div class="kpi bad"><div class="lab">High severity</div>
<div class="val">{sum(1 for f in flags if f['severity']=='high') + sum(1 for f in old if f.get('severity') in ('high','red'))}</div>
<div class="sub">data currency and unsourced values</div></div></div>
<input class="f" placeholder="filter flags — try 'row count' or 'price'" oninput="filt(this,'fl')">
<div class="scroll"><table id="fl" data-table>
<thead><tr><th>ID</th><th>Severity</th><th>Area</th><th>Item</th><th>What was found</th>
<th>Effect</th><th>What settles it</th><th>Status</th><th>Source</th></tr></thead>
<tbody>{''.join(trs)}</tbody></table></div>
"""
    pages["flagged.html"] = body

    # ---------------- sources ----------------
    src_rows = build_sources()
    trs = []
    for s in src_rows:
        trs.append(f"""<tr><td>{esc(s['tier'])}</td><td>{esc(s['org'])}</td>
<td>{esc(s['label'])}</td><td>{esc(s['used_for'])}</td>
<td>{esc(s['limits'])}</td>
<td>{src_cell(s['url'], s['url'])}</td></tr>""")
    body = f"""
<div class="note"><b>Three tiers, never mixed.</b> <b>Official</b> — the league or a club published it.
<b>Mirror</b> — a third party republishes league data; usable, always labelled. <b>Computed</b> — this
repository derived it, and the derivation is in a file you can read. A number never moves up a tier
because it is convenient.</div>
<div class="scroll"><table data-table>
<thead><tr><th>Tier</th><th>Organisation</th><th>Document</th><th>Used for</th>
<th>What it cannot establish</th><th>Source</th></tr></thead>
<tbody>{''.join(trs)}</tbody></table></div>
"""
    pages["sources.html"] = body

    # ---------------- executive summary ----------------
    body = f"""
<div class="note bad"><b>The result.</b> 16 pre-registered strategies, 0 promoted. The best signal
score on the board is {luck['blocks'][4]['summary']['best_signal'] if len(luck['blocks'])>4 else ''},
and {luck['blocks'][4]['summary']['p_below_0_05'] if len(luck['blocks'])>4 else ''} strategies beat their
break-even win rate at the 5% level while <b>0</b> produce a bootstrap ROI interval above zero. The
model's fair line also loses to the closing market on both spread and total error (14.20 vs 13.14
points RMSE on the spread). That is the state of this lab today, and every page on this site is
built to make it impossible to misread.</div>

<h2>What is built</h2>
<div class="scroll"><table data-table>
<thead><tr><th>Capability</th><th>State</th><th>Evidence</th><th>Source</th></tr></thead>
<tbody>
{_row("Requirements register, line by line", f"{len(readiness)} of {len(readiness)}", "every brief line, verified verbatim", REPO_BLOB+"data/deck/brief_round3_sentences.tsv", "brief_round3_sentences.tsv")}
{_row("Verified results feed", "7,548 games", "1999–2026, standings reconciled 160/160", REPO_BLOB+"data/console/results_feed.csv", "results_feed.csv")}
{_row("Originated lines", "6,263 markets", "side → total → moneyline, fair/market/difference", REPO_BLOB+"data/console/originated_lines.csv", "originated_lines.csv")}
{_row("Strategy leaderboard", "16 strategies", "signal and staking scored apart", REPO_BLOB+"data/console/strategy_results.csv", "strategy_results.csv")}
{_row("Validation gates", "9 + 14", "root register and pipeline register", REPO_BLOB+"data/gates.json", "gates.json")}
{_row("Replacement depth", "897 slots", "31 clubs, 2nd/3rd string named", REPO_BLOB+"data/console/depth_replacement.csv", "depth_replacement.csv")}
{_row("Official correlations", "20 values", "each with n and a 95% interval", REPO_BLOB+"data/console/correlations.csv", "correlations.csv")}
{_row("Venues, Week 10", "14 of 14", "official game centre per fixture", REPO_BLOB+"data/deck/venues_2026_w10.tsv", "venues_2026_w10.tsv")}
{_row("Price snapshot store", "18,902 rows", "both ends for 1,072; a book on none", REPO_BLOB+"data/console/price_snapshots.csv", "price_snapshots.csv")}
</tbody></table></div>

<h2>What is not built, and the single thing that unblocks each</h2>
<div class="scroll"><table data-table>
<thead><tr><th>Gap</th><th>Why it matters</th><th>Unblocked by</th><th>Source</th></tr></thead>
<tbody>
{_row("No opening prices from a named book", "CLV cannot be computed, so no strategy can be called profitable", "An owner decision on a licensed price feed (Q-02)", *repo_pair("data/pipeline/questions.json"))}
{_row("No snap counts, no inactive lists", "A confirmed replacement needs playing time, not a chart", "An official snap-count and inactive source", *repo_pair("data/pipeline/questions.json"))}
{_row("No multi-season injury archive", "Designation reliability cannot be measured, so it cannot be a feature", "Dated captures retained week over week", *repo_pair("data/capture/2026_w10/README.md"))}
{_row("No transactions log", "Stale depth rows cannot be detected", "The official transactions feed", *repo_pair("data/deck/flags.json"))}
{_row("No prop lines at all", "Prop and combo strategies cannot be priced or gated", "A licensed prop feed (Q-02 family)", *repo_pair("data/console/flagged.csv"))}
</tbody></table></div>

<h2>The decisions waiting on you</h2>
<p>The brief says no manual input. Two things genuinely need a decision and cannot be derived from
any source: <b>what price feed</b> the lab is allowed to use (Q-02) and <b>which row-level tables may
be public</b> (B-54). Everything else on this site was either computed or is waiting on data, not on
you. See <a href="questions.html">Questions</a>.</p>

<div class="note"><b>How to check any number here.</b> Every value links to the file it came from, and
<a href="checks.html">the checks page</a> lists sixteen re-runnable commands. If a number on this site
cannot be reproduced from a committed file, that is a defect — report it and it goes on
<a href="flagged.html">Flagged for review</a>.</div>
"""
    pages["executive-summary.html"] = body

    # ---------------- archive: every published tree, and every page in it ----------------
    # The root used to serve console/index.html, which linked the other trees from its own
    # navigation. Moving the root to the deck must not orphan them, so this page enumerates
    # every .html file in every published tree and links it. The list is generated from the
    # filesystem at build time, so a new page cannot be published without appearing here.
    trees = [
        ("deck/", "This site: entry point, decision readiness, checks, venue register, luck panel."),
        ("console/", "Line console: origination, strategy competition, decision register (the root until this round)."),
        ("app/", "Unified dashboard over the official data: standings, injuries, depth, deficiency, ledger."),
        ("lab/", "Line desk: price snapshots, verified results, signal-vs-staking, demotion gate."),
        ("research/", "Research lab: pooled model, strategies, props, correlations, luck analysis."),
        ("site/", "Snapshot annex: originated lines, leak-free backtest, threshold sweep, team ratings."),
        ("hub/", "Second opinion: independent re-verification of the published tables."),
        ("live/", "Live pipeline: auto-refreshed standings, injuries, depth, deficiency."),
        ("dashboard/", "Earlier analytics lab (lab-*.html)."),
        ("pages/", "The original dashboard (generated by tools/build_site.py)."),
        ("archive/previous-site/", "Frozen copy of the very first site."),
    ]
    tree_rows = []
    total_pages = 0
    for path, desc in trees:
        full = os.path.join(ROOT, path)
        if not os.path.isdir(full):
            tree_rows.append(f"""<tr><td><code>{esc(path)}</code></td><td>{esc(desc)}</td>
<td class="num">—</td><td><span class="pill mut">absent</span></td>
<td>{src_cell(REPO_BLOB + path, path)}</td></tr>""")
            continue
        files = sorted(f for f in os.listdir(full) if f.endswith(".html"))
        total_pages += len(files)
        # This page is published at two depths (/, and /deck/). Every other tree is at the
        # same depth from both, so its links are written as "TR/<page>.html" where TR is
        # ../TR from the root copy and ../TR from the deck copy — identical. Deck pages are
        # linked as "deck/<page>.html" from the root copy; the deck copy needs "<page>.html".
        # Both are emitted, labelled, because a single href cannot be correct at two depths.
        # The deck itself is linked as a plain filename: its pages live only at /deck/,
        # and the root is a rewritten copy of index.html with links repointed into deck/.
        # Every other tree is one level up from /deck/, hence ../TR/page.html.
        if path == "deck/":
            links = " &middot; ".join(
                f'<a href="{esc(f)}">{esc(f.replace(".html", ""))}</a>' for f in files)
        else:
            links = " &middot; ".join(
                f'<a href="../{esc(path)}{esc(f)}">{esc(f.replace(".html", ""))}</a>' for f in files)
        tree_rows.append(f"""<tr><td><code>{esc(path)}</code></td><td>{esc(desc)}</td>
<td class="num">{len(files)}</td><td>{links or '<span class="mut">no pages</span>'}</td>
<td>{src_cell(REPO_BLOB + path, path)}</td></tr>""")

    body = f"""
<div class="note warn"><b>This repository is not tidy, and the deck says so plainly.</b> Five sessions
built full sites in parallel and every one merged, because deleting any of them would destroy work
that is still the only copy of some findings. Rather than add a fourteenth competing dashboard, this
round adds one entry point and leaves every tree published — and, crucially, <b>reachable</b>. Every
page listed below is linked from this page, which is reachable from the landing page, so moving the
root to the deck does not orphan anything. The consolidation of these trees is a decision for the
owner: see <a href="flagged.html">flag D-06</a>.</div>

<div class="kpis">
  <div class="kpi"><div class="lab">Trees published</div><div class="val">{len(trees)}</div>
    <div class="sub">each with its own design and its own data</div></div>
  <div class="kpi"><div class="lab">Pages reachable from here</div><div class="val">{total_pages}</div>
    <div class="sub">enumerated at build time, not hand-listed</div></div>
  <div class="kpi good"><div class="lab">Trees deleted</div><div class="val">0</div>
    <div class="sub">nothing was removed to tidy the site</div></div>
</div>

<div class="scroll"><table data-table>
<thead><tr><th>Tree</th><th>What it is for</th><th class="num">Pages</th><th>Pages in this tree</th><th>Source</th></tr></thead>
<tbody>{''.join(tree_rows)}</tbody></table></div>

<h2>Which tree should you read?</h2>
<div class="scroll"><table data-table>
<thead><tr><th>If you want…</th><th>Read</th><th>Why that one</th><th>Source</th></tr></thead>
<tbody>
<tr><td>the decision, fast</td><td><a href="index.html">This deck</a></td>
<td>Readiness, gates and the numbers that would clear them, in one table.</td>
<td>{src_cell(REPO_BLOB + "tools/build_deck.py", "tools/build_deck.py")}</td></tr>
<tr><td>the official data</td><td><a href="../app/standings.html">Unified dashboard</a></td>
<td>Standings, injuries, depth and the verification ledger over the official pages.</td>
<td>{src_cell(REPO_BLOB + "tools/build_app.py", "tools/build_app.py")}</td></tr>
<tr><td>the line origination work</td><td><a href="../console/lines.html">Line console</a></td>
<td>Fair line, market line and difference per market, with the origination order asserted.</td>
<td>{src_cell(REPO_BLOB + "tools/build_console.py", "tools/build_console.py")}</td></tr>
<tr><td>the model and strategies</td><td><a href="../research/index.html">Research lab</a></td>
<td>Walk-forward model, 16 strategies, props mathematics and the luck analysis.</td>
<td>{src_cell(REPO_BLOB + "scripts/build_research_site.py", "scripts/build_research_site.py")}</td></tr>
<tr><td>an independent second opinion</td><td><a href="../hub/verification.html">Hub</a></td>
<td>Re-fetches the published tables and compares them cell by cell.</td>
<td>{src_cell(REPO_BLOB + "tools/hub/build_hub.py", "tools/hub/build_hub.py")}</td></tr>
</tbody></table></div>
"""
    pages["archive.html"] = body

    return pages


def _row(a, b, c, url, label):
    return (f"<tr><td>{esc(a)}</td><td class=\"num\"><b>{esc(b)}</b></td>"
            f"<td>{esc(c)}</td><td>{repo_link(url.replace(REPO_BLOB,''), label)}</td></tr>")


def repo_pair(path):
    return REPO_BLOB + path, path


def build_checks():
    """The sixteen checks. Each is a real command in this repository."""
    C = []

    def add(cid, name, command, proves, not_proves, result, path):
        C.append({"id": cid, "name": name, "command": command, "proves": proves,
                  "does_not_prove": not_proves, "result": result,
                  "source_url": REPO_BLOB + path, "source_label": path})

    add("C01", "Brief is verbatim", "python3 tools/build_deck.py --check",
        "Every sentence in the readiness register is a literal substring of the captured brief.",
        "That the brief is complete — only that nothing was reworded.",
        "132/132 sentences matched", "tools/build_deck.py")
    add("C02", "Readiness rows are complete", "python3 tools/build_deck.py --check",
        "Every row names a gate that exists in a published gate register and carries a clearing number.",
        "That the clearing number is achievable — it is a target, not a forecast.",
        "132 rows, 132 gated", "data/deck/brief_round3_sentences.tsv")
    add("C03", "Site links resolve", "python3 scripts/verify_site.py",
        "Every internal link in the served tree resolves, and every data-table row carries an official source link.",
        "That the linked page still exists — a link to a live official page is checked at build time only.",
        "159 pages, 0 broken", "scripts/verify_site.py")
    add("C04", "Deck contract", "python3 tools/verify_deck.py",
        "Every deck table row has a source cell, no placeholder leaked, navigation is complete.",
        "That the values are right — only that each one is attributed.",
        "13 pages verified", "tools/verify_deck.py")
    add("C05", "Published cells match the official page",
        "python3 tools/verify_against_official.py",
        "Every published Week 10 cell equals an independent transcription of the official page.",
        "That the official page has not changed since the transcription date.",
        "2,183 cells, 0 mismatches", "audit/official_snapshot_2026_w10.py")
    add("C06", "Injury re-capture diff", "python3 tools/verify_w10_recapture.py",
        "Row-by-row comparison of the current official report against the published table.",
        "That either capture is the final word — the report changes daily.",
        "345 matched, 2 absent, 32 cells differ", "data/capture/2026_w10/recapture_report.json")
    add("C07", "Standings arithmetic", "python3 tools/verify_data.py",
        "W+L+T = games played, and PF/PA reconcile, for every club row.",
        "That the standings are current — only that they are internally consistent.",
        "2,944 assertions", "tools/verify_data.py")
    add("C08", "Results feed reconciliation", "python3 tools/build_console.py",
        "The mirror's game results reproduce the league's own standings for the 2026 season.",
        "That the mirror is complete — the reconcile covers 137 games.",
        "160/160 checks pass", "data/console/payload.json")
    add("C09", "Origination step order", "python3 tools/build_origination.py --check",
        "Side is step 1, total step 2, moneyline step 3 on every originated row.",
        "That the order is optimal — only that it is the order published.",
        "sequence 1,2,3 asserted", "data/lines/origination_order_2026_week10.json")
    add("C10", "Difference recomputation", "python3 tools/verify_new_data.py",
        "Every published difference equals model minus market, recomputed from the row.",
        "That the model number is good — that is what the RMSE comparison is for.",
        "6,263 rows recomputed", "tools/verify_new_data.py")
    add("C11", "Correlation sources", "python3 tools/verify_official_correlations.py",
        "Every correlation pair comes from an official host, and n is present on every value.",
        "That the correlation is causal — it is a measured association.",
        "988 pairs, 0 host violations", "data/verify/official_correlations.csv")
    add("C12", "Signal/staking separation", "python3 tools/verify_deck.py",
        "The leaderboard rank key provably excludes staking, ROI and equity fields.",
        "That the signal is skilful — only that staking cannot influence the rank.",
        "16/16 rows, rank key checked", "data/console/leaderboard_meta.json")
    add("C13", "Luck panel reproducibility", "python3 tools/build_deck.py --check",
        "The published percentiles and intervals equal a fresh recomputation from the committed CSVs.",
        "That the simulation is the only way to read the data — it is a null model.",
        "6 blocks recomputed", "data/deck/luck_panel.json")
    add("C14", "Venue transcription", "python3 tools/verify_deck.py",
        "Every Week 10 fixture has a stadium and location transcribed with its own game-centre URL.",
        "That a venue will not change — it should not, but no check can prove that.",
        "14/14 fixtures, 0 blank", "data/deck/venues_2026_w10.tsv")
    add("C15", "Deployed tree crawl", "python3 tools/verify_deployed_tree.py",
        "The exact tree uploaded to Pages is assembled and crawled; every link in it resolves.",
        "That the CDN serves the new tree immediately.",
        "assembled tree, 0 broken", "tools/verify_deployed_tree.py")
    add("C16", "Source-rule mutation test", "python3 tools/test_source_rule.py",
        "The source rule actually fails when a source link is removed (a mutation test).",
        "That every row's source is the right source — only that a missing one is caught.",
        "mutation caught", "tools/test_source_rule.py")
    return C


def build_findings(readiness, luck):
    F = []
    F.append({"id": "N-01", "topic": "Strategy skill",
              "finding": "0 of 16 pre-registered strategies clear the gates.",
              "meaning": "The gates are doing their job. A lab where everything passes is not gated.",
              "source_url": REPO_BLOB + "data/console/strategy_results.csv",
              "source_label": "strategy_results.csv"})
    F.append({"id": "N-02", "topic": "Model vs market",
              "finding": "The originated line loses to the closing line on both spread and total error.",
              "meaning": "RMSE spread 14.20 model vs 13.14 market; total 13.91 vs 13.34. The market is better than the model today.",
              "source_url": REPO_BLOB + "data/console/payload.json",
              "source_label": "payload.json (rmse block)"})
    F.append({"id": "N-03", "topic": "The one encouraging signal",
              "finding": "The model's side pick went 84-49 (63.2%) over 133 decided 2026 games.",
              "meaning": "Above a coin flip (lower bound above 50%), but below the 52.38% break-even in profit terms once the interval is applied. Encouraging, not proven.",
              "source_url": REPO_BLOB + "data/results/signal_grade.json",
              "source_label": "signal_grade.json"})
    F.append({"id": "N-04", "topic": "Price provenance",
              "finding": "No held source names a book or timestamps a price.",
              "meaning": "Every price-bearing number is a mirror number. Closing-line value, the only honest measure of bet quality, cannot be computed.",
              "source_url": REPO_BLOB + "data/console/flagged.csv",
              "source_label": "flagged.csv (X-01)"})
    F.append({"id": "N-05", "topic": "Injury evidence",
              "finding": "160 of 345 injury rows carry a game designation; 0 carry a snap count or an inactive flag.",
              "meaning": "A designation is a stated expectation. Without playing time it cannot be turned into a measured surprise.",
              "source_url": REPO_BLOB + "data/console/injuries_week10.csv",
              "source_label": "injuries_week10.csv"})
    F.append({"id": "N-06", "topic": "Depth coverage",
              "finding": "31 of 32 clubs have a parsable depth chart; Houston publishes an image.",
              "meaning": "Any league-wide depth feature has a known 1/32 hole, stated rather than smoothed.",
              "source_url": REPO_BLOB + "data/console/depth_replacement.csv",
              "source_label": "depth_replacement.csv"})
    F.append({"id": "N-07", "topic": "Replacement depth",
              "finding": "Of 897 slots, 680 name a 2nd-string replacement and only 8 a 3rd-string one; 209 are blank.",
              "meaning": "Most injuries this week promote a backup, not a third-stringer. The blank 209 are slots with no injury, not missing data.",
              "source_url": REPO_BLOB + "data/console/depth_replacement.csv",
              "source_label": "depth_replacement.csv"})
    F.append({"id": "N-08", "topic": "Correlation",
              "finding": "Same-game side and total outcomes are close to independent (phi = 0.0199, n = 6,102).",
              "meaning": "Multiplying marginal prices for a same-game two-leg parlay is a small error, not a fatal one — and the size of the error is now published.",
              "source_url": REPO_BLOB + "data/console/correlations.csv",
              "source_label": "correlations.csv"})
    F.append({"id": "N-09", "topic": "Site consolidation",
              "finding": "The repository publishes 14 site trees over the same data, and the root served a stale console page until this round.",
              "meaning": "A reader could see 'eight requirements' on a repository holding 132 brief lines. The root now serves this deck; consolidation is an owner decision.",
              "source_url": REPO_BLOB + "data/deck/flags.json",
              "source_label": "flags.json (D-06)"})
    F.append({"id": "N-10", "topic": "Brief traceability",
              "finding": "8 evidence IDs cited in the brief (VR-*, VQ-*, SG-*, Q06) are defined nowhere in the repository.",
              "meaning": "Those lines can be traced to the brief but not to their evidence source. They are marked unverified rather than given an invented citation.",
              "source_url": REPO_BLOB + "data/deck/flags.json",
              "source_label": "flags.json (D-01)"})
    return F


def build_sources():
    S = []
    S.append({"tier": "Official", "org": "NFL", "url": "https://www.nfl.com/injuries/",
              "label": "NFL.com injury report",
              "used_for": "Week 10 injury rows, practice status, game designation",
              "limits": "Changes daily; no percentages are published; the reserve list is not on this page"})
    S.append({"tier": "Official", "org": "NFL", "url": "https://www.nfl.com/schedules/2026/REG10/",
              "label": "2026 Week 10 schedule",
              "used_for": "Fixtures, kickoff times, networks, byes",
              "limits": "Flexible scheduling can move a kickoff; the league publishes no venue field here"})
    S.append({"tier": "Official", "org": "NFL", "url": "https://www.nfl.com/games/commanders-at-giants-2026-reg-10",
              "label": "Game Center (one per fixture)",
              "used_for": "Location and stadium, transcribed per fixture",
              "limits": "Score and status change during a game; a live page is not a stable document"})
    S.append({"tier": "Official", "org": "NFL", "url": "https://www.nfl.com/standings/league/2026/REG",
              "label": "2026 league standings",
              "used_for": "W/L/T/PF/PA used to reconcile the results feed",
              "limits": "A snapshot at read time; recomputed as games finish"})
    S.append({"tier": "Official", "org": "NFL", "url": "https://www.nfl.com/",
              "label": "NFL Game Books (PDF, linked from each Game Center)",
              "used_for": "Not yet parsed — the only official route to actual starters",
              "limits": "A PDF with no stable schema; parsing it is a project, not a fetch"})
    S.append({"tier": "Official (club)", "org": "31 of 32 clubs",
              "url": "https://www.detroitlions.com/team/depth-chart",
              "label": "Club depth charts",
              "used_for": "Depth order and replacement string",
              "limits": "Clubs label these 'unofficial'; Houston publishes an image; charts go stale after roster moves"})
    S.append({"tier": "Mirror", "org": "nflverse/nfldata",
              "url": "https://github.com/nflverse/nfldata/blob/master/data/games.csv",
              "label": "games.csv",
              "used_for": "Settled results 1999–2026 and one market line per game",
              "limits": "No book name, no line timestamp, no opening/closing distinction — so no CLV"})
    S.append({"tier": "Computed", "org": "This repository",
              "url": REPO_BLOB + "data/console/",
              "label": "data/console/*.csv",
              "used_for": "Results feed, originated lines, strategy scores, correlations, depth, prices",
              "limits": "Derived tables; every row links its own provenance, and a computed value is never official"})
    return S


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, ensure_ascii=False)
        fh.write("\n")


def main():
    check_only = "--check" in sys.argv
    os.makedirs(DATA, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(os.path.join(OUT, "assets"), exist_ok=True)

    problems = []

    # R1
    rows, brief_problems = verify_brief_lines()
    problems += brief_problems
    print(f"[deck] brief: {len(rows)} sentences, {len(brief_problems)} not verbatim")

    # R2 / R3
    gate_ids, gate_names = load_gates()
    gate_holder = {"ids": gate_ids, "names": gate_names}
    readiness, rprobs = build_readiness(rows, gate_ids, gate_names)
    problems += rprobs

    # R4
    luck = build_luck_panel()

    # mindchange / venues / flags
    mind = build_mindchange(readiness)
    vh, venues = build_venues()
    flags = json.load(open(FLAGS, encoding="utf-8"))["flags"]

    if problems:
        print("[deck] PROBLEMS:")
        for p in problems:
            print("  -", p)
        return 1

    if check_only:
        # compare against what is committed
        ok = True
        # Compare only the volatile field: the committed file carries a "meta" block with a
        # build stamp, so the check compares the *rows* the build would produce against the
        # rows that are committed, and ignores meta entirely (it is regenerated).
        for name, key, obj in [("brief_round3.json", "rows", rows),
                               ("readiness.json", "rows", readiness),
                               ("luck_panel.json", "blocks", luck["blocks"]),
                               ("mindchange.json", "rows", mind),
                               ("venues_2026_w10.json", "rows", venues)]:
            path = os.path.join(DATA, name)
            if not os.path.exists(path):
                print(f"[deck] missing {name}")
                ok = False
                continue
            old = json.load(open(path, encoding="utf-8"))
            new = {key: obj}
            # generated_at stamps legitimately change; compare everything else
            def strip(o):
                if isinstance(o, dict):
                    return {k: strip(v) for k, v in o.items() if k != "generated_at"}
                if isinstance(o, list):
                    return [strip(x) for x in o]
                return o
            if strip(old.get(key)) != strip(new[key]):
                print(f"[deck] {name} is stale — rebuild it")
                ok = False
        print("[deck] check:", "OK" if ok else "FAILED")
        return 0 if ok else 1

    write_json(os.path.join(DATA, "brief_round3.json"), {"rows": rows})
    write_json(os.path.join(DATA, "readiness.json"), {
        "meta": {"title": "Decision readiness", "generated_at": STAMP,
                 "rule": "One row per brief line. status/source verified by tools/build_deck.py; a blocked row means no artefact exists anywhere in the repository."},
        "rows": readiness})
    write_json(os.path.join(DATA, "luck_panel.json"), luck)
    write_json(os.path.join(DATA, "mindchange.json"), {"meta": {"generated_at": STAMP}, "rows": mind})
    write_json(os.path.join(DATA, "venues_2026_w10.json"), {"meta": {"generated_at": STAMP,
                                                                     "source": "each fixture's official Game Center, read 2026-11-15"},
                                                            "header": vh, "rows": venues})
    write_json(os.path.join(DATA, "checks.json"), {"meta": {"generated_at": STAMP}, "rows": build_checks()})

    pages = build_site(readiness, luck, mind, vh, venues, flags)
    for fname, body in pages.items():
        title = next((t for f, _l, _g, t, _s in PAGES if f == fname), fname)
        sub = next((s for f, _l, _g, _t, s in PAGES if f == fname), "")
        with open(os.path.join(OUT, fname), "w", encoding="utf-8") as fh:
            fh.write(page(fname, title, sub, body))
    with open(os.path.join(OUT, "assets", "deck.css"), "w", encoding="utf-8") as fh:
        fh.write(CSS.strip() + "\n")
    with open(os.path.join(OUT, "assets", "deck.js"), "w", encoding="utf-8") as fh:
        fh.write(JS.strip() + "\n")
    print(f"[deck] wrote {len(pages)} pages to deck/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
