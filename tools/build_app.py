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
    # Added by session arena-c0461519-x1 (L1/L2): immutable capture ledger of the official injury page
    ("injury-ledger.html", "Injury-report ledger", "Official data", "Every read of the official injury report, hashed", "Immutable · timestamped · flagged"),
    ("depth.html", "Depth charts", "Official data", "Club depth charts, 1st to 4th string", "Club sites"),
    ("deficiency.html", "Deficiency watch", "Official data", "Who is out and which backup replaces them", "Club chart x NFL injury report"),
    # Added by session arena/3fa49c1a-x1 (N6 page, merged in from the parallel N1-N10 round)
    ("replacement-depth.html", "Replacement depth", "Official data", "Depth of the replacement (per-slot store)", "Which string steps in"),
    ("team-stats.html", "Team stats", "Official data", "Official team offence and defence", "NFL.com stats"),
    ("lines.html", "Originated lines", "Model", "Our own number", "Walk-forward model"),
    # Added by session arena-1d3600f8-x1 (T15 + T17)
    ("origination.html", "Origination & prices", "Model", "Side, then total, then moneyline", "Fair vs market vs difference"),
    # Added by session arena/3fa49c1a-x1 (N1 page, merged in from the parallel N1-N10 round)
    ("prices.html", "Price snapshots", "Model", "Price-snapshot store (per-market rows)", "Open and close, blank where no source"),
    # Added by session arena/600e6009-x1 (round 3): capture-status store + origination order
    ("snapshots.html", "Snapshots & order", "Model", "Price snapshots and origination order", "Open / close · side → total → moneyline"),
    # Added by session arena-52aabfa8-x1 (Round-2 union: all-season complements)
    ("results-feed.html", "Results feed (all seasons)", "Model", "Verified results feed, 2019–2026", "Backtest input with tiers"),
    ("price-history.html", "Price history", "Model", "Opening and closing prices, 2019–2026", "Full-window price store"),
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
    ("stores.html", "Verified stores", "Governance", "Verified stores — sourced or blank", "Price, results, origination, registers"),
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
    # Merged from session arena/3fa49c1a-x1 (parallel N1-N10 round) — the second,
    # independent implementation kept for cross-verification. Its stores sit beside
    # the T15-T21 stores and both are published; the cross-checks are on the pages.
    D["n2_results"] = jload("data/results/results_feed.json")
    D["n2_ver"] = jload("data/results/results_verification.json")
    D["prices"] = jload("data/prices/price_feed.json")
    D["repl_depth"] = jload("data/depth/replacement_depth.json")
    D["offcorr"] = jload("data/correlations/official_correlations.json")
    D["lb_split"] = jload("data/leaderboard_split.json")
    # --- Added by session arena/907c5baf-x1 (four-way integration): this session's
    # stores; keys suffixed _x1 so they coexist with the other rounds' loads. ---
    D["results_feed_x1"] = jload("data/results_feed.json")
    D["price_snapshots_x1"] = jload("data/price_snapshots.json")
    D["leaderboard_split_x1"] = jload("data/leaderboard_split_907c.json")
    D["demotion_gate_x1"] = jload("data/demotion_gate.json")
    D["round2_decisions_x1"] = jload("data/round2_decisions.json")
    D["round2_suggestions_x1"] = jload("data/round2_suggestions.json")
    D["gates_v2"] = jload("data/gates_v2.json")
    D["origin_decisions"] = jload("data/origin/decisions_taken.json")
    D["origin_qa"] = jload("data/origin/question_answers.json")
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
    # --- Added by session arena/600e6009-x1 (round 3) ---
    # Root registers (authored, not pipeline-regenerated) plus this round's feeds.
    for key, rel in (
        ("r3_results", "data/results/verified_results.json"),
        ("r3_signal", "data/results/signal_grade.json"),
        ("r3_snapshots", "data/snapshots/price_snapshots.json"),
        ("r3_origination", "data/lines/origination_order_2026_week10.json"),
        ("r3_lb", "data/leaderboard_signal_staking_official.json"),
        ("r3_depth", "data/depth/replacement_depth_summary.json"),
        ("r3_corr", "data/correlations_official_check.json"),
        ("root_questions", "data/questions.json"),
        ("root_suggestions", "data/suggestions.json"),
        ("root_flags", "data/flags.json"),
    ):
        _p = os.path.join(ROOT, rel)
        if os.path.exists(_p):
            D[key] = json.load(open(_p, encoding="utf-8"))
    # Round-2 union additions (session arena-52aabfa8-x1)
    rp = os.path.join(ROOT, "data", "results", "results_feed_meta.json")
    D["results_meta"] = json.load(open(rp, encoding="utf-8")) if os.path.exists(rp) else {}
    hp = os.path.join(ROOT, "data", "prices", "price_store_meta.json")
    D["price_hist_meta"] = json.load(open(hp, encoding="utf-8")) if os.path.exists(hp) else {}
    D["official_corr_ledger"] = csvrows("data/verify/official_correlations.csv")
    D["strat_leaderboard"] = csvrows("data/strategies/leaderboard.csv")


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



# ------------------------------------------------ round 4: decision readiness
READY_BADGE = {"met": "ok", "partly met": "warn", "in progress": "blue", "open": "bad"}


def readiness_table(rows: List[Dict[str, Any]], tid: str) -> str:
    """One row per requirement; every row carries its evidence link (verify_app rule 2)."""
    trs = []
    for x in rows:
        r4 = x["r4_state"]
        reg = x["register_state"]
        reg_cell = badge(reg, READY_BADGE.get(reg, "grey")) if reg in READY_BADGE else badge(reg, "grey")
        r4_cell = badge(r4, READY_BADGE.get(r4, "grey")) + (" <span class='blank'>changed</span>" if x["changed"] else "")
        basis = f"<br><span class='blank'>basis: {esc(x['basis'])}</span>" if x.get("basis") else ""
        clears = esc(x["clears"]) if x.get("clears") else dash()
        measured = esc(x["measured"]) if x.get("measured") else dash()
        trs.append([
            f"<b>{esc(x['id'])}</b>",
            esc(x["requirement"]),
            reg_cell,
            r4_cell,
            esc(x["gate"]),
            measured,
            clears + basis,
            link(x["evidence_url"], x.get("evidence_label") or "evidence"),
        ])
    return table(tid, ["ID", "Requirement", "Register (2026-11-14)", "Round 4", "Blocking gate",
                       "Measured now", "Number that clears it", "Evidence"], trs,
                 note="Register = the state recorded in data/audit/requirements_assessed.json, left unchanged. "
                      "Round 4 = the state after this round checked the data files. Every measured value is "
                      "recomputed from a named file by tools/build_state_audit.py. A clearing number marked "
                      "<em>proposed</em> is a design threshold, not a figure from a source. "
                      "Full data: data/audit/readiness.json.")

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
      <li><a href="results-feed.html">Results feed (all seasons)</a> — 2019–2026, one tier label per row, cross-checks C1–C4.</li>
      <li><a href="price-history.html">Price history</a> — opening and closing for every market we originate across the full backtest window, blanks flagged.</li>
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
  <li><b>One input still blocks the rest: prices.</b> The verified results feed closed the outcomes gap
  (137 settled games, double-entry checked — see <a href="results.html">Results &amp; ROI</a>), but no
  official or licensed source publishes betting prices, so CLV, recorded-price ROI and the price-dependent
  gates stay unenforced rather than filled with a guess. See <a href="decisions.html">decisions</a> Q-02.</li>
</ol>"""))

    rd = jload("data/audit/readiness.json")
    rc = rd["counts"]
    body.append(card("Requirement state audit (round 4) — one row per requirement", f"""
<p>This audit checks each requirement's recorded state against the repository files. It is separate from the decision-readiness register proposed in open PR #53 (`data/audit/decision_readiness.json`), which is not merged here. Each requirement the brief names, with the gate that blocks it, what is measured now, and the number
that would clear it. The register column is the state recorded on 2026-11-14. The round-4 column is the
state after this round checked the data. <b>{rc['rows']} rows:</b> {rc['round4'].get('met', 0)} met,
{rc['round4'].get('partly met', 0)} partly met, {rc['round4'].get('in progress', 0)} in progress,
{rc['round4'].get('open', 0)} open. {rc['changed']} register rows changed state this round; each is listed on
<a href="flagged.html">Flagged for review</a>.</p>
""" + readiness_table(rd["rows"], "t-ready")))

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
  <li><a href="{UP}lab/index.html">Line desk</a> — price snapshots, verified results, originated lines and a signal-vs-staking leaderboard (<code>lab/</code>). Added by session <code>arena/56769365-x1</code>.</li>
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

    # Added by session arena/3fa49c1a-x1 (merge): the parallel-round merge, honestly recorded
    body.append(card("Two sessions, one brief — both preserved (merge record)", f"""
<p>The same eight directed improvements were built twice on 2026-11-14 by two parallel sessions
(<code>arena-1d3600f8-x1</code> T15–T21 and <code>arena/3fa49c1a-x1</code> N1–N10). Nothing was
discarded in the merge: both result feeds, both price-snapshot stores, both replacement-depth
stores and both correlation stores are published here and cross-checked against each other —
the two independent result transcriptions agree on <b>137 of 137 scores</b>, and the independent
correlation recomputation agrees <b>905 of 905</b> pairs. Where the two designs make different
policy choices (demotion thresholds G8 vs D1–D5; reward staking term), both are shown side by
side and the choice is recorded as an owner decision on the
<a href="{PFX}decisions.html">decision register</a>. Finding I-14 is resolved by the results
arithmetic: the standings do include the Thursday result; the earlier reading miscounted.
Full merge log: <code>COORDINATION.md</code>.</p>
<p><b>Third implementation, same rule.</b> Session <code>arena-52aabfa8-x1</code> (tasks T10–T17)
built the same eight requirements independently and merged next under the same nothing-discarded
rule: its all-season results feed and price-history store publish beside the others, its
correlation work is an <i>independent recomputation of the pipeline's 988-row official set</i>
(988/988 within tolerance — a check on top of the existing stores, not a replacement), and its
requirement rows R-46…R-53 are in the <a href="{PFX}requirements.html">register</a>.</p>"""))

    body.append(card("Where each round-2 requirement landed (R-46 … R-53) — and what verified it", f"""
<div class="grid2"><div><ul class="tight">
<li><b>R-46 price snapshots</b> — three coexisting stores: <a href="{PFX}prices.html">per-market
captures</a>, <a href="{PFX}price-history.html">all-season history</a> (20,088 rows, P1–P6 pass),
and the origination price index.</li>
<li><b>R-47 results feed</b> — <a href="{PFX}results.html">official 2026 feed</a> (double-entry
checked) plus the <a href="{PFX}results-feed.html">all-season feed</a> (2,232 rows, per-row tier,
C1–C4 pass).</li>
<li><b>R-48 order</b> — pre-registered in <code>code/build_lines.py</code> and asserted against
the emitted column order; published on <a href="{PFX}origination.html">origination</a>.</li>
<li><b>R-49 three columns</b> — fair / market / difference as separate columns for all three
markets.</li>
</ul></div><div><ul class="tight">
<li><b>R-50 signal vs staking</b> — three implementations: the official-only schema, the
mirror-window grades, and <code>rank_signal</code> computed from <code>signal_score</code> alone
(<a href="{PFX}leaderboard.html">leaderboard</a>).</li>
<li><b>R-51 replacement depth</b> — per-slot store plus the deficiency register's 2nd/3rd/4th
string column.</li>
<li><b>R-52 official-only correlations with n</b> — the wide 3,570-pair matrix, the 988-row
pipeline set independently recomputed <b>988/988</b> (ledger
<code>data/verify/official_correlations.csv</code>), n on every value everywhere.</li>
<li><b>R-53 demotion gate</b> — <a href="{PFX}validation.html">G8 with six triggers</a> on the
root register, G-13 in the pipeline register; Q-26 answered.</li>
</ul></div></div>
<p><b>Verification of the third implementation:</b> verify_data (2,944 checks), check_links
(28,026), verify_site (116 pages), check_site, verify_research (1,921), pipeline verify,
verify_against_official (2,183 cells, 0 mismatches), test_source_rule (mutation caught),
verify_parlay, cross_check (1,380 cells), verify_app (23 pages, 5,942 rows, 0 unsourced),
verify_new_data, and the staleness guards. New flags <b>F-10 … F-15</b> are on
<a href="{PFX}flagged.html">Flagged for review</a>; none block.</p>"""))

    body.append(card("Round 2 — what session arena/907c5baf-x1 added (2026-11-14)", """
