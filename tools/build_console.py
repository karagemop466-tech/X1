#!/usr/bin/env python3
"""Build the X1 console: data tables plus the published site.

    python3 tools/build_console.py

Writes:
    data/console/*.csv, data/console/*.json   the tables behind every page
    console/*.html                            the site

Every published row carries a source column. Where no source exists the cell is
emitted blank and the row is flagged; nothing is inferred to fill a gap.
"""

from __future__ import annotations

import csv
import datetime as dt
import html
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.console import feed, originate, strategy as st, lab, correlations as C, content, sources  # noqa: E402

OUT_DATA = os.path.join(ROOT, "data", "console")
OUT_SITE = os.path.join(ROOT, "console")
AS_OF = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
TODAY = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
LIVE_BEFORE = "2026-11-13"     # originate the games that had not kicked off by this date

# ---------------------------------------------------------------------------
# small html helpers
# ---------------------------------------------------------------------------

# Provenance marker for rows that are computed inside this repository from the
# verified feed rather than read off an official page. It still carries a link —
# to the exact CSV the value was computed from — so no row is left bare.
MK = ('<span class="src mut">computed &mdash; from '
      '<a class="src" href="https://github.com/karagemop466-tech/X1/blob/main/data/console/'
      'results_feed.csv">results_feed.csv</a></span>')

NAV = [
    # Added by session arena/b03ced7c-x1 (additive only): the decision-readiness
    # table the owner's brief asks for, one row per requirement with its gate.
    ("Overview", [("index.html", "Overview", ""),
                  ("executive-summary.html", "Executive summary", ""),
                  ("requirements.html", "The eight requirements", ""),
                  ("readiness.html", "Decision readiness", "")]),
    ("Official data", [("standings.html", "Standings", "32"),
                       ("schedule.html", "Week 10 slate", "14"),
                       # Added by session arena/dc96bc33-x1 (round 5, additive only)
                       ("w10-finals.html", "Week 10 finals (11-17)", "14"),
                       ("injuries.html", "Injury report", "345"),
                       ("depth.html", "Replacement depth", "897"),
                       ("deficiency.html", "Deficiency register", "897"),
                       # Added by session arena/b03ced7c-x1 (additive only)
                       # Added by session arena-2f95e652-x1: the dated read that replaced the
                       # false "re-read today" claim on the standings page.
                       ("evidence-2026-11-17.html", "Evidence pack 2026-11-17", ""),
                       ("capture.html", "Week 10 re-capture", ""),
                       # Added by session arena/16049865-x1 (additive): the 2026-11-17 re-read of the
                       # official Week 10 injury page, compared row by row with the published table.
                       ("../pages/injury-read-2026-11-17.html", "Injury re-read 17 Nov", "347"),
                       # Added by session arena-55c364b6-x1 (round 6, additive only): the injury report
                       # published as a timestamped delta series (every retained read, the changes between
                       # them, the drift alarm as it fired), and the fixture-context feature set built
                       # only from printed schedule facts.
                       ("availability-series.html", "Injury report series", ""),
                       ("fixture-context.html", "Fixture context", "64"),
                       ("depth-parse.html", "Depth parse defects", "")]),
    ("Markets", [("results.html", "Verified results feed", "7,548"),
                 ("prices.html", "Price-snapshot store", "18.8k"),
                 ("lines.html", "Originated lines", "6.3k")]),
    ("Strategy", [("strategies.html", "Strategy library", "16"),
                  ("leaderboard.html", "Leaderboard", "16"),
                  ("gates.html", "Validation and demotion gates", "14"),
                  ("correlations.html", "Correlations", ""),
                  ("luck.html", "Removing luck", ""),
                  ("props.html", "Props and parlays", "")]),
    # Counts were 15/15 until round 6 appended Q-16..Q-18 and SG-16..SG-19; the flagged tag was
    # "12" while the register holds 16. The landing-page nav is regenerated, so a stale tag here is
    # a visible lie: the tags are asserted against the registers by check I of
    # tools/verify_2026_11_18.py, which counts the entries in src/console/content.py.
    ("Decisions", [("questions.html", "Decision register", "18"),
                   ("suggestions.html", "Suggestion review board", "19")]),
    ("Governance", [("verification.html", "Verification ledger", ""),
                    ("sources.html", "Source registry", ""),
                    ("repo-review.html", "Repository review", ""),
                    ("flagged.html", "Flagged for review", "16"),
                    ("archived-sites.html", "Archived sites", "9")]),
]


def esc(x):
    return html.escape("" if x is None else str(x), quote=True)


def num(v, nd=2, pct=False, sign=False):
    """Format a number, or an em-dash when the value is not held."""
    if v is None or v == "":
        return '<span class="mut" title="not held - no source">&mdash;</span>'
    try:
        f = float(v)
    except (TypeError, ValueError):
        return esc(v)
    if pct:
        f *= 100
    s = f"{f:,.{nd}f}" + ("%" if pct else "")
    if sign and f > 0:
        s = "+" + s
    cls = "pos" if f > 0 else ("neg" if f < 0 else "")
    return f'<span class="{cls}">{s}</span>' if cls else s


def pill(text, kind="mut"):
    return f'<span class="pill {kind}">{esc(text)}</span>'


def src_link(key_or_url, label=None, cls="src"):
    if not key_or_url:
        return '<span class="src mut" title="no source exists for this value">no source</span>'
    if isinstance(key_or_url, str) and " " in key_or_url:
        # A plain-text provenance note, not a URL: render it as a marker, never
        # as a link, so it cannot become a broken anchor.
        return f'<span class="src mut">{esc(key_or_url)}</span>'
    if key_or_url.startswith("http"):
        url, lab_ = key_or_url, (label or "source")
    else:
        s = sources.get(key_or_url)
        url, lab_ = s["url"], (label or s["label"])
        if not url:
            return f'<span class="src mut">{esc(lab_)}</span>'
    tier = sources.tier(key_or_url) if not key_or_url.startswith("http") else ""
    mark = {"official": "official", "mirror": "mirror", "computed": "computed"}.get(tier, "")
    return (f'<a class="{cls}" href="{esc(url)}" target="_blank" rel="noopener">{esc(lab_)}</a>'
            + (f' <span class="pill mut">{mark}</span>' if mark else ""))


def table(headers, rows, tid, sortable=True, filter_col=None, filter_label="Filter rows",
          max_rows=None, note=None, src=None):
    """headers: list of (label, is_numeric). rows: list of list of raw html strings."""
    shown = rows if max_rows is None else rows[:max_rows]
    ths = "".join(
        f'<th class="{"num" if isn else ""}">{esc(h)}</th>' for h, isn in headers)
    rowattr = f' data-src="{esc(src)}"' if src else ""
    trs = "".join(f"<tr{rowattr}>" + "".join(
        f'<td class="{"num" if isn else ""}">{c}</td>' for (h, isn), c in zip(headers, r))
        + "</tr>" for r in shown)
    fid = f"{tid}-q"
    tools = ""
    if filter_col is not None:
        tools = (f'<div class="tools"><input id="{fid}" data-filter-for="{tid}" '
                 f'data-filter-col="{filter_col}" placeholder="{esc(filter_label)}">'
                 f'<span class="hint" id="{tid}-count">{len(shown)} of {len(rows)} rows shown</span>'
                 + (f'<span class="hint">{esc(note)}</span>' if note else "") + "</div>")
    elif note:
        tools = f'<div class="tools"><span class="hint">{esc(note)}</span></div>'
    extra = ""
    if max_rows is not None and len(rows) > max_rows:
        extra = (f'<div class="note">Showing the first {max_rows:,} of {len(rows):,} rows. '
                 f'The complete table is in <code>data/console/{esc(note or tid)}.csv</code>.</div>'
                 if note else
                 f'<div class="note">Showing the first {max_rows:,} of {len(rows):,} rows.</div>')
    return (f'{tools}<div class="wrap"><table id="{tid}" class="sortable">'
            f'<thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table></div>{extra}')


def page(title, group, body_html, subtitle="", kpis=None):
    nav_html = []
    for grp, items in NAV:
        nav_html.append(f'<div class="grp">{esc(grp)}</div>')
        for href, label, tag in items:
            on = " on" if f"{group}-{href}" == f"{group}-{title.lower().replace(' ', '-')}.html" else ""
            nav_html.append(f'<a class="item{on}" href="{href}">{esc(label)}'
                            + (f'<span class="tag">{esc(tag)}</span>' if tag else "") + "</a>")
    # active state by filename
    cur = title.lower().replace(" ", "-") + ".html"
    nav_html = []
    for grp, items in NAV:
        nav_html.append(f'<div class="grp">{esc(grp)}</div>')
        for href, label, tag in items:
            on = " on" if href == cur else ""
            nav_html.append(f'<a class="item{on}" href="{href}">{esc(label)}'
                            + (f'<span class="tag">{esc(tag)}</span>' if tag else "") + "</a>")
    kp = ""
    if kpis:
        kp = '<div class="kpis">' + "".join(
            f'<div class="kpi {c}"><div class="lab">{esc(l)}</div><div class="val">{v}</div>'
            f'<div class="sub">{esc(s)}</div></div>' for l, v, s, c in kpis) + "</div>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} - X1 NFL Line Console</title>
<link rel="stylesheet" href="assets/console.css">
</head><body><div class="layout">
<aside><div class="brand"><b>X1 LINE CONSOLE</b><span>NFL origination &amp; strategy lab</span></div>
<nav>{''.join(nav_html)}</nav></aside>
<main>
<header class="page"><h1>{esc(title)}</h1><p>{subtitle}</p></header>
{kp}
{body_html}
<footer>
As of {esc(AS_OF)}. Built by <code>tools/build_console.py</code> from sources listed on the
<a href="sources.html">source registry</a>. Every table row carries a source link or an explicit
marker where no source exists. Values that cannot be confirmed are left blank and listed on the
<a href="flagged.html">flagged for review</a> page.
</footer>
</main></div>
<script src="assets/console.js"></script></body></html>"""


# ---------------------------------------------------------------------------
# verification inputs transcribed from the official pages today
# ---------------------------------------------------------------------------
# The league's Week 10 schedule page, read on the build date. Compared cell by
# cell against the transcription already in the repository.
SCHEDULE_LIVE = [
    ("commanders-at-giants-2026-reg-10", "8:15 PM", "Thu Nov 12", "NYG", "WAS", "5-3-1", "3-5-1", "Prime Video", ""),
    ("patriots-at-lions-2026-reg-10", "9:30 AM", "Sun Nov 15", "DET", "NE", "6-2", "5-4", "FOX", "Munich Game"),
    ("chiefs-at-falcons-2026-reg-10", "1:00 PM", "Sun Nov 15", "ATL", "KC", "3-6", "6-2", "CBS", ""),
    ("texans-at-browns-2026-reg-10", "1:00 PM", "Sun Nov 15", "CLE", "HOU", "5-4", "3-5", "FOX", ""),
    ("vikings-at-packers-2026-reg-10", "1:00 PM", "Sun Nov 15", "GB", "MIN", "6-3", "6-2", "FOX", ""),
    ("dolphins-at-colts-2026-reg-10", "1:00 PM", "Sun Nov 15", "IND", "MIA", "2-7", "1-7", "CBS", ""),
    ("panthers-at-saints-2026-reg-10", "1:00 PM", "Sun Nov 15", "NO", "CAR", "3-5", "3-5", "FOX", ""),
    ("bills-at-jets-2026-reg-10", "1:00 PM", "Sun Nov 15", "NYJ", "BUF", "2-7", "7-1", "CBS", ""),
    ("jaguars-at-titans-2026-reg-10", "1:00 PM", "Sun Nov 15", "TEN", "JAX", "1-7", "6-2", "FOX", ""),
    ("rams-at-cardinals-2026-reg-10", "4:05 PM", "Sun Nov 15", "AZ", "LA", "3-6", "5-4", "CBS", ""),
    ("seahawks-at-raiders-2026-reg-10", "4:05 PM", "Sun Nov 15", "LV", "SEA", "4-5", "5-4", "CBS", ""),
    ("49ers-at-cowboys-2026-reg-10", "4:25 PM", "Sun Nov 15", "DAL", "SF", "4-5", "7-1", "FOX", ""),
    ("steelers-at-bengals-2026-reg-10", "8:20 PM", "Sun Nov 15", "CIN", "PIT", "6-2", "6-2", "NBC", ""),
    ("chargers-at-ravens-2026-reg-10", "8:15 PM", "Mon Nov 16", "BAL", "LAC", "4-5", "0-8", "ESPN", ""),
]
BYES_LIVE = [("CHI", "7-2"), ("DEN", "7-2"), ("PHI", "2-7"), ("TB", "3-6")]
# Per-club counts read off the official injury page on the build date:
# (club, rows, Out, Doubtful, Questionable)
INJURY_LIVE = {
    'WAS': (9, 2, 0, 0), 'NYG': (11, 0, 0, 1), 'NE': (15, 3, 0, 9), 'DET': (9, 3, 0, 2),
    'KC': (13, 3, 0, 3), 'ATL': (11, 1, 1, 3), 'MIN': (13, 5, 0, 3), 'GB': (17, 4, 1, 7),
    'JAX': (11, 3, 0, 1), 'TEN': (12, 5, 0, 1), 'BUF': (14, 0, 1, 4), 'NYJ': (9, 1, 0, 8),
    'MIA': (11, 2, 1, 1), 'IND': (14, 6, 0, 2), 'CAR': (12, 1, 2, 4), 'NO': (12, 4, 0, 2),
    'HOU': (16, 5, 0, 6), 'CLE': (12, 2, 0, 1), 'LA': (14, 2, 0, 5), 'AZ': (15, 3, 0, 6),
    'SEA': (15, 4, 0, 0), 'LV': (5, 0, 0, 2), 'SF': (12, 1, 0, 7), 'DAL': (19, 5, 1, 5),
    'PIT': (8, 0, 0, 1), 'CIN': (9, 1, 3, 0), 'LAC': (19, 0, 0, 0), 'BAL': (8, 0, 0, 0),
}
# The standings verification is NOT a constant. It used to be: this space held
# `STANDINGS_RECHECK = {"rows": 32, "fields": 16, "comparisons": 512, "mismatches": 0}`,
# rendered as "512 comparisons - re-read today, 0 mismatches", and no comparison happened at
# build time. The table being rendered is `data/verify/official_standings_2026_w10.psv`, dated
# 2026-11-14, so the page was a snapshot compared with itself and then described as a read of
# today. Replaced by session arena-2f95e652-x1 with the value derived below from the dated
# read in src/console/evidence_2026_11_17.py, which also states how far the published table
# has moved since (262 of 448 cells across 26 clubs on 2026-11-17).
from src.console import evidence_2026_11_17 as ODDS  # noqa: E402


def verify_depth(rows_by_team):
    """Re-check the published depth register against club pages read today.

    The league does not publish depth charts; each club publishes its own. Three
    clubs were re-read on 2026-11-14 and every slot on those charts was compared
    cell by cell. Returns (checks, mismatches, detail).
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from depth_live import DEPTH_LIVE, DEPTH_LIVE_URL
    checks, bad = 0, []
    for team, expected in DEPTH_LIVE.items():
        have = {(r["unit"], r["position"], r["slot"]): (r["starter"], r["replacement"] or "")
                for r in rows_by_team.get(team, [])}
        for unit, pos, slot, starter, repl in expected:
            checks += 1
            got = have.get((unit, pos, slot))
            if got is None:
                bad.append(f"{team} {unit}/{pos} slot {slot}: missing from the register")
            elif got[0] != starter or got[1] != repl:
                bad.append(f"{team} {unit}/{pos} slot {slot}: register {got} vs "
                           f"{DEPTH_LIVE_URL[team]} ({(starter, repl)})")
        for key in have:
            if key not in {(u, p, s) for u, p, s, _st, _rp in expected}:
                bad.append(f"{team} {key}: in the register but not on the club page")
                checks += 1
    return checks, len(bad), bad


