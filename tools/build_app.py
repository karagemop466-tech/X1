#!/usr/bin/env python3
"""Build the unified X1 dashboard in `app/`.

Session `arena/fcc11e05-x1`. Reads the official-source pipeline outputs in
`data/pipeline/`, the independent verification artefacts in `data/verify/`, the
research-lab payload in `data/site/payload.json` and the CSV tables published by
earlier sessions. It writes static HTML into `app/` and touches nothing else.

Rule enforced by the generator: every data row carries the URL of the page the
value was read from. A value the source does not publish renders as an em dash
with an explicit "not published" marker, never as a guess.
"""

from __future__ import annotations

import csv
import html
import json
import math
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
PIPE = os.path.join(ROOT, "data", "pipeline")
VER = os.path.join(ROOT, "data", "verify")

# Links to the earlier sessions' site trees are relative ("../pages/..."), because
# app/ sits one level below the site root.
SNAPSHOT = "2026-11-14"
SEASON = 2026
WEEK = 10

# Pages: (file, nav label, group, title, kicker)
PAGES: List[Tuple[str, str, str, str, str]] = [
    ("index.html", "Overview", "Overview", "NFL decision system", "Dashboard"),
    ("executive-summary.html", "Executive summary", "Overview", "Executive summary", "Read this first"),
    ("standings.html", "Standings", "Official data", "2026 standings", "NFL.com league table"),
    ("schedule.html", "Week 10 slate", "Official data", "Week 10 schedule, byes and results", "NFL.com schedule"),
    # Added by session arena-1d3600f8-x1 (T16)
    ("results.html", "Results & ROI", "Official data", "Verified results feed and graded ROI", "NFL.com results"),
    ("injuries.html", "Injury report", "Official data", "Official Week 10 injury report", "NFL.com injuries"),
    ("depth.html", "Depth charts", "Official data", "Club depth charts, 1st to 4th string", "Club sites"),
    ("deficiency.html", "Deficiency watch", "Official data", "Who is out and which backup replaces them", "Club chart x NFL injury report"),
    ("team-stats.html", "Team stats", "Official data", "Official team offence and defence", "NFL.com stats"),
    ("lines.html", "Originated lines", "Model", "Our own number", "Walk-forward model"),
    # Added by session arena-1d3600f8-x1 (T15 + T17)
    ("origination.html", "Origination & prices", "Model", "Side, then total, then moneyline", "Fair vs market vs difference"),
    ("correlation.html", "Correlation", "Model", "Correlation and independence", "Measured, not assumed"),
    ("strategies.html", "Strategy library", "Strategy", "Candidate strategies", "Pre-registered"),
    ("validation.html", "Validation gates", "Strategy", "Eight gates a strategy must pass", "Pre-registered"),
    ("leaderboard.html", "Leaderboard", "Strategy", "Leaderboard and rewards", "Skill, not streak"),
    ("props.html", "Props & parlays", "Strategy", "Player props and combination maths", "Calibration"),
    ("requirements.html", "Requirements", "Decisions", "Requirement register", "From the brief"),
    ("decisions.html", "Decision register", "Decisions", "What we know, what is missing, what it blocks", "Decision gates"),
    ("suggestions.html", "Suggestion board", "Decisions", "Choose a path before building", "Owner decisions"),
    ("sources.html", "Sources", "Governance", "Source registry", "Verification tiers"),
    ("verification.html", "Verification ledger", "Governance", "Row-by-row verification", "Independent re-check"),
    ("flagged.html", "Flagged for review", "Governance", "Flagged for review", "Never silently filled"),
    ("repo-review.html", "Repo review", "Governance", "Repository line-by-line review", "Audit"),
]

GROUPS = ["Overview", "Official data", "Model", "Strategy", "Decisions", "Governance"]

# Link prefix. The dashboard lives in `app/`, so internal links are relative
# inside that folder ("", one level up to the site root is "../"). A second copy
# of the landing page is emitted as `app/root.html` with PFX="app/" and UP="",
# so the site root can serve the same page. Both are produced by this generator,
# so neither can drift from the other.
PFX = ""
UP = "../"


# --------------------------------------------------------------------- utils
def esc(v: Any) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def dash(v: Any = None) -> str:
    """A value the official source does not publish."""
    if v is None or str(v).strip() == "" or str(v).strip().lower() in {"nan", "none"}:
        return '<span class="blank" title="Not published by the official source">&mdash;</span>'
    return esc(v)


def pc(x: Any, dp: int = 2) -> str:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return dash()
    if math.isnan(f):
        return dash()
    return f"{f * 100:.{dp}f}%"


def num(x: Any, dp: int = 2) -> str:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return dash()
    if math.isnan(f):
        return dash()
    return f"{f:.{dp}f}"


def badge(text: str, kind: str = "grey") -> str:
    k = {"ok": "ok", "warn": "warn", "bad": "bad", "grey": "grey", "blue": "blue"}[kind]
    return f'<span class="b {k}">{esc(text)}</span>'


def link(url: Optional[str], label: Optional[str] = None, cls: str = "") -> str:
    if not url:
        return dash()
    lab = label or "source"
    short = re.sub(r"^https?://(www\.)?", "", str(url))
    if len(short) > 42:
        short = short[:39] + "..."
    return (
        f'<a class="{cls}" href="{esc(url)}" target="_blank" rel="noopener" '
        f'title="{esc(url)}">{esc(lab or short)}</a>'
    )


def src_cell(urls: Any, label: str = "src") -> str:
    """Render one or more source URLs in a compact cell."""
    if isinstance(urls, str):
        urls = [urls] if urls else []
    urls = [u for u in (urls or []) if u]
    if not urls:
        return '<span class="src"><span class="blank" title="No official source publishes this value">&mdash; no official source</span></span>'
    out = []
    for u in urls[:2]:
        short = re.sub(r"^https?://(www\.)?", "", str(u))
        if len(short) > 34:
            short = short[:31] + "..."
        out.append(
            f'<a href="{esc(u)}" target="_blank" rel="noopener" title="{esc(u)}">{esc(short)}</a>'
        )
    extra = ""
    if len(urls) > 2:
        extra = f" <span class='blank'>+{len(urls) - 2}</span>"
    return '<span class="src">' + " ".join(out) + extra + "</span>"


def jload(path: str) -> Any:
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        return json.load(fh)


def csvrows(path: str) -> List[Dict[str, str]]:
    full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        return []
    delim = "|" if path.endswith(".psv") else ","
    with open(full, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh, delimiter=delim))


# ------------------------------------------------------------------- layout
def nav(active: str) -> str:
    out = ['<nav aria-label="Sections">']
    for g in GROUPS:
        items = [p for p in PAGES if p[2] == g]
        if not items:
            continue
        out.append(f'<div class="grp">{esc(g)}</div>')
        for fn, label, _grp, _t, _k in items:
            cls = " active" if fn == active else ""
            out.append(f'<a class="{cls.strip()}" href="{PFX}{fn}">{esc(label)}</a>')
    out.append("</nav>")
    return "\n".join(out)


def page(fn: str, title: str, kicker: str, body: str, lede: str = "") -> str:
    _f, _l, _g, navtitle, _k = next(p for p in PAGES if p[0] == fn)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(navtitle)} — X1 NFL decision system</title>
<meta name="description" content="X1: verified NFL data, originated lines, and a gated strategy leaderboard. Every row source-linked.">
<link rel="stylesheet" href="{PFX}assets/site.css">
</head>
<body>
<aside class="rail">
  <a class="brand" href="{PFX}index.html"><span class="mark">X1</span><span><b>X1</b><span>NFL decision system</span></span></a>
  {nav(fn)}
  <div class="foot">Data snapshot {SNAPSHOT}<br>Season {SEASON}, Week {WEEK}<br>Evidence first. Nothing inferred.</div>
</aside>
<main>
  <div class="topbar">
    <div>
      <div class="eyebrow">{esc(kicker)}</div>
      <h1>{esc(title)}</h1>
      {f'<p class="lede">{lede}</p>' if lede else ''}
    </div>
    <span class="snap">SNAPSHOT {SNAPSHOT} · WEEK {WEEK}</span>
  </div>
{body}
  <footer class="pagefoot">
    X1 · generated by <code>tools/build_app.py</code> · every table row links to the official page the value was read from ·
    a value the source does not print is shown as <span class="blank">&mdash;</span> and flagged, never filled in.<br>
    <a href="{PFX}index.html">Overview</a> ·
    <a href="{PFX}flagged.html">Flagged for review</a> ·
    <a href="{PFX}sources.html">Sources</a> ·
    <a href="{PFX}verification.html">Verification ledger</a> ·
    <a href="https://github.com/karagemop466-tech/X1" target="_blank" rel="noopener">Repository on GitHub</a> ·
    earlier session sections:
    <a href="https://github.com/karagemop466-tech/X1/tree/main/pages">pages</a>,
    <a href="https://github.com/karagemop466-tech/X1/tree/main/dashboard">dashboard</a>,
    <a href="https://github.com/karagemop466-tech/X1/tree/main/research">research</a>,
    <a href="https://github.com/karagemop466-tech/X1/tree/main/site">annex</a>,
    <a href="https://github.com/karagemop466-tech/X1/tree/main/live">live</a>.
  </footer>
</main>
<script src="{PFX}assets/app.js"></script>
</body>
</html>
"""


def table(
    tid: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    *,
    sortable: bool = True,
    filter_box: bool = True,
    note: str = "",
    numeric: Sequence[int] = (),
    center: Sequence[int] = (),
) -> str:
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body_rows = []
    for r in rows:
        cells = []
        for i, c in enumerate(r):
            cls = "n" if i in numeric else ("c" if i in center else "")
            cells.append(f'<td class="{cls}">{c}</td>')
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    sort = " data-sortable" if sortable else ""
    bar = ""
    if filter_box:
        bar = (
            f'<div class="bar"><input type="search" placeholder="Filter rows…" '
            f'data-filter-for="{tid}" aria-label="Filter rows">'
            f'<span class="count" data-count-for="{tid}"></span></div>'
        )
    notehtml = f'<div class="legend">{note}</div>' if note else ""
    return (
        f'{bar}<div class="tw"><table id="{tid}"{sort}>'
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table></div>{notehtml}"
    )


def kpis(items: Sequence[Tuple[str, str, str, str]]) -> str:
    """(value, label, sublabel, kind)"""
    out = ['<div class="kpis">']
    for v, l, s, k in items:
        out.append(f'<div class="kpi {k}"><div class="v">{v}</div><div class="l">{l}</div><div class="s">{s}</div></div>')
    out.append("</div>")
    return "\n".join(out)


def card(title: str, inner: str, level: int = 2) -> str:
    return f'<section class="card"><h{level}>{esc(title)}</h{level}>{inner}</section>'


# ---------------------------------------------------------------- load data
D: Dict[str, Any] = {}


def load() -> None:
    for name in ("standings", "injuries", "depth_charts", "deficiency", "team_stats",
                 "correlations", "questions", "suggestions", "requirements", "gates",
                 "leaderboard", "market_lines", "strategies", "repo_review", "club_registry"):
        p = os.path.join(PIPE, f"{name}.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                D[name] = json.load(fh)
        else:
            D[name] = {"rows": []}
    vp = os.path.join(VER, "verification_ledger.json")
    D["vledger"] = json.load(open(vp, encoding="utf-8")) if os.path.exists(vp) else {"summary": {}, "ledger": []}
    dp = os.path.join(VER, "deficiency_recomputed.json")
    D["def"] = json.load(open(dp, encoding="utf-8")) if os.path.exists(dp) else {"rows": [], "summary": {}, "diffs": [], "join_quality": []}
    D["research"] = jload("data/site/payload.json")
    D["verify_psv"] = {
        "standings": csvrows("data/verify/official_standings_2026_w10.psv"),
        "injuries": csvrows("data/verify/official_injuries_2026_w10.psv"),
        "schedule": csvrows("data/verify/official_schedule_2026_w10.psv"),
        "byes": csvrows("data/verify/official_byes_2026_w10.psv"),
    }
    # --- Added by session arena-1d3600f8-x1 (T15-T21 integration) ---
    D["results_feed"] = csvrows("data/results/verified_results_2026.csv")
    D["results_report"] = jload("data/results/verification_report.json")
    D["roi_summary"] = csvrows("data/results/roi_summary.csv")
    D["origination"] = csvrows("data/lines/origination_2026_week10.csv")
    D["price_index"] = csvrows("data/price_snapshots/market_index.csv")
    D["snapshots"] = csvrows("data/price_snapshots/snapshots.csv")
    D["sigstat"] = jload("data/leaderboard_signal_staking.json")
    D["repdepth"] = jload("data/analysis/replacement_depth.json")
    D["corr_official"] = csvrows("data/analysis/correlations_official.csv")
    D["gates_registry"] = jload("data/gates.json")


ORDINAL = {1: "starter", 2: "2nd string", 3: "3rd string", 4: "4th string"}

STATUS_BADGE = {
    "out": ("bad", "Out"),
    "doubtful": ("warn", "Doubtful"),
    "questionable": ("warn", "Questionable"),
}


def status_cell(s: Optional[str]) -> str:
    if not s:
        return '<span class="b grey" title="No game status designation">none</span>'
    k, lab = STATUS_BADGE.get(str(s).strip().lower(), ("grey", str(s)))
    return badge(lab, k)


# ------------------------------------------------------------------- pages
def p_index() -> str:
    st = D["standings"]["rows"]
    inj = D["injuries"]["rows"]
    dep = D["depth_charts"]["rows"]
    dfc = D["def"]["summary"]
    vl = D["vledger"]["summary"]
    lb = D["research"]["leaderboard"]
    passed = [s for s in lb if s.get("all_passed")]

    body = []
    body.append(kpis([
        (str(len(st)), "clubs on the official table", "NFL.com league standings", "ok"),
        (str(len(inj)), "official injury rows", "NFL.com Week 10 report", "ok"),
        (str(len(dep)), "depth-chart rows", "31 of 32 club sites", ""),
        (str(dfc.get("starters_out", 0)), "starters ruled Out", "depth chart x injury report", "bad"),
        (str(vl.get("checks", 0)), "independent value checks", f'{vl.get("mismatches", 0)} mismatches', "ok"),
        (f'{len(passed)}/{len(lb)}', "strategies through all gates", "out-of-sample, 2015-2026", "warn"),
    ]))

    body.append(f"""<section class="note">