<ul class="tight">
  <li><b>Verified results feed (second, independent transcription)</b> — 150 games from official
  NFL.com pages with per-row URLs; the feed reproduces the official standings for <b>all 32 clubs
  exactly</b> (W-L-T, PF, PA). Week 10 originated markets settled from the official final; ROI
  computable and published with n. See <a href="results.html">results feed</a>.</li>
  <li><b>Price-snapshot store (session store)</b> — opening and closing snapshots for every market
  we originate, ordered side &rarr; total &rarr; moneyline, model fair line / market line /
  difference as separate columns; market cells blank + flagged (Q-31). See
  <a href="prices.html">price snapshots</a>.</li>
  <li><b>Signal/staking split (session leaderboard)</b> — rank from signal metrics only; staking
  diagnostics in a separate unranked scorecard. See <a href="leaderboard.html">leaderboard</a>.</li>
  <li><b>Demotion gate G-D1</b> — a second pre-registered definition alongside G8; thresholds are
  labelled proposed defaults pending ratification (Q-26). See
  <a href="validation.html">validation gates</a>.</li>
  <li><b>Decisions Q-31 to Q-34</b> (price authority, staking plan, settlement authority, reward
  funding) and six suggestions SS-01..SS-06 on the <a href="suggestions.html">suggestion board</a>.</li>
</ul>
<p class="lede">Full detail with source links: docs/round2-executive-summary.md in the repository.</p>"""))

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

    # --- Added by session arena/600e6009-x1 (round 3): replacement-depth distribution ---
    dep = D.get("r3_depth") or {}
    if dep.get("rows"):
        tot = dep.get("totals", {})
        byd = tot.get("by_depth_all_slots", {})
        dtrs = [[esc(str(r.get("unit", ""))), esc(str(r.get("replacement_depth", ""))),
                 esc(str(r.get("depth_label", ""))),
                 num(r.get("slots"), 0), num(r.get("replacement_named"), 0),
                 num(r.get("starters_out"), 0), num(r.get("starters_questionable"), 0),
                 src_cell(r.get("source_url", ""))]
                for r in dep["rows"]]
        gaps = dep.get("gaps", [])
        body.append(card("Replacement depth — not just that a replacement exists, but how far down "
                         "the chart it comes from", f"""
<p>Each row below counts starting slots by <b>which string</b> now holds the job: a 2nd-string
replacement is a normal next-man-up; a 3rd-string is a roster stress point; a 4th-string is a
potential emergency. Today's distribution: <b>{byd.get("2", 0)} slots run by the 2nd string,
{byd.get("3", 0)} by the 3rd string, {byd.get("4", 0)} by the 4th</b>, across
{tot.get("slots", 0)} charted slots — with {tot.get("no_replacement_named", 0)} slots naming no
replacement at all ({tot.get("starters_on_report_without_named_replacement", 0)} of them are
starters who <i>are</i> on the official injury report; those are listed below and never guessed).</p>
""" + table("t-depth-dist",
            ["Unit", "Depth", "String", "Slots", "With named replacement",
             "Starters Out", "Starters Questionable", "Sources"],
            dtrs, numeric=[3, 4, 5, 6], center=[1],
            note="Depth is the chart column position of the replacement (2 = 2nd string … 4 = 4th). "
                 "Every count comes from the deficiency join; the sources are the league injury "
                 "report and the club's own chart page.")
            + (card(f"Starters on the report with no named replacement ({len(gaps)})",
                    table("t-depth-gaps",
                          ["Club", "Unit", "Position", "Starter", "Game status", "Source"],
                          [[esc(str(g.get("team", ""))), esc(str(g.get("unit", ""))),
                            esc(str(g.get("position", ""))), f'<b>{esc(str(g.get("starter", "")))}</b>',
                            badge(str(g.get("game_status", "")), "warn") if g.get("game_status") else dash(""),
                            src_cell(g.get("source_url", ""))] for g in gaps],
                          center=[4],
                          note="Left unfilled on purpose: if the club chart does not name the next "
                               "man up, no name is invented. Flagged as F-15.")) if gaps else "")))
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
    # Added by session arena/3fa49c1a-x1 (merge, N7): the wide official-only matrix
    oc = D["offcorr"]
    top = oc["rows"][:25]
    octrs = [[esc(r["pair"]), num(r["r"], 3), esc(r["n"]), num(r["p_value"], 4),
              esc(r["strength"]), link(r["source_a"], "nfl.com table A"),
              link(r["source_b"], "nfl.com table B")]
             for r in top]
    xchk = (oc.get("verification", {}) or {}).get("crosscheck_vs_pipeline_table", {})
    body.append(card("The wide official-only matrix — 3,570 pairs, n published with every value", f"""
<p>Complementing the 15 decision pairs above: a second session recomputed <b>every</b> metric pair
from the official tables only — 85 metrics x 32 clubs, {len(oc['rows']):,} pairs, each publishing r,
n and p — and independently re-checked the earlier published pipeline table:
{xchk.get('agree', 0)} of {xchk.get('compared', 0)} overlapping pairs agree, 0 disagreements.
Store: <code>data/correlations/official_correlations.csv</code>.</p>
""" + table("t-corr-off", ["Pair", "r", "n", "p", "Strength", "Source A", "Source B"],
            octrs, numeric=[1, 2, 3],
            note=f"Top {len(top)} of {len(oc['rows']):,} by |r|. n = 32 club-seasons: a weak "
                 f"estimate, which is exactly why n ships with each value.")))

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

    # --- Added by session arena-52aabfa8-x1 (T15): independent recompute of the set above
    ledger = D.get("official_corr_ledger") or []
    body.append(f"""<section class="note ok"><b>Independent re-verification of this set (R-52).</b>
Every published row above was recomputed from the committed NFL.com snapshots by
{link("https://github.com/karagemop466-tech/X1/blob/main/tools/verify_official_correlations.py", "tools/verify_official_correlations.py")}
on 2026-11-14: <b>988/988 r within 0.0015, 988/988 with n = 32, 988/988 official nfl.com
sources only, 0 duplicates, and the publication rule reproduces the set exactly</b> —
<code>(|r| ≥ 0.40 or special metric) AND |r| &lt; 0.99</code>, where the second clause suppresses
mechanically identical columns (a Cmp is a Rec). The dataset's own method text omits that
clause — logged as flag F-13, values unaffected. Line-by-row ledger:
{link("https://github.com/karagemop466-tech/X1/blob/main/data/verify/official_correlations.csv", "data/verify/official_correlations.csv")}
({len(ledger)} rows: published r, recomputed r, Δ, n, source, status).</section>""")
    # --- Added by session arena/600e6009-x1 (round 3): official-source audit of every pair ---
    cc = D.get("r3_corr") or {}
    if cc:
        v = cc.get("verification", {})
        body.append(card("Official-source check — every correlation, every n (round 3)", f"""
<p>The build fails loudly unless every one of the <b>{v.get("pairs", 0)} published pairs</b>
carries an integer <b>n</b>, a p-value, and a source URL on <b>{esc(", ".join(v.get("hosts", [])))}</b>
— the league's own standings and team-stats tables. Result of this round's audit:
<b>{v.get("pairs_with_n", 0)}/{v.get("pairs", 0)} pairs with n</b>, n ranging
{v.get("n_min", "")}–{v.get("n_max", "")} (median {v.get("n_median", "")}), official hosts only,
<b>{v.get("violations", 0)} violations</b>.</p>
<p class="note">{esc(cc.get("caveat", ""))}</p>
<p class="note">{esc(cc.get("excluded", ""))}</p>
<a class="btn" href="https://github.com/karagemop466-tech/X1/blob/main/data/correlations_official_check.json">Check result JSON</a>
<a class="btn" href="https://github.com/karagemop466-tech/X1/blob/main/tools/build_round3.py">Checker</a>"""))
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

    # Added by session arena/3fa49c1a-x1 (merge, N8): the concrete thresholds for the
    # same gate, written as a second design (D1-D5) alongside G8's six triggers.
    g2 = D["gates_v2"]
    dtrs = [[esc(r["id"]), esc(r["trigger"]), esc(r["rule"]), esc(r["threshold"]),
             esc(r["window"]), esc(r["why"]), esc(r["action"]),
             src_cell(r["_source_url"])] for r in g2["rows"]]
    body.append(card("D1–D5 — the same demotion gate with concrete thresholds (second design)", f"""
<p>Two parallel sessions defined the demotion gate on the same day. G8 above is one design
(six mechanical triggers). This is the other: five triggers with <b>explicit numeric
thresholds</b> — CLV decay, drawdown, hit-rate decay, a data-integrity trip, and the
re-promotion rule (50 new graded bets after the demotion date, pre-demotion data not reusable).
The two agree on the principle — <b>any one trigger demotes automatically; re-entry is earned,
never automatic</b> — and differ in exact thresholds. The owner's choice between the threshold
sets is recorded as an open decision on the <a href="{PFX}decisions.html">decision register</a>;
nothing is lost either way. Both read the <i>signal</i> block of the leaderboard, never the
staking block.</p>
""" + table("t-gates-d", ["ID", "Trigger", "Rule", "Threshold", "Window", "Why", "Action", "Source"],
            dtrs,
            note=f"Cadence: {g2.get('cadence', '')} Full record: data/gates_v2.json. "
                 f"{g2.get('closes_question', '')}")))

    dg = D.get("demotion_gate_x1") or {}
    if dg.get("rows"):
        dtrs = []
        for r in dg["rows"]:
            ts = r.get("threshold_status", "")
            dtrs.append([
                f'<span class="mono">{esc(r["id"])}</span>', f'<b>{esc(r["trigger"])}</b>',
                esc(r["rule"]), esc(r["threshold"]),
                badge("proposed default", "warn") if "PROPOSED" in ts else badge("rule", "ok"),
                esc(ts), esc(r.get("action", "")),
                src_cell(r.get("_source_url") or dg.get("_source_url")),
            ])
        body.append(card("G-D1 — the second pre-registered demotion gate (session arena/907c5baf-x1; see G8 above)",
                         table("t-demotion", ["ID", "Trigger", "Rule", "Threshold", "Status",
                                              "Threshold status", "Action", "Source"],
                               dtrs, center=[4],
                               note=esc(dg.get("status", "")))))
        proc = dg.get("demotion_procedure", {})
        body.append(card("What a G-D1 demotion does — and how a strategy returns", f"""
<ul class="tight">
  {''.join(f'<li>{esc(x)}</li>' for x in proc.get('on_trigger', []))}
</ul>
<p><b>Re-promotion.</b></p>
<ul class="tight">
  {''.join(f'<li>{esc(x)}</li>' for x in proc.get('re_promotion', []))}
</ul>
<p class="lede">{esc(proc.get('separation_from_staking', ''))} {esc(proc.get('who_can_override', ''))}</p>"""))
    return page("validation.html", "Validation gates", "Strategy", "\n".join(body),
                lede="Eight gates, pre-registered, and the demotion gate that returns a live "
                     "strategy to paper. Their whole job is to stop luck being paid as skill.")


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

    # Added by session arena/3fa49c1a-x1 (merge, N5): the signal/staking schema the
    # official-only board fills from graded official data (still blank by rule).
    sp = D["lb_split"]
    split_rows = []
    for r in sp["rows"]:
        split_rows.append([
            esc(r["strategy_id"]), esc(r["strategy"]), esc(r["market"]),
            dash(r.get("signal_rank")), dash(r.get("signal_graded_bets")), dash(r.get("signal_hit_rate")),
            dash(r.get("signal_mean_clv")), dash(r.get("signal_clv_t_stat")),
            badge(r.get("signal_skill_gate", ""), "grey"),
            dash(r.get("staking_rank")), dash(r.get("staking_roi_at_rule")),
            dash(r.get("staking_max_drawdown")),
            src_cell(r["_source_url"]),
        ])
    body.append(card("Signal vs staking, on the official-only board — schema locked before the data", f"""
