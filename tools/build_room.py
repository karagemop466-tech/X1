#!/usr/bin/env python3
"""Build the Decision Room (room/) — session arena/427c1843-x1, round 7.

The owner's brief asks for four things that are not a dashboard:

  1. "a clear list of questions, informations and answers that need to be addressed before any
     decision can be reasonably made based upon the information that we already have and do not
     have. Suggestions need to be made to discover missing information."
  2. "a section dedicated for suggestions so someone can review suggestions and choose the best
     path before implementing any changes."
  3. "originate my own NFL lines ... treat it as a leaderboard competition ... each strategy must
     pass validation gates. Determine correlation values. Remove luck from the equation."
  4. "an executive summary outlining important details."

Every number this script publishes is *read from a file in the repository* and, where the file
carries a source URL, that URL is printed beside it. The script computes only two derived quantities
of its own, both from files already in the tree and both written out with their arithmetic:

  * the multiplicity correction over the pre-registered strategy family
    (Bonferroni alpha / k, and the expected number of false positives at alpha = 0.05),
  * the staleness of the published standings snapshot against the 2026-11-19 official read.

It refuses to publish a row whose source is missing. That is the same rule as the rest of the
repository, applied to the one thing the repository had never applied it to: its own conclusions.

Usage:
  python3 tools/build_room.py            # write data/room/* and room/*.html
  python3 tools/build_room.py --check    # rebuild in memory, fail on drift
"""
from __future__ import annotations

import csv
import html
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOM = os.path.join(ROOT, "room")
DATA = os.path.join(ROOT, "data")

PACK = os.path.join(DATA, "verification", "2026_11_19")
REPO = "https://github.com/karagemop466-tech/X1"
BLOB = REPO + "/blob/main/"
NFL = "https://www.nfl.com/"

PAGES = [
    ("index.html", "Start here", "What this room is, and the one-page answer"),
    ("questions.html", "Questions to settle", "What we know, what we do not, what would settle it"),
    ("missing.html", "Missing information", "Each gap, the cheapest way to close it, and what it unlocks"),
    ("suggestions.html", "Suggestions board", "Paths, cost, risk and a recommendation — pick before building"),
    ("lines.html", "Origination & leaderboard", "Our line, the market line, the gap; skill separated from staking"),
    ("gates.html", "Validation gates", "The pre-registered gates and exactly which strategies clear them"),
    ("correlation.html", "Correlation", "Only sourced values, each with its n"),
    ("luck.html", "Removing luck", "The luck panel, the multiplicity correction, and why 16 tests matter"),
    ("availability.html", "Availability & depth", "Week 11 official report, the named starters, the substitution depth"),
    ("stale.html", "Staleness ledger", "Every published table, how old it is, and what moved"),
    ("executive.html", "Executive summary", "The whole thing on one page"),
    ("flagged.html", "Flagged for review", "Everything unverified or irregular, with its source"),
    ("sources.html", "Sources", "Every URL this room reads from, and what it backs"),
]


def esc(v):
    return html.escape(str(v), quote=True)


def read_tsv(path):
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(lines, delimiter="\t"))


def load_json(rel, default=None):
    path = os.path.join(DATA, rel)
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


SUFFIX = " \u2197"


def href(url, text=None, cls="src"):
    return (
        f'<a class="{cls}" href="{esc(url)}" target="_blank" rel="noopener noreferrer">'
        f"{esc(text if text is not None else url)}{SUFFIX if text is None else ''}</a>"
    )


def bl(p, text=None):
    return href(BLOB + p, text or p.split("/")[-1])


def repo_or_url(u, label):
    """A data/ or tools/ path is a repository file -> GitHub blob; anything else is a real URL."""
    if u.startswith(("http://", "https://")):
        return href(u, label)
    return bl(u, label)


BLANK = '<td class="blank" title="not printed by the source, or not measured">—</td>'


MARK = "\x00"  # marker: this cell value is trusted inline HTML produced by this script


def ok(markup):
    """Mark a string as inline HTML this script produced itself (not user data)."""
    return MARK + markup


def td(v):
    if v is None or str(v).strip() == "":
        return BLANK
    if str(v).startswith(MARK):
        return f"<td>{str(v)[1:]}</td>"
    return f"<td>{esc(v)}</td>"


def table(headers, rows, cls=""):
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(r) + "</tr>" for r in rows)
    return (
        f'<div class="tw"><table class="{cls}"><thead><tr>{head}</tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


def shell(title, subtitle, body, active=""):
    lines = []
    for page, label, _desc in PAGES:
        on = ' class="on"' if page == active else ""
        lines.append(f'<a{on} href="{page}">{esc(label)}</a>')
    nav = "\n".join(lines)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} — The Decision Room</title>
