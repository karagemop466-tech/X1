"""
Strategy research harness for the X1 project.

Inputs : nflverse `nfldata` snapshot (data/games.csv), pinned commit a04d58c0268645ce5081a210bd33650ab222547a.
         Line provenance is NOT documented by the source -> gate G0 fails for every strategy (see I-10).
Outputs: data/strategy_splits.csv, data/strategy_leaderboard.csv, data/strategy_correlations.csv,
         data/parlay_results.csv, data/data_checks.json, data/strategy_registry.csv

Conventions (verified against nfldata DATASETS.md and checked in data_checks.json):
  * spread_line > 0  => home team favored by spread_line points (DATASETS.md).
  * Home covers ATS iff (home_score - away_score) > spread_line; away covers iff < spread_line; equal = push.
  * Over wins iff total > total_line; equal = push.
  * Pricing assumption: standard -110 both sides (breakeven 110/210 = 52.38%). NOT verified against any book.
Nothing here is betting advice. Parameters were fixed before testing and not tuned on any split.
"""
import json, math, sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/nfldata/data/games.csv")
PINNED = "a04d58c0268645ce5081a210bd33650ab222547a"

BREAKEVEN = 110 / 210          # 0.5238 at -110
PAYOUT = 100 / 110             # profit per 1 unit won at -110
PARLAY_DEC = (1 + PAYOUT) ** 2 # 2-leg parlay decimal odds at -110 each

# Pre-registered split definitions (seasons inclusive)
SPLITS = {
    "discovery_2006_2015": (2006, 2015),
    "validation_2016_2020": (2016, 2020),
    "holdout_2021_2025": (2021, 2025),
    "forward_2026": (2026, 2026),
}
ELO_K, ELO_HFA, ELO_SCALE, ELO_REVERT, ELO_BASE = 20.0, 65.0, 25.0, 1 / 3, 1500.0
ELO_EDGE_THRESHOLD = 3.0       # points between model line and market line
MIN_HOLDOUT_BETS = 300
MIN_SEASON_POSITIVE_SHARE = 0.60
BONFERRONI_DIVISOR = 10        # = number of pre-registered strategies (S01-S10)
PHI_LIMIT = 0.50

FRANCHISE_MAP = {"STL": "LA", "SD": "LAC", "OAK": "LV"}  # relocations, applied before rating

def wilson(k, n, z=1.96):
    if n == 0: return (np.nan, np.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)

def load():
    g = pd.read_csv(SRC)
    g = g[g.game_type == "REG"].copy()
    g["home_team"] = g.home_team.replace(FRANCHISE_MAP)
    g["away_team"] = g.away_team.replace(FRANCHISE_MAP)
    g["gameday"] = pd.to_datetime(g.gameday)
    g = g.sort_values(["gameday", "game_id"]).reset_index(drop=True)
    return g

def elo_lines(g):
    """Own model: sequential Elo with fixed a-priori constants. Uses only games strictly before each game."""
    rating = {}
    pred_margin = np.full(len(g), np.nan)
    prev_season = None
    for i, r in g.iterrows():
        if prev_season is not None and r.season != prev_season:
            for t in list(rating):
                rating[t] = ELO_BASE + (1 - ELO_REVERT) * (rating[t] - ELO_BASE)
        prev_season = r.season
        h = rating.get(r.home_team, ELO_BASE)
        a = rating.get(r.away_team, ELO_BASE)
        pred_margin[i] = (h + ELO_HFA - a) / ELO_SCALE
        if pd.notna(r.home_score) and pd.notna(r.away_score):
            exp_h = 1 / (1 + 10 ** (-((h + ELO_HFA) - a) / 400))
            s_h = 1.0 if r.home_score > r.away_score else (0.0 if r.home_score < r.away_score else 0.5)
            rating[r.home_team] = h + ELO_K * (s_h - exp_h)
            rating[r.away_team] = a - ELO_K * (s_h - exp_h)
    return pred_margin