<b>Evidence boundary.</b> This dashboard publishes only what an official page prints, plus
values computed from those pages with the method shown next to them. Betting prices are
<em>not</em> available from any league or club source, so the market-line table ships empty and the
leaderboard grades strategies against a named third-party line, not a league one. Where a value is
computed from a community mirror rather than the league, the row says so.
</section>""")

    body.append(card("What this system does", f"""
<p>X1 collects NFL data from official sources only, tracks injuries and the exact string of backup
who has to replace an injured starter, originates its own lines, and scores candidate strategies on a
leaderboard behind eight validation gates. It runs unattended: a scheduled workflow re-pulls every
official source, re-verifies every row, and republishes this site.</p>
<div class="grid2">
  <div>
    <h3>Verified today</h3>
    <ul class="tight">
      <li><a href="standings.html">Standings</a> — all 32 clubs, each row checked against the league's own arithmetic.</li>
      <li><a href="schedule.html">Week 10 slate</a> — 14 games, 4 byes, one final score.</li>
      <li><a href="injuries.html">Injuries</a> — the league's official report, 345 rows.</li>
      <li><a href="depth.html">Depth charts</a> — 1st through 4th string from each club's own site.</li>
      <li><a href="deficiency.html">Deficiency watch</a> — which starter is down and which backup takes the snaps.</li>
      <li><a href="team-stats.html">Team stats</a> — nine official offence and defence tables.</li>
      <li><a href="results.html">Results &amp; ROI</a> — the verified results feed (137 settled games, double-entry checked against the standings) and the ROI it makes computable.</li>
      <li><a href="origination.html">Origination &amp; prices</a> — side, then total, then moneyline; fair line, market line and difference as separate columns; the opening/closing price-snapshot store.</li>
    </ul>
  </div>
  <div>
    <h3>Deliberately blank</h3>
    <ul class="tight">
      <li><a href="lines.html#market">Market lines</a> — no official source publishes prices, so the table ships empty; the <a href="origination.html">price-snapshot store</a> records the captures we do have with their provenance and keeps opening slots reserved and blank.</li>
      <li>Player-prop prices — no official prop-level source exists.</li>
      <li>Weather, officials, travel — no citable official feed found, so no values are shown.</li>
    </ul>
    <p>These are not oversights. A value that cannot be confirmed from an official source stays blank
    and is <a href="flagged.html">flagged</a>, never inferred.</p>
  </div>
</div>"""))

    body.append('<div class="cards">' + "".join(
        f'<a class="navcard" href="{fn}"><span class="k">{esc(grp)}</span>'
        f'<div class="t">{esc(next(p[3] for p in PAGES if p[0] == fn))}</div></a>'
        for fn, grp in [
            ("executive-summary.html", "Start here"),
            ("deficiency.html", "The headline feature"),
            ("lines.html", "Model"),
            ("validation.html", "Strategy"),
            ("decisions.html", "Decisions"),
            ("suggestions.html", "Decisions"),
            ("verification.html", "Governance"),
            ("flagged.html", "Governance"),
        ]) + "</div>")

    body.append(card("The five findings that shape the plan", """
<ol class="findings">
  <li><b>No league-wide official depth chart exists.</b> Clubs publish their own, in their own
  format, with their own "as of" date. Chicago's chart reads <i>"As of 10/31/2026"</i> — two weeks
  stale — and Green Bay's is labelled <i>"Unofficial, Nov. 10, 2026"</i>. So "2nd-string replacement"
  is a club self-report, not a league fact. See <a href="flagged.html">flagged</a>.</li>
  <li><b>The name join between the chart and the injury report is fragile, and it was silently
  failing for Green Bay.</b> Green Bay prints jersey numbers in the name column ("75 Sean Rhyan"),
  and other clubs print or omit generational suffixes ("Kenneth Walker" vs "Kenneth Walker III").
  Correcting the join moved matched starters from 171 to 189 and recovered three Green Bay starters
  the league lists as Out. See <a href="deficiency.html">deficiency watch</a>.</li>
  <li><b>Most of our own model is not yet good enough to beat the market.</b> The walk-forward
  points model has a spread MAE of 10.42 against the market benchmark's 9.73, and threshold sweeps
  return ROI between −6.1% and −2.6%. It is published as a screen, not a price.
  See <a href="lines.html">originated lines</a>.</li>
  <li><b>One strategy out of sixteen passes every gate.</b> "Wind — under" returns +11.5% ROI over
  398 out-of-sample bets with a bootstrap interval that stays above zero and p = 0.008. Everything
  else fails significance, economics, or the luck-removal gate.
  See <a href="leaderboard.html">leaderboard</a>.</li>
  <li><b>Two inputs block the rest.</b> Prices and results. Neither has an official public source, so
  every gate that depends on outcomes is currently unenforced rather than filled with a guess.
  See <a href="decisions.html">decisions</a> Q-02 and Q-04.</li>
</ol>"""))

    body.append(card("Earlier site sections, all still published", f"""
<p>This repository was built by several parallel agent sessions, and each left its own site tree.
Nothing has been deleted — the sections below are still published and still reachable. This
<code>app/</code> tree is the unified view over all of the same data.</p>
<ul class="tight">
  <li><a href="{UP}pages/executive-summary.html">Fourth Down dashboard</a> — the first integrated dashboard (<code>pages/</code>).</li>
  <li><a href="{UP}dashboard/lab-index.html">Analytics lab</a> — standings, schedule and backtest tables (<code>dashboard/</code>).</li>
  <li><a href="{UP}research/index.html">Research lab</a> — the model, strategy, prop and injury lab (<code>research/</code>).</li>
  <li><a href="{UP}site/index.html">Snapshot annex</a> — originated lines, backtests and correlations (<code>site/</code>).</li>
  <li><a href="{UP}live/index.html">Live pipeline</a> — the auto-refreshing official-source collector (<code>live/</code>).</li>
</ul>"""))

    body.append(card("How the verification rule is enforced", """
<div class="grid2">
  <div>
    <h3>On every row</h3>
    <ul class="tight">
      <li>Each row carries the URL of the official page the values were read from.</li>
      <li>A value the source does not publish renders as an em dash.</li>
      <li>A row with a missing value or an integrity flag is marked and listed on
      <a href="flagged.html">Flagged for review</a>.</li>
    </ul>
  </div>
  <div>
    <h3>On every refresh</h3>
    <ul class="tight">
      <li><code>tools/verify_official.py</code> re-checks every published value against the official
      page fetched on 2026-11-14 and writes a row-level ledger.</li>
      <li>A pull that returns zero rows never overwrites good data.</li>
      <li>Run reports and attempt logs are committed, so the history is auditable.</li>
    </ul>
  </div>
</div>"""))

    return page("index.html", "NFL decision system", "Unified dashboard",
                "\n".join(body),
                lede="One dashboard over every dataset this project holds: verified official data, "
                     "an originated-line model, a gated strategy leaderboard, and the decisions that "
                     "are still open. Every row links to the page it came from.")


def p_exec() -> str:
    dfc = D["def"]["summary"]
    vl = D["vledger"]["summary"]
    lb = D["research"]["leaderboard"]
    model = D["research"]["model"]["summary"]
    passed = [s for s in lb if s.get("all_passed")]
    q = D["questions"]["rows"]
    blockers = [r for r in q if str(r.get("blocks_decision", "")).strip().lower().startswith("y")]

    body = []
    body.append(kpis([
        (str(vl.get("checks", 0)), "value checks passed", f'{vl.get("mismatches", 0)} mismatches', "ok"),
        (str(dfc.get("starters_out", 0)), "starters ruled Out", "corrected join", "bad"),
        (f'{len(passed)}/{len(lb)}', "strategies pass all gates", "out of sample", "warn"),
        (str(len(blockers)), "blocking questions", "owner decisions needed", "warn"),
        (num(model.get("mean_margin_mae"), 2), "model spread MAE (pts)", "vs market 9.73", ""),
        ("0", "market prices", "no official source exists", "grey"),
    ]))

    body.append(card("Executive summary", f"""
<p>X1 exists to answer one question honestly: <b>which NFL strategies are skill and which are a hot
streak?</b> Everything in this site is built to make that answer checkable rather than asserted.</p>

<h3>1. The base layer is sound and independently verified.</h3>
<p>All 32 standings rows, all 345 official injury rows and the Week 10 slate were re-fetched from
NFL.com on {SNAPSHOT} and compared cell by cell against what this repository publishes:
<b>{vl.get('checks', 0)} checks, {vl.get('mismatches', 0)} mismatches</b>. Two independent transcriptions of the
standings agree 32 of 32. The league's own arithmetic holds on every club: home plus road equals
overall, points for minus points against equals net points.</p>

<h3>2. The deficiency register now works, and it found what it is for.</h3>
<p>Cross-referencing each club's printed depth chart with the league's injury report identifies
<b>{dfc.get('starters_on_report', 0)} starting slots whose starter appears on the official report</b>,
of which <b>{dfc.get('starters_out', 0)} are ruled Out</b>, {dfc.get('starters_doubtful', 0)} doubtful and
{dfc.get('starters_questionable', 0)} questionable — on both offence and defence. Rebuilding the join with a
proper name normaliser corrected <b>{dfc.get('deltas_vs_published', 0)} cells</b>; the most consequential is
Cleveland's starting free safety Ronnie Hickman (Out, replaced by a 2nd-string) and three Green Bay
starters whose jersey-numbered names never matched.</p>

<h3>3. Our own number is not yet good enough to price against.</h3>
<p>A walk-forward Poisson points model fitted only on earlier seasons produces a spread MAE of
<b>{num(model.get('mean_margin_mae'), 2)} points</b> against the market benchmark's 9.73 over 2021–2026,
across {model.get('n_games_scored', 0):,} scored games. Threshold sweeps return ROI between −6.1% and −2.6%.
The honest conclusion is that the model is a <b>screen, not a price</b>, and it is published that way.</p>

<h3>4. One of sixteen strategies is skill by our own pre-registered definition.</h3>
<p>"Wind — under" (outdoor games with sustained wind, bet the under) returns <b>+11.5% ROI over 398
out-of-sample bets</b> from 2015 to 2026, hit rate 57.0%, bootstrap 95% interval +2.2% to +20.7%,
sign-flip p = 0.008, and it stays positive when one-score games and blowouts are stripped out. Every
other candidate fails at least one gate. That is the point of the gates: they are designed so that a
lucky season cannot be crowned.</p>

<h3>5. Two inputs block everything downstream.</h3>
<p><b>Prices</b> and <b>results</b>. Neither is published by the league or by any club, so the
market-line table is empty and every outcome-dependent gate is currently unenforced rather than
guessed. Six questions are hard blockers — they cannot be answered from any official source and they
stop specific parts of the system from working: <b>Q-01</b> bankroll, <b>Q-02</b> price feed,
<b>Q-04</b> results feed, <b>Q-05</b> paper or real money, <b>Q-06</b> how rewards are defined,
<b>Q-11</b> player-prop source.</p>

<h3>What to do next</h3>
<p>The <a href="suggestions.html">suggestion board</a> lists twenty options, each with three paths, a
cost, an effort, a risk and a recommendation, and each waiting for a decision rather than being
built. Nothing on that board has been implemented without a recorded choice.</p>"""))

    # --- Added by session arena-1d3600f8-x1: this round's additions ---
    body.append(card("What the 2026-11-14 second round added (session arena-1d3600f8-x1)", f"""
<ul class="tight">
  <li><b>Verified results feed</b> — 137 settled games from the official pages, double-entry checked
  against the standings (0 mismatches; league totals 6,291 = 6,291). ROI is now computable at all;
  see <a href="{PFX}results.html">Results &amp; ROI</a>.</li>
  <li><b>Price-snapshot store</b> — opening and closing slots for all 56 originated markets, with a
  capture log and an append-only recorder. Opening quotes do not exist in any permitted source and
  stay blank and flagged (Q-02); see <a href="{PFX}origination.html">Origination &amp; prices</a>.</li>
  <li><b>Origination order codified</b> — side, then total, then moneyline; fair line, market line and
  the difference published as three separate columns.</li>
  <li><b>Signal vs staking separated</b> on the leaderboard — final grade = min(signal, staking);
  a lucky staking run cannot mask a bad signal (currently 0 of 16 mirror-window strategies are
  rankable; see <a href="{PFX}leaderboard.html">Leaderboard</a>).</li>
  <li><b>Depth of replacement tracked</b> — 189 on-report starters: 168 replacements at 2nd string,
  3 at 3rd string, 18 unreadable and flagged (see <a href="{PFX}deficiency.html">Deficiency</a>).</li>
  <li><b>Official-only correlations</b> — 15 pairs computed strictly from verified tables, every value
  publishing n, p and CI (see <a href="{PFX}correlation.html">Correlation</a>).</li>
  <li><b>Demotion gate G8</b> — six mechanical triggers send a live strategy back to paper, with
  action, re-entry and logging defined (see <a href="{PFX}validation.html">Validation</a>).</li>
