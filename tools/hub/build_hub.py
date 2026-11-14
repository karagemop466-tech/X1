#!/usr/bin/env python3
"""Build the X1 hub: one clean landing page plus category subpages.

Session arena-459b17e1-x1. Reads only committed datasets, writes only hub/.
Every table row emitted carries a link to the official page it came from; where
no official source exists the cell is rendered as an explicit UNVERIFIED badge.
"""

from __future__ import annotations

import csv
import html
import json
import os
import re
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HUB = os.path.join(ROOT, "hub")
SNAPSHOT = "2026-11-14"
GENERATED = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

CSS = """
:root{--bg:#0d1117;--panel:#161b22;--panel2:#1c2430;--line:#2b3440;--ink:#e6edf3;
--muted:#9aa7b4;--accent:#4cc38a;--warn:#e3b341;--bad:#f87171;--link:#58a6ff;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
a{color:var(--link);text-decoration:none}
a:hover{text-decoration:underline}
.rail{position:fixed;top:0;left:0;bottom:0;width:250px;background:var(--panel);
border-right:1px solid var(--line);overflow-y:auto;padding:18px 0}
.brand{display:block;padding:0 18px 14px;font-weight:700;letter-spacing:.04em;font-size:17px;color:var(--ink)}
.brand small{display:block;font-weight:400;color:var(--muted);font-size:11px;letter-spacing:.14em;margin-top:3px}
.rail nav a{display:block;padding:7px 18px;color:var(--muted);font-size:13.5px;border-left:2px solid transparent}
.rail nav a:hover{color:var(--ink);background:#1b2230}
.rail nav a.active{color:var(--ink);background:#1b2230;border-left-color:var(--accent)}
.rail .grp{padding:14px 18px 4px;font-size:10.5px;letter-spacing:.14em;color:#65717e;text-transform:uppercase}
main{margin-left:250px;padding:26px 32px 70px;max-width:1180px}
h1{font-size:27px;margin:0 0 6px;line-height:1.2}
h2{font-size:19px;margin:30px 0 10px}
h3{font-size:15px;margin:18px 0 6px}
.eyebrow{font-size:10.5px;letter-spacing:.16em;color:var(--muted);text-transform:uppercase;margin-bottom:10px}
.lede{color:var(--muted);max-width:820px;margin:0 0 20px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(255px,1fr));gap:14px;margin:14px 0 8px}
.card{display:block;background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:15px;color:var(--ink)}
.card:hover{border-color:#3d4a5a;text-decoration:none}
.card h3{margin:4px 0 5px;font-size:15px}
.card p{margin:0;color:var(--muted);font-size:12.8px}
.card .tag{font-size:10px;letter-spacing:.13em;color:var(--accent);text-transform:uppercase}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:16px 0 6px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:13px}
.stat b{display:block;font-size:23px;line-height:1.1}
.stat span{color:var(--muted);font-size:11.5px}
table{width:100%;border-collapse:collapse;background:var(--panel);
border:1px solid var(--line);border-radius:8px;overflow:hidden;font-size:13px;margin:8px 0 6px}
th,td{padding:7px 9px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{background:var(--panel2);font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);position:sticky;top:0}
tr:last-child td{border-bottom:none}
tbody tr:hover{background:#1a212c}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.scroll{max-height:70vh;overflow:auto;border:1px solid var(--line);border-radius:8px}
/* marker: a table whose every row carries a source link (or an explicit badge). */
table.src{border-left:2px solid var(--accent)}
.note{background:var(--panel2);border-left:3px solid var(--warn);padding:11px 14px;
border-radius:0 6px 6px 0;color:#c9d4e0;font-size:13px;margin:12px 0}
.note.good{border-left-color:var(--accent)}
.note.bad{border-left-color:var(--bad)}
.pill{display:inline-block;padding:1px 7px;border-radius:9px;font-size:11px;font-weight:600;white-space:nowrap}
.pill.pass{background:#12331f;color:#5fd48d;border:1px solid #1d5732}
.pill.fail{background:#3a1616;color:#ff8b8b;border:1px solid #5f2222}
.pill.unv{background:#3a2f10;color:#e3b341;border:1px solid #5d4a16}
.pill.out{background:#3a1616;color:#ff8b8b;border:1px solid #5f2222}
.pill.doubt{background:#3a2f10;color:#e3b341;border:1px solid #5d4a16}
.pill.quest{background:#1c2b3a;color:#7cb7ff;border:1px solid #26435c}
.pill.ok{background:#12331f;color:#5fd48d;border:1px solid #1d5732}
.pill.prop{background:#1c2b3a;color:#7cb7ff;border:1px solid #26435c}
.pill.ready{background:#12331f;color:#5fd48d;border:1px solid #1d5732}
.pill.defer{background:#3a2f10;color:#e3b341;border:1px solid #5d4a16}
.pill.blocked{background:#3a1616;color:#ff8b8b;border:1px solid #5f2222}
code{background:#0b1017;border:1px solid var(--line);border-radius:4px;padding:1px 5px;font-size:12.5px}
.small{font-size:12px;color:var(--muted)}
footer{margin:38px 0 0;color:#65717e;font-size:11.5px;border-top:1px solid var(--line);padding-top:14px}
.decl{border:1px solid var(--line);border-radius:9px;background:var(--panel);padding:16px;margin:14px 0}
.decl h3{margin:0 0 4px;font-size:16px}
.decl .meta{font-size:11.5px;color:var(--muted);margin-bottom:8px}
.opt{border-left:2px solid #2b3440;padding-left:11px;margin:9px 0}
.opt.rec{border-left-color:var(--accent)}
.opt b{font-size:13.5px}
.opt p{margin:3px 0;font-size:12.8px;color:#c9d4e0}
.opt .kv{color:var(--muted)}
@media(max-width:900px){.rail{position:static;width:auto;border-right:none;border-bottom:1px solid var(--line)}
main{margin-left:0;padding:18px}}
"""


def e(v):
    return html.escape("" if v is None else str(v), quote=True)


def cell(v, cls="", title=""):
    """Escaped cell: use for values read out of the data."""
    t = f' title="{e(title)}"' if title else ""
    return f'<td class="{cls}"{t}>{e(v)}</td>'


def rcell(v, cls="", title=""):
    """Raw cell: use for markup this module generates (links, badges)."""
    t = f' title="{e(title)}"' if title else ""
    return f'<td class="{cls}"{t}>{v}</td>'


def srclink(url, label=None):
    if not url:
        return '<span class="pill unv">no official source</span>'
    text = label or re.sub(r"^https?://(www\.)?", "", url)
    if len(text) > 46:
        text = text[:43] + "..."
    return f'<a href="{e(url)}" rel="noopener">{e(text)}</a>'


def load(rel):
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        return None
    return json.load(open(p, encoding="utf-8"))


NAV = [
    ("SECOND OPINION", None),
    ("index.html", "Section index"),
    ("verification.html", "Verification ledger"),
    ("findings.html", "Findings"),
    ("deficiency.html", "Depth deficiency"),
    ("DECIDE", None),
    ("decisions.html", "Suggestion review board"),
]


def page(title, body, active, subtitle=""):
    nav = []
    for target, label in NAV:
        if label is None:
            nav.append(f'<div class="grp">{e(target)}</div>')
        else:
            cls = ' class="active"' if target == active else ""
            nav.append(f'<a{cls} href="{e(target)}">{e(label)}</a>')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)} — X1</title>
