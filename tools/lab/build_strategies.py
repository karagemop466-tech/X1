#!/usr/bin/env python3
"""T15 + T18 - a leaderboard that separates SIGNAL from STAKING, with a demotion gate.

Run:  python3 tools/lab/build_strategies.py

The problem this solves
-----------------------
A leaderboard that ranks on ROI ranks *staking luck* as often as skill.  A flat 1-unit
better and a 5%-of-bankroll better can hold the identical picks and finish the season in
different order, and one hot parlay can put a losing signal on top of the table.  So every
strategy is scored twice, on two different objects:

    SIGNAL   the picks only.  Did the number beat the close, and does it beat chance over n?
             Measured independently of stake size: hit rate, z against the break-even
             probability, bootstrap interval, and the luck decomposition.
    STAKING  the money only.  ROI, maximum drawdown, risk of ruin, and the same ROI under a
             deliberately different stake plan.  A staking run that cannot survive a change
             of stake plan is not a result.

A strategy can be **signal-positive and staking-negative** or the reverse, and the board
shows both columns.  Only a strategy that is positive on both, with a demotion gate that
can send it back to paper, is allowed to carry a live label.

The demotion gate (the owner's eighth requirement)
--------------------------------------------------
A live strategy is demoted to paper -- automatically, from published numbers, no judgement
call -- when ANY of these fires:

    D-01  signal decay   the rolling 30-ticket z falls below 0 for two consecutive windows
    D-02  staking break  realised drawdown exceeds the pre-registered cap
    D-03  price loss     mean CLV proxy turns negative for a full window
    D-04  drift          the live hit rate falls more than 2 standard errors below the
                         rate the strategy was promoted on

The gate is evaluated on every build, and its verdict is published even when it says
"demote".  A gate that cannot fail is not a gate.

No strategy here is live.  Eight candidates are scored; all eight are on paper, and the
board says why in the strategy's own row.  That is the correct output of a validation
system on its first run, not a failure of the system.
"""

from __future__ import annotations

import json
import math
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import (  # noqa: E402
    ROOT, SNAPSHOT, UPSTREAM_PIN, utcnow, write_json,
)

RNG = random.Random(20261114)      # fixed seed: the bootstrap is reproducible
N_BOOT = 2000
N_PERM = 2000
TEST_FROM, TEST_TO = 2015, 2026
BREAK_EVEN_DECIMAL = 1 + 100.0 / 110.0        # -110 both ways
BREAK_EVEN_PROB = 1.0 / BREAK_EVEN_DECIMAL
STAKE_UNIT = 1.0
DRAWDOWN_CAP = 0.25                            # 25% of bankroll, matches gate G5
DEMOTION_WINDOW = 30


# ------------------------------------------------------------------ settlement
def settle(edge: float) -> str:
    """W/L/P from a signed margin of the bet, using the registered settlement rule."""
    if abs(edge) < 1e-9:
        return "P"
    return "W" if edge > 0 else "L"


def american_to_decimal(odds: float | None) -> float:
    if odds is None:
        return 0.0
    if odds >= 100:
        return 1.0 + odds / 100.0
    return 1.0 + 100.0 / abs(odds)


def payout_decimal(b: dict) -> float:
    """Decimal return of one unit on this ticket.

    A single at -110 returns 1.909; a TWO-LEG parlay at -110 each returns 1.909^2 = 3.645
    (profit 2.645).  An earlier version of this file paid every ticket at single-leg odds,
    which understated the parlay's return by a factor of 1.9 and published a -40.7% ROI for a
    strategy whose hit rate was 3 points ABOVE its own break-even.  The price on the ticket
    is the compounded price, not the price of one leg.
    """
    if b.get("decimal_price"):
        return float(b["decimal_price"])
    if b.get("price") is not None:
        return american_to_decimal(b["price"])
    if b.get("legs"):
        return BREAK_EVEN_DECIMAL ** int(b["legs"])
    return BREAK_EVEN_DECIMAL


# ------------------------------------------------------------------ metrics
def bet_break_even(b: dict) -> float:
    """The probability a bet must win at to break even, *for that bet*.

    This is the correction that matters most on this page.  A flat 52.38% bar is only right
    for a -110 single.  A moneyline bet at +250 breaks even at 28.6%; a two-leg parlay at
    -110 each breaks even at 27.44%.  Testing every strategy against 52.38% made the parlay
    look catastrophically bad (z = -7.2 at a 30.4% hit rate that is actually ABOVE its own
    27.44% bar) and made the moneyline look worse than it was.  The bar is per ticket, and
    for a parlay it is the product of the legs' bars.
    """
    if b.get("break_even_prob") is not None:
        return float(b["break_even_prob"])
    d = american_to_decimal(b.get("price"))
    if d > 1.0:
        return 1.0 / d
    return BREAK_EVEN_PROB


