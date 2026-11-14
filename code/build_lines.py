#!/usr/bin/env python3
"""X1 NFL line origination engine.

Originates the project's own spreads and totals from schedule-adjusted team
ratings fitted on historical game results, then measures them against the
market (benchmark, not truth) and reports the correlation structure needed
for parlay/prop risk control.

Design principles
-----------------
1. No market data is used to FIT the ratings — the model is built purely from
   game results (points). Market lines appear only in the evaluation step.
2. Expanding-window backtest: each historical game is priced using ratings
   fitted ONLY on games that happened before it (no leakage).
3. Deterministic: no RNG anywhere. Same input -> same output.
4. Pure standard library. No numpy/pandas dependency.

Outputs (data/lines/):
  model_config.json            fit windows, HFA, noise estimates, thresholds
  team_ratings_2026_w10.csv    offense/defense/margin ratings + source note
  backtest_summary.csv         per-season accuracy & market-vs-model economics
  backtest_bets.csv            full bet log for the audited edge strategies
  originated_lines_2026_week10.csv   the project's own Week 10 lines
  correlation_report.csv/.md   computed correlation values with sample sizes

Model
-----
Two ordinary-least-squares systems over team ratings (32 teams) fitted on
per-game observations, solved with Gaussian elimination:

  Margin system : margin(home-away) = R_home - R_away + HFA
  Scoring system: home_pts = O_home - D_away + HOFF
                  away_pts = O_away - D_home
  Constraints   : mean(D) = 0 and mean(O) = league mean points scored
                  (removes the two rank deficiencies), tiny ridge for stability.

spread = home_pts_hat - away_pts_hat ; total = home_pts_hat + away_pts_hat
Moneylines are derived with a normal approximation using the empirical
residual standard deviations (documented in model_config.json).
"""
import csv, json, math, os, sys, datetime

ROOT = os.path.join(os.path.dirname(__file__), "..")
GAMES = os.path.join(ROOT, "data", "raw", "nflverse", "games.csv")
OUT = os.path.join(ROOT, "data", "lines")
FIT_SEASONS = ["2019", "2020", "2021", "2022", "2023", "2024", "2025"]
FINAL_SEASONS = FIT_SEASONS + ["2026"]           # 2026 = played games only
WARMUP_GAMES = 80                                # skip backtest until enough data
RIDGE = 1e-6

# canonical abbr list exactly as used by games.csv (LA = Rams, LAC = Chargers,
# LV = Raiders, WAS = Commanders, MIN = Vikings)
TEAMS = ["ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN",
         "DET", "GB", "HOU", "IND", "JAX", "KC", "LAC", "LV", "LA", "MIA",
         "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SF", "SEA", "TB",
         "TEN", "WAS"]
IDX = {t: i for i, t in enumerate(TEAMS)}
NT = 32
# relocation aliases in historical data
ALIAS = {"OAK": "LV"}