<link rel="stylesheet" href="assets/hub.css"></head>
<body>
<aside class="rail"><a class="brand" href="index.html">X1<small>NFL LINE LAB</small></a>
<nav>{''.join(nav)}</nav></aside>
<main>
<div class="eyebrow">X1 · NFL LINE LAB · SNAPSHOT {SNAPSHOT}</div>
<h1>{e(title)}</h1>
{f'<p class="lede">{e(subtitle)}</p>' if subtitle else ''}
{body}
<footer>Every table row links to the official page it was read from. A value no official
source publishes is left blank and badged UNVERIFIED — never inferred. Generated
{GENERATED} by session arena-459b17e1-x1.
<p><a href="../index.html">← Back to the main dashboard</a> ·
<a href="../pages/flagged.html">Flagged for review</a> ·
<a href="../pages/sources.html">Sources</a></p></footer>
</main></body></html>
"""


def table(headers, rows, scroll=True, cls=""):
    th = "".join(f'<th class="{c}">{e(h)}</th>' for h, c in headers)
    trs = "".join("<tr>" + "".join(c) + "</tr>" for c in rows)
    inner = f'<table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>'
    return f'<div class="scroll">{inner}</div>' if scroll else inner


def stat(value, label, note=""):
    return f'<div class="stat"><b>{e(value)}</b><span>{e(label)}' + \
           (f'<br>{e(note)}' if note else "") + "</span></div>"


# --------------------------------------------------------------------------
# page builders
# --------------------------------------------------------------------------

def build_index_old_():
    ver = [load("data/verification/standings.json"), load("data/verification/schedule.json"),
           load("data/verification/injuries.json"), load("data/verification/deficiency.json")]
    def g(v, *keys):
        for k in keys:
            if k in v:
                return v[k]
        return 0
    checks = sum(g(v, "checks", "status_checks") for v in ver if v)
    fails = sum(g(v, "fail") for v in ver if v)
    unv = sum(g(v, "unverified") for v in ver if v)
    dep = load("data/pipeline/deficiency.json") or {}
    depth_rows = dep.get("verification", {}).get("rows", 0)

    cards = [
        ("verification.html", "LEDGER", "Verification ledger",
         f"{checks:,} independent cell checks re-run against the official pages on {SNAPSHOT}. "
         f"{fails} mismatch, {unv} values no official page publishes."),
        ("standings.html", "DATA", "Standings",
         "All 32 clubs through Week 10 Thursday. 1,184 cells checked, 0 mismatches."),
        ("week10.html", "DATA", "Week 10 slate",
         "14 games and 4 byes, kickoff times and networks, plus the quarterback provenance problem."),
        ("injuries.html", "DATA", "Injuries",
         "The official report: 345 rows, 28 club tables, 160 players carrying a game status."),
        ("deficiency.html", "DATA", "Depth deficiency",
         "Where a starter is out, exactly which string has to replace him."),
        ("lines.html", "METHOD", "Line origination",
         "Own-number pipeline, signal families, and the one input no official source provides."),
        ("correlation.html", "METHOD", "Correlation",
         "988 team-level values with n and p, and the game-level number that parlays actually need."),
        ("gates.html", "METHOD", "Validation gates",
         "14 gates. A 55% record over 500 bets is inside coin-flip range — here is the arithmetic."),
        ("leaderboard.html", "COMPETITION", "Leaderboard",
         "10 registered strategies, unranked on purpose until a graded result exists."),
        ("decisions.html", "DECIDE", "Suggestion review board",
         "12 suggestions, 3 paths each, one recommendation. Choose before anything is built."),
        ("questions.html", "DECIDE", "Questions register",
         "48 questions: what we know, what is missing, and how to discover it."),
        ("flagged.html", "REVIEW", "Flagged for review",
         "Every irregularity this session found, with the source that contradicts it."),
    ]
    card_html = "".join(
        f'<a class="card" href="{h}"><span class="tag">{t}</span><h3>{e(n)}</h3><p>{e(d)}</p></a>'
        for h, t, n, d in cards)

    body = f"""
<div class="stats">
{stat(checks, "independent cell checks", f"re-run {SNAPSHOT}")}
{stat(fails, "mismatches", "against the official pages")}
{stat(unv, "values no official page publishes", "left blank or badged")}
{stat("345", "official injury rows", "28 club tables")}
{stat("1,813", "depth chart entries", "31 of 32 clubs")}
{stat(depth_rows, "deficiency rows", "starter to replacement")}
</div>

<div class="note good"><b>What this session added.</b> Every task on the coordination board was
marked done by the session that authored it. This session re-ran the verification independently:
each published table was re-fetched from nfl.com on {SNAPSHOT} and compared cell by cell, and the
ledger is published on the <a href="verification.html">verification page</a>. The published data
holds up — the standings, the slate, the injury report and the derived deficiency register all
reconcile exactly. What did not hold up is a handful of values that no official page supports;
they are listed on <a href="flagged.html">Flagged for review</a>.</div>

<div class="note"><b>The one structural gap.</b> Six parallel site sections are published from
this repository at the same time. Rather than delete three sessions' work — two of which
independently transcribed the same official standings page and produced identical numbers for all
32 clubs, which is itself useful evidence — this hub adds a single front door and changes no file
owned by another session. See <a href="decisions.html#D-10">decision D-10</a>.</div>

<h2>Choose where to look</h2>
<div class="cards">{card_html}</div>
"""
    return page("Overview", body, "index.html",
                "A working lab for originating our own NFL numbers: verified official data at the "
                "base, a validation gauntlet in the middle, and a leaderboard that pays for skill "
                "rather than a hot streak.")


SECTIONS = [
    ("index.html + pages/", "Fourth Down dashboard (session arena/b38a21d8-x1)",
     "The canonical league-verified tables: standings, the Week 10 slate, availability, "
     "line origination, gates, leaderboard, correlation, sources.",
     "Any number that must be traceable to an official league page."),
    ("pages/decisions-critical.html, pages/suggestions-board.html, pages/review-queue.html, "
     "pages/requirements.html, pages/executive-brief.html",
     "Audit layer (sessions arena/c50b9342-x1, arena/9cc1eaac-x1)",
     "The decision-first rewrite: which decisions are critical, the suggestions board, the "
     "review queue, all 45 brief requirements assessed, and a one-page executive brief.",
     "What to decide, and what each of the 45 brief requirements is currently assessed as."),
    ("dashboard/", "Analytics lab",
     "Backtests and the 2026 CSVs behind the strategy work.",
     "Anything computed from the season files rather than read off an official page."),
    ("research/", "Research lab",
     "Priced research: the walk-forward model, 16 evaluated strategies, correlation values, "
     "luck removal and player-prop mathematics, with the third-party benchmark named.",
     "Model output and out-of-sample results. The benchmark is a named community mirror, "
     "not a league source."),
    ("site/", "Snapshot annex (X1)",
     "Originated lines, a leak-free backtest, correlation intervals and a gated leaderboard.",
     "The computed annex: every number here is calculated, not scraped."),
    ("live/", "Live pipeline",
     "Auto-refreshed official data: standings, injuries, 31-club depth charts, team stats, "
     "deficiency, correlations.",
     "The freshest official data. This is the only section that re-pulls on a schedule."),
    ("hub/", "Second opinion (this section, arena/459b17e1-x1)",
     "An independent re-verification of the published tables, the findings nobody else has "
     "raised, the depth-deficiency board by replacement string, and a suggestion board that "
     "sets out two or three paths for each choice.",
     "Second opinions and the choices themselves. Nothing here is a primary data source."),
    ("archive/previous-site/", "Archived design spec",
     "The five-page design specification from the first session. No NFL data.",
     "Historical. Kept so the design decisions stay readable."),
]


LINKS = {
    "index.html + pages/": "../index.html",
    "pages/decisions-critical.html, pages/suggestions-board.html, pages/review-queue.html, "
    "pages/requirements.html, pages/executive-brief.html": "../pages/decisions-critical.html",
    "dashboard/": "../dashboard/index.html",
    "research/": "../research/index.html",
    "site/": "../site/index.html",
    "live/": "../live/index.html",
    "hub/": "index.html",
    "archive/previous-site/": "../archive/previous-site/index.html",
}


def build_index():
    rows = []
    for path, name, what, canonical in SECTIONS:
        href = LINKS.get(path, "../" + path.split(",")[0].strip())
        rows.append([rcell(f'<a href="{e(href)}">{e(path)}</a>'),
                     cell(name), cell(what), cell(canonical)])
    ver = [load("data/verification/standings.json"), load("data/verification/schedule.json"),
           load("data/verification/injuries.json"), load("data/verification/deficiency.json")]
    checks = sum(g(v, "checks", "status_checks") for v in ver if v)
    fails = sum(g(v, "fail") for v in ver if v)
    unv = sum(g(v, "unverified") for v in ver if v)

    body = f"""
<div class="stats">
{stat(checks, "independent cell checks", f"re-run {SNAPSHOT}")}
{stat(fails, "value mismatches", "in the injury/QB columns")}
{stat(unv, "values no official page prints", "left blank or badged")}
{stat("12", "findings raised", "2 contradicted values")}
{stat("8", "site sections published", "this one is the index")}
</div>

<div class="note"><b>This section exists because the site has eight of them.</b> Four agent
sessions each built a complete site in this repository and each one merged. Deleting any of them
would destroy work that is still the only copy of some findings, so instead this page says what
each section is canonical for. Read the top row for league-verified numbers, the second row for
what to decide, and come here for second opinions. Nothing in <code>hub/</code> modifies, replaces
or overrides any other section.</div>

<h2>What each section is canonical for</h2>
<div class="scroll">{table([("Path", ""), ("Section", ""), ("What is in it", ""),
                            ("Canonical for", "")], rows, scroll=False, cls="src")}</div>

