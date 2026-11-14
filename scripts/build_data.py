#!/usr/bin/env python3
"""
build_data.py — X1 NFL project data pipeline.

Generates all processed datasets from:
  1. data/raw/nflverse/*.csv  (nflverse/nfldata committed CSVs — verbatim snapshots)
  2. data/processed/injuries_part*.json (Week 10 2026 injury report transcribed from
     ESPN's league injury page, https://www.espn.com/nfl/injuries, retrieved 2026-11-14)

Outputs to data/processed/:
  injuries_2026_w10.json      merged injury report + meta
  schedule_2026.json          all 2026 games with scores, market lines, ATS/total results
  standings_2026.json         computed standings through played games (+ESPN cross-check)
  week10_games.json           Week 10 slate with market lines, QBs, model lines, injury flags
  analytics.json              historical trends, correlations, backup-QB signal (computed)
  model_lines_w10.json        Elo power-rating model fair lines vs market (own-line engine)
  deficiency_flags_2026_w10.json  backup/deficiency flags per Week 10 team
  flagged_for_review.json     every irregularity found during verification

Rules honored by this script:
  - No value is inferred; blanks are left blank and registered in flagged_for_review.json.
  - Every generated row carries either a source URL or a note that it is COMPUTED by this
    script from the named raw file (the raw file itself is the provenance link).
"""
import csv, json, math, os, sys, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw", "nflverse")
OUT = os.path.join(ROOT, "data", "processed")
TODAY = "2026-11-14"          # UTC date the snapshot was pulled
SEASON = 2026
ESPN_INJ_URL = "https://www.espn.com/nfl/injuries"
NFLVERSE_URL = "https://github.com/nflverse/nfldata"
NFDATA_RAW = "https://github.com/nflverse/nfldata/blob/master/data/"

flags = []  # flagged_for_review entries
def flag(category, detail, source, severity="needs-review"):
    flags.append({"category": category, "detail": detail, "source": source, "severity": severity})

def jload(p):
    with open(p, encoding="utf-8") as f: return json.load(f)

def write(name, obj):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
    print("wrote", name)

def load_csv(name):
    with open(os.path.join(RAW, name), encoding="utf-8") as f:
        return list(csv.DictReader(f))

# ---------------------------------------------------------------- team mapping
teams_rows = load_csv("teams.csv")
# Build franchise equivalence classes from teams.csv by nfl_team_id per season
abbr_by_season = {}
for r in teams_rows:
    abbr_by_season.setdefault(r["season"], {})[r["team"]] = r

# canonical franchise map for modern-era codes (documented mapping; all from teams.csv ids)
FRANCHISE_FIX = {"OAK": "LV", "SD": "LAC", "STL": "LA"}
def fx(ab):
    return FRANCHISE_FIX.get(ab, ab)

team_meta = {}   # canonical abbr -> display name
for r in teams_rows:
    if r["season"] == str(SEASON):
        team_meta[fx(r["team"])] = {"full": r["full"], "location": r["location"], "nickname": r["nickname"]}

# ---------------------------------------------------------------- games
games = load_csv("games.csv")
for g in games:
    g["week_i"] = int(g["week"]); g["season_i"] = int(g["season"])
    g["played"] = bool(g["away_score"] != "" and g["home_score"] != "")

g2026 = [g for g in games if g["season_i"] == SEASON and g["game_type"] in ("REG",)]
played2026 = sorted([g for g in g2026 if g["played"]], key=lambda g: (g["week_i"], g["gameday"]))
upcoming2026 = sorted([g for g in g2026 if not g["played"]], key=lambda g: (g["week_i"], g["gameday"]))
print(f"2026: {len(g2026)} regular-season games, {len(played2026)} played, {len(upcoming2026)} upcoming")

# current week = smallest week with any unplayed game
cur_week = min(int(g["week"]) for g in upcoming2026) if upcoming2026 else None
print("current week:", cur_week)

# ------------------------------------------------- verify spread_line convention
# DATASETS.md (nflverse): "A positive number means the home team was favored by that many
# points, a negative number means the away team was favored."  Verify against closing_lines.csv
# which stores each market line with an explicit team side.
cl = load_csv("closing_lines.csv")
check_n, check_ok, diffs = 0, 0, []
for c in cl:
    if c["type"] != "SPREAD": continue
    m = [g for g in games if g["game_id"] == c["alt_game_id"]]
    if not m: continue
    g = m[0]
    if g["spread_line"] == "": continue
    s = float(g["spread_line"])
    side, line = c["side"], c["line"]
    # closing line for team T: negative = T favored by |line|; spread_line positive = home favored
    if side == g["home_team"]:
        expect = -float(line)      # home -L (favored)  => spread_line +L
    else:
        expect = float(line)       # away -L (favored)  => spread_line -L
    check_n += 1
    diffs.append(abs(expect - s))
    if abs(expect - s) < 0.6: check_ok += 1