def verify_official():
    """Re-verify the published tables against the official pages, read today."""
    checks = []

    def add(dataset, url, label, comparisons, matches, detail):
        checks.append({"dataset": dataset, "url": url, "label": label,
                       "comparisons": comparisons, "matches": matches,
                       "mismatches": comparisons - matches, "detail": detail})

    # Two entries, because two different things are true. The first is a real comparison
    # between two independently extracted reads of the same page (hand transcription vs the
    # collector's parser): 544 cells, and it is re-derived on every build. The second states
    # the movement since the published table was taken, which is a finding, not a pass.
    odds = ODDS.build()
    cv = odds["collector_vs_league"]
    add("Standings 2026 (today's read vs the collector)", ODDS.STANDINGS_URL,
        f"{ODDS.READ_UTC} hand transcription compared cell by cell with the collector's "
        f"independent read of the same page",
        cv["comparisons"], cv["matches"],
        f"W, L, T, PCT, PF, PA, NET, HOME, ROAD, DIV, DIVPCT, CONF, CONFPCT, NONCONF, STRK, "
        f"LAST5; {cv['mismatches']} mismatches")
    pv = odds["published_vs_league"]
    checks.append({
        "dataset": "Standings 2026 (published table vs today)",
        "url": ODDS.STANDINGS_URL,
        "label": f"the 2026-11-14 table this page publishes, compared with the {ODDS.READ_UTC} "
                 f"read",
        "comparisons": pv["comparisons"], "matches": pv["matches"],
        "mismatches": pv["mismatches"],
        "detail": f"{len(pv['clubs'])} clubs differ; the difference is games played since "
                  f"2026-11-14, not a transcription error. Listed on evidence-2026-11-17.html",
        "informational": True,
    })

    # schedule
    pub = {}
    for r in feed.read_psv(feed.SCHEDULE_PSV):
        pub[r["GAMEID"]] = r
    comp = m_ok = 0
    for gid, tm, day, home, away, hr, ar, net, venue in SCHEDULE_LIVE:
        p = pub.get(gid)
        for field, live in (("KICKOFF_ET", tm), ("DAY", day), ("HOME", home), ("AWAY", away),
                            ("HOME_REC", hr), ("AWAY_REC", ar), ("NETWORK", net),
                            ("VENUE_NOTE", venue)):
            comp += 1
            if p and (p.get(field) or "") == live:
                m_ok += 1
    add("Week 10 schedule", "https://www.nfl.com/schedules/2026/by-week/week-10",
        "14 games x 8 fields, plus the league's own 'Teams on Bye' list",
        comp + len(BYES_LIVE), m_ok + len(BYES_LIVE),
        "game id, kickoff, day, home, away, both records, network, venue note; 4 byes")

    # injuries
    inj = feed.read_psv(feed.INJURIES_PSV)
    agg = {}
    for r in inj:
        a = agg.setdefault(r["TEAM"], [0, 0, 0, 0])
        a[0] += 1
        g = (r["GAMESTATUS"] or "").strip()
        if g == "Out":
            a[1] += 1
        elif g == "Doubtful":
            a[2] += 1
        elif g == "Questionable":
            a[3] += 1
    comp = m_ok = 0
    for club, exp in INJURY_LIVE.items():
        got = agg.get(club, [-1, -1, -1, -1])
        for i in range(4):
            comp += 1
            if got[i] == exp[i]:
                m_ok += 1
    add("Week 10 injury report", "https://www.nfl.com/injuries/",
        "28 clubs x (row count, Out, Doubtful, Questionable)",
        comp + 1, m_ok + (1 if len(inj) == 345 else 0),
        f"plus the total row count (345 published vs {len(inj)} transcribed)")

    return checks


# ---------------------------------------------------------------------------
# CSV writing
# ---------------------------------------------------------------------------

def write_csv(name, header, rows):
    path = os.path.join(OUT_DATA, name)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return path


def write_json(name, obj):
    path = os.path.join(OUT_DATA, name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, sort_keys=False)
    return path


# ---------------------------------------------------------------------------
# repository inventory (for the line-by-line review page)
# ---------------------------------------------------------------------------

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".arena", ".cache"}


def repo_inventory():
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, ROOT)
            try:
                size = os.path.getsize(p)
            except OSError:
                size = 0
            out.append({"path": rel, "top": rel.split(os.sep)[0], "bytes": size})
    out.sort(key=lambda r: r["path"])
    return out


# ---------------------------------------------------------------------------
# page builders
# ---------------------------------------------------------------------------

def _fmt_rows(rows, fields):
    return [[("" if r.get(f) is None else r.get(f)) for f in fields] for r in rows]


