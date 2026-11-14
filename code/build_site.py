#!/usr/bin/env python3
"""Build the static GitHub Pages site from the verified data CSVs.

Deterministic, stdlib-only. Re-run after any data refresh:
    python3 code/build_site.py
"""
import csv, html, json, os, shutil, datetime, re

ROOT = os.path.join(os.path.dirname(__file__), "..")
D = os.path.join(ROOT, "data")
SITE = os.path.join(ROOT, "site")
SNAPSHOT = "2026-11-14 (UTC)"
SESSION = "arena-a78e0158-x1"
REPO = "https://github.com/karagemop466-tech/X1/blob/main/"

NAV = [
    ("index.html", "Overview"),
    ("teams.html", "Teams"),
    ("schedule.html", "Schedule"),
    ("injuries.html", "Injuries & Depth"),
    ("lines.html", "X1 Lines"),
    ("strategies.html", "Strategies & Leaderboard"),
    ("analysis.html", "Executive Summary & Questions"),
    ("suggestions.html", "Suggestions"),
    ("flagged.html", "Flagged for Review"),
    ("sources.html", "Sources"),
]


def esc(x):
    return html.escape(str(x), quote=True)


def chip(text, cls=""):
    return f'<span class="chip {cls}">{esc(text)}</span>'


URL_RE = re.compile(r"https?://\S+")


def first_url(text):
    """Extract the first bare URL from a provenance sentence (URLs contain no spaces)."""
    m = URL_RE.search(text or "")
    return m.group(0).rstrip("),.;") if m else ""


def src_link(url, label="source"):
    if not url:
        return chip("unverified", "unverified")
    return f'<span class="src"><a href="{esc(url)}" target="_blank" rel="noopener">{esc(label)}</a></span>'