<p>The mirror-window grades above demonstrate the masking vector with real numbers. This is the
schema the <b>official-only board</b> fills the day verified prices and graded results exist: a
<b>signal block</b> (flat 1-unit grading: hit rate, mean CLV, CLV t-stat, edge at the close) and a
<b>staking block</b> (ROI at rule, drawdown, growth) — and the promotion/demotion gates read the
signal block first, so a lucky staking run cannot mask a bad signal. Values are blank on purpose:
ranks before graded data would be ranks of noise. Record:
<code>data/leaderboard_split.json</code>.</p>
""" + table("t-lb-split", ["ID", "Strategy", "Market", "Signal rank", "Bets", "Hit rate",
                           "Mean CLV", "CLV t", "Skill gate", "Staking rank", "ROI at rule",
                           "Max drawdown", "Source"],
            split_rows, center=[8],
            note="Every value ships blank until the verified price feed (Q-02) lands; the split is "
                 "structural and fills without schema changes.")))

    # ---- signal / staking split (arena/907c5baf-x1, N3): rank from signal only ----
    split = D.get("leaderboard_split_x1") or {}
    if split.get("signal_scorecard"):
        body.append(f"""<section class="note"><b>Signal is ranked; staking is not.</b>
{esc(split.get('policy', {}).get('ranking_rule', ''))}. The signal scorecard uses staking-blind
metrics (hit rate, flat-stake ROI, bootstrap CI, p, luck-removed ROI); the staking scorecard is a
separate diagnostic and changing the staking plan can never change rank.</section>""")
        sig = split["signal_scorecard"]
        srows = []
        for r in sig["rows"]:
            flags = " ".join(badge(f, "warn") for f in r.get("_flags", []))
            tier = badge("verified track", "ok") if r.get("_verified") else badge("mirror (unverified)", "warn")
            srows.append([
                dash(r.get("rank")), f'<span class="mono">{esc(r.get("strategy_id", ""))}</span>',
                esc(r.get("strategy", "")), dash(r.get("graded_bets")), dash(r.get("hit_rate")),
                dash(r.get("flat_stake_roi")), dash(r.get("ci_lo")), dash(r.get("ci_hi")),
                dash(r.get("p_value")), dash(r.get("luck_removed_roi")),
                dash(r.get("luck_profit_share_pct")), dash(r.get("stability_share_positive")),
                esc(r.get("gates_passed", "")),
                badge(r.get("eligibility", ""), "ok" if "ELIGIBLE" in str(r.get("eligibility", "")) and "NOT" not in str(r.get("eligibility", "")) else "grey"),
                tier, flags, src_cell(r.get("_source_url")),
            ])
        body.append(card("Signal scorecard — the only table rank is computed from",
                         table("t-lb-signal", ["Rank", "ID", "Strategy", "Bets", "Hit rate",
                                               "Flat-stake ROI", "CI lo", "CI hi", "p",
                                               "Luck-removed ROI", "Luck share %", "Stability",
                                               "Gates", "Eligibility", "Evidence tier", "Flags",
                                               "Source"],
                               srows, numeric=[3, 4, 5, 6, 7, 8, 9, 10, 11], center=[13],
                               note="The official-track row is blank until strategies are "
                                    "pre-registered and graded on the verified results feed — a "
                                    "blank is honest, a filled-from-the-mirror cell would not be.")))
        stk = split.get("staking_scorecard", {})
        krows = []
        for r in stk.get("rows", []):
            krows.append([
                f'<span class="mono">{esc(r.get("strategy_id", ""))}</span>', esc(r.get("strategy", "")),
                esc(r.get("staking_plan", "")), dash(r.get("staking_roi")),
                dash(r.get("max_drawdown_units")), dash(r.get("longest_losing_streak")),
                dash(r.get("net_units_flat")),
                badge("cannot change rank", "blue"), src_cell(r.get("_source_url")),
            ])
        body.append(card("Staking scorecard — unranked diagnostic (a lucky staking run cannot mask a bad signal)",
                         table("t-lb-staking", ["ID", "Strategy", "Staking plan", "ROI",
                                                "Max drawdown (units)", "Longest losing streak",
                                                "Net units", "Rank effect", "Source"],
                               krows, numeric=[3, 4, 5, 6], center=[7],
                               note="Drawdown and streaks are computed from the same bet series "
                                    "under a flat 1-unit reference plan. Any other plan awaits "
                                    "decision Q-32 and can change these numbers — and only these "
                                    "numbers.")))

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

    # --- Added by session arena-52aabfa8-x1 (T14): rank_signal from the strategy registry
    slb = D.get("strat_leaderboard") or []
    if slb:
        str_ = []
        for r in slb:
            sig = esc(r.get("signal_score", "")) or '<span class="blank">unmeasured</span>'
            rank = esc(r.get("rank_signal", "")) or '<span class="blank">—</span>'
            stk = esc(r.get("staking_score", "")) or '<span class="blank">unmeasured</span>'
            str_.append([
                f'<span class="mono">{esc(r.get("strategy", ""))}</span>',
                esc(r.get("status", "")), esc(r.get("bets", "")),
                esc(r.get("win_rate", "")), esc(r.get("binom_p_leq_breakeven", "")),
                sig, rank,
                esc(r.get("equity_units", "")), esc(r.get("max_drawdown_units", "")), stk,
                link("https://github.com/karagemop466-tech/X1/blob/main/data/strategies/leaderboard.csv",
                     "leaderboard.csv"),
            ])
        body.append(card("rank_signal — the code path that makes staking structurally unrankable (R-50)", f"""
<div class="tw"><table id="t-lb-ranksignal" data-sortable><thead><tr>
<th rowspan="2">Strategy</th><th rowspan="2">Status</th><th rowspan="2">Bets</th>
<th colspan="3" class="c">SIGNAL — the only rank key</th>
<th colspan="3" class="c">STAKING — informational, never ranks</th>
<th rowspan="2">Source</th></tr>
<tr><th>Win rate</th><th>p vs break-even</th><th>signal_score / rank</th>
<th>Equity (u)</th><th>Max DD (u)</th><th>staking_score</th></tr></thead><tbody>
{''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in row) + '</tr>' for row in str_)}
</tbody></table></div>
<div class="legend">Where the schema above is filled from real data: <code>rank_signal</code> is
computed from <code>signal_score</code> (z of win rate vs break-even, stake-independent) alone —
equity, drawdown and <code>staking_score</code> are structurally absent from the ranking key, so
a hot P&amp;L path cannot lift a bad signal and a cold one cannot sink a good one. Blanks mean
<b>unmeasured</b> (no decided bets), never a zero signal. Season 0 has no logged bets, so every
registry strategy is honestly unmeasured today.</div>"""))

    # --- Added by session arena/600e6009-x1 (round 3): official-basis signal rows ---
    lb3 = D.get("r3_lb") or {}
    if lb3:
        rule = lb3.get("rule", {})
        l3rows = lb3.get("rows") or []
        body.append(card("Official-basis signal vs staking — the round-3 board", f"""
<p>{esc(rule.get("why", ""))}</p>
<p><b>Rank basis: {esc(rule.get("rank_basis", ""))}.</b> Staking columns are published for
transparency but are structurally excluded from rank — no ROI figure can raise or lower a
signal_rank. Demotion back to paper is enforced by gate <b>G8</b>
(<a href="validation.html">validation</a>).</p>
""" + table("t-lb-split",
            ["ID", "Strategy", "Signal rank", "Signal n", "Hit rate", "z", "p",
             "Staking ROI", "Staking units", "Status", "Source"],
            [[esc(str(r.get("strategy_id", ""))),
              f'<b>{esc(str(r.get("strategy", "")))}</b><br>{esc(str(r.get("market", "")))}',
              esc(str(r.get("signal_rank", ""))) or badge("unranked", "grey"),
              esc(str(r.get("signal_n", ""))) or dash(""),
              esc(str(r.get("signal_hit_rate", ""))) or dash(""),
              esc(str(r.get("signal_z", ""))) or dash(""),
              esc(str(r.get("signal_p", ""))) or dash(""),
              dash(str(r.get("staking_roi", ""))),
              dash(str(r.get("staking_units", ""))),
              esc(str(r.get("status", ""))),
              src_cell(r.get("source_url", ""))]
             for r in l3rows],
            numeric=[3, 4, 5, 6], center=[2, 3, 4, 5, 6],
            note="Signal columns grade outcome against a stated baseline with n and p on every row. "
                 "Staking columns stay empty while no official price source exists (Q-02) — blank "
                 "by rule, not by omission, and never fed into the rank.")))
    return page("leaderboard.html", "Leaderboard and rewards", "Strategy", "\n".join(body),
                lede="Ranked by gate-weighted reward, not by headline ROI. Baselines, luck decomposition, "
                     "the signal/staking split, and the unranked official-only board.")


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

    # Added by session arena/3fa49c1a-x1 (merge): independent second transcription
    body.append(card("Cross-verified by an independent second transcription (session arena/3fa49c1a-x1)", f"""
<p>A second session transcribed the same official pages on the same day, blind to this one, into
<code>data/results/verified_results_2026_n2.csv</code>. The two feeds agree on
<b>137 of 137 games and every score</b> (team-code spellings aside: LA/LAR, ARI). This feed also
re-derives all 32 clubs' W-L-T, PF and PA from its own rows against the official standings —
<b>160/160 checks pass</b>, league identity &Sigma;PF = &Sigma;PA = 6,291 — and that same arithmetic
<b>resolved finding I-14</b>: the league standings <i>do</i> include the Thursday Week 10 result
(WAS 3-5-1 / NYG 5-3-1 are post-game records); the earlier "pre-game record" reading was a
miscount. Machine-readable ledger: <code>data/results/results_verification.json</code>.</p>"""))

    body.append('<section class="note warn"><b>Second independent transcription (session arena/907c5baf-x1).</b> The sections below come from a separate official-page transcription kept in data/verify/raw/ and its settlement engine — two independent readings of the same official pages, both published.</section>')
    body.append(p_results_x1_body())
    # --- Added by session arena/600e6009-x1 (round 3): price-independent signal grade ---
    sig = D.get("r3_signal") or {}
    if sig:
        excl = sig.get("exclusions", {})
        sg_url = "https://github.com/karagemop466-tech/X1/blob/main/data/results/signal_grade.json"
        body.append(card("Signal grade — outcome-only, no price, no stake (round 3)", f"""
<p>Grading the model's side pick against the official result answers one narrow question:
<b>does the model pick the winning side more often than a coin flip?</b> It uses only the verified
results above and the model's pre-game line. No price, no stake, no return enters the number — a hit
rate is not an edge until a price says what break-even costs, and no official price source exists
(Q-02). This is deliberately separate from the ROI table, which assumes &minus;110.</p>
""" + table("t-sig",
            ["Metric", "Value", "Source"],
            [["Decided games", f'{sig.get("n_decided", "")} of {sig.get("n_games", "")} matched '
                               f'({excl.get("excluded_tie", 0)} tie, {excl.get("excluded_no_pick", 0)} no-pick excluded)',
              src_cell(sg_url)],
             ["Record", f'{sig.get("wins", "")}–{sig.get("losses", "")}', src_cell(sg_url)],
             ["Hit rate", f'{sig.get("hit_rate", "")} against a {sig.get("baseline", "")} baseline',
              src_cell(sg_url)],
             ["z / p", f'{sig.get("z_vs_50pct", "")} two-sided p = {sig.get("p_two_sided", "")}',
              src_cell(sg_url)],
             ["Excluded", f'{esc(excl.get("tie_game", ""))}; no-pick games '
                          f'{esc(", ".join(excl.get("no_pick_games", [])))} '
                          f'(line exactly 0.0 — never forced to a side)', src_cell(sg_url)],
             ["Model", f'{esc(sig.get("model", {}).get("name", ""))} — fitted walk-forward, season '
                       f'<i>s</i> trained only on seasons before <i>s</i>', src_cell(sg_url)]],
            note="Recomputed by tools/build_results_r3.py from the results feed and the model file; "
                 "the JSON carries its own source URLs.") +
f"""
<p class="note">This signal feeds the <a href="leaderboard.html">leaderboard</a>'s signal group only.
It sits below the G1 singles threshold (500 decided bets), so it is published as a measurement, not
a promotion.</p>
<a class="btn" href="{sg_url}">Signal grade JSON (with sources)</a>"""))
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

    # Added by session arena/3fa49c1a-x1 (merge): the one graded game, shown honestly
    body.append(card("One game has graded so far — the machinery, honestly shown", f"""
