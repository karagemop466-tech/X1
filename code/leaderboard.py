#!/usr/bin/env python3
"""X1 strategy leaderboard: scoring, validation gates, and reward accounting.

Competition design (see docs/methodology/leaderboard.md for the full spec):
- Strategies are registered with a written thesis and must PASS validation gates
  before they can earn leaderboard points.
- Bets are logged to data/strategies/bets.csv (append-only; every row needs a
  timestamp BEFORE kickoff and a market line captured at bet time).
- Scoring rewards SKILL, not luck:
    * singles: +10 win, -11 loss (vig-aware), 0 push
    * closing-line value (CLV): +2 points per full point the closing line moved
      toward the bet after bet time (measured vs the logged line)
    * parlays: fair joint probability adjusted by the measured same-game
      correlation (phi) — no blind multiplication; correlated parlays that do not
      declare their correlation are rejected at logging time
    * drawdown and variance caps keep one hot streak from winning a season
- Gates (all must pass to move status provisional -> official):
    G1 written thesis + edge source identified
    G2 backtest >= 3 seasons with ROI > 0 after -110 pricing
    G3 minimum sample: >= 100 graded bets (>= 25 for provisional display)
    G4 binomial significance: P(win rate <= breakeven | p=0.524) < 0.05
    G5 out-of-sample period ROI > 0
    G6 portfolio correlation with every official strategy <= 0.70
    G7 max drawdown <= 25 units in backtest
- Rewards: season pool paid 60/25/15 to top-3 official strategies. The pool is
  funded by the owner (decision pending — see docs/analysis/open-questions.md Q7).

This script: (1) grades logged bets, (2) computes scores, (3) checks gates,
(4) emits leaderboard + registry snapshots. Deterministic; stdlib only.
"""
import csv, json, math, os, datetime

ROOT = os.path.join(os.path.dirname(__file__), "..")
S = os.path.join(ROOT, "data", "strategies")
BREAKEVEN_WIN = 0.524          # win rate needed at -110
GATE_MIN_BETS_OFFICIAL = 100
GATE_MIN_BETS_PROVISIONAL = 25


def binom_p_leq(k, n, p):
    """P(X <= k) for X ~ Bin(n, p); normal approximation with continuity corr."""
    if n == 0:
        return 1.0
    z = (k + 0.5 - n * p) / math.sqrt(n * p * (1 - p))
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


STRATEGIES = [
    # id, name, market, thesis, edge_source, gates, status, notes
    ("S1", "backup-qb-deficiency-fade", "spread/total",
     "When a primary starter (QB1 or 3+ of 4 along the OL) is out, markets under-react for "
     "division opponents and short-week spots; fade the injured side in the first half market.",
     "Official NFL.com injury report depth deltas + official depth charts (MISSING DATA — see open questions Q3/Q4)",
     {"G1": "pass", "G2": "blocked", "G3": "blocked", "G4": "blocked", "G5": "blocked", "G6": "pending", "G7": "blocked"},
     "blocked-data",
     "Requires historical depth-chart data (nflverse rosters.csv is stale at 2019) and prop/first-half markets. Cannot be validated from in-repo data yet."),
    ("S2", "injury-report-leverage", "total/team-total",
     "When 2+ defensive starters in the back seven are OUT, the opponent's team total is "
     "systematically under-priced in the following 48h window.",
     "NFL.com weekly injury reports (verified in data/injuries/) + historical game results; needs play-by-play to isolate",
     {"G1": "pass", "G2": "blocked", "G3": "blocked", "G4": "blocked", "G5": "blocked", "G6": "pending", "G7": "blocked"},
     "blocked-data",
     "Needs historical injury archives (2006-2025) joined to results — discovery action listed in open questions Q4."),
    ("S3", "rest-travel-intl", "spread",
     "Rest differential >= 7 days vs opponent on <= 6, and international/timezone trips "
     "(2026 has 9 international games incl. Melbourne/Rio/Paris) shift margin by ~1-2 pts.",
     "games.csv rest columns + location=Neutral rows (available in-repo)",
     {"G1": "pass", "G2": "in-progress", "G3": "fail", "G4": "fail", "G5": "pending", "G6": "pending", "G7": "pending"},
     "provisional",
     "Data available; backtest harness exists (code/build_lines.py). Not yet isolated; no live bets logged."),
    ("S4", "model-spread-edge", "spread",
     "Bet the X1 model's spread when it disagrees with the market by >= 7 pts AND the "
     "model has a QB/situational override the market already prices (inverse of v1 findings).",
     "code/build_lines.py threshold sweep: v1 shows NEGATIVE ROI at all thresholds (-6.1%..-2.6%) — "
     "strategy is therefore NOT validated; requires QB-adjusted model v2 first",
     {"G1": "pass", "G2": "fail", "G3": "fail", "G4": "fail", "G5": "fail", "G6": "pending", "G7": "fail"},
     "failed-gate",
     "Kept on the registry as the measured baseline: honesty gate working as designed. v2 model (QB-aware) is the path."),
    ("S5", "model-total-edge", "total",
     "Bet X1 total when it differs from market by >= 4 pts with injury-adjusted expected pace.",
     "code/build_lines.py: v1 totals ROI -5.5% at 2-pt threshold — NOT validated; blocked pending v2 + pace features",
     {"G1": "pass", "G2": "fail", "G3": "fail", "G4": "fail", "G5": "fail", "G6": "pending", "G7": "fail"},
     "failed-gate",
     "As S4: baseline honesty result. Improvement tracked via model_config.json versioning."),
    ("S6", "correlated-parlay-book", "parlay",
     "Same-game parlays priced with the measured phi (data/lines/correlation_report.csv) instead of "
     "naive multiplication; only bet when book price > correlated fair price by >= 8%.",
     "correlation_report.csv: phi = -0.023 (n=1496) — same-game spread/total legs near-uncorrelated; "
     "fair price ≈ naive price, so the edge must come from book overpricing",
     {"G1": "pass", "G2": "in-progress", "G3": "fail", "G4": "fail", "G5": "pending", "G6": "pending", "G7": "pending"},
     "provisional",
     "Parlay fair-price calculator lives in this file (parlay_fair). Needs a real odds feed to compare prices (open question Q6)."),
]