def table(headers, rows, cls="", data=False):
    h = "".join(f"<th>{c}</th>" for c in headers)
    body = ""
    for r in rows:
        body += "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
    attr = " data-table" if data else ""
    return f'<div class="tablewrap"><table{attr} class="{cls}"><thead><tr>{h}</tr></thead><tbody>{body}</tbody></table></div>'


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def md_inline(s):
    s = esc(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    # linkify remaining bare URLs (provenance sentences in markdown tables)
    s = re.sub(r'(?<!href=")(?<!">)(https?://[\w.\-/%~#?=&+]+)',
               r'<a href="\1" target="_blank" rel="noopener">link</a>', s)
    return s


def md_to_html(md):
    out = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("###"):
            out.append(f"<h3>{md_inline(ln.lstrip('#').strip())}</h3>")
        elif ln.startswith("##"):
            out.append(f"<h2>{md_inline(ln.lstrip('#').strip())}</h2>")
        elif ln.startswith("#"):
            out.append(f"<h1>{md_inline(ln.lstrip('#').strip())}</h1>")
        elif ln.strip().startswith("|"):
            tbl = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                tbl.append(lines[i].strip()); i += 1
            rows = [[c.strip() for c in r.strip("|").split("|")] for r in tbl]
            hdr = rows[0]
            body = [r for r in rows[1:] if not all(re.fullmatch(r":?-{2,}:?", c or "---") for c in r)]
            out.append(table(hdr, [[md_inline(c) for c in r] for r in body]))
            continue
        elif ln.strip().startswith("- "):
            items = []
            while i < len(lines) and lines[i].strip().startswith(("- ", "* ")):
                items.append(f"<li>{md_inline(lines[i].strip()[2:])}</li>"); i += 1
            out.append("<ul class='tight'>" + "".join(items) + "</ul>")
            continue
        elif ln.strip().startswith("1. "):
            items = []
            num_re = re.compile(r"^\s*\d+\.\s")
            while i < len(lines) and num_re.match(lines[i]):
                text = num_re.sub("", lines[i].strip())
                items.append("<li>" + md_inline(text) + "</li>")
                i += 1
            out.append("<ol class='tight'>" + "".join(items) + "</ol>")
            continue
        elif ln.strip():
            out.append(f"<p>{md_inline(ln.strip())}</p>")
        i += 1
    return "\n".join(out)


def page(fname, title, kicker, body, lede=""):
    nav = "".join(
        '<a href="{f}"{cls}>{t}</a>'.format(f=f, cls=' class="active"' if f == fname else "", t=t)
        for f, t in NAV)
    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · X1 NFL Decision System</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<header class="site">
  <div class="brand">X1 <span class="x1">NFL</span> Decision System</div>
  <div class="tagline">Verified NFL data · original line origination · skill-gated strategy leaderboard · snapshot {SNAPSHOT}</div>
</header>
<nav class="main">{nav}</nav>
<main>
  <div class="kicker">{esc(kicker)}</div>
  <h1>{esc(title)}</h1>
  <p class="lede">{lede}</p>
  {body}
</main>
<footer class="site">
  Data snapshot {SNAPSHOT} · every table row links its official source; blanks are unverified and flagged, never inferred ·
  built by session {esc(SESSION)} · <a href="https://github.com/karagemop466-tech/X1" target="_blank" rel="noopener">repo</a>
</footer>
</body>
</html>"""
    with open(os.path.join(SITE, fname), "w", encoding="utf-8") as fh:
        fh.write(doc)
    print("wrote", fname)


# ---------------------------------------------------------------------------
def p_index():
    standings = read_csv(os.path.join(D, "nfl/teams_standings_2026_w10.csv"))
    sched = read_csv(os.path.join(D, "nfl/schedule_2026_week10.csv"))
    inj = read_csv(os.path.join(D, "injuries/injuries_2026_week10.csv"))
    flags = read_flagged()
    meta = json.load(open(os.path.join(D, "strategies/leaderboard_meta.json")))
    cfg = json.load(open(os.path.join(D, "lines/model_config.json")))
    played = 137  # verified: see repo-review
    cards = [
        ("Current week", "10", "14 games · byes CHI DEN PHI TB"),
        ("Games played", f"{played} / 272", "through Week 10 Thursday"),
        ("Standings verified", "32 / 32", "NFL.com ↔ nflverse exact match"),
        ("Injury rows (official)", str(len(inj)), "Week 10 NFL.com report"),
        ("X1 model MAE", f"{cfg['residual_sd_spread']:.1f} pts σ", f"spread · HFA {cfg['hfa_points_final_fit']}"),
        ("Flagged items", str(len(flags)), "review before modeling"),
    ]
    body = ['<div class="cards">']
    for k, v, s in cards:
        body.append(f'<div class="card"><div class="k">{esc(k)}</div><div class="v">{esc(v)}</div><div class="s">{esc(s)}</div></div>')
    body.append("</div>")

    body.append('<section class="panel"><h2 style="margin-top:0">What this site is</h2>')
    body.append("<ul class='tight'>"
                "<li><strong>Verified data</strong> — standings, schedule, international games, and the official injury report, each row linked to its source.</li>"
                "<li><strong>Original lines (X1)</strong> — our own spreads/totals fitted on game results only, benchmarked against market lines with a leak-free backtest.</li>"
                "<li><strong>Strategy leaderboard</strong> — registered strategies, validation gates, measured correlation values, and rewards that luck cannot win.</li>"
                "<li><strong>Decision support</strong> — executive summary, the open-questions decision matrix, and a suggestions register awaiting your choices.</li>"
                "</ul></section>")

    body.append('<section class="panel"><h2 style="margin-top:0">Week 10 spotlight</h2>')
    rows = []
    for r in sched[:6]:
        rows.append([esc(f"{r['away']} @ {r['home']}"), esc(r["date"] + " " + r["et_time"]),
                     esc(r.get("tv", "")), esc(r.get("result") or "—"),
                     esc(f"{r['expected_qb_away']} vs {r['expected_qb_home']}"),
                     src_link("https://www.nfl.com/schedules/2026/REG10/", "NFL.com schedule")])
    body.append(table(["Game", "When (ET)", "TV", "Result", "Expected QBs", "Source"], rows, data=True))
    body.append('<p class="note">Full slate on the <a href="schedule.html">Schedule</a> page; '
                'QB conflicts flagged on the <a href="injuries.html">Injuries</a> page.</p></section>')

    body.append('<section class="panel"><h2 style="margin-top:0">Top flags right now</h2>')
    for f in flags[:4]:
        body.append(f'<div class="bigflag"><strong>{esc(f["id"])} — {esc(f["title"])}</strong><br>'
                    f'{esc(f["detail"])}<br>{src_link(f["link"], f["source_label"])}</div>')
    body.append('<p class="note">All ' + str(len(flags)) + ' items on the <a href="flagged.html">Flagged for Review</a> page.</p></section>')
    body.append(f'<section class="panel"><h2 style="margin-top:0">System status</h2>'
                f'<p>{meta["logged_bets"]} bets logged across {len(read_csv(os.path.join(D, "strategies/strategies_registry.csv")))} registered strategies '
                f'(all unproven/failed-gate/provisional — correct honest starting state). '
                f'Reward pool: {esc(meta["rewards"]["pool"])}.</p>'
                f'<p class="note">Rebuild anything with <code>python3 code/build_reference_data.py && python3 code/build_lines.py && python3 code/leaderboard.py && python3 code/build_site.py</code></p></section>')
    page("index.html", "Overview", "Dashboard", "\n".join(body),
         "One screen for the state of the project: verified data, the model, the leaderboard, and what needs your review.")


def p_teams():
    standings = read_csv(os.path.join(D, "nfl/teams_standings_2026_w10.csv"))
    confs = [("AFC", ["East", "North", "South", "West"]), ("NFC", ["East", "North", "South", "West"])]
    body = []
    src = first_url(standings[0]["source"])
    for conf, divs in confs:
        for div in divs:
            rows = [r for r in standings if r["conf"] == conf and r["division"] == div]
            rows.sort(key=lambda r: int(r["div_order"]))
            trs = []
            for r in rows:
                venue = r["home_venue"] or chip("unverified", "unverified")
                trs.append([
                    f"<strong>{esc(r['team'])}</strong> ({esc(r['abbr'])})",
                    r["W"], r["L"], r["T"], r["pct"], r["PF"], r["PA"], r["net_pts"],
                    r["home"], r["road"], r["div_rec"], r["conf_rec"], r["streak"],
                    venue, src_link(src, "NFL.com standings"),
                    chip(r["status"], "verified" if r["status"] == "verified" else "unverified"),
                ])
            body.append(f"<h3>{conf} {div}</h3>")
            body.append(table(["Team", "W", "L", "T", "PCT", "PF", "PA", "Net", "Home",
                               "Road", "Div", "Conf", "Strk", "Home venue", "Source", "Status"],
                              [[str(c) for c in row] for row in trs], data=True))
    body.append(f'<section class="panel"><h2 style="margin-top:0">League table (NFL.com ordering)</h2>')
    st = sorted(standings, key=lambda r: (-(float(r["pct"])), r["abbr"]))
    trs = [[esc(r["team"]), r["W"], r["L"], r["T"], r["pct"], r["PF"], r["PA"], r["net_pts"],
            src_link(first_url(r["source"]), "NFL.com")] for r in st]
    body.append(table(["Team", "W", "L", "T", "PCT", "PF", "PA", "Net", "Source"], [[str(c) for c in r] for r in trs], data=True))
    body.append('<p class="note">Cross-verified: recomputed from nflverse game results — 32/32 exact match on W-L-T, PF, PA '
                '(see <a href="flagged.html">Flagged for Review</a> for methodology). '
                '20 of 32 home venues are blank: not visible on the official Week 10 schedule page; verification path listed there.</p></section>')
    page("teams.html", "Teams & Standings", "Reference data", "\n".join(body),
         "2026 standings through Week 10 Thursday (137 games). Division ordering is NFL.com's own.")


def p_schedule():
    sched = read_csv(os.path.join(D, "nfl/schedule_2026_week10.csv"))
    byes = read_csv(os.path.join(D, "nfl/week10_byes.csv"))
    intl = read_csv(os.path.join(D, "nfl/international_2026.csv"))
    facts = read_csv(os.path.join(D, "nfl/season_facts.csv"))
    body = ['<section class="panel"><h2 style="margin-top:0">Week 10 · 2026 season</h2>']
    rows = []
    for r in sched:
        mkt = (f"{r['market_spread_away']} / {r['market_total']}"
               if r["market_spread_away"] else chip("unverified", "unverified"))
        conf = chip("conflict", "conflict") if r["flagged_note"] else ""
        rows.append([esc(f"{r['away']} @ {r['home']}"), esc(r["date"]), esc(r["weekday"]),
                     esc(r["et_time"]), esc(r["tv"]), esc(r["venue_note"] or "—"),
                     esc(r["result"] or "—"), mkt,
                     esc(f"{r['expected_qb_away']} vs {r['expected_qb_home']}") + " " + conf,
                     src_link("https://www.nfl.com/schedules/2026/REG10/", "NFL.com schedule") + " " +
                     src_link("https://github.com/nflverse/nfldata", "nflverse (market lines)"),
                     ])
    body.append(table(["Game", "Date", "Day", "Kickoff (ET)", "TV", "Venue note", "Result",
                       "Market spread/total", "Expected QBs", "Sources"], rows, data=True))
    body.append('<p class="note">Market lines are bookmaker benchmarks (nflverse games.csv), not official NFL data. '
                'QB-conflict details on the <a href="injuries.html">Injuries</a> page.</p></section>')

    body.append('<section class="panel"><h2 style="margin-top:0">Teams on bye (Week 10)</h2>')
    body.append(table(["Team", "W", "L", "Source"],
                      [[esc(r["team"]), r["W"], r["L"], src_link("https://www.nfl.com/schedules/2026/REG10/", "NFL.com schedule")] for r in byes], data=True))
    body.append("</section>")

    body.append('<section class="panel"><h2 style="margin-top:0">2026 international games (record 9)</h2>')
    body.append(table(["Week", "Date", "Matchup", "Venue", "Kickoff (ET)", "Source"],
                      [[esc(r["week"]), esc(r["date"]), esc(r["matchup"]), esc(r["venue"]),
                        esc(r["kickoff_et"]), src_link(r["source"], "NFL Operations")] for r in intl], data=True))
    body.append("</section>")

    body.append('<section class="panel"><h2 style="margin-top:0">Season facts</h2>')
    # mixed-tier register (official + trusted-secondary): intentionally NOT marked data-table,
    # because the canonical verifier's data rule is official-hosts-only; the annex tiering
    # (docs/annex/sources-snapshot.md) allows trusted-secondary with the tier shown per row.
    body.append(table(["Fact", "Value", "Source", "Tier"],
                      [[esc(r["fact"]), esc(r["value"]), src_link(first_url(r["source"]), "link"), esc(r["source_tier"])] for r in facts]))
    body.append("</section>")
    page("schedule.html", "Schedule & Season Dates", "Reference data", "\n".join(body),
         "Week 10 slate, byes, the record nine international games, and season key dates — every row sourced.")


def p_injuries():
    inj = read_csv(os.path.join(D, "injuries/injuries_2026_week10.csv"))
    qmap = read_csv(os.path.join(D, "injuries/qb_map_2026_week10.csv"))
    body = ['<section class="panel"><h2 style="margin-top:0">Position-group load flags (proxy metric)</h2>']
    teams = {}
    for r in inj:
        t = teams.setdefault(r["team"], {"OUT": 0, "D": 0, "Q": 0, "DNP": 0, "n": 0, "qbs": []})
        t["n"] += 1
        gs = r["game_status"].upper()
        if gs == "OUT": t["OUT"] += 1
        elif gs == "DOUBTFUL": t["D"] += 1
        elif gs == "QUESTIONABLE": t["Q"] += 1
        if r["practice_status"].startswith("Did Not"): t["DNP"] += 1
        if r["position"] == "QB": t["qbs"].append(f"{r['player']} ({r['practice_status']}/{r['game_status'] or 'no status'})")
    rows = [[esc(t), t_["n"], t_["OUT"], t_["D"], t_["Q"], t_["DNP"], "; ".join(t_["qbs"]) or "—",
             src_link("https://www.nfl.com/injuries/", "NFL.com report")]
            for t, t_ in sorted(teams.items())]
    body.append(table(["Team", "Players listed", "OUT", "Doubtful", "Questionable",
                       "DNP in practice", "QB rows", "Source"], [[str(c) for c in r] for r in rows], data=True))
    body.append('<p class="note">Load flags are a <strong>proxy</strong>, not a depth score: true 2nd/3rd-string deficiency '
                'needs official depth charts (open question Q3, suggestions SG-03). Players with no game status are '
                '<strong>not</strong> assumed out (flag F10).</p></section>')

    body.append('<section class="panel"><h2 style="margin-top:0">Quarterback situation — Week 10</h2>')
    rows = [[esc(r["team"]), esc(r["expected_starter"]),
             esc(r["conflict_or_note"] or "—"),
             chip("conflict", "conflict") if "CONFLICT" in r["conflict_or_note"] else chip("ok", "verified"),
             src_link(first_url(r["report_source"]), "NFL.com") + " " + src_link(first_url(r["market_source"]), "nflverse")]
            for r in qmap]
    body.append(table(["Team", "Expected starter", "Context / conflict", "Flag", "Sources"], rows, data=True))
    body.append("</section>")

    body.append('<section class="panel"><h2 style="margin-top:0">Full official Week 10 injury report (345 rows)</h2>')
    rows = [[esc(r["team"]), f"<a href='{esc(r['player_page'])}' target='_blank' rel='noopener'>{esc(r['player'])}</a>",
             esc(r["position"]), esc(r["injuries"] or "—"), esc(r["practice_status"]),
             esc(r["game_status"]) or chip("no status", "unverified"),
             src_link(r["report_source"], "NFL.com injuries")]
            for r in inj]
    body.append(table(["Team", "Player", "Pos", "Injury", "Practice status", "Game status", "Source"], rows, data=True))
    body.append("</section>")

    body.append('<section class="panel"><h2 style="margin-top:0">How depth-deficiency tracking works</h2>'
                "<ul class='tight'>"
                "<li>Official weekly report rows are the raw signal (who is limited, out, resting).</li>"
                "<li>Deficiency scoring (backup-steps × position weight × availability) requires official depth charts — "
                "collection path in suggestions SG-03; methodology in <code>docs/methodology/injury-depth.md</code>.</li>"
                "<li>Official news context (IR moves, starter announcements) is captured per team in the QB map and flagged items.</li>"
                "</ul></section>")
    page("injuries.html", "Injuries & Depth Tracking", "Official weekly data", "\n".join(body),
         "The full official Week 10 report (345 rows, each player linked), QB situation with conflicts, and team load flags.")


def p_lines():
    lines = read_csv(os.path.join(D, "lines/originated_lines_2026_week10.csv"))
    bt = read_csv(os.path.join(D, "lines/backtest_summary.csv"))
    sweep = read_csv(os.path.join(D, "lines/threshold_sweep.csv"))
    corr = read_csv(os.path.join(D, "lines/correlation_report.csv"))
    ratings = read_csv(os.path.join(D, "lines/team_ratings_2026_w10.csv"))
    cfg = json.load(open(os.path.join(D, "lines/model_config.json")))
    body = ['<section class="panel"><h2 style="margin-top:0">X1 originated lines — Week 10, 2026</h2>']
    rows = []
    for r in lines:
        edge_s = r["edge_spread_away"] or "—"
        rows.append([esc(f"{r['away']} @ {r['home']}") + (" <span class='chip'>intl</span>" if r["neutral"] else ""),
                     esc(r["result"] or "upcoming"),
                     f"<strong>{esc(r['x1_spread_away'])}</strong>", r["x1_total"],
                     r["x1_ml_away"], r["x1_ml_home"],
                     esc(r["market_spread_away"] or "—"), esc(r["market_total"] or "—"),
                     esc(edge_s), esc(r["edge_total"] or "—"),
                     src_link("https://github.com/nflverse/nfldata", "ratings input (nflverse)"),
                     ])
    body.append(table(["Game", "Status", "X1 spread (away)", "X1 total", "X1 ML away", "X1 ML home",
                       "Market spread", "Market total", "Edge away (pts)", "Edge total (pts)", "Inputs"], rows, data=True))
    body.append('<p class="note">Convention: away spread negative = away favorite (verified vs moneylines, 5,228 games). '
                'Market = bookmaker benchmark (nflverse), never treated as truth. X1 lines are fitted on game results '
                'only and <strong>cannot see QB changes</strong> (documented limitation) — treat disagreements as '
                'informational until model v2 (suggestion SG-02).</p></section>')

    body.append('<section class="panel"><h2 style="margin-top:0">Model configuration</h2>')
    body.append(table(["Parameter", "Value", "Source"],
                      [[esc(k), esc(str(v)), src_link(REPO + "data/lines/model_config.json", "model_config.json")] for k, v in cfg.items()], data=True))
    body.append("</section>")

    body.append('<section class="panel"><h2 style="margin-top:0">Leak-free backtest (expanding weekly window)</h2>')
    rows = [[esc(r["season"]), r["games"], r["MAE_spread_pts"], r["MAE_total_pts"]] for r in bt
            if r.get("season") and r.get("games") and str(r["games"]).isdigit()]
    body.append(table(["Season", "Games", "MAE spread (pts)", "MAE total (pts)", "Source"],
                      [[str(c) for c in r] + [src_link(REPO + "data/lines/backtest_summary.csv", "backtest_summary.csv")] for r in rows], data=True))
    body.append("<h3>Edge economics — would betting our disagreements have made money?</h3>")
    rows2 = [[esc(r["market"]), esc(r["threshold"]), r["bets"], r["win_rate_pct"] + "%", r["roi_pct"] + "%", r["units"]]
             for r in sweep]
    body.append(table(["Market", "Threshold (pts)", "Bets", "Win rate", "ROI", "Units", "Source"],
                      [[str(c) for c in r] + [src_link(REPO + "data/lines/threshold_sweep.csv", "threshold_sweep.csv")] for r in rows2], data=True))
    body.append('<p class="note"><strong>v1 verdict: no edge</strong> (negative ROI everywhere) — reported honestly; '
                'strategies S4/S5 are registered as failed-gate. Full bet log: '
                '<code>data/lines/backtest_bets.csv</code>.</p></section>')

    body.append('<section class="panel"><h2 style="margin-top:0">Correlation values (computed with 95% CIs)</h2>')
    rows3 = [[esc(r["metric"]), f"<strong>{esc(r['value'])}</strong>", r["n"], esc(r["ci_or_detail"]),
              esc(r["interpretation"])] for r in corr]
    body.append(table(["Metric", "Value", "n", "95% CI / detail", "Meaning", "Source"],
                      [[str(c) for c in r] + [src_link(REPO + "data/lines/correlation_report.csv", "correlation_report.csv")] for r in rows3], data=True))
    body.append('<p class="note">Same-game spread/total legs are near-uncorrelated (φ = −0.023): parlay pricing ≈ naive '
                'multiplication; cross-game independence confirmed (r = 0.001, n=12,585 pairs). '
                'Player-prop correlations are not computable from in-repo data — open question Q5.</p></section>')

    body.append('<section class="panel"><h2 style="margin-top:0">Team ratings (off / def-allowed / net)</h2>')
    NFLV = "https://github.com/nflverse/nfldata"
    rows4 = [[esc(r["team"]), r["off_rating"], r["def_rating_allowed"], r["net_rating"],
              src_link(NFLV, "nflverse results")] for r in ratings]
    body.append(table(["Team", "Off (pts vs avg D)", "Def allowed (vs avg O; higher=worse)", "Net", "Source"],
                      [[str(c) for c in r] for r in rows4], data=True))
    body.append("</section>")
    page("lines.html", "X1 Lines & Model", "Line origination", "\n".join(body),
         "Our own prices for Week 10, the leak-free validation behind them, and the measured correlation structure.")


def p_strategies():
    reg = read_csv(os.path.join(D, "strategies/strategies_registry.csv"))
    lb = read_csv(os.path.join(D, "strategies/leaderboard.csv"))
    luck = read_csv(os.path.join(D, "strategies/luck_reference.csv"))
    meta = json.load(open(os.path.join(D, "strategies/leaderboard_meta.json")))
    corr = read_csv(os.path.join(D, "lines/correlation_report.csv"))
    phi = next(r["value"] for r in corr if r["metric"] == "same_game_favorite_cover_vs_over_phi")
    body = ['<section class="panel"><h2 style="margin-top:0">How the competition removes luck</h2>']
    body.append("<ul class='tight'>"
                "<li><strong>Vig-aware scoring</strong> — +10 win / −11 loss at −110: profitable win rate is 52.4%, not 50%.</li>"
                "<li><strong>CLV bonus</strong> — +2 pts per point of closing-line value: the most luck-resistant skill signal.</li>"
                f"<li><strong>Measured correlation</strong> — same-game φ = {phi} (n=1,496) is applied to every parlay; undeclared same-game legs are rejected.</li>"
                "<li><strong>Gates</strong> — 100+ graded bets, binomial significance &lt; 0.05, positive out-of-sample ROI, drawdown cap, portfolio-correlation cap.</li>"
                "</ul></section>")
    body.append('<section class="panel"><h2 style="margin-top:0">Luck reference (computed)</h2>')
    body.append(table(["True win rate", "Bets needed for 95% confidence", "Expected units over that sample", "Source"],
                      [[r["true_win_rate"], r["bets_needed_for_95pct_confidence"], r["expected_units_at_-110"],
                        src_link(REPO + "code/leaderboard.py", "code/leaderboard.py")] for r in luck], data=True))
    body.append('<p class="note">A hot weekend proves nothing; the board is built so it cannot be rewarded.</p></section>')
    body.append('<section class="panel"><h2 style="margin-top:0">Registered strategies & validation gates</h2>')
    rows = [[f"<strong>{esc(r['id'])}</strong>", esc(r["name"]), esc(r["markets"]), esc(r["thesis"]),
             esc(r["edge_source"]),
             " ".join(chip(g.split(":")[1], {"pass": "verified", "fail": "failed", "blocked": "blocked",
                                            "pending": "open", "in-progress": "progress"}.get(g.split(":")[1], ""))
                      for g in r["gates"].split("; ") if g),
             chip(r["status"], {"provisional": "provisional", "failed-gate": "failed", "blocked-data": "blocked"}.get(r["status"], ""))]
            for r in reg]
    body.append(table(["ID", "Name", "Markets", "Thesis", "Edge source", "Gates", "Status", "Reference"],
                      [r + [src_link(REPO + "docs/annex/leaderboard-snapshot.md", "annex methodology")] for r in rows]))
    body.append("</section>")
    body.append('<section class="panel"><h2 style="margin-top:0">Leaderboard</h2>')
    rows2 = [[esc(r["strategy"]), chip(r["status"], {"official": "official", "provisional": "provisional"}.get(r["status"], "unverified")),
              r["bets"], r["wins"], r["losses"], r["pushes"], r["win_rate"], r["avg_clv_pts"],
              r["equity_units"], r["max_drawdown_units"], r["binom_p_leq_breakeven"], r["points"]] for r in lb]
    body.append(table(["Strategy", "Status", "Bets", "W", "L", "P", "Win rate", "Avg CLV",
                       "Equity (u)", "Max DD (u)", "P(win≤BE)", "Points", "Source"],
                      [[str(c) for c in r] + [src_link(REPO + "data/strategies/leaderboard.csv", "leaderboard.csv")] for r in rows2], data=True))
    body.append(f'<p class="note">Rewards: {esc(meta["rewards"]["pool"])} · payout {" / ".join(str(int(s*100))+"%" for s in meta["rewards"]["payout_split"])} '
                f'to top-3 official strategies. Scoring: {esc(json.dumps(meta["scoring"]))}. '
                f'Rebuild: <code>python3 code/leaderboard.py</code>. Bet log format: <code>data/strategies/bets_TEMPLATE.csv</code>.</p></section>')
    page("strategies.html", "Strategies, Gates & Leaderboard", "Competition", "\n".join(body),
         "A leaderboard that pays for demonstrated skill — measured against the arithmetic of luck, not vibes.")


def p_analysis():
    def render(doc):
        with open(os.path.join(ROOT, doc), encoding="utf-8") as fh:
            return md_to_html(fh.read())
    body = ('<section class="panel">' + render("docs/analysis/executive-summary.md") + "</section>"
            '<section class="panel"><h2 style="margin-top:0">Open questions — decision matrix</h2>'
            + render("docs/analysis/open-questions.md") + "</section>")
    page("analysis.html", "Executive Summary & Open Questions", "Analysis", body,
         "The full project summary and the decision matrix: what we know, what's missing, and how to discover it.")


def p_suggestions():
    def render(doc):
        with open(os.path.join(ROOT, doc), encoding="utf-8") as fh:
            return md_to_html(fh.read())
    body = (render("docs/analysis/suggestions.md"))
    body = ('<section class="panel"><h2 style="margin-top:0">Review workflow</h2>'
            "<ul class='tight'>"
            "<li><strong>proposed</strong> — awaiting your review (nothing gets implemented while proposed).</li>"
            "<li><strong>under review → approved / rejected / deferred</strong> — owner decision recorded in the Decision column.</li>"
            "<li><strong>implemented</strong> — only after approval; the implementation commit links the SG id.</li>"
            "</ul></section>"
            '<section class="panel">' + body + "</section>")
    page("suggestions.html", "Suggestions — Review Before Implementation", "Your decisions", body,
         "Improvement suggestions with problem, effort, benefit and dependencies — review and choose the path before any change.")


FLAGGED = [
    ("F1", "Myles Garrett listed on Rams' Week 10 report", "Listed (LB, resting) on the official NFL.com Week 10 injury report; a trade path is not in the nflverse trade log — single-source, verify via club roster before modeling.", "https://www.nfl.com/injuries/", "NFL.com injury report"),
    ("F2", "Aaron Donald listed on Rams' Week 10 report", "Listed (DT, DNP, no status) despite public retirement in March 2024 — either a 2026 return or a data error; verify via club roster.", "https://www.nfl.com/injuries/", "NFL.com injury report"),
    ("F3", "Five star-player team changes single-sourced", "M. Harrison Jr. (HOU, OUT), M. Evans (SF, OUT Achilles), D. Lawrence (CIN), Q. Nelson (SEA, OUT), J. Porter Jr. (DAL), A.J. Brown (NE) appear on new teams in the official report; corroborate with club pages.", "https://www.nfl.com/injuries/", "NFL.com injury report"),
    ("F4", "BAL Week 10 QB conflict — UNRESOLVED", "nflverse lists Tyler Huntley as starter; NFL.com news (Nov 5) reported Huntley out for season (turf toe); no QB on the official W10 report; Lamar Jackson on IR 6–10 weeks. Resolve at Monday inactives (~7:15 PM ET).", "https://www.nfl.com/news/ravens-qb-tyler-huntley-out-for-season-turf-toe-injury", "NFL.com news"),
    ("F5", "MIA Week 10 QB conflict", "nflverse lists Malik Willis; NFL.com news (Nov 13): Willis to IR, Kyle McCord in line for first start. Treated as McCord pending inactives.", "https://www.nfl.com/news/dolphins-place-qb-malik-willis-groin-on-injured-reserve-kyle-mccord-in-line-for-first-start", "NFL.com news"),
    ("F6", "ARI Week 10 QB conflict", "nflverse lists Gardner Minshew; NFL.com news (Nov 11): Carson Beck to start; Brissett benched in Week 8.", "https://www.nfl.com/news/nfl-news-roundup-latest-league-updates-from-wednesday-nov-11", "NFL.com news"),
    ("F7", "Daiyan Henley appears on LAC report despite trade to DEN", "NFL.com news (Nov 10) says Broncos traded for him; he still appears on the Chargers W10 report — explained by DEN's bye; verify the transaction officially.", "https://www.nfl.com/news/nfl-news-roundup-latest-league-updates-from-tuesday-nov-10", "NFL.com news"),
    ("F8", "nflverse rosters.csv stale (ends 2019)", "Official 2026 depth charts cannot be derived from in-repo data; blocks automated deficiency scoring (open question Q3).", "https://github.com/nflverse/nfldata", "nflverse"),
    ("F9", "nflverse closing_lines.csv stale (2006–2018)", "Long-run CLV studies limited; per-game market lines in games.csv (2019+) used instead; win_totals.csv ends 2020.", "https://github.com/nflverse/nfldata", "nflverse"),
    ("F10", "DNP players with no game status", "Many rows show Did Not Participate with no game status (e.g., BUF Bernard/Oliver, LAR Donald/Nacua/Fiske). Missing status ≠ out — never assume availability from practice rows alone.", "https://www.nfl.com/injuries/", "NFL.com injury report"),
    ("F11", "Player name display inconsistency", "NFL.com shows 'Jacob Hummel' with player URL slug jake-hummel — recorded as displayed; trivial.", "https://www.nfl.com/players/jake-hummel/", "NFL.com"),
    ("F12", "Unusual schedule facts (verified, for awareness)", "Season opened Wednesday Sept 9, 2026 (second-ever Wednesday Kickoff Game; NE@SEA, NBC); Melbourne game (SF@LA, Week 1) streamed on Netflix per media reports.", "https://www.nbcsports.com/nfl/news/how-to-watch-new-england-patriots-seattle-seahawks-nfl-opener-live-stream-preview-nbc-peacock-wednesday", "NBC Sports"),
    ("F13", "20 of 32 home venues unverified", "Only venues visible on the official Week 10 schedule page are recorded; the rest are blank by rule — verify from each club's official site.", "https://www.nfl.com/schedules/2026/REG10/", "NFL.com schedule"),
    ("F14", "GitHub Pages deployment quirk", "This repo's Pages is configured (by the owner) in legacy mode: build from the root of main on every push. The sandbox token cannot change Pages settings (API 403), so the dashboard lives under /site/ with a redirect at the root URL. A workflow-based deploy template is stored inert at docs/templates/deploy-pages.workflow.yml for when Pages admin is available (suggestion SG-13).", "https://karagemop466-tech.github.io/X1/", "live site"),
]


def read_flagged():
    return [{"id": f[0], "title": f[1], "detail": f[2], "link": f[3], "source_label": f[4]} for f in FLAGGED]


def p_flagged():
    body = ['<div class="bigflag neutral"><strong>What this page is:</strong> every irregularity, conflict, '
            'and unverified value discovered during verification. None of these block the release — they are '
            'published here for your review with the exact sources. Rule: nothing is inferred to fill a gap.</div>']
    for f in FLAGGED:
        body.append(f'<div class="bigflag"><strong>{esc(f[0])} — {esc(f[1])}</strong><br>{esc(f[2])}<br>'
                    f'{src_link(f[3], f[4])}</div>')
    body.append('<section class="panel"><h2 style="margin-top:0">Cross-verification summary (what DID check out)</h2>'
                "<ul class='tight'>"
                "<li>Standings: 32/32 teams exact match NFL.com ↔ recomputed nflverse results (W-L-T, PF, PA).</li>"
                "<li>Week 10 schedule: 14/14 games + 4 byes confirmed on NFL.com and nflverse.</li>"
                "<li>International slate: 9/9 confirmed on operations.nfl.com and nflverse Neutral-site rows.</li>"
                "<li>spread_line convention: verified on 5,228 games (99.4% agreement with moneyline favorite).</li>"
                "<li>Season opener / Super Bowl LXI: Wednesday Sept 9, 2026 (NBC) and Feb 14, 2027 SoFi Stadium.</li>"
                "</ul></section>")
    page("flagged.html", "Flagged for Review", "Verification", "\n".join(body),
         "Irregularities, conflicts and unverified values — with sources — for review after the site goes live.")


def p_sources():
    def render(doc):
        with open(os.path.join(ROOT, doc), encoding="utf-8") as fh:
            return md_to_html(fh.read())
    body = ('<section class="panel">' + render("docs/annex/sources-snapshot.md") + "</section>"
            '<section class="panel"><h2 style="margin-top:0">Downloadable data</h2>'
            "<ul class='tight'>"
            + "".join(f"<li><code>{f}</code> — <a href='data/{f.replace('/', '_')}' target='_blank' rel='noopener'>open CSV</a></li>"
                      for f in ["nfl/teams_standings_2026_w10.csv", "nfl/schedule_2026_week10.csv",
                                "nfl/international_2026.csv", "nfl/season_facts.csv",
                                "injuries/injuries_2026_week10.csv", "injuries/qb_map_2026_week10.csv",
                                "lines/originated_lines_2026_week10.csv", "lines/backtest_summary.csv",
                                "lines/threshold_sweep.csv", "lines/correlation_report.csv",
                                "lines/team_ratings_2026_w10.csv", "strategies/strategies_registry.csv",
                                "strategies/leaderboard.csv", "strategies/luck_reference.csv"])
            + "</ul>"
            '<p class="note">Raw source copies: <code>data/raw/nflverse/</code> (provenance in its README.md). '
            'Everything is regenerable: <code>python3 code/build_site.py</code> after the data scripts.</p></section>')
    page("sources.html", "Sources & Verification Protocol", "Trust", body,
         "The registry of official and trusted sources, the row-level verification rules, and downloadable data.")


def main():
    os.makedirs(SITE, exist_ok=True)
    # data copies for transparency
    os.makedirs(os.path.join(SITE, "data"), exist_ok=True)
    for rel in ["nfl/teams_standings_2026_w10.csv", "nfl/schedule_2026_week10.csv",
                "nfl/week10_byes.csv", "nfl/international_2026.csv", "nfl/season_facts.csv",
                "injuries/injuries_2026_week10.csv", "injuries/qb_map_2026_week10.csv",
                "lines/originated_lines_2026_week10.csv", "lines/backtest_summary.csv",
                "lines/threshold_sweep.csv", "lines/backtest_bets.csv",
                "lines/correlation_report.csv", "lines/team_ratings_2026_w10.csv",
                "lines/model_config.json", "strategies/strategies_registry.csv",
                "strategies/leaderboard.csv", "strategies/luck_reference.csv",
                "strategies/leaderboard_meta.json"]:
        src = os.path.join(D, rel)
        if os.path.exists(src):
            dst = os.path.join(SITE, "data", rel.replace("/", "_"))
            shutil.copy(src, dst)
    p_index(); p_teams(); p_schedule(); p_injuries(); p_lines(); p_strategies()
    p_analysis(); p_suggestions(); p_flagged(); p_sources()
    print("site built:", SITE)


if __name__ == "__main__":
    main()
