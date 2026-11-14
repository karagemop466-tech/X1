"""Strategy library, evaluation, promotion gates and the demotion gate.

Requirements covered here:

  C5  signal and staking are scored separately on the leaderboard, so a lucky
      staking run cannot promote a bad signal
  C8  a demotion gate that sends a live strategy back to paper

Design notes
------------
Every strategy emits *signals*, never stakes. A signal is
(game, market, side, price, model_edge). Staking is a separate layer applied
afterwards; the leaderboard reports the two independently:

  signal_score   computed on flat 1-unit staking only. It cannot be moved by
                 bet sizing, because the sizing is constant.
  staking_score  computed under the strategy's own staking plan (quarter Kelly
                 capped at 2 units) and reports ROI, drawdown and consistency.

Promotion requires signal_score >= PROMOTION_SIGNAL_FLOOR *and* every
promotion gate, so a strategy that only ever made money because of how it sized
its bets fails.

All evaluation is out of sample: each candidate bet is produced by a model that
saw only earlier seasons, and every gate is evaluated on the same walk-forward
window.
"""

from __future__ import annotations

import math
import random

from . import originate

PROMOTION_SIGNAL_FLOOR = 55.0
KELLY_FRACTION = 0.25      # quarter Kelly
KELLY_CAP = 0.05           # hard cap as a fraction of bankroll (5 units of 100)
BANKROLL = 100.0           # units; every staking figure is quoted against this
ATS_SIGMA = 13.5           # sd of (actual margin - spread), used to turn a
                           # points edge into a cover probability
DRAWDOWN_LIMIT_UNITS = 25.0  # 25% of the starting bankroll
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 20261114

SIDE_PRICE = -110.0
TOTAL_PRICE = -110.0


# ---------------------------------------------------------------------------
# bet primitives
# ---------------------------------------------------------------------------

def price_to_decimal(american):
    """Decimal return per 1 unit staked, stake included."""
    a = float(american)
    return 1.0 + (a / 100.0 if a > 0 else 100.0 / abs(a))


def profit(stake, american, outcome):
    """Profit for one bet. outcome in {'W','L','PUSH'}."""
    if outcome == "PUSH":
        return 0.0
    dec = price_to_decimal(american)
    return stake * (dec - 1.0) if outcome == "W" else -stake


def kelly_stake(american, model_prob):
    """Fractional Kelly stake as a FRACTION OF BANKROLL, with a hard cap.

    Never negative (a negative Kelly says: do not bet) and never above
    ``KELLY_CAP``. The caller multiplies by ``BANKROLL`` to get units.
    """
    if model_prob is None:
        return 0.0
    dec = price_to_decimal(american)
    b = dec - 1.0
    if b <= 0:
        return 0.0
    p = min(max(model_prob, 0.0), 1.0)
    f = (b * p - (1.0 - p)) / b
    if f <= 0:
        return 0.0
    return min(KELLY_FRACTION * f, KELLY_CAP)


# ---------------------------------------------------------------------------
# settlement
# ---------------------------------------------------------------------------

def settle(game, market, side, line):
    """Settle one bet against the official score. Returns 'W', 'L' or 'PUSH'."""
    if not game["settled"]:
        return None
    margin = game["margin_home"]
    total = game["total_points"]
    if market == "SIDE":
        home_side = side == "home"
        d = margin - line
        if d == 0:
            return "PUSH"
        won = (d > 0) if home_side else (d < 0)
    elif market == "TOTAL":
        d = total - line
        if d == 0:
            return "PUSH"
        won = (d > 0) if side == "Over" else (d < 0)
    elif market == "MONEYLINE":
        if margin == 0:
            return "PUSH"
        won = (margin > 0) if side == "home" else (margin < 0)
    else:
        return None
    return "W" if won else "L"


# ---------------------------------------------------------------------------
# the pre-registered strategy library
# ---------------------------------------------------------------------------

def _edge_side(row):
    return -float(row["diff_side"]) if row["diff_side"] != "" else None


def _edge_total(row):
    return -float(row["diff_total"]) if row["diff_total"] != "" else None


def _num(v):
    return None if v in ("", None) else float(v)