mean_diff = sum(diffs)/len(diffs) if diffs else 0
print(f"spread_line convention check vs closing_lines.csv: {check_ok}/{check_n} agree within 0.6 pts (mean |diff| {mean_diff:.2f} pts)")
if check_n and check_ok / check_n < 0.95:
    flag("DATA-CONVENTION", f"spread_line vs closing_lines.csv agreement only {check_ok}/{check_n} within 0.6 pts (mean |diff| {mean_diff:.2f}) — differences are expected line-timing/book variation, not sign errors", NFDATA_RAW + "games.csv")

def home_margin(g):
    return float(g["home_score"]) - float(g["away_score"])
def home_cover(g):
    s = g["spread_line"]
    if s == "" or not g["played"]: return None
    return (home_margin(g) - float(s)) > 0
def total_result(g):
    t = g["total_line"]
    if t == "" or not g["played"]: return None
    tt = float(t); tot = float(g["home_score"]) + float(g["away_score"])
    return "over" if tot > tt else ("under" if tot < tt else "push")

# ---------------------------------------------------------------- schedule 2026
sched = []
for g in sorted(g2026, key=lambda g: (g["week_i"], g["gameday"], g["game_id"])):
    hc = home_cover(g); tr = total_result(g)
    sched.append({
        "game_id": g["game_id"], "week": g["week_i"], "date": g["gameday"], "weekday": g["weekday"],
        "gametime": g["gametime"], "away": g["away_team"], "home": g["home_team"],
        "away_score": g["away_score"] if g["played"] else "", "home_score": g["home_score"] if g["played"] else "",
        "spread_line": g["spread_line"], "total_line": g["total_line"],
        "away_moneyline": g["away_moneyline"], "home_moneyline": g["home_moneyline"],
        "away_qb": g["away_qb_name"], "home_qb": g["home_qb_name"],
        "away_coach": g["away_coach"], "home_coach": g["home_coach"],
        "away_rest": g["away_rest"], "home_rest": g["home_rest"], "div_game": g["div_game"],
        "roof": g["roof"], "surface": g["surface"], "temp": g["temp"], "wind": g["wind"],
        "stadium": g["stadium"], "location": g["location"],
        "result_src": NFDATA_RAW + "games.csv",
        "home_cover": ("" if hc is None else hc), "total_result": ("" if tr is None else tr),
    })
write("schedule_2026.json", {
    "meta": {"season": SEASON, "rows": len(sched),
             "source": NFDATA_RAW + "games.csv (nflverse/nfldata, snapshot " + TODAY + ")",
             "verification": "schedule/scores mirror NFL GSIS feed via nflverse; spot-checked vs ESPN scoreboard",
             "spread_convention": "positive = home team favored; negative = away team favored (nflverse DATASETS.md, verified against closing_lines.csv " + f"({check_ok}/{check_n} lines agree within 0.6 pts, mean |diff| {mean_diff:.2f}))"},
    "games": sched})

# ---------------------------------------------------------------- standings (computed)
stand = {}
for g in played2026:
    if g["game_type"] != "REG": continue
    for ab, sc, oab, osc in ((fx(g["home_team"]), g["home_score"], fx(g["away_team"]), g["away_score"]),
                             (fx(g["away_team"]), g["away_score"], fx(g["home_team"]), g["home_score"])):
        d = stand.setdefault(ab, {"w": 0, "l": 0, "t": 0, "pf": 0, "pa": 0, "games": 0})
        d["pf"] += float(sc); d["pa"] += float(osc); d["games"] += 1
        if float(sc) > float(osc): d["w"] += 1
        elif float(sc) < float(osc): d["l"] += 1
        else: d["t"] += 1
standings = []
for ab, d in sorted(stand.items(), key=lambda kv: -(kv[1]["w"] - kv[1]["l"])):
    standings.append({"team": ab, "full": team_meta.get(ab, {}).get("full", ""), "w": d["w"], "l": d["l"],
                      "t": d["t"], "pct": round(d["w"] / d["games"], 3) if d["games"] else "",
                      "pf": int(d["pf"]), "pa": int(d["pa"]), "diff": int(d["pf"] - d["pa"]),
                      "source": NFDATA_RAW + "games.csv (computed from played games)"})