def signal_metrics(bets: list[dict]) -> dict:
    n = len(bets)
    if n == 0:
        return {"n": 0}
    w = sum(1 for b in bets if b["outcome"] == "W")
    l = sum(1 for b in bets if b["outcome"] == "L")
    p = n - w - l
    decided = w + l
    hit = w / decided if decided else None
    bars = [bet_break_even(b) for b in bets if b["outcome"] in "WL"]
    expected = sum(bars) if bars else None
    # Poisson-binomial z: each ticket is its own Bernoulli with its own bar.  This is the
    # only correct test when the tickets carry different prices.
    if bars and expected is not None:
        var = sum(x * (1 - x) for x in bars)
        z = (w - expected) / math.sqrt(var) if var > 0 else None
        mean_bar = expected / len(bars)
        excess = (w - expected) / expected if expected else None
    else:
        z = mean_bar = excess = None
    # bootstrap CI on the hit rate (resample decided bets)
    decided_outcomes = [1 if b["outcome"] == "W" else 0 for b in bets if b["outcome"] in "WL"]
    ci = bootstrap_ci(decided_outcomes)
    # luck decomposition: drop the two game classes where variance dominates
    trimmed = [b for b in bets if b.get("margin_bucket") == "competitive"]
    if len(trimmed) < 10:
        trimmed = []
    tw = sum(1 for b in trimmed if b["outcome"] == "W")
    tl = sum(1 for b in trimmed if b["outcome"] == "L")
    t_hit = tw / (tw + tl) if (tw + tl) else None
    return {
        "n": n, "wins": w, "losses": l, "pushes": p, "decided": decided,
        "hit_rate": round(hit, 4) if hit is not None else None,
        "break_even_hit_rate": round(mean_bar, 4) if mean_bar is not None else None,
        "expected_wins_at_the_bar": round(expected, 2) if expected is not None else None,
        "actual_minus_expected_wins": round(w - expected, 2) if expected is not None else None,
        "z_vs_break_even": round(z, 3) if z is not None else None,
        "hit_rate_ci95": [round(ci[0], 4), round(ci[1], 4)] if ci else None,
        "ci_excludes_break_even": bool(ci and mean_bar is not None and ci[0] > mean_bar),
        "trimmed_n": len(trimmed),
        "trimmed_hit_rate": round(t_hit, 4) if t_hit is not None else None,
        "trimmed_note": ("too few competitive-margin tickets to decompose"
                         if not trimmed else "one-score and blowout games removed"),
        "trimmed_z": round((t_hit - mean_bar) / math.sqrt(t_hit * (1 - t_hit) / (tw + tl)), 3)
        if t_hit and 0 < t_hit < 1 and (tw + tl) and mean_bar else None,
        "signal_positive": bool(z is not None and z >= 1.96),
    }


def bootstrap_ci(outcomes: list[int], n_boot: int = N_BOOT, alpha: float = 0.05) -> tuple[float, float] | None:
    if len(outcomes) < 20:
        return None
    means = []
    k = len(outcomes)
    for _ in range(n_boot):
        s = 0
        for _ in range(k):
            s += outcomes[RNG.randrange(k)]
        means.append(s / k)
    means.sort()
    lo = means[int(alpha / 2 * n_boot)]
    hi = means[int((1 - alpha / 2) * n_boot) - 1]
    return lo, hi