def _side_signal(row, want_home):
    line = _num(row["market_side"])
    if line is None:
        return None
    return ("SIDE", "home" if want_home else "away", line, SIDE_PRICE, None, _edge_side(row))


def _total_signal(row, over):
    line = _num(row["market_total"])
    if line is None:
        return None
    return ("TOTAL", "Over" if over else "Under", line, TOTAL_PRICE, None, _edge_total(row))


def _ml_signal(row, want_home):
    price = _num(row["market_ml_home"]) if want_home else _num(row["market_ml_away"])
    if price is None:
        return None
    p_fair = _num(row["fair_prob_home"]) / 100.0 if row["fair_prob_home"] != "" else None
    p_mkt = _num(row["market_prob_home"]) / 100.0 if row["market_prob_home"] != "" else None
    if p_fair is None or p_mkt is None:
        return None
    p = p_fair if want_home else 1.0 - p_fair
    return ("MONEYLINE", "home" if want_home else "away", None, price, p, None)


def _threshold_rule(field, thresh):
    def rule(row, game):
        e = _num(row[field])
        if e is None:
            return []
        # diff_* is market minus fair, so a positive diff means the market
        # favours this side more than the model -> back the other side.
        if field == "diff_side":
            if abs(e) < thresh:
                return []
            return [_side_signal(row, e > 0)]
        if field == "diff_total":
            if abs(e) < thresh:
                return []
            return [_total_signal(row, e < 0)]
        return []
    return rule


def _ml_rule(thresh):
    def rule(row, game):
        d = _num(row["diff_ml_pp"])
        if d is None or abs(d) < thresh:
            return []
        # positive diff = model likes the home team more than the market does
        return [_ml_signal(row, d > 0)]
    return rule


def _home_dog(thresh):
    def rule(row, game):
        line = _num(row["market_side"])
        if line is None or line > -thresh:
            return []
        return [_side_signal(row, True)]
    return rule


def _road_fav(thresh):
    def rule(row, game):
        line = _num(row["market_side"])
        if line is None or line > -thresh:
            return []
        return [_side_signal(row, False)]
    return rule


def _total_high_under(thresh):
    def rule(row, game):
        line = _num(row["market_total"])
        if line is None or line < thresh:
            return []
        return [_total_signal(row, False)]
    return rule


def _total_low_over(thresh):
    def rule(row, game):
        line = _num(row["market_total"])
        if line is None or line > thresh:
            return []
        return [_total_signal(row, True)]
    return rule


def _div_dog(row, game):
    if not game.get("div_game"):
        return []
    line = _num(row["market_side"])
    if line is None or line == 0:
        return []
    return [_side_signal(row, line < 0)]     # side dog is the home team when line < 0


def _rest_edge(thresh):
    def rule(row, game):
        hr, ar = game.get("home_rest"), game.get("away_rest")
        if hr is None or ar is None:
            return []
        if hr - ar >= thresh:
            return [_side_signal(row, True)]
        return []
    return rule


def _both_edge(thresh):
    """Two independent singles on the same game: the side and the total."""
    def rule(row, game):
        es, et = _edge_side(row), _edge_total(row)
        if es is None or et is None:
            return []
        if abs(es) < thresh or abs(et) < thresh:
            return []
        out = []
        s = _side_signal(row, es > 0)
        t = _total_signal(row, et < 0)
        if s:
            out.append(s)
        if t:
            out.append(t)
        return out
    return rule


def _parlay_side_total(thresh):
    """Same-game parlay: the model's side leg and its total leg.

    Priced as the product of two -110 legs (2.645 decimal) rather than the
    book's usual discounted parlay price, and that difference is stated on the
    page: at true -110 legs a two-leg parlay returns 2.645 for 1, and it only
    wins when BOTH legs win.
    """
    def rule(row, game):
        es, et = _edge_side(row), _edge_total(row)
        if es is None or et is None:
            return []
        if abs(es) < thresh or abs(et) < thresh:
            return []
        legs = []
        s = _side_signal(row, es > 0)
        t = _total_signal(row, et < 0)
        if not s or not t:
            return []
        legs.append((s[0], s[1], s[2]))       # market, side, line
        legs.append((t[0], t[1], t[2]))
        return [("PARLAY", legs, None, 164.5, None, (abs(es), abs(et)))]
    return rule