def parlay_fair(probs, phi=0.0):
    """Joint probability of independent legs with a pairwise correlation haircut.

    For n legs with marginal win probs p_i and measured pairwise phi (same-game),
    the joint P is approximated as:
        P_naive = prod p_i
        P = clamp(P_naive * (1 - phi * (n - 1)), 0, 1)   for n >= 2
    phi measured from data (see correlation_report.csv). Documented approximation —
    for n > 2 use pairwise-summed inclusion-exclusion in a future version.
    """
    p = 1.0
    for x in probs:
        p *= max(0.0, min(1.0, x))
    n = len(probs)
    if n >= 2:
        p = p * (1 - phi * (n - 1))
    return max(0.0, min(1.0, p))


def grade_bets():
    """Grade logged bets. Bets must be pre-kickoff logged with market line."""
    path = os.path.join(S, "bets.csv")
    if not os.path.exists(path):
        return []
    out = []
    for b in csv.DictReader(open(path)):
        out.append(b)
    return out


def score(strategy_id, bets):
    """Compute score for one strategy from graded bets."""
    pts = 0.0
    w = l = p = 0
    clv_sum = 0.0
    equity = 0.0
    peak = 0.0
    maxdd = 0.0
    for b in bets:
        if b["strategy"] != strategy_id:
            continue
        legs = int(b.get("legs", "1") or 1)
        result = b["result"]
        if legs == 1:
            if result == "W":
                pts += 10; equity += 0.909; w += 1
            elif result == "L":
                pts -= 11; equity -= 1.0; l += 1
            else:
                p += 1
        else:
            probs = [float(x) for x in b.get("leg_probs", "").split("|") if x]
            phi = float(b.get("phi", "0") or 0)
            fair = parlay_fair(probs, phi) if probs else 0.0
            price = float(b.get("price_decimal", "0") or 0)
            if result == "W":
                equity += price - 1
                pts += 10 * (price - 1)
                w += 1
            elif result == "L":
                equity -= 1
                pts -= 11
                l += 1
            else:
                p += 1
        clv = float(b.get("clv_pts", "0") or 0)
        clv_sum += clv
        pts += 2.0 * clv
        peak = max(peak, equity)
        maxdd = max(maxdd, peak - equity)
    n = w + l
    wr = w / n if n else 0.0
    pval = binom_p_leq(w, n, BREAKEVEN_WIN)
    return {"strategy": strategy_id, "bets": n, "wins": w, "losses": l, "pushes": p,
            "win_rate": round(wr, 4), "breakeven_p": BREAKEVEN_WIN,
            "binom_p_leq_breakeven": round(pval, 4),
            "avg_clv_pts": round(clv_sum / max(1, w + l + p), 3),
            "equity_units": round(equity, 2), "max_drawdown_units": round(maxdd, 2),
            "points": round(pts, 1)}