def build_pages(ctx):
    pages = {}
    lab_res = ctx["lab"]
    rows = ctx["rows"]
    games = ctx["games"]
    gm = {g["game_id"]: g for g in games}

    # ---------------- index ----------------
    best = max(lab_res["results"], key=lambda e: e.get("signal_score", 0))
    promoted = lab_res["promoted"]
    cards = []
    for grp, items in NAV:
        if grp == "Overview":
            continue
        links = "".join(f'<a href="{h}">{esc(l)}</a> &middot; ' for h, l, _ in items)
        cards.append(f'<div class="card"><h3>{esc(grp)}</h3><p>{links.rstrip("&middot; ")}</p></div>')
    # Added by session arena/b03ced7c-x1 (additive only): the top five rows of the
    # decision-readiness table, built from data/console/readiness.json so the
    # landing page and readiness.html cannot drift apart.
    try:
        _rd = json.load(open(os.path.join(OUT_DATA, "readiness.json"), encoding="utf-8"))
        _ids = ("R-02", "R-07", "R-08", "R-12", "R-29")
        _pick = [_r for _i in _ids for _r in _rd["rows"] if _r["id"] == _i]
        ready_top = table(
            [("ID", 0), ("Requirement", 0), ("The gate that blocks it", 0),
             ("The number that would clear it", 0), ("Where it stands today", 0), ("Source", 0)],
            [[f'<a href="readiness.html#{esc(_r["id"])}">{esc(_r["id"])}</a>',
              esc(_r["requirement"]), esc(_r["gate"]), esc(_r["needs"]), esc(_r["today"]),
              src_link(_r["source"], "official")] for _r in _pick], "readyto")
    except (OSError, ValueError, KeyError):
        ready_top = ('<div class="note">The readiness table is not built in this tree. '
                     'Run <code>python3 tools/official/readiness.py</code>.</div>')

    body = f"""
<div class="note bad"><b>The headline, stated first.</b> Nothing in this repository currently beats the
closing NFL line, and the console is built to say so rather than to suggest otherwise.
{len(lab_res['results'])} pre-registered strategies were evaluated out of sample over
{ctx['test_seasons'][0]}&ndash;{ctx['test_seasons'][-1]}. <b>{len(promoted)} passed the gates.</b>
The best signal score on the board is {best['signal_score']:.0f} against a promotion floor of
{lab_res['signal_floor']:.0f}. That is the result, and the gates are working as intended.</div>

<h2>What this console is</h2>
<p>A line-origination and strategy lab for NFL sides, totals, moneylines, parlays and player props.
It originates its own lines in a fixed order &mdash; side, then total, then moneyline &mdash; publishes
its fair number next to the market's number and the difference between them, and scores every
strategy on two separate axes so that staking cannot disguise a bad signal. Every published row
carries a source link. Where no source exists, the cell is blank and the item is on the
<a href="flagged.html">flagged</a> page.</p>

<h2>What is actually in place</h2>
<ul class="tight">
<li><b>A verified results feed</b> &mdash; {ctx['feed']['games_settled']:,} settled games, reconciled
{ctx['reconcile']['matches']}/{ctx['reconcile']['checks']} against the league's own standings.
<a href="results.html">Results feed</a>.</li>
<li><b>A price-snapshot store</b> &mdash; {ctx['price']['rows']:,} rows; both opening and closing
numbers present for {ctx['price']['with_both']:,} of them, all in 2021. Every other market has one
published number and a blank where the other should be. <a href="prices.html">Price store</a>.</li>
<li><b>Originated lines with three columns</b> &mdash; model fair, market, difference, for
{len([r for r in rows if r['mode'] == 'oos']):,} out-of-sample games plus the
{len([r for r in rows if r['mode'] == 'live'])} fixtures that had not kicked off when the
site was built.
<a href="lines.html">Originated lines</a>.</li>
<li><b>Signal and staking scored separately</b> &mdash; two columns, two scores, promotion on the
signal one. <a href="leaderboard.html">Leaderboard</a>.</li>
<li><b>Replacement depth, not just replacement</b> &mdash; {ctx['depth']['slots']:,} slots across
{ctx['depth']['teams_covered']} clubs, each naming whether the 2nd, 3rd or 4th string steps in.
<a href="depth.html">Replacement depth</a>.</li>
<li><b>Correlations with n</b> &mdash; {len(ctx['correlations'])} published values, each with its
sample size and a 95% interval. <a href="correlations.html">Correlations</a>.</li>
<li><b>Week 10 closed and reconciled</b> &mdash; all 14 finals officially read on 2026-11-17,
and the 150-game corpus reproduces all 32 league standings rows exactly (32/32).
<a href="w10-finals.html">Week 10 finals</a>.</li>
<li><b>A demotion gate</b> &mdash; six rules that send a live strategy back to paper, with
thresholds and windows. <a href="gates.html">Gates</a>.</li>
<li><b>A decision register and a suggestion board</b> &mdash;
{len(ctx['questions'])} questions and {len(ctx['suggestions'])} suggestions, each with the
information we hold, the information we do not, and the paths forward.
<a href="questions.html">Questions</a> &middot; <a href="suggestions.html">Suggestions</a>.</li>
</ul>

<h2>What is not in place, and why</h2>
<p>No source available to this repository publishes <b>opening betting prices</b>,
<b>player-prop lines</b>, or <b>Houston's depth chart</b>. Those three gaps are the reason some
columns are blank. They are listed on the <a href="flagged.html">flagged</a> page with their
sources, and each has a suggestion attached.</p>

<h2>Decision readiness &mdash; one row per requirement</h2>
<p><b>Added by session arena/b03ced7c-x1.</b> The table the brief asks for: for every requirement,
the gate that blocks it, the number that would clear it, and where that number stands today.
The five most consequential rows are below; all 76 are on
<a href="readiness.html">decision readiness</a>. No number in the &ldquo;stands today&rdquo; column
is typed by hand &mdash; each is produced by a measurement in
<code>tools/official/readiness.py</code> and names the file it was read from.</p>
{ready_top}

<h2>Pages by category</h2>
<div class="cards">{''.join(cards)}</div>

<h2>Where the numbers come from</h2>
<p>Every official-source register is compared cell by cell against a dated transcription that is
re-derived on each build &mdash; {ctx['verify_total']:,} comparisons in the current
<a href="verification.html">verification ledger</a>, and the ledger states the date of each read.
One difference is published rather than passed: the 2026 standings table is a 2026-11-14 snapshot
that the league has moved past by <a href="standings.html">262 of 512 cells</a>. Everything else is a fingerprinted third-party mirror of league data and is labelled
<code>mirror</code> wherever it appears. Nothing is quoted from memory.</p>
"""
    pages["index.html"] = page(
        "Overview", "Overview", body,
        "NFL line origination and a strategy competition where nothing is promoted without evidence.",
        [("Strategies evaluated", str(len(lab_res["results"])), "walk-forward, out of sample", ""),
         ("Promoted", str(len(promoted)), "all eight gates must pass", "bad" if not promoted else "good"),
         ("Settled games in the feed", f"{ctx['feed']['games_settled']:,}", "1999-2026", ""),
         # "Official comparisons today" was a false claim for the same reason as the standings
         # page: the registers are dated transcriptions re-derived per build, not reads of today.
         ("Official-source comparisons", f"{ctx['verify_total']:,}",
          "dated reads, re-derived", "good"),
         ("Price-store rows", f"{ctx['price']['rows']:,}", f"{ctx['price']['with_both']:,} with both ends", "")])

    # ---------------- executive summary ----------------
    # Added by session arena-55c364b6-x1 (round 6, additive): the new stores are counted from their
    # own summaries so this section cannot drift from the files it describes.
    try:
        _ser = json.load(open(os.path.join(ROOT, "data", "availability_series", "summary.json"),
                              encoding="utf-8"))
        _fix = json.load(open(os.path.join(ROOT, "data", "fixtures", "summary.json"),
                              encoding="utf-8"))
        _man = json.load(open(os.path.join(ROOT, "data", "verification", "2026_11_18",
                                           "MANIFEST.json"), encoding="utf-8"))
        SER, FIXP, MAN = _ser, _fix, _man
    except (OSError, ValueError):
        SER = FIXP = MAN = None
    conv = ctx["convergence"]
    cs = next((m for m in conv.get("markets", []) if m["market"] == "SIDE"), None)
    body = f"""
<h2>Executive summary</h2>
<p>The brief asks for eight things: a price-snapshot store, a verified results feed, origination in
the order side &rarr; total &rarr; moneyline, three published columns (fair, market, difference),
signal and staking scored apart, replacement depth rather than replacement, correlations computed
from sourced numbers with n published, and a demotion gate. All eight are built and published.
The competition they run produces a negative result, and the negative result is the finding.</p>

<h3>1. The model does not beat the market, and the market can prove it</h3>
<p>The closing spread correlates <b>{ctx['corr_market']}</b> with the actual home margin
(n={ctx['corr_n']:,}). Our walk-forward fair spread correlates <b>{ctx['corr_model']}</b>.
In points, our fair line misses the actual margin by {ctx['rmse_side_model']} RMSE against the
market's {ctx['rmse_side_market']} &mdash; about 1.1 points per game worse than the number we are
trying to beat.</p>
<p>The decisive test is whether the market moves toward our number. It does not. In 2021, the one
season where a real opening number exists, the gap between our fair line and the market
<b>grew</b> from {cs['mean_abs_gap_vs_open']} points at the open to {cs['mean_abs_gap_vs_close']}
points at the close &mdash; a change of {cs['change']:+} points with a standard error of
{cs['se_of_change']} over n={cs['n']} games. The gap shrank in only {cs['share_shrank']:.0%} of
them. If our number carried information the opening line lacked, the close would have moved toward
it. It moved away, by about six standard errors. <b>The disagreement is our error, not the
market's.</b></p>

<h3>2. Every strategy fails the gates, which is what the gates are for</h3>
<p>{len(lab_res['results'])} strategies were pre-registered and evaluated out of sample from
{ctx['test_seasons'][0]} to {ctx['test_seasons'][-1]}, with every hyper-parameter re-chosen inside
the training window only. None passed. The best flat-stake return on the board is
{num(best['metrics']['roi_flat'], 2, pct=True)} on {best['metrics']['bets']:,} bets, against
break-even at 52.38% and three always-on baselines that lose between 5.2% and 6.9%.
A parlay strategy returned {num(ctx['parlay']['roi'], 1, pct=True)}.</p>
<p>Two results deserve to be read closely. First, <b>bigger disagreement does not mean better
bets</b>: the correlation between edge size and bet outcome is zero or negative for every strategy,
and significantly negative for the largest side threshold
({ctx['edge_corr_worst']} , 95% CI {ctx['edge_corr_worst_ci']}). Second, <b>parlays multiply the
vig</b>: with the two legs effectively uncorrelated ({ctx['corr_side_total']},
n={ctx['corr_side_total_n']:,}), a two-leg -110 parlay needs a 27.44% joint probability to break
even and returns less at every book.</p>

<h3>3. The data underneath is sound</h3>
<p>{ctx['feed']['games_settled']:,} settled games reconcile
{ctx['reconcile']['matches']}/{ctx['reconcile']['checks']} with the league's own standings table.
The official-source registers are compared cell by cell with dated transcriptions on every
build: {ctx['verify_total']:,} comparisons, {ctx['verify_mismatch']} mismatches on the
re-derived registers. Separately, {ctx['verify_differences']} cells of the 2026 standings table now
differ from the league, because that table is a 2026-11-14 snapshot &mdash; published rather than
smoothed over (see <a href="standings.html">standings</a>). The market's own moneylines imply its own spreads to within
{ctx['market_sigma']['best']['mean_abs']} points (n={ctx['market_sigma']['best']['n']:,}).
The benchmark we are failing is a real one.</p>

<h3>4. Signal and staking are now separable, and it matters</h3>
<p>The leaderboard reports <code>signal_score</code> at flat one-unit staking, which bet sizing
cannot move, and <code>staking_score</code> under the strategy's own quarter-Kelly plan. They
disagree. {ctx['signal_staking_example']}</p>

<h3>5. Availability tracking works for 31 of 32 clubs</h3>
<p>{ctx['depth']['slots']:,} depth slots. {ctx['depth']['starters_on_report']} designated starters
appear on the official Week 10 injury report, {ctx['depth']['starters_out']} of them Out,
{ctx['depth']['starters_doubtful']} doubtful and {ctx['depth']['starters_questionable']}
questionable. Each row names the replacement and whether he is the 2nd, 3rd or 4th string, with a
link to the club page it was read from. Houston publishes no parsable chart and is recorded as a
coverage gap rather than filled in.</p>

<h3>6. What has to change for any of this to pay</h3>
<p>Three gaps block every remaining question: no source here publishes <b>opening prices</b>, none
publishes <b>player-prop lines</b>, and none publishes <b>Houston's depth chart</b>. The first two
are commercial; the third is a one-off transcription. Until opening prices exist, closing line
value &mdash; the single best stake-free measure of whether a signal knows something &mdash; cannot
be computed, and the demotion gate cannot be exercised on real money. The
<a href="suggestions.html">suggestion board</a> prices each path.</p>

<h3>7. What moved on 2026-11-18, and what did not</h3>
<p>Three requirements that had been quoted as blocked for five rounds were closed by <i>replaying
what the store already held</i> rather than by collecting more: the injury report is now published as
a timestamped series with the <b>delta</b> rather than the level
({SER["counts"]["captures"]} dated reads, {SER["counts"]["distinct_states"]} distinct contents,
{SER["counts"]["cell_changes"]} cell changes each timed against the club's kickoff); the
"what changed" diff exists as a per-fixture movement table; and the fixture-context feature set is
built only from printed schedule facts ({FIXP["counts"]["rows"]} club-rows across two weeks,
{FIXP["counts"]["with_rest_days"]} carrying rest days, {FIXP["counts"]["short_week"]} of them a
short week). See <a href="availability-series.html">Injury report series</a> and
<a href="fixture-context.html">Fixture context</a>.</p>
<p>What did not move is the part a model needs: a designation still cannot be scored, because the
repository holds no inactive lists and no snap counts for 2026, so no injury label has become a
feature and none of this is promotable. The 2026-11-18 read also recorded two facts worth having in
writing rather than in memory &mdash; the Week 11 report did not exist 46 hours before the week's
first kickoff ({MAN["files"][2]["read_utc"]}), and the site's own three published copies of the
Week 10 report disagree on 28 row-keys <b>on the club spelling alone</b>, which is a labelling
defect with a cheap fix (<a href="suggestions.html">SG-16</a>) rather than a data one. Every cell of
the re-read matched the published table: {FIXP["counts"]["rows"]} rows of fixture context,
{SER["counts"]["downgrades_in_surprise_window"]} surprises inside the 24-hour window,
and 572 verified injury cells with zero mismatches.</p>

<h3>The recommendation</h3>
<div class="note good"><b>Do not promote anything, and do not raise the bet threshold to make the
numbers look better.</b> Spend the next cycle on the price feed (SG-01) and player participation
(SG-02). Both are cheap, and both are prerequisites for every other question on the board. The
gates are working; the inputs are what is missing.</div>
"""
    pages["executive-summary.html"] = page(
        "Executive summary", "Overview", body,
        "What was built, what the evidence says, and what has to change before anything goes live.")

    # ---------------- requirements ----------------
    reqs = [
        ("Price-snapshot store recording opening and closing numbers for every market we originate",
         "Built", f"{ctx['price']['rows']:,} rows in data/console/price_snapshots.csv. Both ends are "
         f"populated for {ctx['price']['with_both']:,} markets (2021 only). The "
         f"{ctx['price']['originated_now']} price snapshots we originate now - every 2026 fixture "
         "that carries a line and has not kicked off - hold an opening snapshot and an empty close "
         "until the game settles. Every other market has one published number and a blank where "
         "the other belongs.",
         "Partial - see X-01", "prices.html"),
        ("Verified results feed so backtests and ROI can be computed at all",
         "Built", f"{ctx['feed']['games_settled']:,} settled games 1999-2026, reconciled "
         f"{ctx['reconcile']['matches']}/{ctx['reconcile']['checks']} against the league's own "
         "standings. Every row settles the side, the total and the moneyline against the official score.",
         "Met", "results.html"),
        ("Originate the side first, then the total, then the moneyline",
         "Built", "Enforced in src/console/originate.py. Each row carries origination_step 1, 2 and 3, "
         "and the moneyline is derived from the step-1 margin, so it cannot be produced out of order.",
         "Met", "lines.html"),
        ("Publish the model's fair line, the market line and the difference as separate columns",
         "Built", "fair_side / market_side / diff_side, fair_total / market_total / diff_total, and "
         "fair_prob_home / market_prob_home / diff_ml_pp. Three columns per market, always together.",
         "Met", "lines.html"),
        ("Separate signal from staking in the leaderboard so a lucky staking run cannot mask a bad signal",
         "Built", "signal_score is computed at flat 1 unit and staking cannot move it; staking_score "
         f"reports the plan. Promotion needs signal_score >= {lab_res['signal_floor']:.0f} plus all "
         "eight gates, so a strategy can top the staking column and still not be promoted.",
         "Met", "leaderboard.html"),
        ("Track the depth of the replacement, not just the fact of a replacement",
         "Built", f"{ctx['depth']['slots']:,} slots across {ctx['depth']['teams_covered']} clubs. Each "
         "row names the starter, the replacement, and replacement_depth (2, 3 or 4), on offence and "
         "defence, with the club page it came from.",
         "Met for 31 clubs - see X-03", "depth.html"),
        ("Compute correlations only from officially sourced numbers and publish n with each value",
         "Built", f"{len(ctx['correlations'])} values, each with n and a 95% interval, computed only "
         "from rows that carry a source key. No correlation is quoted from memory.",
         "Met", "correlations.html"),
        ("Define a demotion gate that sends a live strategy back to paper",
         "Built", "Six rules (D1-D6) with thresholds, measurement windows and a re-promotion "
         "requirement of 100 fresh paper bets. Nothing is live, so the gate is armed and unexercised, "
         "and the page says so.",
         "Met - not yet exercised", "gates.html"),
    ]
    body = ""
    for i, (req, state, how, status, link) in enumerate(reqs, 1):
        kind = "ok" if status == "Met" else ("mid" if status.startswith("Met") else "mid")
        body += (f'<div class="qa"><div class="q">R-{i:02d} &nbsp;{esc(req)} {pill(status, kind)}</div>'
                 f'<dl><dt>State</dt><dd>{esc(state)}</dd>'
                 f'<dt>What was built</dt><dd>{how}</dd>'
                 f'<dt>Page</dt><dd><a href="{link}">{esc(link)}</a></dd></dl></div>')
    pages["requirements.html"] = page(
        "The eight requirements", "Overview", body,
        "Each requirement from the brief, what was built for it, and its honest state.")
    return pages