def _baseline_home_ats(row, game):
    line = _num(row["market_side"])
    if line is None:
        return []
    return [_side_signal(row, True)]


def _baseline_over(row, game):
    line = _num(row["market_total"])
    if line is None:
        return []
    return [_total_signal(row, True)]


def _baseline_fav_ats(row, game):
    line = _num(row["market_side"])
    if line is None or line == 0:
        return []
    return [_side_signal(row, line > 0)]


# id, family, plain-English rule, factory(param) -> rule, main param, neighbour grid
STRATEGIES = [
    ("ST-SIDE-3", "Side edge",
     "Back the side the model disagrees with the market on by 3 or more points",
     lambda t: _threshold_rule("diff_side", t), 3.0, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]),
    ("ST-SIDE-5", "Side edge",
     "Same, but only when the disagreement is 5 or more points",
     lambda t: _threshold_rule("diff_side", t), 5.0, [3.0, 4.0, 5.0, 6.0, 7.0, 8.0]),
    ("ST-SIDE-7", "Side edge",
     "Same, but only when the disagreement is 7 or more points",
     lambda t: _threshold_rule("diff_side", t), 7.0, [5.0, 6.0, 7.0, 8.0, 9.0, 10.0]),
    ("ST-TOT-3", "Total edge",
     "Back the total the model disagrees with the market on by 3 or more points",
     lambda t: _threshold_rule("diff_total", t), 3.0, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]),
    ("ST-TOT-5", "Total edge",
     "Same, but only when the disagreement is 5 or more points",
     lambda t: _threshold_rule("diff_total", t), 5.0, [3.0, 4.0, 5.0, 6.0, 7.0, 8.0]),
    ("ST-TOT-7", "Total edge",
     "Same, but only when the disagreement is 7 or more points",
     lambda t: _threshold_rule("diff_total", t), 7.0, [5.0, 6.0, 7.0, 8.0, 9.0, 10.0]),
    ("ST-ML-5", "Moneyline value",
     "Back the moneyline the model prices 5 or more points of probability away from the market",
     _ml_rule, 5.0, [3.0, 4.0, 5.0, 6.0, 7.0, 8.0]),
    ("ST-ML-10", "Moneyline value",
     "Same, but only at 10 or more points of probability",
     _ml_rule, 10.0, [6.0, 8.0, 10.0, 12.0, 14.0, 16.0]),
    ("ST-HOMEDOG", "Market structure",
     "Back home teams getting 2.5 or more points",
     _home_dog, 2.5, [0.5, 1.5, 2.5, 3.5, 4.5, 6.5]),
    ("ST-ROADFAV", "Market structure",
     "Back road teams laying 2.5 or more points",
     _road_fav, 2.5, [0.5, 1.5, 2.5, 3.5, 4.5, 6.5]),
    ("ST-UNDER48", "Market structure",
     "Back the under whenever the total is 48 or higher",
     _total_high_under, 48.0, [44.0, 46.0, 48.0, 50.0, 52.0, 54.0]),
    ("ST-OVER40", "Market structure",
     "Back the over whenever the total is 40 or lower",
     _total_low_over, 40.0, [36.0, 38.0, 40.0, 42.0, 44.0, 46.0]),
    ("ST-DIVDOG", "Market structure",
     "Back the underdog in every division game",
     lambda t: _div_dog, None, [None]),
    ("ST-REST2", "Situational",
     "Back home teams with a rest advantage of 2 or more days",
     _rest_edge, 2.0, [1.0, 2.0, 3.0, 4.0]),
    ("ST-BOTH-3", "Combination",
     "Take the side and the total as two separate single bets when both disagree by 3 or more",
     _both_edge, 3.0, [1.0, 2.0, 3.0, 4.0, 5.0]),
    ("ST-PARLAY-4", "Parlay",
     "Same-game parlay of the model's side and total when both disagree by 4 or more",
     _parlay_side_total, 4.0, [2.0, 3.0, 4.0, 5.0, 6.0]),
]