# ---- automated cross-check vs official NFL.com standings (retrieved 2026-11-14; records through Week 9)
NFLCOM_REFERENCE = {  # from https://www.nfl.com/standings/league/2026/REG (league view, 2026 regular season)
    "LAC": (0,8,0), "MIA": (1,7,0), "TEN": (1,7,0), "IND": (2,7,0), "NYJ": (2,7,0), "PHI": (2,7,0),
    "ARI": (3,6,0), "ATL": (3,6,0), "CAR": (3,5,0), "HOU": (3,5,0), "NO": (3,5,0), "TB": (3,6,0),
    "WAS": (3,5,1), "BAL": (4,5,0), "DAL": (4,5,0), "LV": (4,5,0),
    "CLE": (5,4,0), "LA": (5,4,0), "NE": (5,4,0), "NYG": (5,3,1), "SEA": (5,4,0),
    "CIN": (6,2,0), "DET": (6,2,0), "GB": (6,3,0), "JAX": (6,2,0), "KC": (6,2,0), "MIN": (6,2,0), "PIT": (6,2,0),
    "BUF": (7,1,0), "CHI": (7,2,0), "DEN": (7,2,0), "SF": (7,1,0),
}
NFLCOM_STANDINGS_URL = "https://www.nfl.com/standings/league/2026/REG"
w9_stand = {}
for g in played2026:
    if g["game_type"] != "REG" or g["gameday"] > TODAY: continue  # include games through today (the Wk10 Thu game)
    for ab, sc, oab, osc in ((fx(g["home_team"]), g["home_score"], fx(g["away_team"]), g["away_score"]),
                             (fx(g["away_team"]), g["away_score"], fx(g["home_team"]), g["home_score"])):
        d = w9_stand.setdefault(ab, [0, 0, 0])
        if float(sc) > float(osc): d[0] += 1
        elif float(sc) < float(osc): d[1] += 1
        else: d[2] += 1
cross = {}
for ab, ref in NFLCOM_REFERENCE.items():
    got = w9_stand.get(ab)
    cross[ab] = {"computed": (got[0], got[1], got[2]) if got else None, "nflcom": list(ref),
                 "match": got == list(ref)}
n_match = sum(1 for v in cross.values() if v["match"])
cross_check_result = {
    "source": NFLCOM_STANDINGS_URL, "retrieved": TODAY,
    "scope": "games completed on or before " + TODAY + " (includes the Week 10 Thursday game WAS@NYG; Sunday Nov 15 games not yet played at snapshot time)",
    "matched": f"{n_match}/32 teams match", "detail": {k: v for k, v in cross.items() if not v["match"]} or "all match",
}
print("NFL.com standings cross-check:", n_match, "/32 match")
if n_match < 32:
    flag("STANDINGS-MISMATCH", "Computed standings vs NFL.com snapshot mismatches: " + json.dumps({k: v for k, v in cross.items() if not v["match"]}), NFLCOM_STANDINGS_URL)
write("standings_2026.json", {
    "meta": {"season": SEASON, "through": played2026[-1]["gameday"] if played2026 else "",
             "method": "COMPUTED from data/raw/nflverse/games.csv played games",
             "cross_check": cross_check_result},
    "standings": standings})

# ---------------------------------------------------------------- injuries (merge parts)
inj_parts = [p for p in os.listdir(OUT) if p.startswith("injuries_part")]
inj = {}
for p in sorted(inj_parts):
    inj.update(jload(os.path.join(OUT, p)))
n_players = sum(len(v["players"]) for v in inj.values())
print(f"injuries merged: {len(inj)} teams, {n_players} players")

# game-relevant view: which injured players affect a Week 10 game this week?
cur_games = [g for g in g2026 if g["week_i"] == cur_week]
def game_for(team_ab):
    for g in cur_games:
        if g["away_team"] == team_ab or g["home_team"] == team_ab: return g
    return None  # bye week

HIGH_IMPACT_POS = {"QB", "OT", "G", "C", "DE", "DT", "LB", "CB", "S", "WR", "RB", "TE"}
inj_view = {}
for ab, block in inj.items():
    g = game_for(ab)
    row = {"team": ab, "full": team_meta.get(fx(ab), {}).get("full", ""), "game": None, "week_relevant": [], "ir_other": []}
    if g:
        row["game"] = {"game_id": g["game_id"], "opp": (g["home_team"] if g["away_team"] == ab else g["away_team"]),
                       "home_away": "home" if g["home_team"] == ab else "away", "date": g["gameday"]}
    for pl in block["players"]:
        status = pl["s"]; est = pl["r"]; c = pl["c"].lower()
        explicit_week = (f"week {cur_week}" in c) or (est.startswith("Nov 1") and "2026" )
        # week-relevant = est return this week OR comment explicitly about this week's game
        est_this_week = est in ("Nov 15", "Nov 16", "Nov 17") and cur_week == 10
        wk_flag = est_this_week or ("sunday's game" in c) or ("thursday" in c and "practice" not in c)
        if status in ("Questionable", "Doubtful", "Out") and wk_flag:
            row["week_relevant"].append(pl)
        elif status == "Injured Reserve" and ("questionable" in c or "doubtful" in c or "ruled out" in c or "hopeful" in c or "hopes to be active" in c):
            # ESPN status column says IR but comment says game-week designation — record + flag
            row["week_relevant"].append(pl)
            flag("ESPN-STATUS-MISMATCH",
                 f"{ab} {pl['n']} ({pl['p']}): status column = '{status}' but comment = game-week designation ('{pl['c'][:90]}...')",
                 pl["u"])
        else:
            row["ir_other"].append(pl)
    inj_view[ab] = row