def staking_metrics(bets: list[dict], stake_plan: str = "flat") -> dict:
    """ROI and drawdown under a named stake plan.  Two plans are computed for every strategy
    so a result that only exists under one of them is visible as such."""
    if not bets:
        return {"n": 0}
    bankroll = 100.0
    peak = bankroll
    max_dd = 0.0
    profit = 0.0
    for b in bets:
        if stake_plan == "flat":
            stake = STAKE_UNIT
        elif stake_plan == "pct":
            stake = 0.05 * bankroll
        elif stake_plan == "kelly_cap":
            stake = min(0.05 * bankroll, max(0.0, b.get("edge_pts", 0)) / 10.0 * bankroll)
        else:
            stake = STAKE_UNIT
        if b["outcome"] == "W":
            gain = stake * (payout_decimal(b) - 1.0)
        elif b["outcome"] == "L":
            gain = -stake
        else:
            gain = 0.0
        profit += gain
        if stake_plan != "flat":
            bankroll += gain
            peak = max(peak, bankroll)
            max_dd = max(max_dd, (peak - bankroll) / peak if peak > 0 else 0.0)
    staked = sum(STAKE_UNIT if stake_plan == "flat" else 0 for _ in bets) if stake_plan == "flat" else None
    roi = profit / staked if stake_plan == "flat" and staked else None
    if stake_plan != "flat":
        roi = profit / 100.0
    return {
        "plan": stake_plan,
        "profit_units": round(profit, 3),
        "roi": round(roi, 4) if roi is not None else None,
        "max_drawdown": round(max_dd, 4) if stake_plan != "flat" else None,
        "within_drawdown_cap": (max_dd <= DRAWDOWN_CAP) if stake_plan != "flat" else None,
    }


def rolling_demotion(bets: list[dict]) -> dict:
    """Evaluate the four demotion triggers on the ordered ticket list."""
    checks = []
    # D-01 signal decay: rolling 30-ticket hit rate z, two consecutive windows below 0
    wins, zs = [], []
    window = []
    bars_window = []
    for b in bets:
        if b["outcome"] not in "WL":
            continue
        window.append(1 if b["outcome"] == "W" else 0)
        bars_window.append(bet_break_even(b))
        if len(window) > DEMOTION_WINDOW:
            window.pop(0)
            bars_window.pop(0)
        if len(window) >= DEMOTION_WINDOW:
            h = sum(window) / len(window)
            bar = sum(bars_window) / len(bars_window)
            se = math.sqrt(h * (1 - h) / len(window)) if 0 < h < 1 else 0.0001
            zs.append((h - bar) / se)
    neg = [z for z in zs if z < 0]
    consecutive = 0
    for z in zs:
        consecutive = consecutive + 1 if z < 0 else 0
    d01 = consecutive >= 2
    checks.append({
        "id": "D-01", "name": "signal decay", "fires": d01,
        "detail": f"{consecutive} consecutive rolling {DEMOTION_WINDOW}-ticket windows with "
                  f"z < 0" + (f" ({len(neg)} of {len(zs)} windows negative)" if zs else ""),
    })

    # D-02 staking break: realised drawdown over the cap (5% stakes, compounded)
    st = staking_metrics(bets, "pct")
    d02 = bool(st.get("max_drawdown") is not None and st["max_drawdown"] > DRAWDOWN_CAP)
    checks.append({"id": "D-02", "name": "staking break", "fires": d02,
                   "detail": f"max drawdown {st.get('max_drawdown')} vs cap {DRAWDOWN_CAP}"})

    # D-03 price loss: the CLV proxy (fair - market) at settlement, last full window < 0
    tail = [b for b in bets if b.get("edge_pts") is not None][-DEMOTION_WINDOW:]
    clv = statistics.mean([-b["edge_pts"] for b in tail]) if tail else None
    d03 = bool(clv is not None and clv < 0)
    checks.append({"id": "D-03", "name": "price loss", "fires": d03,
                   "detail": f"mean CLV proxy over the last {len(tail)} tickets "
                             f"{round(clv, 3) if clv is not None else None} points"})

    # D-04 drift: live rate more than 2 SE below the promoted rate (break-even here)
    tail_hit = None
    t = [b for b in bets if b["outcome"] in "WL"][-100:]
    if t:
        th = sum(1 for b in t if b["outcome"] == "W") / len(t)
        bar_t = sum(bet_break_even(b) for b in t) / len(t)
        se = math.sqrt(bar_t * (1 - bar_t) / len(t))
        tail_hit = th
        d04 = (th - bar_t) < -2 * se
    else:
        d04 = False
    checks.append({"id": "D-04", "name": "drift", "fires": d04,
                   "detail": f"last {len(t)} decided tickets at "
                             f"{round(tail_hit, 4) if tail_hit is not None else None} vs the "
                             f"promotion bar for those same tickets"})

    return {"checks": checks, "demote": any(c["fires"] for c in checks)}