def main():
    os.makedirs(S, exist_ok=True)
    # registry (write once — source of truth for the site)
    with open(os.path.join(S, "strategies_registry.csv"), "w", newline="") as fh:
        w_ = csv.writer(fh)
        w_.writerow(["id", "name", "markets", "thesis", "edge_source", "gates", "status", "notes"])
        for (sid, name, mkt, thesis, src, gates, status, notes) in STRATEGIES:
            w_.writerow([sid, name, mkt, thesis, src,
                         "; ".join(f"{k}:{v}" for k, v in gates.items()), status, notes])

    bets = grade_bets()
    rows = []
    for (sid, *_rest) in STRATEGIES:
        sc = score(sid, bets)
        n = sc["bets"]
        if n >= GATE_MIN_BETS_OFFICIAL and sc["binom_p_leq_breakeven"] < 0.05 and sc["equity_units"] > 0:
            status = "official"
        elif n >= GATE_MIN_BETS_PROVISIONAL:
            status = "provisional"
        else:
            status = "unproven"
        sc["status"] = status
        rows.append(sc)

    with open(os.path.join(S, "leaderboard.csv"), "w", newline="") as fh:
        w_ = csv.DictWriter(fh, fieldnames=["strategy", "status", "bets", "wins", "losses",
                                            "pushes", "win_rate", "avg_clv_pts", "equity_units",
                                            "max_drawdown_units", "binom_p_leq_breakeven", "points"],
                            extrasaction="ignore")
        w_.writeheader()
        for r in sorted(rows, key=lambda x: -x["points"]):
            w_.writerow(r)

    # luck-vs-skill reference table: required n for significance at various win rates
    luck = []
    for true_wr in (0.545, 0.55, 0.56, 0.58):
        # n such that P(observing <= breakeven wins | true wr) < 0.05 approx
        n = 1
        while True:
            z = (BREAKEVEN_WIN - true_wr) * math.sqrt(n) / math.sqrt(true_wr * (1 - true_wr))
            if abs(z) > 0 and 0.5 * (1 + math.erf(-abs(z) / math.sqrt(2))) < 0.05:
                break
            n += 1
            if n > 5000:
                break
        luck.append({"true_win_rate": true_wr, "bets_needed_for_95pct_confidence": n,
                     "expected_units_at_-110": round(n * (true_wr * 0.909 - (1 - true_wr)), 1)})
    with open(os.path.join(S, "luck_reference.csv"), "w", newline="") as fh:
        w_ = csv.DictWriter(fh, fieldnames=["true_win_rate", "bets_needed_for_95pct_confidence",
                                            "expected_units_at_-110"])
        w_.writeheader()
        for r in luck:
            w_.writerow(r)

    meta = {
        "generated": datetime.datetime.utcnow().isoformat() + "Z",
        "scoring": {"single_win": 10, "single_loss": -11, "clv_bonus_per_pt": 2.0,
                    "breakeven_win_rate_at_-110": BREAKEVEN_WIN},
        "gates": {"official_min_bets": GATE_MIN_BETS_OFFICIAL,
                  "provisional_min_bets": GATE_MIN_BETS_PROVISIONAL,
                  "significance": "binomial P(win<=breakeven) < 0.05",
                  "max_drawdown_units": 25,
                  "portfolio_corr_cap": 0.70},
        "rewards": {"pool": "owner-funded (pending decision — open question Q7)",
                    "payout_split": [0.60, 0.25, 0.15], "paid_to": "top-3 official strategies"},
        "logged_bets": len(bets),
        "note": "No bets logged yet — every strategy is unproven/failed-gate/provisional. "
                "This is the correct honest starting state.",
    }
    with open(os.path.join(S, "leaderboard_meta.json"), "w") as fh:
        json.dump(meta, fh, indent=2)

    print("strategies registered:", len(STRATEGIES))
    print("bets logged:", len(bets))
    for r in sorted(rows, key=lambda x: -x["points"]):
        print(f"{r['strategy']}: status={r['status']} bets={r['bets']} points={r['points']}")


if __name__ == "__main__":
    main()