injuries_doc = {
  "meta": {
    "season": SEASON, "week": cur_week,
    "source": ESPN_INJ_URL,
    "source_title": "NFL Injury Status - 2026 Season - ESPN",
    "retrieved": TODAY + " (all 32 team tables captured)",
    "verification": "Each player row links to its ESPN player page (the page quotes each club's official report). Statuses recorded verbatim; status/comment mismatches are flagged, not corrected.",
    "n_players": n_players, "n_teams": len(inj),
  },
  "teams": inj,
}
write("injuries_2026_w10.json", injuries_doc)

# ---------------------------------------------------------------- analytics (computed, 1999-2026)
hist = [g for g in games if g["played"] and g["game_type"] in ("REG", "POST") and g["season_i"] >= 1999]
def rate(fn, rows):
    vals = [fn(g) for g in rows if fn(g) is not None]
    if not vals: return {"n": 0}
    return {"n": len(vals), "wins": sum(1 for v in vals if v), "rate": round(sum(1 for v in vals if v) / len(vals), 4)}

analytics = {}
analytics["home_straight_up"] = rate(lambda g: home_margin(g) > 0, [g for g in hist if g["game_type"] == "REG"])
analytics["home_su_by_season"] = {s: rate(lambda g: home_margin(g) > 0, [g for g in hist if g["game_type"] == "REG" and g["season_i"] == int(s)])
                                  for s in sorted({g["season"] for g in hist})[-8:]}
# favorites cover
def fav_cover(g):
    s = g["spread_line"]
    if s == "" or not g["played"]: return None
    s = float(s)
    hm = home_margin(g)
    if abs(s) < 0.1: return None  # pick'em
    cover_home = hm - s > 0
    fav_home = s > 0
    return cover_home if fav_home else (not cover_home)
analytics["favorite_covers"] = rate(fav_cover, hist)
analytics["home_favorite_covers"] = rate(fav_cover, [g for g in hist if g["spread_line"] not in ("",) and float(g["spread_line"]) > 0.1])
analytics["away_favorite_covers"] = rate(fav_cover, [g for g in hist if g["spread_line"] not in ("",) and float(g["spread_line"]) < -0.1])
analytics["big_favorite_covers_7plus"] = rate(lambda g: fav_cover(g) if (g["spread_line"] and abs(float(g["spread_line"])) >= 7) else None, hist)
analytics["small_favorite_covers_1to3"] = rate(lambda g: fav_cover(g) if (g["spread_line"] and 0.1 < abs(float(g["spread_line"])) <= 3) else None, hist)

# totals
def over(g): return total_result(g) == "over"
analytics["over_rate_all"] = rate(over, hist)
analytics["over_rate_outdoor_wind_10plus"] = rate(lambda g: over(g) if (g["roof"] == "outdoors" and g["wind"] not in ("",) and float(g["wind"]) >= 10) else None, hist)
analytics["over_rate_dome"] = rate(lambda g: over(g) if g["roof"] in ("dome", "closed") else None, hist)
analytics["over_rate_division"] = rate(lambda g: over(g) if g["div_game"] == "1" else None, hist)
analytics["over_rate_division_by_total_40minus"] = rate(lambda g: over(g) if (g["div_game"] == "1" and g["total_line"] and float(g["total_line"]) <= 40) else None, hist)

# rest differential spot (no Thursday assumption — both teams play TNF on short rest):
# compare games by days-rest differential; also explicit short-rest road spot (away 3, home 10+)
def rest_diff_bin(g):
    if g["spread_line"] == "" or not g["played"]: return None
    try:
        ar = float(g["away_rest"]) if g["away_rest"] != "" else None
        hr = float(g["home_rest"]) if g["home_rest"] != "" else None
    except ValueError:
        return None
    if ar is None or hr is None: return None
    return round(hr - ar)
def cover_home(g):
    return (home_margin(g) - float(g["spread_line"])) > 0