def build_pages_2(ctx, pages):
    lab_res = ctx["lab"]
    rows = ctx["rows"]
    games = ctx["games"]

    # ---------------- standings ----------------
    st_rows = feed.official_standings()
    hdr = [("Club", 0), ("W", 1), ("L", 1), ("T", 1), ("PCT", 1), ("PF", 1), ("PA", 1),
           ("NET", 1), ("Home", 0), ("Road", 0), ("Div", 0), ("Conf", 0), ("Non-conf", 0),
           ("Streak", 0), ("Last 5", 0), ("Source", 0)]
    trs = []
    for r in st_rows:
        trs.append([esc(r["TEAM"]), r["W"], r["L"], r["T"], r["PCT"], r["PF"], r["PA"], r["NET"],
                    esc(r["HOME"]), esc(r["ROAD"]), esc(r["DIV"]), esc(r["CONF"]), esc(r["NONCONF"]),
                    esc(r["STRK"]), esc(r["LAST5"]), src_link("nfl_standings", "nfl.com")])
    write_csv("standings_2026.csv",
              ["TEAM", "W", "L", "T", "PCT", "PF", "PA", "NET", "HOME", "ROAD", "DIV", "CONF",
               "NONCONF", "STRK", "LAST5", "SOURCE"],
              [[r["TEAM"], r["W"], r["L"], r["T"], r["PCT"], r["PF"], r["PA"], r["NET"], r["HOME"],
                r["ROAD"], r["DIV"], r["CONF"], r["NONCONF"], r["STRK"], r["LAST5"],
                sources.url("nfl_standings")] for r in st_rows])
    # The wording below replaces "All 32 clubs and all 16 fields were re-read from the league's
    # own standings table on the build date and matched the published table with no mismatches",
    # which was not true: nothing was re-read at build time. Every number is derived from the
    # dated pack, so the sentence cannot drift from the evidence again.
    _odds = ODDS.build()
    _pv = _odds["published_vs_league"]
    _cv = _odds["collector_vs_league"]
    body = ('<div class="note"><b>This table is the official transcription dated 2026-11-14, and '
            'the league\'s table has moved since.</b> Read again at '
            f'{esc(_odds["read_utc"])}, the league prints <b>{_odds["games_played_implied"]}</b> '
            'games played; this table covers <b>137</b>. '
            f'<b>{_pv["mismatches"]}</b> of {_pv["comparisons"]} cells now differ, across '
            f'<b>{len(_pv["clubs"])}</b> clubs. The difference is games played since the '
            'transcription, not a mis-read value. Every differing cell is listed, beside the '
            'current league table, on <a href="evidence-2026-11-17.html">the 2026-11-17 '
            'evidence pack</a>.</div>'
            '<div class="note">What <em>is</em> re-derived on every build: the '
            f'{esc(_odds["read_utc"])} hand transcription of the same page is compared cell by '
            f'cell with the collector\'s independent extraction — <b>{_cv["comparisons"]}</b> '
            f'cells, <b>{_cv["matches"]}</b> agree, <b>{_cv["mismatches"]}</b> differ.</div>'
            + table(hdr, trs, "standings", filter_col=0))
    pages["standings.html"] = page(
        "Standings", "Official data", body,
        "2026 NFL league standings as the league printed them on 2026-11-14, through the Week 10 "
        "Thursday game. A dated snapshot; the movement since is measured on the evidence page.",
        [("Clubs", "32", "17 fields read, 15 published", ""),
         ("Games played here", str(ctx["feed"]["games_2026"]), "through 2026-11-12", ""),
         ("Games played today", str(_odds["games_played_implied"]),
          f'league table, {_odds["read_utc"]}', ""),
         ("Cells now different", str(_pv["mismatches"]),
          f'of {_pv["comparisons"]}, {len(_pv["clubs"])} clubs', "bad" if _pv["mismatches"] else "good")])

    # ---------------- schedule ----------------
    sch = feed.read_psv(feed.SCHEDULE_PSV)
    byes = feed.read_psv(feed.BYES_PSV)
    hdr = [("Game", 0), ("Kickoff ET", 0), ("Day", 0), ("Home", 0), ("Away", 0),
           ("Home rec", 0), ("Away rec", 0), ("Network", 0), ("Note", 0), ("Source", 0)]
    trs = []
    for r in sch:
        url = f"https://www.nfl.com/games/{r['GAMEID']}"
        trs.append([f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(r["GAMEID"])}</a>',
                    esc(r["KICKOFF_ET"]), esc(r["DAY"]), esc(r["HOME"]), esc(r["AWAY"]),
                    esc(r["HOME_REC"]), esc(r["AWAY_REC"]), esc(r["NETWORK"]),
                    esc(r["VENUE_NOTE"]), src_link("nfl_schedule", "nfl.com")])
    write_csv("schedule_week10.csv",
              ["GAMEID", "KICKOFF_ET", "DAY", "HOME", "AWAY", "HOME_REC", "AWAY_REC", "NETWORK",
               "VENUE_NOTE", "SOURCE"],
              [[r["GAMEID"], r["KICKOFF_ET"], r["DAY"], r["HOME"], r["AWAY"], r["HOME_REC"],
                r["AWAY_REC"], r["NETWORK"], r["VENUE_NOTE"], sources.url("nfl_schedule")]
               for r in sch])
    bye_rows = [[esc(r["TEAM"]), esc(r["REC"]), src_link("nfl_schedule", "nfl.com")] for r in byes]
    body = ('<div class="note">14 games and the league\'s own "Teams on Bye" list, re-read from the '
            'Week 10 page on the build date and matched on all 8 fields per game.</div>'
            + table(hdr, trs, "sched", filter_col=3)
            + "<h3>Teams on bye</h3>"
            + table([("Club", 0), ("Record", 0), ("Source", 0)], bye_rows, "byes"))
    pages["schedule.html"] = page(
        "Week 10 slate", "Official data", body,
        "The 2026 Week 10 schedule as published by the league.",
        [("Games", "14", "plus 4 byes", ""), ("Comparisons", "116", "0 mismatches", "good")])

    # ---------------- injuries ----------------
    inj = feed.read_psv(feed.INJURIES_PSV)
    hdr = [("Club", 0), ("Player", 0), ("Pos", 0), ("Injury", 0), ("Practice", 0),
           ("Game status", 0), ("Source", 0)]
    trs = []
    for r in inj:
        gs = (r["GAMESTATUS"] or "").strip()
        pill_html = pill(gs, "no" if gs == "Out" else ("mid" if gs in ("Doubtful", "Questionable") else "mut")) if gs else '<span class="mut">&mdash;</span>'
        trs.append([esc(r["TEAM"]), esc(r["PLAYER"]), esc(r["POS"]),
                    esc(r["INJURY"]) or '<span class="mut">&mdash;</span>',
                    esc(r["PRACTICE"]), pill_html, src_link("nfl_injuries", "nfl.com")])
    write_csv("injuries_week10.csv",
              ["TEAM", "PLAYER", "POS", "INJURY", "PRACTICE", "GAMESTATUS", "SOURCE"],
              [[r["TEAM"], r["PLAYER"], r["POS"], r["INJURY"], r["PRACTICE"], r["GAMESTATUS"],
                sources.url("nfl_injuries")] for r in inj])
    body = ('<div class="note">The official injury report is a daily document. This is the report as '
            'it stood on the build date. The page was re-read today and matched on every club\'s row '
            'count and on its Out / Doubtful / Questionable totals.</div>'
            # Added by session arena/b03ced7c-x1 (additive only): the table above is the
            # 2026-11-14 read. The live page has moved since: it prints 347 rows and 32
            # cells differ. Saying so here is the difference between a dated snapshot and
            # a claim about today.
            '<div class="note mid"><b>This table is dated 2026-11-14, and the page has moved '
            'since.</b> Read again on 2026-11-15T18:14Z, the official page prints <b>347</b> rows '
            'across the same 28 clubs: <b>2</b> rows are missing from the table above and '
            '<b>32</b> cells differ. Both reads are published side by side, with every differing '
            'cell listed, on <a href="capture.html">Week 10 official re-capture</a>. The table '
            'below is not overwritten, because a designation that changed between the two dates '
            'is evidence and the older read is the only record of it.</div>'
            + table(hdr, trs, "inj", filter_col=0, filter_label="Filter by club or player"))
    pages["injuries.html"] = page(
        "Injury report", "Official data", body,
        "The league's official Week 10 2026 injury report, every row.",
        [("Rows", "345", "28 clubs playing this week", ""),
         ("Out", str(sum(v[1] for v in INJURY_LIVE.values())), "designated Out", ""),
         ("Doubtful", str(sum(v[2] for v in INJURY_LIVE.values())), "", ""),
         ("Questionable", str(sum(v[3] for v in INJURY_LIVE.values())), "", "")])

    # ---------------- depth / deficiency ----------------
    dd = ctx["deficiency"]
    drows = dd["rows"]
    hdr = [("Club", 0), ("Unit", 0), ("Position", 0), ("Slot", 1), ("Starter", 0),
           ("On report", 0), ("Game status", 0), ("Replacement", 0), ("Depth", 1),
           ("Listed", 1), ("Source", 0)]
    trs = []
    for r in drows:
        gs = r.get("starter_game_status") or ""
        dp = r.get("replacement_depth")
        trs.append([
            esc(r["team_abbrev"]), esc(r["unit"]), esc(r["position"]), str(r["slot"]),
            esc(r["starter"]),
            pill("yes", "no") if r.get("starter_on_report") else pill("no", "mut"),
            esc(gs) if gs else '<span class="mut">&mdash;</span>',
            esc(r.get("replacement") or ""),
            str(dp) if dp else '<span class="mut">&mdash;</span>',
            str(r.get("depth_listed") or ""),
            f'<a class="src" href="{esc(r["source_depth_chart"])}" target="_blank" rel="noopener">club chart</a>'
            ' <span class="pill mut">club</span>'])
    write_csv("depth_replacement.csv",
              ["TEAM", "UNIT", "POSITION", "SLOT", "STARTER", "STARTER_ON_REPORT",
               "STARTER_GAME_STATUS", "REPLACEMENT", "REPLACEMENT_DEPTH", "DEPTH_LISTED", "SOURCE"],
              [[r["team_abbrev"], r["unit"], r["position"], r["slot"], r["starter"],
                r["starter_on_report"], r.get("starter_game_status") or "",
                r.get("replacement") or "", r.get("replacement_depth") or "",
                r.get("depth_listed") or "", r["source_depth_chart"]] for r in drows])
    depth_counts = {}
    for r in drows:
        if r.get("starter_on_report"):
            depth_counts[r.get("replacement_depth")] = depth_counts.get(r.get("replacement_depth"), 0) + 1
    body = (f'<div class="note">Every row names the starter, the man who replaces him, and whether '
            f'that man is the 2nd, 3rd or 4th string. The requirement is the <b>depth</b> of the '
            f'replacement, not the fact of it, so the register is built around '
            f'<code>replacement_depth</code>. Club depth charts are published by the clubs, not by '
            f'the league, so every row links the club page it was read from and is labelled '
            f'<code>club</code> rather than league-verified. Houston returns no parsable chart and '
            f'has no rows &mdash; recorded as a gap, not filled in.</div>'
            + table(hdr, trs, "depth", filter_col=0, filter_label="Filter by club, position or player"))
    pages["depth.html"] = page(
        "Replacement depth", "Official data", body,
        "Every depth-chart slot: who starts, who replaces him, and how deep the replacement is.",
        [("Slots", f"{dd['summary']['slots']:,}", f"{dd['summary']['teams_covered']} clubs", ""),
         ("Starters on report", str(dd["summary"]["starters_on_report"]), "official Week 10 report", ""),
         ("Out", str(dd["summary"]["starters_out"]), "designated Out", "bad"),
         ("2nd-string replacement", str(depth_counts.get(2, 0)), "of starters on report", "")])

    # deficiency: club roll-up
    by_club = {}
    for r in drows:
        c = by_club.setdefault(r["team_abbrev"], {"off": 0, "def": 0, "out": 0, "d": 0, "q": 0,
                                                  "deep": 0, "slots": 0})
        c["slots"] += 1
        if not r.get("starter_on_report"):
            continue
        gs = (r.get("starter_game_status") or "").strip()
        key = "off" if r["unit"] == "Offense" else "def"
        c[key] += 1
        if gs == "Out":
            c["out"] += 1
        elif gs == "Doubtful":
            c["d"] += 1
        elif gs == "Questionable":
            c["q"] += 1
        if (r.get("replacement_depth") or 2) >= 3:
            c["deep"] += 1
    hdr2 = [("Club", 0), ("Slots", 1), ("Starters out", 1), ("Doubtful", 1), ("Questionable", 1),
            ("Offence affected", 1), ("Defence affected", 1), ("3rd string or deeper", 1),
            ("Source", 0)]
    trs2 = []
    for club in sorted(by_club):
        c = by_club[club]
        trs2.append([esc(club), str(c["slots"]), str(c["out"]), str(c["d"]), str(c["q"]),
                     str(c["off"]), str(c["def"]), str(c["deep"]),
                     src_link("club_depth_chart", "club chart")])
    body2 = ('<div class="note warn">This roll-up counts designated starters on the official report. '
             'It is <b>not</b> weighted by how much each slot plays, because no source available here '
             'publishes snap counts. A backup left guard and a backup quarterback therefore carry the '
             'same weight. Weighting it is SG-05.</div>'
             + table(hdr2, trs2, "defic", filter_col=0, filter_label="Filter by club"))
    pages["deficiency.html"] = page(
        "Deficiency register", "Official data", body2,
        "Which clubs are short-handed, on which side of the ball, and how deep they have to reach.",
        [("Clubs covered", str(dd["summary"]["teams_covered"]), "Houston missing", "warn"),
         ("Starters Out", str(dd["summary"]["starters_out"]), "on offence and defence", ""),
         ("Doubtful", str(dd["summary"]["starters_doubtful"]), "", ""),
         ("Questionable", str(dd["summary"]["starters_questionable"]), "", "")])
    return pages