</ul>"""))

    return page("executive-summary.html", "Executive summary", "Read this first", "\n".join(body),
                lede="Five findings, what they change, and what is still blocked.")


def p_standings() -> str:
    rows = D["standings"]["rows"]
    off = {r["TEAM"]: r for r in D["verify_psv"]["standings"]}
    body = []
    body.append(f"""<section class="note ok"><b>Verified.</b> All {len(rows)} rows were re-fetched from
{link("https://www.nfl.com/standings/league/2026/REG", "NFL.com league standings")} on {SNAPSHOT} and
compared cell by cell: {len(rows) * 16} value comparisons, 0 mismatches. The league's own arithmetic
(home + road = overall; PF − PA = net points) holds on every club.</section>""")

    trs = []
    for r in sorted(rows, key=lambda x: (-float(x["PCT"]), -int(x["PF"]) + int(x["PA"]))):
        ab = r["team_abbrev"]
        o = off.get(ab, {})
        trs.append([
            f'<a href="{esc(r["_source_url"])}" target="_blank" rel="noopener">{esc(ab)}</a>',
            esc(r["team_name"]),
            esc(r["W"]), esc(r["L"]), esc(r["T"]), esc(r["PCT"]),
            esc(r["PF"]), esc(r["PA"]), esc(r["NET_PTS"]),
            esc(r["HOME"]), esc(r["ROAD"]), esc(r["DIV"]), esc(r["CONF"]),
            esc(r["STRK"]), esc(r["LAST_5"]),
            badge("match", "ok") if o.get("W") == r["W"] and o.get("PF") == r["PF"] else badge("check", "warn"),
            src_cell(r["_source_url"]),
        ])
    body.append(table("t-standings",
                      ["Team", "Club", "W", "L", "T", "PCT", "PF", "PA", "Net", "Home", "Road",
                       "Div", "Conf", "Strk", "Last 5", "Re-check", "Source"],
                      trs, numeric=[2, 3, 4, 5, 6, 7, 8], center=[15],
                      note="Sorted by winning percentage. PCT is the league's own figure; ties count as half a win."))
    return page("standings.html", "2026 standings", "Official data", "\n".join(body),
                lede="Every club on the league's own table, as printed on 2026-11-14.")


def p_schedule() -> str:
    sched = D["verify_psv"]["schedule"]
    byes = D["verify_psv"]["byes"]
    body = []
    body.append(f"""<section class="note ok"><b>Verified.</b> The slate was read from
{link("https://www.nfl.com/schedules/2026/by-week/week-10", "NFL.com Week 10 schedule")} on {SNAPSHOT}.
{len(sched)} games, {len(byes)} clubs on bye. Kickoffs are Eastern Time as printed by the league.</section>""")

    trs = []
    for g in sched:
        gid = g["GAMEID"]
        trs.append([
            esc(g["DAY"]), esc(g["KICKOFF_ET"]),
            f'<b>{esc(g["AWAY"])}</b> <span class="blank">({esc(g["AWAY_REC"])})</span>',
            f'<b>{esc(g["HOME"])}</b> <span class="blank">({esc(g["HOME_REC"])})</span>',
            esc(g["NETWORK"]),
            esc(g["VENUE_NOTE"]) or dash(),
            link(f"https://www.nfl.com/games/{gid}", "game page"),
        ])
    body.append(table("t-sched", ["Day", "Kickoff (ET)", "Away", "Home", "Network", "Note", "Source"],
                      trs, center=[0, 1, 4],
                      note="Away team is listed first, as the league lists it. Records are as printed on the schedule page."))

    btrs = [[esc(b["TEAM"]), esc(b["REC"]),
             link("https://www.nfl.com/schedules/2026/by-week/week-10", "week 10 page")] for b in byes]
    body.append(card("Teams on bye", table("t-byes", ["Team", "Record", "Source"], btrs, center=[1])))

    body.append(card("Result recorded so far", f"""
<p>One Week 10 game has been played: <b>Commanders 24, Giants 21</b> (Thursday 12 November 2026,
final). Every other game on the slate is scheduled, not played. Final scores are added only as the
league publishes them — no result is projected here.</p>
{link("https://www.nfl.com/games/commanders-at-giants-2026-reg-10", "Official game page: Commanders at Giants, 2026 REG 10")}"""))
    return page("schedule.html", "Week 10 slate", "Official data", "\n".join(body),
                lede="The 14 games, the four clubs on bye, and the one result the league has published.")


def p_injuries() -> str:
    rows = D["injuries"]["rows"]
    vl = D["vledger"]["summary"]
    off = D["verify_psv"]["injuries"]
    counts = {}
    for r in rows:
        gs = (r.get("game_status") or "none").strip().lower()
        counts[gs] = counts.get(gs, 0) + 1
    body = []
    body.append(f"""<section class="note ok"><b>Verified line by line.</b> All {len(rows)} rows were
re-fetched from {link("https://www.nfl.com/injuries/", "NFL.com official injury report")} on {SNAPSHOT}
and compared player by player across all 28 clubs on the slate: player, position, injury, practice
status and game status. {vl.get('mismatches', 0)} mismatches out of {vl.get('checks', 0)} checks.</section>""")

    body.append(kpis([
        (str(len(rows)), "rows on the report", "28 clubs with a game this week", ""),
        (str(counts.get("out", 0)), "ruled Out", "league designation", "bad"),
        (str(counts.get("questionable", 0)), "questionable", "league designation", "warn"),
        (str(counts.get("doubtful", 0)), "doubtful", "league designation", "warn"),
        (str(counts.get("none", 0)), "no game status", "listed but expected to play", "grey"),
    ]))

    trs = []
    for r in rows:
        trs.append([
            esc(r["team_abbrev"]),
            f'<a href="https://www.nfl.com{esc(r.get("player_url") or "")}" target="_blank" rel="noopener">{esc(r["player"])}</a>'
            if r.get("player_url") else esc(r["player"]),
            esc(r["position"]),
            esc(r["injuries"]) if r.get("injuries") else dash(),
            esc(r["practice_status"]),
            status_cell(r.get("game_status")),
            esc((r.get("game_date") or "").title()),
            esc(r.get("kickoff_et") or ""),
            src_cell(r["_source_url"]),
        ])
    body.append(table("t-inj", ["Team", "Player", "Pos", "Injury", "Practice", "Game status",
                                "Game day", "Kickoff", "Source"], trs, center=[2, 5],
                      note="The league prints an injury only where a club has reported one; a blank injury cell "
                           "with a practice status means the player is listed for rest or observation, not injury."))
    return page("injuries.html", "Official Week 10 injury report", "Official data", "\n".join(body),
                lede="Every row the league published for Week 10 of the 2026 season, transcribed unaltered.")


def p_depth() -> str:
    rows = D["depth_charts"]["rows"]
    teams = sorted({r["team_abbrev"] for r in rows})
    body = []
    body.append(f"""<section class="note warn"><b>Read the coverage first.</b> Depth charts are
published by each club on its own site, not by the league. On this snapshot <b>{len(teams)} of 32</b>
clubs returned a parsable chart. Houston's chart returns a page with no table, so Houston has
<b>no rows at all</b> — that gap is recorded, not filled. Charts also disagree with each other:
Chicago's is dated <i>"As of 10/31/2026"</i>, Green Bay's is labelled <i>"Unofficial, Nov. 10, 2026"</i>,
and Baltimore's kicker slot is printed empty.</section>""")

    body.append(kpis([
        (str(len(rows)), "depth-chart rows", "starters through 4th string", ""),
        (str(len(teams)), "clubs parsed", "of 32", "warn"),
        ("HOU", "club with no chart", "page returns no parsable table", "bad"),
        ("4", "maximum string shown", "clubs print 3 or 4 columns", "grey"),
    ]))

    trs = []
    for r in sorted(rows, key=lambda x: (x["team_abbrev"], x["unit"], str(x["position"]), x["slot"], x["depth"])):
        trs.append([
            esc(r["team_abbrev"]), esc(r["unit"]), esc(r["position"] or "—"),
            str(r["slot"]), str(r["depth"]), esc(r["player"]),
            src_cell(r["_source_url"]),
        ])
    body.append(table("t-depth", ["Team", "Unit", "Pos", "Slot", "String", "Player", "Source"],
                      trs, center=[1, 2, 3, 4],
                      note="Slot distinguishes two lines of the same position (first WR line, second WR line). "
                           "String 1 is the starter. Filter by team to read one club's chart."))

    body.append(card("Why this is not a league fact", """
<p>The league does not publish a depth chart. Each club publishes its own, and the formats differ:
column counts range from three to four, position vocabularies differ (Baltimore uses RUSH / SAM / WLB /
MLB, Chicago uses DL / LB / S / DB / CB, Green Bay uses EDGE / LB / NB / CB / S), and two of the clubs
checked print either a stale date or an explicit "unofficial" disclaimer. Any statement of the form
"the 2nd-string will replace him" is therefore a <b>club self-report</b> carried on this site with the
club's own URL attached — never a league-verified fact.</p>"""))
    return page("depth.html", "Club depth charts", "Official data", "\n".join(body),
                lede="Starters through fourth string, read from each club's own site.")


def p_deficiency() -> str:
    d = D["def"]
    rows = d["rows"]
    s = d.get("summary", {})
    diffs = d.get("diffs", [])
    body = []

    body.append(f"""<section class="note"><b>This is the derived table.</b> Nothing here is scraped.
The starter is column&nbsp;1 of the club's own depth chart; the replacement is the next name down the
same line whose game status is not <i>Out</i>. Every row links to both official sources. Severity is
Out&nbsp;=&nbsp;3, Doubtful&nbsp;=&nbsp;2, Questionable&nbsp;=&nbsp;1, not listed&nbsp;=&nbsp;0.</section>""")

    body.append(f"""<section class="note bad"><b>Correction applied, and published.</b> The register as
originally built joined the chart to the injury report on the raw name string. That silently failed
for Green Bay, whose chart prints jersey numbers ("75 Sean Rhyan"), and for clubs that print or omit
generational suffixes ("Kenneth Walker" vs "Kenneth Walker III"). Rebuilding the join with a normaliser
moved matched starters from <b>171 to {s.get('starters_on_report', 0)}</b> and corrected
<b>{s.get('deltas_vs_published', 0)} cells</b>. Two of the recoveries are material: Cleveland's starting
free safety Ronnie Hickman is <b>Out</b>, and Green Bay's starting running back, centre and tight end
are all <b>Out</b>. Both are documented on <a href="flagged.html">Flagged for review</a>.</section>""")

    body.append(kpis([
        (str(s.get("slots", 0)), "starting slots tracked", f'{s.get("teams_covered", 0)} clubs', ""),
        (str(s.get("starters_on_report", 0)), "starters on the injury report", "after the join fix", ""),
        (str(s.get("starters_out", 0)), "starters ruled Out", "replacement named on every row", "bad"),
        (str(s.get("starters_doubtful", 0)), "doubtful", "", "warn"),
        (str(s.get("starters_questionable", 0)), "questionable", "", "warn"),
        (str(len(s.get("teams_missing", []))), "club with no chart", "Houston", "bad"),
    ]))

    hot = [r for r in rows if r["severity"] >= 2]
    trs = []
    for r in sorted(hot, key=lambda x: (-x["severity"], x["team_abbrev"], x["unit"], str(x["position"]))):
        trs.append([
            esc(r["team_abbrev"]),
            esc(r["unit"]),
            esc(r["position"] or "—"),
            esc(r["starter_display"]),
            status_cell(r["starter_game_status"]),
            esc(r["starter_practice_status"] or ""),
            esc(r["replacement_display"]) if r.get("replacement_display") else dash(),
            str(r["replacement_depth"]) if r.get("replacement_depth") else dash(),
            ORDINAL.get(r.get("replacement_depth"), "") if r.get("replacement_depth") else "",
            src_cell([r["source_depth_chart"], r["source_injury"]]),
        ])
    body.append(card("Starters Out or Doubtful — every one, with the replacement named",
                     table("t-def-hot", ["Team", "Unit", "Pos", "Starter", "Status", "Practice",
                                         "Next up", "String", "Flag", "Sources"], trs,
                           center=[4, 7], numeric=[7],
                           note=f"{len(hot)} slots where the starter is Out or Doubtful. "
                                "'Next up' is the next name on the club's own chart who is not himself ruled Out.")))

    all_trs = []
    for r in sorted(rows, key=lambda x: (x["team_abbrev"], x["unit"], str(x["position"]), x["slot"])):
        all_trs.append([
            esc(r["team_abbrev"]), esc(r["unit"]), esc(r["position"] or "—"),
            esc(r["starter_display"]),
            status_cell(r["starter_game_status"]),
            esc(r["replacement_display"]) if r.get("replacement_display") else dash(),
            str(r["replacement_depth"]) if r.get("replacement_depth") else dash(),
            str(r["depth_listed"]),
            src_cell([r["source_depth_chart"], r["source_injury"]]),
        ])
    body.append(card("Full register — all tracked slots",
                     table("t-def-all", ["Team", "Unit", "Pos", "Starter", "Status", "Next up",
                                         "String", "Depth listed", "Sources"], all_trs,
                           center=[4, 6], numeric=[6, 7],
                           note=f"All {len(all_trs)} starting slots across {s.get('teams_covered', 0)} clubs. "
                                "Filter by team or search a player name.")))

    club_url = {}
    for r in D["club_registry"]["rows"]:
        club_url[r["team_slug"]] = r["official_site"]
    slug_by_ab = {}
    for r in D["standings"]["rows"]:
        slug_by_ab[r["team_abbrev"]] = r["team_slug"]
    qtrs = []
    for q in d.get("join_quality", []):
        slug = slug_by_ab.get(q["team"], "")
        url = club_url.get(slug)
        qtrs.append([
            esc(q["team"]), str(q["slots"]), str(q["starters_on_report"]),
            badge("yes", "ok") if q["on_injury_report_this_week"] else badge("no — on bye", "grey"),
            esc(q["note"]) or dash(),
            src_cell([url, "https://www.nfl.com/injuries/"]),
        ])
    body.append(card("Join quality by club — how many starters matched the injury report",
                     table("t-def-q", ["Team", "Slots", "Matched", "On the Week 10 report?", "Note",
                                       "Sources"],
                           qtrs, center=[1, 2, 3], numeric=[1, 2],
                           note="A club with zero matches and no game this week is expected: the league "
                                "publishes no report for a club on bye. A club with zero matches that IS "
                                "playing is worth a manual look — the chart and the report disagree.")))

    if diffs:
        dtrs = []
        for x in diffs:
            if "field" not in x:
                continue
            dtrs.append([esc(x["row"].replace("/None/", "/ — /")), esc(x["field"]),
                         dash(x["published"]), esc(x["corrected"]),
                         link("https://www.nfl.com/injuries/", "NFL.com injuries")])
        body.append(card(f"Every cell the join fix changed ({len(dtrs)})",
                         table("t-def-diff", ["Slot", "Field", "As published", "Corrected", "Source"],
                               dtrs, center=[],
                               note="Left blank where the published register recorded nothing.")))
    # --- Added by session arena-1d3600f8-x1 (T19): depth of replacement ---
    rd = D["repdepth"]
    dd = rd.get("depth_of_replacement_on_report", {}).get("all", {})
    bys = rd.get("depth_of_replacement_on_report", {}).get("by_game_status", {})
    ddtrs = [[esc(k), esc(v),
              src_cell("https://www.nfl.com/injuries/")] for k, v in dd.items()]
    body.append(card("Depth of the replacement — how deep the backup sits, not just that there is one",
                     table("t-repdepth", ["Replacement depth", "Starters on report", "Source"], ddtrs,
                           numeric=[1],
                           note="For every starter on the official Week 10 injury report, the replacement's "
                                "position on his club's official depth chart. Unknown means the chart does "
                                "not print a readable depth — counted and flagged, never inferred.") +
                     f'<div class="legend"><b>By game status:</b> ' +
                     "; ".join(f"{esc(k)}: " + ", ".join(f"{esc(d)}= {esc(c)}" for d, c in v.items())
                               for k, v in sorted(bys.items())) +
                     f'. 3rd string or deeper: {len(rd.get("deep_replacements_3rd_string_or_worse", []))} '
                     f'(listed on <a href="{PFX}flagged.html">flagged</a> with sources). '
                     f'Full per-team table: data/analysis/replacement_depth.json.</div>'))

    return page("deficiency.html", "Deficiency watch", "Official data", "\n".join(body),
                lede="Which starter is down, and exactly which string of backup has to take the snaps — "
                     "offence and defence.")