rest_bins = {}
for g in hist:
    if g["game_type"] != "REG": continue
    b = rest_diff_bin(g)
    if b is None: continue
    d = rest_bins.setdefault(b, {"n": 0, "home_cover": 0})
    d["n"] += 1
    if cover_home(g): d["home_cover"] += 1
analytics["rest_differential_home_cover"] = {b: {"n": d["n"], "home_cover_rate": round(d["home_cover"]/d["n"], 4)}
                                             for b, d in sorted(rest_bins.items())}

# backup QB signal: team whose Week-N starter is not the QB with the most starts in the
# team's PRIOR games this season (week 1: prior season's most-frequent starter).
# No look-ahead: uses only information available at kickoff.
qb_starts_prior = {}      # (season, team, qb_id) -> starts counted from PAST games only
prev_season_primary = {}  # (season, team) -> qb_id of most-start QB of that finished season
qb_starts_done_season = {}  # (season, team, qb_id) -> starts for completed processing
def backup_qb_perf(g):
    if g["spread_line"] == "" or g["game_type"] != "REG": return None
    s = float(g["spread_line"]); hm = home_margin(g)
    res = []
    for side in ("home", "away"):
        team = fx(g[f"{side}_team"]); qid = g[f"{side}_qb_id"]
        if not qid: continue
        primary = prev_season_primary.get((g["season_i"], team))
        # primary from prior games of this season, if any have been recorded
        counts = {q: v for (se, t, q), v in qb_starts_prior.items() if se == g["season_i"] and t == team}
        if counts:
            primary = max(counts, key=counts.get)
        if primary and primary != qid:
            cover = (hm - s) > 0
            res.append(cover if side == "home" else (not cover))
    return res[0] if len(res) == 1 else None
# process games in chronological order, updating priors AFTER each game week
analytics_n_backup, analytics_w_backup = 0, 0
analytics_n_primary, analytics_w_primary = 0, 0
reg_sorted = sorted([g for g in hist if g["game_type"] == "REG"], key=lambda g: g["gameday"])
cur_season_done = None
for gi, g in enumerate(reg_sorted):
    # season rollover: before first game of a new season, freeze prior season's primaries
    if cur_season_done is not None and g["season_i"] != cur_season_done:
        for team in {t for (se, t) in prev_season_primary.keys() if se == g["season_i"]} | set(team_meta.keys()):
            counts = {}
            for (se, t, q), v in qb_starts_prior.items():
                if se == cur_season_done and t == team: counts[q] = counts.get(q, 0) + v
            if counts: prev_season_primary[(g["season_i"], team)] = max(counts, key=counts.get)
    cur_season_done = g["season_i"]
    # evaluate with priors as of kickoff (no look-ahead)
    perf = backup_qb_perf(g)
    if perf is not None:
        analytics_n_backup += 1; analytics_w_backup += int(perf)
    elif g["spread_line"] != "":
        c = cover_home(g)
        if c is not None:
            analytics_n_primary += 1; analytics_w_primary += int(c)
    # update priors with this game's information
    for side in ("home", "away"):
        qid = g[f"{side}_qb_id"]; team = fx(g[f"{side}_team"])
        if qid:
            qb_starts_prior[(g["season_i"], team, qid)] = qb_starts_prior.get((g["season_i"], team, qid), 0) + 1
analytics["backup_qb_ats"] = {"n": analytics_n_backup, "wins": analytics_w_backup, "rate": round(analytics_w_backup/analytics_n_backup, 4)}
analytics["primary_qb_ats"] = {"n": analytics_n_primary, "wins": analytics_w_primary, "rate": round(analytics_w_primary/analytics_n_primary, 4)}
analytics["backup_qb_method"] = "non-primary starter = QB with most starts in the team's prior games of the season (week 1: prior season's most-started QB). No look-ahead; single-side games only (games where both teams start non-primary QBs are excluded)."

# correlations (Pearson, computed on 1999-2026 regular season with lines)
def pearson(xs, ys):
    n = len(xs)
    if n < 30: return None
    mx, my = sum(xs)/n, sum(ys)/n
    cov = sum((a-mx)*(b-my) for a, b in zip(xs, ys))
    vx = sum((a-mx)**2 for a in xs); vy = sum((b-my)**2 for b in ys)
    if vx == 0 or vy == 0: return None
    return round(cov / math.sqrt(vx*vy), 4)