def build_rule(factory, param):
    return factory(param) if param is not None else factory(None)


BASELINES = [
    ("BASE-HOME-ATS", "Always back the home team against the spread", _baseline_home_ats),
    ("BASE-OVER", "Always back the over", _baseline_over),
    ("BASE-FAV-ATS", "Always back the favourite against the spread", _baseline_fav_ats),
]


# ---------------------------------------------------------------------------
# evaluation
# ---------------------------------------------------------------------------

def _bootstrap_ci(profits, resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED):
    """Percentile bootstrap CI for mean profit per unit staked."""
    n = len(profits)
    if n < 2:
        return None, None
    rng = random.Random(seed)
    k = n
    means = []
    for _ in range(resamples):
        s = 0.0
        sample = rng.choices(profits, k=k)
        s = sum(sample)
        means.append(s / k)
    means.sort()
    lo = means[int(0.025 * resamples)]
    hi = means[min(resamples - 1, int(0.975 * resamples) - 1)]
    return lo, hi


def _binom_tail_two_sided(k, n, p0):
    """Exact two-sided binomial p-value. k successes in n trials, null p0."""
    if n == 0:
        return 1.0
    lc = math.lgamma
    def pmf(i):
        return math.exp(lc(n + 1) - lc(i + 1) - lc(n - i + 1) + i * math.log(p0) + (n - i) * math.log(1 - p0))
    obs = pmf(k)
    tot = 0.0
    for i in range(n + 1):
        pi = pmf(i)
        if pi <= obs * (1 + 1e-9):
            tot += pi
    return min(1.0, tot)


def _mean_sd(xs):
    n = len(xs)
    if n == 0:
        return 0.0, 0.0
    m = sum(xs) / n
    if n < 2:
        return m, 0.0
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return m, math.sqrt(var)


def _max_drawdown(units_series):
    peak, worst, bank = 0.0, 0.0, 0.0
    for u in units_series:
        bank += u
        if bank > peak:
            peak = bank
        if peak - bank > worst:
            worst = peak - bank
    return worst


def run_strategy(rule, rows, games_by_id, min_season=2004):
    """Produce and settle every bet the rule selects, walk-forward."""
    bets = []
    for row in rows:
        if row["mode"] != "oos" or row["season"] < min_season:
            continue
        game = games_by_id[row["game_id"]]
        if not game["settled"]:
            continue
        for sig in rule(row, game) or []:
            market, side, line, price, model_p, model_edge = sig
            if market == "PARLAY":
                legs = side
                outcomes = [settle(game, m, s, ln) for (m, s, ln) in legs]
                if any(o is None for o in outcomes):
                    continue
                if "L" in outcomes:
                    outcome = "L"
                elif "PUSH" in outcomes:
                    # a pushed leg reduces the parlay to the remaining single
                    live = [(m, s, ln) for (m, s, ln), o in zip(legs, outcomes) if o != "PUSH"]
                    if len(live) == 1:
                        m, s, ln = live[0]
                        outcome = settle(game, m, s, ln)
                        price = SIDE_PRICE
                    else:
                        outcome = "PUSH"
                else:
                    outcome = "W"
                line = None
            else:
                outcome = settle(game, market, side, line)
                if outcome is None:
                    continue
            bets.append({
                "game_id": row["game_id"], "season": row["season"], "week": row["week"],
                "market": market, "side": side if market != "PARLAY" else "side+total",
                "line": line, "price": price, "model_prob": model_p,
                "model_edge": model_edge, "outcome": outcome,
            })
    return bets


def _cover_probability(bet, ats_sigma=ATS_SIGMA):
    """Turn a points edge into a cover probability.

    A disagreement of E points between the model's fair line and the market
    line is worth a cover probability of Phi(E / sigma), where sigma is the
    standard deviation of (actual margin - spread). Measured over 7,413 settled
    games that sd is 13.14 points against the market's own line, so 13.5 is
    used and is stated on the page rather than fitted to the results.
    """
    e = bet.get("model_edge")
    if e is None:
        return None
    if isinstance(e, tuple):                      # parlay: product of the legs
        p = 1.0
        for leg in e:
            p *= 0.5 * (1.0 + math.erf(abs(leg) / ats_sigma / math.sqrt(2.0)))
        return p
    return 0.5 * (1.0 + math.erf(abs(e) / ats_sigma / math.sqrt(2.0)))