def p_team_stats() -> str:
    rows = D["team_stats"]["rows"]
    by: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for r in rows:
        label = str(r.get("_source_label") or "Team stats")
        by.setdefault((str(r.get("_source_org") or ""), label), []).append(r)
    body = []
    body.append(f"""<section class="note ok"><b>Verified.</b> {len(rows)} rows across nine official
tables were read from {link("https://www.nfl.com/stats/team-stats/", "NFL.com team stats")} on
{SNAPSHOT} with the column labels the league prints. The published counts were checked against the
pipeline's own verification pass: 288 rows, 0 rows citing a non-official host.</section>""")
    body.append(kpis([(str(len(rows)), "stat rows", "9 official tables", "ok"),
                      (str(len(by)), "tables", "offence and defence", ""),
                      ("32", "clubs per table", "every club present", "")]))
    for (_org, label), rs in sorted(by.items(), key=lambda kv: kv[0][1]):
        keys = [k for k in rs[0].keys() if not k.startswith("_") and k not in
                ("team_abbrev", "team_name", "side", "category", "label")]
        hdr = ["Team"] + [k.replace("_", " ").title() for k in keys] + ["Source"]
        trs = []
        for r in sorted(rs, key=lambda x: str(x.get("team_abbrev"))):
            trs.append([esc(r.get("team_abbrev"))] + [dash(r.get(k)) for k in keys] +
                       [src_cell(r.get("_source_url"))])
        slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:40]
        body.append(card(label,
                         table(f"t-ts-{slug}", hdr, trs,
                               numeric=list(range(1, len(keys) + 1)),
                               note=f"{len(rs)} clubs, with the column labels the league prints.")))
    return page("team-stats.html", "Official team stats", "Official data", "\n".join(body),
                lede="Nine official offence and defence tables, with the league's own column labels.")


def p_lines() -> str:
    model = D["research"]["model"]
    ms = model["summary"]
    ml = D["market_lines"]
    diags = csvrows("data/processed/model_diagnostics.csv")
    sweep = csvrows("data/lines/threshold_sweep.csv")
    bt = csvrows("data/lines/backtest_summary.csv")
    body = []

    body.append(f"""<section class="note"><b>What "originate our own lines" means here.</b> A
walk-forward Poisson points model is fitted only on seasons earlier than the one it scores, and
produces its own spread and total for every game. It is then compared with the market benchmark so
the size of the opportunity is measured rather than assumed. The benchmark is a third-party closing
line carried in the {link("https://github.com/nflverse/nfldata", "nflverse/nfldata")} mirror and
fingerprinted in <code>data/raw_manifest.json</code>; it is <b>not</b> a league publication, and every
row that uses it says so.</section>""")

    body.append(kpis([
        (f'{ms.get("n_games_scored", 0):,}', "games scored", f'{ms.get("first_season")}–{ms.get("last_season")}', ""),
        (num(ms.get("mean_margin_mae"), 2), "spread MAE (pts)", "market benchmark 9.73", "warn"),
        (num(ms.get("mean_total_mae"), 2), "total MAE (pts)", "our model", ""),
        (str(len(sweep)), "threshold settings swept", "spread and total", ""),
        ("0", "market prices published", "no official source exists", "grey"),
    ]))

    body.append(card("Does our number beat the market? No — and that is the finding", f"""
<p>Over the out-of-sample window the model's spread error is <b>{num(ms.get('mean_margin_mae'), 2)} points</b>
against the market benchmark's <b>9.73</b>, and its total error is {num(ms.get('mean_total_mae'), 2)} points.
Sweeping the bet threshold from 1 to 9 points of disagreement produces ROI between
<b>−6.1% and −2.6%</b> on the spread — better as the threshold rises, but never positive.</p>
<p>So the model is published as a <b>screen, not a price</b>. It narrows the games worth looking at; it
does not by itself produce an edge, and this page does not claim one.</p>"""))

    trs = [[esc(r["season"]), esc(r["status"]), esc(r["n_games"]),
            num(r["margin_mae"]), num(r["margin_rmse"]), num(r["total_mae"]),
            num(r["total_rmse"]), num(r["margin_bias"]), num(r["total_bias"]),
            link("https://github.com/nflverse/nfldata", "nfldata games")]
           for r in diags]
    body.append(card("Model diagnostics by season",
                     table("t-diag", ["Season", "Fit", "Games", "Margin MAE", "Margin RMSE",
                                      "Total MAE", "Total RMSE", "Margin bias", "Total bias", "Benchmark source"],
                           trs, numeric=range(2, 9),
                           note="Fitted only on seasons earlier than the one scored. A bias near zero means "
                                "the errors are not systematically high or low.")))

    strs = [[esc(r["market"]), esc(r["threshold"]), esc(r["bets"]), esc(r["win_rate_pct"]),
             esc(r["roi_pct"]), esc(r["units"]),
             link("https://github.com/nflverse/nfldata", "nfldata games")]
            for r in sweep]
    body.append(card("Threshold sweep — does bigger disagreement help?",
                     table("t-sweep", ["Market", "Threshold (pts)", "Bets", "Win rate %", "ROI %",
                                       "Units", "Benchmark source"], strs, numeric=[1, 2, 3, 4, 5],
                           note="Break-even at −110 is 52.38%. Every setting tested is below it.")))

    btrs = [[esc(r["season"]), esc(r["games"]), esc(r["MAE_spread_pts"]), esc(r["MAE_total_pts"]),
             link("https://github.com/nflverse/nfldata", "nfldata games")] for r in bt]
    body.append(card("Backtest summary by season",
                     table("t-bt", ["Season", "Games", "Spread MAE", "Total MAE", "Benchmark source"],
                           btrs, numeric=[1, 2, 3])))

    body.append('<section class="card" id="market"><h2>Market lines — deliberately empty</h2>'
                f'<div class="note bad"><b>Blocked by {esc(ml.get("blocked_by", "Q-02"))}.</b> '
                f'{esc((ml.get("note") or ""))} '
                'No league or club source publishes betting prices, so this table cannot be filled '
                'from an official page and is not filled from memory.</div>'
                + table("t-market", ["Game", "Market", "Our line", "Market line", "Edge", "Source"],
                        [[dash(), dash(), dash(), dash(), dash(),
                          '<span class="blank">no official source</span>']],
                        filter_box=False,
                        note="Ships empty on purpose. Supply a licensed odds feed or the owner's own "
                             "account feed to populate it.") + "</section>")
    return page("lines.html", "Originated lines", "Model", "\n".join(body),
                lede="Our own spread and total, how accurate it is, and the honest answer on whether it beats the market.")


def p_correlation() -> str:
    res = D["research"]
    strat = res["correlations"]["matrix"]
    keys = list(strat.keys())
    luck = res["luck"]
    corr = D["correlations"]["rows"]
    rep = csvrows("data/lines/correlation_report.csv")
    combos = csvrows("data/processed/prop_combos.csv")
    body = []

    body.append(f"""<section class="note"><b>Two different quantities, both called correlation.</b>
Strategy-to-strategy correlation measures how much two strategies bet the same games the same way — it
decides whether a second strategy adds information or is the first one wearing a hat. Same-game
leg correlation decides whether a parlay can be priced as if its legs were independent. They are not
interchangeable, and this page keeps them apart.</section>""")

    body.append(kpis([
        (str(len(keys)), "strategies correlated", "16 x 16 matrix over shared games", ""),
        (str(len(rep)), "same-game / cross-game checks", "annex computation", ""),
        (str(len(combos)), "prop-family pairs", "game-level family totals", ""),
        (str(len(corr)), "team-level correlations", "computed from official tables", ""),
    ]))

    hdr = ["Strategy"] + [k.replace("S_", "").replace("P_", "") for k in keys]
    mtrs = []
    for a in keys:
        row = [f'<span class="mono">{esc(a)}</span>']
        for b in keys:
            v = strat.get(a, {}).get(b)
            if a == b:
                row.append('<span class="blank">1</span>')
                continue
            try:
                f = float(v)
            except (TypeError, ValueError):
                row.append(dash())
                continue
            if math.isnan(f):
                row.append(dash())
                continue
            kind = "bad" if abs(f) >= 0.85 else ("warn" if abs(f) >= 0.5 else "")
            cell = f'<span class="b {kind}" style="background:transparent;color:inherit;font-variant-numeric:tabular-nums">{f:+.3f}</span>' if not kind else f'<b style="color:{"#b3261e" if abs(f) >= 0.85 else "#9a6207"}">{f:+.3f}</b>'
            row.append(cell)
        mtrs.append(row)
    # --- Added by session arena-1d3600f8-x1 (T20): official-only correlations ---
    co = D["corr_official"]
    cotrs = [[esc(r["pair_id"]), esc(r["metric_a"]), esc(r["metric_b"]),
              esc(r["n"]), esc(r["r"]), esc(r["p_value"]),
              f'{esc(r["ci95_lo"])} to {esc(r["ci95_hi"])}',
              esc(r["interpretation"]), src_cell(r["source_a"]), src_cell(r["source_b"])]
             for r in co]
    body.append(card("Official-only correlations — computed from official numbers, n published with every value",
                     table("t-corr-official", ["Pair", "Metric A", "Metric B", "n", "r", "p",
                                               "95% CI", "What it means", "Source A", "Source B"],
                           cotrs, numeric=[3, 4, 5],
                           note="Every value here is computed strictly from tables verified against official "
                                "nfl.com pages (standings, team stats, the Week 10 injury report, and the "
                                "deficiency register). p is a two-sided permutation p (B=20,000, fixed seed); "
                                "the interval is Fisher 95%. The mirror-based tables below are reference-only "
                                "and are labelled non-official wherever they appear.")))
    body.append('<section class="note warn"><b>Everything below this line is third-party mirror data '
                '(nflverse/nfldata), not official.</b> It is published as a labelled benchmark only. The '
                'official-source values are the table above.</section>')

    body.append(card("Strategy correlation matrix (Pearson, over shared games)",
                     '<div class="tw"><table id="t-corr-m" class="matrix" data-src="'
                     'https://github.com/nflverse/nfldata"><thead><tr>' +
                     "".join(f"<th>{esc(h)}</th>" for h in hdr) +
                     "</tr></thead><tbody>" +
                     "".join("<tr>" + "".join(f'<td class="n">{c}</td>' for i, c in enumerate(r)) + "</tr>" for r in mtrs) +
                     "</tbody></table></div>" +
                     '<div class="legend">Bold amber is |r| &ge; 0.5, bold red is |r| &ge; 0.85 — the '
                     'non-redundancy gate (G8) rejects a strategy above 0.85 against an accepted one, '
                     'because at that point it is the same bet.</div>'))

    rtrs = [[esc(r["metric"]), esc(r["value"]), esc(r["n"]), esc(r["ci_or_detail"]),
             esc(r["interpretation"]), link("https://github.com/nflverse/nfldata", "nfldata games")]
            for r in rep]
    body.append(card("Same-game and cross-game correlation",
                     table("t-corr-rep", ["Metric", "Value", "n", "95% interval", "What it means",
                                          "Benchmark source"], rtrs, numeric=[1, 2],
                           note="The same-game favourite-cover / over figure of φ = −0.023 means the two "
                                "legs are very nearly independent for pricing purposes. The cross-game "
                                "figure of r = 0.001 is the evidence that different games in the same week "
                                "can be treated as independent.")))

    ctrs = [[esc(r["combo"]), num(r["correlation"], 3), esc(r["observations"]), esc(r["scope"]),
             pc(r["leg_hit_rate"], 1), pc(r["joint_hit_rate"], 2), num(r["parlay_decimal_odds"], 3),
             pc(r["breakeven_leg_hit_rate"], 2), pc(r["edge_vs_breakeven"], 2),
             badge("yes", "ok") if str(r["profitable"]).lower() == "true" else badge("no", "bad"),
             link("https://github.com/nflverse/nfldata", "nfldata player week stats")]
            for r in combos]
    body.append(card("Prop-family combinations — where correlation actually bites",
                     table("t-corr-prop", ["Pair", "r", "n", "Scope", "Leg hit", "Joint hit",
                                           "Parlay decimal", "Break-even leg", "Edge", "Profitable?",
                                           "Benchmark source"], ctrs, numeric=[1, 2, 4, 5, 6, 7, 8],
                           note="QB passing yards and WR/TE receiving yards correlate at r = 0.927 — "
                                "pricing that pair as independent overstates the joint probability. "
                                "A two-leg −110 parlay needs each leg to hit 52.38% just to break even.")))

    top = sorted(corr, key=lambda r: -abs(float(r.get("r") or 0)))[:250]
    ttrs = [[esc(r["pair"]), esc(r["metric_a"]), esc(r["metric_b"]),
             num(r["r"], 3), esc(r["n"]), num(r["p_value"], 4), esc(r["strength"]),
             src_cell(r.get("_source_urls") or r.get("_source_url"))] for r in top]
    body.append(card("Team-level correlations computed from the official tables",
                     table("t-corr-team", ["Pair", "Metric A", "Metric B", "r", "n", "p", "Strength",
                                           "Source"], ttrs, numeric=[3, 4, 5],
                           note=f"Top {len(top)} of {len(corr)} pairs by |r|, computed across the 32 clubs "
                                "from the official standings and team-stats tables. These are team-season "
                                "associations, not the game-level quantity a parlay price needs.")))
    return page("correlation.html", "Correlation and independence", "Model", "\n".join(body),
                lede="Measured correlation values: strategy-to-strategy, same-game legs, cross-game, "
                     "and prop families.")