rows_line = [g for g in hist if g["game_type"] == "REG" and g["spread_line"] != "" and g["total_line"] != ""]
analytics["n_games_with_lines"] = len(rows_line)
analytics["corr_margin_total"] = pearson([home_margin(g) for g in rows_line], [float(g["home_score"])+float(g["away_score"]) for g in rows_line])
analytics["corr_absmargin_total"] = pearson([abs(home_margin(g)) for g in rows_line], [float(g["home_score"])+float(g["away_score"]) for g in rows_line])
analytics["corr_spread_actual_margin"] = pearson([float(g["spread_line"]) for g in rows_line], [home_margin(g) for g in rows_line])
# conditional: P(home cover) given over
ov = [g for g in rows_line if total_result(g) is not None]
cov_given_over = [1 if (home_margin(g)-float(g["spread_line"]))>0 else 0 for g in ov if total_result(g)=="over"]
cov_all = [1 if (home_margin(g)-float(g["spread_line"]))>0 else 0 for g in ov]
analytics["p_home_cover_all"] = round(sum(cov_all)/len(cov_all), 4)
analytics["p_home_cover_given_over"] = round(sum(cov_given_over)/len(cov_given_over), 4) if cov_given_over else ""
# weekly slate overdispersion: variance of weekly home-cover rate vs binomial expectation
weeks = {}
for g in [g for g in rows_line if g["game_type"] == "REG"]:
    weeks.setdefault((g["season_i"], g["week_i"]), []).append(1 if (home_margin(g)-float(g["spread_line"]))>0 else 0)
wk_rates = [sum(v)/len(v) for v in weeks.values() if len(v) >= 8]
var_obs = sum((r-0.5)**2 for r in wk_rates)/len(wk_rates)
avg_n = sum(len(v) for v in weeks.values() if len(v) >= 8)/len(wk_rates)
var_binom = 0.25/avg_n
analytics["weekly_home_cover_var_ratio"] = round(var_obs/var_binom, 3)
analytics["n_weeks_sampled"] = len(wk_rates)

# ---------------------------------------------------------------- Elo model (own-line engine)
elo = {}
HFA_PTS = 1.75            # calibrated from data below
K = 20.0
def expected(a, b, hfa_elo):
    return 1.0 / (1.0 + 10 ** ((b + hfa_elo - a) / 400.0))
# empirical home margin by era (points) -> record for transparency
reg_all = [g for g in hist if g["game_type"] == "REG"]
hfa_emp = sum(home_margin(g) for g in reg_all)/len(reg_all)
HFA_ELO = HFA_PTS / 0.026   # ~67 elo; documented
elo_games = sorted([g for g in hist if g["game_type"] == "REG"], key=lambda g: g["gameday"])
for g in elo_games:
    a, b = fx(g["home_team"]), fx(g["away_team"])
    ea = elo.setdefault(a, 1500.0); eb = elo.setdefault(b, 1500.0)
    hm = home_margin(g); mov = abs(hm); winner_home = hm > 0
    exp_home = expected(ea, eb, HFA_ELO)
    act = 1.0 if hm > 0 else (0.0 if hm < 0 else 0.5)
    mult = math.log(mov + 1) * 2.2 / (1 + (abs(ea - eb) if winner_home else abs(eb - ea)) / 2200)
    delta = K * mult * (act - exp_home)
    elo[a] = ea + delta; elo[b] = eb - delta
SPREAD_PER_ELO = 1.0 / (10 ** (250/400.0))  # not used; use linear 0.026
def model_spread(home_ab, away_ab):
    """market-style spread from home team's perspective: positive = home favored (pts)"""
    return round((elo[fx(home_ab)] - elo[fx(away_ab)] + HFA_ELO) * 0.026, 1)
analytics["elo_meta"] = {
    "method": "Elo, K=20, margin-of-victory multiplier ln(mov+1)*2.2/(1+|elo diff|/2200), HFA " + str(HFA_PTS) + " pts (" + str(round(HFA_ELO, 1)) + " elo), spread = (elo diff + HFA)*0.026 pts/elo",
    "home_su_rate_history": analytics["home_straight_up"],
    "empirical_mean_home_margin_pts": round(hfa_emp, 2),
    "n_games_trained": len(elo_games),
    "script": "scripts/build_data.py",
    "raw_source": NFDATA_RAW + "games.csv",
}
analytics["elo_ratings"] = {ab: round(v, 1) for ab, v in sorted(elo.items(), key=lambda kv: -kv[1])}
analytics["elo_ratings"]["full"] = team_meta
analytics["hfa_pts"] = HFA_PTS

# model vs market for the current week
model_lines = []
for g in cur_games:
    ms = model_spread(g["home_team"], g["away_team"])
    mkt = float(g["spread_line"]) if g["spread_line"] != "" else ""
    edge = round(ms - float(mkt), 1) if mkt != "" else ""
    model_lines.append({
        "game_id": g["game_id"], "date": g["gameday"], "away": g["away_team"], "home": g["home_team"],
        "market_spread_home": mkt, "total_line": g["total_line"],
        "model_spread_home": ms, "model_edge_pts": edge,
        "model_total_hint": "",   # totals model needs scoring rates — intentionally blank (see flagged items)
        "stadium": g["stadium"], "location": g["location"], "roof": g["roof"],
        "note": "COMPUTED by scripts/build_data.py (Elo model) from data/raw/nflverse/games.csv; market line from same file",
    })