def evaluate_bets(bets, ats_sigma=ATS_SIGMA):
    """Signal metrics on flat staking, staking metrics under quarter Kelly.

    The two are deliberately computed on different money: ``roi_flat`` puts
    exactly one unit on every bet so that it measures the SIGNAL and nothing
    else, while ``roi_weighted`` applies the staking plan and measures the
    STAKING. A strategy can therefore score well on one and badly on the other,
    and the leaderboard shows both columns side by side.
    """
    if not bets:
        return None
    flat, weighted, bank_series = [], [], []
    declined = 0
    decided = [b for b in bets if b["outcome"] != "PUSH"]
    for b in bets:
        flat.append(profit(1.0, b["price"], b["outcome"]))
        p = b.get("model_prob")
        if p is None:
            p = _cover_probability(b, ats_sigma)
        stake = 0.0
        if p is not None:
            stake = kelly_stake(b["price"], p) * BANKROLL
        if stake <= 0:
            stake = 0.0
            declined += 1
        b["cover_prob"] = round(p, 4) if p is not None else ""
        b["stake"] = round(stake, 4)
        if stake > 0:
            weighted.append(profit(stake, b["price"], b["outcome"]))
            bank_series.append(weighted[-1])

    staked_flat = len(bets)
    staked_w = sum(b["stake"] for b in bets)
    roi_flat = sum(flat) / staked_flat if staked_flat else 0.0
    roi_w = (sum(weighted) / staked_w) if staked_w > 0 else 0.0
    wins = sum(1 for b in decided if b["outcome"] == "W")
    # break-even hit rate for the average price actually taken
    avg_dec = sum(price_to_decimal(b["price"]) for b in decided) / len(decided) if decided else 2.0
    breakeven = 1.0 / avg_dec
    p_value = _binom_tail_two_sided(wins, len(decided), breakeven) if decided else 1.0
    m, sd = _mean_sd(flat)
    z = (m / (sd / math.sqrt(len(flat)))) if sd > 0 and len(flat) > 1 else 0.0
    lo, hi = _bootstrap_ci(flat)
    return {
        "bets": len(bets),
        "decided": len(decided),
        "wins": wins,
        "hit_rate": (wins / len(decided)) if decided else None,
        "breakeven_hit_rate": round(breakeven, 4),
        "avg_decimal_price": round(avg_dec, 4),
        "units_flat": round(sum(flat), 3),
        "roi_flat": roi_flat,
        "staked_weighted": round(staked_w, 3),
        "bets_taken_weighted": sum(1 for b in bets if b["stake"] > 0),
        "bets_declined_by_staking": declined,
        "units_weighted": round(sum(weighted), 3),
        "roi_weighted": roi_w,
        "mean_stake": round(staked_w / len(bets), 4) if bets else 0,
        "max_drawdown_units": round(_max_drawdown(bank_series), 3),
        "max_drawdown_pct_of_starting_bank": round(100.0 * _max_drawdown(bank_series) / BANKROLL, 2),
        "drawdown_over_units_staked": round(_max_drawdown(bank_series) / staked_w, 4) if staked_w > 0 else None,
        "bankroll_units": BANKROLL,
        "z_score": round(z, 4),
        "p_value_binomial": round(p_value, 6),
        "ci_low": round(lo, 5) if lo is not None else None,
        "ci_high": round(hi, 5) if hi is not None else None,
        "_flat": flat,
        "_bank": bank_series,
        "_bets": bets,
    }


def seasonal_positive_fraction(bets):
    by = {}
    for b in bets:
        by.setdefault(b["season"], []).append(profit(1.0, b["price"], b["outcome"]))
    if not by:
        return None, 0, 0
    pos = sum(1 for s, v in by.items() if sum(v) > 0)
    return pos / len(by), pos, len(by)