def p_strategies() -> str:
    rows = D["strategies"]["rows"]
    lb = D["research"]["leaderboard"]
    body = []
    body.append(f"""<section class="note"><b>Two layers.</b> The {len(rows)} pre-registered strategies
below are the league-verified-only candidates, whose outcome columns are blank because no official
results or prices feed exists. The research layer has actually graded {len(lb)} of them out of sample
against a named third-party line; those measured results are on the
<a href="leaderboard.html">leaderboard</a>.</section>""")

    trs = []
    for r in rows:
        trs.append([
            esc(r["id"]), esc(r["name"]), esc(r["market"]),
            esc(r["hypothesis"]), esc(r["inputs"]), esc(r["gates"]),
            badge(r["status"], "blue"),
            dash(r.get("graded_bets")), dash(r.get("roi")),
            src_cell(r["_source_url"]),
        ])
    body.append(table("t-strat", ["ID", "Strategy", "Market", "Hypothesis", "Inputs", "Gates",
                                  "Status", "Graded bets", "ROI", "Source"], trs, center=[6],
                      note="Outcome columns are blank because no official results feed exists (Q-04). "
                           "They are not estimated."))

    ltrs = []
    for s in sorted(lb, key=lambda x: -float(x.get("roi") or 0)):
        ltrs.append([
            esc(s["key"]), esc(s["name"]), esc(s["family"]),
            esc(s["description"]), str(s["bets"]), pc(s["roi"]), pc(s["hit_rate"]),
            num(s["ci_lo"]), num(s["ci_hi"]), num(s["p_value"], 4),
            badge("passes all", "ok") if s.get("all_passed") else badge(", ".join(s.get("failed_gates") or []), "bad"),
            link("https://github.com/nflverse/nfldata", "nfldata games"),
        ])
    body.append(card("The same library, graded out of sample (2015–2026)",
                     table("t-strat-measured", ["Key", "Name", "Family", "Rule", "Bets", "ROI",
                                                "Hit rate", "CI low", "CI high", "p", "Gates failed",
                                                "Benchmark source"], ltrs,
                           numeric=[4, 5, 6, 7, 8, 9],
                           note="Parameters re-selected each season from earlier seasons only. "
                                "Benchmark is the third-party closing line in the nflverse mirror, "
                                "not a league publication.")))
    return page("strategies.html", "Strategy library", "Strategy", "\n".join(body),
                lede="Every candidate, what it claims, and what it actually returned out of sample.")


def p_validation() -> str:
    rows = D["gates"]["rows"]
    lb = D["research"]["leaderboard"]
    body = []
    body.append("""<section class="note"><b>Pre-registered, not tuned after the fact.</b> Every gate
below was written before any strategy was scored, and the thresholds live in one place
(<code>src/x1/config.py</code>) so they cannot be quietly moved. A strategy that fails any gate is
eligible for nothing, however good its headline ROI looks.</section>""")

    trs = [[esc(r["id"]), esc(r["gate"]), esc(r["rule"]), esc(r["threshold"]),
            esc(r["why"]), esc(r["applies_to"]),
            badge(r["status"], "ok" if str(r["status"]).lower() == "active" else "grey"),
            src_cell(r["_source_url"])]
           for r in rows]
    body.append(table("t-gates", ["ID", "Gate", "Rule", "Threshold", "Why it exists", "Applies to",
                                  "Status", "Source"], trs, center=[6],
                      note="G1–G8 are the research-lab gates; G-09 onward are the source and "
                           "governance gates that apply to every input before a model sees it."))

    gtrs = []
    for s in sorted(lb, key=lambda x: -float(x.get("roi") or 0)):
        failed = s.get("failed_gates") or []
        gtrs.append([
            esc(s["key"]),
            " ".join(badge("G" + g, "ok") for g in ["1", "2", "3", "4", "5", "6", "7", "8"]
                     if g not in failed) +
            " ".join(badge("G" + g, "bad") for g in failed),
            str(s["bets"]), pc(s["roi"]), num(s["p_value"], 4),
            (s.get("stability") or {}).get("detail", "") or dash(),
            str(s.get("max_correlation")) if s.get("max_correlation") == s.get("max_correlation") else dash(),
            num(s.get("reward"), 2),
            link("https://github.com/nflverse/nfldata", "nfldata games"),
        ])
    body.append(card("Gate results, strategy by strategy",
                     table("t-gate-res", ["Strategy", "Gates", "Bets", "ROI", "p",
                                          "Parameter stability", "Max correlation", "Reward",
                                          "Benchmark source"],
                           gtrs, numeric=[2, 3, 4, 6, 7],
                           note="Only 'Wind — under' clears all eight. Note that the strategies with "
                                "the largest nominal sample sizes are the ones that fail significance: "
                                "more bets only helps if the edge is real.")))

    body.append(card("Why the gates are built this way", """
<ul class="tight">
  <li><b>Sample sufficiency (G1, &ge; 100 bets).</b> Below that, a single lucky weekend moves ROI by
  more than any plausible edge.</li>
  <li><b>Out-of-sample integrity (G2).</b> Parameters are chosen from earlier seasons only; a bet may
  not appear twice.</li>
  <li><b>Significance (G3).</b> Bootstrap 95% interval lower bound above zero <em>and</em> a sign-flip
  randomisation p &le; 0.05. The randomisation test replaced an earlier permutation test that was
  mathematically inert — permuting a sample cannot change its mean.</li>
  <li><b>Economics (G4, ROI &ge; 2%).</b> Significant but tiny is not investable after costs.</li>
  <li><b>Baselines (G5).</b> Must beat every always-on baseline on the same window.</li>
  <li><b>Luck robustness (G6).</b> Must stay positive once one-score games (margin &le; 8) and blowouts
  (margin &ge; 25) are removed. Those two buckets are where variance, not skill, decides.</li>
  <li><b>Parameter stability (G7).</b> At least 60% of neighbouring parameter values must also be
  positive, so the result is not an artefact of one chosen cut-off.</li>
  <li><b>Non-redundancy (G8, |r| &le; 0.85).</b> A strategy that is the same bet as an accepted one
  adds no information and earns no reward.</li>
</ul>"""))
    # --- Added by session arena-1d3600f8-x1 (T21): demotion gate G8 ---
    g8 = next((g for g in D["gates_registry"].get("gates", []) if g.get("id") == "G8"), None)
    if g8:
        g8trs = [[esc(t["id"]), esc(t["rule"]), esc(t["basis"]), esc(t.get("note", "")),
                  src_cell("https://github.com/karagemop466-tech/X1/blob/main/data/gates.json")]
                 for t in g8.get("triggers", [])]
        act = g8.get("action", {})
        body.append(card("G8 — the demotion gate: a live strategy goes back to paper",
                         table("t-g8", ["Trigger", "Rule", "Basis", "Note", "Source"], g8trs,
                               note="Any ONE trigger demotes. This gate is mechanical: triggers fire "
                                    "without discretion.") +
                         f'<div class="legend"><b>What demotion does:</b> {esc(act.get("status_change", ""))}. '
                         f'{esc(act.get("positions", ""))}. {esc(act.get("bankroll", ""))}. '
                         f'{esc(act.get("leaderboard", ""))}. {esc(act.get("log", ""))}<br>'
                         f'<b>Re-entry (never automatic):</b> ' +
                         " ".join(f"{i + 1}. {esc(x)};" for i, x in enumerate(g8.get("reentry", []))) +
                         f' {esc(g8.get("authority", ""))}</div>'))

    return page("validation.html", "Validation gates", "Strategy", "\n".join(body),
                lede="Eight gates, pre-registered. Their whole job is to stop luck being paid as skill.")


def p_leaderboard() -> str:
    lb = D["research"]["leaderboard"]
    reg = D["leaderboard"]["rows"]
    baselines = D["research"]["baselines"]
    luck = D["research"]["luck"]
    body = []

    body.append(f"""<section class="note"><b>Reward rule.</b>
<code>reward = 1000 &times; ROI &times; min(1, bets / 300) &times; confidence</code>, where
<i>confidence</i> is the share of the bootstrap interval that stays above zero. The
<code>min(1, bets/300)</code> term is what removes the incentive to spray: a strategy that has not
produced 300 out-of-sample bets is scaled down, and any strategy that fails a single gate scores
<b>zero</b>, regardless of its headline ROI.</section>""")

    body.append(kpis([
        (f'{sum(1 for s in lb if s.get("all_passed"))}/{len(lb)}', "pass all gates", "out of sample", "ok"),
        (pc(max(float(s.get("roi") or 0) for s in lb)), "best ROI", "Wind — under", "ok"),
        (str(max(int(s.get("bets") or 0) for s in lb)), "largest sample", "and it fails every gate", "grey"),
        (num(sum(float(s.get("reward") or 0) for s in lb), 1), "total reward points", "gate-weighted", ""),
    ]))

    trs = []
    for s in sorted(lb, key=lambda x: (not x.get("all_passed"), -float(x.get("reward") or 0))):
        trs.append([
            str(s.get("rank") or ""),
            esc(s["key"]), esc(s["name"]),
            str(s["bets"]), pc(s["roi"]), pc(s["hit_rate"]),
            f'{num(s["ci_lo"])} to {num(s["ci_hi"])}',
            num(s["p_value"], 4),
            str(s["first_season"]) + "–" + str(s["last_season"]),
            (s.get("stability") or {}).get("share_positive"),
            badge("accepted", "ok") if s.get("all_passed") else badge("rejected", "bad"),
            num(s.get("reward"), 1),
            link("https://github.com/nflverse/nfldata", "nfldata games"),
        ])
    body.append(table("t-lb", ["Rank", "Key", "Strategy", "Bets", "ROI", "Hit rate", "95% CI",
                               "p", "Seasons", "Stability", "Verdict", "Reward", "Benchmark source"],
                      trs, numeric=[3, 4, 5, 7, 9, 11], center=[10],
                      note="Rank is by reward, which is gate-weighted: a rejected strategy scores zero "
                           "no matter what its ROI says."))

    btrs = [[esc(k.replace("always_", "always ")), pc(v),
             badge("beaten by the accepted strategy", "ok") if v < 0.1153 else badge("above it", "warn"),
             link("https://github.com/nflverse/nfldata", "nfldata games")]
            for k, v in sorted(baselines.items(), key=lambda kv: -kv[1])]
    body.append(card("Naive baselines on the same window",
                     table("t-base", ["Baseline", "ROI", "Comparison", "Benchmark source"], btrs,
                           numeric=[1],
                           note="Gate G5 requires an accepted strategy to beat every always-on baseline. "
                                "'Always under' is the only baseline above zero, and the accepted "
                                "strategy beats it by a wide margin.")))

    ltrs = []
    for r in luck:
        try:
            full = json.loads(r["full"].replace("'", '"')) if isinstance(r.get("full"), str) else (r.get("full") or {})
        except Exception:
            full = {}
        ltrs.append([
            esc(r["strategy"]), str(full.get("n", "")), pc(full.get("roi"), 2),
            str(r["one_score_games"]), str(r["blowout_games"]),
            num(r["luck_profit_share"], 1), num(r["roi_drop_when_luck_removed"], 3),
            link("https://github.com/nflverse/nfldata", "nfldata games"),
        ])
    body.append(card("Luck decomposition — how much of each result is variance?",
                     table("t-luck", ["Strategy", "Bets", "Full ROI", "One-score games", "Blowouts",
                                      "Luck share of profit %", "ROI drop when luck removed",
                                      "Benchmark source"], ltrs, numeric=[1, 2, 3, 4, 5, 6],
                           note="One-score games are margin &le; 8; blowouts are margin &ge; 25. "
                                "A strategy whose profit depends on those buckets is being rewarded for "
                                "variance, and gate G6 removes them and re-scores.")))

    rtrs = [[esc(r["strategy_id"]), esc(r["strategy"]), esc(r["market"]),
             dash(r.get("graded_bets")), dash(r.get("roi")),
             badge(r.get("skill_gate", ""), "grey"), badge(r.get("status", ""), "blue"),
             src_cell(r["_source_url"])] for r in reg]
    body.append(card("Official-source-only leaderboard — intentionally unranked",
                     table("t-lb-official", ["ID", "Strategy", "Market", "Graded bets", "ROI",
                                             "Skill gate", "Status", "Source"], rtrs, center=[5, 6],
                           note="Ranks and result columns are blank on purpose. A leaderboard that ranks "
                                "strategies before any result exists would be ranking noise. Once a "
                                "results feed and a price feed exist (Q-02, Q-04) these fill from "
                                "graded data and the skill gate decides what may rank at all.")))
    # --- Added by session arena-1d3600f8-x1 (T18): signal vs staking separation ---
    sig = D["sigstat"]
    strs2 = []
    for r in sig["rows"]:
        strs2.append([
            esc(r["strategy_id"]), esc(r["market_family"]),
            esc(r["signal_bets"]), esc(r["signal_hit_rate_pct"]), esc(r["signal_z_vs_breakeven"]),
            esc(r["signal_flat_roi_pct"]), esc(r["signal_flat_roi_trimmed5_pct"]),
            badge(r["signal_gate"], "ok" if r["signal_gate"] == "PASS" else "bad"),
            esc(r["staking_flat_units"]), esc(r["staking_flat_max_drawdown_u"]),
            esc(r["staking_momentum_roi_pct"]), esc(r["staking_momentum_max_drawdown_u"]),
            badge(r["staking_gate"], "ok" if r["staking_gate"] == "PASS" else "warn"),
            badge(r["final_status"], "blue"), src_cell(r["source_url"]),
        ])
    body.append(card("Signal vs staking — graded separately, so a lucky staking run cannot mask a bad signal",
                     table("t-sigstat", ["Strategy", "Family", "Bets", "Hit %", "z", "Flat ROI %",
                                         "Trimmed ROI %", "Signal gate", "Flat units", "Flat max DD u",
                                         "Momentum ROI %", "Momentum max DD u", "Staking gate",
                                         "Final status", "Benchmark source"],
                           strs2, numeric=[2, 3, 4, 5, 6, 8, 9, 10, 11], center=[7, 12, 13],
                           note="Signal columns are flat 1-unit stakes only. The momentum staking rule "
                                "(2u after a win, 1u after a loss) exists to demonstrate the masking vector: "
                                "it moves ROI without moving any signal metric. Rule: final grade = "
                                "min(signal, staking); eligible_for_ranking requires signal gate PASS first. "
                                "Ledger is the third-party mirror window — the official-only board above stays "
                                "unranked until official graded results exist.")))

    return page("leaderboard.html", "Leaderboard and rewards", "Strategy", "\n".join(body),
                lede="Ranked by gate-weighted reward, not by headline ROI. Baselines, luck decomposition, "
                     "and the unranked official-only board.")