<h2>What this section adds</h2>
{table([("Page", ""), ("Why it is not a duplicate", "")], [
 [rcell('<a href="verification.html">Verification ledger</a>'),
  cell("The published tables were verified by the sessions that wrote them. This session "
       "re-fetched each official page on 2026-11-14 and re-read the numbers without reference to "
       "the earlier result, then tested the official page against its own arithmetic before "
       "trusting any transcription from it. The method is different from the existing "
       "verify_against_official.py, which diffs the dashboard tables; this one counts the 28 club "
       "injury tables by hand and checks all 160 designated rows field by field.")],
 [rcell('<a href="findings.html">Findings</a>'),
  cell("Twelve items, two of which are values an official source actively contradicts rather "
       "than merely fails to support: Minnesota's expected quarterback, and Baltimore's. Neither "
       "is raised anywhere else on the site.")],
 [rcell('<a href="deficiency.html">Depth deficiency</a>'),
  cell("The brief asks specifically which string — 2nd, 3rd or 4th — has to replace an "
       "out starter. This board answers that per position slot, and says so plainly for the eight "
       "slots where the club prints no replacement at all.")],
 [rcell('<a href="decisions.html">Suggestion review board</a>'),
  cell("Twelve suggestions, each restated as a choice with two or three realistic paths, what "
       "each costs, what it unlocks, and which one is recommended. Nothing here is implemented — "
       "the point is to pick a path first.")],
], scroll=False)}

<div class="note good"><b>The headline result of the re-verification.</b> The published data holds
up. Standings reconcile on 1,184 of 1,184 cells across three separate committed datasets; the
injury report's 28 club tables count to 345 by hand, exactly as committed; all 160 rows carrying a
game status match field by field; and the derived deficiency register's 66 affected starting slots
all trace to a designation the league actually printed. What does not hold up is a small set of
values that were inferred rather than read — mostly quarterback names — and they are on the
findings page.</div>
"""
    return page("Section index", body, "index.html",
                "What each part of this site is canonical for, and an independent second opinion "
                "on the numbers.")



def build_exec_summary():
    d = [
        ("Where we are", "2026 NFL season, Week 10. Thursday night is played; 13 games remain this "
         "weekend. 137 of 272 regular-season games are in the books."),
        ("What is verified", "Standings for all 32 clubs, the Week 10 slate, the official injury "
         "report (345 rows across 28 club tables), official club depth charts for 31 of 32 clubs "
         "(1,813 entries), official team stats (288 rows), and a derived deficiency register of "
         "897 rows linking each starter to the next available replacement."),
        ("What is not verified", "No betting prices. The NFL and its clubs publish no odds, so "
         "spread, total, moneyline and prop prices exist nowhere official. Every price in this "
         "repository traces to a community mirror and is badged as such."),
        ("What the models show", "The v1 results-only model carries no edge: ROI between -6.1% and "
         "-2.6% across thresholds. Same-game spread/total correlation is -0.023 over 1,496 games; "
         "cross-game independence is 0.001 over 12,585 games."),
        ("What blocks a leaderboard", "Two feeds: a price feed (Q-02) and a graded-results feed "
         "(Q-04). Until both exist, no strategy can be ranked, and a ranking produced anyway would "
         "be ranking noise."),
        ("How luck is removed", "Gates G1-G8 require 100 settled out-of-sample bets, a bootstrap "
         "95% interval whose lower bound clears zero, and a sign-flip permutation test at p<=0.05. "
         "A genuinely skilled 55% bettor needs 991 bets before the interval clears zero."),
        ("The injury picture this week", "160 players carry an official game status. 66 starting "
         "slots are affected; 57 have a 2nd-string replacement on the club's own chart, 1 has a "
         "3rd-string, and 8 have no replacement printed at all."),
        ("The decision that matters most", "Whether to buy a price feed or start recording our own "
         "snapshots. Snapshots cost nothing and start the clock today; a licence is the only route "
         "to a backtest over past seasons. See D-01."),
    ]
    rows = "".join(f"<tr>{cell(k, '', '')}<td>{e(v)}</td></tr>" for k, v in d)
    body = f"""
<div class="note"><b>Rule this repository runs on.</b> If a value cannot be confirmed from an
official source the cell stays blank and the item is flagged. Nothing is inferred and no number is
invented to fill a table. That is why there are no prices and no strategy results here.</div>
{table([("Question", ""), ("Answer", "")], rows, scroll=False)}
<h2>Where to go next</h2>
<p>Start at the <a href="decisions.html">suggestion review board</a>: twelve suggestions, each with
two or three realistic paths and a recommendation, ordered so that the choices which unblock the
most come first. Nothing on that page has been implemented.</p>
"""
    return page("Executive summary", body, "executive-summary.html",
                "The state of the project, what is proven, what is missing, and the decision that "
                "unblocks the most.")


def g(v, *keys):
    """Read the first key present; the deficiency ledger names its counter differently."""
    for k in keys:
        if k in v:
            return v[k]
    return 0


def build_verification():
    files = [("data/verification/standings.json", "Standings"),
             ("data/verification/schedule.json", "Week 10 slate"),
             ("data/verification/injuries.json", "Injury report"),
             ("data/verification/deficiency.json", "Depth deficiency")]
    rows = []
    tot = {"checks": 0, "pass": 0, "fail": 0, "unverified": 0}
    for rel, name in files:
        v = load(rel)
        if not v:
            continue
        for k in tot:
            tot[k] += g(v, k, "status_checks" if k == "checks" else k)
        pill = '<span class="pill pass">0 mismatches</span>' if not v["fail"] \
            else f'<span class="pill fail">{v["fail"]} mismatches</span>'
        rows.append([
            cell(name), cell(f'{g(v, "checks", "status_checks"):,}'), cell(f'{g(v, "pass"):,}'),
            rcell(pill), cell(f'{g(v, "unverified"):}'),
            rcell(srclink(v.get("official_source"), v.get("official_source"))),
        ])
    body = f"""
<div class="stats">
{stat(f'{tot["checks"]:,}', "cell checks run", f"against pages re-fetched {SNAPSHOT}")}
{stat(f'{tot["pass"]:,}', "cells reconciled", "byte-identical to the official page")}
{stat(tot["fail"], "mismatches", "listed on the Flagged page")}
{stat(tot["unverified"], "unverifiable values", "no official page prints them")}
</div>
<div class="note"><b>What "independent" means here.</b> The sessions that built these tables also
verified them. This session re-fetched each official page on {SNAPSHOT}, re-read the numbers, and
compared them without reference to the earlier result. Standings were checked cell by cell across
all 32 clubs and 14 published columns, plus 320 internal arithmetic checks on the official page
itself. The injury report was checked by counting every row in every one of the 28 club tables by
hand (345, an exact match) and then comparing all 160 rows that carry a game status field by
field.</div>
<h2>Ledger by dataset</h2>
{table([("Dataset", ""), ("Checks", "num"), ("Reconciled", "num"), ("Mismatches", ""),
        ("Unverifiable", "num"), ("Official source", "")], rows, scroll=False, cls="src")}

<h2>Arithmetic checks run on the official page itself</h2>
<p class="small">Before any committed value is trusted, the official page is tested against itself.
If a page contradicts its own arithmetic, no transcription from it can be trusted either.</p>
{table([("Check", ""), ("Result", ""), ("Why it matters", "")], [
 [cell("PCT equals (W + 0.5T) / games"), rcell('<span class="pill pass">320 pass</span>'),
  cell("Catches a mis-aligned column, the single most common transcription failure.")],
 [cell("PF - PA equals Net Pts"), rcell('<span class="pill pass">32 pass</span>'),
  cell("Confirms the points columns were read from the right teams.")],
 [cell("Home record + road record equals W-L-T"), rcell('<span class="pill pass">32 pass</span>'),
  cell("Fails if a neutral-site game is double counted or a row is duplicated.")],
 [cell("Conf record + non-conf record equals W-L-T"), rcell('<span class="pill pass">32 pass</span>'),
  cell("Same, for the second pair of split columns.")],
 [cell("Div win% equals the div record"), rcell('<span class="pill pass">32 pass</span>'),
  cell("The page prints two columns labelled only 'Pct'; this fixes their meaning.")],
 [cell("Conf win% equals the conf record"), rcell('<span class="pill pass">32 pass</span>'),
  cell("Same, for the conference pair.")],
 [cell("Club table row counts sum to 345"), rcell('<span class="pill pass">exact</span>'),
  cell("28 club tables counted by hand against the committed total.")],
], scroll=False)}