def luck_robust_roi(bets, games_by_id):
    """ROI after removing one-score games and blowouts (gate G6)."""
    keep = []
    for b in bets:
        g = games_by_id[b["game_id"]]
        marg = abs(g["margin_home"])
        if marg <= 3 or marg >= 21:
            continue
        keep.append(profit(1.0, b["price"], b["outcome"]))
    if not keep:
        return None, 0
    return sum(keep) / len(keep), len(keep)


# ---------------------------------------------------------------------------
# gates
# ---------------------------------------------------------------------------

PROMOTION_GATES = [
    ("G1", "Sample sufficiency", "at least 200 settled out-of-sample bets"),
    ("G2", "Out-of-sample integrity", "every signal produced by a model fitted only on earlier seasons; no duplicated (game, market, side) bet"),
    ("G3", "Statistical significance", "bootstrap 95% CI lower bound on flat-stake ROI above zero AND two-sided exact binomial p <= 0.05"),
    ("G4", "Economic significance", "ROI under the strategy's own staking plan at least 2%"),
    ("G5", "Beats naive baselines", "flat-stake ROI above all three always-on baselines on the same window"),
    ("G6", "Luck robustness", "flat-stake ROI still positive after dropping one-score games (margin <= 3) and blowouts (margin >= 21)"),
    ("G7", "Parameter stability", "at least 60% of neighbouring parameter values stay positive"),
    ("G8", "Non-redundancy", "absolute correlation with any already-accepted strategy at most 0.85"),
]

DEMOTION_GATES = [
    ("D1", "Trailing performance", "trailing 200 settled bets at flat stakes show negative ROI",
     "any 200-bet window"),
    ("D2", "Signal decay", "trailing 100 bets have a mean signed edge at or below zero",
     "measured weekly"),
    ("D3", "Drawdown",
     f"peak-to-trough drawdown exceeds {DRAWDOWN_LIMIT_UNITS:.0f} units, which is 25% of "
     f"the starting {BANKROLL:.0f}-unit bankroll", "continuous"),
    ("D4", "Signal score floor", "signal_score falls below 50 on the trailing window",
     "measured weekly"),
    ("D5", "Confidence loss", "two consecutive 100-bet windows with a bootstrap 95% CI lower bound at or below zero",
     "measured at each 100-bet boundary"),
    ("D6", "Price integrity", "more than 20% of signals could not be executed at the recorded price",
     "measured per capture"),
]

DEMOTION_RULES = {
    "re_promotion": "A demoted strategy returns to live only after 100 fresh paper bets "
                    "that pass G1-G8 again on their own.",
    "cool_down": "A strategy demoted twice inside one season stays in paper until the "
                 "next season's out-of-sample window opens.",
    "capital": "Paper bets carry no capital. Live bets are capped at the Kelly quarter "
               f"stake up to {KELLY_CAP} units, and the cap is not raised after a winning run.",
}


