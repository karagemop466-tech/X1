"""The competition: run every pre-registered strategy, apply the gates, score
signal and staking separately, and publish the leaderboard.

This is the module that implements requirement C5. The leaderboard has two
score columns and promotion depends on the SIGNAL one, so a strategy that made
money only because of how it sized its bets cannot be promoted.
"""

from __future__ import annotations

from . import strategy as st


def _dedupe_ok(bets):
    seen = set()
    for b in bets:
        key = (b["game_id"], b["market"], b["side"])
        if key in seen:
            return False
        seen.add(key)
    return True


def run(games, rows, progress=None):
    games_by_id = {g["game_id"]: g for g in games}

    # ---- baselines: always-on strategies on the same window -------------
    baselines = {}
    for bid, desc, rule in st.BASELINES:
        bets = st.run_strategy(rule, rows, games_by_id)
        ev = st.evaluate_bets(bets)
        baselines[bid] = ev["roi_flat"] if ev else 0.0

    results = []
    accepted = []          # (sid, bets) for the non-redundancy gate
    for sid, family, desc, factory, param, grid in st.STRATEGIES:
        if progress:
            progress(sid)
        rule = st.build_rule(factory, param)
        bets = st.run_strategy(rule, rows, games_by_id)
        ev = st.evaluate_bets(bets) if bets else None
        entry = {
            "id": sid, "family": family, "rule": desc, "param": param,
            "grid": grid, "bets": len(bets),
        }
        if ev is None:
            entry.update({"status": "no bets on the out-of-sample window",
                          "signal_score": 0.0, "staking_score": 0.0,
                          "gates": [], "demotion": st.demotion_status(None)})
            results.append(entry)
            continue

        robust_roi, robust_n = st.luck_robust_roi(bets, games_by_id)
        ev["_robust_roi"] = None if robust_roi is None else round(robust_roi, 5)
        ev["_robust_n"] = robust_n
        pos_fraction, pos_n, n_seasons = st.seasonal_positive_fraction(bets)

        # gate G7 - parameter stability over neighbouring settings
        neighbour_rois = []
        for p in grid:
            if param is not None and abs(p - param) < 1e-9:
                continue
            nb = st.run_strategy(st.build_rule(factory, p), rows, games_by_id)
            if len(nb) < 30:
                continue
            nev = st.evaluate_bets(nb)
            neighbour_rois.append((p, nev["roi_flat"], len(nb)))
        if neighbour_rois:
            stab = sum(1 for _, r, _ in neighbour_rois if r > 0) / len(neighbour_rois)
        else:
            stab = 0.0

        # gate G8 - non-redundancy against already-accepted strategies
        max_corr, corr_with = 0.0, ""
        for aid, abets in accepted:
            c, n = st.bet_correlation(bets, abets)
            if c is not None and abs(c) > max_corr:
                max_corr, corr_with = abs(c), f"{aid} (n={n})"
        if not accepted:
            corr_with = "no accepted strategy yet"

        gates = st.check_promotion(ev, baselines, stab, max_corr, _dedupe_ok(bets))
        sig = st.signal_score(ev, stab, (ev["_robust_roi"] or -1) > 0)
        stk = st.staking_score(ev, pos_fraction)
        all_pass = all(g[3] for g in gates)
        promoted = all_pass and sig >= st.PROMOTION_SIGNAL_FLOOR
        if promoted:
            accepted.append((sid, bets))

        entry.update({
            "status": "promoted" if promoted else ("passed gates, below signal floor"
                                                   if all_pass else "failed gates"),
            "promoted": bool(promoted),
            "signal_score": sig,
            "staking_score": stk,
            "neighbour_rois": neighbour_rois,
            "max_corr": round(max_corr, 4),
            "corr_with": corr_with,
            "stability": round(stab, 4),
            "metrics": {k: v for k, v in ev.items() if not k.startswith("_")},
            "seasons_positive": f"{pos_n}/{n_seasons}",
            "gates": [{"id": g[0], "name": g[1], "criterion": g[2],
                       "passed": g[3], "observed": g[4]} for g in gates],
            "demotion": st.demotion_status(ev),
            "bets": len(bets),
        })
        results.append(entry)

    # reward: only promoted strategies earn anything
    for e in results:
        if e.get("promoted"):
            ev_roi = e["metrics"]["roi_flat"]
            conf = min(1.0, e["metrics"]["bets"] / 500.0)
            e["reward_units"] = round(1000.0 * ev_roi * conf, 2)
        else:
            e["reward_units"] = 0.0

    results.sort(key=lambda e: (-e["signal_score"], -e["metrics"].get("roi_flat", 0)
                                if e.get("metrics") else 0))
    return {
        "baselines": baselines,
        "results": results,
        "promoted": [e["id"] for e in results if e.get("promoted")],
        "signal_floor": st.PROMOTION_SIGNAL_FLOOR,
        "bankroll": st.BANKROLL,
        "kelly_fraction": st.KELLY_FRACTION,
        "kelly_cap": st.KELLY_CAP,
    }