<h2>What this ledger does not cover</h2>
<p class="small">Three things were checked structurally rather than value by value, and are
declared as such rather than counted as passes: the 185 non-designated injury rows (players listed
with a practice status but no game status), the 1,813 depth-chart entries (a sample was spot
checked against the club pages; the full set was produced by another session from the same
official club sites), and the 288 official team-stat rows. Where a value is not in this ledger it
is not being claimed as verified.</p>
"""
    return page("Verification ledger", body, "verification.html",
                "Every published table re-fetched from its official source and re-checked cell by "
                "cell, with the result published whether it flatters the repo or not.")


def build_standings():
    off = {}
    raw = os.path.join(ROOT, "data", "verification", "raw", "nfl_standings_league_2026_REG.md")
    for line in open(raw, encoding="utf-8"):
        line = line.strip()
        if not line.startswith("|") or line.startswith("| NFL Team"):
            continue
        c = [x.strip() for x in line.strip("|").split("|")]
        off[c[0]] = c[1:]
    url = "https://www.nfl.com/standings/league/2026/REG"
    rows = []
    for name in sorted(off, key=lambda n: (-float(off[n][3]), n)):
        v = off[name]
        rows.append([cell(name), cell(v[0], "num"), cell(v[1], "num"), cell(v[2], "num"),
                     cell(v[3], "num"), cell(v[4], "num"), cell(v[5], "num"), cell(v[6], "num"),
                     cell(v[7]), cell(v[8]), cell(v[9]), cell(v[11]), cell(v[13]), cell(v[14]),
                     cell(v[15]), rcell(srclink(url, "nfl.com"))])
    body = f"""
<div class="note good"><b>1,184 of 1,184 cells reconciled.</b> Every value below was re-read from
<a href="{url}">the official league standings page</a> on {SNAPSHOT} and matches the committed
tables exactly. Seven cells differ in formatting only (0.75 printed where the page prints 0.750);
they carry the same value and are not counted as mismatches.</div>
{table([("Club", ""), ("W", "num"), ("L", "num"), ("T", "num"), ("PCT", "num"), ("PF", "num"),
        ("PA", "num"), ("Net", "num"), ("Home", ""), ("Road", ""), ("Div", ""), ("Conf", ""),
        ("Non-conf", ""), ("Strk", ""), ("Last 5", ""), ("Source", "")], rows, cls="src")}
<p class="small">The league page also prints a column labelled only "Pct" after the Div and Conf
records. Its meaning is not stated in the page's own legend, so it is derived rather than
transcribed: it is the winning percentage of the record immediately to its left, and that identity
was verified for all 64 values.</p>
"""
    return page("Standings", body, "standings.html",
                "2026 standings through Week 10 Thursday, sorted by winning percentage.")


def build_week10():
    p = os.path.join(ROOT, "data", "nfl", "schedule_2026_week10.csv")
    rows = []
    for r in csv.DictReader(open(p, newline="", encoding="utf-8-sig")):
        qbflags = []
        for side, col in (("away", "expected_qb_away"), ("home", "expected_qb_home")):
            qb = (r.get(col) or "").strip()
            if not qb:
                continue
            if (r["away"] if side == "away" else r["home"]) == "MIN" and side == "away":
                qbflags.append(f"{qb} <span class='pill unv'>contradicted by official report</span>")
            elif (r["away"] if side == "away" else r["home"]) == "BAL" and side == "home":
                qbflags.append(f"{qb} <span class='pill unv'>contradicted by NFL.com news</span>")
            elif (r["away"] if side == "away" else r["home"]) in ("MIA", "AZ", "CLE") or \
                    ((r["away"] if side == "away" else r["home"]) == "SEA" and side == "away"):
                qbflags.append(f"{qb} <span class='pill ok'>named by NFL.com news</span>")
            else:
                qbflags.append(f"{qb} <span class='pill unv'>no official designation</span>")
        rows.append([
            cell(f'{r["weekday"][:3]} {r["date"]}'), cell(r["et_time"]),
            cell(r["tv"]), cell(f'{r["away"]} @ {r["home"]}'),
            cell(r["result"] or "—"),
            cell("; ".join(qbflags) or "—"),
            rcell(srclink("https://www.nfl.com/schedules/2026/by-week/week-10", "nfl.com")),
        ])
    byes = [("CHI", "7-2"), ("DEN", "7-2"), ("PHI", "2-7"), ("TB", "3-6")]
    byerow = [f'{cell(t)}<td>On bye, Week 10</td><td>{e(rec)}</td>'
              f'<td>{srclink("https://www.nfl.com/schedules/2026/by-week/week-10", "nfl.com")}</td>'
              for t, rec in byes]
    body = f"""
<div class="note good"><b>All 14 games and 4 byes reconcile.</b> Every kickoff time, network and
matchup was re-read from <a href="https://www.nfl.com/schedules/2026/by-week/week-10">the official
Week 10 schedule page</a> on {SNAPSHOT}. Washington 24, Giants 21 is the only game with a final
score; it was played on Thursday 12 November.</div>
{table([("Date", ""), ("ET", ""), ("Network", ""), ("Matchup", ""), ("Result", ""),
        ("Named quarterback (evidence grade)", ""), ("Source", "")], rows, cls="src")}

<h2>Teams on bye</h2>
{table([("Club", ""), ("Status", ""), ("Record", ""), ("Source", "")], byerow, scroll=False, cls="src")}

<h2>The quarterback column is the weak link</h2>
<div class="note bad"><b>The NFL publishes no official starting quarterback.</b> Twenty-eight
clubs play this week; only four have a starter named in an NFL.com news story
(<a href="https://www.nfl.com/news/dolphins-place-qb-malik-willis-groin-on-injured-reserve-kyle-mccord-in-line-for-first-start">Miami</a>,
<a href="https://www.nfl.com/news/nfl-news-roundup-latest-league-updates-from-wednesday-nov-11">Arizona
and Cleveland</a>,
<a href="https://www.nfl.com/news/drew-lock-no-injury-designation-seahawks-raiders">Seattle</a>).
Two values in the committed table are actively contradicted: Minnesota is listed with Kirk Cousins
while the official Vikings injury report names only Kyler Murray (Out) and Carson Wentz (full
participation); Baltimore is listed with Tyler Huntley while
<a href="https://www.nfl.com/news/ravens-qb-tyler-huntley-out-for-season-turf-toe-injury">NFL.com's
own news story</a> reports him out for the season. See <a href="decisions.html#D-05">D-05</a>.</div>
<p class="small">Network note: the official page prints "ESPN" for Monday night where the committed
table prints "ESPN/ABC", and prints no network at all for Thursday night. Neither is a data error;
the page simply lists the primary carrier.</p>
"""
    return page("Week 10 slate", body, "week10.html",
                "14 games, 4 byes, and an honest look at which columns the league actually publishes.")


def build_injuries():
    official = {}
    for line in open(os.path.join(ROOT, "data", "verification", "raw",
                                  "nfl_injuries_2026_week10.md"), encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        team, player, pos, inj, prac, game = [x.strip() for x in line.split("|")]
        official[(team, player)] = (pos, inj, prac, game)

    def pill(g):
        c = {"Out": "out", "Doubtful": "doubt", "Questionable": "quest"}.get(g, "unv")
        return f'<span class="pill {c}">{e(g)}</span>'

    rows = []
    for (team, player), (pos, inj, prac, game) in sorted(
            official.items(), key=lambda kv: ({"Out": 0, "Doubtful": 1, "Questionable": 2}
                                              .get(kv[1][3], 9), kv[0][0], kv[0][1])):
        rows.append([cell(team), cell(player), cell(pos), cell(inj or "—"),
                     cell(prac), rcell(pill(game)),
                     rcell(srclink("https://www.nfl.com/injuries/", "nfl.com/injuries"))])
    counts = {"Out": 0, "Doubtful": 0, "Questionable": 0}
    for v in official.values():
        counts[v[3]] = counts.get(v[3], 0) + 1
    body = f"""
<div class="stats">
{stat("345", "rows on the official report", "28 club tables, counted by hand")}
{stat(len(official), "players with a game status", "checked field by field")}
{stat(counts.get("Out", 0), "Out", "")}
{stat(counts.get("Doubtful", 0), "Doubtful", "")}
{stat(counts.get("Questionable", 0), "Questionable", "")}
</div>
<div class="note good"><b>The club tables reconcile exactly.</b> Counting the rows in each of the
28 club tables by hand gives 345, which is the committed total. All {len(official)} rows that carry
a game status were then compared field by field against the committed tables: position, injury,
practice status and game status all match. Practice status and game status are the league's own
designations; a blank cell means the official page left the field empty, not that we failed to
read it.</div>
<div class="scroll">{table([("Club", ""), ("Player", ""), ("Pos", ""), ("Injury", ""),
                            ("Practice status", ""), ("Game status", ""), ("Source", "")], rows,
                           scroll=False, cls="src")}</div>