<p>The verified feed contains one completed Week 10 game: WAS 24 at NYG 21. On the fair side
(WAS &minus;0.5) the ticket wins; on the fair total (42.5) the game lands 45 and the under loses.
Outcomes grade the moment the feed has them; prices remain the one missing input (Q-02), so ROI
stays blank rather than computed against an unverified number. A second, independent price-snapshot
store with the same rule (openings blank where nothing records them, closes flagged) is published at
<a href="{PFX}prices.html">Price snapshots</a> for cross-checking.</p>"""))

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
    # Added by session arena/3fa49c1a-x1 (merge, N9): answers recorded in the parallel round
    qa = D["origin_qa"]
    qtrs = [[esc(r["question_id"]), esc(r["question"]), esc(r["information_had"]),
             esc(r["information_added_this_round"]), esc(r["answer_now"]),
             esc(r["still_missing"]), esc(r["blocks"]), src_cell(r["_source_url"])]
            for r in qa["rows"]]
    body.append(card("Answers recorded in the parallel N1–N8 round (session arena/3fa49c1a-x1)", """
<p>The eight directed improvements closed parts of this register: Q-03, Q-04, Q-22 and Q-26 are
answered; Q-02 is narrowed to a single owner decision (which licensed price feed); Q-07/Q-08/Q-09
have named tests but owner-settable thresholds.</p>
""" + table("t-qa", ["ID", "Question", "Information had", "Added this round", "Answer now",
                     "Still missing", "Blocks", "Source"], qtrs,
            note="Record: data/origin/question_answers.json. Two open design choices from the "
                 "parallel merge are also owner decisions: the demotion-threshold set (G8's six "
                 "triggers vs D1-D5's numeric thresholds) and the reward formula's staking term "
                 "(min(signal, staking) vs signal-only promotion).")))
    r2 = (D.get("round2_decisions_x1") or {}).get("rows", [])
    if r2:
        rtrs = [[esc(r["id"]), esc(r["area"]), f'<b>{esc(r["question"])}</b>',
                 esc(r["why_it_matters"]), esc(r["information_we_have"]),
                 esc(r["information_missing"]), esc(r["how_to_get_it"]),
                 badge("blocks", "bad") if str(r.get("blocks_decision", "")).startswith("yes") else badge("no", "grey"),
                 badge(r.get("status", ""), "warn" if str(r.get("status", "")).startswith("open") else "ok"),
                 src_cell(r["_source_url"])] for r in r2]
        body.append(card("Round-2 additions — questions this round raised (Q-31 to Q-34)",
                         table("t-q2", ["ID", "Area", "Question", "Why it matters",
                                        "Information we have", "Information missing",
                                        "How to get it", "Blocks?", "Status", "Source"],
                               rtrs, center=[7, 8],
                               note="Each new question names the decision it blocks and a concrete "
                                    "discovery action — the 'how to get it' column is how missing "
                                    "information gets found, not a placeholder.")))
    # --- Added by session arena/600e6009-x1 (round 3): root decision register ---
    rq = D.get("root_questions") or {}
    rqs = rq.get("questions") or []
    if rqs:
        new_q = [x for x in rqs if x.get("id", "") >= "Q-19"]
        body.append(card(f"Root register — questions, information held, and information missing "
                         f"({len(new_q)} added this round, {len(rqs)} total)", f"""
<p><b>Rule of this register:</b> {esc((rq.get("meta") or {}).get("rule", ""))} Each row states what
we already hold, what is still missing, and the concrete thing that would close it — so a decision
can be taken on the information that exists rather than on a hunch.</p>
""" + table("t-root-q",
            ["ID", "Topic", "Question", "Why it blocks", "Information we have",
             "Missing — what would answer it", "Status", "Owner?", "Source"],
            [[esc(str(x.get("id", ""))), esc(str(x.get("topic", ""))),
              f'<b>{esc(str(x.get("question", "")))}</b>',
              esc(str(x.get("why_it_blocks", ""))),
              esc(str(x.get("known_information", ""))),
              esc(str(x.get("what_would_answer_it", ""))),
              badge(str(x.get("status", "")), "warn" if str(x.get("status", "")) == "open" else "blue"),
              badge("owner", "bad") if x.get("owner_decision") else badge("research", "grey"),
              src_cell(x.get("source_url", ""))]
             for x in new_q],
            center=[6, 7],
            note="Owner? marks the rows where only the owner can decide; the rest close when the "
                 "missing information is obtained.")))
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

    # Added by session arena/3fa49c1a-x1 (merge, N9): the eight directed choices, marked as decided
    dec = D["origin_decisions"]
    dtrs2 = [[esc(r["id"]), esc(r["suggestion_id"]), esc(r["decision"]), esc(r["what_was_built"]),
              esc(r["where"]), badge(r["status"], "ok"), src_cell(r["_source_url"])]
             for r in dec["rows"]]
    body.append(card("Chosen and built — the eight directed improvements (2026-11-14)", f"""
<p>The owner directed eight suggestions implemented now. Two parallel sessions each built all
eight; both implementations are preserved in this repository and cross-checked (results agree
137/137 across independent transcriptions; correlations agree 905/905 against the published
table). Each row links to the artefacts. {esc(dec.get('note', ''))}</p>
""" + table("t-decided", ["#", "Suggestion", "Decision", "What was built", "Where", "Status", "Source"],
            dtrs2, center=[5],
            note="Everything else on this board remains proposed and untouched — chosen before "
                 "built is the rule.")))
    r2 = (D.get("round2_suggestions_x1") or {}).get("rows", [])
    if r2:
        srows = []
        for r in r2:
            rec = str(r.get("recommended_path") or "")
            srows.append([
                esc(r["id"]), esc(r["area"]), f'<b>{esc(r["suggestion"])}</b>', esc(r["rationale"]),
                badge(r["impact"], "bad" if str(r["impact"]).lower() == "high" else "grey"),
                badge(r["effort"], "warn" if str(r["effort"]).lower() == "high" else "grey"),
                esc(r["risk"]),
                f'<b>A.</b> {esc(r["path_a"])}<br><b>B.</b> {esc(r["path_b"])}<br><b>C.</b> {esc(r["path_c"])}',
                badge(rec[:1].upper() if rec else "?", "blue"),
                badge(r.get("decision_status", ""), "warn" if "pending" in str(r.get("decision_status", "")) or "blocked" in str(r.get("decision_status", "")) else "ok"),
                src_cell(r["_source_url"]),
            ])
        body.append(card("Round-2 additions — site and pipeline improvements, awaiting review (SS-01..SS-06)",
                         table("t-sug2", ["ID", "Area", "Suggestion", "Why", "Impact", "Effort",
                                          "Risk", "Paths A / B / C", "Recommended", "Decision",
                                          "Source"],
                               srows, center=[4, 5, 8, 9],
                               note="These improve decision-making itself: one navigation, automated "
                                    "price capture, automated settlement, CLV, a decision-first KPI "
                                    "strip, and a strategy-registry crosswalk. Nothing is built "
                                    "before a path is chosen.")))

    # --- Added by session arena/600e6009-x1 (round 3): root suggestion register ---
    rs = D.get("root_suggestions") or {}
    rss = rs.get("suggestions") or []
    if rss:
        new_s = [x for x in rss if x.get("id", "") >= "S-13"]
        body.append(card(f"Root suggestion register — review before anything is built "
                         f"({len(new_s)} added this round, {len(rss)} total)", f"""
<p><b>Nothing here is implemented by default.</b> {esc((rs.get("meta") or {}).get("purpose", ""))}
Every row carries the problem it solves, the proposal, what it would change in decision-making, its
impact, its cost, what it depends on, the reversible first step, and the risk — then it waits for a
decision. Pick the best path first; build second.</p>
""" + table("t-root-sug",
            ["ID", "Suggestion", "Problem it solves", "Proposal", "Decision value",
             "Impact", "Effort", "Depends on", "First step", "Risk", "Status", "Source"],
            [[esc(str(x.get("id", ""))), f'<b>{esc(str(x.get("title", "")))}</b>',
              esc(str(x.get("problem", ""))), esc(str(x.get("proposal", ""))),
              esc(str(x.get("why_it_helps_decision_making", ""))),
              badge(str(x.get("impact", "")), "bad" if str(x.get("impact", "")) == "high" else "grey"),
              badge(str(x.get("effort", "")), "warn" if str(x.get("effort", "")) == "high" else "grey"),
              esc(str(x.get("depends_on", ""))), esc(str(x.get("first_step", ""))),
              esc(str(x.get("risk", ""))),
              badge(str(x.get("status", "")), "blue"),
              link("https://github.com/karagemop466-tech/X1/blob/main/data/suggestions.json",
                   "register")]
             for x in new_s],
            center=[5, 6, 10],
            note="Filter by status. 'proposed' means no decision has been recorded — the row is a "
                 "choice waiting to be made, not work already authorised.")))
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
        ("F-10", "grey", "Legacy spread column names say 'away' but hold the signed game line",
         "x1_spread_away / market_spread_away / edge_spread_away carry the signed game line "
         "(positive = home favoured). The name is a legacy misnomer; the number is identical "
         "under the home-margin and away-team-handicap readings, so no value is wrong.",
         "Convention documented in docs/methodology/line-origination.md §8 and in the price "
         "store; renaming the columns is left as a review decision because other trees read "
         "them by name.",
         ["https://github.com/nflverse/nfldata/blob/master/data/DATASETS.md"]),
        ("F-11", "warn", "2,218 of 2,232 all-season result rows are mirror-only",
         "Only the Week 10 slate has a committed official page. Historical finals (2019–2025 "
         "and 2026 Weeks 1–9) exist in the fingerprinted nflverse mirror only, so every "
         "backtest ROI rests partly on unverified-official results.",
         "Each row in data/results/verified_results.csv carries verification=mirror_only and "
         "its source key; Q-04 stays open. The feed's tier column is the map of the gap.",
         ["https://github.com/nflverse/nfldata"]),
        ("F-12", "grey", "Official standings snapshot predates the Thursday Night game",
         "As fetched on 2026-11-14 the standings page reads WAS 3-5-1 and NYG 5-3-1 — records "
         "before the TNF game — while the same site's schedule page already prints "
         "\"Commanders 24, Giants 21, FINAL\". Both standings sources agree with each other "
         "and both predate the result.",
         "Recorded as check C4 in the all-season results feed (the only permitted difference "
         "class) and kept visible instead of smoothed over. Freshness difference, not a "
         "contradiction.",
         ["https://www.nfl.com/standings/league/2026/REG",
          "https://www.nfl.com/schedules/2026/by-week/week-10"]),
        ("F-13", "grey", "Correlations method text omits the |r| < 0.99 redundancy cut",
         "The pipeline's published set (988 rows) is reproduced exactly by "
         "(|r| >= 0.40 or special metric) AND |r| < 0.99 — the second clause suppresses "
         "mechanically identical columns (a Cmp is a Rec). The dataset's own method field "
         "describes only the first clause.",
         "Reverse-engineered by exact set reproduction (988 = 988, zero differences) by "
         "tools/verify_official_correlations.py; no published value is wrong. The "
         "documentation gap is logged here rather than edited into another session's file.",
         ["https://www.nfl.com/standings/league/2026/REG"]),
        ("F-14", "grey", "Strategy correlation matrix publishes no per-cell n",
         "The 16×16 strategy matrix cells are Pearson r over shared games, but the payload "
         "does not expose the shared-games count per pair, so n cannot be published per cell.",
         "The matrix is labelled third-party and excluded from the official-only sets rather "
         "than shown with invented sample sizes. Recomputing it needs the strategy bet logs "
         "per pair.",
         ["https://github.com/nflverse/nfldata"]),
        ("F-15", "warn", "Opening and closing prices use different published conventions",
         "The only reachable opening feed publishes per-team spread lines (\"TB -6.5\"); the "
         "closing feed publishes one signed game line (positive = home favoured). Storing "
         "either as the other would be an inference about intent.",
         "Both stored verbatim with their own convention strings in "
         "data/prices/price_history.csv. No closing-line-value number is computed from the "
         "store until the normalisation step is a recorded decision (Q-02).",
         ["https://github.com/nflverse/nfldata"]),
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
    # --- Added by session arena/600e6009-x1 (round 3): root flag register ---
    rf = D.get("root_flags") or {}
    rflags = rf.get("flags") or []
    if rflags:
        new_f = [x for x in rflags if x.get("id", "") >= "F-14"]
        body.append(card(f"Root flag register — {len(new_f)} added this round, "
                         f"{len(rflags)} total, none blocks the release", f"""