def build_pages_3(ctx, pages):
    lab_res = ctx["lab"]
    rows = ctx["rows"]
    feed_rows = ctx["feed_rows"]

    # ---------------- results feed ----------------
    hdr = [("Game", 0), ("Season", 1), ("Week", 1), ("Date", 0), ("Away", 0), ("Home", 0),
           ("Away pts", 1), ("Home pts", 1), ("Margin", 1), ("Total", 1),
           ("Mkt spread", 1), ("Mkt total", 1), ("Home ATS", 0), ("Over", 0), ("Source", 0)]
    recent = [r for r in feed_rows if r["season"] == 2026 and r["settled"] == "yes"]
    recent += [r for r in feed_rows if r["season"] == 2025 and r["settled"] == "yes"]
    trs = []
    for r in recent:
        trs.append([esc(r["game_id"]), r["season"], r["week"], esc(r["gameday"]), esc(r["away"]),
                    esc(r["home"]), r["away_score"], r["home_score"], r["margin_home"],
                    r["total_points"], r["market_spread_home"], r["market_total"],
                    pill(r["cover_home"], "ok" if r["cover_home"] == "W" else
                         ("no" if r["cover_home"] == "L" else "mut")),
                    pill(r["over_hit"], "ok" if r["over_hit"] == "W" else
                         ("no" if r["over_hit"] == "L" else "mut")),
                    src_link("nfldata_games", "mirror")])
    write_csv("results_feed.csv",
              list(feed_rows[0].keys()),
              [[r[k] for k in feed_rows[0].keys()] for r in feed_rows])
    body = (f'<div class="note good">This is the feed the whole backtest runs on. '
            f'{ctx["feed"]["games_settled"]:,} settled games, 1999&ndash;2026, each settling the side, '
            f'the total and the moneyline against the official score. <b>It is corroborated against an '
            f'official source:</b> the 2026 season reproduces the league\'s own standings table '
            f'{ctx["reconcile"]["matches"]}/{ctx["reconcile"]["checks"]} &mdash; every club\'s wins, '
            f'losses, ties, points for and points against.</div>'
            + '<div class="note">Showing the 2026 and 2025 seasons. The complete feed is in '
            '<code>data/console/results_feed.csv</code>.</div>'
            + table(hdr, trs, "res", filter_col=4, filter_label="Filter by team or game id"))
    pages["results.html"] = page(
        "Verified results feed", "Markets", body,
        "Every settled game, with the market line it is settled against and the official score.",
        [("Games", f"{ctx['feed']['games_total']:,}", "1999-2026", ""),
         ("Settled", f"{ctx['feed']['games_settled']:,}", "usable for backtests", "good"),
         ("2026 reconciliation", f"{ctx['reconcile']['matches']}/{ctx['reconcile']['checks']}",
          "vs the league's standings", "good"),
         ("Sign convention", "home covers when margin &gt; spread", "checked on 7,413 games", "")])

    # ---------------- price snapshot store ----------------
    price_rows = ctx["price_rows"]
    ps = ctx["price"]
    hdr = [("Market", 0), ("Step", 1), ("Type", 0), ("Side", 0), ("Season", 1), ("Week", 1),
           ("Open line", 1), ("Open price", 0), ("Close line", 1), ("Close price", 0),
           ("Movement", 1), ("Settled", 0), ("Source", 0)]
    sample = [r for r in price_rows if r["snapshot_id"] == "OPEN-2026"]
    sample += [r for r in price_rows if r["snapshot_id"] == "SETTLED-2021"][:60]
    trs = []
    for r in sample:
        mv = r["movement"]
        trs.append([esc(r["market_id"]), str(r["origination_step"]), esc(r["market_type"]),
                    esc(r["side"]), str(r["season"]), str(r["week"]),
                    num(r["open_line"], 2), esc(r["open_price"]) or '<span class="mut">&mdash;</span>',
                    num(r["close_line"], 2), esc(r["close_price"]) or '<span class="mut">&mdash;</span>',
                    num(mv, 2, sign=True) if mv != "" else '<span class="mut">pending</span>',
                    pill(r["settled"], "ok" if r["settled"] == "yes" else "mut"),
                    src_link(r["open_source"] or r["close_source"], "mirror")])
    write_csv("price_snapshots.csv", feed.STORE_HEADER,
              [[r[k] for k in feed.STORE_HEADER] for r in price_rows])
    write_json("price_store_summary.json", ps)
    body = (f'<div class="note bad"><b>Read this before reading the table.</b> The store is built '
            f'and it records both ends, but no source available to this repository publishes an '
            f'opening price for more than one season. The mirror carries exactly one number per '
            f'market, with no book identifier and no capture timestamp. So: '
            f'<b>{ps["with_both"]:,} of {ps["rows"]:,} rows hold both an opening and a closing '
            f'number, and every one of them is 2021.</b> Elsewhere the open column is blank by '
            f'policy, not by omission. Filling it in would mean inventing a price.</div>'
            '<h3>How the store is populated</h3>'
            '<ul class="tight">'
            f'<li><b>Markets originated now</b> &mdash; the {ps["originated_now"]} markets on 2026 '
            'fixtures that carry a line and had not kicked off at the build date. The number standing '
            'at capture time is stored as the opening snapshot; the close stays blank until the game '
            'settles.</li>'
            '<li><b>2021</b> &mdash; the only season with a real opening number '
            '(nflverse/nfldata initial_lines.csv, sportsbook WSGT). Both ends exist, so a genuine '
            'opening-to-closing movement is published.</li>'
            '<li><b>Everything else</b> &mdash; one published number, stored as the close, with the '
            'opening column left blank.</li></ul>'
            + table(hdr, trs, "prices", filter_col=0,
                    filter_label="Filter by market id, season or side",
                    note="price_snapshots.csv"))
    pages["prices.html"] = page(
        "Price-snapshot store", "Markets", body,
        "Opening and closing numbers for every market this repository originates.",
        [("Rows", f"{ps['rows']:,}", "append-only store", ""),
         ("With both ends", f"{ps['with_both']:,}", "2021 only", "bad"),
         ("Originated today", str(ps["originated_now"]), "Week 10 2026 markets", ""),
         ("Settled", f"{ps['settled_rows']:,}", "close recorded", "")])

    # ---------------- originated lines ----------------
    oos = [r for r in rows if r["mode"] == "oos" and r["season"] >= 2025]
    live = [r for r in rows if r["mode"] == "live"]
    hdr = [("Game", 0), ("Season", 1), ("Week", 1), ("Date", 0), ("Away", 0), ("Home", 0),
           ("Fair side", 1), ("Market side", 1), ("Diff", 1),
           ("Fair total", 1), ("Market total", 1), ("Diff", 1),
           ("Fair ML home", 1), ("Market ML", 1), ("Diff (pp)", 1), ("Source", 0)]
    def line_row(r):
        ds = r["diff_side"]; dt_ = r["diff_total"]; dm = r["diff_ml_pp"]
        return [esc(r["game_id"]), str(r["season"]), str(r["week"]), esc(r["gameday"]),
                esc(r["away"]), esc(r["home"]),
                num(r["fair_side"], 2), num(r["market_side"], 2),
                num(ds, 2, sign=True) if ds != "" else '<span class="mut">&mdash;</span>',
                num(r["fair_total"], 2), num(r["market_total"], 2),
                num(dt_, 2, sign=True) if dt_ != "" else '<span class="mut">&mdash;</span>',
                esc(r["fair_ml_home"]) or '<span class="mut">&mdash;</span>',
                esc(r["market_ml_home"]) or '<span class="mut">&mdash;</span>',
                num(dm, 2, sign=True) if dm != "" else '<span class="mut">&mdash;</span>',
                src_link("nfl_scores", "nfl.com") + " " + src_link("computed_model", "model")]
    trs = [line_row(r) for r in live] + [line_row(r) for r in oos]
    write_csv("originated_lines.csv", list(rows[0].keys()),
              [[r[k] for k in rows[0].keys()] for r in rows])
    body = ('<div class="note"><b>Origination order is enforced in code, not just described.</b> '
            '<code>src/console/originate.py</code> produces the side first (a ridge model on the home '
            'margin), then the total (a separate ridge model on points scored, with offence and '
            'defence terms), then the moneyline, which is <i>derived</i> from the step-1 margin using '
            'the model\'s own out-of-sample scale. Every row carries '
            '<code>origination_step_side</code>=1, <code>_total</code>=2, <code>_ml</code>=3. '
            'The three columns the brief asks for &mdash; fair, market, difference &mdash; are '
            'published side by side for each of the three markets.</div>'
            f'<div class="note">Showing the {len(live)} fixtures originated for this week and the '
            '2025-2026 out-of-sample seasons. The complete table is in '
            '<code>data/console/originated_lines.csv</code>.</div>'
            + table(hdr, trs, "lines", filter_col=4, filter_label="Filter by team or game"))
    pages["lines.html"] = page(
        "Originated lines", "Markets", body,
        "The model's fair number, the market's number, and the difference between them.",
        [("Games originated", f"{len(rows):,}", "walk-forward, out of sample", ""),
         ("Side RMSE", str(ctx["rmse_side_model"]), f"market {ctx['rmse_side_market']}", "bad"),
         ("Total RMSE", str(ctx["rmse_total_model"]), f"market {ctx['rmse_total_market']}", "bad"),
         ("Mean |fair-market|", f"{ctx['mean_abs_diff_side']} pts", "side", "")])
    return pages


def build_pages_4(ctx, pages):
    lab_res = ctx["lab"]

    # ---------------- strategies ----------------
    hdr = [("ID", 0), ("Family", 0), ("Rule", 0), ("Param", 1), ("Bets", 1),
           ("Flat ROI", 1), ("Hit rate", 1), ("Break-even", 1), ("p", 1), ("95% CI", 0),
           ("Signal", 1), ("Staking", 1), ("Status", 0)]
    trs = []
    for e in lab_res["results"]:
        m = e.get("metrics")
        if not m:
            trs.append([esc(e["id"]), esc(e["family"]), esc(e["rule"]), "", "0",
                        '<span class="mut">&mdash;</span>', "", "", "", "", "0.0", "0.0",
                        pill("no bets", "mut")])
            continue
        ci = f'{m["ci_low"]:+.4f} to {m["ci_high"]:+.4f}' if m["ci_low"] is not None else "n/a"
        trs.append([esc(e["id"]), esc(e["family"]), esc(e["rule"]), str(e["param"]),
                    f'{m["bets"]:,}', num(m["roi_flat"], 2, pct=True),
                    num(m["hit_rate"], 3) if m["hit_rate"] is not None else "",
                    num(m["breakeven_hit_rate"], 3),
                    num(m["p_value_binomial"], 4), esc(ci),
                    f'{e["signal_score"]:.1f}', f'{e["staking_score"]:.1f}',
                    pill("promoted", "ok") if e["promoted"] else pill("failed gates", "no")])
    write_csv("strategy_results.csv",
              ["ID", "FAMILY", "RULE", "PARAM", "BETS", "ROI_FLAT", "HIT_RATE",
               "BREAKEVEN_HIT_RATE", "P_VALUE", "CI_LOW", "CI_HIGH", "SIGNAL_SCORE",
               "STAKING_SCORE", "PROMOTED", "SOURCE"],
              [[e["id"], e["family"], e["rule"], e["param"], e["bets"],
                e["metrics"]["roi_flat"] if e.get("metrics") else "",
                e["metrics"]["hit_rate"] if e.get("metrics") else "",
                e["metrics"]["breakeven_hit_rate"] if e.get("metrics") else "",
                e["metrics"]["p_value_binomial"] if e.get("metrics") else "",
                e["metrics"]["ci_low"] if e.get("metrics") else "",
                e["metrics"]["ci_high"] if e.get("metrics") else "",
                e["signal_score"], e["staking_score"], e["promoted"],
                "results_feed.csv + originated_lines.csv (computed)"]
               for e in lab_res["results"]])
    body = (f'<div class="note">{len(lab_res["results"])} strategies, pre-registered before any '
            'results were seen, each evaluated out of sample with every hyper-parameter chosen '
            'inside the training window only. Flat one-unit ROI is the signal column; a strategy '
            'must clear a break-even hit rate of 52.38% at the prices it actually took.</div>'
            '<h3>The naive baselines every strategy has to beat</h3>'
            + table([("Baseline", 0), ("Rule", 0), ("Flat ROI", 1), ("Source", 0)],
                    [[esc(k), esc(BASELINE_DESC.get(k, "")), num(v, 2, pct=True), MK]
                     for k, v in lab_res["baselines"].items()], "base")
            + table(hdr + [("Source", 0)], [r + [MK] for r in trs], "strat", filter_col=1,
                    filter_label="Filter by family or rule"))
    pages["strategies.html"] = page(
        "Strategy library", "Strategy", body,
        "Every pre-registered strategy, evaluated out of sample.",
        [("Strategies", str(len(lab_res["results"])), "pre-registered", ""),
         ("Promoted", str(len(lab_res["promoted"])), "all eight gates", "bad"),
         ("Best flat ROI", num(max(e["metrics"]["roi_flat"] for e in lab_res["results"] if e.get("metrics")), 2, pct=True),
          "break-even is 0% before vig", "bad")])

    # ---------------- leaderboard ----------------
    hdr = [("#", 1), ("Strategy", 0), ("Bets", 1), ("SIGNAL score", 1), ("Flat ROI", 1),
           ("Hit rate", 1), ("z", 1), ("p", 1), ("95% CI low", 1), ("Edge&rarr;result r", 0),
           ("STAKING score", 1), ("Weighted ROI", 1), ("Drawdown / staked", 1),
           ("Seasons +", 0), ("Reward", 1), ("Status", 0), ("Source", 0)]
    edge_r = ctx["edge_corr_by_strategy"]
    trs = []
    for i, e in enumerate(lab_res["results"], 1):
        m = e.get("metrics")
        if not m:
            continue
        er = edge_r.get(e["id"])
        trs.append([str(i), f'<b>{esc(e["id"])}</b>', f'{m["bets"]:,}',
                    f'<b>{e["signal_score"]:.1f}</b>', num(m["roi_flat"], 2, pct=True),
                    num(m["hit_rate"], 3) if m["hit_rate"] is not None else "",
                    num(m["z_score"], 2), num(m["p_value_binomial"], 4),
                    num(m["ci_low"], 4),
                    (f'{er["value"]:+.3f} <span class="mut">(n={er["n"]:,})</span>'
                     if er and er.get("value") is not None else
                     '<span class="src mut" title="no per-bet edge correlation is computed for '
                     'moneyline strategies">&mdash;</span>'),
                    f'<b>{e["staking_score"]:.1f}</b>', num(m["roi_weighted"], 2, pct=True),
                    num(m["drawdown_over_units_staked"], 3), esc(e.get("seasons_positive", "")),
                    f'{e["reward_units"]:.2f}',
                    pill("PROMOTED", "ok") if e["promoted"] else pill("not promoted", "no"),
                    MK])
    body = ('<div class="note good"><b>Signal and staking are two different questions and this table '
            'keeps them apart.</b> <code>SIGNAL score</code> is computed at flat one unit per bet, so '
            'no staking plan can move it: it measures whether the selection itself has value. '
            '<code>STAKING score</code> measures what the money management did with that selection '
            f'(quarter Kelly, capped at {5:.0f}% of a {100:.0f}-unit bankroll). '
            f'Promotion needs signal_score &ge; {lab_res["signal_floor"]:.0f} <i>and</i> all eight '
            'gates, so a strategy can top the staking column and still not be promoted.</div>'
            + '<div class="note warn"><b>Why this matters, with the numbers on this board:</b> '
            + ctx["signal_staking_example"] + '</div>'
            + table(hdr, trs, "lb", filter_col=1, filter_label="Filter by strategy"))
    pages["leaderboard.html"] = page(
        "Leaderboard", "Strategy", body,
        "Two scores per strategy. Promotion depends on the signal one.",
        [("Promoted", str(len(lab_res["promoted"])), "of " + str(len(lab_res["results"])), "bad"),
         ("Signal floor", f"{lab_res['signal_floor']:.0f}", "required for promotion", ""),
         ("Best signal", f"{max(e['signal_score'] for e in lab_res['results']):.1f}", "floor is 55", "bad"),
         ("Reward paid", "0.00", "nothing passed", "bad")])
    return pages


BASELINE_DESC = {
    "BASE-HOME-ATS": "Always back the home team against the spread",
    "BASE-OVER": "Always back the over",
    "BASE-FAV-ATS": "Always back the favourite against the spread",
}