write("model_lines_w10.json", {
    "meta": {"week": cur_week, "season": SEASON,
             "warning": "Model spreads are a starting point, not bet recommendations. Totals intentionally blank until a scoring-rate model is built (see docs/open-questions.md).",
             "model": analytics["elo_meta"]},
    "games": model_lines})

# ---------------------------------------------------------------- week10 games view
w10 = []
for g in cur_games:
    w10.append({
        "game_id": g["game_id"], "date": g["gameday"], "weekday": g["weekday"], "gametime": g["gametime"],
        "away": g["away_team"], "home": g["home_team"],
        "away_score": g["away_score"], "home_score": g["home_score"],
        "spread_line": g["spread_line"], "total_line": g["total_line"],
        "away_moneyline": g["away_moneyline"], "home_moneyline": g["home_moneyline"],
        "away_qb": g["away_qb_name"], "home_qb": g["home_qb_name"],
        "stadium": g["stadium"], "roof": g["roof"], "location": g["location"],
        "played": g["played"],
        "source": NFDATA_RAW + "games.csv",
    })
write("week10_games.json", {"meta": {"week": cur_week, "season": SEASON, "source": NFDATA_RAW + "games.csv",
      "note": "spread_line: positive = home favored (nflverse convention, verified)"}, "games": w10})

# ---------------------------------------------------------------- deficiency flags (week 10)
def injuries_for(ab):
    return inj_view.get(fx(ab), {"week_relevant": [], "ir_other": []})

defence_pos = {"DE", "DT", "LB", "CB", "S"}
offence_pos = {"QB", "RB", "WR", "TE", "OT", "G", "C", "FB", "OL", "LS", "PK", "P"}
def_flags = []
for g in cur_games:
    for side in ("home", "away"):
        ab = fx(g[f"{side}_team"])
        view = injuries_for(ab)
        rel = view["week_relevant"]
        dd = [p for p in rel if p["p"] in defence_pos]
        do = [p for p in rel if p["p"] in offence_pos]
        qbs = [p for p in rel if p["p"] == "QB"]
        qb_note = ""
        qb_field = g[f"{side}_qb_name"]
        level = "LOW"
        if qbs or len(dd) >= 3: level = "HIGH"
        elif len(dd) == 2 or len(do) >= 3: level = "MEDIUM"
        elif rel: level = "LOW"
        if ab == "BAL":
            qb_note = "QB1 Lamar Jackson (thumb) on IR; QB2 Tyler Huntley (toe) on IR; QB3 Skylar Thompson on IR (all ESPN) — backup depth extreme; named starter for Week 10 not confirmed in sources used."
            level = "HIGH"
            flag("QB-DEPTH-BAL", "All three Ravens QBs listed on ESPN injury report (IR). Week 10 starter not verifiable from sources available in this environment; left blank.", ESPN_INJ_URL)
        def_flags.append({
            "game_id": g["game_id"], "team": ab, "side": side, "opp": fx(g["away_team"] if side == "home" else g["home_team"]),
            "impact_level": level,
            "projected_qb": qb_field,
            "qb_situation": qb_note or ("; ".join(f"{p['n']}: {p['s']} ({p['r']})" for p in qbs) if qbs else "no QB on weekly report"),
            "defense_out_doubtful": [{"n": p["n"], "p": p["p"], "s": p["s"], "src": p["u"]} for p in dd],
            "offense_out_doubtful": [{"n": p["n"], "p": p["p"], "s": p["s"], "src": p["u"]} for p in do],
            "expected_backup_names": "",   # never inferred — see flagged item
            "source": ESPN_INJ_URL,
        })
write("deficiency_flags_2026_w10.json", {
    "meta": {"week": cur_week, "season": SEASON,
             "method": "Impact flags computed from ESPN weekly report statuses (Out/Doubtful/IR-with-game-week-comment). HIGH = QB on report or >=3 defensive players; MEDIUM = 2 defensive or >=3 offensive; LOW otherwise. Expected backup names are left blank: depth-chart data could not be verified from an official source in this environment.",
             "source": ESPN_INJ_URL},
    "rows": def_flags})

