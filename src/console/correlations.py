"""Correlations, computed only from sourced numbers, each published with n.

Requirement C7. Two rules are enforced:

  1. Every value is computed from numbers that appear in a named source in
     ``sources.py``. No correlation is published from a number this repository
     made up, and none is quoted from memory.
  2. Every value is published with the n it was computed on, plus a 95%
     interval, so a reader can see how much weight it carries.

The headline use is parlay pricing: a two-leg same-game parlay is only worth
what the legs' marginal prices imply if the two legs are independent. The
measured within-game correlation between the spread result and the total result
is the number that decides whether a side/total parlay is mispriced.
"""

from __future__ import annotations

import math

from . import originate, strategy


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def fisher_ci(r, n, level=1.96):
    """95% CI for a correlation via the Fisher z transform."""
    if r is None or n < 4:
        return None, None
    r = max(-0.999999, min(0.999999, r))
    z = 0.5 * math.log((1 + r) / (1 - r))
    se = 1.0 / math.sqrt(n - 3)
    lo, hi = z - level * se, z + level * se
    return math.tanh(lo), math.tanh(hi)


def phi_coefficient(a, b):
    """Correlation of two 0/1 series (equivalently Pearson on indicators)."""
    return pearson([1.0 if x else 0.0 for x in a], [1.0 if y else 0.0 for y in b])


def point_biserial(xs, flags):
    """Correlation between a continuous series and a 0/1 outcome."""
    return pearson(xs, [1.0 if f else 0.0 for f in flags])


def _record(name, question, r, n, source_key, unit="correlation", note=""):
    lo, hi = fisher_ci(r, n)
    return {
        "name": name,
        "question": question,
        "value": None if r is None else round(r, 4),
        "n": n,
        "ci_low": None if lo is None else round(lo, 4),
        "ci_high": None if hi is None else round(hi, 4),
        "unit": unit,
        "source_key": source_key,
        "note": note,
    }


def compute(games, rows, bets_by_strategy=None):
    """All published correlations. ``games`` supplies official scores, ``rows``
    the out-of-sample model output."""
    out = []
    gm = {g["game_id"]: g for g in games}
    scored = [r for r in rows if r["mode"] == "oos" and gm[r["game_id"]]["settled"]]

    # 1. within-game: does the spread result tell you about the total result?
    home_cover, over_hit = [], []
    for r in scored:
        g = gm[r["game_id"]]
        if r["market_side"] == "" or r["market_total"] == "":
            continue
        home_cover.append(g["margin_home"] - float(r["market_side"]) > 0)
        over_hit.append(g["total_points"] - float(r["market_total"]) > 0)
    out.append(_record(
        "Spread result vs total result, same game",
        "If the home team covers, is the over more or less likely?",
        phi_coefficient(home_cover, over_hit), len(home_cover), "nfldata_games",
        note="Phi coefficient on two indicators. This is the number that decides "
             "whether a same-game side/total parlay is mispriced by the product of "
             "the legs' prices."))

    # 2. margin vs total points
    ms = [gm[r["game_id"]]["margin_home"] for r in scored]
    ts = [gm[r["game_id"]]["total_points"] for r in scored]
    out.append(_record(
        "Home margin vs total points, same game",
        "Do blowouts score more?",
        pearson(ms, ts), len(scored), "nfldata_games"))

    # 3. market efficiency: market spread vs actual margin
    mk = [float(r["market_side"]) for r in scored if r["market_side"] != ""]
    am = [gm[r["game_id"]]["margin_home"] for r in scored if r["market_side"] != ""]
    out.append(_record(
        "Market spread vs actual home margin",
        "How much of the result does the closing spread already know?",
        pearson(mk, am), len(mk), "nfldata_games",
        note="The benchmark every model in this repository has to beat."))

    # 4. model spread vs actual margin
    fm = [float(r["fair_side"]) for r in scored if r["market_side"] != ""]
    out.append(_record(
        "Model fair spread vs actual home margin",
        "How much of the result does our own model know?",
        pearson(fm, am), len(fm), "computed_model"))

    # 5. the parlay correlation proper: spread error vs total error
    se, te = [], []
    for r in scored:
        g = gm[r["game_id"]]
        if r["market_side"] == "" or r["market_total"] == "":
            continue
        se.append(g["margin_home"] - float(r["market_side"]))
        te.append(g["total_points"] - float(r["market_total"]))
    out.append(_record(
        "Spread error vs total error, same game",
        "If the favourite covers by more than the spread, is the total also high?",
        pearson(se, te), len(se), "nfldata_games",
        note="Positive means the two legs move together, which is exactly what a "
             "same-game parlay needs and what books price against."))

    # 6. cross-game independence: does one team's result predict its next?
    by_team = {}
    for r in sorted(scored, key=lambda x: x["gameday"]):
        g = gm[r["game_id"]]
        if r["market_side"] == "":
            continue
        err = g["margin_home"] - float(r["market_side"])
        by_team.setdefault(g["home"], []).append(err)
        by_team.setdefault(g["away"], []).append(-err)
    xs, ys = [], []
    for t, series in by_team.items():
        for a, b in zip(series, series[1:]):
            xs.append(a)
            ys.append(b)
    out.append(_record(
        "A team's ATS result vs its next ATS result",
        "Is there any momentum in covering the spread?",
        pearson(xs, ys), len(xs), "nfldata_games",
        note="Lag-1 autocorrelation within a team across consecutive games."))

    # 7. does our own edge predict the outcome? (the signal's own validity)
    for sid, bets in (bets_by_strategy or {}).items():
        edges, won = [], []
        for b in bets:
            e = b.get("model_edge")
            if e is None or isinstance(e, tuple):
                continue
            edges.append(abs(e))
            won.append(b["outcome"] == "W")
        if len(edges) >= 30:
            out.append(_record(
                f"Edge size vs bet result - {sid}",
                "Does a bigger disagreement with the market actually win more often?",
                point_biserial(edges, won), len(edges), "computed_model",
                note="Point-biserial. A signal worth staking has a positive value here; "
                     "zero means the edge size carries no information."))

    # 8. rest differential vs home margin
    rd, rm = [], []
    for r in scored:
        g = gm[r["game_id"]]
        if g.get("home_rest") is None or g.get("away_rest") is None:
            continue
        rd.append(g["home_rest"] - g["away_rest"])
        rm.append(g["margin_home"])
    out.append(_record(
        "Rest differential vs home margin",
        "Is a rest advantage worth points?",
        pearson(rd, rm), len(rd), "nfldata_games"))

    return out