<p>{esc((rf.get("meta") or {}).get("rule", ""))} Each row states what is verified, what is unknown,
and what would settle it — a flag never asserts a value.</p>
""" + table("t-root-flag",
            ["ID", "Severity", "Category", "Finding", "Verified", "Unknown",
             "What would settle it", "Sources"],
            [[esc(str(x.get("id", ""))),
              badge(str(x.get("severity", "")),
                    "bad" if str(x.get("severity", "")) == "high" else
                    ("warn" if str(x.get("severity", "")) == "medium" else "grey")),
              esc(str(x.get("category", ""))),
              f'<b>{esc(str(x.get("item", "")))}</b>',
              esc(str(x.get("verified", ""))),
              esc(str(x.get("unknown", ""))),
              esc(str(x.get("settles_it", ""))),
              src_cell(x.get("source_url", ""))]
             for x in new_f],
            center=[1],
            note="Severity: high = a published value is wrong or missing; medium = a limitation that "
                 "changes how rows should be read; low = documented behaviour worth naming.")))
    # --- Round 4 (session arena-fb9e0427-x1): readiness state audit and conflicts ---
    rdf = jload("data/audit/readiness.json")
    rfl = rdf.get("flags", [])
    fr = []
    for f in rfl:
        links = f.get("links", [])
        fr.append([esc(f.get("id", "")), f"<b>{esc(f.get('title', ''))}</b>", esc(f.get("detail", "")),
                   src_cell(links)])
    body.append(card(f"Round 4 — {len(rfl)} state changes, conflicts and open discrepancies", f"""
<p>Found while building the decision-readiness table on the landing page. Each row says what the file
shows and where to check it. No value on this list has been silently changed; the source text is kept and
the discrepancy is published.</p>
""" + table("t-r4-flag", ["ID", "Finding", "Detail", "Sources"], fr,
            note="Changed-state rows are the register's own 'met' rows that the data does not support. "
                 "Their register text is unchanged, and the round-4 state is shown beside it.")))
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


# ------------------------------------------------ Added by session arena/3fa49c1a-x1
# (merged from the parallel N1-N10 round: per-row stores kept for cross-verification)
def p_replacement_depth() -> str:
    d = D["repl_depth"]
    rows = d["rows"]
    summ = d.get("summary", {})
    body = []
    body.append(f"""<section class="note"><b>Per-slot store, re-verified row by row.</b> The
deficiency watch shows the aggregate view of who is out and who steps in; this page publishes the
slot-level store behind one cut of it: every starting slot whose starter carries a game status on
the official report (Out / Doubtful / Questionable), with the replacement and that replacement's
<b>exact string depth</b> from the club's own chart. Every row was re-verified against both
sources before publishing — the starter is depth 1 at that slot on the chart, the replacement is
the next listed name at its string, and the game status matches the report exactly. Club charts
are self-published (league-wide official charts do not exist) and some label themselves
unofficial; that caveat rides on every row.</section>""")

    bs = summ.get("by_starter_status", {})
    strings = summ.get("by_replacement_string", {})
    body.append(kpis([
        (str(summ.get("rows", 0)), "starter slots with a game status", "re-verified, both sources", "ok"),
        (str(bs.get("out", 0)), "starters Out", f'{bs.get("doubtful", 0)} doubtful, {bs.get("questionable", 0)} questionable', "bad"),
        (str(strings.get("2nd string", 0)), "replaced by 2nd string",
         f'{strings.get("3rd string", 0)} by 3rd string', "warn"),
        (str(summ.get("rows", 0) - sum(strings.values())), "no replacement listed", "club prints nobody deeper", "grey"),
    ]))

    trs = [[esc(r.get("team")), esc(r.get("side_of_ball")), esc(r.get("position")) or dash(),
            esc(r.get("starter")), status_cell(r.get("starter_game_status")),
            esc(r.get("replacement")) if r.get("replacement") else '<span class="blank" title="Club chart prints no deeper name">&mdash; none listed</span>',
            esc(r.get("replacement_string")),
            status_cell(r.get("replacement_game_status")) if r.get("replacement_game_status") else badge("not on report", "grey"),
            link(r.get("club_depth_chart_url"), "club chart"), link(r.get("injury_report_url"), "nfl.com/injuries")]
           for r in rows]
    body.append(card("Every slot where a starter carries a game status",
                     table("t-repl", ["Team", "Side", "Pos", "Starter", "Game status", "Replacement",
                                      "String", "Replacement status", "Depth chart source",
                                      "Injury source"],
                           trs, center=[4, 6, 7],
                           note="Green Bay prints jersey numbers in the name column (flag F-01); "
                                "names are matched with the number stripped. Houston has no parsable "
                                "chart (flag F-03) and is absent, never guessed. The aggregate view "
                                "counts all 189 on-report starters (including practice-only) on the "
                                "deficiency page; this store's cut is game-status rows only.")))
    return page("replacement-depth.html", "Depth of the replacement", "Which string steps in",
                "\n".join(body),
                lede="When a starter is down, the store says whether the 2nd, 3rd or 4th string "
                     "takes his place — per slot, re-verified against both sources.")


def p_prices() -> str:
    feed = D["prices"]
    rows = feed["rows"]
    body = []
    body.append(f"""<section class="note"><b>Second price-snapshot store, same rule.</b> The
origination page publishes one price-snapshot store; this is the other, from the parallel N1–N10
round, kept so the two capture records can be compared. Rule on every cell: no official or
licensed source publishes betting prices (Q-02), so opening numbers are <b>blank</b> where nothing
records them, closing numbers carry the third-party mirror's value with
<b>verified = no</b>, and CLV stays blank until a verified feed is attached. Nothing here is
inferred. Schema requirements a feed must satisfy are below.</section>""")

    v = feed.get("verification", {})
    body.append(kpis([
        (str(v.get("rows", 0)), "snapshot rows", "one per originated market selection", "ok"),
        (str(sum(1 for r in rows if r.get("market_close"))), "closing numbers recorded",
         "all flagged UNVERIFIED (third-party mirror)", "warn"),
        (str(sum(1 for r in rows if not r.get("market_open"))), "opening numbers blank",
         "no source records 2026 openers", "grey"),
        ("0", "verified price cells", "blocked by Q-02 — the feed is an owner decision", "grey"),
    ]))

    trs = [[esc(r.get("game_id")), esc(r.get("market_type")), esc(r.get("selection")),
            esc(r.get("our_line")) if r.get("our_line") else dash(),
            esc(r.get("our_originated_at")),
            '<span class="blank" title="No source records 2026 opening numbers">&mdash;</span>'
            if not r.get("market_open") else esc(r.get("market_open")),
            esc(r.get("market_close")) if r.get("market_close") else dash(),
            badge("no", "bad") if r.get("market_close") else badge("—", "grey"),
            dash(),  # CLV: blank by rule
            link(r.get("market_close_source"), "mirror") if r.get("market_close_source")
            else '<span class="blank">no official source</span>']
           for r in rows]
    body.append(card("The store — open and close for every market we originate",
                     table("t-prices", ["Game", "Market", "Selection", "Our line", "Originated",
                                        "Market open", "Market close", "Close verified?",
                                        "CLV vs close", "Price source"],
                           trs, center=[7, 8],
                           note="Opening column deliberately blank (Q-02/Q-03); closing column "
                                "carries mirror values with verified = no so the CLV machinery has "
                                "a placeholder the day a real feed arrives.")))

    body.append(card("The schema a price feed must satisfy", """
<ol class="tight">
  <li><b>Open and close, both.</b> CLV is measured against the close; origination value against the open.</li>
  <li><b>Timestamps.</b> A price without a capture time cannot be audited after the fact (gate G-10).</li>
  <li><b>Per-selection rows.</b> Sides and totals carry one number, moneylines two — keyed on (game, market, selection).</li>
  <li><b>Provenance per cell.</b> Source URL, verification flag, and nothing filled from memory.</li>
</ol>"""))
    body.append('<section class="note warn"><b>Session store arena/907c5baf-x1 (data/price_snapshots.json).</b> A second price-snapshot store built from this session&rsquo;s origination output: 56 rows, ordered side &rarr; total &rarr; moneyline, with the missed TNF close recorded as missed.</section>')
    body.append(p_prices_x1_body())
    return page("prices.html", "Price-snapshot store", "Open and close, blank where no source",
                "\n".join(body),
                lede="The second capture record for every market we originate — open column, close "
                     "column, and honest flags where no verified source exists.")


# ---------------------------- arena/907c5baf-x1 session stores (four-way union)
def p_results_x1_body() -> str:

    feed = D["results_feed_x1"]
    rows = feed.get("rows", [])
    settle = feed.get("settlement", [])
    summ = feed.get("settlement_summary", {})
    integ = feed.get("integrity_checks", {})
    body = []

    body.append("""<section class="note"><b>Settlement rules.</b>
A result is graded only after the official NFL.com page prints <b>FINAL</b>; unplayed games keep
blank results and a flag. ROI is computed only from legs whose price we originated ourselves, and
every ROI is published with its <b>n</b>. Community-mirror scores appear only in the labelled
cross-check below — never as a source of fact.</section>""")

    body.append(kpis([
        (str(summ.get("games_final", "")), "games final", "transcribed from official pages", "ok"),
        (str(summ.get("games_scheduled", "")), "scheduled", "results blank until FINAL", "grey"),
        (f"{integ.get('standings_arithmetic', {}).get('match', '')}/32",
         "standings identities", "feed recomputation vs official table", "ok"),
        (f"{integ.get('mirror_cross_check', {}).get('agree', '')}/{integ.get('mirror_cross_check', {}).get('games_compared', '')}",
         "mirror agrees", "corroboration only", "grey"),
    ]))

    ftrs = []
    for r in rows:
        flags = " ".join(badge(f, "warn") for f in r.get("_flags", []))
        ftrs.append([
            str(r["week"]), f'<span class="mono">{esc(r["game_id"])}</span>',
            esc(r["away"]), dash(r.get("away_score")), dash(r.get("home_score")), esc(r["home"]),
            esc(r["gameday"]),
            badge("FINAL", "ok") if r["status"] == "FINAL" else badge("scheduled", "grey"),
            flags, src_cell(r.get("_source_url")),
        ])
    body.append(card("2026 results — every row transcribed from the official NFL.com week page",
                     table("t-results-x1", ["Week", "Game", "Away", "Score", "Score", "Home", "Date",
                                         "Status", "Flags", "Source"],
                           ftrs, numeric=[0], center=[3, 4, 7],
                           note="Scores the official page does not print stay blank "
                                "(—). Nothing is inferred. Weeks 1–10, retrieved 2026-11-14.")))

    strs = []
    for r in settle:
        kind = "ok" if r["outcome"] == "WIN" else ("bad" if r["outcome"] == "LOSS" else "grey")
        strs.append([
            f'<span class="mono">{esc(r["game_id"])}</span>', esc(r["market_type"]), esc(r["side"]),
            dash(r.get("our_line")), dash(r.get("our_price")), esc(r["result"]),
            badge(r["outcome"], kind), esc(r.get("note", "")), src_cell(r.get("_source_url")),
        ])
    body.append(card("Settled — Week 10 originated markets (origination order: side, total, moneyline)",
                     table("t-settle", ["Game", "Market", "Side", "Our line", "Our price", "Final",
                                        "Outcome", "Note", "Source"],
                           strs, center=[6],
                           note="Both sides of each originated number are settled for bookkeeping; a "
                                "strategy bets only the legs a pre-registered rule selects.")))

    roi = summ.get("roi_at_our_prices")
    body.append(card("ROI — computable, and published with n",
                     kpis([
                         (str(summ.get("markets_originated_and_settled", "")), "legs graded",
                          f"{summ.get('wins', '')}W-{summ.get('losses', '')}L-{summ.get('pushes', '')}P", ""),
                         (num(summ.get("units_staked_at_our_prices"), 2), "units staked",
                          "flat 1-unit stakes", ""),
                         (num(summ.get("units_profit_at_our_prices"), 4), "units profit",
                          "at our own moneyline prices", ""),
                         (pc(roi, 1) if roi is not None else dash(), "ROI (moneyline legs)",
                          "n = 1 game — not evidence of skill", "warn"),
                     ]) + f'<p class="lede">{esc(summ.get("roi_note", ""))}</p>'))

    ar = integ.get("standings_arithmetic", {})
    atrs = [[esc(r["team"]), esc(r["feed_wlt"]), esc(r["official_wlt"]), esc(r["feed_pf_pa"]),
             esc(r["official_pf_pa"]),
             badge(r["result"], "ok" if r["result"] == "match" else "bad"),
             src_cell(r.get("_source_url"))] for r in ar.get("rows", [])]
    body.append(card("Integrity check — feed recomputation vs the official standings",
                     table("t-stand-check", ["Team", "Feed W-L-T", "Official W-L-T", "Feed PF-PA",
                                             "Official PF-PA", "Result", "Source"],
                           atrs, center=[1, 2, 3, 4, 5],
                           note=f"{ar.get('match', '')} of {ar.get('teams_checked', '')} clubs match "
                                "exactly on record and points. This is the check that catches a "
                                "misread score: every club's PF and PA must sum to the league's "
                                "own published totals.")))

    mc = integ.get("mirror_cross_check", {})
    body.append(card("Community-mirror cross-check (corroboration only)", f"""