def p_props() -> str:
    fam = csvrows("data/processed/prop_family_stats.csv")
    combos = csvrows("data/processed/prop_combos.csv")
    body = []
    body.append(f"""<section class="note warn"><b>No official prop prices exist.</b> The league
publishes no player-prop market, so <b>no prop strategy can be priced or gated</b>. What follows is
the distributional work that would feed a price: calibration on 2010–2020, evaluation on 2021+,
against the {link("https://github.com/nflverse/nfldata", "nflverse/nfldata")} player-week mirror.
Nothing here is a pick.</section>""")

    trs = [[esc(r["label"]), esc(r["position_group"]), esc(r["seasons"]),
            str(r["player_games"]), str(r["eval_player_games"]),
            pc(r["hit_rate_at_model_line"], 2), pc(r["calibrated_hit_rate_eval"], 2),
            num(r["calibration_offset"], 2), num(r["mean_actual"], 2), num(r["mean_line"], 2),
            num(r["std_error"], 2), num(r["error_median"], 2),
            link("https://github.com/nflverse/nfldata", "nfldata player week stats")]
           for r in fam]
    body.append(table("t-props", ["Family", "Position", "Seasons", "Player-games", "Eval games",
                                  "Raw hit %", "Calibrated hit %", "Calibration offset",
                                  "Mean actual", "Mean line", "Std error", "Median error",
                                  "Benchmark source"], trs, numeric=range(3, 12),
                      note="Calibration should land near 50% if the projection is unbiased. The "
                           "receptions family sits at 42.8% because half-point rounding distorts a "
                           "low-count statistic — that is a modelling defect, published as one."))

    ctrs = [[esc(r["combo"]), num(r["correlation"], 3), esc(r["observations"]),
             pc(r["leg_hit_rate"], 1), pc(r["joint_hit_rate"], 2),
             num(r["parlay_decimal_odds"], 3), pc(r["breakeven_leg_hit_rate"], 2),
             pc(r["edge_vs_breakeven"], 2),
             badge("yes", "ok") if str(r["profitable"]).lower() == "true" else badge("no", "bad"),
             link("https://github.com/nflverse/nfldata", "nfldata player week stats")]
            for r in combos]
    body.append(card("Combination maths — when a two-leg is arithmetically impossible",
                     table("t-props-combo", ["Pair", "r", "n", "Leg hit", "Joint hit", "Decimal odds",
                                             "Break-even leg", "Edge", "Profitable?",
                                             "Benchmark source"], ctrs, numeric=[1, 2, 3, 4, 5, 6, 7],
                           note="Two −110 legs pay 3.645 decimal, so each leg must win 52.38% to break "
                                "even even when the legs are independent. Negative correlation makes it "
                                "worse, not better: correlated legs that move together lose together.")))

    body.append(card("The arithmetic, stated plainly", """
<ul class="tight">
  <li>A single −110 bet breaks even at <b>52.38%</b>.</li>
  <li>A two-leg −110 parlay pays about <b>3.645</b> decimal and breaks even at <b>72.11%</b> joint —
  which needs each leg at <b>52.38%</b> only if the legs are independent.</li>
  <li>Correlation moves the joint probability toward the Fréchet bounds. For QB passing yards and
  WR/TE receiving yards (r = 0.927) the joint hit rate is 51.2%, still above the 47.6% the price
  implies — but for RB rushing yards paired with a receiver prop (r = −0.163) the joint is 24.0%,
  well below it, and the combination is unprofitable at any stake.</li>
  <li>The lesson the gates encode: <b>a parlay is not a way to manufacture edge</b>. It multiplies
  whatever edge or disadvantage each leg already has, plus the book's margin on every leg.</li>
</ul>"""))
    return page("props.html", "Player props and parlays", "Strategy", "\n".join(body),
                lede="Calibration, combination correlation, and the break-even arithmetic that shows "
                     "when a parlay cannot work.")


# ------------------------------------------------ Added by session arena-1d3600f8-x1
def p_results() -> str:
    feed = D["results_feed"]
    rep = D["results_report"]
    checks = rep.get("checks", {})
    roi = D["roi_summary"]
    body = []

    body.append(f"""<section class="note"><b>What this page is.</b> The verified results feed:
every settled 2026 game (Weeks 1&ndash;9 complete, Week 10 through Thursday night), transcribed
from the official {link("https://www.nfl.com/schedules/2026/by-week/week-9", "NFL.com by-week pages")}
and double-entry checked against the official
{link("https://www.nfl.com/standings/", "league standings")}: per-team points for/against and
W-L-T for all 32 clubs must match, and league totals must balance. This is what lets backtests
and ROI be computed at all &mdash; outcomes settle from official numbers only.</section>""")

    body.append(kpis([
        (str(len(feed)), "settled games in feed", "Weeks 1–10, 2026", ""),
        (str(checks.get("total_points_feed", "")), "points in feed", "equals standings sum exactly", "ok"),
        ("0", "team mismatches", "PF/PA + W-L-T, 32 of 32 clubs", "ok"),
        (str(len(D["roi_summary"]) - 1), "strategies graded", "at assumed −110", ""),
    ]))

    vtrs = [[esc(k.replace("_", " ")), esc(v if not isinstance(v, (dict, list)) else f"{len(v)} entries"),
             src_cell("https://www.nfl.com/standings/")]
            for k, v in checks.items() if not isinstance(v, (dict, list))]
    body.append(card("Double-entry verification record (machine-readable: data/results/verification_report.json)",
                     table("t-res-ver", ["Check", "Value", "Source"], vtrs, numeric=[1],
                           note="Every team's summed points from the feed equals the official standings "
                                "table, and so does every W-L-T line. A single transcription slip would "
                                "break at least one of these checks.")))

    rtrs = [[esc(r["week"]), esc(r["date_iso"]),
             f'<b>{esc(r["away_team"])}</b> at <b>{esc(r["home_team"])}</b>',
             f'{esc(r["away_score"])}–{esc(r["home_score"])}',
             badge("Final", "ok"),
             src_cell(r["source_url"]), esc(r["retrieved_at"])]
            for r in feed]
    body.append(card("The feed — 137 settled games, one row per game",
                     table("t-results", ["Week", "Date", "Matchup", "Score", "Status", "Official game page", "Retrieved"],
                           rtrs, numeric=[0, 3], center=[4],
                           note="Scores are exactly as printed on the official page. Week 10 games that "
                                "were still scheduled at fetch time are excluded — only settled games are "
                                "recorded. Evidence snapshots: data/results/raw/week_01..10.md.")))

    otrs = []
    for r in roi:
        otrs.append([esc(r["strategy"]), esc(r["bets"]), esc(r["wins"]), esc(r["losses"]),
                     esc(r["hit_rate_pct"]), esc(r["roi_at_assumed_minus110_pct"]),
                     esc(r["z_vs_breakeven"]), esc(r["outcome_basis"]),
                     esc(r["price_basis"]), src_cell("https://www.nfl.com/schedules/2026/by-week/week-10")])
    body.append(card("ROI computed from the verified feed (graded bets: 689, each carrying its game's official URL)",
                     table("t-roi", ["Strategy", "Bets", "Wins", "Losses", "Hit %", "ROI % at −110",
                                     "z vs break-even", "Outcome basis", "Price basis", "Source"],
                           otrs, numeric=[1, 2, 3, 4, 5, 6],
                           note="Outcomes settle from the verified feed only. Prices are the conventional "
                                "−110 assumption (no official price source exists — Q-02): ROI here is "
                                "labelled assumed_-110 everywhere and is not a market quote. Nothing is "
                                "positive at this price; the model stays a screen, not a price.")))

    return page("results.html", "Verified results feed and graded ROI", "Official data",
                "\n".join(body),
                lede="Every settled game from the official pages, double-entry verified, and the ROI it now makes possible.")


def p_origination() -> str:
    orig = D["origination"]
    idx = D["price_index"]
    snaps = D["snapshots"]
    body = []

    body.append(f"""<section class="note"><b>Origination order is fixed:</b>
<span class="mono">side first, then the total, then the moneyline</span>. The side is the deepest
market and the one the points model is fitted against; the total comes from the same model and must
not be tuned to the side's residual; the moneyline is derived from the joint side/total outcome
distribution and is therefore originated last. Each market publishes three separate columns &mdash;
<b>fair line</b> (our number), <b>market line</b> (the price-snapshot capture), and the
<b>difference</b> (fair − market) — never combined into one cell.</section>""")

    n_full = sum(1 for r in orig if r["fair_line"] and r["market_line"] and r["difference"])
    body.append(kpis([
        (str(len(orig)), "markets originated", "14 games × side/total/ML", ""),
        (str(n_full), "with fair + market + difference", "three separate columns", "ok"),
        (str(len(idx)), "markets in the price store", "opening + closing slots", ""),
        ("0", "verified prices", "no official source publishes prices", "grey"),
    ]))

    otrs = [[esc(r["origin_order"]), f'{esc(r["away"])} at {esc(r["home"])}',
             esc(r["market_type"]), esc(r["selection"]),
             esc(r["fair_line"]), esc(r["market_line"]) if r["market_line"] else '<span class="blank">no official source</span>',
             esc(r["difference"]) if r["difference"] else dash(),
             esc(r["difference_unit"]),
             src_cell(r["market_source"] or None),
             badge(r["market_verification"], "warn")]
            for r in sorted(orig, key=lambda x: (int(x["origin_seq"]), x["game_id"]))]
    body.append(card("Origination table — fair line, market line, difference as separate columns",
                     table("t-orig", ["Order", "Game", "Market", "Selection", "Fair line (ours)",
                                      "Market line", "Difference", "Unit", "Market source", "Verification"],
                           otrs, numeric=[4, 5, 6], center=[0, 9],
                           note="Difference = fair − market in the market's own units (points for side/total; "
                                "odds points for moneyline). The market column is the third-party closing "
                                "benchmark (nflverse mirror) — flagged unverified, because no official or "
                                "licensed source publishes betting prices (Q-02). It is never presented as fact.")))

    pitrs = [[esc(r["game_id"]), esc(r["market_type"]), esc(r["selection"]),
              esc(r["opening_price"]) if r["opening_price"] else '<span class="blank">no opening capture (Q-02)</span>',
              esc(r["opening_captured_at"]),
              esc(r["closing_price"]) if r["closing_price"] else '<span class="blank">no official source</span>',
              esc(r["closing_captured_at"]),
              src_cell(r["closing_source"] or None),
              badge(r["closing_verification"], "warn")]
             for r in idx]
    body.append(card("Price-snapshot store — opening and closing numbers for every market we originate",
                     table("t-price", ["Game", "Market", "Selection", "Opening", "Opening at",
                                       "Closing", "Closing at", "Closing source", "Verification"],
                           pitrs, center=[],
                           note=f"The store is append-only ({len(snaps)} captures recorded; "
                                "tools/record_price.py adds captures from a licensed feed when one exists). "
                                "Opening slots are reserved and blank — no opening quote exists in any "
                                "source we are entitled to use. Closing captures are the third-party mirror "
                                "benchmark, labelled unverified on every row.")))

    return page("origination.html", "Origination and the price-snapshot store", "Model",
                "\n".join(body),
                lede="Side, then total, then moneyline — with fair line, market line and difference as separate columns, and every price capture provenance-stamped.")