# ------------------------------------------------------------------ strategies
def build_bets(rows: list[dict]) -> dict[str, list[dict]]:
    """Turn the originated lines into tickets for each candidate strategy."""
    out: dict[str, list[dict]] = {}

    def final_rows():
        return [r for r in rows if r["status"] == "FINAL" and TEST_FROM <= r["season"] <= TEST_TO]

    # S-01 side model, threshold 1.0 point
    for thr in (0.5, 1.0, 2.0):
        key = f"S-01-side-{'%.1f' % thr}"
        bets = []
        for r in final_rows():
            if r["side_diff"] is None or abs(r["side_diff"]) < thr:
                continue
            back_home = r["side_diff"] < 0
            edge = (r["result_home_margin"] + r["market_side"]) * (1 if back_home else -1)
            bets.append({
                "game_id": r["game_id"], "season": r["season"], "week": r["week"],
                "market": "SIDE", "side": "home" if back_home else "away",
                "edge_pts": abs(r["side_diff"]), "price": None,
                "outcome": settle(edge), "margin_bucket": bucket(r["result_home_margin"]),
            })
        out[key] = bets

    # S-02 total model, threshold 1.0 point
    for thr in (1.0, 2.0):
        key = f"S-02-total-{'%.1f' % thr}"
        bets = []
        for r in final_rows():
            if r["total_diff"] is None or abs(r["total_diff"]) < thr:
                continue
            over = r["total_diff"] > 0
            edge = (r["result_total"] - r["market_total"]) * (1 if over else -1)
            bets.append({
                "game_id": r["game_id"], "season": r["season"], "week": r["week"],
                "market": "TOTAL", "side": "over" if over else "under",
                "edge_pts": abs(r["total_diff"]), "price": None,
                "outcome": settle(edge), "margin_bucket": "competitive",
            })
        out[key] = bets

    # S-03 moneyline: bet the side our probability likes against the published price
    key = "S-03-moneyline"
    bets = []
    for r in final_rows():
        if r["ml_prob_diff_pts"] is None or abs(r["ml_prob_diff_pts"]) < 3.0:
            continue
        back_home = r["ml_prob_diff_pts"] > 0
        price = r["market_ml_home"] if back_home else r["market_ml_away"]
        won = (r["result_home_margin"] > 0) if back_home else (r["result_home_margin"] < 0)
        outcome = "P" if r["result_home_margin"] == 0 else ("W" if won else "L")
        bets.append({
            "game_id": r["game_id"], "season": r["season"], "week": r["week"],
            "market": "MONEYLINE", "side": "home" if back_home else "away",
            "edge_pts": abs(r["ml_prob_diff_pts"]) / 10.0, "price": price,
            "outcome": outcome, "margin_bucket": bucket(r["result_home_margin"]),
        })
    out[key] = bets

    # S-04 two-leg parlay: the two largest side disagreements on the same card
    key = "S-04-parlay-2"
    by_week: dict[tuple[int, int], list[dict]] = {}
    for r in final_rows():
        if r["side_diff"] is None or r["fair_side"] is None:
            continue
        by_week.setdefault((r["season"], r["week"]), []).append(r)
    bets = []
    for wk, grp in sorted(by_week.items()):
        grp = sorted(grp, key=lambda r: -abs(r["side_diff"]))[:2]
        if len(grp) < 2:
            continue
        legs = []
        for r in grp:
            back_home = r["side_diff"] < 0
            edge = (r["result_home_margin"] + r["market_side"]) * (1 if back_home else -1)
            legs.append(settle(edge))
        outcome = "L" if "L" in legs else ("P" if "P" in legs else "W")
        bets.append({
            "game_id": "+".join(r["game_id"] for r in grp),
            "season": wk[0], "week": wk[1], "market": "PARLAY_2", "side": "both",
            "edge_pts": sum(abs(r["side_diff"]) for r in grp) / 2, "price": None,
            "break_even_prob": BREAK_EVEN_PROB ** 2,
            "legs": 2,
            "decimal_price": BREAK_EVEN_DECIMAL ** 2,
            "outcome": outcome,
            # A parlay is variance-dominated if ANY leg is: one bounce in one leg decides
            # the ticket.  An earlier version required ALL legs to be competitive, which put
            # 195 of 234 tickets in "other" and left the luck decomposition measuring almost
            # nothing (trimmed n = 39).
            "margin_bucket": ("variance_dominated"
                              if any(bucket(r["result_home_margin"]) == "variance_dominated"
                                     for r in grp) else "competitive"),
        })
    out[key] = bets

    # S-05 prop combos: cannot be computed here -- no prop prices or prop outcomes are
    # reachable from this sandbox.  Published empty with the reason, never simulated.
    out["S-05-prop-combo"] = []
    return out