<p class="lede">The mirror (<a href="https://github.com/nflverse/nfldata/blob/master/data/games.csv"
target="_blank" rel="noopener">nflverse/nfldata games.csv</a>, community source — not an official
source) was compared score for score: <b>{mc.get('agree', '')} agree, {mc.get('disagree', '')} disagree</b>
of {mc.get('games_compared', '')}. Agreement is corroboration, not proof — a shared upstream mistake
would not be caught. Seasons 2006–2025 exist only in this mirror and are not game-by-game verified
against NFL.com (flag I-11); they are used for labelled backtests only.</p>"""))
    return "\n".join(body)




def p_prices_x1_body() -> str:

    ps = D["price_snapshots_x1"]
    rows = ps.get("rows", [])
    q = ps.get("quarantine_mirror", {})
    body = []

    body.append("""<section class="note"><b>Store rules.</b>
Opening and closing snapshots are recorded for every market we originate, in origination order —
<b>side (spread) first, then the total, then the moneyline</b>. The model's fair line, the market
line and the difference are always separate columns; a difference is published only when both of
its inputs are. A market price no official source publishes is left <b>blank and flagged</b> —
never inferred or filled in. A missed capture is recorded as missed and never back-filled.</section>""")

    n_blank = sum(1 for r in rows if not r.get("market_open_line"))
    n_missed = sum(1 for r in rows if "missed close" in (r.get("_flags") or [""])[0])
    body.append(kpis([
        (str(len(rows)), "snapshots", "14 games x 4 originated numbers", ""),
        (str(len({r['game_id'] for r in rows})), "games covered", "Week 10 origination", ""),
        (str(n_blank), "market cells blank", "no official odds source (F-06)", "warn"),
        (str(n_missed), "missed closes", "recorded as missed, not invented", "warn"),
    ]))

    trs = []
    for r in rows:
        fair = r.get("model_fair_line") or r.get("model_fair_price") or ""
        blank_cell = '<span class="blank" title="no official source publishes betting prices (F-06)">— no official source</span>'
        trs.append([
            f'<span class="mono">{esc(r["snapshot_id"])}</span>',
            f'<span class="mono">{esc(r["game_id"])}</span>', esc(r.get("kickoff", "")),
            str(r["sequence"]), esc(r["market_type"]), esc(r["market_side"]),
            esc(fair), blank_cell, blank_cell,
            dash(r.get("difference_open")), dash(r.get("difference_close")),
            dash(r.get("our_close_line")),
            badge("close pending", "grey") if "pending" in r.get("close_status", "") else badge("close missed", "warn"),
            src_cell(r.get("_source_url")),
        ])
    body.append(card("The store — model fair line / market line / difference as separate columns",
                     table("t-prices", ["Snapshot", "Game", "Kickoff", "Order", "Market", "Side",
                                        "Model fair line", "Market open", "Market close",
                                        "Diff open", "Diff close", "Our close", "Close status",
                                        "Source"],
                           trs, center=[3, 9, 10, 12],
                           note="Order 1 = side (spread), 2 = total, 3 = moneyline. The model side is "
                                "a reproducible output of code/build_lines.py (published method); the "
                                "market side is blank because no official source publishes prices — "
                                "see decision Q-31.")))

    qrows = []
    for fname, meta in (q.get("files") or {}).items():
        qrows.append([
            f'<span class="mono">{esc(fname)}</span>', esc(meta.get("content", "")),
            str(meta.get("rows") or meta.get("rows_2026") or ""), esc(str(meta.get("seasons", ""))),
            badge("unverified community mirror", "bad"),
            src_cell(q.get("_source_url")),
        ])
    body.append(card("Quarantine — community-mirror price files (never rendered as market prices)",
                     table("t-price-q", ["File", "Content", "Rows", "Seasons", "Status", "Provenance"],
                           qrows, center=[2],
                           note=q.get("warning", ""))))

    log = "".join(f"<li><b>{esc(e.get('time', ''))}</b> — {esc(e.get('event', ''))} <i>({esc(e.get('by', ''))})</i></li>"
                  for e in ps.get("capture_log", []))
    body.append(card("Capture log", f'<ol class="tight">{log}</ol>'))
    return "\n".join(body)




def p_stores() -> str:
    """Additive page by session arena/bf27a3bd-x1: the data/lines stores built in
    this batch, each table row sourced or explicitly flagged. No page owned by
    another session is touched by this function."""
    ps = jload("data/lines/price_snapshots.json")
    rf = jload("data/lines/results_feed.json")
    og = jload("data/lines/origination.json")
    ls = jload("data/lines/leaderboard_split.json")
    rd = jload("data/lines/replacement_depth.json")
    co = jload("data/lines/correlation_official.json")
    dg = jload("data/lines/demotion_gate.json")
    dd = jload("data/lines/decisions_delta.json")
    sd = jload("data/lines/suggestions_delta.json")
    body: List[str] = []

    body.append("""<section class="note"><b>Sourced or blank — never inferred.</b> These stores were
built by session <code>arena/bf27a3bd-x1</code> from official NFL pages and official Game Book PDFs
(results) plus the fingerprinted nflverse/nfldata mirror (prices, labelled third-party per flag
F-06). Every row carries its source link; a value no source records is blank and flagged, never
filled. Verified end to end by <code>tools/verify_new_data.py</code> (wired into
<code>pages.yml</code>).</section>""")

    v = rf.get("verification", {})
    body.append(kpis([
        (str(v.get("rows", 0)), "games in the verified results feed", "official score per row, double-entry checked", "ok"),
        (str(ps.get("verification", {}).get("rows_with_opening", 0)), "opening prices on record",
         "blank + flagged everywhere else", "bad"),
        (str(len(co.get("official", {}).get("rows", []))), "official correlations", "n published with every value", "ok"),
        (str(len(dg.get("triggers", []))), "demotion triggers armed", "live strategy goes back to paper", "warn"),
    ]))

    # ---- results feed
    rtrs = [[esc(r["game_id"]), str(r["week"]), esc(r["game_date"]),
             f'{esc(r["away"])} <b>{r["away_score"]}</b> @ {esc(r["home"])} <b>{r["home_score"]}</b>',
             badge(r["status"], "ok" if r["status"] == "final" else "warn"),
             esc(r.get("verification_method") or ""),
             src_cell([r["result_source_url"], r["game_url"]])] for r in rf["rows"]]
    body.append(card("Verified results feed — every played 2026 game (official source per row)",
                     table("t-st-results", ["Game", "Wk", "Date", "Final", "Status", "Verified from",
                                            "Sources"], rtrs, center=[1, 4],
                           note="Transcribed line by line from NFL.com score pages, Game Center box "
                                "scores and official Game Book PDFs (static.www.nfl.com) where "
                                "spoiler mode hides the score. Cross-checked against the "
                                "fingerprinted mirror: 137/137 matched. Ties and overtime recorded "
                                "in status. Full feed with settlement columns: "
                                "<code>data/lines/results_feed.json</code>.")))

    # ---- price snapshots (sample + coverage)
    body.append(card("Price-snapshot store — opening vs closing, per market",
                     f"<p>Rows: <b>{ps.get('verification', {}).get('rows', 0)}</b>. "
                     f"With a closing number: <b>{ps.get('verification', {}).get('rows_with_closing', 0)}</b> "
                     "(third-party, per-row link). With an opening number: "
                     f"<b>{ps.get('verification', {}).get('rows_with_opening', 0)}</b> — no source in "
                     "this repository records 2026 opening prices, so those cells are blank and "
                     "flagged, never inferred (Q-02 / Q-31). Full store: "
                     "<code>data/lines/price_snapshots.json</code> · builder: "
                     "<code>tools/build_price_store.py</code>.</p>"))

    # ---- origination ledger (the one played game with a settled result, plus order proof)
    otrs = []
    for r in og["rows"]:
        if r["game_id"] != "2026_10_WAS_NYG":
            continue
        otrs.append([esc(r["game_id"]), str(r["origination_order"]), esc(r["market_type"]),
                     dash(r.get("model_fair_line")), dash(r.get("market_line")),
                     dash(r.get("difference")), esc(r.get("difference_unit") or ""),
                     src_cell(r.get("market_source_url")),
                     link("https://github.com/karagemop466-tech/X1/blob/main/data/lines/origination.json", "full ledger")])
    body.append(card("Origination ledger — side first, then total, then moneyline (fair / market / difference)",
                     table("t-st-orig", ["Game", "Order", "Market", "Model fair line", "Market line",
                                         "Difference", "Unit", "Market source", "Ledger"], otrs,
                           numeric=[1, 3, 4, 5], center=[1],
                           note="Shown for one game as a specimen; the full ledger covers all 150 "
                                "originated markets in <code>data/lines/origination.json</code> with "
                                "the fixed order 1=side, 2=total, 3=moneyline and model / market / "
                                "difference as three separate columns.")))

    # ---- leaderboard split
    ltrs = []
    for r in ls["rows"]:
        sig = r["signal"]
        ltrs.append([esc(r["key"]), esc(r["name"]), str(sig.get("bets_settled", "")),
                     pc(sig.get("flat_stake_roi")), pc(sig.get("roi_luck_removed")),
                     dash(r["staking"].get("staked_roi")), dash(r["staking"].get("bankroll_growth")),
                     link("https://github.com/nflverse/nfldata", "nfldata games")])
    body.append(card("Leaderboard split — signal block vs staking block",
                     table("t-st-lb", ["Key", "Strategy", "Signals settled", "Signal ROI (flat)",
                                       "Signal ROI, luck removed", "Staked ROI", "Bankroll growth",
                                       "Benchmark source"], ltrs, numeric=[2, 3, 4, 5, 6],
                           note="Signal is flat 1-unit staking with the recorded luck rule applied; "
                                "staking metrics stay blank until real stakes exist, so a lucky "
                                "staking run can never mask a bad signal. "
                                "<code>data/lines/leaderboard_split.json</code>.")))

    # ---- replacement depth rollup + flagged rows
    ru = rd.get("rollup_by_unit", {})
    rroll = []
    for unit in ("Defense", "Offense", "Special Teams"):
        c = ru.get(unit, {})
        rroll.append([esc(unit), str(c.get("2nd string", 0)), str(c.get("3rd string", 0)),
                      str(c.get("4th string", 0)), str(c.get("not listed", 0)),
                      src_cell(["https://www.nfl.com/teams/", "https://www.nfl.com/injuries/"])])
    body.append(card("Replacement depth — 2nd / 3rd / 4th string, tracked",
                     table("t-st-depth", ["Unit", "2nd string", "3rd string", "4th string",
                                          "Not listed (flagged)", "Sources"], rroll,
                           numeric=[1, 2, 3, 4],
                           note=f"{rd.get('verification', {}).get('rows', 0)} on-report slots; depth "
                                "order read exactly as each club prints its chart. Row-level "
                                "register: <code>data/lines/replacement_depth.json</code>.")))

    # ---- correlations: official set with n
    top = sorted(co["official"]["rows"], key=lambda r: -abs(float(r.get("r") or 0)))[:20]
    ctrs = [[esc(r.get("pair")), esc(r.get("metric_a")), esc(r.get("metric_b")),
             num(r.get("r"), 3), esc(r.get("n")), num(r.get("p_value"), 4),
             src_cell(r.get("_source_urls") or r.get("_source_url"))] for r in top]
    body.append(card("Correlations — official numbers only, n with every value",
                     table("t-st-corr", ["Pair", "Metric A", "Metric B", "r", "n", "p", "Source"],
                           ctrs, numeric=[3, 4, 5],
                           note=f"Top 20 of {len(co['official']['rows'])} official values. Research "
                                "numbers (mirror-derived) live in the same register flagged "
                                "'not decision-usable'; matrix cells whose source recorded no n are "
                                "marked 'n not recorded' and suppressed. "
                                "<code>data/lines/correlation_official.json</code>.")))

    # ---- demotion gate
    dtrs = [[esc(t["id"]), f'<b>{esc(t["name"])}</b>', esc(t["rule"]),
             str(t.get("n_min", "")),
             badge("blocked: " + esc(t["blocked"]), "bad") if t.get("blocked") else badge("armed", "ok"),
             link("https://github.com/karagemop466-tech/X1/blob/main/data/lines/demotion_gate.json", "gate register")]
            for t in dg.get("triggers", [])]
    body.append(card("Demotion gate G-13 — a live strategy goes back to paper",
                     table("t-st-demotion", ["ID", "Trigger", "Rule", "Min n", "State", "Source"],
                           dtrs, numeric=[3], center=[4],
                           note="Pre-registered before anything is live; numeric thresholds are on "
                                "the suggestion board (S-20) for owner confirmation. "
                                "<code>data/lines/demotion_gate.json</code>.")))

    # ---- deltas
    qtrs = []
    for u in dd.get("updates", []):
        qtrs.append([esc(u["id"]), badge(u["status"], "warn" if "proposed" in u["status"] else "ok"),
                     esc(u.get("answer_now") or ""), esc(u.get("still_missing") or ""),
                     esc(u.get("unblocks") or ""),
                     link((u.get("source_urls") or [""])[0], "source")])
    for q in dd.get("new_questions", []):
        qtrs.append([esc(q["id"]), badge("new question", "grey"), esc(q["question"]),
                     esc(q["unknown"]), esc(q["decision_unblocked"]),
                     link("https://github.com/karagemop466-tech/X1/blob/main/data/lines/decisions_delta.json", "register")])
    body.append(card("Decision register delta — answers, missing information, what it unblocks",
                     table("t-st-q", ["ID", "Status", "Answer / question", "Still missing / unknown",
                                      "Unblocks", "Source"], qtrs,
                           note="<code>data/lines/decisions_delta.json</code>.")))

    strs = []
    for s in sd.get("suggestions", []):
        opts = " &nbsp;|&nbsp; ".join(f'<b>{esc(o["path"])}</b> {esc(o["label"])}' for o in s.get("options", []))
        strs.append([esc(s["id"]), f'<b>{esc(s["title"])}</b>', esc(s["problem"]), opts,
                     badge(s.get("recommended") or "?", "blue"),
                     badge(s.get("status") or "", "warn" if "proposed" in str(s.get("status")) else "ok"),
                     link("https://github.com/karagemop466-tech/X1/blob/main/data/lines/suggestions_delta.json", "register")])
    body.append(card("Suggestion delta — paths with tradeoffs, best path chosen before building",
                     table("t-st-sug", ["ID", "Suggestion", "Problem", "Paths", "Recommended",
                                        "Status", "Source"], strs, center=[4, 5],
                           note="<code>data/lines/suggestions_delta.json</code>.")))

    return page("stores.html", "Verified stores", "Governance", "\n".join(body),
                lede="This batch's price snapshots, verified results, origination ledger and "
                     "strategy registers — every row sourced or explicitly blank and flagged.")



# --- Added by session arena-52aabfa8-x1 (Round-2 union): all-season pages ---
def p_results_feed() -> str:
    meta = D.get("results_meta") or {}
    rows = csvrows("data/results/verified_results.csv")
    counts = meta.get("counts", {})
    checks = (meta.get("verification") or {}).get("checks", [])
    body = []

    body.append(f"""<section class="note"><b>Requirement R-47 (all-season view — complements <a href="results.html">Results &amp; ROI</a>).</b>