def load_games():
    with open(GAMES, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        if r["game_type"] != "REG":
            continue
        out.append({
            "game_id": r["game_id"], "season": r["season"], "week": int(r["week"]),
            "gameday": r["gameday"], "home": ALIAS.get(r["home_team"], r["home_team"]),
            "away": ALIAS.get(r["away_team"], r["away_team"]),
            "home_pts": r["home_score"], "away_pts": r["away_score"],
            "spread_line": r.get("spread_line", ""),       # away-team spread (verified vs ML)
            "total_line": r.get("total_line", ""),
            "away_ml": r.get("away_moneyline", ""), "home_ml": r.get("home_moneyline", ""),
            "location": r.get("location", ""),
        })
    out.sort(key=lambda g: (g["season"], g["week"], g["gameday"], g["game_id"]))
    return out


def solve(A, b):
    """Gaussian elimination with partial pivoting. A: n x n, b: n."""
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-12:
            raise ValueError("singular system")
        M[c], M[p] = M[p], M[c]
        inv = 1.0 / M[c][c]
        for r in range(n):
            if r != c and M[r][c]:
                f = M[r][c] * inv
                for k in range(c, n + 1):
                    M[r][k] -= f * M[c][k]
    return [M[i][n] / M[i][i] for i in range(n)]


def fit(games):
    """Ordinary least squares via normal equations.
    vars = O(32) + D(32) + HOFF(1) = 65; rows = 2 per game + 2 constraints."""
    nv = 2 * NT + 1
    XtX = [[0.0] * nv for _ in range(nv)]
    Xty = [0.0] * nv
    league_pts = 0.0
    rows = []
    for g in games:
        h, a = g["home"], g["away"]
        # home points: O_h - D_a + HOFF
        r = [0.0] * nv
        r[IDX[h]] = 1.0; r[NT + IDX[a]] = -1.0; r[2 * NT] = 1.0
        rows.append((r, g["hp"]))
        # away points: O_a - D_h
        r = [0.0] * nv
        r[IDX[a]] = 1.0; r[NT + IDX[h]] = -1.0
        rows.append((r, g["ap"]))
        league_pts += g["hp"] + g["ap"]
    # constraints as heavily weighted pseudo-observations.
    # NOTE: the whole row (features AND target) must be scaled by W, otherwise the
    # effective target becomes y/W (bug caught by inspecting mean(O) of the fit).
    W = 1e4
    # constraint 1: mean(D) = 0
    r = [0.0] * nv
    for i in range(NT):
        r[NT + i] = W / NT
    rows.append((r, W * 0.0))
    # constraint 2: mean(O) = league mean points scored PER TEAM PER GAME
    r = [0.0] * nv
    for i in range(NT):
        r[i] = W / NT
    rows.append((r, W * league_pts / (2 * len(games))))
    # accumulate normal equations (rows are sparse: ~3 nonzeros)
    for r, y in rows:
        nz = [(i, r[i]) for i in range(nv) if r[i]]
        for i, xi in nz:
            Xty[i] += xi * y
            for j, xj in nz:
                if j >= i:
                    XtX[i][j] += xi * xj
    for i in range(nv):
        for j in range(i + 1, nv):
            XtX[j][i] = XtX[i][j]
    for i in range(nv):
        XtX[i][i] += RIDGE
    x = solve(XtX, Xty)
    O = x[:NT]; D = x[NT:2 * NT]; HOFF = x[2 * NT]
    return {"O": O, "D": D, "HOFF": HOFF}


def predict(m, home, away, neutral=False):
    hp = m["O"][IDX[home]] - m["D"][IDX[away]] + (0.0 if neutral else m["HOFF"])
    ap = m["O"][IDX[away]] - m["D"][IDX[home]]
    return hp, ap


def american_ml(prob):
    p = min(max(prob, 1e-6), 1 - 1e-6)
    return round(-100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


def main():
    os.makedirs(OUT, exist_ok=True)
    all_games = load_games()
    by_key = {g["game_id"]: g for g in all_games}

    # sanity: empirical spread_line convention check (away-team spread)
    agree_a = agree_h = 0; checked = 0
    for g in all_games:
        if not g["spread_line"] or not g["away_ml"] or not g["home_ml"]:
            continue
        s = float(g["spread_line"])
        fav_by_ml = "home" if float(g["home_ml"]) < float(g["away_ml"]) else "away"
        # hypothesis A: away-team spread (negative = away favorite)
        fav_by_spread = "away" if s < 0 else "home"
        agree_a += fav_by_ml == fav_by_spread; checked += 1
    conv_rate = agree_a / checked if checked else 0.0
    convention = "away_team_spread" if conv_rate > 0.9 else "UNCERTAIN"
    print(f"spread_line convention: away-team-spread agrees with ML favorite on "
          f"{agree_a}/{checked} games ({conv_rate:.1%}) -> {convention}")
    assert convention == "away_team_spread", "spread sign convention unresolved"

    # ---------------- expanding-window backtest -----------------------------
    hist = [g for g in all_games if g["season"] in FIT_SEASONS and g["home_pts"] != ""]
    fut = [g for g in all_games if g["season"] == "2026" and g["home_pts"] != ""]
    print(f"history: {len(hist)} games 2019-2025; 2026 played: {len(fut)}")

    m = None
    residuals_spread, residuals_total = [], []
    betlog = []
    season_stats = {}
    # group by (season, week) -> refit once per week on all prior games (no leakage)
    groups = {}
    for g in hist:
        groups.setdefault((g["season"], g["week"]), []).append(g)
    history = []
    scored = 0
    for key in sorted(groups):
        if len(history) >= WARMUP_GAMES:
            m = fit([{"home": x["home"], "away": x["away"],
                      "hp": int(x["home_pts"]), "ap": int(x["away_pts"])}
                     for x in history])   # ratings from games BEFORE this week
            for g in groups[key]:
                gp, ap = predict(m, g["home"], g["away"])
                margin_hat = gp - ap; total_hat = gp + ap
                g_hp, g_ap = int(g["home_pts"]), int(g["away_pts"])
                margin_act = g_hp - g_ap; total_act = g_hp + g_ap
                residuals_spread.append(margin_act - margin_hat)
                residuals_total.append(total_act - total_hat)
                scored += 1
                seas = g["season"]
                st = season_stats.setdefault(seas, {"n": 0, "mae_s": 0.0, "mae_t": 0.0})
                st["n"] += 1; st["mae_s"] += abs(margin_act - margin_hat)
                st["mae_t"] += abs(total_act - total_hat)
                # economics: bet where the model disagrees with the market
                if g["spread_line"]:
                    s_away = float(g["spread_line"])       # market away-team spread (= market home margin)
                    mhat_away = margin_hat                 # model away-team spread (same convention)
                    edge_home = margin_hat - s_away        # + => model likes home more than market
                    side = None
                    if edge_home >= 1.0: side = ("home", s_away)
                    elif edge_home <= -1.0: side = ("away", s_away)
                    if side:
                        # home covers iff margin > s_away ; away covers iff margin < s_away
                        won = (margin_act > s_away) if side[0] == "home" else (margin_act < s_away)
                        push = (margin_act == s_away)
                        betlog.append({"game": g["game_id"], "season": seas, "week": g["week"],
                                       "market": "spread", "side": side[0],
                                       "market_line_away": s_away, "model_line_away": round(mhat_away, 1),
                                       "edge": round(abs(edge_home), 1),
                                       "result": "W" if won else ("P" if push else "L")})
                if g["total_line"]:
                    mt = float(g["total_line"])
                    if total_hat - mt >= 2.0:
                        betlog.append({"game": g["game_id"], "season": seas, "week": g["week"],
                                       "market": "total", "side": "over",
                                       "market_line_away": mt, "model_line_away": round(total_hat, 1),
                                       "edge": round(total_hat - mt, 1),
                                       "result": "W" if total_act > mt else ("P" if total_act == mt else "L")})
                    elif total_hat - mt <= -2.0:
                        betlog.append({"game": g["game_id"], "season": seas, "week": g["week"],
                                       "market": "total", "side": "under",
                                       "market_line_away": mt, "model_line_away": round(total_hat, 1),
                                       "edge": round(mt - total_hat, 1),
                                       "result": "W" if total_act < mt else ("P" if total_act == mt else "L")})
        history.extend(groups[key])
    print(f"backtest scored on {len(residuals_spread)} games (warmup {WARMUP_GAMES} skipped)")

    # ---------------- economics of the audited edge strategies --------------
    def econ(market):
        bets = [b for b in betlog if b["market"] == market]
        w = sum(1 for b in bets if b["result"] == "W")
        l = sum(1 for b in bets if b["result"] == "L")
        p = sum(1 for b in bets if b["result"] == "P")
        pnl = 0.909 * w - 1.0 * l
        roi = pnl / max(1, (w + l))
        return {"bets": len(bets), "wins": w, "losses": l, "pushes": p,
                "units": round(pnl, 1), "roi_pct": round(100 * roi, 2),
                "win_rate_pct": round(100 * w / max(1, w + l), 2)}
    sp = econ("spread"); to = econ("total")
    print("spread edge strategy:", sp)
    print("total  edge strategy:", to)

    # threshold sweep (real numbers for strategy validation gates)
    def sweep(market, cuts):
        out = []
        for c in cuts:
            bets = [b for b in betlog if b["market"] == market and b["edge"] >= c]
            w = sum(1 for b in bets if b["result"] == "W")
            l = sum(1 for b in bets if b["result"] == "L")
            pnl = 0.909 * w - 1.0 * l
            out.append({"threshold": c, "bets": len(bets),
                        "win_rate_pct": round(100 * w / max(1, w + l), 2),
                        "roi_pct": round(100 * pnl / max(1, (w + l)), 2),
                        "units": round(pnl, 1)})
        return out
    sweep_rows = ([{"market": "spread", **r} for r in sweep("spread", [1, 2, 3, 5, 7])] +
                  [{"market": "total", **r} for r in sweep("total", [2, 3, 4, 6, 8])])
    with open(os.path.join(OUT, "threshold_sweep.csv"), "w", newline="") as fh:
        w_ = csv.DictWriter(fh, fieldnames=["market", "threshold", "bets", "win_rate_pct", "roi_pct", "units"])
        w_.writeheader()
        for r in sweep_rows:
            w_.writerow(r)
    print("threshold sweep:", sweep_rows)

    # noise estimates
    sd_spread = math.sqrt(sum(x * x for x in residuals_spread) / len(residuals_spread))
    sd_total = math.sqrt(sum(x * x for x in residuals_total) / len(residuals_total))

    # ---------------- final fit incl. 2026 played games ---------------------
    final_rows = [{"home": g["home"], "away": g["away"],
                   "hp": int(g["home_pts"]), "ap": int(g["away_pts"])}
                  for g in all_games if g["season"] in FINAL_SEASONS and g["home_pts"] != ""]
    mfin = fit(final_rows)
    hfa = mfin["HOFF"]

    # ---------------- originate Week 10 lines -------------------------------
    wk10 = [g for g in all_games if g["season"] == "2026" and g["week"] == 10]
    lines = []
    for g in sorted(wk10, key=lambda x: x["gameday"]):
        neutral = g["location"] == "Neutral"
        hp, ap = predict(mfin, g["home"], g["away"], neutral=neutral)
        margin_hat = hp - ap; total_hat = hp + ap
        # away-team spread (convention verified vs market: spread = predicted home margin)
        away_spread = margin_hat
        away_spread_r = round(away_spread * 2) / 2
        total_r = round(total_hat * 2) / 2
        p_home = 0.5 * (1 + math.erf((margin_hat) / (sd_spread * math.sqrt(2))))
        p_over = 0.5 * (1 + math.erf((total_r - total_hat) / (sd_total * math.sqrt(2))))
        ml_home = american_ml(p_home); ml_away = american_ml(1 - p_home)
        mkt = None
        if g["spread_line"]:
            mkt = (float(g["spread_line"]), float(g["total_line"]))
        lines.append({
            "game_id": g["game_id"], "date": g["gameday"], "away": g["away"], "home": g["home"],
            "neutral": "Y" if neutral else "",
            "x1_spread_away": away_spread_r, "x1_total": total_r,
            "x1_ml_away": ml_away, "x1_ml_home": ml_home,
            "market_spread_away": mkt[0] if mkt else "", "market_total": mkt[1] if mkt else "",
            "edge_spread_away": round(mkt[0] - away_spread_r, 1) if mkt else "",
            "edge_total": round(total_r - mkt[1], 1) if mkt else "",
            "played": "Y" if g["home_pts"] != "" else "",
            "result": f"{g['away_pts']}-{g['home_pts']}" if g["home_pts"] != "" else "",
            "model_input": f"ratings fitted on {len(final_rows)} game-results rows "
                           f"(2019-2025 + 2026 played); market used for benchmark only",
        })

    # ---------------- correlations ------------------------------------------
    used = [g for g in all_games if g["season"] in ["2021", "2022", "2023", "2024", "2025", "2026"]
            and g["home_pts"] != ""]
    xs, ys = [], []
    for g in used:
        hp, ap = int(g["home_pts"]), int(g["away_pts"])
        xs.append(hp - ap); ys.append(hp + ap)
    n = len(xs)
    mx = sum(xs) / n; my = sum(ys) / n
    cov = sum((a - mx) * (c - my) for a, c in zip(xs, ys)) / n
    r_margin_total = cov / (math.sqrt(sum((a - mx) ** 2 for a in xs) / n) *
                            math.sqrt(sum((c - my) ** 2 for c in ys) / n))

    # favorite-cover vs over (same-game parlay correlation) using market lines
    n11 = n10 = n01 = n00 = 0
    for g in used:
        if not g["spread_line"] or not g["total_line"]:
            continue
        s = float(g["spread_line"]); t = float(g["total_line"])
        hp, ap = int(g["home_pts"]), int(g["away_pts"])
        m_act = hp - ap; tot_act = hp + ap
        # favorite is away if s<0 (covers iff m_act < s) ; home if s>0 (covers iff m_act > s)
        fav_covers = (m_act < s) if s < 0 else (m_act > s)
        over = tot_act > t
        if fav_covers and over: n11 += 1
        elif fav_covers and not over: n10 += 1
        elif not fav_covers and over: n01 += 1
        else: n00 += 1
    ntot = n11 + n10 + n01 + n00
    phi = (n11 * n00 - n10 * n01) / math.sqrt(
        (n11 + n10) * (n01 + n00) * (n11 + n01) * (n10 + n00))
    p_over_given_cover = n11 / (n11 + n10)
    p_over = (n11 + n01) / ntot

    # model-error correlation, spread residual vs total residual (same game)
    # from the backtest residual lists (paired by construction)
    mres = residuals_spread; tres = residuals_total
    mm = sum(mres) / len(mres); tm = sum(tres) / len(tres)
    cov2 = sum((a - mm) * (c - tm) for a, c in zip(mres, tres)) / len(mres)
    r_model_err = cov2 / (math.sqrt(sum((a - mm) ** 2 for a in mres) / len(mres)) *
                          math.sqrt(sum((c - tm) ** 2 for c in tres) / len(tres)))

    # cross-game independence: corr of margin residuals between same-week games
    # rebuild game->residual mapping in the same order residuals were appended
    res_map = {}
    k = 0
    history2 = []
    for key in sorted(groups):
        if len(history2) >= WARMUP_GAMES:
            for g in groups[key]:
                res_map[g["game_id"]] = residuals_spread[k]; k += 1
        history2.extend(groups[key])
    by_week = {}
    for g in hist:
        if g["game_id"] in res_map:
            by_week.setdefault((g["season"], g["week"]), []).append(res_map[g["game_id"]])
    pairs = []
    for wk, rs in by_week.items():
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                pairs.append((rs[i], rs[j]))
    npair = len(pairs)
    # sample-level correlation across all same-week pairs
    if npair > 100:
        px = [a for a, b in pairs]; py = [b for a, b in pairs]
        mp1 = sum(px) / npair; mp2 = sum(py) / npair
        covp = sum((a - mp1) * (b - mp2) for a, b in pairs) / npair
        r_cross = covp / (math.sqrt(sum((a - mp1) ** 2 for a in px) / npair) *
                           math.sqrt(sum((b - mp2) ** 2 for b in py) / npair))
    else:
        r_cross = None

    # Fisher z CI for the reported Pearson correlations
    def fisher_ci(r, nn, alpha=0.05):
        if r is None or nn < 4: return None
        z = 0.5 * math.log((1 + r) / (1 - r))
        se = 1 / math.sqrt(nn - 3)
        dz = 1.959964 * se
        lo = math.tanh(z - dz); hi = math.tanh(z + dz)
        return round(lo, 3), round(hi, 3)

    ci_mt = fisher_ci(r_margin_total, n)
    ci_err = fisher_ci(r_model_err, len(mres))
    phi_se = 1.0 / math.sqrt(ntot)
    ci_phi = (round(phi - 1.959964 * phi_se, 3), round(phi + 1.959964 * phi_se, 3))
    ci_cross = fisher_ci(r_cross, npair)

    # ---------------- write outputs ------------------------------------------
    cfg = {
        "generated": datetime.datetime.utcnow().isoformat() + "Z",
        "fit_seasons_backtest": FIT_SEASONS,
        "fit_rows_final": len(final_rows),
        "warmup_games": WARMUP_GAMES,
        "ridge": RIDGE,
        "hfa_points_final_fit": round(hfa, 2),
        "residual_sd_spread": round(sd_spread, 2),
        "residual_sd_total": round(sd_total, 2),
        "spread_line_convention": "away-team spread; negative = away favorite (verified vs ML on %d games)" % checked,
        "bet_thresholds": {"spread_pts": 1.0, "total_pts": 2.0},
        "price_assumption": "flat -110 (win +0.909 units, loss -1)",
        "data_source": "nflverse/nfldata games.csv (https://github.com/nflverse/nfldata)",
    }
    with open(os.path.join(OUT, "model_config.json"), "w") as fh:
        json.dump(cfg, fh, indent=2)

    with open(os.path.join(OUT, "team_ratings_2026_w10.csv"), "w", newline="") as fh:
        w_ = csv.writer(fh)
        w_.writerow(["team", "off_rating", "def_rating_allowed", "net_rating",
                     "note", "source"])
        for t in TEAMS:
            off = mfin["O"][IDX[t]]
            def_allowed = -mfin["D"][IDX[t]]   # points allowed vs league avg (higher = worse)
            net = off - def_allowed
            w_.writerow([t, round(off, 2), round(def_allowed, 2), round(net, 2),
                         "off = expected pts vs league-avg defense; def_allowed = pts allowed vs league-avg offense (higher = worse); "
                         "net = off - def_allowed; home bonus HOFF=%.2f added to home team only at predict time" % hfa,
                         "derived from nflverse games.csv results (https://github.com/nflverse/nfldata)"])

    with open(os.path.join(OUT, "backtest_summary.csv"), "w", newline="") as fh:
        w_ = csv.writer(fh)
        w_.writerow(["season", "games", "MAE_spread_pts", "MAE_total_pts"])
        for seas in sorted(season_stats):
            st = season_stats[seas]
            w_.writerow([seas, st["n"], round(st["mae_s"] / st["n"], 2),
                         round(st["mae_t"] / st["n"], 2)])
        w_.writerow(["ALL", len(residuals_spread),
                     round(sum(abs(x) for x in residuals_spread) / len(residuals_spread), 2),
                     round(sum(abs(x) for x in residuals_total) / len(residuals_total), 2)])
        w_.writerow([])
        w_.writerow(["edge_strategy", "bets", "wins", "losses", "pushes",
                     "units_at_-110", "roi_pct", "win_rate_pct"])
        for name, e in (("spread_vs_market_edge>=1.0", sp), ("total_vs_market_edge>=2.0", to)):
            w_.writerow([name, e["bets"], e["wins"], e["losses"], e["pushes"],
                         e["units"], e["roi_pct"], e["win_rate_pct"]])

    with open(os.path.join(OUT, "backtest_bets.csv"), "w", newline="") as fh:
        w_ = csv.DictWriter(fh, fieldnames=["game", "season", "week", "market", "side",
                                            "market_line_away", "model_line_away", "edge", "result"])
        w_.writeheader()
        for b in betlog:
            w_.writerow(b)

    with open(os.path.join(OUT, "originated_lines_2026_week10.csv"), "w", newline="") as fh:
        w_ = csv.DictWriter(fh, fieldnames=["game_id", "date", "away", "home", "neutral",
                                            "x1_spread_away", "x1_total", "x1_ml_away",
                                            "x1_ml_home", "market_spread_away", "market_total",
                                            "edge_spread_away", "edge_total", "played", "result",
                                            "model_input"])
        w_.writeheader()
        for row in lines:
            w_.writerow(row)

    corr_rows = [
        ["game_margin_vs_game_total_pearson_r", round(r_margin_total, 3), n,
         f"95% CI {ci_mt}", "same-game: higher-scoring games & margin relationship"],
        ["same_game_favorite_cover_vs_over_phi", round(phi, 3), ntot,
         f"95% CI {ci_phi}; P(over|fav covers)={p_over_given_cover:.3f} vs P(over)={p_over:.3f}",
         "same-game parlay correlation (market lines, 2021-2026)"],
        ["model_spread_error_vs_total_error_r", round(r_model_err, 3), len(mres),
         f"95% CI {ci_err}", "same-game model errors"],
        ["cross_game_same_week_residual_r", (round(r_cross, 3) if r_cross is not None else ""), npair,
         (f"95% CI {ci_cross}" if ci_cross else ""), "independence check across games in same week"],
    ]
    with open(os.path.join(OUT, "correlation_report.csv"), "w", newline="") as fh:
        w_ = csv.writer(fh)
        w_.writerow(["metric", "value", "n", "ci_or_detail", "interpretation"])
        w_.writerows(corr_rows)

    md = []
    md.append("# Correlation report (computed, deterministic)\n")
    md.append("All values computed by `code/build_lines.py` from nflverse game results + "
              "market lines embedded in games.csv. No external claims.\n")
    md.append("| Metric | Value | n | 95% CI / detail | Meaning |")
    md.append("|---|---|---|---|---|")
    for row in corr_rows:
        md.append("| " + " | ".join(str(c) for c in row) + " |")
    md.append("\nParlay risk control: same-game spread/total legs carry phi ≈ %.3f — "
              "joint probability must be adjusted, naive multiplication understates risk "
              "by roughly the difference between P(over|fav covers)=%.3f and P(over)=%.3f."
              % (phi, p_over_given_cover, p_over))
    if r_cross is not None:
        md.append("Cross-game residual correlation r ≈ %.3f (n=%d pairs) supports treating "
                  "different games as near-independent when building multi-game parlays."
                  % (r_cross, npair))
    with open(os.path.join(OUT, "correlation_report.md"), "w") as fh:
        fh.write("\n".join(md) + "\n")

    print("\n=== Week 10 originated lines (X1) vs market ===")
    for row in lines:
        print(f"{row['date']} {row['away']}@{row['home']}"
              f"{' [N]' if row['neutral'] else ''}: X1 {row['x1_spread_away']:+.1f} | total {row['x1_total']:.1f}"
              f" | mkt {row['market_spread_away']} / {row['market_total']}"
              f" | edge_away {row['edge_spread_away']}/total {row['edge_total']}"
              + (f" | FINAL {row['result']}" if row['played'] else ""))
    print("\nBacktest MAE spread %.2f / total %.2f | HFA %.2f | sd_spread %.2f sd_total %.2f"
          % (sum(abs(x) for x in residuals_spread) / len(residuals_spread),
             sum(abs(x) for x in residuals_total) / len(residuals_total), hfa,
             sd_spread, sd_total))
    print("Spread edge strat:", sp)
    print("Total  edge strat:", to)
    print("Correlations: margin-total r=%.3f | fav-cover/over phi=%.3f | model err r=%.3f"
          % (r_margin_total, phi, r_model_err))


if __name__ == "__main__":
    main()