def build_bets(g):
    """Return long frame: one row per (game, strategy) bet with outcome in {1,0,push}."""
    g = g.copy()
    g["margin"] = g.home_score - g.away_score
    g["total_pts"] = g.home_score + g.away_score
    g["pred_margin"] = elo_lines(g)
    g["home_fav"] = g.spread_line > 0
    rows = []
    base = g[g.spread_line.notna() & g.margin.notna()].copy()
    out = []
    def ats_rows(d, pick_home_mask, name, family):
        d = d.copy()
        d["strategy"] = name
        d["family"] = family
        d["pick"] = np.where(pick_home_mask.loc[d.index], "home", "away")
        m = d.margin - d.spread_line   # >0 => home covers
        win = np.where(m == 0, np.nan, np.where(d.pick == "home", (m > 0).astype(float), (m < 0).astype(float)))
        d["outcome"] = win
        out.append(d)
    def tot_rows(d, pick_over_mask, name):
        d = d[d.total_line.notna() & d.total_pts.notna()].copy()
        d["strategy"] = name
        d["family"] = "TOTAL"
        d["pick"] = np.where(pick_over_mask.loc[d.index], "over", "under")
        m = d.total_pts - d.total_line
        d["outcome"] = np.where(m == 0, np.nan, np.where(d.pick == "over", (m > 0).astype(float), (m < 0).astype(float)))
        out.append(d)

    all_true = pd.Series(True, index=base.index)
    ats_rows(base, all_true, "S01 Home team ATS (every game)", "ATS")
    ats_rows(base, ~all_true, "S02 Away team ATS (every game)", "ATS")
    ats_rows(base, base.spread_line > 0, "S03 Favorite ATS (every game)", "ATS")
    ats_rows(base, base.spread_line < 0, "S04 Underdog ATS (every game)", "ATS")
    ats_rows(base[base.spread_line < 0], pd.Series(True, index=base.index), "S05 Home underdog ATS", "ATS")
    big = base[base.spread_line.abs() >= 7]
    ats_rows(big, big.spread_line > 0, "S06 Favorite of 7+ points ATS", "ATS")
    tot_rows(base, pd.Series(True, index=base.index), "S07 Over total (every game)")
    tot_rows(base, pd.Series(False, index=base.index), "S08 Under total (every game)")
    rest = base[(base.home_rest - base.away_rest).abs() >= 2]
    ats_rows(rest, (rest.home_rest > rest.away_rest), "S09 Rest edge >= 2 days ATS", "ATS")
    # S10: own model vs market line
    edge = base.pred_margin - base.spread_line
    e = base[edge.abs() >= ELO_EDGE_THRESHOLD]
    ats_rows(e, (edge.loc[e.index] > 0), "S10 Own Elo model vs line (edge >= 3 pts)", "MODEL")
    bets = pd.concat(out, ignore_index=True)
    bets = bets[bets.outcome.notna()].copy()
    bets["season"] = bets.season.astype(int)
    return bets, g

def split_of(season):
    for name, (a, b) in SPLITS.items():
        if a <= season <= b: return name
    return None

def summarize(bets):
    rows = []
    for strat, d in bets.groupby("strategy"):
        for sp in SPLITS:
            a, b = SPLITS[sp]
            x = d[(d.season >= a) & (d.season <= b)]
            n = len(x); k = int(x.outcome.sum())
            if n == 0:
                rows.append(dict(strategy=strat, split=sp, bets=0, wins=0, win_pct=np.nan, ci95_lo=np.nan, ci95_hi=np.nan, roi_110=np.nan, p_raw=np.nan, p_bonf=np.nan))
                continue
            wp = k / n
            lo, hi = wilson(k, n)
            roi = (k * PAYOUT - (n - k)) / n
            p = binomtest(k, n, BREAKEVEN, alternative="greater").pvalue
            rows.append(dict(strategy=strat, split=sp, bets=n, wins=k, win_pct=round(wp, 4),
                             ci95_lo=round(lo, 4), ci95_hi=round(hi, 4), roi_110=round(roi, 4),
                             p_raw=round(p, 6), p_bonf=round(min(1.0, p * BONFERRONI_DIVISOR), 6)))
    return pd.DataFrame(rows)