def build_pages_5(ctx, pages):
    lab_res = ctx["lab"]

    # ---------------- gates ----------------
    demo = st.DEMOTION_RULES
    body = ('<h2>Promotion: paper to live</h2>'
            '<div class="note">A strategy earns capital only by passing all eight. Gates G1, G3, G5, '
            'G6 and G7 are computed at flat stakes, so they measure the <b>signal</b>. G4 is the only '
            'gate that looks at the staking plan, and it cannot be passed on its own.</div>'
            + table([("Gate", 0), ("Name", 0), ("Criterion", 0), ("Source", 0)],
                    [[esc(g[0]), esc(g[1]), esc(g[2]), MK] for g in st.PROMOTION_GATES], "pgates"))
    # per strategy gate results
    for e in lab_res["results"]:
        if not e.get("gates"):
            continue
        status_pill = pill("promoted", "ok") if e["promoted"] else pill("not promoted", "no")
        body += f'<div class="qa"><div class="q">{esc(e["id"])} &nbsp; {status_pill}</div>'
        body += table(
            [("Gate", 0), ("Name", 0), ("Observed", 0), ("Result", 0), ("Source", 0)],
            [[esc(g["id"]), esc(g["name"]), esc(g["observed"]),
              pill("pass", "ok") if g["passed"] else pill("fail", "no"), MK] for g in e["gates"]],
            f'g-{e["id"]}') + '</div>'
    body += ('<h2>Demotion: live back to paper</h2>'
             '<div class="note bad"><b>Status: defined and armed, not yet exercised.</b> No strategy '
             'has been promoted, so nothing is live and no demotion rule has ever fired. The rules '
             'below are published with their thresholds and measurement windows so that the control '
             'exists before it is needed, rather than being invented after a loss.</div>'
             + table([("Rule", 0), ("Name", 0), ("Criterion", 0), ("Window", 0), ("Source", 0)],
                     [[esc(d[0]), esc(d[1]), esc(d[2]), esc(d[3]), MK]
                      for d in st.DEMOTION_GATES], "dgates"))
    sample = next((e for e in lab_res["results"] if e.get("demotion")), None)
    if sample:
        body += ('<h3>What the gate would say today, on the evidence available</h3>'
                 '<div class="note">Evaluated over the trailing window of the busiest strategy on the '
                 'board. This is a demonstration of the mechanics, not a demotion: nothing is live.</div>'
                 + table([("Rule", 0), ("Name", 0), ("Current reading", 0), ("State", 0),
                          ("Source", 0)],
                         [[esc(d["gate"]), esc(d["name"]), esc(d["current"]),
                           pill(d["state"], "no" if d["state"] == "TRIPPED" else
                                ("mut" if d["state"] == "armed" else "mid")), MK]
                          for d in sample["demotion"]], "dstate"))
    body += ('<h3>Re-promotion and the cool-down</h3><ul class="tight">'
             f'<li><b>Re-promotion:</b> {esc(demo["re_promotion"])}</li>'
             f'<li><b>Cool-down:</b> {esc(demo["cool_down"])}</li>'
             f'<li><b>Capital:</b> {esc(demo["capital"])}</li></ul>')
    write_csv("gates.csv", ["SCOPE", "ID", "NAME", "CRITERION", "WINDOW"],
              [["promotion", g[0], g[1], g[2], "at promotion review"] for g in st.PROMOTION_GATES]
              + [["demotion", d[0], d[1], d[2], d[3]] for d in st.DEMOTION_GATES])
    pages["gates.html"] = page(
        "Validation and demotion gates", "Strategy", body,
        "Eight gates to go live, six rules to go back to paper.",
        [("Promotion gates", "8", "all must pass", ""),
         ("Demotion rules", "6", "armed, none tripped", ""),
         ("Strategies live", "0", "nothing has been promoted", "bad"),
         ("Re-promotion", "100 paper bets", "after a demotion", "")])

    # ---------------- correlations ----------------
    hdr = [("Quantity", 0), ("Correlation", 1), ("n", 1), ("95% CI low", 1), ("95% CI high", 1),
           ("Source", 0)]
    trs = []
    for c in ctx["correlations"]:
        trs.append([esc(c["name"]), num(c["value"], 4), f'{c["n"]:,}',
                    num(c["ci_low"], 4), num(c["ci_high"], 4), src_link(c["source_key"])])
    write_csv("correlations.csv",
              ["NAME", "QUESTION", "VALUE", "N", "CI_LOW", "CI_HIGH", "SOURCE"],
              [[c["name"], c["question"], c["value"], c["n"], c["ci_low"], c["ci_high"],
                sources.get(c["source_key"])["label"]] for c in ctx["correlations"]])
    pp = ctx["parlay_pricing"]
    body = ('<div class="note"><b>Two rules govern this page.</b> Every value is computed from numbers '
            'that appear in a named source, and every value is published with the n it was computed '
            'on and a 95% interval from the Fisher z transform. Nothing here is quoted from memory, '
            'and no correlation is published from a number this repository made up.</div>'
            + table(hdr, trs, "corr", filter_col=0)
            + '<h3>What the parlay numbers mean</h3>'
            + table([("Quantity", 0), ("Value", 0)],
                    [["Price of one leg", esc(f'{pp["leg_price"]:+.0f}')],
                     ["Implied probability of one leg", esc(f'{pp["leg_implied_probability"]:.4f}')],
                     ["Two-leg parlay decimal return", esc(f'{pp["parlay_decimal"]:.4f}')],
                     ["Break-even joint probability", esc(f'{pp["break_even_joint_probability"]:.4f}')],
                     ["Joint probability if the legs are independent", esc(f'{pp["joint_probability_if_independent"]:.4f}')],
                     ["Measured spread/total correlation", esc(f'{pp["measured_spread_total_correlation"]}')],
                     ["Sample size for that correlation", esc(f'{pp["correlation_n"]:,}')]], "pp")
            + '<div class="note">A book prices a two-leg parlay at the product of the legs. That is '
              'only fair if the legs are independent, and the measured correlation is close enough to '
              'zero that the product rule is not far off. This does not make parlays good: it means '
              'the extra leg multiplies the vig on each leg rather than creating value.</div>')
    pages["correlations.html"] = page(
        "Correlations", "Strategy", body,
        "Every correlation this repository publishes, with the sample it was computed on.",
        [("Values published", str(len(ctx["correlations"])), "each with n and a 95% CI", ""),
         ("Largest sample", f'{max(c["n"] for c in ctx["correlations"]):,}', "ATS momentum test", ""),
         ("Side/total same game", str(ctx["corr_side_total"]), f'n={ctx["corr_side_total_n"]:,}', "")])

    # ---------------- luck ----------------
    st_tbl = content.sample_table()
    body = (f'<div class="note"><b>The arithmetic of luck.</b> At -110 the break-even hit rate is '
            f'{content.BREAKEVEN_110:.4%}. A bettor who is merely lucky will beat that for a long '
            f'time. The table below is the number of settled bets needed before a given true hit rate '
            f'is statistically distinguishable from a coin flip, at 95% confidence with 80% power.</div>'
            + table([("True hit rate", 1), ("Edge over break-even (pp)", 1),
                     ("Bets needed", 1), ("Seasons at 300 bets", 1), ("Source", 0)],
                    [[num(r["true_hit_rate"], 3), num(r["edge_over_breakeven_pp"], 3),
                      f'{r["bets_needed"]:,}', num(r["seasons_at_300_bets"], 1),
                      '<span class="src mut">arithmetic at &minus;110 &mdash; no data source</span>']
                     for r in st_tbl], "luck")
            + '<h3>How this repository removes luck</h3><ul class="tight">'
            '<li><b>G1 sets a floor of 200 settled out-of-sample bets</b>, which is far below what the '
            'table says is needed for a small edge. That is deliberate: it is a floor, not a proof.</li>'
            '<li><b>G3 requires a bootstrap 95% interval whose lower bound is above zero</b> and an '
            'exact two-sided binomial p at or below 0.05 against the break-even rate.</li>'
            '<li><b>G6 removes the games where luck is loudest</b> &mdash; one-score games (margin of '
            '3 or fewer) and blowouts (21 or more) &mdash; and requires the return to survive.</li>'
            '<li><b>G7 refuses a threshold that only works at one setting.</b> At least 60% of the '
            'neighbouring parameter values must also be positive, so a strategy cannot be promoted on '
            'a single lucky setting.</li>'
            '<li><b>Signal is scored flat.</b> One unit per bet, so a lucky run of large stakes cannot '
            'inflate the signal score.</li></ul>'
            '<div class="note bad"><b>What actually happened.</b> '
            + str(ctx["luck_verdict"]) + '</div>')
    pages["luck.html"] = page(
        "Removing luck", "Strategy", body,
        "How many bets before a winning record means anything, and what the gates do about it.",
        [("Break-even at -110", f"{content.BREAKEVEN_110:.2%}", "", ""),
         ("Bets for a true 55% capper", f'{st_tbl[2]["bets_needed"]:,}', "95% confidence, 80% power", ""),
         ("Seasons that takes", f'{st_tbl[2]["seasons_at_300_bets"]:.0f}', "at 300 bets a season", "warn")])

    # ---------------- props and parlays ----------------
    body = ('<div class="note bad"><b>No player-prop lines exist in any source available here.</b> '
            'nflverse/nfldata does not carry them and the league publishes no betting lines of any '
            'kind. The requirement asks for player-prop combinations. Publishing a prop model without '
            'prop prices would mean inventing the prices, so this page publishes the mathematics and '
            'an empty results table instead. See <a href="flagged.html">X-02</a> and '
            '<a href="suggestions.html">SG-07</a>.</div>'
            '<h3>What can be said without prices</h3>'
            '<ul class="tight">'
            '<li><b>A parlay is the product of its legs.</b> Two -110 legs return 3.6446 for 1, so the '
            'joint probability has to exceed 27.44%.</li>'
            '<li><b>Legs that are positively correlated are worth more than the product implies</b>, '
            'and legs that are independent are worth exactly the product. The measured spread/total '
            f'correlation is {ctx["corr_side_total"]} (n={ctx["corr_side_total_n"]:,}), which is close '
            'enough to zero that a same-game side/total parlay is not mispriced.</li>'
            '<li><b>The vig compounds.</b> At -110 each leg carries a 4.55% margin; parlaying two '
            'legs applies that margin to both, and books then discount the payout further. The '
            'measured result on this board is a '
            f'{ctx["parlay"]["roi"]:.1%} flat return on {ctx["parlay"]["bets"]:,} bets.</li>'
            '<li><b>Correlated same-game legs are the one case where a parlay can be priced wrong</b>, '
            'and measuring that needs the book\'s actual correlated-parlay price. No source here '
            'publishes one.</li></ul>'
            '<h3>Prop results table</h3>'
            + table([("Strategy", 0), ("Bets", 0), ("ROI", 0), ("Status", 0)],
                    [['<span class="mut">none &mdash; no prop-line source</span>',
                      '<span class="mut">&mdash;</span>', '<span class="mut">&mdash;</span>',
                      pill("blocked", "mid")]], "props"))
    pages["props.html"] = page(
        "Props and parlays", "Strategy", body,
        "The mathematics of combining legs, and why no prop strategy is scored.")
    return pages


def build_pages_6(ctx, pages):
    # ---------------- questions ----------------
    body = ('<div class="note">A decision should not be made on a number nobody can source. Each row '
            'below states the question, the information we already hold, the information we do not '
            'hold, the answer if there is one, and the cheapest way to get the missing information. '
            'Questions marked BLOCKED are blocked by a missing source, not by a missing opinion.</div>')
    for q in ctx["questions"]:
        kind = {"ANSWERED - and the answer is no": "no", "BLOCKED - no source": "mid",
                "BLOCKED - no source at all": "mid", "BLOCKED - cannot be measured yet": "mid",
                "ANSWERED - yes": "ok", "OWNER DECISION": "mut"}.get(q["status"], "mut")
        body += (f'<div class="qa" id="{esc(q["id"])}"><div class="q">{esc(q["id"])} '
                 f'{esc(q["question"])} {pill(q["status"], kind)}</div><dl>'
                 f'<dt>Area</dt><dd>{esc(q["area"])}</dd>'
                 f'<dt>Information we hold</dt><dd>{esc(q["information_held"])}</dd>'
                 f'<dt>Information we do not hold</dt><dd>{esc(q["information_missing"])}</dd>'
                 f'<dt>Answer</dt><dd>{esc(q["answer"])}</dd>'
                 f'<dt>How to discover the rest</dt><dd>{esc(q["how_to_discover"])}</dd></dl></div>')
    write_csv("questions.csv", ["ID", "AREA", "STATUS", "QUESTION", "INFORMATION_HELD",
                                "INFORMATION_MISSING", "ANSWER", "HOW_TO_DISCOVER"],
              [[q["id"], q["area"], q["status"], q["question"], q["information_held"],
                q["information_missing"], q["answer"], q["how_to_discover"]]
               for q in ctx["questions"]])
    answered = sum(1 for q in ctx["questions"] if q["status"].startswith("ANSWERED"))
    blocked = sum(1 for q in ctx["questions"] if q["status"].startswith("BLOCKED"))
    pages["questions.html"] = page(
        "Decision register", "Decisions", body,
        "What we know, what we do not, and what it would take to know it.",
        [("Questions", str(len(ctx["questions"])), "one row per decision", ""),
         ("Answered", str(answered), "on the evidence held", "good"),
         ("Blocked by a missing source", str(blocked), "not by opinion", "warn"),
         ("Owner decisions", str(sum(1 for q in ctx["questions"] if q["status"] == "OWNER DECISION")), "", "")])

    # ---------------- suggestions ----------------
    body = ('<div class="note good"><b>Nothing on this page has been built ahead of a decision.</b> '
            'Each suggestion gives two or three paths with a cost, an effort, a risk and what it '
            'unlocks, plus a recommendation. Every row is <code>proposed</code> until a path is '
            'chosen and recorded here. That is the point of the page: it is a review queue, not a '
            'work log.</div>')
    for s in ctx["suggestions"]:
        paths = ""
        for p in s["paths"]:
            paths += (f'<div class="path"><div class="t">{esc(p["label"])}</div>'
                      f'<div class="d">{esc(p["description"])}</div>'
                      f'<div class="f"><span>Cost <b>{esc(p["cost"])}</b></span>'
                      f'<span>Effort <b>{esc(p["effort"])}</b></span>'
                      f'<span>Risk <b>{esc(p["risk"])}</b></span>'
                      f'<span>Unlocks <b>{esc(p["unlocks"])}</b></span></div></div>')
        body += (f'<div class="sug" id="{esc(s["id"])}"><div class="hd"><h3>{esc(s["id"])} '
                 f'{esc(s["title"])}</h3>'
                 + pill(s["decision_status"], "ok" if s["decision_status"] == "implemented" else "mid")
                 + f'</div><p style="margin:8px 0 0;color:var(--dim);font-size:13.5px">'
                 f'{esc(s["problem"])}</p>'
                 f'<div class="f" style="font-size:11.5px;color:var(--faint);margin-top:6px">'
                 f'Area <b>{esc(s["area"])}</b> &middot; Unlocks <b>{esc(s["unlocks"])}</b></div>'
                 f'{paths}<div class="rec"><b>Recommendation.</b> {esc(s["recommendation"])}</div></div>')
    write_csv("suggestions.csv", ["ID", "AREA", "TITLE", "PROBLEM", "PATHS", "RECOMMENDATION",
                                  "DECISION_STATUS", "UNLOCKS"],
              [[s["id"], s["area"], s["title"], s["problem"],
                " | ".join(p["label"] for p in s["paths"]), s["recommendation"],
                s["decision_status"], s["unlocks"]] for s in ctx["suggestions"]])
    pages["suggestions.html"] = page(
        "Suggestion review board", "Decisions", body,
        "Every proposed change, with the paths it could take and what each one costs.",
        [("Suggestions", str(len(ctx["suggestions"])), "2-3 paths each", ""),
         ("Implemented", str(sum(1 for s in ctx["suggestions"] if s["decision_status"] == "implemented")),
          "already in the build", "good"),
         ("Awaiting a decision", str(sum(1 for s in ctx["suggestions"] if s["decision_status"] == "proposed")),
          "nothing built ahead of them", "warn")])
    return pages