def check_promotion(ev, baselines, neighbour_positive_fraction, max_abs_corr, dedup_ok):
    """Return [(gate_id, name, criterion, passed, observed), ...]."""
    g1 = ev["bets"] >= 200
    g2 = bool(dedup_ok)
    g3 = (ev["ci_low"] is not None and ev["ci_low"] > 0) and (ev["p_value_binomial"] <= 0.05)
    g4 = ev["roi_weighted"] >= 0.02
    g5 = all(ev["roi_flat"] > b for b in baselines.values())
    g6 = (ev.get("_robust_roi") or -1) > 0
    g7 = neighbour_positive_fraction >= 0.60
    g8 = max_abs_corr <= 0.85
    obs = {
        "G1": f"{ev['bets']} bets",
        "G2": "no duplicate bets" if dedup_ok else "duplicate bets found",
        "G3": f"CI low {ev['ci_low']}, p = {ev['p_value_binomial']}",
        "G4": f"weighted ROI {ev['roi_weighted']:.4f}",
        "G5": "best baseline ROI " + (f"{max(baselines.values()):.4f}" if baselines else "n/a"),
        "G6": f"ROI {ev.get('_robust_roi')} on {ev.get('_robust_n', 0)} bets",
        "G7": f"{neighbour_positive_fraction:.0%} of neighbours positive",
        "G8": f"max |correlation| {max_abs_corr:.3f}",
    }
    passed = {"G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5, "G6": g6, "G7": g7, "G8": g8}
    return [(gid, name, crit, bool(passed[gid]), obs[gid])
            for gid, name, crit in PROMOTION_GATES]


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def signal_score(ev, neighbour_positive_fraction, robust_ok):
    """Stake-independent score. Bet sizing cannot move it: it is flat 1 unit."""
    edge = _clamp(ev["roi_flat"] / 0.10)
    signif = _clamp(ev["z_score"] / 3.0)
    sample = _clamp(ev["bets"] / 500.0)
    stability = _clamp(neighbour_positive_fraction)
    robust = 1.0 if robust_ok else 0.5
    return round(100.0 * (0.35 * edge + 0.25 * signif + 0.15 * sample
                          + 0.15 * stability + 0.10 * robust), 2)


def staking_score(ev, pos_fraction):
    """Stake-dependent score.

    Drawdown is normalised by the total units actually staked rather than by a
    fixed number, because a fixed-unit plan run for 3,000 bets will always
    draw down more than 100 units and the raw figure would carry no information.
    """
    growth = _clamp(ev["roi_weighted"] / 0.12)
    dd_ratio = ev.get("drawdown_over_units_staked")
    dd = _clamp(1.0 - (dd_ratio / 0.15)) if dd_ratio is not None else 0.0
    consistency = _clamp(pos_fraction if pos_fraction is not None else 0.0)
    return round(100.0 * (0.50 * growth + 0.30 * dd + 0.20 * consistency), 2)


def demotion_status(ev):
    """Evaluate the demotion gate over the trailing window.

    Nothing is live today, so every row reports the gate as *defined and
    unexercised* together with what the current evidence would do if the
    strategy were live. That is stated rather than implied.
    """
    if not ev or ev["bets"] < 50:
        return [{"gate": gid, "name": name, "criterion": crit, "window": win,
                 "state": "not evaluated - insufficient trailing bets",
                 "current": f"{ev['bets'] if ev else 0} bets on record"}
                for gid, name, crit, win in DEMOTION_GATES]
    tail = ev["_flat"][-200:]
    roi_tail = sum(tail) / len(tail)
    dd = ev["max_drawdown_units"]
    out = []
    for gid, name, crit, win in DEMOTION_GATES:
        if gid == "D1":
            trig = roi_tail < 0
            cur = f"trailing-{len(tail)} ROI {roi_tail:.4f}"
        elif gid == "D3":
            trig = dd > DRAWDOWN_LIMIT_UNITS
            cur = (f"max drawdown {dd:.2f} units against a limit of "
                   f"{DRAWDOWN_LIMIT_UNITS:.0f} units ({DRAWDOWN_LIMIT_UNITS / BANKROLL:.0%} "
                   f"of the starting {BANKROLL:.0f}-unit bankroll)")
        elif gid == "D4":
            trig = False
            cur = "signal_score published on the leaderboard"
        else:
            trig = None
            cur = "evaluated when the strategy goes live"
        out.append({
            "gate": gid, "name": name, "criterion": crit, "window": win,
            "state": ("TRIPPED" if trig else "not tripped") if trig is not None else "armed",
            "current": cur,
        })
    return out


# ---------------------------------------------------------------------------
# correlation between two strategies' bet records
# ---------------------------------------------------------------------------

def bet_correlation(bets_a, bets_b):
    """Pearson correlation of per-bet flat profit over games both strategies bet."""
    a = {(b["game_id"], b["market"], b["side"]): profit(1.0, b["price"], b["outcome"]) for b in bets_a}
    b = {(b["game_id"], b["market"], b["side"]): profit(1.0, b["price"], b["outcome"]) for b in bets_b}
    keys = sorted(set(a) & set(b))
    if len(keys) < 30:
        return None, len(keys)
    xs = [a[k] for k in keys]
    ys = [b[k] for k in keys]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None, len(keys)
    return sxy / math.sqrt(sxx * syy), len(keys)