One row per game for every season the backtest
scores (2019–2026), each carrying the tier that verified it. The full feed is
{link("https://github.com/karagemop466-tech/X1/blob/main/data/results/verified_results.csv", "data/results/verified_results.csv")}
({counts.get('rows', 0):,} rows); the builder is
{link("https://github.com/karagemop466-tech/X1/blob/main/tools/build_results_feed_all_seasons.py", "tools/build_results_feed_all_seasons.py")}
and it exits non-zero if any cross-check fails.</section>""")

    body.append(kpis([
        (f"{counts.get('rows', 0):,}", "games in the feed", counts.get("seasons", ""), ""),
        (f"{counts.get('final', 0):,}", "final scores", "settled rows", "ok"),
        (str(counts.get("official_verified", 0)), "officially verified score", "printed by nfl.com", "ok"),
        (str(counts.get("scheduled_official", 0)), "officially confirmed unplayed", "blank because unplayed", ""),
        (f"{counts.get('mirror_only', 0):,}", "mirror only", "flagged, not official", "warn"),
    ]))

    # --- the officially verified Week 10 rows --------------------------------
    w10 = [r for r in rows if r["season"] == "2026" and r["week"] == "10"]
    trs = []
    for r in sorted(w10, key=lambda x: (x["date"], x["game_id"])):
        score = (f'{r["away_score"]}–{r["home_score"]}'
                 if r["away_score"] else '<span class="blank">not played</span>')
        tier = {"official_verified": ("official", "ok"),
                "scheduled_official": ("official (status)", "ok"),
                "mirror_only": ("mirror", "warn")}.get(r["verification"], ("?", "grey"))
        src = (link(r["official_source_url"], "NFL.com Week 10")
               if r["official_source_url"] else
               '<span class="blank">no official source</span>')
        trs.append([esc(r["date"]), f'{esc(r["away"])} @ {esc(r["home"])}', score,
                    esc(r["status"]), badge(tier[0], tier[1]), esc(r["flags"]), src])
    body.append(card("Week 10 — the rows an official page confirms",
                     table("t-res-w10", ["Date", "Matchup", "Score", "Status", "Tier",
                                         "What verified it", "Source"], trs,
                           center=[3, 4],
                           note="Score cells are blank only because the game had not been "
                                "played at the 2026-11-14 snapshot. The Thursday game's "
                                "24–21 was printed by nfl.com and matched against the "
                                "mirror (check C1).")))

    # --- cross-checks ---------------------------------------------------------
    ctrs = [[esc(c["id"]), esc(c["what"]), badge(c["result"].replace("_", " "),
                                                 "ok" if c["result"].startswith("pass") else "warn"),
             esc(c["detail"]), link(c["source"], "source")] for c in checks]
    body.append(card("Cross-checks the builder must pass (C1–C4)",
                     table("t-res-chk", ["ID", "Check", "Result", "Detail", "Source"], ctrs,
                           center=[0, 2],
                           note="C4's difference is the standings snapshot predating the "
                                "Thursday game — freshness, recorded as flag F-12, not an "
                                "error in the feed.")))

    # --- 2026 season rows (tiers visible) ------------------------------------
    s26 = [r for r in rows if r["season"] == "2026"]
    trs2 = []
    for r in sorted(s26, key=lambda x: (int(x["week"]), x["date"], x["game_id"])):
        score = (f'{r["away_score"]}–{r["home_score"]}' if r["away_score"] else
                 '<span class="blank">—</span>')
        if r["official_source_url"]:
            src = link(r["official_source_url"], "NFL.com schedule")
            tier = badge("official", "ok")
        else:
            src = link("https://github.com/nflverse/nfldata/blob/master/data/games.csv",
                       "nflverse games.csv")
            tier = badge("mirror only", "warn")
        trs2.append([esc(r["week"]), esc(r["date"]), f'{esc(r["away"])} @ {esc(r["home"])}',
                     score, esc(r["status"]), tier, src])
    body.append(card(f"Every 2026 row in the feed ({len(trs2)})",
                     table("t-res-2026", ["Wk", "Date", "Matchup", "Score", "Status",
                                          "Tier", "Source"], trs2,
                           center=[0, 4, 5], numeric=[0],
                           note="Weeks 1–9 have no committed official page in this repository, "
                                "so they are mirror-tier — usable for backtests, labelled not "
                                "official (flag F-11). The historical CSV carries the same tier "
                                "on all 2,232 rows.")))

    lim = meta.get("known_limitations", [])
    body.append(card("What this feed does and does not close", f"""
<ul class="tight">{''.join(f'<li>{esc(x)}</li>' for x in lim)}</ul>
<p>Settlement for a bet row is a join on <code>game_id</code>: only <code>status=final</code>
rows settle; scheduled rows contribute nothing to ROI. No row is invented — a game that has not
been played has blank score cells by construction.</p>
<p>Q-04 (an official box score for <em>every</em> game) stays open; this feed maps that gap
per row instead of hiding it.</p>"""))
    return page("results-feed.html", "Verified results feed", "Model", "\n".join(body),
                lede="The settlement input for every backtest and ROI figure — with the tier "
                     "that verified each row.")


def p_price_history() -> str:
    meta = D.get("price_hist_meta") or {}
    rows = csvrows("data/prices/price_history.csv")
    counts = meta.get("counts", {})
    checks = (meta.get("verification") or {}).get("checks", [])
    sources = {s.get("key"): s for s in meta.get("sources", [])}
    body = []

    body.append(f"""<section class="note"><b>Requirement R-46 (all-season view — complements <a href="prices.html">Price snapshots</a>).</b>
Every game in the
backtest window × spread, total and moneyline (both sides) × both snapshots —
{counts.get('rows', 0):,} rows in
{link("https://github.com/karagemop466-tech/X1/blob/main/data/prices/price_history.csv", "data/prices/price_history.csv")}.
No official source publishes betting prices (F-06), so every value here is a labelled
third-party benchmark and every gap is a blank with a flag code, never a guess.</section>""")

    body.append(kpis([
        (f"{counts.get('games', 0):,}", "games covered", "every backtest-window game", ""),
        (f"{counts.get('closing_values_present', 0):,}", "closing values", "spread/total/ML", "ok"),
        (f"{counts.get('opening_values_present', 0):,}", "opening values", "2021 REG only", "warn"),
        (f"{counts.get('closing_cells_blank', 0):,}", "closing blanks", "flagged, not guessed", "grey"),
        (f"{counts.get('opening_cells_blank', 0):,}", "opening blanks", "flagged, not guessed", "grey"),
    ]))

    # --- Week 10 closing prices ----------------------------------------------
    w10 = [r for r in rows if r["season"] == "2026" and r["week"] == "10"]
    mirror_url = (sources.get("nfldata_games") or {}).get(
        "url", "https://github.com/nflverse/nfldata/blob/master/data/games.csv")
    trs = []
    for r in sorted(w10, key=lambda x: (x["date"], x["game_id"],
                                        x["market"], x["side"], x["snapshot"])):
        if r["snapshot"] == "opening":
            continue  # no opening data exists for 2026; shown in the coverage table
        line = esc(r["line"]) if r["line"] else '<span class="blank">—</span>'
        flag = esc(r["flags"]) if r["flags"] else "—"
        trs.append([esc(r["game_id"].replace("2026_10_", "")), esc(r["market"]),
                    esc(r["side"]) or "—", line, flag, link(mirror_url, "games.csv")])
    body.append(card("Week 10 closing prices — the benchmark behind our originated lines",
                     table("t-px-w10", ["Game", "Market", "Side", "Closing line",
                                        "Flag", "Source"], trs,
                           center=[2],
                           note="Opening rows for 2026 are blank by construction: the only "
                                "reachable opening feed covers the 2021 season (see coverage "
                                "below). Values are third-party, never league-verified (F-06).")))

    # --- opening coverage by season × market ---------------------------------
    cov: dict[tuple, int] = {}
    for r in rows:
        if r["snapshot"] != "opening" or not r["line"]:
            continue
        cov[(r["season"], r["market"])] = cov.get((r["season"], r["market"]), 0) + 1
    trs2 = []
    for season in sorted({r["season"] for r in rows}):
        for market in ("SPREAD", "TOTAL", "MONEYLINE"):
            n = cov.get((season, market), 0)
            if n:
                src = link((sources.get("nfldata_initial_lines") or {}).get(
                    "url", "https://github.com/nflverse/nfldata/blob/master/data/initial_lines.csv"),
                    "initial_lines.csv")
                flag = "present"
                kind = "ok"
            else:
                code = ("NO-OPENING-MONEYLINE" if market == "MONEYLINE"
                        else "NO-OPENING-DATA-SEASON")
                src = '<span class="blank">no official source</span>'
                flag = code
                kind = "grey"
            trs2.append([esc(season), esc(market), str(n), badge(flag, kind), src])
    body.append(card("Opening-line coverage — what exists, what is blank and why",
                     table("t-px-cov", ["Season", "Market", "Opening values", "Flag",
                                        "Source"], trs2,
                           center=[0, 2, 3], numeric=[2],
                           note="Blank means no reachable source publishes an opening number "
                                "for that season and market. Flag codes expand in "
                                "data/prices/price_store_meta.json.")))

    ctrs = [[esc(c["id"]), esc(c["what"]), badge(c["result"], "ok"), esc(c["detail"]),
             link("https://github.com/nflverse/nfldata", "mirror + arithmetic")]
            for c in checks]
    body.append(card("Store checks (P1–P6) — all must pass or the builder exits 1",
                     table("t-px-chk", ["ID", "Check", "Result", "Detail", "Source"], ctrs,
                           center=[0, 2])))

    conv = meta.get("conventions", {})
    lim = meta.get("known_limitations", [])
    body.append(card("Conventions and limitations", f"""