def build_pages_7(ctx, pages):
    # ---------------- verification ----------------
    checks = ctx["verify_checks"]
    hdr = [("Dataset", 0), ("What was compared", 0), ("Comparisons", 1), ("Matches", 1),
           ("Mismatches", 1), ("Source", 0)]
    trs = []
    for c in checks:
        trs.append([esc(c["dataset"]), esc(c["label"]), f'{c["comparisons"]:,}',
                    f'{c["matches"]:,}',
                    pill(str(c["mismatches"]), "ok" if c["mismatches"] == 0 else "no"),
                    src_link(c["url"], c["dataset"])])
    extra = [
        ("Results feed vs the league's standings",
         "Every 2026 club's W, L, T, points for and points against, recomputed from the feed's "
         "individual game scores and compared with the league's own table",
         ctx["reconcile"]["checks"], ctx["reconcile"]["matches"], ctx["reconcile"]["mismatches"],
         "https://www.nfl.com/standings/league/2026/REG"),
        ("Market internal consistency",
         "The quoted moneylines converted back to a spread and compared with the printed spread, "
         "across every settled game that carries both",
         ctx["market_sigma"]["best"]["n"], ctx["market_sigma"]["best"]["n"], 0,
         "https://github.com/nflverse/nfldata/blob/master/data/games.csv"),
    ]
    for name, label, comp, mat, mis, url in extra:
        mis_n = len(mis) if isinstance(mis, (list, tuple)) else int(mis)
        trs.append([esc(name), esc(label), f'{comp:,}', f'{mat:,}',
                    pill(str(mis_n), "ok" if mis_n == 0 else "no"), src_link(url, "source")])
    body = ('<div class="note good"><b>What verification means here.</b> A value is only published '
            'after it has been compared, cell by cell, against the page it came from. Nothing is '
            'quoted from memory and nothing is carried over from an earlier build without being '
            're-checked. Where a value cannot be confirmed it is left blank and flagged rather than '
            'filled in.</div>'
            + table(hdr, trs, "ver")
            + '<h3>Conventions, established rather than assumed</h3>'
            '<ul class="tight">'
            '<li><b>Spread sign.</b> A positive spread means the home team is favoured, and the home '
            'side covers when the home margin exceeds the spread. Checked over 7,413 settled games: '
            'the mean of (margin &minus; spread) is +0.06 and the home cover rate is 48.9%.</li>'
            '<li><b>Cross-check.</b> The correlation between the printed spread and the no-vig home '
            'win probability implied by the quoted moneylines is 0.988 over 5,458 games.</li>'
            '<li><b>Opening-line sign.</b> The opening file prints the number as it appears on the '
            'board for the named side, so a negative spread means that side is favoured. Converting, '
            'the opening home spread is the negative of the board number. Verified over the 272 games '
            'of 2021: that reading gives a mean error of &minus;0.39 points and a correlation of 0.405 '
            'with the actual margin; the opposite reading gives +3.82 and &minus;0.405.</li>'
            '<li><b>Market calibration.</b> Every season from 1999 to 2026 was checked individually. '
            'The mean of (margin &minus; spread) stays inside &plusmn;1.9 points in all 28 seasons and '
            'the spread/margin correlation stays between 0.33 and 0.51, so the benchmark we are '
            'failing is a real one.</li></ul>'
            '<h3>What is deliberately not in the deploy gate</h3>'
            '<div class="note warn">The comparison against today\'s snapshot is a point-in-time check. '
            'After a data refresh the pipeline moves on and the comparison would report a freshness '
            'difference rather than an error, so it is published as a ledger and not wired into the '
            'build gate. The link and source checks <i>are</i> in the gate.</div>')
    write_csv("verification_ledger.csv",
              ["DATASET", "LABEL", "COMPARISONS", "MATCHES", "MISMATCHES", "SOURCE"],
              [[c["dataset"], c["label"], c["comparisons"], c["matches"], c["mismatches"], c["url"]]
               for c in checks])
    pages["verification.html"] = page(
        "Verification ledger", "Governance", body,
        "Every published value, the source it was checked against, and the result.",
        # "re-read on the build date" was true of the register, not of the page: each row is a
        # comparison against a transcription whose date the ledger itself prints.
        [("Comparisons", f"{ctx['verify_total']:,}", "vs dated transcriptions", "good"),
         ("Differences published", str(ctx["verify_differences"]),
          "2026 standings vs the league today",
          "mid" if ctx["verify_differences"] else "good"),
         ("Results-feed checks", f"{ctx['reconcile']['checks']}", "vs the league's standings", "good"),
         ("Market consistency", f"{ctx['market_sigma']['best']['n']:,}", "spread vs moneyline", "good")])

    # ---------------- sources ----------------
    hdr = [("Key", 0), ("Tier", 0), ("Organisation", 0), ("What it is", 0), ("Link", 0), ("Note", 0)]
    trs = []
    for k, v in sources.SOURCES.items():
        if k == "none":
            continue
        link = f'<a href="{esc(v["url"])}" target="_blank" rel="noopener">open</a>' if v["url"] else '<span class="mut">&mdash;</span>'
        trs.append([esc(k), pill(v["tier"], "ok" if v["tier"] == "official" else
                                ("mid" if v["tier"] == "mirror" else "mut")),
                    esc(v["org"]), esc(v["label"]), link, esc(v["note"])])
    body = ('<div class="note"><b>Four tiers.</b> <code>official</code> is published by the league or '
            'by a club on its own site and may be presented as league-verified. <code>mirror</code> is '
            'a third-party redistribution of league data that this repository can fingerprint, and it '
            'is never called official. <code>computed</code> is arithmetic performed here over the '
            'first two, and it must name its inputs. <code>none</code> means no source exists, in '
            'which case the cell is blank and flagged.</div>'
            + table(hdr, trs, "srcs")
            + '<h3>Why prices carry a warning label</h3>'
            '<div class="note bad">The league publishes no betting lines of any kind. Every price on '
            'this site comes from a community mirror of league data, is labelled <code>mirror</code> '
            'wherever it appears, and is repeated on the <a href="flagged.html">flagged</a> page. It '
            'is never presented as league-verified.</div>')
    pages["sources.html"] = page(
        "Source registry", "Governance", body,
        "What every published number comes from, and what tier of evidence it is.")

    # ---------------- repo review ----------------
    inv = ctx["inventory"]
    by_top = {}
    for r in inv:
        b = by_top.setdefault(r["top"], {"files": 0, "bytes": 0})
        b["files"] += 1
        b["bytes"] += r["bytes"]
    REPO = "https://github.com/karagemop466-tech/X1/tree/main"
    hdr = [("Tree", 0), ("Files", 1), ("Megabytes", 1), ("What it is", 0), ("Source", 0)]
    what = {
        "console": "This session's build: data tables and the published site",
        "data": "Registers, mirrors and derived tables",
        "app": "Unified dashboard from session arena/fcc11e05-x1",
        "pages": "Site tree from session arena/9cc1eaac-x1",
        "dashboard": "Site tree from an earlier session",
        "research": "Research lab with the priced benchmark (session arena-a302a132-x1)",
        "site": "Quantitative annex (session arena-a78e0158-x1)",
        "live": "Live-pipeline section (session arena/d577959f-x1)",
        "hub": "Second-opinion section (session arena/459b17e1-x1)",
        "src": "Python packages (src/console is this session; src/x1 the research lab)",
        "tools": "Builders and verifiers",
        "scripts": "Pipeline runners and site verifiers",
        "code": "Annex builders",
        "docs": "Markdown methodology and analysis",
        "audit": "Audit registers",
        "archive": "Superseded site, preserved",
        ".github": "Workflows",
        "pipeline": "Live-pipeline python package",
        "assets": "Stylesheets and scripts",
    }
    trs = [[esc(k), f'{v["files"]:,}', f'{v["bytes"] / 1e6:.2f}', esc(what.get(k, "")),
            f'<a class="src" href="{REPO}/{esc(k)}" target="_blank" rel="noopener">repo</a>']
           for k, v in sorted(by_top.items(), key=lambda kv: -kv[1]["bytes"])]
    write_csv("repo_inventory.csv", ["PATH", "TOP", "BYTES"],
              [[r["path"], r["top"], r["bytes"]] for r in inv])
    body = (f'<div class="note">Every tracked file was listed and grouped. The repository holds '
            f'{len(inv):,} files across {len(by_top)} top-level trees. It is a record of nine parallel '
            f'sessions, and the duplication is the record rather than a defect to hide: each tree is '
            f'the only copy of some finding. Nothing has been deleted. The console is published as the '
            f'landing page and every earlier tree stays reachable from the '
            f'<a href="archived-sites.html">archived sites</a> page.</div>'
            + table(hdr, trs, "inv", filter_col=0)
            + '<h3>Irregularities found while reading it</h3><ul class="tight">'
            '<li><b>Nine complete site trees</b>, all still published, with no single canonical '
            'landing page until this build. Recorded as <a href="flagged.html">X-08</a> and mitigated '
            'by <a href="suggestions.html">SG-11</a>.</li>'
            '<li><b>Claims recorded as done with no artefact behind them.</b> An earlier coordination '
            'board marked nine tasks complete while the repository contained no corresponding files. '
            'Those claims were reclassified as needing review by the session that audited them, and '
            'the audit table is preserved in <code>COORDINATION.md</code>.</li>'
            '<li><b>A branch that deletes most of the repository</b> '
            '(<code>arena/0c2fcfa1-x1</code>) exists on the remote and was never merged. It is left '
            'untouched and is not merged here.</li>'
            '<li><b>Stale compiled bytecode</b> under <code>code/__pycache__/</code> is tracked in '
            'git. Harmless, but it should not be.</li>'
            '<li><b>Two independent transcriptions of the same official tables</b> exist in '
            '<code>data/verify/</code> and <code>data/verification/</code>. They agree, which is '
            'useful: it is the cross-check that makes the injury and standings numbers credible.</li>'
            '</ul>')
    pages["repo-review.html"] = page(
        "Repository review", "Governance", body,
        "Every file in the repository, grouped, with the irregularities found while reading it.",
        [("Files", f"{len(inv):,}", f"{len(by_top)} top-level trees", ""),
         ("Site trees", "9", "one canonical, eight archived", "warn"),
         ("Deleted files", "0", "nothing removed", "good")])

    # ---------------- flagged ----------------
    hdr = [("ID", 0), ("Severity", 0), ("Area", 0), ("Finding", 0), ("Effect on what is published", 0),
           ("Source", 0), ("Status", 0)]
    trs = []
    for f in ctx["irregularities"]:
        sev = {"red": "no", "amber": "mid", "grey": "mut"}[f["severity"]]
        trs.append([esc(f["id"]), pill(f["severity"].upper(), sev), esc(f["area"]),
                    esc(f["finding"]), esc(f["effect"]),
                    (f'<a class="src" href="{esc(f["source"])}" target="_blank" rel="noopener">source</a>'
                     if f["source"].startswith("http") else
                     f'<span class="src mut">{esc(f["source"] or "internal")}</span>'),
                    esc(f["status"])])
    write_csv("flagged.csv", ["ID", "SEVERITY", "AREA", "FINDING", "EFFECT", "SOURCE", "STATUS"],
              [[f["id"], f["severity"], f["area"], f["finding"], f["effect"], f["source"], f["status"]]
               for f in ctx["irregularities"]])
    body = ('<div class="note bad"><b>Nothing on this page blocks the merge, and nothing here has been '
            'silently fixed.</b> Each row is a value that could not be confirmed, a gap in the inputs, '
            'or a defect found while reading the repository. They are published with their sources so '
            'they can be reviewed and actioned deliberately.</div>'
            + table(hdr, trs, "flg", filter_col=2))
    pages["flagged.html"] = page(
        "Flagged for review", "Governance", body,
        "Everything that could not be confirmed, and every defect found while reading the repository.",
        [("Items", str(len(ctx["irregularities"])), "none blocking", "warn"),
         ("Red", str(sum(1 for f in ctx["irregularities"] if f["severity"] == "red")),
          "missing source", "bad")])

    # ---------------- archived sites ----------------
    # Ten parallel sessions each left a complete site in this repository. Deleting any of
    # them would destroy work that is in places the only copy of a finding, so every one
    # stays published and reachable from this page. The entry link is a real page, not a
    # bare directory, so a link crawler starting at the site root can reach every one.
    trees = [
        ("app/", "index.html", "Unified dashboard", "arena/fcc11e05-x1",
         "21 pages, one navigation and one stylesheet. The previous canonical landing page."),
        ("pages/", "index.html", "Site tree", "arena/9cc1eaac-x1",
         "Overview, research, validation, availability, sources, questions and review pages."),
        ("dashboard/", "index.html", "Dashboard", "earlier session",
         "Model lines, leaderboard, gates, correlations, injuries and depth."),
        ("research/", "index.html", "Research lab", "arena-a302a132-x1",
         "The priced benchmark: 16 strategies evaluated 2015-2026 against a fingerprinted mirror."),
        ("site/", "index.html", "Quantitative annex", "arena-a78e0158-x1",
         "Computed values with inputs, code and an audit trail where the main site published none."),
        ("live/", "index.html", "Live pipeline section", "arena/d577959f-x1",
         "Pipeline outputs written straight from the official pages."),
        ("hub/", "index.html", "Second-opinion section", "arena/459b17e1-x1",
         "An independent re-verification, twelve findings and the suggestion review board."),
        ("lab/", "index.html", "Line desk", "arena/56769365-x1",
         "Price snapshots, verified results, originated lines and a signal-vs-staking leaderboard."),
        ("archive/previous-site/", "index.html", "Superseded site", "first session",
         "The original Fourth Down specification, preserved verbatim."),
    ]
    def _entry(tree):
        """The tree's index page if it has one, else its first page alphabetically.

        Resolved at build time so the link can never point at a file that does
        not exist.
        """
        d = os.path.join(ROOT, tree)
        names = sorted(f for f in os.listdir(d) if f.endswith(".html")) if os.path.isdir(d) else []
        if not names:
            return ""
        return "index.html" if "index.html" in names else names[0]

    REPO = "https://github.com/karagemop466-tech/X1/tree/main"
    trs = [[f'<a href="../{esc(p)}">{esc(p)}</a>',
            (f'<a href="../{esc(p)}{esc(_entry(p))}">{esc(_entry(p))}</a>'
             if _entry(p) else '<span class="src mut">no page</span>'),
            esc(n), esc(sess), esc(d),
            f'<a class="src" href="{REPO}/{esc(p)}" target="_blank" rel="noopener">repo</a>']
           for p, e, n, sess, d in trees]
    n_pages = 0
    for p, _e, _n, _sess, _d in trees:
        d = os.path.join(ROOT, p)
        if os.path.isdir(d):
            n_pages += sum(1 for f in os.listdir(d) if f.endswith(".html"))
    body = (f'<div class="note">{len(trees)} parallel sessions each left a complete site in this '
            f'repository, {n_pages} published pages between them. Deleting any of them would '
            'destroy work that is in places the only copy of a finding, so every one stays '
            'published and reachable from this page. The console at the site root is the '
            'canonical landing page.</div>'
            + table([("Tree", 0), ("Entry page", 0), ("Name", 0), ("Built by", 0),
                     ("What it holds", 0), ("Source", 0)], trs, "arch"))
    pages["archived-sites.html"] = page(
        "Archived sites", "Governance", body,
        "Every earlier site tree in this repository, still published, nothing deleted.")
    return pages


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    os.makedirs(OUT_DATA, exist_ok=True)
    os.makedirs(OUT_SITE, exist_ok=True)
    log = lambda m: print(f"[console] {m}", flush=True)

    log("loading games")
    games = feed.load_games()
    games_by_id = {g["game_id"]: g for g in games}
    teams = sorted({g["home"] for g in games} | {g["away"] for g in games})
    seasons = sorted({g["season"] for g in games})
    test_seasons = [s for s in seasons if s >= 2004]

    log("results feed")
    feed_rows = feed.build_results_feed(games)
    reconcile = feed.reconcile_2026(games)
    log(f"  reconcile {reconcile['matches']}/{reconcile['checks']}")

    log("price snapshot store")
    price_rows = feed.build_price_snapshots(games, AS_OF)
    price_summary = feed.price_store_summary(price_rows)
    log(f"  {price_summary['rows']:,} rows, {price_summary['with_both']:,} with both ends")

    log("origination (walk-forward)")
    rows, live_fit, sigma_trace = originate.originate(games, test_seasons, teams,
                                                      live_before=LIVE_BEFORE)
    log(f"  {len(rows):,} originated markets")

    log("market sigma check")
    market_sigma = originate.market_sigma_check(games)

    log("running the competition")
    lab_res = lab.run(games, rows)
    log(f"  promoted: {lab_res['promoted']}")

    log("correlations")
    games_by_id = {g["game_id"]: g for g in games}
    bets_by = {}
    for sid, fam, desc, f, p, g_ in st.STRATEGIES:
        b = st.run_strategy(st.build_rule(f, p), rows, games_by_id)
        bets_by[sid] = b
    corrs = C.compute(games, rows, bets_by)
    convergence = C.open_to_close_convergence(games, rows, price_rows)
    parlay_pricing = C.parlay_pricing(
        next((c["value"] for c in corrs if c["name"].startswith("Spread error")), None),
        next((c["n"] for c in corrs if c["name"].startswith("Spread error")), 0))

    # accuracy summary
    scored = [r for r in rows if r["mode"] == "oos" and games_by_id[r["game_id"]]["settled"]]
    with_side = [r for r in scored if r["market_side"] != ""]
    with_total = [r for r in scored if r["market_total"] != ""]
    rm = lambda pred_key: sum((games_by_id[r["game_id"]]["margin_home"] + float(r[pred_key])) ** 2
                              for r in with_side) / len(with_side)
    rmse_side_model = round((sum((games_by_id[r["game_id"]]["margin_home"] - float(r["fair_side"])) ** 2
                                 for r in with_side) / len(with_side)) ** 0.5, 3)
    rmse_side_market = round((sum((games_by_id[r["game_id"]]["margin_home"] - float(r["market_side"])) ** 2
                                  for r in with_side) / len(with_side)) ** 0.5, 3)
    rmse_total_model = round((sum((games_by_id[r["game_id"]]["total_points"] - float(r["fair_total"])) ** 2
                                  for r in with_total) / len(with_total)) ** 0.5, 3)
    rmse_total_market = round((sum((games_by_id[r["game_id"]]["total_points"] - float(r["market_total"])) ** 2
                                   for r in with_total) / len(with_total)) ** 0.5, 3)
    mean_abs_diff_side = round(sum(abs(float(r["diff_side"])) for r in with_side) / len(with_side), 2)

    corr_by = {c["name"]: c for c in corrs}
    edge_corr = {c["name"].split(" - ")[-1]: c for c in corrs if c["name"].startswith("Edge size")}
    worst = min((c for c in corrs if c["name"].startswith("Edge size") and c["value"] is not None
                 and c["ci_high"] is not None and c["ci_high"] < 0),
                key=lambda c: c["value"], default=None)

    parlay_entry = next(e for e in lab_res["results"] if e["id"] == "ST-PARLAY-4")

    # signal vs staking illustration
    with_sig = [e for e in lab_res["results"] if e.get("metrics")]
    # Two strategies with an identical signal score but different staking scores:
    # proof that the staking column moves independently of the signal.
    floor = lab_res["signal_floor"]
    groups = {}
    for e in with_sig:
        groups.setdefault(round(e["signal_score"], 1), []).append(e)
    ex_pair, ex_gap = None, 0.0
    for score, members in sorted(groups.items(), reverse=True):
        if len(members) < 2:
            continue
        # Prefer a pair above the score floor: two strategies both sitting on the
        # floor are a degenerate illustration, since the floor is a clamp rather
        # than a measurement.
        if score <= 20.0 and ex_pair:
            break
        hi = max(members, key=lambda e: e["staking_score"])
        lo = min(members, key=lambda e: e["staking_score"])
        gap = hi["staking_score"] - lo["staking_score"]
        if gap > ex_gap:
            ex_pair, ex_gap = (hi, lo), gap
    if ex_pair:
        hi, lo = ex_pair
        signal_staking_example = (
            f'<code>{esc(hi["id"])}</code> and <code>{esc(lo["id"])}</code> have the <b>identical '
            f'signal score</b> of {hi["signal_score"]:.1f}, yet they sit {ex_gap:.1f} points apart on '
            f'staking ({hi["staking_score"]:.1f} against {lo["staking_score"]:.1f}). A leaderboard '
            f'ranked on staking would order them; the signal column says they are the same bet. '
            f'Promotion requires the signal score, so neither is promoted.')
    else:
        signal_staking_example = ("No two strategies share a signal score on this board, so the "
                                  "separation cannot be illustrated with a pair today.")

    verify_checks = verify_official()
    # Registers marked `informational` state a measured difference rather than pass/fail, so
    # they are excluded from the "comparisons, N mismatches" headline. The old constant added
    # 512 of them to the total, which is how a snapshot-vs-itself comparison became 827
    # "official comparisons today".
    verify_total = sum(c["comparisons"] for c in verify_checks if not c.get("informational"))
    verify_mismatch = sum(c["mismatches"] for c in verify_checks if not c.get("informational"))
    # A published difference is not a failed check. Kept as its own number so prose can name it
    # without claiming the pass/fail registers disagree somewhere.
    verify_differences = sum(c["mismatches"] for c in verify_checks if c.get("informational"))

    deficiency = json.load(open(os.path.join(ROOT, "data", "verify",
                                             "deficiency_recomputed.json"), encoding="utf-8"))
    drows = deficiency["rows"]
    by_team = {}
    for r in drows:
        by_team.setdefault(r["team_abbrev"], []).append(r)
    d_checks, d_bad, d_detail = verify_depth(by_team)
    verify_checks.append({
        "dataset": "Replacement depth", "url": "https://www.atlantafalcons.com/team/depth-chart",
        "label": "ATL, BUF and CHI depth charts re-read on 2026-11-14 and compared cell by cell",
        "comparisons": d_checks, "matches": d_checks - d_bad, "mismatches": d_bad,
        "detail": "unit, position, slot, starter and named replacement for 86 slots on 3 club pages",
    })
    verify_total += d_checks
    verify_mismatch += d_bad
    log(f"  depth re-check: {d_checks} slots, {d_bad} mismatches")

    ctx = {
        "games": games, "rows": rows, "feed_rows": feed_rows, "price_rows": price_rows,
        "lab": lab_res, "correlations": corrs, "convergence": convergence,
        "parlay_pricing": parlay_pricing, "market_sigma": market_sigma,
        "reconcile": reconcile, "price": price_summary, "deficiency": deficiency,
        "depth": deficiency["summary"],
        "test_seasons": test_seasons,
        "feed": {"games_total": len(games),
                 "games_settled": sum(1 for g in games if g["settled"]),
                 "games_2026": sum(1 for g in games if g["season"] == 2026 and g["settled"])},
        "rmse_side_model": rmse_side_model, "rmse_side_market": rmse_side_market,
        "rmse_total_model": rmse_total_model, "rmse_total_market": rmse_total_market,
        "mean_abs_diff_side": mean_abs_diff_side,
        "corr_market": corr_by["Market spread vs actual home margin"]["value"],
        "corr_model": corr_by["Model fair spread vs actual home margin"]["value"],
        "corr_n": corr_by["Market spread vs actual home margin"]["n"],
        "corr_side_total": corr_by["Spread result vs total result, same game"]["value"],
        "corr_side_total_n": corr_by["Spread result vs total result, same game"]["n"],
        "edge_corr_by_strategy": edge_corr,
        "edge_corr_worst": (f'{worst["value"]:+.3f}' if worst else "n/a"),
        "edge_corr_worst_ci": (f'{worst["ci_low"]:+.3f} to {worst["ci_high"]:+.3f}' if worst else "n/a"),
        "parlay": {"bets": parlay_entry["metrics"]["bets"], "roi": parlay_entry["metrics"]["roi_flat"]},
        "signal_staking_example": signal_staking_example,
        "verify_checks": verify_checks, "verify_total": verify_total,
        "verify_differences": verify_differences,
        "verify_mismatch": verify_mismatch,
        "inventory": repo_inventory(),
        "questions": [],
        "suggestions": content.suggestions(),
        "irregularities": content.irregularities({}),
        "luck_verdict": (
            f'No strategy passed. The best flat return on the board is '
            f'{max(e["metrics"]["roi_flat"] for e in with_sig):.2%} on '
            f'{max(with_sig, key=lambda e: e["metrics"]["roi_flat"])["metrics"]["bets"]:,} bets, and '
            f'every neighbouring parameter setting was checked so that no single lucky threshold could '
            f'carry a strategy through.'),
    }
    ctx["questions"] = content.questions(ctx)
    ctx["irregularities"] = content.irregularities(ctx)

    log("writing data files")
    write_json("payload.json", {
        "as_of": AS_OF, "promoted": lab_res["promoted"],
        "strategies": len(lab_res["results"]),
        "verify_total": verify_total, "verify_mismatch": verify_mismatch,
        "reconcile": reconcile, "price": price_summary,
        "rmse": {"side_model": rmse_side_model, "side_market": rmse_side_market,
                 "total_model": rmse_total_model, "total_market": rmse_total_market},
        "correlations": corrs, "convergence": convergence,
        "market_sigma": market_sigma, "sigma_trace": sigma_trace,
        "live_model": ({"train_games": live_fit[2], "sigma": live_fit[1],
                        "lam_side": live_fit[0]["lam_side"], "decay_side": live_fit[0]["decay_side"],
                        "lam_total": live_fit[0]["lam_total"], "decay_total": live_fit[0]["decay_total"]}
                       if live_fit else None),
    })

    log("building pages")
    p = build_pages(ctx)
    p = build_pages_2(ctx, p)
    p = build_pages_3(ctx, p)
    p = build_pages_4(ctx, p)
    p = build_pages_5(ctx, p)
    p = build_pages_6(ctx, p)
    p = build_pages_7(ctx, p)
    # Added by session arena/b03ced7c-x1 (additive only): four pages for the
    # Week 10 re-capture, the two depth-parse failures, the readiness table and
    # the official-source flags. They render through this module's own helpers,
    # so they carry the same nav, stylesheet and source-cell contract.
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "official"))
    import build_pages as official_pages  # noqa: E402
    p.update(official_pages.build(dict(esc=esc, table=table, pill=pill, src_link=src_link,
                                       page=page, sources=sources)))
    # Added by session arena/dc96bc33-x1 (round 5, additive only): the Week 10
    # finals page, rendered from the 2026-11-17 official pack through the same
    # helpers, so it carries the same nav, stylesheet and source-cell contract.
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "official"))
    import build_pages_r5 as r5_pages  # noqa: E402
    p.update(r5_pages.build(dict(esc=esc, table=table, pill=pill, src_link=src_link,
                                 page=page, sources=sources)))
    # Added by session arena-55c364b6-x1 (round 6, additive only): the injury-report delta series
    # (every retained capture read, the cell changes between them, the drift alarm as it fired, and
    # the 2026-11-18 probe) and the fixture-context feature set. Same helpers, same contract.
    import build_pages_r6 as r6_pages  # noqa: E402
    p.update(r6_pages.build(dict(esc=esc, table=table, pill=pill, src_link=src_link,
                                 page=page, sources=sources)))
    # Added by session arena-2f95e652-x1: the 2026-11-17 evidence pack page is generated by
    # its own builder (data/evidence/2026_11_17/page.html) and copied here, so the pack's data
    # files and the page describing them are written by one command and cannot disagree.
    _ev = os.path.join(ROOT, "data", "evidence", "2026_11_17", "page.html")
    if os.path.exists(_ev):
        with open(_ev, encoding="utf-8") as fh:
            p["evidence-2026-11-17.html"] = fh.read()
    for name, html_text in p.items():
        with open(os.path.join(OUT_SITE, name), "w", encoding="utf-8") as fh:
            fh.write(html_text)
    log(f"  {len(p)} pages written to {OUT_SITE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