def bucket(margin: float | None) -> str:
    """Luck decomposition buckets: one-score games (<=8) and blowouts (>=25) are where a
    single bounce decides the ticket.  Removing them is the luck test, not a filter for
    good results."""
    if margin is None:
        return "other"
    if abs(margin) <= 8 or abs(margin) >= 25:
        return "variance_dominated"
    return "competitive"


CATALOGUE = [
    {"id": "S-01-side-0.5", "name": "Side model, 0.5-pt threshold", "division": "singles",
     "shape": "single", "market": "SIDE",
     "hypothesis": "When our originated spread differs from the market by at least half a "
                   "point, we hold an advantage the price does not reflect.",
     "falsifier": "Hit rate at -110 is not above the 52.38% break-even over the test window."},
    {"id": "S-01-side-1.0", "name": "Side model, 1-pt threshold", "division": "singles",
     "shape": "single", "market": "SIDE",
     "hypothesis": "A full-point disagreement is large enough to survive the vig.",
     "falsifier": "Hit rate at -110 is not above the break-even over the test window."},
    {"id": "S-01-side-2.0", "name": "Side model, 2-pt threshold", "division": "singles",
     "shape": "single", "market": "SIDE",
     "hypothesis": "Selecting only large disagreements raises the hit rate enough to pay the vig.",
     "falsifier": "Larger threshold does not raise the hit rate above break-even."},
    {"id": "S-02-total-1.0", "name": "Total model, 1-pt threshold", "division": "singles",
     "shape": "single", "market": "TOTAL",
     "hypothesis": "The total model's disagreements with the market total are informative.",
     "falsifier": "Hit rate at -110 is not above break-even over the test window."},
    {"id": "S-02-total-2.0", "name": "Total model, 2-pt threshold", "division": "singles",
     "shape": "single", "market": "TOTAL",
     "hypothesis": "Only large total disagreements carry information.",
     "falsifier": "Hit rate at -110 is not above break-even over the test window."},
    {"id": "S-03-moneyline", "name": "Moneyline value", "division": "singles",
     "shape": "single", "market": "MONEYLINE",
     "hypothesis": "Where our win probability beats the published price by 3 points, the price "
                   "is wrong.",
     "falsifier": "ROI at the published price does not exceed zero with a CI excluding it."},
    {"id": "S-04-parlay-2", "name": "Two-leg side parlay", "division": "parlays_2_3",
     "shape": "parlay", "market": "PARLAY_2",
     "hypothesis": "The two biggest disagreements on a card are independent enough that the "
                   "parlay's true probability beats the product the book charges for.",
     "falsifier": "Realised parlay hit rate is not above the compounded break-even "
                  "(52.38%^2 = 27.44%) after correlation adjustment."},
    {"id": "S-05-prop-combo", "name": "Player-prop combo", "division": "prop_combos_samegame",
     "shape": "prop_combo", "market": "PROP",
     "hypothesis": "NOT TESTED: no prop price and no prop outcome is reachable from this "
                   "environment, so no claim is made in either direction.",
     "falsifier": "n/a until a prop feed exists -- publishing a result here would be a "
                  "simulation presented as evidence."},
]