def season_stability(bets, strat):
    d = bets[(bets.strategy == strat) & (bets.season >= 2021) & (bets.season <= 2025)]
    res = []
    for s, x in d.groupby("season"):
        n = len(x); k = int(x.outcome.sum())
        roi = (k * PAYOUT - (n - k)) / n if n else np.nan
        res.append((s, n, roi))
    pos = sum(1 for _, n, r in res if n and r > 0)
    return pos, len(res), res

def main():
    DATA.mkdir(exist_ok=True)
    g = load()
    bets, gg = build_bets(g)
    summ = summarize(bets)
    summ.to_csv(DATA / "strategy_splits.csv", index=False)

    # ---- gates ----
    strategies = sorted(bets.strategy.unique())
    lb = []
    for strat in strategies:
        s = summ[summ.strategy == strat].set_index("split")
        ho = s.loc["holdout_2021_2025"]
        pos, tot, season_rows = season_stability(bets, strat)
        core = ["discovery_2006_2015", "validation_2016_2020", "holdout_2021_2025"]
        g2 = bool(all(s.loc[k].bets > 0 and s.loc[k].win_pct > BREAKEVEN for k in core))
        g1 = bool(ho.bets >= MIN_HOLDOUT_BETS)
        g3 = bool(pd.notna(ho.p_bonf) and ho.p_bonf < 0.05)
        g4 = bool(tot and pos / tot >= MIN_SEASON_POSITIVE_SHARE)
        g0 = False  # line provenance not verifiable from an official or documented source (I-10)
        passes = dict(G0=g0, G1=g1, G2=g2, G3=g3, G4=g4)
        failed = [k for k, v in passes.items() if not v]
        lb.append(dict(
            strategy=strat, family=bets[bets.strategy == strat].family.iloc[0],
            holdout_bets=int(ho.bets), holdout_win_pct=ho.win_pct, holdout_ci95=f"{ho.ci95_lo:.4f}-{ho.ci95_hi:.4f}" if pd.notna(ho.ci95_lo) else "",
            holdout_roi_110=ho.roi_110, holdout_p_raw=ho.p_raw, holdout_p_bonf=ho.p_bonf,
            discovery_win_pct=s.loc["discovery_2006_2015"].win_pct, validation_win_pct=s.loc["validation_2016_2020"].win_pct,
            forward_2026_bets=int(s.loc["forward_2026"].bets), forward_2026_win_pct=s.loc["forward_2026"].win_pct,
            forward_2026_roi_110=s.loc["forward_2026"].roi_110,
            holdout_positive_seasons=f"{pos}/{tot}",
            G0_provenance_verified=g0, G1_sample_ge_300=g1, G2_win_gt_breakeven_all_splits=g2,
            G3_bonferroni_p_lt_0_05=g3, G4_season_stability_ge_60pct=g4,
            G5_correlation_checked_in_portfolio="see strategy_correlations.csv",
            failed_gates=";".join(failed) if failed else "none",
            status="NOT ELIGIBLE (G0 fails: line provenance unverified)" if not g0 else ("PASS" if not failed else "FAIL"),
        ))
    lbdf = pd.DataFrame(lb)
    lbdf["rank_key"] = lbdf.holdout_p_bonf.fillna(9)
    lbdf = lbdf.sort_values(["rank_key", "holdout_roi_110"], ascending=[True, False]).drop(columns="rank_key")
    lbdf.insert(0, "rank", range(1, len(lbdf) + 1))
    lbdf.to_csv(DATA / "strategy_leaderboard.csv", index=False)

    # ---- registry ----
    reg = pd.DataFrame([
        ("S01","Home team ATS (every game)","ATS","Bet home side against spread_line"),
        ("S02","Away team ATS (every game)","ATS","Mirror of S01 (ignores pushes)"),
        ("S03","Favorite ATS (every game)","ATS","Favorite = side with spread_line sign"),
        ("S04","Underdog ATS (every game)","ATS","Mirror of S03"),
        ("S05","Home underdog ATS","ATS","Home side when spread_line < 0"),
        ("S06","Favorite of 7+ points ATS","ATS","|spread_line| >= 7, bet favorite"),
        ("S07","Over total (every game)","TOTAL","Bet over total_line"),
        ("S08","Under total (every game)","TOTAL","Mirror of S07"),
        ("S09","Rest edge >= 2 days ATS","ATS","Team with >= 2 more rest days than opponent"),
        ("S10","Own Elo model vs line (edge >= 3 pts)","MODEL","Elo K=20, HFA=65, 25 Elo/pt, 1/3 season reversion; bet when |model - line| >= 3"),
    ], columns=["strategy_id","name","family","definition"])
    reg.to_csv(DATA / "strategy_registry.csv", index=False)

    # ---- correlations (phi) on holdout outcomes, same games ----
    h = bets[(bets.season >= 2021) & (bets.season <= 2025)].copy()
    h["key"] = h.game_id
    piv = h.pivot_table(index="key", columns="strategy", values="outcome", aggfunc="first")
    corr = piv.corr(method="pearson", min_periods=30)   # phi for binary outcomes
    corr_long = corr.rename_axis(index="strategy_a", columns="strategy_b").stack().rename("phi").reset_index()
    corr_long["phi"] = corr_long.phi.round(4)
    corr_long["n_common_games"] = corr_long.apply(
        lambda r: int(piv[[r.strategy_a, r.strategy_b]].dropna().shape[0]), axis=1)
    corr_long.to_csv(DATA / "strategy_correlations.csv", index=False)

    # ---- parlays: all pairs, holdout, same-game overlap ----
    par = []
    names = strategies
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            both = piv[[a, b]].dropna()
            n = len(both)
            if n < 30:
                par.append(dict(leg_a=a, leg_b=b, common_games=n)); continue
            pa, pb = both[a].mean(), both[b].mean()
            joint = (both[a] * both[b]).mean()
            ind = pa * pb
            phi = np.corrcoef(both[a], both[b])[0, 1] if both[a].std() > 0 and both[b].std() > 0 else np.nan
            redundant = bool(phi == phi and abs(phi) >= 0.80)  # mirror/nested/near-identical bets: parlay is degenerate
            par.append(dict(leg_a=a, leg_b=b, common_games=n, redundant_mirror_or_nested=redundant,
                            p_leg_a=round(pa, 4), p_leg_b=round(pb, 4),
                            p_both_observed=round(joint, 4), p_both_if_independent=round(ind, 4),
                            dependence_gap=round(joint - ind, 4), phi=round(phi, 4),
                            breakeven_2leg=round(1 / PARLAY_DEC, 4),
                            parlay_roi_observed=round(joint * PARLAY_DEC - 1, 4),
                            parlay_roi_if_independent=round(ind * PARLAY_DEC - 1, 4)))
    pd.DataFrame(par).to_csv(DATA / "parlay_results.csv", index=False)

    # ---- own model lines for the upcoming 2026 Week 10 slate (research output, NOT a recommendation) ----
    wk = gg[(gg.season == 2026) & (gg.week == 10)].copy()
    wk["model_home_margin"] = wk.pred_margin.round(2)
    wk["market_spread_home_UNVERIFIED"] = wk.spread_line
    wk["edge_model_minus_line"] = (wk.pred_margin - wk.spread_line).round(2)
    wk["model_side_if_edge_ge_3"] = np.select(
        [wk.edge_model_minus_line >= ELO_EDGE_THRESHOLD, wk.edge_model_minus_line <= -ELO_EDGE_THRESHOLD],
        ["home", "away"], default="no bet")
    wk["market_total_UNVERIFIED"] = wk.total_line
    wk["game_status"] = np.where(wk.margin.notna(), "final (model line is pre-game)", "scheduled")
    wk[["game_id","gameday","away_team","home_team","game_status","model_home_margin","market_spread_home_UNVERIFIED",
        "edge_model_minus_line","model_side_if_edge_ge_3","market_total_UNVERIFIED"]].to_csv(
        DATA / "model_lines_2026_week10.csv", index=False)

    # ---- data checks ----
    checks = {}
    checks["source"] = {"file": str(SRC.name), "pinned_commit": PINNED,
                        "rows_all": int(len(pd.read_csv(SRC, usecols=[0]))),
                        "rows_regular_season": int(len(g)), "seasons": [int(g.season.min()), int(g.season.max())]}
    checks["games_per_season_reg"] = {int(k): int(v) for k, v in g.groupby("season").size().items()}
    comp = gg[gg.margin.notna()]
    checks["completed_games_reg"] = int(len(comp))
    checks["missing_spread_reg_2006plus"] = int(g[(g.season >= 2006)].spread_line.isna().sum())
    checks["missing_total_reg_2006plus"] = int(g[(g.season >= 2006)].total_line.isna().sum())
    checks["duplicate_game_ids"] = int(g.game_id.duplicated().sum())
    # sign-convention check: favorite (per spread sign) should win SU ~65-70% (sanity, not proof)
    s = comp[comp.spread_line.notna() & (comp.spread_line != 0)].copy()
    fav_home = s.spread_line > 0
    fav_won = np.where(fav_home, s.margin > 0, s.margin < 0)
    checks["sign_check_favorite_su_win_pct"] = round(float(fav_won.mean()), 4)
    # moneyline agreement: negative home moneyline should match home-favored spread
    ml = comp[comp.home_moneyline.notna() & comp.away_moneyline.notna() & comp.spread_line.notna()]
    agree = ((ml.home_moneyline < ml.away_moneyline) == (ml.spread_line > 0)).mean()
    checks["sign_check_moneyline_agreement"] = round(float(agree), 4)
    checks["n_sign_check_moneyline"] = int(len(ml))
    checks["dataset_2026_week10_check"] = {
        "game": "2026_10_WAS_NYG", "nfldata_score": "WAS 24 - NYG 21",
        "nflcom_score": "Commanders 24, Giants 21, FINAL (nfl.com schedule page)",
        "match": bool(((g.game_id == "2026_10_WAS_NYG") & (g.away_score == 24) & (g.home_score == 21)).any())}
    checks["team_codes_in_source_not_on_nfl_com"] = {"ARI": "NFL.com uses AZ", "STL/SD/OAK": "legacy codes, mapped to LA/LAC/LV for rating only"}
    checks["bets_total_rows"] = int(len(bets))
    checks["holdout_season_counts"] = {int(s): int(len(gg[gg.season == s])) for s in range(2021, 2026)}
    checks["pricing_assumption"] = "-110 both sides; breakeven 52.38%; NOT verified against any sportsbook"
    checks["elo_params"] = dict(K=ELO_K, home_field=ELO_HFA, points_per_elo=ELO_SCALE, season_reversion=ELO_REVERT, base=ELO_BASE, edge_threshold=ELO_EDGE_THRESHOLD)
    checks["bonferroni_divisor"] = BONFERRONI_DIVISOR
    (DATA / "data_checks.json").write_text(json.dumps(checks, indent=2, default=str))
    print(json.dumps({k: checks[k] for k in ["completed_games_reg","sign_check_favorite_su_win_pct","sign_check_moneyline_agreement","dataset_2026_week10_check"]}, indent=1, default=str))
    print(lbdf[["rank","strategy","holdout_bets","holdout_win_pct","holdout_roi_110","holdout_p_bonf","holdout_positive_seasons","failed_gates"]].to_string(index=False))

if __name__ == "__main__":
    main()