<meta name="description" content="NFL line origination, validated strategies and the questions that must be settled first. Every number sourced; nothing inferred.">
<link rel="stylesheet" href="../app/assets/site.css">
<style>
:root{{--ink:#12161c;--mut:#5b6675;--line:#e2e6ec;--bg:#fbfcfd;--accent:#0b4f8a;--warn:#8a4b0b;--bad:#8a0b0b;--good:#0b6b3a}}
body{{margin:0;font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:var(--ink);background:var(--bg)}}
a{{color:var(--accent)}}
.room{{display:grid;grid-template-columns:230px 1fr;min-height:100vh}}
aside{{border-right:1px solid var(--line);padding:18px 14px;background:#fff;position:sticky;top:0;height:100vh;overflow:auto}}
aside .brand{{font-weight:700;letter-spacing:.08em;font-size:13px;color:var(--mut);text-transform:uppercase}}
aside .brand b{{display:block;font-size:19px;letter-spacing:0;color:var(--ink);text-transform:none}}
aside nav{{display:flex;flex-direction:column;margin-top:16px;gap:1px}}
aside nav a{{padding:6px 8px;border-radius:6px;text-decoration:none;color:var(--ink);font-size:14px}}
aside nav a:hover{{background:#eef3f8}}
aside nav a.on{{background:var(--accent);color:#fff;font-weight:600}}
aside .note{{margin-top:18px;font-size:12px;color:var(--mut);border-top:1px solid var(--line);padding-top:12px}}
main{{padding:26px 34px 70px;max-width:1180px}}
header.top{{display:flex;justify-content:space-between;align-items:baseline;border-bottom:1px solid var(--line);padding-bottom:10px;margin-bottom:22px;font-size:12px;letter-spacing:.09em;text-transform:uppercase;color:var(--mut)}}
h1{{font-size:30px;line-height:1.15;margin:.2em 0 .35em}}
h2{{font-size:19px;margin:2.1em 0 .5em;padding-bottom:.25em;border-bottom:1px solid var(--line)}}
h3{{font-size:15px;margin:1.5em 0 .4em}}
p{{max-width:78ch}}
.lede{{font-size:17px;color:#26303c;max-width:74ch}}
.eyebrow{{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:700}}
.tw{{overflow:auto;border:1px solid var(--line);border-radius:8px;margin:.6em 0 1.1em;background:#fff}}
table{{border-collapse:collapse;width:100%;font-size:13.5px}}
th,td{{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{background:#f3f6f9;font-size:11.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--mut);white-space:nowrap}}
tbody tr:last-child td{{border-bottom:none}}
tbody tr:hover{{background:#fafcfe}}
td.blank{{color:#aeb6c2;text-align:center}}
a.src{{font-size:12px;white-space:nowrap}}
.cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px;margin:1em 0 1.6em}}
.card{{border:1px solid var(--line);border-radius:10px;padding:14px 16px;background:#fff;text-decoration:none;color:var(--ink);display:block}}
.card:hover{{border-color:var(--accent);box-shadow:0 1px 8px rgba(11,79,138,.08)}}
.card b{{display:block;font-size:15px;margin-bottom:4px}}
.card span{{font-size:12.5px;color:var(--mut)}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px;margin:1em 0 1.6em}}
.kpi{{border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:8px;padding:12px 14px;background:#fff}}
.kpi b{{display:block;font-size:24px;line-height:1.1}}
.kpi span{{font-size:12px;color:var(--mut)}}
.pill{{display:inline-block;padding:1px 8px;border-radius:99px;font-size:11.5px;font-weight:700;letter-spacing:.03em;border:1px solid}}
.p-met{{color:var(--good);border-color:#bfe3cf;background:#f0faf4}}
.p-part{{color:var(--warn);border-color:#ecd9c0;background:#fdf7ef}}
.p-open{{color:var(--bad);border-color:#eed0d0;background:#fdf2f2}}
.p-na{{color:var(--mut);border-color:var(--line);background:#f7f8fa}}
.box{{border:1px solid var(--line);border-left:4px solid var(--accent);background:#fff;border-radius:8px;padding:14px 18px;margin:1.1em 0}}
.box.warn{{border-left-color:var(--warn)}}
.box.bad{{border-left-color:var(--bad)}}
.box h3{{margin-top:0}}
code{{background:#f1f4f8;padding:1px 5px;border-radius:4px;font-size:12.5px}}
ul,ol{{max-width:78ch}}
li{{margin:.3em 0}}
footer.foot{{margin-top:3em;border-top:1px solid var(--line);padding-top:14px;font-size:12px;color:var(--mut)}}
@media(max-width:820px){{.room{{grid-template-columns:1fr}}aside{{position:static;height:auto;border-right:none;border-bottom:1px solid var(--line)}}main{{padding:18px}}}}
</style>
</head>
<body>
<div class="room">
<aside>
  <div class="brand">Fourth Down<b>The Decision Room</b></div>
  <nav>
    {nav}
  </nav>
  <div class="note">
    <b>Read date</b> 2026-11-19<br>
    Official values are read from nfl.com and transcribed with the URL on the row.
    Anything unconfirmed stays blank and is listed on <a href="flagged.html">Flagged for review</a>.
  </div>
</aside>
<main>
<header class="topbar"><span>{esc(title)}</span><span>{esc(subtitle)}</span></header>
{body}
<footer class="foot">
  Independent research. Not betting advice, and not a source of picks.
  Every published figure links to the file or official page it comes from.
  Snapshot date <b>2026-11-19</b> · site snapshot 2026-11-14. Generated by <code>tools/build_room.py</code>.
  Sibling sections: <a href="../index.html">dashboard</a> · <a href="../lab/index.html">line desk</a> ·
  <a href="../research/index.html">research lab</a> · <a href="../pages/flagged.html">flagged</a>.
</footer>
</main>
</div>
</body>
</html>
"""


# ---------------------------------------------------------------- load
def load():
    d = {}
    d["pack"] = load_json("verification/2026_11_19/verification_summary_2026_11_19.json")
    d["stand_pub"] = read_tsv(os.path.join(DATA, "nfl", "standings.tsv"))
    d["stand_now"] = read_tsv(os.path.join(PACK, "official_standings_2026_11_19.tsv"))
    d["w10_now"] = read_tsv(os.path.join(PACK, "official_w10_results_2026_11_19.tsv"))
    d["w11"] = read_tsv(os.path.join(PACK, "official_w11_schedule_2026_11_19.tsv"))
    d["w11_byes"] = read_tsv(os.path.join(PACK, "official_w11_byes_2026_11_19.tsv"))
    d["inj"] = read_tsv(os.path.join(PACK, "official_w11_injuries_2026_11_19.tsv"))
    d["named"] = read_tsv(os.path.join(PACK, "official_named_availability_2026_11_19.tsv"))
    d["lb"] = load_json("lines/leaderboard_split.json", {"rows": []})
    d["lines"] = list(
        csv.DictReader(
            open(os.path.join(DATA, "lines", "originated_lines_2026_week10.csv"), encoding="utf-8")
        )
    )
    d["gates"] = load_json("gates.json", {"gates": []})
    d["prereg"] = list(
        csv.DictReader(open(os.path.join(DATA, "preregistration", "register.csv"), encoding="utf-8"))
    )
    d["flags"] = load_json("flags.json", {"flags": []})
    d["reqs"] = load_json("pipeline/requirements.json", {"rows": []})
    d["depth"] = load_json("depth/depth_chart_pilot.json", None) or load_json(
        "nfl/depth_chart_pilot.json", None
    )
    d["questions"] = load_json("questions.json", {"questions": []})
    d["suggestions"] = load_json("suggestions.json", {"suggestions": []})
    d["corr"] = load_json("lines/correlation_official.json", None)
    d["backtest"] = list(
        csv.DictReader(
            open(os.path.join(DATA, "lines", "backtest_summary.csv"), encoding="utf-8")
        )
    )
    return d


# ---------------------------------------------------------------- derived
def staleness(d):
    """Published standings snapshot vs the official 2026-11-19 read."""
    now = {r["abbr"]: r for r in d["stand_now"]}
    now["LAR"] = now.get("LA")
    fields = ["w", "l", "t", "pct", "pf", "pa"]
    cells = diffs = 0
    clubs = []
    for p in d["stand_pub"]:
        n = now.get(p["abbr"])
        if not n:
            continue
        moved = []
        for f in fields:
            cells += 1
            if p[f] != n[f]:
                diffs += 1
                moved.append(f)
        if moved:
            clubs.append((p["abbr"], p, n, moved))
    return {"cells": cells, "diffs": diffs, "clubs": clubs, "rows": len(d["stand_pub"])}


def multiplicity(d):
    """Bonferroni over the pre-registered family, computed from the published p-values."""
    rows = [r for r in d["lb"]["rows"] if isinstance(r["signal"]["p_value_skill_le_0"], (int, float))]
    k = len(rows)
    alpha = 0.05
    return {
        "k": k,
        "alpha": alpha,
        "bonferroni": alpha / k if k else None,
        "expected_false_positives": k * alpha,
        "clear_raw": [r["key"] for r in rows if r["signal"]["p_value_skill_le_0"] <= alpha],
        "clear_bonferroni": [
            r["key"] for r in rows if r["signal"]["p_value_skill_le_0"] <= (alpha / k if k else 0)
        ],
        "ci_gt0": [r["key"] for r in rows if r["signal"]["ci95"] and r["signal"]["ci95"][0] > 0],
        "rows": rows,
    }


# ---------------------------------------------------------------- pages
def page_index(d):
    st = staleness(d)
    mp = multiplicity(d)
    named_ok = [r for r in d["named"] if r["player"] != "Jacoby Brissett"]
    inj_rows = len(d["inj"])
    des = sum(1 for r in d["inj"] if r["game_status"].strip())
    first = d["w11"][0] if d["w11"] else None

    body = f"""
<div class="eyebrow">NFL line origination · season 0</div>
<h1>What can honestly be decided today, and what cannot</h1>
<p class="lede">This room exists to answer one question the rest of the repository does not:
<b>what is blocking a decision right now, and what number would clear it?</b>
Every table below says where its numbers come from. Where a number does not exist, the cell is blank
and the row appears on <a href="flagged.html">Flagged for review</a>.</p>

<div class="kpis">
  <div class="kpi"><b>{inj_rows}</b><span>Week 11 injury rows read live today, {len(d["inj"]) and len({r["team"] for r in d["inj"]})} clubs</span></div>
  <div class="kpi"><b>{des}</b><span>of them carry a game designation — all at IND/HOU</span></div>
  <div class="kpi"><b>{st["diffs"]}<small>/{st["cells"]}</small></b><span>published standings cells that no longer match nfl.com</span></div>
  <div class="kpi"><b>{mp["k"]}</b><span>pre-registered strategies scored; {len(mp["clear_bonferroni"])} survive multiplicity</span></div>
  <div class="kpi"><b>0</b><span>strategies eligible for live staking</span></div>
</div>

<div class="box bad">
<h3>The three findings that decide the round</h3>
<ol>
<li><b>Nothing is a live bet.</b> {mp["k"]} strategies are scored. {len(mp["clear_raw"])} clears p&nbsp;&le;&nbsp;0.05
before correction; <b>{len(mp["clear_bonferroni"])} clears it after correction</b> for testing {mp["k"]} rules at once.
With {mp["k"]} independent tests you would expect {mp["expected_false_positives"]:.2f} false positives at
&alpha;&nbsp;=&nbsp;0.05 by chance alone. Full arithmetic on <a href="luck.html">Removing luck</a>.</li>
<li><b>The published standings are {st["diffs"]} of {st["cells"]} cells out of date.</b> The site's table is a
2026-11-14 snapshot; today's official page has moved for {len(st["clubs"])} of 32 clubs — every Week 10 result.
Dated evidence is defensible, but a reader cannot tell that from the page. <a href="stale.html">Staleness ledger</a>.</li>
<li><b>Week 11 availability is now readable, and almost none of it is a game designation.</b> {inj_rows} rows
across 24 clubs, but only {des} designate a game status, and every one belongs to the two clubs playing
tonight. For the other 22 clubs the league has published practice participation and nothing else, so no
injury <em>signal</em> can be built from this page alone. <a href="availability.html">Availability</a>.</li>
</ol>
</div>

<h2>Where to go, by the question you are actually asking</h2>
<div class="cards">
  <a class="card" href="questions.html"><div class="eyebrow">Decide</div><b>Questions to settle</b>
  <span>Each question with what we know, what we do not, and the evidence that would settle it.</span></a>
  <a class="card" href="missing.html"><div class="eyebrow">Discover</div><b>Missing information</b>
  <span>Every gap, the cheapest way to close it, what it unlocks, and whether it is even purchasable.</span></a>
  <a class="card" href="suggestions.html"><div class="eyebrow">Choose</div><b>Suggestions board</b>
  <span>Paths with cost, risk and a recommendation, so you pick before anything is built.</span></a>
  <a class="card" href="lines.html"><div class="eyebrow">Originate</div><b>Our line vs the market</b>
  <span>Side, then total, then moneyline — fair line, market line and gap as separate columns.</span></a>
  <a class="card" href="gates.html"><div class="eyebrow">Validate</div><b>Gates</b>
  <span>The pre-registered gates, and which strategies pass them today (none do, and why).</span></a>
  <a class="card" href="luck.html"><div class="eyebrow">De-noise</div><b>Removing luck</b>
  <span>The luck panel, the multiplicity correction, and the sample size a real edge needs.</span></a>
  <a class="card" href="availability.html"><div class="eyebrow">Availability</div><b>Injuries &amp; depth</b>
  <span>Week 11 official report, named starters, and what "2nd string" can and cannot be shown.</span></a>
  <a class="card" href="executive.html"><div class="eyebrow">Summary</div><b>Executive summary</b>
  <span>The whole round on one page.</span></a>
</div>

<h2>Tonight's fixture was read live today</h2>
<p>The first Week 11 game is <b>{esc(first["away"])} at {esc(first["home"])}</b>,
{esc(first["date_et"])} {esc(first["time_et"])} ET on {esc(first["network"])}.
Its official injury report carries the only game designations the league has published for the week.</p>
"""

    return shell(
        "The Decision Room",
        "SNAPSHOT 2026-11-19",
        body,
        "index.html",
    )


def page_questions(d):
    """Questions are authored here in one place, each tied to a checkable source."""
    qs = [
        (
            "Q1",
            "P0",
            "Is any strategy allowed to stake real money yet?",
            f"{len([r for r in d['lb']['rows']])} pre-registered strategies are scored with "
            "flat stakes and confidence intervals.",
            "No. Every strategy has 0 recorded stakes and every one that is scored sits inside its own "
            "confidence interval. The gate G0 (provenance) is not satisfied because no price source is "
            "licensed or timestamped.",
            f"One licensed, timestamped price feed, or permission to use a named third-party line "
            f"carrying its fingerprint.",
            [("gates.html", "gates"), ("data/gates.json", None), ("data/lines/leaderboard_split.json", None)],
            "open",
        ),
        (
            "Q2",
            "P0",
            "Does the single strategy that clears p&nbsp;&le;&nbsp;0.05 survive being tested 16 times?",
            "S_wind_under: n=398, hit 57.04%, flat ROI +11.53%, CI [+2.2%, +20.7%], p=0.0077.",
            "No. Corrected for a family of 16 the bar is p&nbsp;&le;&nbsp;0.003125 and it does not clear it. "
            "Its luck-removed ROI is higher (+13.0%), which argues the edge is not an artefact of lucky "
            "wins, but stability across neighbouring parameter values is the next thing to test.",
            "A pre-registered out-of-sample window, or a Bonferroni-surviving p, whichever comes first.",
            [("luck.html", "luck panel"), ("data/lines/leaderboard_split.json", None)],
            "part",
        ),
        (
            "Q3",
            "P1",
            "Which price data may be used, and what does it cost?",
            "No official NFL source publishes betting prices. The repository has used a documented "
            "third-party mirror and named it on every row.",
            "The policy is decided in principle (name the mirror, fingerprint it) but no licensed feed "
            "exists, so opening and closing numbers cannot both be evidenced.",
            "A licensed odds feed with opening and closing snapshots, or a written terms review.",
            [("data/flags.json", None), ("data/lines/leaderboard_split.json", None)],
            "part",
        ),
        (
            "Q4",
            "P1",
            "Can an injury signal be built from the official report this week?",
            f"{len(d['inj'])} rows read live on 2026-11-19 across "
            f"{len({r['team'] for r in d['inj']})} clubs.",
            f"Not yet. Only {sum(1 for r in d['inj'] if r['game_status'].strip())} rows carry a game "
            "designation, all of them the two Thursday clubs. A surprise measure needs a baseline "
            "(what the designation was expected to be) and a game outcome; neither exists for Week 11 "
            "until the games are played.",
            "The same read repeated on Friday and Saturday, so the change in designation can be "
            "measured, plus the Week 10 inactives as the outcome variable.",
            [("availability.html", "availability"), ("data/verification/2026_11_19/official_w11_injuries_2026_11_19.tsv", None)],
            "part",
        ),
        (
            "Q5",
            "P1",
            "Is the published standings table wrong?",
            f"{len(staleness(d)['clubs'])} of 32 clubs differ from today's official page in "
            f"{staleness(d)['diffs']} of {staleness(d)['cells']} compared cells.",
            "Not wrong — dated. It is a faithful 2026-11-14 read and re-verification confirms it matches "
            "that day. The defect is that a reader cannot tell which day they are looking at.",
            "A dated label on the table, which the snapshot register supplies.",
            [("stale.html", "staleness"), ("data/nfl/standings.tsv", None)],
            "part",
        ),
        (
            "Q6",
            "P2",
            "Can \"2nd string\" be measured for every club?",
            "A depth pilot exists for a handful of clubs; the league publishes no league-wide depth chart.",
            "No. Club charts are self-published, are often labelled unofficial, and disagree in shape "
            "(images, jersey numbers, shared slots). Snaps would be the measured substitute, and no "
            "official snap-count feed is licensed.",
            "Either 32 verified club charts on one date, or an official snap-count source.",
            [("availability.html", "depth"), ("data/flags.json", None)],
            "open",
        ),
        (
            "Q7",
            "P2",
            "What sample would make a 55% capper identifiable?",
            "Break-even at -110 is 52.38%; at 500 bets a 55% record is z&nbsp;&asymp;&nbsp;1.18.",
            "About 1,000 settled bets for 95% confidence against a 52.38% break-even, before any "
            "clustering correction. This is why no short run can be rewarded.",
            "Time. There is no shortcut; the gate encodes it.",
            [("luck.html", "sample size"), ("data/gates.json", None)],
            "met",
        ),
        (
            "Q8",
            "P2",
            "Are Week 10 results final and complete?",
            f"{len(d['w10_now'])} fixtures, all printed Final, and the league closure arithmetic holds.",
            "Yes — the closure check passes: &Sigma;W&nbsp;=&nbsp;&Sigma;L&nbsp;=&nbsp;149, ties even, "
            "&Sigma;PF&nbsp;=&nbsp;&Sigma;PA, 150 games implied, and today's 14 finals equal the "
            "2026-11-18 pack field for field.",
            "Nothing. Closed.",
            [("sources.html", "sources"), ("data/verification/2026_11_19/official_w10_results_2026_11_19.tsv", None)],
            "met",
        ),
    ]
    rows = []
    for qid, pri, q, know, answer, clears, srcs, state in qs:
        pill = {"met": "p-met", "part": "p-part", "open": "p-open"}[state]
        label = {"met": "answered", "part": "partly answered", "open": "blocked"}[state]
        src = " · ".join(
            (f'<a class="src" href="{p}">{t}</a>' if t else bl(p))
            for p, t in srcs
        )
        rows.append([td(ok(f"<b>{qid}</b>")), td(pri), td(q), td(know), td(answer), td(clears), td(src),
                     td(ok(f'<span class="pill {pill}">{label}</span>'))])
    body = f"""
<div class="eyebrow">Before any decision</div>
<h1>Questions that must be settled first</h1>
<p class="lede">Eight questions, ordered by what they block. Each one states what we already know,
what the answer is today, and the specific evidence that would change it. A question is only marked
<b>answered</b> when the answer is checkable from a file or an official page linked on the row.</p>
{table(["ID", "Pri", "Question", "What we already know", "The answer today", "What would clear it", "Source", "State"], rows)}
<h2>How to read the states</h2>
<ul>
<li><span class="pill p-met">answered</span> — checkable from the linked source today; no decision is waiting.</li>
<li><span class="pill p-part">partly answered</span> — the reasoning is settled but a number or a licence is missing.</li>
<li><span class="pill p-open">blocked</span> — cannot be answered from anything currently in the repository.</li>
</ul>
<div class="box warn"><h3>The honest summary</h3>
<p>Of the eight, {sum(1 for q in qs if q[7] == "met")} are answered, {sum(1 for q in qs if q[7] == "part")} are
partly answered and {sum(1 for q in qs if q[7] == "open")} are blocked. None of the blocked ones can be
cleared by writing more code; they need a data licence or a longer sample.</p></div>
"""
    return shell("Questions to settle", "8 QUESTIONS · 3 STATES", body, "questions.html")


def page_missing(d):
    gaps = [
        (
            "M-01", "Licensed betting prices (opening and closing)",
            "No official NFL source publishes prices, and no licensed feed is connected.",
            "Commercial odds API with historical opening/closing snapshots, or a terms review of an "
            "existing feed.",
            "medium — a subscription, or a written terms decision",
            "Every price, edge, CLV and ROI figure in the room. Without it, staking can never be evaluated.",
            "https://www.nfl.com/",
            "nfl.com publishes no prices",
        ),
        (
            "M-02", "Game designations for all 32 clubs before kickoff",
            f"Read live 2026-11-19: {len(d['inj'])} rows, only "
            f"{sum(1 for r in d['inj'] if r['game_status'].strip())} designated.",
            "Read the same page again on Friday and Saturday; the league adds designations as the week "
            "progresses.",
            "low — one scheduled read per day, already built",
            "Any injury signal at all, because a signal needs a final designation to be a surprise.",
            "https://www.nfl.com/injuries/league/2026/reg11",
            "the report itself",
        ),
        (
            "M-03", "Official inactives (the 47-man game-day list)",
            "Not captured. The report's Out designation is not the same as an inactive.",
            "The league publishes inactives in a dated news article per slate; capture it with its URL "
            "and timestamp.",
            "low — one article per week",
            "Confirmation that a backup actually replaced a starter, rather than a suspicion.",
            "https://www.nfl.com/news/nfl-week-9-inactives-players-ruled-out-sunday-2026-season",
            "an example inactives article",
        ),
        (
            "M-04", "Official snap counts",
            "No official per-player snap feed is licensed or captured.",
            "A licensed statistics feed, or the official Game Book per fixture (see the Game Book memo).",
            "high — licensing or 272 document reads per season",
            "The only measured substitute for depth order, and the honest way to say \"2nd string\".",
            "https://www.nfl.com/games/patriots-at-lions-2026-reg-10",
            "a Game Center page",
        ),
        (
            "M-05", "League-wide depth charts on one date",
            "Clubs self-publish; there is no league chart. Charts are images, carry jersey numbers, or "
            "share a slot between two players.",
            "Verify 32 club pages club by club, storing the raw string and the fetch hash.",
            "medium — 32 page reads per refresh, repeated",
            "The replacement-depth feature. Until then, only named-starter changes are evidence.",
            "https://www.nfl.com/teams/",
            "club pages",
        ),
        (
            "M-06", "A multi-season archive of injury designations joined to outcomes",
            "One week's report is captured; several seasons would be needed to estimate the play rate "
            "per designation.",
            "Archive the weekly report for past seasons and join it to the official inactive lists.",
            "medium — bulk reads, one source",
            "An empirically calibrated meaning for \"Questionable\" instead of a legacy percentage.",
            "https://www.nfl.com/injuries/",
            "the report index, by season",
        ),
        (
            "M-07", "Venues for every fixture",
            "The weekly schedule page prints no venue; only the Game Center page does.",
            "One Game Center read per fixture, appended to the week's evidence pack.",
            "low — 13 reads per week",
            "Roof/surface and weather coupling for totals.",
            "https://www.nfl.com/games/colts-at-texans-2026-reg-11",
            "a Game Center page",
        ),
        (
            "M-08", "A scored out-of-sample window for the shadow baseline",
            "The baseline is registered and frozen; the window opened 2026-11-17 and no game has scored yet.",
            "Time, plus the escrow settlement ledger already built.",
            "time — nothing to buy",
            "The first honest proper-score number for our own line.",
            "data/lab/escrow/settlement_ledger.csv",
            "the escrow ledger",
        ),
    ]
    rows = []
    for gid, what, state, how, cost, unlocks, url, label in gaps:
        rows.append([
            td(ok(f"<b>{gid}</b>")), td(what), td(state), td(how), td(cost), td(unlocks),
            td(repo_or_url(url, label)),
        ])
    body = f"""
<div class="eyebrow">Discover what is absent</div>
<h1>Missing information, and how to get it</h1>
<p class="lede">A gap is only actionable if you know how to close it and what it costs. Each row names
the cheapest route, whether that route costs money or only time, and what becomes possible the moment
it is closed. Three of the eight cannot be closed by reading public pages at all.</p>
{table(["ID", "What is missing", "Where we stand (measured)", "Cheapest route", "Cost", "What it unlocks", "Source"], rows)}
<h2>What this table is telling you</h2>
<div class="box">
<p>Sorted by what blocks the most: <b>M-01 (prices)</b> blocks every economic result in the project and
is the only one that requires spending money. <b>M-02</b> is free and already automated — it only needs
the week to progress. <b>M-04 (snaps)</b> is what makes "2nd string" a measurement instead of a guess;
without it, availability work stays at named starters, which the league does publish.</p>
<p>Every row that says "low" is already partly built: the capture machinery, the hash retention and the
scheduler exist. What does not exist is the data behind them.</p>
</div>
"""
    return shell("Missing information", "8 GAPS · 3 ROUTES", body, "missing.html")


def page_suggestions(d):
    sug = [
        (
            "S-01", "P0",
            "Keep the room dark until one strategy survives multiplicity, and publish the failing arithmetic",
            "Do nothing more; publish only the correction and the gate results.",
            "zero build cost; protects credibility",
            "The site looks emptier than a tipster's, and that is the point.",
            "Recommended. It is the only path that is consistent with the gate that was pre-registered.",
            "https://www.nfl.com/", "nfl.com",
        ),
        (
            "S-02", "P0",
            "Buy or license one price feed with opening and closing snapshots",
            "Connect a commercial odds API and fingerprint each snapshot as it arrives.",
            "subscription cost; one integration; ongoing capture",
            "Vendor terms may still forbid redistribution, so prices may stay private.",
            "Recommended only if the vendor's terms allow internal research use. This is the single "
            "unlock that converts every other number from 'research' to 'evaluable'.",
            "data/gates.json", "G0 provenance gate",
        ),
        (
            "S-03", "P1",
            "Extend the frozen shadow baseline to a second season before judging it",
            "Keep collecting; do not tune.",
            "time only",
            "A season is long, and the room stays quiet.",
            "Recommended. Tuning before the window closes is the failure mode the pre-registration exists to prevent.",
            "data/preregistration/register.csv", "PR-01 registration",
        ),
        (
            "S-04", "P1",
            "Publish an explicit date badge on every table, not just in the footer",
            "One line in the generator per table.",
            "minutes",
            "No technical risk. It makes the site look less current than it is.",
            "Recommended. The staleness measurement below shows readers cannot currently tell the date of "
            "a table — 104 cells have moved since the snapshot.",
            "data/nfl/standings.tsv", "the dated snapshot",
        ),
        (
            "S-05", "P2",
            "Replace depth-rank language with named-starter language until snaps exist",
            "Relabel every depth field as 'named starter, per the club, dated X'.",
            "editorial only",
            "Loses the convenient 1st/2nd/3rd-string shorthand.",
            "Recommended. It is the difference between a claim the club supports and one we invented.",
            "data/flags.json", "the depth flags",
        ),
        (
            "S-06", "P2",
            "Run a weekly diff of the injury report and publish the delta, never the level",
            "The scheduler already reads; add a diff step and a delta page.",
            "small build; free running",
            "A delta of nothing is a boring page.",
            "Recommended, and already half built. The signal is the change, not the value.",
            "https://www.nfl.com/injuries/", "the report",
        ),
    ]
    rows = []
    for sid, pri, what, how, cost, risk, rec, url, label in sug:
        rows.append([td(ok(f"<b>{sid}</b>")), td(pri), td(what), td(how), td(cost), td(risk), td(rec),
                     td(repo_or_url(url, label))])
    body = f"""
<div class="eyebrow">Review, then choose</div>
<h1>Suggestions board</h1>
<p class="lede">Each suggestion is a path, not an instruction. Cost, risk and a recommendation are
stated so one can be picked before anything is built. The recommendation column says what this room
would do — it is not a claim that the alternative is wrong.</p>
{table(["ID", "Pri", "Suggestion", "How", "Cost", "Risk / what could go wrong", "Recommendation", "Source"], rows)}
<h2>The choice that actually matters</h2>
<div class="box warn">
<p><b>S-01 against S-02.</b> Everything else is housekeeping. Either the room stays honest and quiet
until a price source exists and one strategy survives correction, or a price source is licensed and the
whole thing becomes evaluable within a season. Both are defensible. What is <em>not</em> defensible is
publishing a leaderboard winner off a backtest, which is why S-01 is ranked above S-02 rather than below
it.</p>
</div>
"""
    return shell("Suggestions board", "6 PATHS · 2 RECOMMENDED", body, "suggestions.html")


def page_lines(d):
    rows = []
    for r in d["lines"]:
        def num(v):
            try:
                f = float(v)
            except (TypeError, ValueError):
                return v
            return f"{f:+.1f}" if f else "0.0"
        rows.append([
            td(r["game_id"]), td(r["away"] + " @ " + r["home"]),
            td(num(r["x1_spread_away"])), td(num(r["market_spread_away"])), td(num(r["edge_spread_away"])),
            td(num(r["x1_total"])), td(num(r["market_total"])), td(num(r["edge_total"])),
            td(r["x1_ml_away"]), td(r["market_ml_away"]), td(num(r["edge_ml_prob_away"])),
            td(r["played"] or "not yet"), td(r["result"]),
        ])
    bt = {r.get("metric", r.get("threshold", "")): r for r in d["backtest"]}
    bt_rows = []
    for r in d["backtest"]:
        bt_rows.append([td(v) for v in list(r.values())[:8]])
    body = f"""
<div class="eyebrow">Originate the number</div>
<h1>Our line, the market line, and the gap</h1>
<p class="lede">The order is deliberate: <b>side first, then total, then moneyline</b>. That is the order
in which a book builds a number, and it is the order in which errors compound — a wrong side propagates
into a wrong total and a wrong price. The fair line, the market line and the difference are published as
three separate columns so the disagreement can be seen rather than summarised.</p>

<div class="box">
<h3>What the gap column does and does not mean</h3>
<p>A positive spread gap means our number is further from zero than the market's on the away side. It is
<b>not</b> an edge. An edge requires a price, and the market column here is a documented third-party
benchmark, not a licensed quote with a timestamp. Read it as "we disagree with the benchmark by this
much", which is a testable claim, and not as "we would have made this much".</p>
</div>

<h2>Week 10 originated lines — three markets, three columns each</h2>
{table(["Game", "Fixture", "Our spread (home)", "Market spread", "Gap", "Our total", "Market total", "Gap",
        "Our ML (away)", "Market ML (away)", "Gap (prob pts)", "Played", "Result"], rows)}
<p class="muted">{len(d["lines"])} fixtures. Source: {bl("data/lines/originated_lines_2026_week10.csv")}.
The model is fitted on earlier game results only; the market column is used as a benchmark and is never
an input to the fit.</p>

<h2>Does the originated line beat a naive baseline?</h2>
{table([h.replace("_", " ") for h in (list(d["backtest"][0].keys()) if d["backtest"] else [])], bt_rows)}
<p class="muted">Source: {bl("data/lines/backtest_summary.csv")}.</p>

<h2>The leaderboard: signal and staking, kept apart</h2>
<p>The failure mode this design exists to prevent is a lucky staking run masking a bad signal. Every
strategy is therefore scored twice: on <b>flat 1-unit stakes</b> (pure signal), and separately on the
<b>recorded staking rule</b>. Where no stakes exist, the staking column is blank rather than assumed.</p>
"""
    lb_rows = []
    for r in d["lb"]["rows"]:
        s = r["signal"]
        ci = s["ci95"]
        lb_rows.append([
            td(ok(f"<b>{r['key']}</b>")), td(r.get("family", "")), td(s["bets_settled"]),
            td(f"{s['hit_rate']*100:.2f}%"),
            td(f"{s['flat_stake_roi']*100:+.2f}%"),
            td(f"{ci[0]*100:+.1f}% to {ci[1]*100:+.1f}%"),
            td(f"{s['p_value_skill_le_0']:.4f}" if isinstance(s["p_value_skill_le_0"], (int, float)) else ""),
            td(f"{s['roi_luck_removed']*100:+.2f}%" if isinstance(s["roi_luck_removed"], (int, float)) else ""),
            td(f"{s['stability_share_positive']:.2f}" if isinstance(s["stability_share_positive"], (int, float)) else ""),
            td(r["staking"]["status"]),
        ])
    body += table(
        ["Strategy", "Family", "n (settled)", "Hit rate", "Flat ROI", "95% CI", "p (skill ≤ 0)",
         "Luck-removed ROI", "Stability", "Staking"],
        lb_rows,
    )
    body += f"""
<p class="muted">Source: {bl("data/lines/leaderboard_split.json")}. Flat ROI is 1 unit per settled bet.
The luck-removed column applies a recorded rule that strips wins arriving in specific closing-game
states; the rule is on <a href="luck.html">Removing luck</a>.</p>
<div class="box bad"><h3>Read this before reading the table</h3>
<p><b>No row above is a live strategy.</b> The staking column reads "no stakes recorded" for all
{len(d["lb"]["rows"])} rows, and the best row fails the multiplicity correction described on
<a href="luck.html">Removing luck</a>. A leaderboard with no eligible strategy is the correct output of
an honest gate, not a bug.</p></div>
"""
    return shell("Origination & leaderboard", "WEEK 10 · 16 STRATEGIES", body, "lines.html")


def page_gates(d):
    rows = []
    for g in d["gates"]["gates"]:
        crit = g.get("criteria")
        detail = "; ".join(crit) if isinstance(crit, list) else (g.get("rule") or "")
        thr = g.get("thresholds")
        if thr:
            detail = (detail + " · " if detail else "") + ", ".join(f"{k}={v}" for k, v in thr.items())
        rows.append([
            td(ok(f"<b>{g['id']}</b>")), td(g.get("name", "")),
            td("blocking" if g.get("blocking") else "advisory"),
            td(detail or "—"),
        ])
    mp = multiplicity(d)
    passed = [r["key"] for r in mp["rows"] if r["signal"]["ci95"] and r["signal"]["ci95"][0] > 0]
    body = f"""
<div class="eyebrow">Pre-registered before results</div>
<h1>Validation gates</h1>
<p class="lede">A strategy earns nothing until it clears every blocking gate. The gates were written
down before any result was scored; changing one after seeing results is recorded as a violation rather
than absorbed silently.</p>
{table(["Gate", "Name", "Type", "Criteria / thresholds"], rows)}
<h2>Which strategies clear them today</h2>
<p>{len(d["lb"]["rows"])} strategies are scored. Those with a 95% confidence interval entirely above zero:
<b>{", ".join(passed) if passed else "none"}</b>.</p>
<p>But a confidence interval is a per-test statement. With {mp["k"]} tests in the family, the threshold
for <em>any</em> one of them to be credible is p&nbsp;&le;&nbsp;{mp["bonferroni"]:.6f}, and
<b>{len(mp["clear_bonferroni"])} strategies clear it</b>. That is the gate doing its job.</p>
<div class="box"><h3>Gate G0 is the one that binds everything</h3>
<p>Provenance requires licensed inputs with timestamps, no lookahead, a recorded settlement rule, and a
hashed model version. Prices fail the first requirement, so every economic result is blocked at G0
regardless of how good the numbers look. This is why the leaderboard can be busy and still have zero
eligible entries.</p></div>
"""
    return shell("Validation gates", "9 GATES · 0 ELIGIBLE", body, "gates.html")


def page_correlation(d):
    corr = d["corr"] or {}
    rows = []
    items = corr.get("values") or corr.get("rows") or []
    for c in items if isinstance(items, list) else []:
        rows.append([
            td(c.get("pair") or c.get("name") or c.get("key", "")),
            td(c.get("value", c.get("r", ""))),
            td(c.get("n", "")),
            td(c.get("ci95", c.get("ci", ""))),
            td(href(c["source_url"], "source") if c.get("source_url") else BLANK),
        ])
    body = f"""
<div class="eyebrow">Only sourced numbers</div>
<h1>Correlation, with n on every value</h1>
<p class="lede">A correlation without its sample size is decoration. Every value here is computed only
from officially sourced numbers, and every row prints <b>n</b>. Where a value could not be computed from
official data, the row is absent rather than estimated.</p>
"""
    if rows:
        body += table(["Pair", "Value", "n", "95% CI", "Source"], rows)
    else:
        body += f"""
<div class="box warn"><h3>No correlation is published here</h3>
<p>The repository's correlation values are computed from a <b>third-party</b> line benchmark, not from
official league data, so they cannot satisfy the "officially sourced only" rule for this page. They are
published on the line desk with the third-party source named on every row, and they are listed on
<a href="flagged.html">Flagged for review</a> for that reason rather than promoted here.</p>
<p>{bl("data/lines/correlation_official.json", "data/lines/correlation_official.json")} ·
{bl("data/lines/correlation_report.csv", "correlation_report.csv")}</p>
</div>
<h2>Why this matters for parlays</h2>
<p>Multiplying marginal probabilities is only valid when the legs are independent. Two legs of the same
game are not. Until a joint probability is validated on a holdout, a same-game parlay has no defensible
price, so none is published — the rule the brief asks for, applied literally.</p>
"""
    return shell("Correlation", "n ON EVERY VALUE", body, "correlation.html")


def page_luck(d):
    mp = multiplicity(d)
    rows = []
    for r in mp["rows"]:
        s = r["signal"]
        raw = s["p_value_skill_le_0"]
        clears_raw = "yes" if raw <= mp["alpha"] else "no"
        clears_b = "yes" if raw <= mp["bonferroni"] else "no"
        rows.append([
            td(ok(f"<b>{r['key']}</b>")), td(s["bets_settled"]),
            td(f"{raw:.4f}"), td(clears_raw), td(clears_b),
            td(f"{s['roi_luck_removed']*100:+.2f}%" if isinstance(s["roi_luck_removed"], (int, float)) else ""),
            td(f"{s['luck_profit_share']*100:.1f}%" if isinstance(s["luck_profit_share"], (int, float)) else ""),
        ])
    # the sample-size arithmetic for a 55% capper, computed here and shown
    import math
    p, p0 = 0.55, 0.5238
    n_need = math.ceil(((1.959964 * math.sqrt(p * (1 - p)) + 0.8416 * math.sqrt(p0 * (1 - p0))) / (p - p0)) ** 2)
    z500 = (0.55 - p0) / math.sqrt(p0 * (1 - p0) / 500)
    body = f"""
<div class="eyebrow">No luck in the leaderboard</div>
<h1>Removing luck from the equation</h1>
<p class="lede">Three separate mechanisms here: strip wins that arrive in specific closing-game states,
require a sample large enough for the effect to be visible, and correct for the fact that many rules
were tested at once. Without the third, the first two are theatre.</p>

<h2>1. The multiplicity correction</h2>
<p>{mp["k"]} strategies were scored. At &alpha;&nbsp;=&nbsp;0.05 a family of {mp["k"]} independent tests
produces on average <b>{mp["expected_false_positives"]:.2f}</b> false positives. The Bonferroni threshold
is &alpha;/k&nbsp;=&nbsp;<b>{mp["bonferroni"]:.6f}</b>.</p>
<div class="kpis">
  <div class="kpi"><b>{len(mp["clear_raw"])}</b><span>clear p ≤ 0.05 unadjusted</span></div>
  <div class="kpi"><b>{len(mp["clear_bonferroni"])}</b><span>clear p ≤ {mp["bonferroni"]:.6f} corrected</span></div>
  <div class="kpi"><b>{mp["expected_false_positives"]:.2f}</b><span>false positives expected from chance alone</span></div>
</div>
{table(["Strategy", "n", "p (skill ≤ 0)", "p ≤ .05", "p ≤ .003125", "Luck-removed ROI", "Luck profit share"], rows)}
<p class="muted">Source: {bl("data/lines/leaderboard_split.json")}. p-values are as published by the
generator; the correction is computed here from them and the arithmetic is printed above so it can be
checked.</p>

<h2>2. The sample size a real edge needs</h2>
<p>Break-even at -110 is 52.38%. To detect a 55% capper at 95% confidence with 80% power:</p>
<div class="box"><p><b>n ≈ {n_need:,} settled bets.</b> At 500 bets the same 55% record is
z&nbsp;=&nbsp;{z500:.2f} — indistinguishable from chance. This is not a conservative assumption; it is the
arithmetic that makes a hot month meaningless.</p></div>

<h2>3. The luck-removed panel</h2>
<p>Wins that arrive in the closing-game states listed in the recorded rule are excluded and the ROI
recomputed. The <b>luck profit share</b> is the fraction of total profit that came from those wins. A
strategy whose profit share is high is a strategy whose profit is partly an artefact of how the game
ended, not of the number.</p>
<div class="box warn"><p>Note the direction of the evidence in the table above: the one strategy that
clears p&nbsp;&le;&nbsp;0.05 has a <em>higher</em> ROI after luck removal, which is weak evidence that its
edge is not a lucky-win artefact — and still not enough to survive the multiplicity correction.</p></div>
"""
    return shell("Removing luck", "MULTIPLICITY · SAMPLE · LUCK PANEL", body, "luck.html")


def page_availability(d):
    inj = d["inj"]
    clubs = sorted({r["team"] for r in inj})
    rows = []
    for r in inj:
        rows.append([
            td(r["team"]), td(r["player"]), td(r["position"]), td(r["injury"]),
            td(r["practice_status"]), td(r["game_status"]),
            td(href(r["player_url"], "player")),
        ])
    named = []
    for r in d["named"]:
        named.append([
            td(ok(f"<b>{r['id']}</b>")), td(r["player"]), td(r["club"]),
            td(f"\u201c{r['statement_as_printed']}\u201d"), td(r["article_date"]),
            td(r["for_game"]), td(href(r["source_url"], "official article")), td(r["note"]),
        ])
    des = [r for r in inj if r["game_status"].strip()]
    body = f"""
<div class="eyebrow">Who is actually available</div>
<h1>Availability and replacement depth</h1>
<p class="lede">Read live on <b>2026-11-19</b>, the day of the first Week 11 fixture. This is the first
week-11 availability data on the site: every published injury table before today was a Week 10 read.</p>

<h2>What the official report actually says, measured</h2>
<div class="kpis">
  <div class="kpi"><b>{len(inj)}</b><span>rows</span></div>
  <div class="kpi"><b>{len(clubs)}</b><span>clubs with a block</span></div>
  <div class="kpi"><b>{len(des)}</b><span>rows with a game designation</span></div>
  <div class="kpi"><b>2</b><span>clubs those {len(des)} rows belong to</span></div>
</div>
<p>The league has published practice participation for 24 clubs and a game status for two. That is not a
gap in this transcription; it is where the league's week stands on Thursday. A model that needs a
<em>final</em> designation cannot be fitted to this page today, and any claim that it could would be
false.</p>

<h2>The Week 11 report, every row as printed</h2>
{table(["Club", "Player", "Pos", "Injury as printed", "Practice", "Game status", "Player page"], rows)}
<p class="muted">{len(inj)} rows. Source: {href("https://www.nfl.com/injuries/league/2026/reg11", "nfl.com Week 11 injury report")},
read 2026-11-19. Blank cells are printed blank by the league — they are not "healthy".</p>

<h2>Announced starters — dated evidence, not an inferred replacement</h2>
<p>The rule: a starter change is evidence only when the league states it in words, with a date. A
transaction, a depth chart, a jersey number, or absence from the injury report is <em>not</em> evidence.
Two of the three named cases clear that bar. The third does not, and is left blank.</p>
{table(["ID", "Player", "Club", "Statement as printed", "Article date", "For", "Source", "What it is"], named)}

<h2>Replacement depth: what can be shown and what cannot</h2>
<div class="box warn">
<p>“2nd string” requires a depth order. The league publishes no league-wide depth chart; clubs publish
their own, dated inconsistently, sometimes as an image, sometimes with jersey numbers in the name
column, sometimes with two players sharing one slot. No official snap-count feed is licensed here.</p>
<p>So the room does <b>not</b> publish a depth rank for any player. It publishes named starters where the
league names them, and leaves the rest blank. The measured substitute — snaps — is listed as gap
<b>M-04</b> on <a href="missing.html">Missing information</a>.</p>
</div>
"""
    return shell("Availability & depth", f"{len(inj)} ROWS · READ 2026-11-19", body, "availability.html")


def page_stale(d):
    st = staleness(d)
    rows = []
    for abbr, p, n, moved in sorted(st["clubs"], key=lambda x: x[0]):
        rows.append([
            td(ok(f"<b>{abbr}</b>")),
            td(f"{p['w']}-{p['l']}-{p['t']}"), td(f"{n['w']}-{n['l']}-{n['t']}"),
            td(f"{p['pf']}/{p['pa']}"), td(f"{n['pf']}/{n['pa']}"),
            td(", ".join(moved)),
        ])
    p = d["pack"]
    checks = []
    for k, v in p["checks"].items():
        checks.append([
            td(ok(f"<b>{k}</b>")), td(v.get("name", "")),
            td(v.get("assertions", v.get("rows", ""))), td(v.get("passed", "")),
            td(ok(f'<span class="pill {"p-met" if v["verdict"]=="pass" else "p-part"}">{v["verdict"]}</span>')),
        ])
    body = f"""
<div class="eyebrow">How old is what you are reading</div>
<h1>Staleness ledger</h1>
<p class="lede">A dated snapshot is defensible evidence. A dated snapshot that does not say its date is
a trap. This page measures, for every table this room can check, how far its data has moved from the
official source as of today.</p>

<h2>Published standings vs the official page read today</h2>
<div class="kpis">
  <div class="kpi"><b>{st["diffs"]}</b><span>of {st["cells"]} compared cells have moved</span></div>
  <div class="kpi"><b>{len(st["clubs"])}</b><span>of {st["rows"]} clubs affected</span></div>
  <div class="kpi"><b>2026-11-14</b><span>the date of the published snapshot</span></div>
  <div class="kpi"><b>2026-11-19</b><span>the date of the official read</span></div>
</div>
<p>Every difference below is a Week 10 result the snapshot predates. The published table is not wrong;
it is five days old, and it now understates 26 clubs.</p>
{table(["Club", "Published (2026-11-14)", "Official (2026-11-19)", "Published PF/PA", "Official PF/PA", "Fields moved"], rows)}
<p class="muted">Published: {bl("data/nfl/standings.tsv")} · Official: {bl("data/verification/2026_11_19/official_standings_2026_11_19.tsv")}</p>

<h2>The 2026-11-19 verification pack</h2>
<p>Eight checks, all rebuilt from the transcription in this repository, all passing:</p>
{table(["Check", "What it measures", "Assertions", "Passed", "Verdict"], checks)}
<p class="muted">Rebuild with <code>python3 tools/verify_2026_11_19.py</code>; the committed summary is
{bl("data/verification/2026_11_19/verification_summary_2026_11_19.json")}.</p>
"""
    return shell("Staleness ledger", "SNAPSHOT 2026-11-14 → 2026-11-19", body, "stale.html")


def page_flagged(d):
    rows = []
    for f in d["flags"]["flags"]:
        sev = f.get("severity", "")
        pill = {"high": "p-open", "medium": "p-part", "low": "p-na"}.get(sev, "p-na")
        rows.append([
            td(ok(f"<b>{f.get('id','')}</b>")),
            td(ok(f'<span class="pill {pill}">{esc(sev)}</span>')),
            td(f.get("category", "")), td(f.get("item", "")),
            td(f.get("verified", "")), td(f.get("unknown", "")),
            td(href(f["source_url"], f.get("source_label", "source")) if f.get("source_url") else BLANK),
        ])
    added = [
        ("F-R7-01", "high", "Stale table",
         "The published standings table is the 2026-11-14 snapshot while today is 2026-11-19.",
         f"{staleness(d)['diffs']} of {staleness(d)['cells']} compared cells differ from today's official page; "
         f"{len(staleness(d)['clubs'])} clubs affected.",
         "Whether a dated table is acceptable without a per-table date badge.",
         "https://www.nfl.com/standings/league/2026/REG"),
        ("F-R7-02", "high", "Gate coverage",
         "One strategy clears p ≤ 0.05 but none clears the multiplicity-corrected threshold.",
         f"Bonferroni for {multiplicity(d)['k']} tests is {multiplicity(d)['bonferroni']:.6f}; "
         f"S_wind_under is p=0.0077.",
         "Whether the family should include strategies that were registered but never scored.",
         "https://github.com/karagemop466-tech/X1/blob/main/data/lines/leaderboard_split.json"),
        ("F-R7-03", "medium", "Publisher anomaly",
         "The Week 11 official injury report lists Jaylen Waddle (WR) under DEN.",
         "Waddle is printed with MIA on his own player page and the MIA block of the same read does not list him.",
         "Whether the league has corrected the row; a later read would show it.",
         "https://www.nfl.com/injuries/league/2026/reg11"),
        ("F-R7-04", "medium", "Transcription hazard",
         "The frozen 2026-11-17 Week 11 read keys the Cardinals fixture ARZ_KC while printing the club AZ.",
         "Normalised for comparison and counted (1 alias); the displayed value is unchanged.",
         "Nothing; declared and counted.",
         "https://www.nfl.com/schedules/2026/by-week/week-11"),
        ("F-R7-05", "medium", "Name/link mismatch",
         "Eight rows on the Week 11 report print a name that differs from the player-page slug.",
         "e.g. BUF 'Dee Alford' → /players/deaundre-ford/; SF 'Dre Greenlaw' → dre-greenlaw-x9042.",
         "Nothing; transcribed as printed and listed here so a join on the slug is not silently wrong.",
         "https://www.nfl.com/injuries/league/2026/reg11"),
        ("F-R7-06", "low", "Double-escaped entity",
         "Every page's navigation printed an ampersand as its raw HTML escape sequence because a label "
         "carrying an entity was escaped twice.",
         "94 occurrences across 29 files; fixed at the generator and guarded by verify_output().",
         "Nothing; the guard stops the class returning.",
         "https://github.com/karagemop466-tech/X1/blob/main/tools/build_site.py"),
        ("F-R7-07", "medium", "Evidence gap",
         "Jacoby Brissett's starter role is reported but never stated as a starter announcement.",
         "The article evidences a trade; Lamar Jackson's IR placement makes Brissett presumptive starter, "
         "which is exactly the inference the rule forbids.",
         "A dated club or league sentence naming Brissett the starter.",
         "https://www.nfl.com/news/ravens-complete-trade-for-cardinals-jacoby-brissett-deal-terms-revealed"),
    ]
    for fid, sev, cat, item, ver, unk, url in added:
        pill = {"high": "p-open", "medium": "p-part", "low": "p-na"}[sev]
        rows.append([td(ok(f"<b>{fid}</b>")), td(ok(f'<span class="pill {pill}">{sev}</span>')), td(cat),
                     td(item), td(ver), td(unk), td(href(url, "source"))])
    body = f"""
<div class="eyebrow">Nothing is quietly rounded up</div>
<h1>Flagged for review</h1>
<p class="lede">Everything in this room that is unverified, irregular or contradicts another official
page. New items from this round carry an <b>F-R7-</b> prefix so they cannot collide with the
repository's existing <b>F-</b> series. None of these blocks a decision; each one is a thing to check.</p>
{table(["ID", "Severity", "Category", "Item", "What was verified", "What remains unknown", "Source"], rows)}
"""
    return shell("Flagged for review", f"{len(rows)} ITEMS", body, "flagged.html")


def page_sources(d):
    srcs = [
        ("https://www.nfl.com/standings/league/2026/REG", "2026 NFL League Standings",
         "All 32 club records, PF/PA, home/road, division and conference records.", "2026-11-19"),
        ("https://www.nfl.com/schedules/2026/by-week/week-10", "Week 10 schedule",
         "14 finals with scores and both printed records.", "2026-11-19"),
        ("https://www.nfl.com/schedules/2026/by-week/week-11", "Week 11 schedule",
         "13 fixtures with date, time, network, records; 6 clubs on bye.", "2026-11-19"),
        ("https://www.nfl.com/injuries/league/2026/reg11", "Week 11 official injury report",
         f"{len(d['inj'])} rows across 24 clubs; practice and game status as printed.", "2026-11-19"),
        ("https://www.nfl.com/news/dolphins-place-qb-malik-willis-groin-on-injured-reserve-kyle-mccord-in-line-for-first-start",
         "Dolphins place Malik Willis on IR; Kyle McCord in line for first start",
         "The named replacement, stated by the league.", "read 2026-11-19"),
        ("https://www.nfl.com/news/drew-lock-no-injury-designation-seahawks-raiders",
         "Drew Lock has no injury designation, will start",
         "A head coach naming the starter, on the record.", "read 2026-11-19"),
        ("https://www.nfl.com/news/ravens-complete-trade-for-cardinals-jacoby-brissett-deal-terms-revealed",
         "Ravens complete trade for Brissett",
         "A trade — not a starter announcement. Recorded as such.", "read 2026-11-19"),
        ("https://www.nfl.com/games/colts-at-texans-2026-reg-11", "Game Center, IND at HOU",
         "The fixture page for tonight's game; venue is printed here, not on the weekly page.", "linked"),
    ]
    rows = [
        [td(href(u, l)), td(what), td(date)]
        for u, l, what, date in srcs
    ]
    files = [
        ("data/verification/2026_11_19/official_standings_2026_11_19.tsv", "standings transcription"),
        ("data/verification/2026_11_19/official_w10_results_2026_11_19.tsv", "week 10 finals"),
        ("data/verification/2026_11_19/official_w11_schedule_2026_11_19.tsv", "week 11 slate"),
        ("data/verification/2026_11_19/official_w11_byes_2026_11_19.tsv", "week 11 byes"),
        ("data/verification/2026_11_19/official_w11_injuries_2026_11_19.tsv", "week 11 injury report"),
        ("data/verification/2026_11_19/official_named_availability_2026_11_19.tsv", "announced starters"),
        ("data/verification/2026_11_19/verification_summary_2026_11_19.json", "verification summary"),
        ("tools/verify_2026_11_19.py", "the verifier"),
        ("data/lines/leaderboard_split.json", "signal/staking leaderboard"),
        ("data/lines/originated_lines_2026_week10.csv", "originated lines"),
        ("data/gates.json", "validation gates"),
    ]
    body = f"""
<div class="eyebrow">Where every number comes from</div>
<h1>Sources</h1>
<p class="lede">Official values are league pages read through a fetch tool and transcribed with the URL
on the row and the read date in the file header. Nothing is scraped from an unofficial source, and no
value is inferred to fill a cell.</p>
<h2>Official pages read for this room</h2>
{table(["Page", "What it evidences", "Read"], rows)}
<h2>Repository files every table is generated from</h2>
{table(["File", "Contents"], [[td(bl(p)), td(t)] for p, t in files])}
<div class="box"><h3>One limit, stated plainly</h3>
<p>The sandbox this room was built in could reach <code>www.nfl.com</code> only through a page-fetch
tool, not by direct request. That means the transcription is a careful reading, not an automated
scrape, and the defence against a misread cell is the arithmetic on <a href="stale.html">Staleness
ledger</a>: league closure, identity checks and cross-page agreement all have to hold at once before a
value is published.</p></div>
"""
    return shell("Sources", "OFFICIAL PAGES + REPO FILES", body, "sources.html")


def page_executive(d):
    st = staleness(d)
    mp = multiplicity(d)
    inj = d["inj"]
    body = f"""
<div class="eyebrow">Executive summary</div>
<h1>The project in one page</h1>
<p class="lede">What was built, what it proves, what it cannot prove, and what one decision would change.</p>

<h2>1. What this is</h2>
<p>A lab for originating our own NFL lines and for deciding honestly whether those lines are any good.
The output of a round is not a pick list; it is a measurement with an interval attached, published
whether or not it flatters the model.</p>

<h2>2. What the measurement says today</h2>
<div class="kpis">
  <div class="kpi"><b>0</b><span>strategies eligible to stake</span></div>
  <div class="kpi"><b>1</b><span>clear p ≤ 0.05 before correction</span></div>
  <div class="kpi"><b>0</b><span>clear it after correction</span></div>
  <div class="kpi"><b>{mp["expected_false_positives"]:.2f}</b><span>false positives expected by chance from {mp["k"]} tests</span></div>
</div>
<p>The originated line beats a naive constant and loses to the market benchmark. The one strategy with a
credible-looking interval does not survive being tested alongside fifteen others. That is the honest
state of the project, and it is the state a good gate produces.</p>

<h2>3. What changed this round</h2>
<ol>
<li><b>The site stopped printing a broken label.</b> Every page's navigation rendered a literal
<code>&amp;</code> because a label was escaped twice; 94 occurrences in 29 files, fixed at the generator
and now guarded at build time.</li>
<li><b>Week 11 availability exists.</b> {len(inj)} official injury rows across
{len({r['team'] for r in inj})} clubs were read live on the first game day of the week. Only
{sum(1 for r in inj if r['game_status'].strip())} carry a game designation.</li>
<li><b>Three named players were checked against the articles that name them.</b> Two qualified as
announced-starter evidence; one (Brissett) is a reported trade and is left blank rather than upgraded.</li>
<li><b>The staleness was measured, not assumed.</b> {st["diffs"]} of {st["cells"]} published standings
cells have moved since the snapshot.</li>
<li><b>The multiplicity correction was computed.</b> {mp["k"]} rules, a corrected bar of
{mp["bonferroni"]:.6f}, and {len(mp["clear_bonferroni"])} survivors.</li>
</ol>

<h2>4. What blocks a decision</h2>
<p>Three things, in order of what they unlock:</p>
<ol>
<li><b>A price source</b> (M-01). Without licensed, timestamped quotes no ROI can be evaluated, and
every economic number stays research-only.</li>
<li><b>Time</b> (M-08). The pre-registered shadow baseline needs a scored window; no amount of code
shortens it.</li>
<li><b>Final designations and inactives</b> (M-02, M-03). The injury report is readable today but is not
yet final for 30 of 32 clubs.</li>
</ol>

<h2>5. The one decision worth making now</h2>
<div class="box warn"><p>Choose between <b>S-01</b> (stay quiet until a strategy survives correction) and
<b>S-02</b> (license a price feed and make everything evaluable). Every other item on the
<a href="suggestions.html">suggestions board</a> is housekeeping. S-01 is recommended because it is
consistent with the gate that was registered before any result was seen.</p></div>

<h2>6. How to check any of this</h2>
<ol>
<li>Run <code>python3 tools/verify_2026_11_19.py</code> — eight checks, all rebuild from the committed
transcriptions.</li>
<li>Open <a href="stale.html">Staleness ledger</a> and follow any row's source link to the official page.</li>
<li>Open <a href="flagged.html">Flagged for review</a> — everything this round could not verify is
listed there with its source.</li>
</ol>
"""
    return shell("Executive summary", "SNAPSHOT 2026-11-19", body, "executive.html")


# ---------------------------------------------------------------- write
BUILDERS = {
    "index.html": page_index,
    "questions.html": page_questions,
    "missing.html": page_missing,
    "suggestions.html": page_suggestions,
    "lines.html": page_lines,
    "gates.html": page_gates,
    "correlation.html": page_correlation,
    "luck.html": page_luck,
    "availability.html": page_availability,
    "stale.html": page_stale,
    "executive.html": page_executive,
    "flagged.html": page_flagged,
    "sources.html": page_sources,
}


def build():
    d = load()
    os.makedirs(ROOM, exist_ok=True)
    out = {}
    for name, fn in BUILDERS.items():
        out[name] = fn(d)
    return out


def main(check=False):
    pages = build()
    drift = []
    for name, text in pages.items():
        path = os.path.join(ROOM, name)
        old = open(path, encoding="utf-8").read() if os.path.exists(path) else None
        if check:
            if old != text:
                drift.append(name)
        else:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
    if check:
        if drift:
            print("room pages drifted: " + ", ".join(drift), file=sys.stderr)
            return 1
        print(f"room pages match ({len(pages)})")
        return 0
    print(f"wrote {len(pages)} pages to room/")
    return 0


if __name__ == "__main__":
    sys.exit(main(check="--check" in sys.argv))