def main() -> int:
    with open(os.path.join(ROOT, "data", "lab", "lines", "fair_lines.json"), encoding="utf-8") as fh:
        rows = json.load(fh)["rows"]

    per_strategy = build_bets(rows)
    board = []
    for cat in CATALOGUE:
        bets = per_strategy.get(cat["id"], [])
        sm = signal_metrics(bets)
        st = staking_metrics(bets, "flat")
        st_pct = staking_metrics(bets, "pct")
        dem = rolling_demotion(bets) if bets else {
            "checks": [], "demote": True,
            "why": "no tickets: a strategy with no evidence cannot be live",
        }
        gates = evaluate_gates(sm, st, st_pct, bets)
        passed = sum(1 for g in gates if g["passed"] is True)
        failed = [g["id"] for g in gates if g["passed"] is False]
        blocked = [g["id"] for g in gates if g["passed"] is None]
        live = bool(len(failed) == 0 and not blocked and not dem["demote"] and sm.get("n", 0) > 0)
        board.append({
            "id": cat["id"], "name": cat["name"], "division": cat["division"],
            "shape": cat["shape"], "market": cat["market"],
            "hypothesis": cat["hypothesis"], "falsifier": cat["falsifier"],
            "signal": sm,
            "staking_flat": st,
            "staking_pct": st_pct,
            "staking_independent": (
                "holds" if (st.get("roi") is not None and st_pct.get("roi") is not None and
                            (st["roi"] > 0) == (st_pct["roi"] > 0))
                else ("breaks under a 5%-of-bankroll plan" if st.get("roi") is not None
                      and st_pct.get("roi") is not None else "no evidence")
            ),
            "gates": gates,
            "gates_passed": passed, "gates_failed": failed, "gates_blocked": blocked,
            "demotion": dem,
            "ticket_games": sorted({b["game_id"].split("+")[0] for b in bets}),
            "status": "live" if live else ("paper" if sm.get("n", 0) else "untested"),
            "status_reason": (
                "passes every gate that can be evaluated" if live else
                (f"blocked on {', '.join(blocked)}; failed {', '.join(failed)}" if blocked or failed
                 else "no tickets")
            ),
        })

    # rank: signal first, then staking.  This is the owner's requirement made mechanical.
    def rank_key(r):
        z = r["signal"].get("z_vs_break_even")
        roi = r["staking_flat"].get("roi")
        return (-(z if z is not None else -99), -(roi if roi is not None else -99))
    board.sort(key=rank_key)
    for i, r in enumerate(board, 1):
        r["rank"] = i

    summary = {
        "generated_at": utcnow(), "snapshot": SNAPSHOT,
        "upstream": {k: UPSTREAM_PIN[k] for k in ("repo", "retrieved_at", "publisher")},
        "test_window": {"from": TEST_FROM, "to": TEST_TO},
        "rule": {
            "ranking": "signal z first, ROI second. A strategy with a positive ROI and a "
                       "negative z is ranked below a strategy with a better z and a worse ROI, "
                       "because the ROI of a losing signal is a staking artefact.",
            "staking_independence": "every strategy is re-priced under a 5%-of-bankroll "
                                    "compounding plan; a profit that survives only the flat "
                                    "plan is labelled as such",
            "demotion": "D-01..D-04, evaluated on every build; any one firing sends the "
                        "strategy to paper",
        },
        "counts": {
            "strategies": len(board),
            "live": sum(1 for r in board if r["status"] == "live"),
            "paper": sum(1 for r in board if r["status"] == "paper"),
            "untested": sum(1 for r in board if r["status"] == "untested"),
            "signal_positive": sum(1 for r in board if r["signal"].get("signal_positive")),
            "staking_positive": sum(1 for r in board if (r["staking_flat"].get("roi") or 0) > 0),
        },
        "finding": None,
        "defects_found_in_this_build": [
            {"id": "B-01", "severity": "high",
             "was": "every strategy was tested against a flat 52.38% break-even",
             "effect": "the two-leg parlay's 30.4% hit rate was scored z = -7.2 although it is "
                       "3 points ABOVE its own 27.44% bar; the moneyline's 34.7% was scored "
                       "z = -19.4 against a bar that applies to no moneyline ticket",
             "fixed_in": "Poisson-binomial test: each ticket carries its own break-even, the "
                         "sum of those bars is the expectation, and the z is computed against "
                         "the sum of the per-ticket variances",
             "caught_by": "reading the row: a z of -7 with a hit rate near break-even is not "
                          "a losing strategy, it is a wrong test"},
            {"id": "B-02", "severity": "high",
             "was": "parlay wins were paid at single-leg -110 odds",
             "effect": "published ROI -40.7% for a strategy that is actually +10.5%",
             "fixed_in": "payout_decimal() compounds the legs' prices (1.909^2 = 3.645)",
             "caught_by": "the same row, after B-01 was fixed: a hit rate above its own bar "
                          "cannot produce a -40% ROI"},
            {"id": "B-03", "severity": "medium",
             "was": "the leaderboard ranked on ROI alone in an early draft",
             "effect": "the parlay, with the weakest signal on the board (z = 1.00), ranked "
                       "first",
             "fixed_in": "rank = (signal z desc, ROI desc); the ROI is shown but never ranks",
             "caught_by": "applying the owner's requirement literally"},
            {"id": "B-04", "severity": "medium",
             "was": "a parlay was bucketed 'competitive' only if EVERY leg was a competitive "
                    "margin, and other strategies were bucketed on their single game's margin",
             "effect": "one bounce in one leg decides the ticket, so 195 of 234 parlay tickets "
                       "landed in 'other' and the luck decomposition had n = 39, too small to "
                       "decompose anything",
             "fixed_in": "a parlay is variance-dominated if ANY leg is; a decomposition with "
                         "fewer than 10 tickets is published as 'too few' rather than computed"},
        ],
    }
    pos_roi = [r for r in board if (r["staking_flat"].get("roi") or 0) > 0]
    pos_sig = [r for r in board if r["signal"].get("signal_positive")]
    if pos_roi and not pos_sig:
        summary["finding"] = (
            f"{len(pos_roi)} strategies show a positive ROI but none has a signal that clears "
            "the 1.96 z bar. On its own, that ROI would have topped a naive leaderboard. This "
            "is exactly the failure mode the split exists to catch: the money was a staking "
            "run, not a signal.")
    elif not pos_roi:
        summary["finding"] = (
            "No strategy shows a positive ROI and none clears the signal bar. The board is "
            "empty of live entries, which is the correct state for a first validation run: "
            "the value delivered this round is the machinery, not a pick.")
    write_json("data/lab/leaderboard.json", {
        "generated_at": utcnow(), "snapshot": SNAPSHOT,
        "columns_note": "signal_* = picks only, independent of stake size; staking_* = money "
                        "only, under a named stake plan; gates_* = the validation gates; "
                        "demotion = the gate that sends a live strategy back to paper",
        "summary": summary,
        "rows": board,
    })

    print(f"strategies: {len(board)}")
    for r in board:
        s = r["signal"]
        print(f"  #{r['rank']} {r['id']:18s} n={s.get('n',0):5d} hit={s.get('hit_rate')} "
              f"z={s.get('z_vs_break_even')} roi={r['staking_flat'].get('roi')} "
              f"status={r['status']} demote={r['demotion']['demote']}")
    print(f"  live={summary['counts']['live']} paper={summary['counts']['paper']} "
          f"untested={summary['counts']['untested']}")
    if summary["finding"]:
        print(f"  FINDING: {summary['finding']}")
    return 0