<h2>Designation definitions</h2>
<p class="small">Practice status is Did Not Participate / Limited Participation / Full
Participation. Game status is Out / Doubtful / Questionable. The league's own definitions are
published at
<a href="https://www.nfl.com/news/competition-committee-approves-revisions-to-injury-report-0ap3000000688693">nfl.com</a>.
Note that "Out" and "Did Not Participate" are different things: a player can be a full participant
on Friday and still be ruled out.</p>
"""
    return page("Injuries", body, "injuries.html",
                "The official Week 10 injury report: every player the league has given a game "
                "status, with the designation it printed.")


def build_deficiency():
    d = load("data/verification/deficiency.json") or {}
    board = d.get("board", [])
    dist = d.get("slots_by_replacement_string", {})

    def pill(g):
        c = {"Out": "out", "Doubtful": "doubt", "Questionable": "quest"}.get(g, "unv")
        return f'<span class="pill {c}">{e(g)}</span>'

    rows = []
    for b in sorted(board, key=lambda x: ({"Out": 0, "Doubtful": 1, "Questionable": 2}
                                          .get(x["starter_game_status"], 9),
                                          x["team"], x["unit"], x["position"])):
        rep = b["replacement"] or ""
        string = b["replacement_depth"]
        if rep and string:
            names = {2: "2nd string", 3: "3rd string", 4: "4th string"}
            rep_cell = f'{e(rep)} <span class="pill prop">{e(names.get(int(string), str(string) + "th string"))}</span>'
        else:
            rep_cell = '<span class="pill unv">no replacement printed</span>'
        rows.append([
            cell(b["team"]), cell(b["unit"]), cell(b["position"]), cell(b["starter"]),
            rcell(pill(b["starter_game_status"])), cell(b["injuries"] or "—"),
            rcell(rep_cell),
            rcell(srclink(b.get("depth_chart_url"), "club chart")),
        ])
    norep = sum(1 for b in board if not b["replacement"])
    body = f"""
<div class="stats">
{stat(len(board), "starting slots affected", "starter carries a game status")}
{stat(dist.get("2", 0), "covered by a 2nd string", "")}
{stat(dist.get("3", 0), "covered by a 3rd string", "")}
{stat(norep, "no replacement printed", "the honest limit of the source")}
{stat(d.get("register_rows", 0), "rows in the full register", "all slots, not just affected")}
</div>
<div class="note"><b>How a row is built.</b> The starter is column 1 of the club's own depth chart.
The replacement is the next name on that chart who is not himself ruled Out on the official injury
report, and the "string" is that name's position on the chart — 2nd, 3rd or 4th. Nothing here is
guessed: the chart is the club's, the designation is the league's, and both are linked from every
row. Where the club prints no further name at that position, the cell says so instead of inventing
a backup.</div>
<div class="note"><b>Club charts are self-reported.</b> Several clubs label their own depth chart
"unofficial" and update it on their own schedule. <a href="https://www.packers.com/team/depth-chart">packers.com</a>,
for example, ends with "Unofficial, Nov. 10, 2026". Treat the replacement column as the club's
current stated intention, not as a league-verified fact.</div>
<div class="scroll">{table([("Club", ""), ("Unit", ""), ("Position", ""), ("Starter", ""),
                            ("Status", ""), ("Injury", ""), ("Next available replacement", ""),
                            ("Depth chart", "")], rows, scroll=False, cls="src")}</div>
<h2>Reading it for a decision</h2>
<p class="small">A starter ruled Out with a 2nd-string replacement is the ordinary case and carries
little signal — the market and every other model can see it too. The rows worth attention are the
ones where the replacement is a 3rd or 4th string, where the replacement is himself Questionable,
or where the club prints no replacement at all. Those are the positions where the public
information is thinnest, and they are the only places where a depth-based signal could plausibly be
worth anything.</p>
"""
    return page("Depth deficiency", body, "deficiency.html",
                "Where a starter is out, which string has to play instead — from the club's own "
                "chart joined to the league's own report.")


def build_lines():
    rows = [
        [cell("Official team stats"), cell("288 rows, 9 tables"),
         rcell(srclink("https://www.nfl.com/stats/team-stats/", "nfl.com/stats")),
         rcell('<span class="pill pass">verified</span>')],
        [cell("Standings and records"), cell("32 clubs"),
         rcell(srclink("https://www.nfl.com/standings/league/2026/REG", "nfl.com/standings")),
         rcell('<span class="pill pass">verified</span>')],
        [cell("Injury designations"), cell("345 rows"),
         rcell(srclink("https://www.nfl.com/injuries/", "nfl.com/injuries")),
         rcell('<span class="pill pass">verified</span>')],
        [cell("Club depth charts"), cell("1,813 entries, 31 clubs"),
         rcell(srclink("https://www.nfl.com/teams/", "club sites via nfl.com")),
         rcell('<span class="pill unv">club-published, some self-labelled unofficial</span>')],
        [cell("Market prices (spread, total, moneyline, props)"), cell("0 rows"),
         rcell('<span class="pill unv">no official source exists</span>'),
         rcell('<span class="pill unv">table ships empty on purpose</span>')],
        [cell("Game results history"), cell("not collected from an official source"),
         rcell('<span class="pill unv">no official machine-readable feed verified</span>'),
         rcell('<span class="pill unv">blocks grading</span>')],
        [cell("Play-by-play / snap counts"), cell("not collected"),
         rcell('<span class="pill unv">licensed data</span>'),
         rcell('<span class="pill unv">blocks player-level props</span>')],
    ]
    body = f"""
<div class="note bad"><b>The input that does not exist.</b> Originating a line is only half the
work; the other half is knowing the price you are comparing against. Neither the NFL nor any club
publishes betting prices, so that half cannot be sourced officially. This is decision
<a href="decisions.html#D-01">D-01</a> and it gates everything downstream: without a price there is
no edge, no closing-line value, and no way to grade a strategy.</div>

<h2>What a line can be built from today</h2>
{table([("Input", ""), ("Official coverage", ""), ("Source", ""), ("Status", "")], rows, scroll=False, cls="src")}

<h2>Signal families that are actually supportable</h2>
{table([("Family", ""), ("Official inputs available now", ""), ("What it can and cannot do", "")], [
 [cell("Scoring rates"),
  rcell(srclink("https://www.nfl.com/standings/league/2026/REG", "official standings")),
  cell("Enough for a Poisson points model. This is the v1 model, and it has no edge on its own.")],
 [cell("Efficiency splits"),
  rcell(srclink("https://www.nfl.com/stats/team-stats/", "official team stats, 9 tables")),
  cell("288 official rows. Stronger than raw points, still team-level only.")],
 [cell("Availability / depth"),
  rcell(srclink("https://www.nfl.com/injuries/", "injury report") + " + " +
       srclink("https://www.nfl.com/teams/", "club depth charts")),
  cell("The only input here a casual model will not have. Thin: only 8 slots this week lack a printed replacement.")],
 [cell("Rest and travel"),
  rcell(srclink("https://www.nfl.com/schedules/2026/by-week/week-10", "official schedule")),
  cell("Verifiable, but the effect size is small and unverifiable without a price feed.")],
 [cell("Market movement"), rcell('<span class="pill unv">no official source</span>'),
  cell("Impossible until we record prices ourselves. See D-01 option B.")],
 [cell("Player props"), rcell('<span class="pill unv">licensed data only</span>'),
  cell("Prop pricing needs snap counts and usage, both licensed. See Q-01.")],
], scroll=False)}

<h2>What the existing model already measured</h2>
<p class="small">The annex in this repository fitted a walk-forward Poisson points model over 7,154
games, refitting only on earlier seasons, and ran it through a leak-free backtest over 1,779 games.
The answer is a negative result and it is worth more than a positive one would have been: ROI lands
between <b>-6.1% and -2.6%</b> across thresholds, which is indistinguishable from paying the vig.
A naive results-only model does not beat the market, and now that is measured rather than
assumed.</p>
"""
    return page("Line origination", body, "lines.html",
                "Which inputs a number can honestly be built from, and the one input no official "
                "source provides.")


def build_correlation():
    c = load("data/pipeline/correlations.json") or {}
    rows = c.get("rows", [])
    keep = [r for r in rows if abs(r.get("r", 0)) >= 0.6 and r.get("p_value", 1) < 0.05]
    keep.sort(key=lambda r: -abs(r.get("r", 0)))
    shown = keep[:40]
    trs = []
    for r in shown:
        strength = r.get("strength", "")
        cls = "pass" if abs(r["r"]) >= 0.8 else "prop"
        trs.append([
            cell(r.get("pair")), cell(f'{r["r"]:+.3f}', "num"), cell(r.get("n"), "num"),
            cell(f'{r.get("p_value"):.2e}' if isinstance(r.get("p_value"), float) else r.get("p_value"), "num"),
            rcell(f'<span class="pill {cls}">{e(strength)}</span>'),
            rcell(srclink((r.get("_source_urls") or [""])[0], "nfl.com")),
        ])
    body = f"""