def parlay_pricing(spread_total_r, n, side_price=-110, total_price=-110):
    """What a two-leg parlay is actually worth, given the measured correlation.

    A book prices a two-leg parlay at the product of the legs. That is only fair
    if the legs are independent. With a measured correlation the joint win
    probability is not the product, so the fair price moves. This returns the
    arithmetic with every input stated.
    """
    p_leg = originate.american_to_prob(side_price)
    if p_leg is None:
        return None
    dec_leg = strategy.price_to_decimal(side_price)
    fair_independent = p_leg * p_leg
    parlay_dec = dec_leg * dec_leg
    break_even = 1.0 / parlay_dec
    return {
        "leg_price": side_price,
        "leg_implied_probability": round(p_leg, 4),
        "parlay_decimal": round(parlay_dec, 4),
        "break_even_joint_probability": round(break_even, 4),
        "joint_probability_if_independent": round(fair_independent, 4),
        "measured_spread_total_correlation": None if spread_total_r is None else round(spread_total_r, 4),
        "correlation_n": n,
        "verdict": ("the product of the legs is the fair joint probability only if the "
                    "correlation is zero; the measured value is published above with its n"),
    }


def open_to_close_convergence(games, rows, price_rows):
    """Does the market move toward our number, or away from it?

    For 2021 - the one season with a genuine opening number - compare how far
    the model's fair line sits from the opening line with how far it sits from
    the closing line. If the disagreement shrank, the market moved our way and
    the model carried information the opening number did not have. If it grew,
    the disagreement was our error, not the market's.

    This is the standard way to separate a real signal from a miscalibrated
    model, and it is the only place in this repository where it can be measured.
    """
    opens = {}
    for r in price_rows:
        if r["snapshot_id"] != "SETTLED-2021" or r["side"] != "home":
            continue
        if r["market_type"] == "SIDE" and r["open_line"] != "":
            opens[("SIDE", r["game_id"])] = float(r["open_line"])
        elif r["market_type"] == "TOTAL" and r["open_line"] != "":
            opens[("TOTAL", r["game_id"])] = float(r["open_line"])
    gm = {g["game_id"]: g for g in games}
    out = {"season": 2021, "markets": [], "note": (
        "Only 2021 has a real opening number in any source available here "
        "(nflverse/nfldata initial_lines.csv, sportsbook WSGT).")}
    for market in ("SIDE", "TOTAL"):
        d_open, d_close = [], []
        for r in rows:
            if r["season"] != 2021 or r["mode"] != "oos":
                continue
            key = (market, r["game_id"])
            if key not in opens:
                continue
            fair = float(r["fair_side"] if market == "SIDE" else r["fair_total"])
            close = float(r["market_side"] if market == "SIDE" else r["market_total"])
            d_open.append(abs(opens[key] - fair))
            d_close.append(abs(close - fair))
        if not d_open:
            continue
        n = len(d_open)
        mean_open = sum(d_open) / n
        mean_close = sum(d_close) / n
        shrank = sum(1 for a, b in zip(d_open, d_close) if b < a)
        se = (sum((b - a) ** 2 for a, b in zip(d_open, d_close)) / n) ** 0.5 / (n ** 0.5)
        out["markets"].append({
            "market": market,
            "n": n,
            "mean_abs_gap_vs_open": round(mean_open, 3),
            "mean_abs_gap_vs_close": round(mean_close, 3),
            "change": round(mean_close - mean_open, 3),
            "games_where_gap_shrank": shrank,
            "share_shrank": round(shrank / n, 4),
            "se_of_change": round(se, 3),
            "reading": ("the closing line is FURTHER from our number than the opening "
                        "line was, so the disagreement is our error, not the market's"
                        if mean_close > mean_open else
                        "the closing line moved toward our number"),
        })
    return out