def evaluate_gates(sm: dict, st: dict, st_pct: dict, bets: list[dict]) -> list[dict]:
    """The eight registered gates (G0-G7) plus the demotion gate, evaluated as far as the
    evidence allows.  `passed: null` means the gate cannot be evaluated -- published as
    blocked, never as a pass."""
    n = sm.get("n", 0)
    z = sm.get("z_vs_break_even")
    roi = st.get("roi")
    ci = sm.get("hit_rate_ci95")
    return [
        {"id": "G0", "name": "Provenance", "passed": None,
         "why": "the market benchmark is a publisher composite with no named book or "
                "timestamp (price-store defects P-04, P-05); the inputs are sourced but the "
                "benchmark is not a market anyone can bet into"},
        {"id": "G1", "name": "Sample size", "passed": n >= 500 if n else False,
         "why": f"n={n} against the 500-ticket bar for singles"},
        {"id": "G2", "name": "Skill above variance", "passed": bool(z is not None and z >= 1.96),
         "why": f"z={z} against 1.96; bootstrap 95% interval {ci}"},
        {"id": "G3", "name": "Calibration", "passed": None,
         "why": "calibration is measured at the model level (model_report.json: Brier "
                "0.241 vs market 0.212), not yet per strategy"},
        {"id": "G4", "name": "Robustness", "passed": None,
         "why": "leave-one-team-out and window-halves are not run per strategy in this build"},
        {"id": "G5", "name": "Risk of ruin", "passed": st_pct.get("within_drawdown_cap"),
         "why": f"max drawdown {st_pct.get('max_drawdown')} vs cap {DRAWDOWN_CAP}"},
        {"id": "G6", "name": "Economic reality", "passed": None,
         "why": "ROI is computed at a flat -110 because no priced market exists for these "
                "selections; no executable price is recorded"},
        {"id": "G7", "name": "Correlation discipline", "passed":
            None if len(bets) == 0 else
            (True if not any(b["market"] in ("PARLAY_2", "PROP") for b in bets) else None),
         "why": "singles do not compound correlation; the two-leg parlay is blocked until a "
                "correlation interval is measured on officially sourced numbers"},
    ]


if __name__ == "__main__":
    raise SystemExit(main())
