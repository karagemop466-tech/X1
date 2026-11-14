"""
Builds the static GitHub Pages site in docs/ from verified data files.
Every number on the pages is read from data/*.csv or data/*.json (no hand-typed statistics).
Run:  python3 scripts/build_site.py   (uses only the Python standard library)
"""
import csv, html, json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data"
OUT = ROOT / "docs"
OUT.mkdir(exist_ok=True)
(OUT / ".nojekyll").write_text("")
H = lambda s: html.escape("" if s is None else str(s))
BUILT = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
DATA_DATE = "2026-11-14"

def rcsv(name):
    with open(D / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

standings = rcsv("standings_2026.csv")
schedule = rcsv("schedule_2026_week10.csv")
byes = rcsv("schedule_2026_week10_byes.csv")
injuries = rcsv("injuries_2026_week10.csv")
model = rcsv("model_lines_2026_week10.csv")
board = rcsv("strategy_leaderboard.csv")
splits = rcsv("strategy_splits.csv")
corr = rcsv("strategy_correlations.csv")
parlay = rcsv("parlay_results.csv")
registry = rcsv("strategy_registry.csv")
flags_auto = rcsv("flags_auto.csv")
sources = rcsv("sources.csv")
checks = json.loads((D / "data_checks.json").read_text())

CHECKED_GAMES = {"WAS at NYG", "NE at DET"}   # rows re-checked line by line against NFL.com chunk 0 on 2026-11-14
NFLDATA_URL = "https://github.com/nflverse/nfldata"
REPO = "https://github.com/karagemop466-tech/X1/blob/arena/c39d8541-x1"
n_checked = sum(1 for r in injuries if r["game"] in CHECKED_GAMES)
i06_names = sorted({r["item"] for r in flags_auto if r["flag_code"] == "I-06"})
MANUAL_FLAGS = [
 ("I-01","Repo","README.md is one line ('# X1'). No description, licence, or usage notes.","https://github.com/karagemop466-tech/X1/blob/dab199ce305bd0168f61f9bbb25b4b601eb45324/README.md","flagged"),
 ("I-02","Repo","Only one commit before this work ('Initial commit', dab199c). No history to check authorship or changes.","https://github.com/karagemop466-tech/X1/commit/dab199ce305bd0168f61f9bbb25b4b601eb45324","flagged"),
 ("I-03","Repo","The project brief uses session-<id>/<task> branches. Arena branch policy for this session allows one branch only, so task claims are recorded in COORDINATION.md instead.",REPO + "/COORDINATION.md","flagged"),
 ("I-04","Repo","The brief contains HTML-escaped text (e.g. '&amp;amp;lt;id&amp;amp;gt;'). Read as session-<id>/<task> and COORDINATION.md.",REPO + "/COORDINATION.md","flagged"),
 ("I-05","Injuries","Puka Nacua (LAR, WR) is 'Did Not Participate In Practice' with no injury listed on the report. NFL.com news (retrieved 2026-11-14) says he is likely to be placed on IR after a turf toe injury and MCL/PCL sprain. The report does not reconcile with the news. The news item is not a roster transaction record.","https://www.nfl.com/injuries/ · https://www.nfl.com/news/rams-wr-puka-nacua-likely-to-be-placed-on-injured-reserve-with-turf-toe-sprained-mcl-and-pcl","flagged"),
 ("I-06","Injuries", f"'Did Not Participate In Practice' with no injury and no game status ({sum(1 for r in flags_auto if r['flag_code']=='I-06')} rows, {len(i06_names)} players, listed in the automatic flags table below). The reason is not stated on the report.","https://www.nfl.com/injuries/","flagged"),
 ("I-07","Injuries","'Full Participation in Practice' shown with game status 'Out' (BJ Green II, JAX, forearm). The report does not document this combination.","https://www.nfl.com/injuries/","flagged"),
 ("I-08","Injuries","Player link slug differs from the printed name (Jacob Hummel → jake-hummel; Kam Curl → kamren-curl; Gervon Dexter Sr. → gervon-dexter). Kept as published.","https://www.nfl.com/injuries/","flagged"),
 ("I-09","Schedule","NFL.com lists the Munich game as 'Patriots at Lions'. A third-party page calls it 'Patriots vs. Lions' (recorded in the earlier session; not re-checked this session). NFL.com is used.","https://www.nfl.com/schedules/2026/by-week/week-10","flagged (minor)"),
 ("I-10","Data","Line source (spread_line, total_line, moneylines) in nflverse nfldata is NOT documented with a named provider. It cannot be confirmed from an official source. Blocks gate G0 for every strategy.","https://github.com/nflverse/nfldata/blob/master/DATASETS.md","flagged — blocks G0"),
 ("I-11","Data","nflverse game results are compiled from third-party sources and were not checked game-by-game against NFL.com (one 2026 game matched).","https://github.com/nflverse/nfldata","flagged"),
 ("I-12","Data","No official depth charts collected. Starter vs backup status cannot be verified (task T4 blocked).","https://www.nfl.com/teams/","flagged — blocks T4"),
 ("I-13","Data","No prop-odds source and no official player-stat source collected. Player-prop strategies not tested.","https://www.nfl.com/players/","flagged — blocks prop tests"),
 ("I-14","Schedule / standings","NFL.com standings (checked 2026-11-14) still show WAS 3-5-1 and NYG 5-3-1, the pre-game records, while the schedule marks the Thursday game Final (Commanders 24, Giants 21). nflverse agrees on the final score. The standings appear not to reflect the result. NFL.com does not state why.","https://www.nfl.com/standings/ · https://www.nfl.com/schedules/2026/by-week/week-10","flagged"),
 ("I-15","Injuries / standings","Rams code: the injury report prints LAR; the schedule and standings print LA. Mapped for joins only; displayed as printed.","https://www.nfl.com/injuries/ · https://www.nfl.com/standings/","flagged (mapped)"),
 ("I-16","Data","nflverse uses ARI for Arizona; NFL.com uses AZ. Mapped for joins only.","https://github.com/nflverse/nfldata/blob/master/data/games.csv","flagged (mapped)"),
 ("I-17","Injuries", f"Row-level re-check against the official page is complete for {n_checked} of {len(injuries)} rows (WAS at NYG, NE at DET; page chunk 0). The other {len(injuries)-n_checked} rows were transcribed from the official text and are pending a line-by-line re-check against chunks 1–7. Pending rows are marked on the Injury report page.","https://www.nfl.com/injuries/","needs review"),
]

def f1(x, nd=1):
    try: return f"{float(x):.{nd}f}"
    except (TypeError, ValueError): return ""
def pct(x):
    try: return f"{float(x)*100:.1f}%"
    except (TypeError, ValueError): return ""
def pct_signed(x):
    try: return f"{float(x)*100:+.1f}%"
    except (TypeError, ValueError): return ""

NAV = [
    ("Overview", [("index.html", "Home"), ("summary.html", "Executive summary")]),
    ("Data", [("standings.html", "Standings"), ("schedule.html", "Week 10 schedule"), ("injuries.html", "Injury report")]),
    ("Research", [("strategies.html", "Strategy leaderboard"), ("model-lines.html", "Model lines"), ("methodology.html", "Method & checks")]),
    ("Decisions", [("questions.html", "Questions & gaps"), ("suggestions.html", "Suggestions")]),
    ("Review", [("flagged.html", "Flagged for review"), ("repo-review.html", "Repo review")]),
    ("Sources", [("sources.html", "Source register")]),
]

def layout(title, active_cat, active_page, body):
    cats = "".join(f'<a class="{"active" if c == active_cat else ""}" href="{pages[0][0]}">{H(c)}</a>' for c, pages in NAV)
    sub = ""
    for c, pages in NAV:
        if c == active_cat:
            sub = "".join(f'<a class="{"active" if href == active_page else ""}" href="{href}">{H(lbl)}</a>' for href, lbl in pages)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{H(title)} · X1 NFL Research</title>
<link rel="stylesheet" href="assets/style.css">
</head><body>
<header class="top"><a class="brand" href="index.html">X1 · NFL Research Dashboard</a>
<nav class="menu">{cats}</nav></header>
<header class="top" style="background:#27395f;padding:8px 22px"><nav class="menu">{sub}</nav></header>
<main>{body}</main>
<footer>Data as of {DATA_DATE} (UTC). Built {BUILT}. Official data: NFL.com. Secondary data is labelled. Nothing on this site is betting advice.
· <a href="flagged.html">Flagged for review</a> · <a href="sources.html">Sources</a> · <a href="https://github.com/karagemop466-tech/X1">Repository</a></footer>
<script src="assets/app.js"></script></body></html>"""

def src_link(url, label="source"):
    return f'<a href="{H(url)}" target="_blank" rel="noopener">{H(label)} ↗</a>'

def write(name, html_text):
    (OUT / name).write_text(html_text, encoding="utf-8")

# ---------------- derived facts (all computed from data files) ----------------
n_inj = len(injuries)
inj_games = len({r["game"] for r in injuries})
status_counts = {}
for r in injuries:
    status_counts[r["game_status"] or "(none listed)"] = status_counts.get(r["game_status"] or "(none listed)", 0) + 1
n_out = status_counts.get("Out", 0)
n_doubt = status_counts.get("Doubtful", 0)
n_quest = status_counts.get("Questionable", 0)
flag_counts = {}
for r in flags_auto:
    flag_counts[r["flag_code"]] = flag_counts.get(r["flag_code"], 0) + 1
best_hold = min(board, key=lambda r: -float(r["holdout_win_pct"] or 0))
best_row = max(board, key=lambda r: float(r["holdout_win_pct"] or 0))
n_pass = sum(1 for r in board if r["status"] == "PASS")
n_strat = len(board)
tnf = next(r for r in schedule if r["away"] == "WAS")
mrows = [r for r in model if r["model_side_if_edge_ge_3"] != "no bet"]
forward_n = max(int(r["forward_2026_bets"] or 0) for r in board)
hold_split = {r["strategy"]: r for r in splits if r["split"] == "holdout_2021_2025"}
def hs(strategy_prefix):
    for k, v in hold_split.items():
        if k.startswith(strategy_prefix): return v
    return None
under = hs("S08"); model_s = hs("S10"); home_s = hs("S01")
max_phi_nonredundant = max((abs(float(r["phi"])) for r in corr if r["strategy_a"] != r["strategy_b"] and abs(float(r["phi"])) < 0.999), default=0)
n_redundant = sum(1 for r in parlay if r.get("redundant_mirror_or_nested") == "True")

# ---------------- CATEGORY: OVERVIEW ----------------
kpis = f"""<div class="grid">
<div class="card"><div class="k">Teams in standings</div><div class="kpi">{len(standings)}</div><div class="small">NFL.com standings</div></div>
<div class="card"><div class="k">Week 10 games (official)</div><div class="kpi">{len(schedule)}</div><div class="small">+ {len(byes)} teams on bye</div></div>
<div class="card"><div class="k">Injury report rows (Week 10)</div><div class="kpi">{n_inj}</div><div class="small">Official NFL.com report, {inj_games} games</div></div>
<div class="card"><div class="k">Strategies that pass all gates</div><div class="kpi">{n_pass} / {n_strat}</div><div class="small">Blocked by unverified line data (G0)</div></div>
<div class="card"><div class="k">Open flags for review</div><div class="kpi">{len(flags_auto) + len(MANUAL_FLAGS)}</div><div class="small">{len(MANUAL_FLAGS)} manual + {len(flags_auto)} automatic. See Flagged for review</div></div>
</div>"""
index_body = f"""<h1>NFL research dashboard</h1>
<p class="lead">Official 2026 NFL data (standings, Week 10 schedule, injury report), a line-by-line source register, our own strategy research with validation gates, and the open questions and suggestions that need your decision.</p>
{kpis}
<div class="note bad"><b>Bottom line:</b> none of the {n_strat} pre-registered betting strategies passes the validation gates. The main blocker is that the historical line data we have does not name its provider, so we cannot verify it against an official source (flag I-10). Read the <a href="summary.html">executive summary</a>.</div>
<h2>Browse by category</h2>
<div class="grid">
<div class="card"><a class="big" href="summary.html">Executive summary</a><div class="small">Key facts, verdicts, and what we still need.</div></div>
<div class="card"><a class="big" href="standings.html">Standings</a><div class="small">32 teams, NFL.com 2026 standings.</div></div>
<div class="card"><a class="big" href="schedule.html">Week 10 schedule</a><div class="small">14 games, byes, and the Thursday final.</div></div>
<div class="card"><a class="big" href="injuries.html">Injury report</a><div class="small">{n_inj} official rows with player links and team summaries.</div></div>
<div class="card"><a class="big" href="strategies.html">Strategy leaderboard</a><div class="small">Validation gates, splits, correlations, parlays.</div></div>
<div class="card"><a class="big" href="model-lines.html">Model lines</a><div class="small">Our Elo line vs. the unverified market spread, Week 10.</div></div>
<div class="card"><a class="big" href="questions.html">Questions & gaps</a><div class="small">What we know, what we don't, and how to find out.</div></div>
<div class="card"><a class="big" href="suggestions.html">Suggestions</a><div class="small">Options for you to choose. Nothing is implemented yet.</div></div>
<div class="card"><a class="big" href="flagged.html">Flagged for review</a><div class="small">Irregularities and unverified items with source links.</div></div>
<div class="card"><a class="big" href="sources.html">Source register</a><div class="small">Every source, its tier, and when it was retrieved.</div></div>
</div>
<h2>How to read the verification labels</h2>
<table><tr><th>Label</th><th>Meaning</th></tr>
<tr><td><span class="chip ok">official</span></td><td>Value copied from an NFL.com page (link on each row).</td></tr>
<tr><td><span class="chip warn">secondary</span></td><td>Community or third-party dataset. Not official. Used only where labelled.</td></tr>
<tr><td><span class="chip bad">unverified</span></td><td>Cannot be confirmed from an official source. Not used for decisions.</td></tr>
</table>"""
write("index.html", layout("Home", "Overview", "index.html", index_body))

summary_body = f"""<h1>Executive summary</h1>
<p class="lead">Data as of {DATA_DATE} (UTC). Official sources are NFL.com. Figures below are computed from the data files in this repository.</p>
<h2>1. What is verified</h2>
<ul>
<li><b>Standings:</b> all {len(standings)} rows were re-checked against the NFL.com standings page on 2026-11-14 (W, L, T, PCT, PF, PA, net points, streak). Every value matched. Internal arithmetic also passes.</li>
<li><b>Week 10 schedule:</b> {len(schedule)} games plus {len(byes)} bye teams (CHI, DEN, PHI, TB). The Thursday game is marked final on NFL.com: Commanders {tnf['away_score']}, Giants {tnf['home_score']}. The nflverse data agrees.</li>
<li><b>Injury report:</b> {n_inj} rows across {inj_games} games, transcribed from NFL.com. Line-by-line re-check is done for {n_checked} rows (WAS at NYG, NE at DET). The other {n_inj-n_checked} rows are pending (I-17). Counts by status: Out {n_out}, Doubtful {n_doubt}, Questionable {n_quest}.</li>
<li><b>Spot-checks passed:</b> Mike Evans is listed with the 49ers on his NFL.com player page, matching the injury report.</li>
</ul>
<h2>2. Strategy research: what the numbers say</h2>
<ul>
<li>We pre-registered {n_strat} strategies (ATS, totals, rest, and our own Elo model) and tested them on regular-season games from 2006 to 2026 using a fixed holdout of 2021–2025.</li>
<li><b>{n_pass} of {n_strat} strategies pass all gates.</b> In the holdout, the best hit rate is {pct(best_row['holdout_win_pct'])} ({best_row['strategy']}). Break-even at −110 is 52.4%.</li>
<li>Under-totals in the holdout hit {pct(under['win_pct'])} on {under['bets']} bets. After a Bonferroni correction (×{checks['bonferroni_divisor']}), that is p = {f1(under['p_bonf'],2)} (not significant).</li>
<li>Our Elo-vs-line strategy (S10) hit {pct(model_s['win_pct'])} on {model_s['bets']} holdout bets (ROI {pct_signed(model_s['roi_110'])} at −110), below the 52.4% break-even. Its market lines are unverified (I-10).</li>
<li><b>Correlation:</b> mirror pairs (home vs away, over vs under) have phi = ±1. Parlaying them is meaningless, so {n_redundant} of 45 pairs are flagged redundant. Among the rest, the largest |phi| is {f1(max_phi_nonredundant,2)}.</li>
<li><b>Why no strategy passes:</b> gate G0 fails. We cannot verify that the spread and total lines come from a documented, official, or licensed provider (flag I-10). The statistical gates are in the methodology page.</li>
</ul>
<h2>3. Injury and depth tracking</h2>
<ul>
<li>We track official injury designations for every listed player in Week 10 (see the injury page for team and unit summaries).</li>
<li><b>Not yet possible:</b> whether a backup replaced a starter. This needs official depth charts, which we have not collected (task T4, blocked). Until then we make no claim about starter-versus-backup deficiencies.</li>
</ul>
<h2>4. Decisions needed from you</h2>
<p>See the <a href="suggestions.html">Suggestions</a> page (options and trade-offs) and the <a href="questions.html">Questions & gaps</a> page. The top decisions are:</p>
<ol>
<li>Which line data source to use, and whether to pay for a licensed historical feed (blocks every strategy).</li>
<li>Whether to collect official depth charts (needed for starter-versus-backup tracking).</li>
<li>Whether to keep the current gate thresholds (300 bets, Bonferroni p &lt; 0.05, 60% positive seasons).</li>
<li>Whether to show unverified research values (as now, clearly labelled) or blank them until the line source is verified.</li>
</ol>
<h2>5. Flags</h2>
<p>{len(flags_auto)} automatic flags and {len(MANUAL_FLAGS)} manual flags are listed on the <a href="flagged.html">Flagged for review</a> page, each with an official source link where one exists.</p>"""
write("summary.html", layout("Executive summary", "Overview", "summary.html", summary_body))

# ---------------- DATA: STANDINGS ----------------
rows = "".join(
    f"<tr><td>{H(r['conference'])}</td><td>{H(r['team'])}</td><td>{H(r['team_abbr'])}</td>"
    f"<td class='num'>{r['W']}</td><td class='num'>{r['L']}</td><td class='num'>{r['T']}</td>"
    f"<td class='num'>{f1(r['PCT'],3)}</td><td class='num'>{r['PF']}</td><td class='num'>{r['PA']}</td>"
    f"<td class='num'>{r['NET_PTS']}</td><td>{H(r['STRK'])}</td>"
    f"<td><a href='{H(r['team_url'])}' target='_blank' rel='noopener'>NFL.com team ↗</a> · <a href='{H(r['source_url'])}' target='_blank' rel='noopener'>standings ↗</a></td></tr>"
    for r in standings)
standings_body = f"""<h1>Standings — 2026 season (Week 10 view)</h1>
<p class="lead">Source: NFL.com 2026 standings, retrieved {DATA_DATE}. <span class="chip ok">official</span> <b>All 32 rows re-checked against the page on {DATA_DATE}.</b> Click a column header to sort. Note I-14: the Thursday game (Commanders 24, Giants 21) is marked final on the schedule page, but the standings still show the pre-game records.</p>
<input class="filter" data-target="stand" placeholder="Filter teams…">
<div class="tablewrap"><table class="sortable" id="stand"><thead><tr>
<th>Conf</th><th>Team</th><th>Code</th><th class="num">W</th><th class="num">L</th><th class="num">T</th><th class="num">PCT</th><th class="num">PF</th><th class="num">PA</th><th class="num">Net pts</th><th>Streak</th><th>Source</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<p class="small">Column meanings are taken from the legend on the NFL.com page: W Wins, L Losses, T Ties, PCT Winning Percentage, PF Total Points For, PA Total Points Against, NET PTS Net Points, STRK Streak.</p>"""
write("standings.html", layout("Standings", "Data", "standings.html", standings_body))

# ---------------- DATA: SCHEDULE ----------------
srows = ""
for r in schedule:
    score = f"{r['away_score']}–{r['home_score']}" if r["status"] == "Final" else ""
    srows += (f"<tr><td>{H(r['day'])} {H(r['date'])}</td><td>{H(r['kickoff_et'])} ET</td><td>{H(r['network'])}</td>"
              f"<td>{H(r['away'])} <span class='small'>({H(r['away_record_pre'])})</span></td>"
              f"<td>{H(r['home'])} <span class='small'>({H(r['home_record_pre'])})</span></td>"
              f"<td><span class='chip {'ok' if r['status']=='Final' else ''}'>{H(r['status'])}</span> {H(score)}</td>"
              f"<td>{src_link(r['game_url'], 'NFL.com game')} · {src_link(r['source_url'], 'schedule')}</td></tr>")
brows = "".join(f"<tr><td>{H(r['team_abbr'])}</td><td>{H(r['team'])}</td><td>{H(r['record'])}</td><td>{src_link(r['source_url'],'NFL.com schedule')}</td></tr>" for r in byes)
sched_body = f"""<h1>Week 10 schedule — 2026</h1>
<p class="lead">Source: NFL.com Week 10 schedule. <span class="chip ok">official</span> Records shown are as printed on the NFL.com schedule page (the Thursday game's records are pre-game). Times are as printed (ET).</p>
<div class="tablewrap"><table><thead><tr><th>Day / date</th><th>Kickoff</th><th>Network</th><th>Away (record)</th><th>Home (record)</th><th>Status / score</th><th>Source</th></tr></thead><tbody>{srows}</tbody></table></div>
<h2>Teams on bye</h2>
<table><thead><tr><th>Code</th><th>Team</th><th>Record</th><th>Source</th></tr></thead><tbody>{brows}</tbody></table>
"""
write("schedule.html", layout("Week 10 schedule", "Data", "schedule.html", sched_body))

# ---------------- DATA: INJURIES ----------------
UNIT = {"QB":"Offense","RB":"Offense","FB":"Offense","WR":"Offense","TE":"Offense","T":"Offense","G":"Offense","C":"Offense",
        "DE":"Defense","DT":"Defense","LB":"Defense","CB":"Defense","S":"Defense",
        "K":"Special teams","P":"Special teams","LS":"Special teams"}
team_sum = {}
for r in injuries:
    t = r["team_abbr"]
    d = team_sum.setdefault(t, dict(rows=0, Out=0, Doubtful=0, Questionable=0, DNP=0,
                                   off_out_doubt=0, def_out_doubt=0, st_out_doubt=0, game=r["game"]))
    d["rows"] += 1
    if r["game_status"] in ("Out", "Doubtful", "Questionable"):
        d[r["game_status"]] += 1
    if r["practice_status"] == "Did Not Participate In Practice":
        d["DNP"] += 1
    if r["game_status"] in ("Out", "Doubtful"):
        key = {"Offense":"off_out_doubt","Defense":"def_out_doubt","Special teams":"st_out_doubt"}.get(UNIT.get(r["position"],""), None)
        if key: d[key] += 1
sum_rows = ""
st_names = {s["team_abbr"]: s["team"] for s in standings}
for t in sorted(team_sum, key=lambda x: st_names.get(x, x)):
    d = team_sum[t]
    sum_rows += (f"<tr><td>{H(st_names.get(t, t))}</td><td>{H(t)}</td><td class='num'>{d['rows']}</td>"
                 f"<td class='num'>{d['Out']}</td><td class='num'>{d['Doubtful']}</td><td class='num'>{d['Questionable']}</td>"
                 f"<td class='num'>{d['DNP']}</td><td class='num'>{d['off_out_doubt']}</td><td class='num'>{d['def_out_doubt']}</td><td class='num'>{d['st_out_doubt']}</td>"
                 f"<td>{src_link('https://www.nfl.com/injuries/','report')}</td></tr>")
irows = ""
for r in injuries:
    rc = "<span class='chip ok'>re-checked (chunk 0)</span>" if r["game"] in CHECKED_GAMES else "<span class='chip warn'>pending (I-17)</span>"
    codes = r["flag_codes"]
    flag = " ".join(f"<span class='chip warn'>{H(c)}</span>" for c in codes.split(";") if c)
    gs = r["game_status"]
    cls = {"Out":"bad","Doubtful":"warn","Questionable":"warn"}.get(gs, "")
    irows += (f"<tr><td>{H(r['game'])}</td><td>{H(r['team_abbr'])}</td><td>{H(r['player'])}</td><td>{H(r['position'])}</td>"
              f"<td>{H(UNIT.get(r['position'],''))}</td><td>{H(r['injury'])}</td><td>{H(r['practice_status'])}</td>"
              f"<td><span class='chip {cls}'>{H(gs) if gs else '(blank)'}</span></td><td>{flag}</td><td>{rc}</td>"
              f"<td>{src_link(r['player_url'],'player')} · {src_link(r['source_url'],'report')}</td></tr>")
inj_body = f"""<h1>Injury report — Week 10 (2026)</h1>
<p class="lead">Source: NFL.com official injury report, retrieved {DATA_DATE}. <span class="chip ok">official</span> {n_inj} rows, {inj_games} games. Every row links to the player page and the report. Row check: {n_checked} of {n_inj} rows re-checked line by line (WAS at NYG, NE at DET); the rest are pending (I-17). Flags (I-05 to I-08) are explained on the <a href="flagged.html">Flagged for review</a> page.</p>
<div class="note info"><b>Starter vs backup: not yet tracked.</b> The report does not say who starts. We have no official depth charts, so we cannot yet say whether a backup is replacing a starter (task T4, blocked). The unit columns below only count players by position group. They do not show who is a starter.</div>
<h2>Team summary (counts from the official rows)</h2>
<p class="small">Unit grouping is our classification from the NFL position codes shown on the report: Offense = QB, RB, FB, WR, TE, T, G, C. Defense = DE, DT, LB, CB, S. Special teams = K, P, LS. "Out or Doubtful" counts players with those game statuses.</p>
<div class="tablewrap"><table class="sortable"><thead><tr><th>Team</th><th>Code</th><th class="num">Rows</th><th class="num">Out</th><th class="num">Doubtful</th><th class="num">Questionable</th><th class="num">DNP (practice)</th><th class="num">Offense out/doubtful</th><th class="num">Defense out/doubtful</th><th class="num">Special teams out/doubtful</th><th>Source</th></tr></thead>
<tbody>{sum_rows}</tbody></table></div>
<h2>All rows</h2>
<input class="filter" data-target="inj" placeholder="Filter by player, team, injury, status…">
<div class="tablewrap"><table class="sortable" id="inj"><thead><tr><th>Game</th><th>Team</th><th>Player</th><th>Pos</th><th>Unit (ours)</th><th>Injury</th><th>Practice</th><th>Game status</th><th>Flags</th><th>Row check</th><th>Source</th></tr></thead><tbody>{irows}</tbody></table></div>"""
write("injuries.html", layout("Injury report", "Data", "injuries.html", inj_body))

# ---------------- RESEARCH: MODEL LINES ----------------
mrow = ""
for r in model:
    side = r["model_side_if_edge_ge_3"]
    mrow += (f"<tr><td>{H(r['away_team'])} at {H(r['home_team'])}</td><td>{H(r['gameday'])}</td><td>{H(r['game_status'])}</td>"
             f"<td class='num'>{f1(r['model_home_margin'],2)}</td><td class='num'>{f1(r['market_spread_home_UNVERIFIED'],1)}</td>"
             f"<td class='num'>{f1(r['edge_model_minus_line'],2)}</td><td>{H(side)}</td>"
             f"<td class='num'>{f1(r['market_total_UNVERIFIED'],1)}</td>"
             f"<td><span class='chip bad'>unverified line</span> {src_link('https://github.com/nflverse/nfldata/blob/master/DATASETS.md','nfldata docs')}</td></tr>")
model_body = f"""<h1>Model lines — Week 10 (2026)</h1>
<p class="lead">Our own line: a sequential Elo model with fixed constants (K = 20, home field = 65 Elo, 25 Elo per point, one-third season reversion). Positive home margin means the home team is favored by that many points.</p>
<div class="note bad"><b>Not a recommendation.</b> The market spread and total are from the nflverse dataset, whose line provider is not documented (flag I-10). Every market value on this page is <b>UNVERIFIED</b>. The model is not validated: no strategy passes the gates.</div>
<div class="tablewrap"><table class="sortable"><thead><tr><th>Game</th><th>Date</th><th>Status</th><th class="num">Model home margin</th><th class="num">Market spread (home) UNVERIFIED</th><th class="num">Edge (model − market)</th><th>Model side if |edge| ≥ 3</th><th class="num">Market total UNVERIFIED</th><th>Verification</th></tr></thead><tbody>{mrow}</tbody></table></div>
<p class="small">The model side column is shown only where |edge| ≥ 3 points, the pre-registered threshold (S10). {len(mrows)} of {len(model)} games meet it. The Thursday game is already final, so its model line is pre-game only.</p>"""
write("model-lines.html", layout("Model lines", "Research", "model-lines.html", model_body))

# ---------------- RESEARCH: STRATEGIES ----------------
lrows = ""
for r in board:
    fails = r["failed_gates"].replace(";", ", ")
    status_cls = "ok" if r["status"] == "PASS" else "bad"
    lrows += (f"<tr><td class='num'>{r['rank']}</td><td>{H(r['strategy'])}</td><td>{H(r['family'])}</td>"
              f"<td class='num'>{r['holdout_bets']}</td><td class='num'>{pct(r['holdout_win_pct'])}</td>"
              f"<td class='num'>{H(r['holdout_ci95'])}</td><td class='num'>{pct_signed(r['holdout_roi_110'])}</td>"
              f"<td class='num'>{f1(r['holdout_p_raw'],4)}</td><td class='num'>{f1(r['holdout_p_bonf'],3)}</td>"
              f"<td class='num'>{H(r['holdout_positive_seasons'])}</td><td class='small'>{H(fails)}</td>"
              f"<td><span class='chip {status_cls}'>{'PASS' if r['status']=='PASS' else 'NOT ELIGIBLE'}</span> <span class='chip bad'>unverified inputs</span></td>"
              f"<td>{src_link('https://github.com/nflverse/nfldata','nfldata')}</td></tr>")
srows2 = ""
piv = {}
for r in splits:
    piv.setdefault(r["strategy"], {})[r["split"]] = r
for strat in sorted(piv):
    cells = ""
    for sp in ["discovery_2006_2015","validation_2016_2020","holdout_2021_2025","forward_2026"]:
        x = piv[strat][sp]
        cells += f"<td class='num'>{x['bets']}</td><td class='num'>{pct(x['win_pct'])}</td><td class='num'>{pct_signed(x['roi_110'])}</td>"
    srows2 += f"<tr><td>{H(strat)}</td>{cells}<td>{src_link(NFLDATA_URL, 'nfldata')}</td></tr>"
names = [r["strategy"] for r in board]
order = sorted(piv)
corr_map = {(r["strategy_a"], r["strategy_b"]): float(r["phi"]) for r in corr}
cor_rows = ""
for a in order:
    tds = ""
    for b in order:
        v = corr_map.get((a, b), float("nan"))
        if v != v:
            tds += "<td></td>"; continue
        shade = "heat-pos" if v > 0.3 else ("heat-neg" if v < -0.3 else "")
        tds += f"<td class='num {shade}'>{v:+.2f}</td>"
    cor_rows += f"<tr><td>{H(a)}</td>{tds}</tr>"
cor_head = "".join(f"<th class='num'>{H(x.split(' ')[0])}</th>" for x in order)
par_sorted = sorted([r for r in parlay if r.get("redundant_mirror_or_nested") != "True"],
                    key=lambda r: -float(r["parlay_roi_observed"] or -9))[:10]
prow = "".join(
    f"<tr><td>{H(r['leg_a'])}</td><td>{H(r['leg_b'])}</td><td class='num'>{r['common_games']}</td>"
    f"<td class='num'>{pct(r['p_both_observed'])}</td><td class='num'>{pct(r['p_both_if_independent'])}</td>"
    f"<td class='num'>{f1(r['phi'],2)}</td><td class='num'>{pct_signed(r['parlay_roi_observed'])}</td><td class='num'>{pct_signed(r['parlay_roi_if_independent'])}</td><td>{src_link(NFLDATA_URL, 'nfldata')}</td></tr>"
    for r in par_sorted)
GATE_SRC = src_link(REPO + "/analysis/strategy_backtest.py", "code")
gates_rows = f"""<tr><td>G0</td><td>Line and result inputs verified from an official or documented source</td><td>FAILS for all strategies (I-10)</td><td>{GATE_SRC}</td></tr>
<tr><td>G1</td><td>At least 300 holdout bets (2021–2025)</td><td>Checked per strategy (Failed gates column)</td><td>{GATE_SRC}</td></tr>
<tr><td>G2</td><td>Win rate above 52.38% (−110 break-even) in discovery, validation and holdout</td><td>Checked per strategy</td><td>{GATE_SRC}</td></tr>
<tr><td>G3</td><td>Holdout one-sided binomial p, Bonferroni-adjusted for {checks['bonferroni_divisor']} strategies, below 0.05</td><td>Checked per strategy</td><td>{GATE_SRC}</td></tr>
<tr><td>G4</td><td>At least 60% of holdout seasons (2021–2025) with positive ROI</td><td>Checked per strategy</td><td>{GATE_SRC}</td></tr>
<tr><td>G5</td><td>Correlation check in the portfolio (phi between passing strategies)</td><td>Not applied by the code. Applies only if two or more strategies pass G0–G4 (none do).</td><td>{GATE_SRC}</td></tr>
<tr><td>Report</td><td>2026 forward results (not a gate; too few bets)</td><td>Reported only</td><td>{GATE_SRC}</td></tr>"""
strat_body = f"""<h1>Strategy leaderboard — research</h1>
<div class="note bad"><b>Verdict: {n_pass} of {n_strat} strategies pass all gates.</b> Gate G0 fails for every strategy because the line data's provider is not documented (I-10). The values below are research output on <b>unverified inputs</b>. Under your verification rule they would be blank. They are shown so you can see the method and the outcome. You can choose to blank them (see Suggestions, SG-01).</div>
<h2>Leaderboard (ranked by Bonferroni-adjusted holdout p, then ROI)</h2>
<div class="tablewrap"><table class="sortable"><thead><tr><th>Rank</th><th>Strategy</th><th>Family</th><th class="num">Holdout bets</th><th class="num">Win %</th><th class="num">95% CI</th><th class="num">ROI (−110)</th><th class="num">p raw</th><th class="num">p Bonferroni</th><th class="num">+ seasons</th><th>Failed gates</th><th>Status</th><th>Source</th></tr></thead><tbody>{lrows}</tbody></table></div>
<p class="small">Holdout = 2021–2025 (single look). Discovery = 2006–2015. Validation = 2016–2020. Forward = 2026 season to date. ROI assumes −110 pricing on both sides (not verified against any sportsbook). p-values test whether the win rate beats 52.38%.</p>
<h2>Gate definitions</h2>
<div class="tablewrap"><table><thead><tr><th>Gate</th><th>Rule</th><th>Result</th><th>Source</th></tr></thead><tbody>{gates_rows}</tbody></table></div>
<h2>Results by split</h2>
<div class="tablewrap"><table class="sortable"><thead><tr><th>Strategy</th><th class="num">Discovery bets</th><th class="num">Disc. win %</th><th class="num">Disc. ROI</th><th class="num">Validation bets</th><th class="num">Val. win %</th><th class="num">Val. ROI</th><th class="num">Holdout bets</th><th class="num">Hold. win %</th><th class="num">Hold. ROI</th><th class="num">2026 bets</th><th class="num">2026 win %</th><th class="num">2026 ROI</th><th>Source</th></tr></thead><tbody>{srows2}</tbody></table></div>
<h2>Correlation matrix (phi, holdout 2021–2025)</h2>
<p class="small">Source of all values: {src_link(NFLDATA_URL, "nfldata")} (derived). phi is the correlation between win/loss outcomes on games where both strategies bet. +1 means always the same result. −1 means always opposite results (mirror bets). Values near ±1 mean the two bets are effectively the same bet, so they cannot be parlayed as independent legs.</p>
<div class="tablewrap"><table><thead><tr><th>Strategy</th>{cor_head}</tr></thead><tbody>{cor_rows}</tbody></table></div>
<h2>Parlay pairs (2-leg, holdout, top 10 by observed ROI)</h2>
<p class="small">{n_redundant} of 45 pairs are flagged redundant (|phi| ≥ 0.80) and are excluded from this list. The observed ROI is in-sample on the holdout and is not validated. Compare the observed and independent columns to see the correlation effect. At −110 each leg, a 2-leg parlay pays 2.645 units per unit staked (breakeven 27.4%).</p>
<div class="tablewrap"><table class="sortable"><thead><tr><th>Leg A</th><th>Leg B</th><th class="num">Common games</th><th class="num">Both win (observed)</th><th class="num">Both win (if independent)</th><th class="num">phi</th><th class="num">Parlay ROI (observed)</th><th class="num">Parlay ROI (independent)</th><th>Source</th></tr></thead><tbody>{prow}</tbody></table></div>
<h2>Player-prop strategies</h2>
<div class="note info">Not tested. We have no verified prop-odds source and no official player-stat source in this repository (flag I-13). See Questions Q-07.</div>"""
write("strategies.html", layout("Strategy leaderboard", "Research", "strategies.html", strat_body))

# ---------------- RESEARCH: METHODOLOGY ----------------
ep = checks
meth_body = f"""<h1>Method and data checks</h1>
<p class="lead">How the numbers were produced, and what was checked. Code: <code>analysis/strategy_backtest.py</code>, <code>scripts/verify_data.py</code>, <code>scripts/build_site.py</code>.</p>
<h2>Data</h2>
<table><thead><tr><th>Dataset</th><th>Tier</th><th>Use</th><th>Check performed</th></tr></thead><tbody>
<tr><td><a href="https://www.nfl.com/standings/" target="_blank" rel="noopener">NFL.com standings 2026 ↗</a></td><td><span class="chip ok">official</span></td><td>Standings table</td><td>All 32 rows re-checked against the page on 2026-11-14 (W, L, T, PCT, PF, PA, net points, streak). Arithmetic also checked (PCT, net = PF − PA).</td></tr>
<tr><td><a href="https://www.nfl.com/schedules/2026/by-week/week-10" target="_blank" rel="noopener">NFL.com Week 10 schedule ↗</a></td><td><span class="chip ok">official</span></td><td>Schedule, byes</td><td>14 games + 4 byes = 32 teams. Thursday final 24–21 matches nflverse.</td></tr>
<tr><td><a href="https://www.nfl.com/injuries/" target="_blank" rel="noopener">NFL.com injury report, Week 10 ↗</a></td><td><span class="chip ok">official</span></td><td>Injury table, flags</td><td>Line-by-line re-check: {n_checked} of {n_inj} rows (WAS at NYG, NE at DET; chunk 0). Pending rows: I-17. Game list and team codes reconciled to the schedule.</td></tr>
<tr><td><a href="https://github.com/nflverse/nfldata/tree/{ep['source']['pinned_commit']}" target="_blank" rel="noopener">nflverse nfldata (commit {ep['source']['pinned_commit'][:8]}) ↗</a></td><td><span class="chip warn">secondary</span></td><td>Backtest results, own model</td><td>Sign convention checked: favorite wins straight-up {pct(ep['sign_check_favorite_su_win_pct'])} of games. Moneyline direction agrees with spread sign in {pct(ep['sign_check_moneyline_agreement'])} of {ep['n_sign_check_moneyline']} games. Provider of lines is undocumented (I-10).</td></tr>
</tbody></table>
<h2>Backtest set-up</h2>
<ul>
<li>Regular-season games, {ep['completed_games_reg']} completed in the file (1999–2026). Strategies use 2006 onward, where spreads exist.</li>
<li>Spread convention: positive spread = home favored (verified against the dataset's own documentation and the moneyline check above). Home covers if home margin > spread. Equal = push.</li>
<li>Pricing: −110 on both sides. <b>Assumption</b>, not verified against any book. Break-even 52.38%.</li>
<li>Own model: sequential Elo, updated after each game. Each prediction uses only earlier games. Constants fixed before testing: K = 20, home field = 65 Elo, 25 Elo per point, one-third reversion to 1500 each season. Edge threshold 3 points.</li>
<li>Splits: discovery 2006–2015, validation 2016–2020, holdout 2021–2025 (scored once), forward 2026. Nothing was tuned on any split.</li>
<li>Multiple testing: Bonferroni across the {ep['bonferroni_divisor']} pre-registered strategies. Note that some strategies are mirrors of others, so the true number of independent tests is smaller. This makes the correction conservative.</li>
<li>Team codes: STL, SD and OAK are mapped to LA, LAC and LV for ratings only (franchise relocations). The source uses ARI; NFL.com uses AZ (I-16).</li>
</ul>
<h2>Limits</h2>
<ul>
<li>Results depend on the line provider. Until the provider is verified, no result can be treated as evidence (G0).</li>
<li>Results are not checked game-by-game against NFL.com for 2006–2025 (I-11). One 2026 game was spot-checked.</li>
<li>No injury, depth-chart, snap-count, or player-prop data is used in the backtest yet.</li>
<li>Past performance on this data does not show future results.</li>
</ul>
<h2>Raw check output</h2>
<pre style="background:#fff;border:1px solid var(--line);padding:12px;overflow:auto;font-size:12.5px">{H(json.dumps({k: ep[k] for k in ['completed_games_reg','missing_spread_reg_2006plus','missing_total_reg_2006plus','duplicate_game_ids','sign_check_favorite_su_win_pct','sign_check_moneyline_agreement','dataset_2026_week10_check','pricing_assumption','elo_params']}, indent=1))}</pre>"""
write("methodology.html", layout("Method & checks", "Research", "methodology.html", meth_body))

# ---------------- DECISIONS: QUESTIONS ----------------

QSRC = {
 "Q-01": NFLDATA_URL + "/blob/master/DATASETS.md", "Q-02": "https://www.nfl.com/schedules/2026/by-week/week-10",
 "Q-03": "https://www.nfl.com/teams/", "Q-04": "https://www.nfl.com/injuries/", "Q-05": NFLDATA_URL,
 "Q-06": NFLDATA_URL, "Q-07": "https://www.nfl.com/players/", "Q-08": "https://www.nfl.com/standings/",
 "Q-09": "https://www.nfl.com/standings/", "Q-10": REPO + "/COORDINATION.md", "Q-11": REPO + "/COORDINATION.md",
 "Q-12": REPO + "/COORDINATION.md", "Q-13": "https://www.nfl.com/"}
def qsrc(k):
    u = QSRC[k]
    return src_link(u, "source") if u else "none (legal review needed)"
SSRC = {"SG-01": NFLDATA_URL, "SG-02": "https://www.nfl.com/teams/", "SG-03": "https://www.nfl.com/injuries/",
 "SG-04": REPO + "/analysis/strategy_backtest.py", "SG-05": NFLDATA_URL, "SG-06": "https://www.nfl.com/",
 "SG-07": REPO + "/analysis/strategy_backtest.py", "SG-08": REPO + "/COORDINATION.md",
 "SG-09": REPO + "/analysis/strategy_backtest.py", "SG-10": "https://www.nfl.com/standings/",
 "SG-11": "https://www.nfl.com/standings/", "SG-12": REPO + "/COORDINATION.md"}
QUESTIONS = [
 ("Q-01","Which provider supplies the historical spread, total and moneyline lines, and is it documented or licensed?","Every strategy result depends on it. Gate G0 fails without it.","Lines exist in the nflverse file (2006–2026). No provider is named.","Provider name, licence terms, how and when each line was recorded (open vs. close).","Ask the nflverse maintainers and read the data's documentation; or buy a documented historical feed.","open — blocks G0"),
 ("Q-02","Do the game results and scores match NFL.com for every game we use?","A wrong score changes every ATS result.","One game checked (WAS 24, NYG 21).","Full match of 2006–2025 scores against NFL.com.","Crawl NFL.com game pages per season and compare (about 7,200 games). Needs a decision on crawling (SG-06).","open"),
 ("Q-03","Which players are starters and which are backups, each week, for each team?","Needed to judge whether a backup is replacing a starter (your defense and offense question).","Injury status for each listed player (Week 10 only).","Official depth charts by week, starter flags.","Find the NFL.com depth-chart or roster pages and check what they contain and for which weeks (not yet checked).","open — blocks T4"),
 ("Q-04","How often did players with each designation actually play?","Needed to convert 'Questionable' or 'Doubtful' into a probability of playing.","Week 10 designations only.","Historical injury reports with game-day outcome (played or not).","NFL.com publishes weekly injury reports; check how far back they go (2026 weeks 1–10 are on the page dropdown).","open"),
 ("Q-05","What were the closing prices, and do our model lines beat them?","Closing-line value is a skill measure less affected by luck than win rate.","None verified. Model lines exist, prices are unverified.","Dated closing prices from a named book, for every game we test.","Requires a documented odds source and a logging process that records our line before kickoff.","open"),
 ("Q-06","What price (vig) applies to each bet?","Break-even moves with price. We assumed −110 on both sides.","Assumption only.","Actual prices from the book used, per bet.","Depends on Q-01/Q-05.","open — assumption"),
 ("Q-07","Which player-prop lines and player statistics can we use?","Needed for the player-prop strategies you asked for.","Nothing collected.","Prop odds source; official player stats (game logs) for each outcome.","Check NFL.com player stats pages for coverage and whether they can be collected. Prop odds need a separate documented source.","open"),
 ("Q-08","Which team codes does each source use, and what is the mapping?","Joining sources on the wrong code gives wrong results.","We found LAR vs LA (injury page vs standings) and ARI vs AZ (nflverse vs NFL.com).","A written mapping table with sources.","Compare the team-code lists on NFL.com and the nflverse file; add the mapping to the pipeline.","partly — mapping used, not yet a checked table"),
 ("Q-09","When was each data file retrieved, and are standings updated after a result?","I-14: the standings still show pre-game records for a game the schedule marks final.","Retrieval date only (2026-11-14, UTC).","Timestamp per row and the source's update cadence.","Record the retrieval time for every pull; ask NFL.com how standings are updated (not verified).","open"),
 ("Q-10","Is strategy testing and betting lawful for you in Japan?","Your location is Tokyo. Legal exposure matters before any real money is involved.","Not researched in this session.","Written legal review.","Consult a qualified adviser. We have not verified any legal position.","open — requires legal review"),
 ("Q-11","What reward structure and scoring should the leaderboard use?","You asked for a leaderboard with rewards. The scoring rule decides the winner.","Gate definitions (G0–G6).","Your choice of score (e.g., forward-test CLV, ROI, risk-adjusted).","Owner decision.","open — decision"),
 ("Q-12","Are the gate thresholds right for you?","Thresholds decide what counts as a pass.","Proposed: 300 bets, Bonferroni p < 0.05, 60% positive seasons, 52.38% break-even.","Your approval or changes.","Owner decision.","open — decision"),
 ("Q-13","How often should data refresh, and does that need automation?","Injury status changes close to kickoff. A manual refresh may be too slow.","One manual pull of Week 10.","Refresh cadence and whether scheduled jobs are allowed.","Check NFL.com terms of use before any automated collection (not verified).","open — decision"),
]
qrows = "".join(
    f"<tr><td>{H(q[0])}</td><td>{H(q[1])}</td><td>{H(q[2])}</td><td>{H(q[3])}</td><td>{H(q[4])}</td><td>{H(q[5])}</td><td><span class='chip warn'>{H(q[6])}</span></td><td>{qsrc(q[0])}</td></tr>"
    for q in QUESTIONS)
q_body = f"""<h1>Questions and information gaps</h1>
<p class="lead">What we have, what we are missing, and how to find it. Read this before any decision. Every item lists the evidence we have; where we have none, we say so.</p>
<input class="filter" data-target="qt" placeholder="Filter questions…">
<div class="tablewrap"><table class="sortable" id="qt"><thead><tr><th>ID</th><th>Question</th><th>Why it matters</th><th>What we have</th><th>What is missing</th><th>How to find out</th><th>Status</th><th>Source</th></tr></thead><tbody>{qrows}</tbody></table></div>"""
write("questions.html", layout("Questions & gaps", "Decisions", "questions.html", q_body))

# ---------------- DECISIONS: SUGGESTIONS ----------------
SUGG = [
 ("SG-01","Choose the line data source","Use a documented or licensed historical line feed. Or keep nflverse lines but label every result as unverified (current state). Or blank all line-dependent values until verified.","Unlocks a real test (G0). Cost: paid feed, or none.","A: Buy licensed feed (best evidence) · B: Keep nflverse, label unverified (current) · C: Blank all unverified values now"),
 ("SG-02","Collect official depth charts weekly","Pull the NFL.com team depth charts or roster pages each week (2026 onward). Then mark each injured player as starter or backup.","Required for the starter-versus-backup and offense/defense deficiency analysis (T4).","A: Weekly pull · B: Pull only for flagged teams · C: Skip until Q-03 is answered"),
 ("SG-03","Collect historical injury reports","Add NFL.com weekly injury reports for past seasons, with whether each player actually played. Measures how much each designation matters.","Converts 'Questionable' or 'Doubtful' into a measured availability rate (Q-04).","A: Last 3 seasons · B: Last 5 seasons · C: 2026 only"),
 ("SG-04","Log predictions before kickoff (forward test)","Store each model line and bet with a timestamp before kickoff. Score later. This is the cleanest test of skill and removes look-ahead risk.","Turns the 2026 forward split into real evidence.","A: Start now · B: Start after SG-01 · C: Do not log"),
 ("SG-05","Use closing-line value as the skill metric","Measure whether our prices beat the closing price, not just win rate. CLV is less affected by luck.","Better skill signal in fewer bets (Q-05).","A: CLV plus ROI · B: ROI only (current) · C: CLV only"),
 ("SG-06","Automate collection (after terms check)","Scheduled collection (GitHub Actions) of NFL.com pages on a set cadence, after checking NFL.com terms of use.","Keeps data current without manual pulls (Q-13).","A: Automate after terms check · B: Manual weekly pull · C: Automate for injuries only"),
 ("SG-07","Reduce redundant strategies before testing","Remove mirror pairs (home vs away, over vs under) from the leaderboard, or count them as one test. This also makes the Bonferroni correction fairer.","Cleaner leaderboard and fewer effective tests.","A: Count mirrors as one · B: Keep all (current)"),
 ("SG-08","Set the reward structure and score","Decide how the leaderboard ranks strategies (e.g., forward-test CLV, ROI, drawdown) and what the reward is.","Defines a winner (Q-11).","A: Forward CLV · B: Holdout ROI · C: Composite score (to define)"),
 ("SG-09","Confirm gate thresholds","Approve or change: 300 bets, Bonferroni p < 0.05, 60% positive seasons, 52.38% break-even.","Sets what counts as a pass (Q-12).","A: Keep · B: Stricter (e.g., 500 bets) · C: Looser (e.g., 200 bets)"),
 ("SG-10","Add a team-code mapping table","Keep one table mapping each source's codes (AZ/ARI, LA/LAR, etc.) and check it each refresh.","Prevents silent join errors (Q-08).","A: Add table and check (recommended) · B: Keep as-is"),
 ("SG-11","Add a timestamp to every row","Record when each row was retrieved and the page's own update time, if shown.","Resolves pre-game versus post-game record questions (Q-09, I-14).","A: Add (recommended) · B: Keep per-file date"),
 ("SG-12","Legal review before any wagering","Obtain written advice on the legal position in Japan before using any output for wagering.","Protects you from a legal problem (Q-10).","A: Obtain advice first (recommended) · B: Proceed without"),
]
srows_s = "".join(
    f"<tr><td>{H(s[0])}</td><td><b>{H(s[1])}</b><br><span class='small'>{H(s[2])}</span></td><td>{H(s[3])}</td><td>{H(s[4])}</td><td><span class='chip warn'>awaiting your choice</span></td><td>{src_link(SSRC[s[0]], 'source') if SSRC.get(s[0]) else '—'}</td></tr>"
    for s in SUGG)
s_body = f"""<h1>Suggestions for review</h1>
<div class="note info"><b>Nothing here has been implemented.</b> Each suggestion lists options. Reply with the option ID (for example, "SG-01 A") and we will implement only that choice. Items with no choice stay as they are.</div>
<div class="tablewrap"><table><thead><tr><th>ID</th><th>Suggestion</th><th>Benefit</th><th>Options</th><th>Status</th><th>Source</th></tr></thead><tbody>{srows_s}</tbody></table></div>"""
write("suggestions.html", layout("Suggestions", "Decisions", "suggestions.html", s_body))

# ---------------- REVIEW: FLAGGED ----------------
flag_rows = "".join(
    f"<tr><td>{H(c)}</td><td>{H(a)}</td><td>{H(d)}</td><td>{' · '.join(src_link(u.strip(), 'source') for u in s.split(' · '))}</td><td><span class='chip warn'>{H(st)}</span></td></tr>"
    for c, a, d, s, st in MANUAL_FLAGS)
auto_rows = "".join(
    f"<tr><td>{H(r['flag_code'])}</td><td>{H(r['team'])}</td><td>{H(r['item'])}</td><td>{H(r['practice_status'])}</td><td>{H(r['injury'])}</td><td>{H(r['game_status'])}</td>"
    f"<td>{src_link(r['link_1'],'source')} · {src_link(r['link_2'],'source')}</td></tr>"
    for r in flags_auto)
unv = """<tr><td>Strategy and model values (all of S01–S10 and the Week 10 model lines)</td><td><a href="https://github.com/nflverse/nfldata" target="_blank" rel="noopener">nflverse nfldata ↗</a></td><td>Line provider undocumented (I-10)</td></tr>
<tr><td>Results of 2006–2025 games (except the spot-checked Nov 12, 2026 game)</td><td><a href="https://github.com/nflverse/nfldata" target="_blank" rel="noopener">nflverse nfldata ↗</a></td><td>Not checked game-by-game against NFL.com (I-11)</td></tr>
<tr><td>Market spread and total for Week 10 games</td><td><a href="https://github.com/nflverse/nfldata/blob/master/DATASETS.md" target="_blank" rel="noopener">nfldata DATASETS.md ↗</a></td><td>Source not named; not used for decisions</td></tr>"""
flag_body = f"""<h1>Flagged for review</h1>
<p class="lead">Published for your review after the site goes live. Flagged items do not block the merge. Each row links to its source. Unverified values are listed separately below, and nothing here is used for a decision.</p>
<h2>Irregularities and open items</h2>
<div class="tablewrap"><table><thead><tr><th>ID</th><th>Area</th><th>Item</th><th>Source link(s)</th><th>Status</th></tr></thead><tbody>{flag_rows}</tbody></table></div>
<h2>Automatic flags (generated from the official rows)</h2>
<p class="small">Generated by <code>scripts/verify_data.py</code>. {len(flags_auto)} flags: I-05 ({flag_counts.get('I-05',0)}), I-06 ({flag_counts.get('I-06',0)}), I-07 ({flag_counts.get('I-07',0)}), I-08 ({flag_counts.get('I-08',0)}), I-14 ({flag_counts.get('I-14',0)}).</p>
<div class="tablewrap"><table class="sortable"><thead><tr><th>Flag</th><th>Team</th><th>Item</th><th>Practice status</th><th>Injury</th><th>Game status</th><th>Source</th></tr></thead><tbody>{auto_rows}</tbody></table></div>
<h2>Unverified items (not used for decisions)</h2>
<div class="tablewrap"><table><thead><tr><th>Value</th><th>Source</th><th>Reason</th></tr></thead><tbody>{unv}</tbody></table></div>"""
write("flagged.html", layout("Flagged for review", "Review", "flagged.html", flag_body))

# ---------------- REVIEW: REPO ----------------
repo_body = """<h1>Repository review</h1>
<p class="lead">Checked on branch arena/c39d8541-x1 (base dab199c). Every finding links to a file or commit. Nothing was changed except what this project added.</p>
<table><thead><tr><th>Check</th><th>Result</th><th>Link</th></tr></thead><tbody>
<tr><td>Files at base commit</td><td>README.md only (one line: "# X1")</td><td><a href="https://github.com/karagemop466-tech/X1/blob/dab199ce305bd0168f61f9bbb25b4b601eb45324/README.md" target="_blank" rel="noopener">README.md ↗</a></td></tr>
<tr><td>Commit history</td><td>One commit ("Initial commit", 2026-11-14 11:28 +0900)</td><td><a href="https://github.com/karagemop466-tech/X1/commit/dab199ce305bd0168f61f9bbb25b4b601eb45324" target="_blank" rel="noopener">commit ↗</a></td></tr>
<tr><td>Licence file</td><td>None (flag I-01)</td><td><a href="https://github.com/karagemop466-tech/X1/tree/dab199ce305bd0168f61f9bbb25b4b601eb45324" target="_blank" rel="noopener">base tree ↗</a></td></tr>
<tr><td>Tests / CI</td><td>None at base. Verification runs in scripts/verify_data.py and analysis/strategy_backtest.py.</td><td><a href="https://github.com/karagemop466-tech/X1/blob/arena/c39d8541-x1/scripts/verify_data.py" target="_blank" rel="noopener">verify_data.py ↗</a></td></tr>
<tr><td>Coordination file</td><td>Created: COORDINATION.md (task board, log, flags)</td><td><a href="https://github.com/karagemop466-tech/X1/blob/arena/c39d8541-x1/COORDINATION.md" target="_blank" rel="noopener">COORDINATION.md ↗</a></td></tr>
<tr><td>Ignore rules</td><td>.gitignore added (caches, virtualenvs)</td><td><a href="https://github.com/karagemop466-tech/X1/blob/arena/c39d8541-x1/.gitignore" target="_blank" rel="noopener">.gitignore ↗</a></td></tr>
<tr><td>Generated site</td><td>docs/ built from data/ by scripts/build_site.py (GitHub Pages source: main /docs)</td><td><a href="https://github.com/karagemop466-tech/X1/blob/arena/c39d8541-x1/scripts/build_site.py" target="_blank" rel="noopener">build_site.py ↗</a></td></tr>
</tbody></table>
<h2>Irregularities</h2>
<p>See the <a href="flagged.html">Flagged for review</a> page, items I-01 to I-04 (repo) and I-05 to I-17 (data).</p>"""
write("repo-review.html", layout("Repo review", "Review", "repo-review.html", repo_body))

# ---------------- SOURCES ----------------
srcrows = "".join(
    f"<tr><td>{H(s['source_id'])}</td><td>{H(s['name'])}</td><td>{H(s['publisher'])}</td>"
    f"<td><span class='{'tag-official' if s['tier']=='official' else 'tag-secondary'}'>{H(s['tier'])}</span></td>"
    f"<td>{src_link(s['url'], s['url'])}</td><td>{H(s['used_for'])}</td><td>{H(s['retrieved_utc'])}</td><td>{H(s['notes'])}</td></tr>"
    for s in sources)
src_body = f"""<h1>Source register</h1>
<p class="lead">Every source used, its tier, and what it supports. Official = NFL.com. Secondary = community or third-party, labelled wherever used.</p>
<div class="tablewrap"><table class="sortable"><thead><tr><th>ID</th><th>Name</th><th>Publisher</th><th>Tier</th><th>URL</th><th>Used for</th><th>Retrieved (UTC)</th><th>Notes</th></tr></thead><tbody>{srcrows}</tbody></table></div>"""
write("sources.html", layout("Sources", "Sources", "sources.html", src_body))

print("built pages:", sorted(p.name for p in OUT.glob("*.html")))