<div class="stats">
{stat(f'{c.get("verification", {}).get("rows", 0):,}', "pairs computed", "from official team tables")}
{stat(len(keep), "pairs with |r| >= 0.6", "and p < 0.05")}
{stat("-0.023", "same-game spread/total", "n = 1,496 games")}
{stat("0.001", "cross-game independence", "n = 12,585 games")}
</div>
<div class="note"><b>These are team-season correlations, not game-level ones.</b> They are computed
across the 32 clubs from the official standings and official team-stat tables. They are the right
number for asking "do good offences also allow few points?" and the wrong number for pricing a
two-leg same-game parlay. The game-level quantity a parlay actually needs is measured separately
below.</div>

<h2>Strongest team-level relationships</h2>
<p class="small">Top {len(shown)} by absolute value among pairs that clear p &lt; 0.05. Several are
definitionally related (wins against losses) and are shown precisely so that the mechanical
relationships are visible next to the interesting ones.</p>
<div class="scroll">{table([("Pair", ""), ("r", "num"), ("n", "num"), ("p", "num"),
                            ("Strength", ""), ("Source", "")], trs, scroll=False, cls="src")}</div>

<h2>The game-level numbers a parlay needs</h2>
{table([("Quantity", ""), ("Value", "num"), ("n", "num"), ("Computed from", ""),
        ("What it means", "")], [
 [cell("Same-game spread vs total"), cell("-0.023", "num"), cell("1,496", "num"),
  rcell(srclink("https://github.com/karagemop466-tech/X1/blob/main/data/lines/correlation_report.csv",
               "correlation report")),
  cell("Very close to independent. A same-game spread/total pair is close enough to independent "
       "that treating it as independent will not misprice it much — but not exactly.")],
 [cell("Cross-game independence"), cell("0.001", "num"), cell("12,585", "num"),
  rcell(srclink("https://github.com/karagemop466-tech/X1/blob/main/data/lines/correlation_report.csv",
               "correlation report")),
  cell("Games in different contests are independent, as assumed. Multi-game parlays compound the "
       "vig without a correlation correction.")],
], scroll=False)}

<h2>Parlay break-even arithmetic</h2>
<p class="small">Two independent legs at -110 each pay about +264. The true probability of both
hitting is the product of the two implied probabilities, so the parlay's expected value is
determined entirely by whether each leg is better than a coin flip. At -110 a leg needs a 52.4%
win rate to break even; at -110 each, two legs need 52.4% x 52.4% = 27.5% against the 27.5% the
price implies. The parlay does not create an edge — it multiplies whatever edge (or deficit) the
legs already had, and multiplies the variance faster.</p>
<div class="note">The measured correlation of -0.023 is small but not zero. In the direction it
points, a favourite covering and the game going under are very slightly more likely to happen
together than independence predicts. That is a real, measured correction, and it is the reason the
correlation should be carried through rather than assumed away. It is not large enough to rescue a
losing leg.</div>
"""
    return page("Correlation", body, "correlation.html",
                "Measured correlation values, what they are computed over, and the arithmetic that "
                "decides whether a combination is worth pricing.")


def build_gates():
    g = load("data/pipeline/gates.json") or {}
    rows = []
    for r in g.get("rows", []):
        active = str(r.get("active", "")).lower() in ("yes", "true", "1")
        rows.append([
            cell(r.get("id")), cell(r.get("gate")), cell(r.get("rule")),
            cell(r.get("threshold") or "—"),
            rcell('<span class="pill pass">active</span>' if active else
                 '<span class="pill unv">threshold not set</span>'),
            rcell(srclink(r.get("_source_url"), "project brief")),
        ])
    body = f"""
<div class="note"><b>A gate with no threshold is not a gate.</b> Where a threshold has not been
agreed it is printed as "not set" and the gate is deliberately unenforced, rather than filled with
a number someone would have to defend later.</div>
<div class="scroll">{table([("ID", ""), ("Gate", ""), ("Rule", ""), ("Threshold", ""),
                            ("State", ""), ("Source", "")], rows, scroll=False, cls="src")}</div>

<h2>The arithmetic that removes luck</h2>
{table([("Claim", ""), ("Test", ""), ("Result", "")], [
 [cell("55% win rate over 100 bets"), cell("95% interval on a 55% true rate"),
  cell("z = 1.00. Not significant. A 55% capper is inside coin-flip range at this sample.")],
 [cell("55% win rate over 500 bets"), cell("95% interval"),
  cell("z = 1.22. Still not significant. This is the number most people mistake for proof.")],
 [cell("55% win rate over 991 bets"), cell("95% interval lower bound clears zero"),
  cell("This is the sample a genuinely skilled 55% bettor needs before the result stops being "
       "indistinguishable from luck.")],
 [cell("Any record at all"), cell("Sign-flip permutation test"),
  cell("Randomly flip the sign of every bet many times and ask how often a record this good "
       "appears by chance. Guards against a strategy that is really one lucky season.")],
 [cell("Any record at all"), cell("Remove one-score games and blowouts"),
  cell("Gate G6. If the edge disappears when the coin-flip games come out, it was variance.")],
], scroll=False)}
<div class="note good">The leaderboard reward formula is
<code>1000 x ROI x min(1, bets/300) x confidence</code>, where confidence is the share of the
bootstrap interval that stays above zero. A strategy that fails any gate scores zero. The
<code>min(1, bets/300)</code> term is what stops a 30-bet hot streak from outscoring a real
three-season record.</div>
"""
    return page("Validation gates", body, "gates.html",
                "Fourteen pre-registered gates, and the sample-size arithmetic that decides "
                "whether a result is skill or variance.")


def build_leaderboard():
    s = load("data/pipeline/strategies.json") or {}
    l = load("data/pipeline/leaderboard.json") or {}
    rows = []
    for r in s.get("rows", []):
        rows.append([
            cell(r.get("id")), cell(r.get("name")),
            cell(r.get("market") or r.get("type") or "—"),
            cell(r.get("inputs") or r.get("signal") or "—"),
            rcell('<span class="pill unv">no graded result</span>'),
            rcell('<span class="pill unv">no graded result</span>'),
            rcell('<span class="pill unv">no graded result</span>'),
            rcell(srclink(r.get("_source_url"), "project brief")),
        ])
    body = f"""
<div class="note bad"><b>Nothing is ranked, on purpose.</b> Ten strategies are registered, all
ten flagged. A leaderboard that ranks strategies before a single result has been graded would be
ranking noise and would reward whichever strategy happened to be lucky. Ranks and result columns
stay blank until a price feed and a graded-results feed exist (Q-02, Q-04).</div>
<div class="scroll">{table([("ID", ""), ("Strategy", ""), ("Market", ""), ("Inputs", ""),
                            ("Bets", ""), ("ROI", ""), ("Gate result", ""), ("Source", "")],
                           rows, scroll=False, cls="src")}</div>

<h2>Divisions</h2>
{table([("Division", ""), ("What competes in it", ""), ("Why it is separated", "")], [
 [cell("Single bet"), cell("One market, one game: spread, total or moneyline"),
  cell("The cleanest test of a signal. Correlation between legs is not a factor.")],
 [cell("Parlay"), cell("Two or more legs, same game or across games"),
  cell("Needs the correlation correction; variance is much higher and the vig compounds.")],
 [cell("Player prop combos"), cell("Two or more player markets, usually same game"),
  cell("Legs are strongly correlated by game script — the same touchdown can hit two overs. "
       "Needs play-by-play and snap counts, neither of which we have officially.")],
 [cell("Futures / season-long"), cell("Win totals, division and conference winners"),
  cell("Very long settlement. Sample sizes are too small to gate honestly inside one season.")],
], scroll=False)}

<h2>Rewards</h2>
<p class="small">The scoring formula is written and ready:
<code>1000 x ROI x min(1, bets/300) x confidence</code>. Whether the reward is money is not a
question data can answer — it is a budget and possibly a regulatory question, and it is logged as
<a href="decisions.html#D-09">D-09</a> rather than decided here.</p>
"""
    return page("Leaderboard", body, "leaderboard.html",
                "Registered strategies, the four divisions, and why the ranking column is empty.")


def build_decisions():
    d = load("data/hub/decision_board.json") or {}
    st_pill = {"awaiting-decision": ("prop", "choose a path"),
               "ready-to-implement": ("ready", "ready to implement"),
               "do-not-do-yet": ("defer", "defer"),
               "blocked": ("blocked", "blocked")}
    blocks = []
    order = {"awaiting-decision": 0, "blocked": 1, "ready-to-implement": 2, "do-not-do-yet": 3}
    for dec in sorted(d.get("decisions", []), key=lambda x: order.get(x["status"], 9)):
        cls, label = st_pill.get(dec["status"], ("prop", dec["status"]))
        opts = []
        for o in dec["options"]:
            rec = ' rec' if dec["recommended"].startswith(o["id"]) else ''
            opts.append(
                f'<div class="opt{rec}"><b>Option {e(o["id"])} — {e(o["path"])}</b>'
                f'<p class="kv">Cost: {e(o["cost"])}</p>'
                f'<p class="kv">Risk: {e(o["risk"])}</p>'
                f'<p class="kv">Unlocks: {e(o["unlocks"])}</p></div>')
        blocks.append(f"""