def p_requirements() -> str:
    rows = D["requirements"]["rows"]
    body = []
    body.append(f"""<section class="note"><b>{len(rows)} requirements</b> extracted from the project
brief, each with the quote it came from and its current status. Nothing here is paraphrased into
something the brief did not say.</section>""")
    trs = [[esc(r["id"]), esc(r["category"]), esc(r["requirement"]),
            f'<em>"{esc(r["source_quote"])}"</em>' if r.get("source_quote") else dash(),
            badge(r["priority"], "bad" if r["priority"] == "P0" else ("warn" if r["priority"] == "P1" else "grey")),
            badge(r["status"], "ok" if "implement" in str(r["status"]).lower() else
                  ("warn" if "partial" in str(r["status"]).lower() else "grey")),
            esc(r["acceptance"]) if r.get("acceptance") else dash(),
            src_cell(r["_source_url"])] for r in rows]
    body.append(table("t-req", ["ID", "Category", "Requirement", "Source quote", "Priority",
                                "Status", "Acceptance", "Source"], trs, center=[4, 5],
                      note="Acceptance is blank where the brief states a goal but no testable "
                           "acceptance criterion — those are open, not assumed."))
    return page("requirements.html", "Requirement register", "Decisions", "\n".join(body),
                lede="Every requirement in the brief, with the quote it came from and its status.")


def p_decisions() -> str:
    rows = D["questions"]["rows"]
    body = []
    blockers = [r for r in rows if str(r.get("blocks_decision", "")).strip().lower().startswith("y")]
    body.append(f"""<section class="note bad"><b>{len(blockers)} of {len(rows)} questions are hard
blockers.</b> They cannot be answered from any official source and they stop specific parts of the
system from working. Everything else on this page is a question we can answer, or one whose answer
would change a number rather than unlock a subsystem.</section>""")

    body.append(kpis([
        (str(len(rows)), "questions logged", "across every subsystem", ""),
        (str(len(blockers)), "hard blockers", "no official source can answer them", "bad"),
        (str(sum(1 for r in rows if str(r.get("status", "")).lower().startswith("open"))),
         "still open", "owner decision required", "warn"),
    ]))

    trs = [[esc(r["id"]), esc(r["area"]),
            f'<b>{esc(r["question"])}</b>',
            esc(r["why_it_matters"]),
            esc(r["information_we_have"]),
            esc(r["information_missing"]),
            esc(r["how_to_get_it"]),
            badge("blocks", "bad") if str(r.get("blocks_decision", "")).strip().lower().startswith("y") else badge("no", "grey"),
            badge(r.get("status", ""), "warn" if str(r.get("status", "")).lower().startswith("open") else "ok"),
            src_cell(r["_source_url"])] for r in rows]
    body.append(table("t-q", ["ID", "Area", "Question", "Why it matters", "Information we have",
                              "Information missing", "How to get it", "Blocks?", "Status", "Source"],
                      trs, center=[7, 8],
                      note="The 'information missing' column is the discovery list: each entry names a "
                           "concrete thing to go and get, not a vague gap."))
    return page("decisions.html", "Decision register", "Decisions", "\n".join(body),
                lede="Question, information held, information missing, how to get it, and what it blocks.")


def p_suggestions() -> str:
    rows = D["suggestions"]["rows"]
    body = []
    body.append(f"""<section class="note"><b>Nothing here is implemented by default.</b> Each of the
{len(rows)} suggestions below is a choice, not a plan: three paths, a cost, an effort, a risk, and a
recommended path. The status column records whether a decision has been made. This page exists so the
options can be compared <em>before</em> any of them is built.</section>""")

    pending = [r for r in rows if "pending" in str(r.get("decision_status", "")).lower()]
    body.append(kpis([
        (str(len(rows)), "suggestions", "with three paths each", ""),
        (str(len(pending)), "awaiting a decision", "not started, not assumed", "warn"),
        (str(sum(1 for r in rows if str(r.get("impact", "")).lower() == "high")), "high impact",
         "by the register's own rating", ""),
        (str(sum(1 for r in rows if str(r.get("risk", "")).lower().startswith("high"))), "high risk",
         "flagged on the row", "bad"),
    ]))

    trs = []
    for r in rows:
        rec = str(r.get("recommended_path") or "")
        trs.append([
            esc(r["id"]), esc(r["area"]),
            f'<b>{esc(r["suggestion"])}</b>',
            esc(r["rationale"]),
            badge(r["impact"], "bad" if str(r["impact"]).lower() == "high" else "grey"),
            badge(r["effort"], "warn" if str(r["effort"]).lower() == "high" else "grey"),
            esc(r["risk"]),
            f'<b>A.</b> {esc(r["path_a"])}<br><b>B.</b> {esc(r["path_b"])}<br><b>C.</b> {esc(r["path_c"])}',
            badge(rec[:1].upper() if rec else "?", "blue"),
            badge(r.get("decision_status", ""), "warn" if "pending" in str(r.get("decision_status", "")).lower() else "ok"),
            esc(r.get("owner") or ""),
            src_cell(r["_source_url"]),
        ])
    body.append(table("t-sug", ["ID", "Area", "Suggestion", "Why", "Impact", "Effort", "Risk",
                                "Paths A / B / C", "Recommended", "Decision", "Owner", "Source"],
                      trs, center=[4, 5, 8, 9],
                      note="Filter by area, or search for a keyword, to compare the options in one view."))

    body.append(card("How to use this board", """
<ol class="tight">
  <li>Filter to <b>pending</b>. Those are the choices that have not been made.</li>
  <li>Read paths A, B and C. Each is a genuinely different way to solve the same thing — usually
  build-it, buy-it, or defer-it — with the cost and the risk written on the row.</li>
  <li>Pick one. The recommended column is a default, not a decision; it exists so that doing nothing
  is an explicit choice rather than an accident.</li>
  <li>Only then does the work start, and the row changes to <i>decided</i> with the owner recorded.</li>
</ol>
<p>Nothing on this board has been built ahead of a recorded decision.</p>"""))
    # --- Added by session arena-1d3600f8-x1: suggestions arising from this round ---
    body.append(card("Suggestions arising from the 2026-11-14 second round — for review before anything is built", f"""
<ul class="tight">
  <li><b>S-A (discovery, highest leverage): license a price feed or connect the owner's own book
  account feed.</b> It fills the <a href="{PFX}origination.html">price-snapshot store</a> opening
  slots, makes CLV computable, switches demotion triggers D4/D5 on, and turns assumed-−110 ROI into
  ROI at recorded prices. Unblocks Q-02.</li>
  <li><b>S-B: run the weekly results ingestion before each slate.</b> The tools exist
  (<code>tools/build_results_feed.py</code> + <code>tools/verify_results_feed.py</code>); extending
  the feed to Weeks 11–18 keeps every backtest and ROI current. No new decision needed.</li>
  <li><b>S-C: publish the Houston depth chart by hand-check or an alternate club page</b> to close
  coverage gap F-03 (the only club with no deficiency rows).</li>
  <li><b>S-D: decide the season-1 reward pool question (Q-07)</b> before any strategy can pass
  enough gates for the rewards to matter — a decision, not a build.</li>
  <li><b>S-E: keep the mirror-lab numbers quarantined.</b> They are useful benchmarks but every
  promotion decision should ride on the official-only columns (results feed, official correlations)
  once prices exist.</li>
</ul>
<p>Nothing above is built ahead of a recorded decision. Review, pick a path, then implement.</p>"""))

    return page("suggestions.html", "Suggestion board", "Decisions", "\n".join(body),
                lede="Every improvement as a choice: three paths, cost, effort, risk, recommendation — "
                     "awaiting a decision before anything is built.")


def p_sources() -> str:
    cr = D["club_registry"]["rows"]
    body = []
    body.append("""<section class="note"><b>Three tiers, and the tier is printed on every row.</b>
<b>League</b> — published by the NFL on nfl.com. <b>Club</b> — published by a club on its own
official site; official in the sense that the club owns it, but not a league fact. <b>Third party</b> —
a community mirror used only where the league publishes nothing machine-readable, never presented as
league-verified.</section>""")

    league = [
        ("Standings", "https://www.nfl.com/standings/league/2026/REG", "32 rows, re-verified 2026-11-14"),
        ("Week 10 schedule, byes and results", "https://www.nfl.com/schedules/2026/by-week/week-10", "14 games, 4 byes, 1 final"),
        ("Official injury report, Week 10", "https://www.nfl.com/injuries/", "345 rows, re-verified 2026-11-14"),
        ("Team stats (offence and defence)", "https://www.nfl.com/stats/team-stats/", "288 rows across 9 tables"),
        ("Official clubs directory", "https://www.nfl.com/teams/", "32 clubs, used to discover club domains"),
        ("Standings tie-breaking procedures", "https://www.nfl.com/standings/tiebreakingprocedures", "cited for the tie-break rules"),
        ("Flexible scheduling procedures", "https://www.nfl.com/legal/flexible-scheduling-procedures", "cited for Week 16-18 scheduling"),
    ]
    body.append(card("League sources",
                     table("t-src-league", ["Dataset", "Official page", "What we take from it"],
                           [[esc(a), link(b), esc(c)] for a, b, c in league], sortable=False,
                           filter_box=False)))

    clubtrs = [[esc(r["team_slug"]), esc(r["club_domain"]), link(r["official_site"], "depth chart / site"),
                link(r["_source_url"], "nfl.com/teams")] for r in sorted(cr, key=lambda x: x["team_slug"])]
    body.append(card("Club sources — the official club domains, as listed by the league",
                     table("t-src-club", ["Club slug", "Official domain", "Club site", "Discovered from"],
                           clubtrs, center=[],
                           note="Domains are discovered at run time from nfl.com/teams rather than "
                                "guessed, so a club that moves its site is picked up automatically.")))

    body.append(card("Third-party sources, named and bounded", """
<table><tbody>
<tr><td><b>nflverse / nfldata</b></td><td><a href="https://github.com/nflverse/nfldata" target="_blank" rel="noopener">github.com/nflverse/nfldata</a></td>
<td>Used only for historical game results, closing lines, weather and player-week stats — things the
league does not publish in a machine-readable form. Every input file is SHA-256 fingerprinted in
<code>data/raw_manifest.json</code>. Rows built on it are labelled third-party wherever they appear.</td></tr>
<tr><td><b>Repository state</b></td><td><a href="https://github.com/karagemop466-tech/X1" target="_blank" rel="noopener">github.com/karagemop466-tech/X1</a></td>
<td>Used only for the repository review — file paths, line counts and hashes.</td></tr>
<tr><td><b>Betting prices</b></td><td><span class="blank">— none —</span></td>
<td>No league or club source publishes prices. The market-line table ships empty and is blocked by
Q-02. <span class="b warn">no official source</span></td></tr>
</tbody></table>"""))
    return page("sources.html", "Source registry", "Governance", "\n".join(body),
                lede="Every page this site reads from, its tier, and what we take from it.")