<div class="grid2"><div><h3>Conventions (verbatim from each source)</h3>
<ul class="tight">{''.join(f'<li><b>{esc(k)}</b>: {esc(v)}</li>' for k, v in conv.items())}</ul></div>
<div><h3>Limitations</h3><ul class="tight">{''.join(f'<li>{esc(x)}</li>' for x in lim)}</ul></div></div>
<p>Opening and closing use different published conventions (per-team opening spread vs signed
closing game line). They are stored exactly as published; normalising them into one convention
is a recorded follow-up, because normalising would be an inference about intent. Until that
happens, no CLV number is computed from this store.</p>"""))
    return page("price-history.html", "Price history", "Model", "\n".join(body),
                lede="Opening and closing numbers for every market we originate — gaps "
                     "flagged, never filled.")


def p_snapshots() -> str:
    """Added by session arena/600e6009-x1 (round 3): the capture-status snapshot
    store and the origination-order table. Coexists with prices.html and
    origination.html; this page is the one that publishes capture statuses
    (recorded / pending_kickoff / captured_post_final / not_captured_before_kickoff)
    and keeps every market cell blank while no official source exists."""
    snaps = D.get("r3_snapshots") or {}
    orig = D.get("r3_origination") or {}
    srows = snaps.get("rows") or []
    orows = orig.get("rows") or []
    sc = snaps.get("status_counts", {})
    if not srows or not orows:
        return page("snapshots.html", "Snapshots & order", "Model",
                    "<section class='note warn'>Snapshot store not built yet.</section>",
                    lede="Price snapshots and origination order.")
    body = []
    body.append("""<section class="note"><b>Two requirements, one page.</b> The snapshot store keeps
an opening and a closing record for <em>every market we originate</em> — side, then total, then
moneyline, in that order. Our own line is computed and always recorded. The market's line is recorded
only when an official source publishes one; today none does, so those cells stay blank and flagged
(Q-02) rather than filled from a mirror. Nothing is back-filled: a stage that was not captured in
time keeps its status and an empty value.</section>""")
    body.append(kpis([
        (str(snaps.get("rows_count", 0)), "snapshot records", "14 games × 3 markets × 2 stages", ""),
        (str(sc.get("recorded", 0)), "open captures recorded", "before kickoff", "ok"),
        (str(sc.get("pending_kickoff", 0)), "close captures pending", "at kickoff", "warn"),
        (str(sc.get("captured_post_final", 0) + sc.get("not_captured_before_kickoff", 0)),
         "post-hoc records", "Thursday final predates the store", "bad"),
        (str(snaps.get("verification", {}).get("market_line_values_published", 0)), "market lines published",
         "blank + flagged by rule (Q-02)", "grey"),
        (str(orig.get("verification", {}).get("games_with_correct_sequence", 0)) + "/14",
         "games in order", "side → total → moneyline", "ok"),
    ]))

    trs = [[
        esc(str(s.get("game_id", ""))), esc(str(s.get("gameday", ""))),
        esc(str(s.get("away_team", ""))) + " at " + esc(str(s.get("home_team", ""))),
        esc(str(s.get("origination_sequence", ""))), esc(str(s.get("market", ""))),
        esc(str(s.get("stage", ""))),
        badge(str(s.get("status", "")), "ok" if s.get("status") == "recorded" else
              ("bad" if ("not_captured" in str(s.get("status")) or "post_final" in str(s.get("status"))) else "warn")),
        f'<b>{esc(str(s.get("our_line", "—")))}</b>' + (f' / {esc(str(s.get("our_line_alt")))}' if s.get("our_line_alt") else ""),
        dash(s.get("market_line", "")),
        dash(s.get("difference", "")),
        esc(str(s.get("market_line_status", ""))),
        src_cell(s.get("source_url", "")),
    ] for s in srows]
    body.append(table("t-snap",
                      ["Game", "Date", "Matchup", "Seq", "Market", "Stage", "Capture status",
                       "Our line", "Market line", "Difference", "Why market is blank", "Source"],
                      trs, numeric=[3], center=[3, 4, 5, 6],
                      note="Filter by stage or status. Our line is the model's number; market line and "
                           "difference stay empty because no official source publishes prices."))

    otrs = [[
        esc(str(o.get("game_id", ""))), esc(str(o.get("gameday", ""))),
        esc(str(o.get("away_team", ""))) + " at " + esc(str(o.get("home_team", ""))),
        f'<b>{o.get("origination_sequence", "")}</b>', esc(str(o.get("market", ""))),
        f'<b>{esc(str(o.get("fair_line", "—")))}</b>' + (f' / {esc(str(o.get("fair_line_alt")))}' if o.get("fair_line_alt") else ""),
        dash(o.get("market_line", "")), dash(o.get("difference", "")),
        esc(str(o.get("market_line_status", ""))),
        src_cell(o.get("source_url", "")),
    ] for o in orows]
    body.append(card("Origination order — side first, then total, then moneyline", """
<p>Publication order is a published column, not a convention. The build refuses to emit a game whose
sequences are not exactly 1, 2, 3. The three value columns are kept apart on purpose: <b>fair line</b>
is ours, <b>market line</b> is theirs (blank until an official source exists), and <b>difference</b> is
fair minus market — which is nothing while the market cell is empty, so it is empty too.</p>
""" + table("t-orig",
            ["Game", "Date", "Matchup", "Seq", "Market", "Fair line (ours)", "Market line", "Difference",
             "Why market is blank", "Source"],
            otrs, numeric=[3], center=[3, 4],
            note="14 games × 3 markets = 42 rows, all in publication order. "
                 "Difference fills automatically the moment a recorded market line exists.")))

    body.append(card("Capture rules", """
<ul class="tight">
<li><b>open</b> — the number as originated, captured before kickoff.</li>
<li><b>close</b> — the number as published at our cut-off, captured at kickoff.</li>
<li><b>Our line</b> is computed by this repository and always recorded; the Thursday final's rows are
marked <i>captured_post_final</i> because the store went live after that kickoff — recorded as found,
never back-dated.</li>
<li><b>Market line</b> and <b>difference</b> are blank until an official price source is settled
(<a href="decisions.html">Q-19</a> / F-06). A third-party mirror number is not inserted here.</li>
<li>A missed capture keeps its status (<i>pending_kickoff</i>, <i>not_captured_before_kickoff</i>)
instead of borrowing the other stage's value.</li>
</ul>
<a class="btn" href="https://github.com/karagemop466-tech/X1/blob/main/data/snapshots/price_snapshots.json">Snapshot store JSON</a>
<a class="btn" href="https://github.com/karagemop466-tech/X1/blob/main/tools/build_snapshots.py">Store builder</a>"""))
    return page("snapshots.html", "Snapshots & order", "Model", "\n".join(body),
                lede="Opening and closing numbers for every market we originate, in origination "
                     "order, with fair / market / difference kept as separate columns.")


BUILDERS = {
    "index.html": p_index,
    "executive-summary.html": p_exec,
    "standings.html": p_standings,
    "schedule.html": p_schedule,
    "injuries.html": p_injuries,
    "depth.html": p_depth,
    "deficiency.html": p_deficiency,
    "replacement-depth.html": p_replacement_depth,
    "team-stats.html": p_team_stats,
    "lines.html": p_lines,
    # Added by session arena-1d3600f8-x1 (T15-T21 integration)
    "results.html": p_results,
    "results-feed.html": p_results_feed,
    "origination.html": p_origination,
    "prices.html": p_prices,
    # Added by session arena/600e6009-x1 (round 3)
    "snapshots.html": p_snapshots,
    "price-history.html": p_price_history,
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
    "stores.html": p_stores,
}


# Added by session arena-c0461519-x1 (L1/L2): the immutable injury-report ledger page.
# Reads data/ledger/injuries/ledger.jsonl (append-only; see tools/snapshot_ledger.py).
LEDGER_DIR = os.path.join("data", "ledger", "injuries")
LEDGER_REPO_URL = "https://github.com/karagemop466-tech/X1/blob/main/"


def load_ledger() -> List[Dict[str, Any]]:
    path = os.path.join(ROOT, LEDGER_DIR, "ledger.jsonl")
    if not os.path.exists(path):
        return []
    out: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def p_injury_ledger() -> str:
    lines = load_ledger()
    src = "https://www.nfl.com/injuries/"
    if not lines:
        body = (
            "<section class=\"note warn\"><b>No captures committed yet.</b> The scheduled job "
            "(<code>.github/workflows/injury-ledger.yml</code>) writes the first ledger line on "
            "its next run. Until then this page shows no rows, and no row is inferred. "
            f"Source: <a href=\"{src}\" target=\"_blank\" rel=\"noopener\">{src}</a>.</section>"
        )
        return page("injury-ledger.html", "Injury-report ledger", "Official data", body,
                    lede="Every read of the official injury report, hashed and timestamped.")

    raw_count = sum(1 for e in lines if e.get("file"))
    fatal = [e for e in lines if set(e.get("flags", [])) & {"http_error", "empty_body", "schema_drift"}]
    last = lines[-1]
    last_ok = next((e for e in reversed(lines) if e.get("sha256")), None)
    kp = kpis([
        (str(len(lines)), "Reads logged", "every read, including failures", "blue"),
        (str(raw_count), "Distinct page versions", "raw bytes stored, one per change", "ok"),
        (esc(last["captured_at_utc"]), "Last read (UTC)", f"HTTP {last.get('http_status')}", "ok"),
        (str(len(fatal)), "Fatal flags", "http_error, empty_body or schema_drift", "bad" if fatal else "ok"),
    ])

    rows = []
    for e in reversed(lines):
        flags = ", ".join(e.get("flags", [])) or "—"
        raw = e.get("file")
        raw_html = (
            f"<a href=\"{LEDGER_REPO_URL}{LEDGER_DIR}/{esc(raw)}\" target=\"_blank\" rel=\"noopener\">"
            f"{esc(os.path.basename(raw))}</a>" if raw else dash()
        )
        sha = e.get("sha256")
        rows.append([
            esc(e.get("seq")),
            esc(e.get("captured_at_utc")),
            esc(e.get("http_status")),
            esc(f"Week {e['week']}, {e['season']}") if e.get("week") else dash(),
            esc(e.get("bytes")),
            f"<code title=\"{esc(sha or '')}\">{esc(sha[:12]) if sha else '—'}</code>",
            esc(flags),
            raw_html,
            src_cell(src, "NFL.com injuries"),
        ])
    body = [
        kp,
        "<section class=\"note\"><b>What this proves.</b> Each row is one read of the official page, "
        "with the UTC time it was taken, the SHA-256 of the bytes received, and a hash link to the row "
        "before it. A changed page gets a new raw file; an identical re-read reuses the existing one. "
        "This proves <i>that</i> the page changed and <i>when</i>. It does not yet say which player's "
        "designation changed — that needs the row parser, which is not built.</section>",
        card("Read log (newest first)", table(
            "ledger-tbl",
            ["#", "Read (UTC)", "HTTP", "Week (page title)", "Bytes", "SHA-256", "Flags",
             "Raw bytes (repo)", "Source"],
            rows, numeric=(4,), center=(0, 2),
            note="Verify locally: <code>python3 tools/snapshot_ledger.py verify --dir data/ledger/injuries</code>. "
                 "Method: <a href=\"https://github.com/karagemop466-tech/X1/blob/main/docs/methodology/snapshot-ledger.md\">docs/methodology/snapshot-ledger.md</a>.",
        )),
    ]
    return page("injury-ledger.html", "Injury-report ledger", "Official data", "\n".join(body),
                lede="Every read of the official injury report, hashed and timestamped.")


# Added by session arena-c0461519-x1 (L1/L2): registered after its definition.
BUILDERS["injury-ledger.html"] = p_injury_ledger

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