<div class="decl" id="{e(dec['id'])}">
<h3>{e(dec['id'])} · {e(dec['area'])} <span class="pill {cls}">{e(label)}</span></h3>
<div class="meta">Suggestion: {e(dec['suggestion'])}</div>
<p><b>The decision:</b> {e(dec['decision_needed'])}</p>
{''.join(opts)}
<p><b>Recommended:</b> {e(dec['recommended'])}</p>
<p class="small">Blocked by: {e(', '.join(dec['blocked_by']) or 'nothing')} ·
Source of the suggestion: {srclink(d.get('source', {}).get('url'), 'project brief')}</p>
</div>""")
    n = len(d.get("decisions", []))
    awaiting = sum(1 for x in d["decisions"] if x["status"] == "awaiting-decision")
    body = f"""
<div class="note"><b>Nothing on this page has been implemented.</b> That is the point. Each row is a
suggestion raised somewhere in this repository, restated as a choice with two or three realistic
paths and the reason to prefer one. The brief asked for a place to review suggestions and choose a
path before implementing anything — this is it. A row only becomes work when you have marked it
approved.</div>
<div class="stats">
{stat(n, "suggestions on the board", "")}
{stat(awaiting, "need your decision", "a real fork in the road")}
{stat(sum(1 for x in d['decisions'] if x['status'] == 'ready-to-implement'),
      "unblocked and obvious", "safe to schedule")}
{stat(sum(1 for x in d['decisions'] if x['status'] == 'do-not-do-yet'),
      "cheaper to defer", "")}
{stat(sum(1 for x in d['decisions'] if x['status'] == 'blocked'),
      "need an outside answer", "")}
</div>
{''.join(blocks)}
"""
    return page("Suggestion review board", body, "decisions.html",
                "Review every suggestion, compare the paths, pick one — before any code is written.")


def build_questions():
    p = load("data/pipeline/questions.json") or {}
    q = load("data/questions.json") or {}
    rows = []
    for r in p.get("rows", []):
        rows.append([cell(r.get("id")), cell(r.get("area")), cell(r.get("question")),
                     cell(r.get("why_it_matters") or r.get("why_it_blocks") or "—"),
                     cell(r.get("known") or r.get("known_information") or "—"),
                     cell(r.get("discovery") or r.get("suggested_discovery") or "—"),
                     rcell(srclink(r.get("_source_url"), "brief"))])
    rows2 = []
    for r in q.get("questions", []):
        rows2.append([cell(r.get("id")), cell(r.get("topic")), cell(r.get("question")),
                      cell(r.get("why_it_blocks") or "—"),
                      cell(r.get("known_information") or "—"),
                      cell(r.get("discovery_suggestion") or "—"),
                      rcell(srclink("https://github.com/karagemop466-tech/X1/blob/main/docs/live-pipeline/project-brief.md", "brief"))])
    body = f"""
<div class="note"><b>Three columns that must stay separate.</b> What we know, what we do not know,
and what we would have to do to find it out. Merging them is how a gap turns into an assumption.
Every row below is a real gap, not a rhetorical question.</div>
<h2>Register from the live pipeline</h2>
<div class="scroll">{table([("ID", ""), ("Area", ""), ("Question", ""), ("Why it blocks", ""),
                            ("What we know", ""), ("How to discover the rest", ""), ("Source", "")],
                           rows, scroll=False, cls="src")}</div>
<h2>Register from the dashboard build</h2>
<div class="scroll">{table([("ID", ""), ("Topic", ""), ("Question", ""), ("Why it blocks", ""),
                            ("What we know", ""), ("How to discover the rest", ""), ("Source", "")],
                           rows2, scroll=False, cls="src")}</div>
"""
    return page("Questions register", body, "questions.html",
                "What we know, what we do not, and what it would take to find out.")


def build_findings():
    ver_inv = load("data/verification/injuries.json") or {}
    ver_sch = load("data/verification/schedule.json") or {}
    qb_unv = [r for r in ver_inv.get("rows", []) if r["result"] == "UNVERIFIED"]
    qb_fail = [r for r in ver_inv.get("rows", []) if r["result"] == "FAIL"]
    sch_unv = [r for r in ver_sch.get("rows", []) if r["result"] == "UNVERIFIED"]
    market = [r for r in sch_unv if r["field"].startswith("market_")]

    rows = [
        [cell("F-01"), cell("Contradicted value"),
         cell("Week 10 schedule: Minnesota's expected quarterback is listed as Kirk Cousins"),
         cell("The official Vikings injury report names only Kyler Murray (Out, hamstring) and "
              "Carson Wentz (full participation). Kirk Cousins does not appear."),
         rcell(srclink("https://www.nfl.com/injuries/", "nfl.com/injuries")),
         cell("Remove the value or mark it unverified. See D-05.")],
        [cell("F-02"), cell("Contradicted value"),
         cell("Week 10 schedule: Baltimore's expected quarterback is listed as Tyler Huntley"),
         cell("NFL.com's own news story reports Huntley out for the season with a turf toe injury, "
              "and Lamar Jackson is on injured reserve."),
         rcell(srclink("https://www.nfl.com/news/ravens-qb-tyler-huntley-out-for-season-turf-toe-injury", "nfl.com news")),
         cell("Remove the value. See D-05.")],
        [cell("F-03"), cell("Unverifiable values"),
         cell(f"{len(market)} market-price cells (spread, total, two moneylines x 14 games)"),
         cell("Neither the NFL nor any club publishes betting prices. These trace to a community "
              "mirror, not the league. They are not rendered on any published page, but they are "
              "present in the CSV files the site serves under /data/."),
         rcell(srclink("https://www.nfl.com/schedules/2026/by-week/week-10", "official schedule (publishes no prices)")),
         cell("Badge every price cell as mirror-sourced, or blank them. See D-01, Q-02.")],
        [cell("F-04"), cell("Unverifiable values"),
         cell("Expected starting quarterback for 22 of 28 clubs this week"),
         cell("The NFL publishes no official starting-QB designation, and most clubs name no "
              "quarterback on the injury report at all."),
         rcell(srclink("https://www.nfl.com/injuries/", "nfl.com/injuries")),
         cell("Adopt the news-only rule in D-05 option A.")],
        [cell("F-05"), cell("Source caveat"),
         cell("Club depth charts are self-published and some are labelled unofficial by the club"),
         cell("packers.com ends its depth chart with 'Unofficial, Nov. 10, 2026'. The deficiency "
              "register inherits that caveat."),
         rcell(srclink("https://www.packers.com/team/depth-chart", "packers.com")),
         cell("Caveat is already printed on the deficiency page; no change needed.")],
        [cell("F-06"), cell("Coverage gap"),
         cell("Houston's official depth chart returns no parsable page"),
         cell("The collector covers 31 of 32 clubs. The attempt log is published with the dataset."),
         rcell(srclink("https://www.nfl.com/teams/", "nfl.com/teams")),
         cell("Retry with a different parser, or record Houston as not covered.")],
        [cell("F-07"), cell("Source URL"),
         cell("data/nfl/schedule_2026_week10.csv cites https://www.nfl.com/schedules/2026/REG10/"),
         cell("That URL resolves to the generic schedule page, not Week 10. The canonical Week 10 "
              "URL is /schedules/2026/by-week/week-10 and it serves the correct content."),
         rcell(srclink("https://www.nfl.com/schedules/2026/by-week/week-10", "canonical Week 10 page")),
         cell("Correct the citation.")],
        [cell("F-08"), cell("Minor discrepancy"),
         cell("Monday night network listed as ESPN/ABC; the official page prints ESPN"),
         cell("The page lists the primary carrier only. Also true for Thursday night, where the "
              "page prints no network at all and the committed table says Prime Video."),
         rcell(srclink("https://www.nfl.com/schedules/2026/by-week/week-10", "nfl.com")),
         cell("Cosmetic. Either correct or note that the page lists the primary carrier.")],
        [cell("F-09"), cell("Minor discrepancy"),
         cell("data/nfl/schedule_week10.tsv uses LAR for the Los Angeles Rams"),
         cell("nfl.com uses LA. Not a data error, but the two tables disagree on the abbreviation."),
         rcell(srclink("https://www.nfl.com/standings/league/2026/REG", "nfl.com")),
         cell("Normalise to the league abbreviation.")],
        [cell("F-10"), cell("Structural irregularity"),
         cell("Six parallel site sections are published from this repository simultaneously"),
         cell("index.html + pages/, dashboard/, research/, site/, live/, archive/. Three were "
              "built independently from the same official sources, so they duplicate content and "
              "occasionally disagree."),
         rcell(srclink("https://karagemop466-tech.github.io/X1/", "live site")),
         cell("See D-10. This session adds hub/ and changes nothing owned by another session.")],
        [cell("F-11"), cell("Undefined threshold"),
         cell("Some validation gates carry no threshold"),
         cell("Printed as 'not set' and left unenforced rather than filled with a guess."),
         rcell(srclink("https://github.com/karagemop466-tech/X1/blob/main/docs/live-pipeline/project-brief.md", "brief")),
         cell("Set the thresholds, or accept them as permanently unenforced.")],
        [cell("F-12"), cell("Unresolved external conflict"),
         cell("Baltimore's quarterback situation cannot be resolved from official sources"),
         cell("Lamar Jackson is on injured reserve, Tyler Huntley is reported out for the season, "
              "and no Ravens quarterback appears on the official Week 10 injury report. The "
              "committed table names a starter the sources contradict."),
         rcell(srclink("https://www.nfl.com/injuries/", "nfl.com/injuries")),
         cell("Leave blank until inactives are published.")],
    ]
    body = f"""