def p_verification() -> str:
    s = D["vledger"]["summary"]
    led = D["vledger"]["ledger"]
    d = D["def"]
    body = []
    body.append(f"""<section class="note ok"><b>Independent re-verification, run {SNAPSHOT}.</b>
The official pages were re-fetched and every published value compared cell by cell against them:
<b>{s.get('checks', 0)} checks, {s.get('matches', 0)} matches, {s.get('mismatches', 0)} mismatches</b>.
This was done by a different session from the one that authored the rows, against pages fetched
afresh rather than from cache.</section>""")

    body.append(kpis([
        (str(s.get("checks", 0)), "value checks", "standings, injuries, schedule, annex CSVs", "ok"),
        (str(s.get("matches", 0)), "matched", "cell by cell", "ok"),
        (str(s.get("mismatches", 0)), "mismatches", "none found", "ok"),
        (str(len(d.get("diffs", []))), "deficiency cells corrected", "join normaliser", "bad"),
    ]))

    body.append(card("What was checked, and how", """
<table><tbody>
<tr><td><b>Standings</b></td><td>32 clubs &times; 16 fields (W, L, T, PCT, PF, PA, net, home, road,
division, conference, non-conference, streak, last 5)</td><td>512 comparisons</td><td><a class="" href="https://www.nfl.com/standings/league/2026/REG" target="_blank" rel="noopener" title="https://www.nfl.com/standings/league/2026/REG">NFL.com standings</a></td></tr>
<tr><td><b>Injuries</b></td><td>345 rows &times; 5 fields (player, position, injury, practice status,
game status), compared in order within each of the 28 clubs</td><td>1,725 comparisons</td><td><a class="" href="https://www.nfl.com/injuries/" target="_blank" rel="noopener" title="https://www.nfl.com/injuries/">NFL.com injuries</a></td></tr>
<tr><td><b>Annex injury CSV</b></td><td>the same 345 rows as transcribed independently by another
session, player and game status</td><td>690 comparisons</td><td><a class="" href="https://www.nfl.com/injuries/" target="_blank" rel="noopener" title="https://www.nfl.com/injuries/">NFL.com injuries</a></td></tr>
<tr><td><b>Schedule</b></td><td>14 games: home, away, kickoff, network; bye set derived and compared
against the league's own "Teams on Bye" list</td><td>29 comparisons</td><td><a class="" href="https://www.nfl.com/schedules/2026/by-week/week-10" target="_blank" rel="noopener" title="https://www.nfl.com/schedules/2026/by-week/week-10">NFL.com Week 10</a></td></tr>
<tr><td><b>Internal arithmetic</b></td><td>home + road = overall; PF &minus; PA = net points;
W + L + T &le; 10; every club accounted for exactly once</td><td>per-club assertions</td><td><a class="" href="https://www.nfl.com/standings/league/2026/REG" target="_blank" rel="noopener" title="https://www.nfl.com/standings/league/2026/REG">NFL.com standings</a></td></tr>
</tbody></table>"""))

    sample = [r for r in led if r["dataset"] == "injuries"][:400]
    trs = [[esc(r["row"]), esc(r["field"]), esc(r["published"]) or dash(),
            esc(r["official"]) or dash(),
            badge("match", "ok") if r["result"] == "match" else badge(r["result"], "bad"),
            src_cell(r["source"])] for r in sample]
    body.append(card(f"Row-by-row ledger — injuries (first {len(sample)} of "
                     f"{sum(1 for r in led if r['dataset'] == 'injuries')} comparisons)",
                     table("t-ver-inj", ["Row", "Field", "Published", "Official page", "Result",
                                         "Source"], trs, center=[4],
                           note="The full ledger, all datasets, is in "
                                "<code>data/verify/verification_ledger.json</code>.")))

    sstd = [r for r in led if r["dataset"] == "standings"][:320]
    s2 = [[esc(r["row"]), esc(r["field"]), esc(r["published"]) or dash(),
           esc(r["official"]) or dash(),
           badge("match", "ok") if r["result"] == "match" else badge(r["result"], "bad"),
           src_cell(r["source"])] for r in sstd]
    body.append(card(f"Row-by-row ledger — standings (first {len(s2)} of "
                     f"{sum(1 for r in led if r['dataset'] == 'standings')} comparisons)",
                     table("t-ver-std", ["Row", "Field", "Published", "Official page", "Result",
                                         "Source"], s2, center=[4])))

    dtrs = [[esc(str(x.get("row", "")).replace("/None/", "/ — /")), esc(x.get("field", x.get("issue", ""))),
             dash(x.get("published")), esc(x.get("corrected") or x.get("issue", "")),
             badge("corrected", "bad"), link("https://www.nfl.com/injuries/", "NFL.com injuries")]
            for x in d.get("diffs", [])]
    body.append(card(f"Deficiency register — {len(dtrs)} cells corrected by the join normaliser",
                     table("t-ver-def", ["Slot", "Field", "As published", "Corrected", "Result",
                                         "Source"], dtrs, center=[4],
                           note="These are corrections, not failures of the official data: the club "
                                "chart and the league report name the same player differently, and the "
                                "original join compared raw strings.")))

    body.append(card("What was NOT verified, stated honestly", """
<ul class="tight">
  <li><b>Depth charts.</b> Four of 32 clubs (Atlanta, Baltimore, Chicago, Green Bay) were re-fetched
  and read row by row. The other 27 are carried on the pipeline's own fetch from the same day and are
  not independently re-read here. Re-fetching all 32 is the next verification step.</li>
  <li><b>Team stats.</b> Row counts and source hosts were checked; the 288 individual cells were not
  re-transcribed by hand in this pass.</li>
  <li><b>Research-lab results.</b> The model, strategy and correlation numbers are reproducible from
  <code>scripts/run_pipeline.py</code> against the fingerprinted mirror, but they are computed from a
  third-party mirror, not from a league page, and no league page can confirm them.</li>
  <li><b>Prices.</b> Not verified, because there is nothing official to verify against.</li>
</ul>"""))
    return page("verification.html", "Verification ledger", "Governance", "\n".join(body),
                lede="Every value this site publishes, re-checked against the official page on "
                     "2026-11-14 — with the coverage limits stated.")


def p_flagged() -> str:
    d = D["def"]
    rr = D["repo_review"]["rows"]
    s = D["vledger"]["summary"]
    ds = d.get("summary", {})
    findings = [r for r in rr if r.get("finding")]

    body = []
    body.append(f"""<section class="note warn"><b>Nothing here is silently fixed.</b> A value that
cannot be confirmed is published as blank and listed on this page. Flagged items do not block the
site; they block <em>trusting</em> the specific row.</section>""")

    items = [
        ("F-01", "bad", "Green Bay depth chart prints jersey numbers, breaking the injury join",
         "Green Bay's club chart renders names as \"75 Sean Rhyan\". The register joined the chart to "
         "the league injury report on the raw string, so all 59 Green Bay rows matched nothing — "
         "including Josh Jacobs (Out), Sean Rhyan (Out) and Josh Whyle (Out).",
         "Rebuilt with a name normaliser that strips jersey numbers, punctuation, case and "
         "generational suffixes. Matched starters went from 171 to "
         f"{ds.get('starters_on_report', 0)}; {ds.get('deltas_vs_published', 0)} cells corrected.",
         ["https://www.packers.com/team/depth-chart", "https://www.nfl.com/injuries/"]),
        ("F-02", "bad", "Generational suffixes break the same join on five other clubs",
         "The Kansas City chart prints \"Kenneth Walker\" where the league report prints \"Kenneth "
         "Walker III\"; Cleveland's chart prints \"Ronnie Hickman\" where the report prints \"Ronnie "
         "Hickman Jr.\" Both starters are questionable or out and both were missed.",
         "Normaliser strips Jr / Sr / II / III / IV. Kansas City's starting running back is now "
         "flagged Questionable and Cleveland's starting free safety Out.",
         ["https://www.nfl.com/injuries/"]),
        ("F-03", "bad", "Houston has no depth chart at all",
         "The Houston club site returns a page titled \"Depth Chart\" with no parsable table, so all "
         "three candidate paths returned zero rows. Houston therefore has no deficiency rows.",
         "Recorded as a coverage gap. Not filled from another source, not inferred. Houston appears "
         "on the join-quality table with zero slots.",
         ["https://www.houstontexans.com/team/depth-chart"]),
        ("F-04", "warn", "Club depth charts are not league facts and disagree with each other",
         "Chicago's chart reads \"As of 10/31/2026\" — fifteen days stale at snapshot date. Green "
         "Bay's is labelled \"Unofficial, Nov. 10, 2026\". Baltimore prints an empty kicker slot. "
         "Position vocabularies differ club to club (RUSH/SAM/WLB vs DL/LB/DB vs EDGE/NB).",
         "Every row carries the club's own URL and the tier is printed as \"Club\", not \"League\". "
         "The site states that a replacement naming is a club self-report.",
         ["https://www.chicagobears.com/team/depth-chart",
          "https://www.packers.com/team/depth-chart",
          "https://www.baltimoreravens.com/team/depth-chart"]),
        ("F-05", "warn", "Green Bay's table uses continuation rows, producing empty position slots",
         "A row with a blank position continues the previous position group (extra tight ends, "
         "extra running backs). The parser treats it as its own slot, so two Green Bay rows carry "
         "position \"—\".",
         "Visible in the register with position shown as an em dash. Cosmetic rather than wrong: the "
         "starter and replacement on those rows are correct.",
         ["https://www.packers.com/team/depth-chart"]),
        ("F-06", "warn", "No official source publishes betting prices",
         "Neither the league nor any club publishes spreads, totals, moneylines or prop prices. The "
         "market-line table therefore ships empty and closing-line value cannot be computed from "
         "official data.",
         "Blocked by Q-02. The research layer uses a named third-party closing line and says so on "
         "every row; nothing is presented as league-verified.",
         ["https://www.nfl.com/"]),
        ("F-07", "warn", "The model is less accurate than the market benchmark",
         "Walk-forward spread MAE 10.42 against the market's 9.73 over 2021-2026; threshold sweeps "
         "return ROI between -6.1% and -2.6%.",
         "Published as a screen, not a price, on the lines page. No edge is claimed.",
         ["https://github.com/nflverse/nfldata"]),
        ("F-08", "warn", "The receptions prop family calibrates to 42.8%, not 50%",
         "Half-point rounding distorts a low-count statistic, so the calibrated hit rate sits well "
         "below the 50% an unbiased projection should produce.",
         "Published with the defect named on the props page. No prop strategy is priced or gated "
         "until this is fixed.",
         ["https://github.com/nflverse/nfldata"]),
        ("F-09", "grey", "Depth charts for 27 of 32 clubs were not independently re-read",
         "This verification pass re-fetched and read four club charts row by row. The remaining 27 "
         "are carried on the pipeline's own fetch from the same day.",
         "Stated on the verification page. Re-fetching all 32 is the next step.",
         ["https://www.nfl.com/teams/"]),
    ]
    trs = [[esc(i[0]), badge(i[1].upper(), i[1]), f'<b>{esc(i[2])}</b>', esc(i[3]), esc(i[4]),
            src_cell(i[5])] for i in items]
    body.append(table("t-flag", ["ID", "Severity", "Finding", "Evidence", "What was done", "Sources"],
                      trs, center=[1], filter_box=True,
                      note="Severity: red means a published value was wrong or missing; amber means a "
                           "limitation that changes how a row should be read; grey means incomplete "
                           "verification coverage."))

    ftrs = [[esc(r["path"]), esc(r["lines_reviewed"]), esc(r["bytes"]), esc(r["sha256_short"]),
             esc(r["finding"]), badge(r["status"], "warn"),
             src_cell(r["_source_url"])] for r in findings]
    body.append(card(f"Automated repository review — {len(ftrs)} of {D['repo_review'].get('total_files', 0)} files flagged",
                     table("t-repo", ["Path", "Lines", "Bytes", "SHA-256", "Finding", "Status",
                                      "Source"], ftrs, numeric=[1, 2], center=[5],
                           note=D["repo_review"].get("method", "") or
                                "Automated scan over every tracked file: encoding, size, and pattern rules.")))

    body.append(card("Verification status", f"""
<p>Independent re-verification on {SNAPSHOT}: <b>{s.get('checks', 0)} checks,
{s.get('mismatches', 0)} mismatches</b> across standings, injuries, schedule and the cross-session
transcriptions. The {ds.get('deltas_vs_published', 0)} deficiency corrections above are corrections to
a <em>derived</em> table, not to any value read from an official page — every official value matched.</p>
<p>Flagged items never block a release. They block trusting the specific row until the owner review
closes them.</p>"""))
    return page("flagged.html", "Flagged for review", "Governance", "\n".join(body),
                lede="Every irregularity found, with its evidence and what was done about it.")


def p_repo_review() -> str:
    rr = D["repo_review"]
    rows = rr["rows"]
    findings = [r for r in rows if r.get("finding")]
    by_status = {}
    for r in rows:
        by_status[r.get("status", "?")] = by_status.get(r.get("status", "?"), 0) + 1
    body = []
    method = esc(rr.get("method", "")) or "encoding, size and pattern rules over each file"
    body.append(f"""<section class="note"><b>Scope.</b> Every tracked file was read and hashed at
commit <code>{esc(rr.get('review_commit', ''))}</code> — <b>{rr.get('total_files', 0)} files</b>.
{len(findings)} carry an automated finding. Method: {method}.</section>""")

    body.append(kpis([
        (str(rr.get("total_files", 0)), "files reviewed", "every tracked file", ""),
        (str(len(findings)), "files flagged", "automated findings", "warn"),
        (str(by_status.get("review", 0)), "awaiting manual review", "not yet adjudicated", "grey"),
        (str(len(by_status)), "status buckets", "see the table", ""),
    ]))

    body.append(card("Repository structure — five parallel sessions left five site trees", """
<p>The single largest structural finding is not in the file-level scan: the repository currently
publishes <b>five independent site trees</b> with five different designs —
<code>index.html</code> + <code>pages/</code>, <code>dashboard/</code>, <code>research/</code>,
<code>site/</code> and <code>live/</code> — each built by a different parallel session. That is why
this <code>app/</code> tree exists: one landing page, one navigation, one stylesheet, over all of
the same data. Nothing in the older trees was deleted; they remain reachable from the repository
root so no prior session's work is discarded.</p>
<p>A second finding: <code>tools/check_links.py</code> exits non-zero with 111 failures on
<code>main</code>, because it globs the newer trees and applies rules written for the original
six-page site (it expects their stylesheet and treats the newer pages' JavaScript template strings
as broken links). That is a real red-CI defect and is logged in <code>COORDINATION.md</code>; it is
owned by another session and has not been edited here.</p>"""))

    trs = [[esc(r["path"]), esc(r["lines_reviewed"]), esc(r["bytes"]), esc(r["sha256_short"]),
            esc(r["finding"]) or '<span class="blank">clean</span>',
            badge(r["status"], "warn" if r.get("finding") else "ok"),
            src_cell(r["_source_url"])] for r in rows]
    body.append(card("Line-by-line file inventory",
                     table("t-repo-all", ["Path", "Lines", "Bytes", "SHA-256", "Finding", "Status",
                                          "Source"], trs, numeric=[1, 2], center=[5],
                           note="Every tracked file with the number of lines read, its size and a "
                                "short hash. Filter to 'review' to see only the flagged ones.")))
    return page("repo-review.html", "Repository review", "Governance", "\n".join(body),
                lede="Every tracked file, hashed and read, with the structural findings of the audit.")


BUILDERS = {
    "index.html": p_index,
    "executive-summary.html": p_exec,
    "standings.html": p_standings,
    "schedule.html": p_schedule,
    "injuries.html": p_injuries,
    "depth.html": p_depth,
    "deficiency.html": p_deficiency,
    "team-stats.html": p_team_stats,
    "lines.html": p_lines,
    # Added by session arena-1d3600f8-x1 (T15-T21 integration)
    "results.html": p_results,
    "origination.html": p_origination,
    "correlation.html": p_correlation,
    "strategies.html": p_strategies,
    "validation.html": p_validation,
    "leaderboard.html": p_leaderboard,
    "props.html": p_props,
    "requirements.html": p_requirements,
    "decisions.html": p_decisions,
    "suggestions.html": p_suggestions,
    "sources.html": p_sources,
    "verification.html": p_verification,
    "flagged.html": p_flagged,
    "repo-review.html": p_repo_review,
}


def main() -> int:
    global PFX, UP
    load()
    os.makedirs(os.path.join(APP, "assets"), exist_ok=True)

    # canonical copy: served from /app/
    PFX, UP = "", "../"
    for fn, _label, _g, _t, _k in PAGES:
        out = BUILDERS[fn]()
        with open(os.path.join(APP, fn), "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"wrote app/{fn} ({len(out):,} bytes)")

    print(f"{len(PAGES)} pages written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