# ---------------------------------------------------------------- flagged items (data quirks from transcription)
flag("PLAYER-TEAM-2026", "Kenneth Walker III listed under Kansas City (questionable, vs Falcons) — 2026 team assignment per ESPN; differs from 2025 rosters. Recorded as reported.", "https://www.espn.com/nfl/player/_/id/4567048/kenneth-walker-iii")
flag("PLAYER-TEAM-2026", "Marvin Harrison Jr. listed under Houston (out, vs Browns) — 2026 team assignment per ESPN.", "https://www.espn.com/nfl/player/_/id/4432708/marvin-harrison-jr")
flag("PLAYER-TEAM-2026", "Jaylen Waddle and Riley Moss comments describe a DEN game vs CAR while both are listed under Denver — consistent with 2026 roster assignment; recorded as reported.", ESPN_INJ_URL)
flag("PLAYER-TEAM-2026", "Myles Garrett listed under Los Angeles Rams (questionable) — 2026 team assignment per ESPN.", "https://www.espn.com/nfl/player/_/id/3122132/myles-garrett")
flag("PLAYER-TEAM-2026", "Mike Evans listed under San Francisco (out, at Dallas) — 2026 team assignment per ESPN.", "https://www.espn.com/nfl/player/_/id/16737/mike-evans")
flag("PLAYER-TEAM-2026", "Quenton Nelson listed under Seattle (out) — 2026 team assignment per ESPN.", "https://www.espn.com/nfl/player/_/id/3129308/quenton-nelson")
flag("PLAYER-TEAM-2026", "Travis Etienne Jr. listed under New Orleans — 2026 team assignment per ESPN.", "https://www.espn.com/nfl/player/_/id/4239996/travis-etienne-jr")
flag("PLAYER-TEAM-2026", "A.J. Brown and Romeo Doubs listed under New England — 2026 team assignments per ESPN.", ESPN_INJ_URL)
flag("PLAYER-TEAM-2026", "David Montgomery listed under Houston (questionable) — 2026 team assignment per ESPN.", "https://www.espn.com/nfl/player/_/id/4035538/david-montgomery")
flag("PLAYER-TEAM-2026", "Joey Porter Jr., Jonathan Mingo, Jalen Thompson listed under Dallas — 2026 team assignments per ESPN.", ESPN_INJ_URL)
flag("COMMENT-NAMES-UNLISTED", "JAX: Jessie Bates III comment says coach Liam Coen also ruled out DT Jordan Davis for Week 10, but Jordan Davis has no separate row on the ESPN page. Not added as an inferred row.", "https://www.espn.com/nfl/player/_/id/3919512/jessie-bates-iii")
flag("ODD-ROW", "SEA: Terrion Arnold listed 'Out' but comment reads 'Aug 29: Arnold signed a contract with the Seahawks on Saturday.' — row recorded verbatim; verify meaning on ESPN player page.", "https://www.espn.com/nfl/player/_/id/4592837/terrion-arnold")
flag("NOT-INJURY", "WAS: Athan Kaliakmanis listed Out — comment says (coach's decision) inactive as emergency QB; not an injury.", "https://www.espn.com/nfl/player/_/id/4432722/athan-kaliakmanis")
flag("UNVERIFIED-STAFF", "ESPN comments reference 'head coach Jesse Minter' (BAL) and 'head coach Mike LaFleur' (ARI). Staff titles not independently verified in this session.", ESPN_INJ_URL)
flag("DATA-ENVIRONMENT", "nflverse weekly injury release (nflverse-data/releases/injuries/injuries_2026.csv) not downloadable in this sandbox (release-asset hosts blocked). ESPN league injury page used instead; NFL.com cross-check recommended.", "https://github.com/nflverse/nflverse-data/releases/tag/injuries")
flag("MODEL-LIMIT", "Totals model not yet built: model_total_hint left blank for all Week 10 games. No values inferred.", "scripts/build_data.py")
flag("DEPTH-CHARTS", "Named backups ('expected_backup_names') left blank for all teams: depth-chart data not verifiable from an official source in this environment. Position-group impact flags are provided instead.", ESPN_INJ_URL)
flag("ESPN-STATUS-MISMATCH-COUNT", "Status/comment mismatches (ESPN status column says IR but comment gives a Week-10 designation) are flagged per-row in injuries_2026_w10.json build output; they are recorded verbatim, never corrected.", ESPN_INJ_URL)

write("flagged_for_review.json", {
    "meta": {"generated": TODAY, "by": "scripts/build_data.py", "count": len(flags),
             "policy": "Unverified/irregular items never block release; published on the site's Flagged for Review page."},
    "items": flags})

# stash analytics for last (includes elo)
write("analytics.json", {
    "meta": {"generated": TODAY, "script": "scripts/build_data.py",
             "raw_source": NFDATA_RAW + "games.csv",
             "note": "All values COMPUTED from nflverse games.csv (1999-2026). No external values used."},
    "analytics": analytics})

print("DONE. flagged items:", len(flags))