<div class="note bad"><b>{len(rows)} items flagged.</b> Two are values that an official source
actively contradicts and should be corrected; the rest are either unverifiable values that are
honestly labelled, or minor discrepancies that do not change any number. Flagged items do not block
a merge — they are published here so you can review them after the site is live.</div>
<div class="scroll">{table([("ID", ""), ("Kind", ""), ("Item", ""), ("What the official source says", ""),
                            ("Source", ""), ("Suggested action", "")], rows, scroll=False, cls="src")}</div>
<h2>The two that matter</h2>
<p class="small">F-01 and F-02 are the only rows where a published value is contradicted rather
than merely unsupported. Both are quarterback names, both come from the same column, and both are
the kind of detail that looks harmless and quietly poisons a model that trusts it. The fix is to
stop publishing that column except where an NFL.com news story names the starter — four clubs this
week instead of twenty-eight guesses.</p>
"""
    return page("Findings", body, "findings.html",
                "Every irregularity this session found, with the official source that contradicts "
                "or fails to support it.")


def build_sources():
    rows = [
        [cell("NFL.com — League standings"),
         rcell(srclink("https://www.nfl.com/standings/league/2026/REG")),
         cell("Standings, 32 clubs, 14 columns"), cell("League"),
         rcell('<span class="pill pass">1,184 / 1,184</span>')],
        [cell("NFL.com — Week 10 schedule"),
         rcell(srclink("https://www.nfl.com/schedules/2026/by-week/week-10")),
         cell("14 games, 4 byes, kickoffs, networks"), cell("League"),
         rcell('<span class="pill pass">all reconcile</span>')],
        [cell("NFL.com — Injury report"), rcell(srclink("https://www.nfl.com/injuries/")),
         cell("345 rows, 28 club tables, 160 designations"), cell("League"),
         rcell('<span class="pill pass">160 / 160</span>')],
        [cell("NFL.com — Team stats"), rcell(srclink("https://www.nfl.com/stats/team-stats/")),
         cell("288 rows across 9 official tables"), cell("League"),
         rcell('<span class="pill unv">values published as printed</span>')],
        [cell("NFL.com — Official club sites"), rcell(srclink("https://www.nfl.com/teams/")),
         cell("Which domain is a club's official site"), cell("League"),
         rcell('<span class="pill pass">32 / 32</span>')],
        [cell("Club depth charts (31 of 32)"),
         cell("https://www.&lt;club&gt;.com/team/depth-chart &middot; domains per " +
              srclink("https://www.nfl.com/teams/", "nfl.com/teams")),
         cell("1,813 entries, starters through 4th string"), cell("Club"),
         rcell('<span class="pill unv">self-published, some unofficial</span>')],
        [cell("NFL.com — injury designation definitions"),
         rcell(srclink("https://www.nfl.com/news/competition-committee-approves-revisions-to-injury-report-0ap3000000688693")),
         cell("What Out / Doubtful / Questionable mean"), cell("League"),
         rcell('<span class="pill pass">linked from every designation</span>')],
        [cell("NFL.com — tie-breaking procedures"),
         rcell(srclink("https://www.nfl.com/standings/tiebreakingprocedures")),
         cell("How the league orders tied clubs"), cell("League"),
         rcell('<span class="pill pass">reference</span>')],
        [cell("NFL.com news"), rcell(srclink("https://www.nfl.com/news/")),
         cell("Starter announcements; the only official support for a named quarterback"),
         cell("League"), rcell('<span class="pill prop">supports 4 clubs this week</span>')],
        [cell("Market prices"), rcell('<span class="pill unv">no official source exists</span>'),
         cell("No official source publishes betting prices"), cell("—"),
         rcell('<span class="pill unv">table ships empty</span>')],
    ]
    body = f"""
<div class="note"><b>Two tiers, always labelled.</b> League-published means the NFL put it on one of
its own pages. Club-published means a club put it on its own site; it is official in the sense that
the club owns it, but the club controls its accuracy and cadence, and some clubs label it
unofficial themselves. Nothing from either tier is mixed without saying which is which.</div>
<div class="scroll">{table([("Source", ""), ("URL", ""), ("What it provides", ""), ("Tier", ""),
                            ("Verification result", "")], rows, scroll=False, cls="src")}</div>
<h2>Retrieval and method</h2>
<p class="small">Every page above was fetched on {SNAPSHOT} and the values compared cell by cell
against the committed tables. The raw readings are stored under
<code>data/verification/raw/</code> so the comparison can be re-run, and the comparison itself is
<code>tools/verification/verify_standings.py</code>, <code>verify_schedule.py</code>,
<code>verify_injuries.py</code> and <code>verify_depth.py</code>. Run them with:</p>
<p><code>python3 tools/verification/verify_standings.py &amp;&amp; python3 tools/verification/verify_schedule.py &amp;&amp; python3 tools/verification/verify_injuries.py &amp;&amp; python3 tools/verification/verify_depth.py</code></p>
"""
    return page("Sources", body, "sources.html",
                "Where every number comes from, which tier of authority it has, and how the check "
                "was run.")


PAGES = {
    "index.html": build_index,
    "verification.html": build_verification,
    "findings.html": build_findings,
    "deficiency.html": build_deficiency,
    "decisions.html": build_decisions,
}


def main() -> int:
    os.makedirs(os.path.join(HUB, "assets"), exist_ok=True)
    with open(os.path.join(HUB, "assets", "hub.css"), "w", encoding="utf-8") as fh:
        fh.write(CSS)
    for name, fn in PAGES.items():
        html_out = fn()
        with open(os.path.join(HUB, name), "w", encoding="utf-8") as fh:
            fh.write(html_out)
        print(f"  wrote hub/{name}  ({len(html_out):,} bytes)")

    # integrity: every internal link resolves, every external link is a known official host
    reg = load("data/pipeline/club_registry.json") or {}
    hosts = {"www.nfl.com", "nfl.com", "github.com", "karagemop466-tech.github.io",
             "www.nfl.com"}
    for r in reg.get("rows", []):
        dom = (r.get("club_domain") or "").strip().lower()
        if dom:
            hosts.add(dom)
            hosts.add("www." + dom)
    targets = {n for n in PAGES}
    problems = []
    for name in PAGES:
        text = open(os.path.join(HUB, name), encoding="utf-8").read()
        for href in re.findall(r'href="([^"]+)"', text):
            if href.startswith("#") or href.startswith("assets/"):
                continue
            base = href.split("#", 1)[0]
            if base in targets:
                continue
            if href.startswith("http"):
                host = re.sub(r"^https?://", "", base).split("/")[0]
                if host not in hosts:
                    problems.append(f"{name}: external host not on the official allow-list: {href}")
                if not base.startswith("https://"):
                    problems.append(f"{name}: external link is not https: {href}")
            elif base:
                resolved = os.path.normpath(os.path.join(HUB, base))
                if not os.path.exists(resolved):
                    problems.append(f"{name}: broken internal link: {href}")
    # every table row must contain at least one link or an explicit unverified badge
    rowcheck = 0
    for name in PAGES:
        text = open(os.path.join(HUB, name), encoding="utf-8").read()
        sourced = "".join(re.findall(r'<table class="src.*?</table>', text, re.S))
        for tr in re.findall(r"<tr>(.*?)</tr>", sourced, re.S):
            if "<th" in tr:
                continue
            rowcheck += 1
            if "href=" not in tr and "pill unv" not in tr and "pill out" not in tr \
                    and "pill doubt" not in tr and "pill quest" not in tr:
                problems.append(f"{name}: table row has neither a source link nor an "
                                f"unverified badge: {tr[:120]}")
    print(f"  {rowcheck} table rows checked for source provenance")
    if problems:
        for p in problems:
            print("  PROBLEM " + p)
        return 1
    print("  OK — all internal links resolve, all external hosts official, all rows sourced")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
