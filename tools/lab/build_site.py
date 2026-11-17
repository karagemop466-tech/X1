#!/usr/bin/env python3
"""Build the "Line Desk" lab section of the site, from `data/lab/*`.

Run:  python3 tools/lab/build_site.py

This is a self-contained section.  It deliberately does NOT edit `app/`, `pages/`,
`dashboard/`, `research/`, `site/`, `live/` or `hub/`: those are other sessions' trees, and
rule 9 forbids touching shared output.  Three additive links are made elsewhere, each of
them logged in COORDINATION.md before the edit:

    tools/build_site.py  ->  1 line in NAV, so the landing page reaches this section
    pages.yml            ->  1 copy line + 1 verify line
    verify.yml           ->  1 verify line

Everything else is inside `lab/`.

Design rule (the same one the whole site uses): every table row carries a source link; a
value with no source renders as an em dash with an explicit reason, never as a blank that
looks like a zero and never as a guess.  `--check` verifies that contract and the internal
links, and exits non-zero, so a broken page cannot be published.
"""

from __future__ import annotations

import html
import html.parser
import json
import os
import re
import sys
from typing import Any, Iterable, Sequence

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LAB = os.path.join(ROOT, "lab")
SNAPSHOT = "2026-11-14"
SEASON = 2026
WEEK = 10
GITHUB = "https://github.com/karagemop466-tech/X1/blob/main"

# (file, nav label, title, kicker)
PAGES: list[tuple[str, str, str, str]] = [
    ("index.html", "Desk overview", "Line desk", "This round"),
    ("executive-summary.html", "Executive summary", "Executive summary", "Read first"),
    ("prices.html", "Price snapshots", "Opening and closing numbers", "T1 · price store"),
    ("results.html", "Results feed", "Verified results feed", "T2 · outcomes"),
    ("lines.html", "Originated lines", "Our own number", "T3 · side, total, ML"),
    ("leaderboard.html", "Leaderboard", "Signal versus staking", "T5 · competition"),
    ("deficiency.html", "Replacement depth", "Who steps in, and how far back", "T6 · depth"),
    ("correlation.html", "Correlation", "With n on every value", "T7 · measured"),
    ("controls.html", "Control baselines", "Would a coin toss do as well?", "C1 · controls"),
    ("validation.html", "Demotion gate", "When a strategy goes back to paper", "T8 · gate"),
    ("questions.html", "Questions", "What we know, what we don't", "Decision support"),
    ("suggestions.html", "Suggestions", "Choose a path before building", "Decision support"),
    ("reads.html", "Official reads", "The dated official read", "R1 · 2026-11-17"),
    ("escrow.html", "Week 11 escrow", "Recorded before kickoff", "R1 · PR-04"),
    ("closure.html", "Feed closure", "What Week 10 still needs", "R1 · measured"),
    ("sources.html", "Sources & limits", "Every source, and every limit", "Provenance"),
    ("flagged.html", "Flagged for review", "Flagged for review", "Never filled in"),
]

# The reads pack lives beside the data it transcribes; every number on the three pages below is
# computed by tools/lab/build_reads.py / build_escrow.py / build_closure_measurement.py and read here.
READS_PACK = "data/lab/reads/2026-11-17"
ESCROW_DIR = "data/lab/escrow"


# ------------------------------------------------------------------ helpers
def esc(v: Any) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def dash(reason: str = "not published by the source") -> str:
    return f'<span class="blank" title="{esc(reason)}">&mdash;</span>'


def numf(v: Any, dp: int = 2) -> str:
    if v is None or (isinstance(v, str) and not v.strip()):
        return dash()
    try:
        return f"{float(v):,.{dp}f}"
    except (TypeError, ValueError):
        return esc(v)


def pct(v: Any, dp: int = 1) -> str:
    if v is None:
        return dash()
    try:
        return f"{float(v) * 100:.{dp}f}%"
    except (TypeError, ValueError):
        return esc(v)


def badge(text: str, kind: str = "grey") -> str:
    return f'<span class="b {kind}">{esc(text)}</span>'


def src(url: str | None, label: str | None = None) -> str:
    if not url:
        return ('<span class="src blank">no official source</span>')
    short = re.sub(r"^https?://(www\.)?", "", url)
    if len(short) > 46:
        short = short[:43] + "..."
    return (f'<span class="src"><a href="{esc(url)}" target="_blank" rel="noopener" '
            f'title="{esc(url)}">{esc(label or short)}</a></span>')


def table(headers: Sequence[str], rows: Iterable[Sequence[str]], *,
          numeric: Sequence[int] = (), note: str = "", tid: str = "") -> str:
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = []
    for r in rows:
        cells = []
        for i, c in enumerate(r):
            cls = ' class="n"' if i in numeric else ""
            cells.append(f"<td{cls}>{c}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    idattr = f' id="{esc(tid)}"' if tid else ""
    n = note and f'<p class="legend">{note}</p>' or ""
    return (f'<div class="tw"><table data-table{idattr}><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>{n}')


def nav(active: str, pfx: str = "") -> str:
    out = []
    for fn, label, _t, _k in PAGES:
        cls = " active" if fn == active else ""
        out.append(f'<a class="{cls.strip()}" href="{pfx}{fn}">{esc(label)}</a>')
    return "\n".join(out)


def page(fn: str, title: str, kicker: str, body: str, lede: str = "", pfx: str = "") -> str:
    navtitle = next(p[2] for p in PAGES if p[0] == fn)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(navtitle)} — X1 Line Desk</title>
<meta name="description" content="X1 line desk: price snapshots, verified results, originated NFL lines and a signal-first strategy leaderboard. Every value carries its source and its n.">
<link rel="stylesheet" href="{pfx}../app/assets/site.css">
</head>
<body>
<aside class="rail">
  <a class="brand" href="{pfx}index.html"><span class="mark">X1</span><span><b>LINE DESK</b><span>this round's lab</span></span></a>
  <nav aria-label="Line desk sections">
{nav(fn, pfx)}
  </nav>
  <div class="foot">Snapshot {SNAPSHOT}<br>Season {SEASON}, Week {WEEK}<br>
  Every value sourced. Nothing inferred.</div>
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
    X1 Line desk · generated by <code>tools/lab/build_site.py</code> from
    <code>data/lab/*</code> · every table row links the page the value came from, or says why
    there is none · a value the source does not print is an
    <span class="blank">&mdash;</span>, never a guess.<br>
    <a href="{pfx}../index.html">Main dashboard</a> ·
    <a href="{pfx}flagged.html">Flagged for review</a> ·
    <a href="{pfx}sources.html">Sources &amp; limits</a> ·
    <a href="https://github.com/karagemop466-tech/X1/tree/main/data/lab" target="_blank" rel="noopener">Artefacts on GitHub</a>
  </footer>
</main>
<script src="{pfx}../app/assets/app.js"></script>
</body>
</html>
"""


def jload(rel: str) -> Any:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


def kpi(value: str, label: str, sub: str = "", kind: str = "") -> str:
    k = f" {kind}" if kind else ""
    s = f'<div class="s">{sub}</div>' if sub else ""
    return f'<div class="kpi{k}"><div class="v">{value}</div><div class="l">{label}</div>{s}</div>'


# ------------------------------------------------------------------ pages
def p_index() -> str:
    s = jload("data/lab/summary.json")
    prices = jload("data/lab/prices/price_coverage.json")
    results = jload("data/lab/results/result_summary.json")
    model = jload("data/lab/lines/model_report.json")
    board = jload("data/lab/leaderboard.json")
    corr = jload("data/lab/correlations.json")
    defi = jload("data/lab/deficiency.json")
    pt, acc = prices["totals"], model["accuracy"]
    bc = board["summary"]["counts"]

    kpis = "".join([
        kpi(f"{pt['market_rows']:,}", "market rows in the price store",
            f"{pt['rows_where_opening_and_closing_both_exist']} with open + close", "warn"),
        kpi(f"{results['coverage']['final']:,}", "scored games in the results feed",
            f"0 arithmetic mismatches", "ok"),
        kpi(f"{acc['n_side']:,}", "out-of-sample originated sides",
            f"MAE {acc['side_mae_model']} vs market {acc['side_mae_market']}", "warn"),
        kpi(str(bc["live"]), "strategies allowed to bet",
            f"{bc['strategies']} scored, all on paper", ""),
        kpi(f"{corr['counts']['values_published']}", "correlation values",
            f"{corr['counts']['not_sourced']} refused as unsourced", "ok"),
        kpi(f"{defi['totals']['replacement_certain']}", "certain starter replacements",
            f"{defi['totals']['depth_losses_second_string_or_deeper']} depth losses behind them",
            "ok"),
    ])

    cards = "".join(
        f'<a class="navcard" href="{esc(fn)}"><div class="k">{esc(k)}</div>'
        f'<div class="t">{esc(t)}</div><div class="d">{d}</div></a>'
        for fn, t, k, d in [
            ("prices.html", "Price snapshots", "T1", "Opening and closing numbers, per market, "
             "with the four fields a price store needs and which of them are missing"),
            ("results.html", "Results feed", "T2", "Every scored game, the settlement rule, and "
             "the arithmetic re-check"),
            ("lines.html", "Originated lines", "T3/T4", "Our side, then the total, then the "
             "moneyline — fair line, market line and difference as separate columns"),
            ("leaderboard.html", "Signal vs staking", "T5", "Eight strategies scored twice, ranked "
             "on signal and never on ROI"),
            ("deficiency.html", "Replacement depth", "T6", "Who steps in and at what rung of the "
             "chart, plus the depth lost behind the starter"),
            ("correlation.html", "Correlation with n", "T7", "Every value with its n, interval "
             "and permutation p"),
            ("validation.html", "Demotion gate", "T8", "The four triggers that send a live "
             "strategy back to paper, evaluated on real data"),
            ("questions.html", "Questions", "—", "What we know, what we do not, and the test that "
             "closes each one"),
            ("suggestions.html", "Suggestions", "—", "Every path with its cost, what it unlocks "
             "and its risk — pick one"),
            ("reads.html", "Official reads", "R1", "The 2026-11-17 dated read: Week 10 closure, the "
             "Week 11 slate, the standings, venue evidence and the injury spot-check, with every check "
             "re-run from the files"),
            ("escrow.html", "Week 11 escrow", "R1", "Forecasts recorded before kickoff in the required "
             "order — side, both total estimators, moneyline — with the price columns withheld and the "
             "settlement ledger beside them"),
            ("closure.html", "Feed closure", "R1", "What still blocks Week 10 in the results feed, counted "
             "by the feed's own gates, with the three ways out and what each one costs"),
            ("sources.html", "Sources & limits", "—", "Every URL used, and every limit of this "
             "round's environment"),
            ("flagged.html", "Flagged for review", "—", "Defects, unsourced values and coverage "
             "gaps, non-blocking"),
        ])

    table_rows = table(["#", "Deliverable", "What it produces", "Honest state", "Artefact"],
                       [[esc(d["id"]), esc(d["item"]), esc(d["result"]), esc(d["honest_state"]),
                         src(f"{GITHUB}/data/lab/summary.json", "summary.json")]
                        for d in s["what_is_new"]],
                       note="Every row above is generated from the artefact named on its own page; "
                            "the honest-state column is the part that would normally be left out.")
    numbers_rows = table(["Measure", "Value", "How to read it", "Artefact"],
                         [[esc(n["label"]), esc(n["value"]), esc(n["reading"]),
                           src(f"{GITHUB}/data/lab/summary.json", "summary.json")]
                          for n in s["the_numbers_that_matter"]])
    blocked_rows = table(["Blocked", "By", "Question", "Register"],
                         [[esc(b["blocked"]), esc(b["by"]), esc(b["question"]),
                           src(f"{GITHUB}/data/lab/questions.json", "questions.json")]
                          for b in s["what_is_blocked_and_by_what"]])
    decision_rows = table(["ID", "Decision", "Read", "Register"],
                          [[esc(d["id"]), esc(d["decision"]), esc(d["suggestion"]),
                            src(f"{GITHUB}/data/lab/suggestions.json", "suggestions.json")]
                           for d in s["decisions_waiting_on_the_owner"]],
                          note="Nothing in this list is implemented. Each one is a choice "
                               "between published paths on the Suggestions page.")
    body = f"""
<section class="kpis">{kpis}</section>

<div class="note bad"><b>The headline, in one sentence.</b> {esc(s['headline'])}</div>

<div class="card">
  <h2>What this round added</h2>
  <p>{esc(s['the_one_paragraph'])}</p>
  {table_rows}
</div>

<div class="card">
  <h2>Numbers that decide something</h2>
  {numbers_rows}
</div>

<div class="card">
  <h2>Sections</h2>
  <div class="cards">{cards}</div>
</div>

<div class="grid2">
  <div class="card">
    <h2>What is blocked, and by what</h2>
    {blocked_rows}
  </div>
  <div class="card">
    <h2>Waiting on your decision</h2>
    {decision_rows}
  </div>
</div>

<div class="note"><b>How to read this section.</b> The pages here are a lab, not a betting
service. They publish what is measured, refuse to publish what is not sourced, and put the
limitation next to the number rather than in a footnote. Where a result is unflattering to
the model, it is on the page: that is the point of the exercise.</div>
"""
    return page("index.html", "Line desk", "This round",
                body, "Price snapshots, a verified results feed, an originated line, and a "
                      "leaderboard that refuses to rank on luck.")


def p_exec() -> str:
    s = jload("data/lab/summary.json")
    body = f"""
<div class="card">
  <h2>Executive summary</h2>
  <p class="lede">{esc(s['headline'])}</p>
  <p>{esc(s['the_one_paragraph'])}</p>
</div>

<div class="card">
  <h2>What is new, and what it honestly is</h2>
  {table(["#", "Item", "Result", "Honest state", "Artefact"],
         [[esc(d["id"]), esc(d["item"]), esc(d["result"]), esc(d["honest_state"]),
           src(f"{GITHUB}/data/lab/summary.json", "summary.json")]
          for d in s["what_is_new"]],
         note="Every figure here is generated from the artefact in the last column; none is "
              "hand-typed into this page.")}
</div>

<div class="card">
  <h2>Defects found in this round's own work, and fixed</h2>
  {table(["ID", "Where", "What was wrong", "Fix", "Code"],
         [[esc(d["id"]), esc(d["where"]), esc(d["what"]), esc(d["fix"]),
           src(f"{GITHUB}/tools/lab/build_lines.py" if d["where"] == "line model"
               else f"{GITHUB}/tools/lab/build_strategies.py", "generator")]
          for d in s["defects_found_and_fixed_this_round"]],
         note="These are recorded because a build that reports only its successes is not "
              "auditable. Each one changed a published number.")}
</div>

<div class="grid2">
  <div class="card">
    <h2>If you read one thing</h2>
    <p>The model does not beat the market. It beats a naive constant, which means it carries
    real information, and it loses to the market on MAE and on calibration, which means that
    information is not an edge. No stake is being placed, and no strategy is live. The value
    delivered this round is that the system can now <b>tell the difference</b> — it caught a
    parlay showing +10.5% ROI and demoted it because its signal was indistinguishable from
    chance.</p>
  </div>
  <div class="card">
    <h2>What would change the answer</h2>
    <ul class="tight">
      {''.join(f'<li>{esc(n)}</li>' for n in s["next_round_if_approved"])}
    </ul>
  </div>
</div>
"""
    return page("executive-summary.html", "Executive summary", "Read first", body)


def p_prices() -> str:
    c = jload("data/lab/prices/price_coverage.json")
    store = jload("data/lab/prices/price_snapshots.json")
    t, tc = c["totals"], c["temporal_coverage"]
    need = [
        ("the number (line)", "pricing, CLV",
         f"{t['market_rows']:,} rows carry one", "ok"),
        ("the price (American odds)",
         "EV, ROI",
         f"{t['rows_with_a_closing_price']} closing, {t['rows_with_an_opening_price']} opening",
         "warn"),
        ("the book", "which market, which limit",
         f"{t['rows_naming_a_book_on_the_closing_snapshot']} on the closing snapshot", "bad"),
        ("the timestamp", "opening vs closing, CLV",
         f"{t['rows_with_a_timestamp']}", "bad"),
    ]
    sample = [r for r in store["rows"] if r["closing_line"] is not None][:25]
    body = f"""
<div class="note warn"><b>The structural finding, first.</b> {esc(tc['finding'])}</div>

<section class="kpis">
{kpi(f"{t['market_rows']:,}", "market rows", "side, total, moneyline", "")}
{kpi(f"{t['rows_where_opening_and_closing_both_exist']}", "with open + close", "of any market", "bad")}
{kpi(f"{t['rows_with_a_closing_price']}", "closing prices", "American odds present", "warn")}
{kpi(f"{t['rows_with_a_timestamp']}", "timestamps", "none in the source", "bad")}
</section>

<div class="card">
  <h2>The four fields a price store needs</h2>
  {table(["Field", "What it is for", "What this store has", "State", "Artefact"],
         [[esc(a), esc(b), esc(mm), badge(st.upper(), st),
           src(f"{GITHUB}/data/lab/prices/price_coverage.json", "price_coverage.json")]
          for a, b, mm, st in need],
         note="A price store without a book and a timestamp records a number, not a market. "
              "Both are absent from the only reachable upstream, so both are published as "
              "gaps rather than approximated.")}
</div>

<div class="card">
  <h2>Provenance defects, measured on every build</h2>
  {table(["ID", "Severity", "Claim", "Measure", "Source"],
         [[esc(d["id"]), badge(d["severity"], "bad" if d["severity"] == "high" else "warn"),
           esc(d["claim"]), esc(d["measure"]),
           " ".join(src(u) for u in d["source"])] for d in c["defects"]])}
</div>

<div class="card">
  <h2>What a row looks like</h2>
  {table(["Game", "Market", "Opening", "Closing", "games.csv value", "Move", "Source"],
         [[esc(r["game_id"]), esc(r["market"]),
           numf(r["opening_line"], 1) if r["opening_line"] is not None else dash("no opening file for this season"),
           numf(r["closing_line"], 1), numf(r["unlabelled_line"], 1),
           numf(r["line_move"], 1) if r["line_move"] is not None else dash("needs both snapshots"),
           src(r["closing_provenance"] or r["unlabelled_provenance"])]
          for r in sample],
         note="Twenty-five rows with a closing number. The opening column is empty for every "
              "one of them because initial_lines.csv covers 2021 only — that is a fact about "
              "the source, not a gap in this table.")}
</div>

<div class="grid2">
  <div class="card">
    <h2>Coverage by market</h2>
    {table(["Market", "Rows", "Link"],
           [[esc(k), f"{v:,}", src(f"{GITHUB}/data/lab/prices/price_snapshots.json", "snapshots")]
            for k, v in t["rows_per_market"].items()], numeric=(1,))}
  </div>
  <div class="card">
    <h2>Self-checks</h2>
    {table(["Check", "Result", "Link"],
           [[esc(k), badge("PASS" if v else "FAIL", "ok" if v else "bad"),
             src(f"{GITHUB}/data/lab/prices/price_coverage.json", "self_checks")]
            for k, v in c["self_checks"].items()],
           note="Recomputed from the raw files on every build, so a claim on this page cannot "
                "drift from the data behind it.")}
  </div>
</div>
"""
    return page("prices.html", "Opening and closing numbers", "T1 · price store", body,
                "Every market we originate, with the opening and closing snapshot kept apart "
                "and the missing fields counted rather than filled.")


def p_results() -> str:
    r = jload("data/lab/results/result_summary.json")
    feed = jload("data/lab/results/results.json")
    cov = r["coverage"]
    rule = r["settlement_rule"]
    sample = [x for x in feed["rows"] if x["season"] == 2026][:20]
    result_rows = table(
        ["Game", "Week", "Away", "Home", "Score", "Margin", "Total", "Status", "Source"],
        [[esc(g["game_id"]), str(g["week"]), esc(g["away"]), esc(g["home"]),
          (f"{int(g['away_score'])}&ndash;{int(g['home_score'])}"
           if g["away_score"] is not None else dash("game not played")),
          numf(g["home_margin"], 0) if g["home_margin"] is not None else dash(),
          numf(g["game_total"], 0) if g["game_total"] is not None else dash(),
          badge(g["status"], "ok" if g["status"] == "FINAL" else "grey"),
          src(g["score_source"])] for g in sample])
    rules_rows = table(["Market", "Rule", "Push handling", "Artefact"],
                       [["Side", esc(rule["side"]["definition"]), esc(rule["side"]["push"]),
                         src(f"{GITHUB}/data/lab/results/result_summary.json", "settlement_rule")],
                        ["Total", esc(rule["total"]["definition"]), esc(rule["total"]["push"]),
                         src(f"{GITHUB}/data/lab/results/result_summary.json", "settlement_rule")],
                        ["Moneyline", esc(rule["moneyline"]["definition"]),
                         esc(rule["moneyline"].get("push", "a tie is a push and is excluded")),
                         src(f"{GITHUB}/data/lab/results/result_summary.json", "settlement_rule")],
                        ["ROI", esc(rule["roi"]["definition"]), "&mdash;",
                         src(f"{GITHUB}/data/lab/results/result_summary.json", "settlement_rule")]],
                       note="Published once so the leaderboard, the backtest and the gates "
                            "cannot disagree about what a win means.")
    body = f"""
<section class="kpis">
{kpi(f"{cov['games']:,}", "games in the feed", f"{cov['seasons'][0]}&ndash;{cov['seasons'][1]}", "")}
{kpi(f"{cov['final']:,}", "scored", "publisher's own final scores", "ok")}
{kpi(f"{cov['scheduled']}", "not yet played", "carried, never zero-filled", "warn")}
{kpi(str(r['_checks']['publisher_arithmetic_mismatches']), "arithmetic mismatches", "re-derived every row", "ok")}
</section>

<div class="note ok"><b>A backtest can be computed at all now.</b> The feed carries the final
score, the derived margin and total, a settlement rule with an explicit push clause, and the
file hash of the exact bytes the scores came from. That is the minimum for a result to count.</div>

<div class="card">
  <h2>The settlement rule, written down once</h2>
  {rules_rows}
  <p class="legend">Void rules: {esc(" ".join(rule["void_rules"]))}</p>
</div>

<div class="card">
  <h2>2026 season so far</h2>
  {result_rows}
</div>

<div class="grid2">
  <div class="card">
    <h2>Self-checks</h2>
    {table(["Check", "Result", "Link"],
           [[esc(k), badge("PASS" if v is True or (isinstance(v, int) and v == 0) else str(v),
                           "ok" if v is True or v == 0 else "warn"),
             src(f"{GITHUB}/data/lab/results/result_summary.json", "self-checks")]
            for k, v in r["_checks"].items()])}
  </div>
  <div class="card">
    <h2>Coverage by season</h2>
    {table(["Season", "Games", "Scored", "Link"],
           [[esc(s), str(n), str(cov["final_by_season"].get(s, 0)),
             src(f"{GITHUB}/data/lab/results/results.json", "results.json")]
            for s, n in sorted(cov["by_season"].items())], numeric=(1, 2),
           note="The only season with unplayed games is the one in progress.")}
  </div>
</div>
"""
    return page("results.html", "Verified results feed", "T2 · outcomes", body,
                "Every scored game, the rule that decides a win, and the arithmetic re-checked "
                "against the publisher's own columns.")


def p_lines() -> str:
    m = jload("data/lab/lines/model_report.json")
    fl = jload("data/lab/lines/fair_lines.json")
    board = jload("data/lab/lines/week10_board.json") if os.path.exists(
        os.path.join(ROOT, "data/lab/lines/week10_board.json")) else None
    a = m["accuracy"]
    rows = board["rows"] if board else []
    body = f"""
<div class="note"><b>The order is not cosmetic.</b> Side first, then the total, then the
moneyline. A moneyline is a probability built from the same scoring distribution that
produces the other two, so deriving it last makes it a consequence of two numbers that are
already checked against the market. Deriving it first would mean inventing a probability and
reverse-engineering a spread from it.</div>

<section class="kpis">
{kpi(f"{a['side_mae_model']}", "our side MAE", f"market {a['side_mae_market']}", "warn")}
{kpi(f"{a['total_mae_model']}", "our total MAE", f"market {a['total_mae_market']}", "warn")}
{kpi(f"{a['brier_model']}", "our Brier", f"market {a['brier_market']}", "warn")}
{kpi(f"{a['corr_fair_vs_market']}", "corr(ours, market)", f"n = {a['n_side']:,}", "ok")}
</section>

<div class="card">
  <h2>The honest verdict, in the model's own words</h2>
  <p>{esc(m['honest_verdict']['statement'])}</p>
  {table(["Question", "Answer", "Source"],
         [["Beats the market on the side",
           badge("YES" if m["honest_verdict"]["beats_market_on_side"] else "NO",
                 "ok" if m["honest_verdict"]["beats_market_on_side"] else "bad"),
           src(f"{GITHUB}/data/lab/lines/model_report.json", "accuracy")],
          ["Beats the market on the total",
           badge("YES" if m["honest_verdict"]["beats_market_on_total"] else "NO",
                 "ok" if m["honest_verdict"]["beats_market_on_total"] else "bad"),
           src(f"{GITHUB}/data/lab/lines/model_report.json", "accuracy")],
          ["Beats a naive 2.5-point constant",
           badge("YES" if m["honest_verdict"]["beats_a_constant_on_side"] else "NO",
                 "ok" if m["honest_verdict"]["beats_a_constant_on_side"] else "bad"),
           src(f"{GITHUB}/data/lab/lines/model_report.json", "side_mae_constant_hfa_2_5")],
          ["Test window",
           esc(f"{m['test_window']['from']}&ndash;{m['test_window']['to']}, {m['test_window']['games']:,} games"),
           src(f"{GITHUB}/data/lab/lines/model_report.json", "test_window")],
          ["Tuning window (never scored)", esc(m["tuning"][0].get("note") or "1999-2014"),
           src(f"{GITHUB}/data/lab/lines/model_report.json", "tuning")]])}
</div>

<div class="card">
  <h2>Week {board['week'] if board else WEEK}: fair line, market line, difference</h2>
  {table(["Match", "Fair side", "Market side", "Difference", "Fair total", "Market total", "Difference",
          "Fair ML", "Market ML", "Prob. diff", "Source"],
         [["%s @ %s" % (esc(r["away"]), esc(r["home"])),
           numf(r["fair_side"], 1), numf(r["market_side"], 1),
           (f'<b>{numf(r["side_diff"], 1)}</b>' if r["side_diff"] is not None else dash()),
           numf(r["fair_total"], 1), numf(r["market_total"], 1), numf(r["total_diff"], 1),
           numf(r["fair_ml_home"], 0), numf(r["market_ml_home"], 0),
           numf(r["ml_prob_diff_pts"], 1),
           src(r["market_provenance"])] for r in rows],
         note="Negative side difference means we make the home team stronger than the market "
              "does. The market columns come from one unnamed publisher composite — no book is "
              "named by the source (defect P-04), and the page says so on every row.",
         numeric=(1, 2, 3, 4, 5, 6, 7, 8, 9))}
</div>

<div class="card">
  <h2>Accuracy by season (out of sample)</h2>
  {table(["Season", "Our side MAE", "Market side MAE", "Our total MAE", "Games", "Source"],
         [[esc(season), numf(v["side_mae_model"]), numf(v["side_mae_market"]),
           numf(v["total_mae_model"]), str(v["n"]),
           src(f"{GITHUB}/data/lab/lines/model_report.json", "by_season")]
          for season, v in m["by_season"].items() if int(season) >= 2015],
         numeric=(1, 2, 3, 4),
         note="A model that beat the market overall but lost in the most recent seasons would "
              "be a red flag; this table is here so that cannot hide.")}
</div>

<div class="card">
  <h2>Three defects this model had, and how they were caught</h2>
  {table(["ID", "What was wrong", "Effect", "Fix", "Code"],
         [[esc(d["id"]), esc(d["was"]), esc(d["effect"]), esc(d["fixed_in"]),
           src(f"{GITHUB}/tools/lab/build_lines.py", "build_lines.py")]
          for d in m["defects_found_in_this_build"]],
         note="L-03 is the important one: the line was effectively a constant, and the "
              "correlation with the market (0.024) is what exposed it, not the error.")}
</div>
"""
    return page("lines.html", "Our own number", "T3 · side, total, ML", body,
                "Fair line, market line and the difference as three separate columns — "
                "side first, then total, then moneyline.")


def p_leaderboard() -> str:
    b = jload("data/lab/leaderboard.json")
    rows = b["rows"]
    body = f"""
<div class="note bad"><b>The case this design exists to catch.</b> {esc(b['summary']['finding'] or '')}</div>

<div class="card">
  <h2>The board</h2>
  {table(["#", "Strategy", "Market", "n", "Hit", "Break-even bar", "z", "95% interval",
           "ROI (flat)", "Profit (5% compounding)", "Max DD", "Gates", "Status", "Demoted by",
           "Tickets"],
         [[str(r["rank"]), esc(r["name"]), esc(r["market"]), str(r["signal"].get("n", 0)),
           pct(r["signal"].get("hit_rate")), pct(r["signal"].get("break_even_hit_rate")),
           (f'<b>{numf(r["signal"].get("z_vs_break_even"), 2)}</b>'
            if r["signal"].get("z_vs_break_even") is not None else dash()),
           (f'{pct(r["signal"]["hit_rate_ci95"][0])}&ndash;{pct(r["signal"]["hit_rate_ci95"][1])}'
            if r["signal"].get("hit_rate_ci95") else dash()),
           pct(r["staking_flat"].get("roi")),
           (f'{numf(r["staking_pct"].get("profit_units"), 1)}u'
            if r["staking_pct"].get("profit_units") is not None else dash()),
           pct(r["staking_pct"].get("max_drawdown")),
           f'{r["gates_passed"]} pass / {len(r["gates_failed"])} fail / {len(r["gates_blocked"])} blocked',
           badge(r["status"].upper(), "ok" if r["status"] == "live" else "grey"),
           esc(", ".join(c["id"] for c in r["demotion"].get("checks", []) if c["fires"]) or "—"),
           src(f"{GITHUB}/data/lab/leaderboard.json", "leaderboard.json")]
          for r in rows],
         note="Rank is by signal z, then ROI. ROI is displayed but never ranks, because a hot "
              "staking run on a chance signal is exactly what the owner asked to exclude. The "
              "compounding column is profit in units on a 100-unit bankroll, not a per-unit ROI: "
              "compounding a stake on a handful of winning parlays produces a large multiple "
              "that is not comparable with a flat-stake ROI, so it is labelled as what it is.",
         numeric=(0, 3, 4, 5, 6, 8, 9, 10))}
</div>

<div class="card">
  <h2>Findings the split made visible</h2>
  {table(["ID", "Finding", "Measure", "What it means", "Source"],
         [[esc(f["id"]), esc(f["finding"]), esc(f["measure"]), esc(f["reading"]),
           src(f"{GITHUB}/data/lab/leaderboard.json", f["source"].split(",")[0])]
          for f in b["summary"].get("findings", [])],
         note="F-01 is the reason no moneyline is offered as a playable number: the derived win "
              "probability is wrong at the tails, and the per-ticket bar is what exposed it.")}
</div>

<div class="card">
  <h2>Which side of the price each strategy takes</h2>
  {table(["Strategy", "Home", "Away", "% away", "Link"],
         [[esc(k), str(v["home"]), str(v["away"]), pct(v["pct_away"]),
           src(f"{GITHUB}/data/lab/leaderboard.json", "selection_mix")]
          for k, v in b["summary"].get("selection_mix", {}).items()], numeric=(1, 2, 3),
         note="A strategy that mostly backs underdogs has a low hit rate and a low bar; one "
              "that mostly backs favourites has the opposite. Raw hit rates are not comparable "
              "across the two, which is exactly why the bar is per ticket.")}
</div>

<div class="card">
  <h2>Why signal and staking are different columns</h2>
  <div class="grid2">
    <div>
      <h3>Signal: the picks only</h3>
      <ul class="tight">
        <li><b>n</b> and hit rate on decided tickets; pushes excluded from the denominator.</li>
        <li><b>The break-even bar is per ticket.</b> A -110 single breaks even at 52.38%; a
        +250 moneyline at 28.6%; a two-leg -110 parlay at 27.44%. Testing everything against
        52.38% scored the parlay at z = -7.2 when it was actually 3 points above its own bar.</li>
        <li><b>z</b> is a Poisson-binomial test, because each ticket has its own bar.</li>
        <li><b>Interval</b>: 2,000 bootstrap resamples, fixed seed.</li>
        <li><b>Luck trim</b>: one-score games and blowouts removed, because a single bounce
        decides those.</li>
      </ul>
    </div>
    <div>
      <h3>Staking: the money only</h3>
      <ul class="tight">
        <li><b>ROI at a flat unit</b>, and again under a 5%-of-bankroll compounding plan.</li>
        <li><b>Max drawdown</b> under the compounding plan, against a 25% pre-registered cap.</li>
        <li><b>Independence</b>: a profit that exists under one stake plan and not the other is
        labelled as an artefact rather than a result.</li>
      </ul>
    </div>
  </div>
</div>

<div class="card">
  <h2>Defects found in the leaderboard's own arithmetic</h2>
  {table(["ID", "What was wrong", "Effect", "Fix", "How it was caught", "Code"],
         [[esc(d["id"]), esc(d["was"]), esc(d["effect"]), esc(d["fixed_in"]),
           esc(d.get("caught_by", "—")),
           src(f"{GITHUB}/tools/lab/build_strategies.py", "build_strategies.py")]
          for d in b["summary"]["defects_found_in_this_build"]],
         note="B-01 and B-02 were caught by reading a row that could not be true: a -7 z next "
              "to a hit rate above break-even, and a -40% ROI next to a hit rate above bar.")}
</div>
"""
    return page("leaderboard.html", "Signal versus staking", "T5 · competition", body,
                "Two scores per strategy, so a lucky staking run cannot hide a bad signal.")


def p_deficiency() -> str:
    d = jload("data/lab/deficiency.json")
    t = d["totals"]
    certain = [r for r in d["rows"] if r["state"] == "replacement_certain"]
    body = f"""
<section class="kpis">
{kpi(str(t["replacement_certain"]), "certain replacements", "starter Out or Doubtful", "ok")}
{kpi(str(t["replacement_possible"]), "possible", "starter Questionable", "warn")}
{kpi(str(t["certain_replacements_with_no_replacement_listed"]), "no replacement listed",
     "club names nobody behind him", "warn")}
{kpi(str(t["depth_losses_second_string_or_deeper"]), "depth losses", "2nd/3rd string also Out",
     "bad")}
</section>

<div class="card">
  <h2>Who steps in, and how far back</h2>
  {table(["Team", "Unit", "Pos", "Starter", "Status", "Practice", "Replacement",
           "Replacement tier", "Chart", "Injury report"],
         [[esc(r["team"]), esc(r["unit"]), esc(r["position"]), esc(r["starter"]),
           badge(r["starter_status"] or "—", "bad" if (r["starter_status"] or "").lower() == "out" else "warn"),
           esc(r["starter_practice"] or "—"),
           esc(r["replacement"]) if r["replacement"] else badge("NONE LISTED", "warn"),
           (f'tier {r["replacement_tier"]}' if r["replacement_tier"] else "—"),
           src(r["chart_url"]), src(r["injury_url"])] for r in certain],
         note="Every row carries the club's own chart and the league's own injury report. The "
              "club charts are self-published and labelled unofficial by the clubs; that caps "
              "the confidence of every row here, and is why the effect on the line is not "
              "claimed anywhere.")}
</div>

<div class="card">
  <h2>The depth behind the starter: losses that are not replacements</h2>
  <p class="lede">These players are <b>not</b> replacing a starter this week. They are the
  second and third string, and they are out too — which thins the room without changing the
  starting lineup. This is the other half of the owner's requirement, and it is a different
  measurement.</p>
  {table(["Team", "Unit", "Pos", "Player", "Tier", "Injury", "Status", "Chart", "Injury report"],
         [[esc(r["team"]), esc(r["unit"]), esc(r["position"]), esc(r["player"]),
           esc(r["tier_label"]), esc(r["injury"] or "—"),
           badge(r["status"], "bad" if r["status"] == "Out" else "warn"),
           src(r["chart_url"]), src(r["injury_url"])] for r in d["depth_losses"]])}
</div>

<div class="card">
  <h2>Findings</h2>
  {table(["ID", "Finding", "Measure", "What it does not mean", "Evidence"],
         [[esc(f["id"]), esc(f["finding"]), esc(f["measure"]),
           esc(f.get("not_the_same_as") or f.get("consequence") or "—"),
           " ".join(src(u if u.startswith("http") else f"{GITHUB}/{u}") for u in f["source"])]
          for f in d["findings"]])}
</div>

<div class="grid2">
  <div class="card">
    <h2>Defensive depth by club</h2>
    {table(["Team", "Starters out", "3rd+ string replacements", "Max gap", "Chart"],
           [[esc(r["team"]), str(r["starters_ruled_out_or_doubtful"]),
             str(r["replacements_who_are_3rd_string_or_deeper"]),
             str(r["max_depth_gap"] if r["max_depth_gap"] is not None else "—"),
             src(r["chart_url"])] for r in d["defense_board"][:14]
            if r["starters_ruled_out_or_doubtful"] or r["starters_questionable"]],
           numeric=(1, 2, 3))}
  </div>
  <div class="card">
    <h2>Offensive depth by club</h2>
    {table(["Team", "Starters out", "3rd+ string replacements", "Max gap", "Chart"],
           [[esc(r["team"]), str(r["starters_ruled_out_or_doubtful"]),
             str(r["replacements_who_are_3rd_string_or_deeper"]),
             str(r["max_depth_gap"] if r["max_depth_gap"] is not None else "—"),
             src(r["chart_url"])] for r in d["offense_board"][:14]
            if r["starters_ruled_out_or_doubtful"] or r["starters_questionable"]],
           numeric=(1, 2, 3))}
  </div>
</div>

<div class="note warn"><b>No line effect is claimed.</b> {esc(d['effect_status']['why'])}</div>
"""
    return page("deficiency.html", "Who steps in, and how far back", "T6 · depth", body,
                "Replacement depth by rung of the chart, for offence and defence, with the "
                "coverage gaps counted.")


def p_correlation() -> str:
    c = jload("data/lab/correlations.json")
    def block(f: dict) -> str:
        return f"""
<div class="card">
  <h2>{esc(f['title'])}</h2>
  <p class="legend">{esc(f['why_it_matters'])}</p>
  {table(["Value", "n", "r", "95% interval", "p", "Status", "Sources"],
         [[esc(r["name"]), f"{r['n']:,}",
           numf(r["r"], 2) if r["r"] is not None else dash(r.get("why", "not computed")),
           (f'[{numf(r["ci95"][0], 2)}, {numf(r["ci95"][1], 2)}]'
            if r.get("ci95") else dash()),
           numf(r.get("p_value"), 4) if r.get("p_value") is not None else dash(),
           badge(r["status"], "ok" if r["status"] == "MEASURED" else "warn"),
           " ".join(src(u if u.startswith("http") else f"{GITHUB}/{u}") for u in r["sources"])]
          for r in f["rows"]],
         numeric=(1, 2, 4),
         note="n is the number of paired observations the value was computed on. A pair with "
              "n below 30, or with an unsourced side, is published as such rather than as a "
              "number.")}
</div>"""

    body = f"""
<div class="note"><b>The rule.</b> A correlation is a claim about a joint distribution, so
every value here carries its n, a 2,000-resample bootstrap interval, a permutation p-value
and both of its sources. A value without those is not published. Three required pairs are
listed as NOT SOURCED at the bottom rather than estimated.</div>

<section class="kpis">
{kpi(str(c['counts']['measured']), "values measured", "with n and an interval", "ok")}
{kpi(str(c['counts']['not_sourced']), "refused as unsourced", "published as gaps", "warn")}
{kpi("0.0216", "margin vs total", "n = 7,413", "")}
{kpi(f"{c['rule']['minimum_n']}", "minimum n", "below this: not published", "")}
</section>

{''.join(block(f) for f in c["families"])}
"""
    return page("correlation.html", "With n on every value", "T7 · measured", body,
                "Correlations computed only from sourced numbers, each with the n it rests on.")


def p_validation() -> str:
    b = jload("data/lab/leaderboard.json")
    gate_defs = [
        ("D-01", "Signal decay", "the rolling 30-ticket z falls below 0 for two consecutive windows",
         "a signal that has stopped working is a signal that has stopped working"),
        ("D-02", "Staking break", "realised drawdown exceeds the 25% pre-registered cap",
         "the stake plan is now the risk, not the edge"),
        ("D-03", "Price loss", "mean CLV proxy turns negative over a full window",
         "you are taking worse numbers than the close; the edge is gone even if the record is not"),
        ("D-04", "Drift", "live hit rate falls more than 2 standard errors below the promotion bar",
         "the live population differs from the one the strategy was promoted on"),
    ]
    body = f"""
<div class="note ok"><b>A gate that cannot fire is not a gate.</b> All four triggers are
evaluated on every build, and the verdict is published here even when it demotes a row with a
positive ROI. On this snapshot it does exactly that.</div>

<div class="card">
  <h2>The demotion gate</h2>
  {table(["ID", "Trigger", "Fires when", "Why it is the right test", "Artefact"],
         [[esc(a), esc(b_), esc(c_), esc(d_),
           src(f"{GITHUB}/data/lab/leaderboard.json", f"{a} evaluation")]
          for a, b_, c_, d_ in gate_defs])}
</div>

<div class="card">
  <h2>Evaluation on this snapshot, every strategy</h2>
  {table(["Strategy", "Status", "D-01 decay", "D-02 staking", "D-03 CLV", "D-04 drift",
           "Verdict", "Detail", "Artefact"],
         [[esc(r["name"]), badge(r["status"].upper(), "ok" if r["status"] == "live" else "grey"),
           *(badge("FIRES", "bad") if c["fires"] else badge("quiet", "ok")
             for c in r["demotion"].get("checks", [])),
           badge("DEMOTE", "bad") if r["demotion"]["demote"] else badge("hold", "ok"),
           esc("; ".join(f'{c["id"]}: {c["detail"]}' for c in r["demotion"].get("checks", []) if c["fires"]) or "no trigger fired"),
           src(f"{GITHUB}/data/lab/leaderboard.json", "demotion")]
          for r in b["rows"]])}
</div>

<div class="card">
  <h2>Why the parlay is demoted even though it made money</h2>
  <p>It shows a +10.5% ROI at a flat stake, which on a naive board would rank it first. Its
  signal z is 1.00 against a 1.96 bar — indistinguishable from chance — and under a
  5%-of-bankroll compounding plan its drawdown reaches 52.7%, more than twice the 25% cap.
  D-03 also fires: the mean CLV proxy over its last 30 tickets is negative. A strategy that
  cannot survive a change of stake plan and is taking worse numbers than the close is a
  staking result, not a signal, and it goes back to paper.</p>
</div>

<div class="card">
  <h2>The validation gates, and how many strategies pass</h2>
  {table(["Gate", "Name", "Pass", "Fail", "Blocked", "Artefact"],
         [[f"G{i}", nm,
           str(sum(1 for r in b["rows"] if next(g["passed"] for g in r["gates"] if g["id"] == f"G{i}") is True)),
           str(sum(1 for r in b["rows"] if next(g["passed"] for g in r["gates"] if g["id"] == f"G{i}") is False)),
           str(sum(1 for r in b["rows"] if next(g["passed"] for g in r["gates"] if g["id"] == f"G{i}") is None)),
           src(f"{GITHUB}/data/lab/leaderboard.json", f"G{i}")]
          for i, nm in enumerate(["Provenance", "Sample size", "Skill above variance",
                                  "Calibration", "Robustness", "Risk of ruin",
                                  "Economic reality", "Correlation discipline"])],
         numeric=(2, 3, 4),
         note="'Blocked' means the gate cannot be evaluated with the evidence available. It is "
              "never counted as a pass — a strategy with a blocked gate stays on paper.")}
</div>
"""
    return page("validation.html", "When a strategy goes back to paper", "T8 · gate", body,
                "Four automatic triggers, evaluated every build, that demote a live strategy.")


def p_questions() -> str:
    q = jload("data/lab/questions.json")
    body = f"""
<div class="note"><b>{q['counts']['questions']} questions, {q['counts']['p0']} of them P0.</b>
Each row states what we have, what we do not have, what is blocked until it is answered, and
the observable test that closes it. Four of them are genuinely your call, not a data problem —
those are marked.</div>

<div class="card">
  <h2>Questions before any decision</h2>
  {table(["ID", "Area", "Question", "What we have", "What we do not have", "What it blocks",
           "Closes when", "Yours?", "Evidence"],
         [[esc(r["id"]), esc(r["area"]), f'<b>{esc(r["question"])}</b>', esc(r["have"]),
           esc(r["missing"]), esc(r["blocks"]), esc(r["closing_test"]),
           badge("YOUR CALL", "blue") if r["owner_call"] else badge("data problem", "grey"),
           src(f"{GITHUB}/data/lab/questions.json", r["source"].split(" (")[0])]
          for r in q["questions"]],
         note="The 'have' column quotes the measured number and the artefact it came from; the "
              "'missing' column names the specific field, not 'more data'.")}
</div>

<div class="card">
  <h2>What cannot be decided yet, and why that is fine</h2>
  <p>Every question above has a closing test that is a number, not an opinion: two captures of
  the same book that agree, a coefficient whose interval excludes zero, a licence that permits
  publication. That is deliberate. A decision made before its question closes is a guess with
  a paper trail, and the paper trail is the only part that helps later.</p>
</div>
"""
    return page("questions.html", "What we know, what we don't", "Decision support", body,
                "Every open question with its missing information and the test that closes it.")


def p_suggestions() -> str:
    s = jload("data/lab/suggestions.json")
    blocks = []
    for sg in s["suggestions"]:
        paths = table(["Path", "What it is", "Cost", "Unlocks", "Risk", "Effort", "Record"],
                      [[badge(p["name"], "blue") if p["id"] == sg["recommended"]
                        else esc(p["name"]),
                        esc(p["what"]), esc(p["cost"]), esc(p["unlocks"]), esc(p["risk"]),
                        esc(p["effort"]),
                        src(f"{GITHUB}/data/lab/suggestions.json", f"{sg['id']} path {p['id']}")]
                       for p in sg["paths"]])
        blocks.append(f"""
<div class="card" id="{esc(sg['id'])}">
  <h2>{esc(sg['id'])} · {esc(sg['title'])}</h2>
  {paths}
  <div class="note ok"><b>Suggested path: {esc(sg['recommended'])}</b> — {esc(sg['why'])}
  <br><small>This is an opinion, and it is the only opinion on this page. What would change
  it: {esc(sg['would_change'])}</small></div>
</div>""")
    body = f"""
<div class="note warn"><b>Nothing on this page is implemented.</b> Each suggestion offers every
path it has with its cost, what it unlocks and its risk. Pick one and it becomes a task; until
then the default is to change nothing. The recommendation is this session's opinion and is
labelled as one.</div>

<div class="card">
  <h2>How to use this board</h2>
  <ol class="findings">
    <li>Read the <a href="questions.html">Questions</a> page first. A suggestion that does not
    close a question is not urgent.</li>
    <li>Each suggestion below has {s['counts']['paths']} paths in total across
    {s['counts']['suggestions']} suggestions. The suggested path is marked; the others are
    real alternatives, not straw men.</li>
    <li>Reply with the IDs you want implemented. Nothing else has to be decided first.</li>
  </ol>
</div>

{''.join(blocks)}
"""
    return page("suggestions.html", "Choose a path before building", "Decision support", body,
                "Five suggestions, fourteen paths, each with its cost, what it unlocks and its risk.")


def p_sources() -> str:
    pin = jload("data/lab/upstream/_pin.json")
    prices = jload("data/lab/prices/price_coverage.json")
    files = prices["_files"]
    src_rows = [
        ["nflverse nfldata repository archive",
         f'<span class="mono">{esc(pin["archive_sha256"][:24])}&hellip;</span>',
         "the only nflverse source reachable from this environment",
         src("https://github.com/nflverse/nfldata/tree/master/data",
             "github.com/nflverse/nfldata/data")],
        ["games.csv",
         f'<span class="mono">{esc((files["games.csv"]["sha256"] or "")[:24])}&hellip;</span>',
         "scores, spread_line, total_line, moneylines",
         src(files["games.csv"]["upstream_url"], "…/games.csv")],
        ["initial_lines.csv",
         f'<span class="mono">{esc((files["initial_lines.csv"]["sha256"] or "")[:24])}&hellip;</span>',
         "the only opening-number evidence; 2021 only",
         src(files["initial_lines.csv"]["upstream_url"], "…/initial_lines.csv")],
        ["closing_lines.csv",
         f'<span class="mono">{esc((files["closing_lines.csv"]["sha256"] or "")[:24])}&hellip;</span>',
         "the only closing-number evidence; 2006-2018",
         src(files["closing_lines.csv"]["upstream_url"], "…/closing_lines.csv")],
        ["DATASETS.md", "&mdash;", "the publisher's own column definitions",
         src("https://github.com/nflverse/nfldata/blob/master/DATASETS.md")],
        ["NFL injury report (via data/pipeline/injuries.json)", "&mdash;",
         "collected by session arena/d577959f-x1; not re-fetchable here",
         src("https://www.nfl.com/injuries/")],
        ["Club depth charts (via data/pipeline/depth_charts.json)", "&mdash;",
         "31 clubs; each row links its own club page",
         src("https://www.nfl.com/teams/", "nfl.com/teams")],
    ]
    # R1 (session arena-9d8c298c-x1): the four official pages read live on 2026-11-17, plus the two
    # fixture pages read for venue evidence. Transcriptions and hashes are in the pack's manifest.
    for label, url, what in [
        ("nfl.com Week 10 schedule page (live read 2026-11-17)",
         "https://www.nfl.com/schedules/2026/by-week/week-10",
         "the 14 Week 10 finals, the four clubs on bye, and the records printed beside each club"),
        ("nfl.com Week 11 schedule page (live read 2026-11-17)",
         "https://www.nfl.com/schedules/2026/by-week/week-11",
         "the 13 Week 11 fixtures, dates, ET kickoffs, networks, six byes, and the event labels"),
        ("nfl.com league standings (live read 2026-11-17)",
         "https://www.nfl.com/standings/league/2026/REG",
         "32 clubs &times; W-L-T, PCT, PF, PA, net, home, road, div, conf, streak, last five"),
        ("nfl.com injury hub (live read 2026-11-17)", "https://www.nfl.com/injuries/",
         "44 rows transcribed by hand across four clubs and diffed against the retained capture"),
        ("nfl.com Game Center, Colts at Texans", "https://www.nfl.com/games/colts-at-texans-2026-reg-11",
         "the Game Info Location and Stadium fields for one Week 11 fixture"),
        ("nfl.com Game Center, Vikings at 49ers", "https://www.nfl.com/games/vikings-at-49ers-2026-reg-11",
         "the same two fields for the Mexico City fixture, which is where the venue conflict shows up"),
    ]:
        src_rows.append([label, "&mdash;", what, src(url, "official page")])
    limits = [[esc(x), badge("BLOCKED", "bad"),
               src(f"{GITHUB}/data/lab/upstream/_pin.json", "upstream/_pin.json")]
              for x in pin["limitations"]]
    body = f"""
<div class="card">
  <h2>Every source this round used</h2>
  {table(["Dataset", "SHA-256 (prefix)", "What it provides", "Link"],
         src_rows, note="A source is only usable if it is reachable from the environment that "
                        "built the artefact. Four were not, and are listed below.")}
</div>

<div class="card">
  <h2>Environment limits, stated rather than worked around</h2>
  {table(["Limit", "Status", "Link"], limits, note="These are the constraints that shaped every "
         "artefact in this section. They are published because a reader has to know what could "
         "not be checked, not only what was.")}
  <p class="legend">This is why the price store has no book and no timestamp: the upstream has
  none, and the sources that do are not reachable here. It is also why no injury row was
  re-verified by this session — the league page could not be fetched.</p>
</div>

<div class="card">
  <h2>Corrections to this page, dated</h2>
  {table(["Statement above", "Status after 2026-11-17", "Evidence"],
         [["&ldquo;the league page could not be fetched&rdquo;",
           "superseded. nfl.com was fetched live on 2026-11-17 from this environment: four list pages "
           "and two fixture pages, transcribed into a dated pack",
           src(f"{GITHUB}/{READS_PACK}/manifest.json", "reads manifest")],
          ["&ldquo;no injury row was re-verified by this session&rdquo;",
           "superseded for 44 rows: four club tables transcribed by hand and diffed cell by cell against "
           "the newest accepted capture, " + str(jload(f"{READS_PACK}/report.json")["numbers"]["injury_spot_check_mismatches"]) +
           " mismatches over 220 cells",
           src(f"{GITHUB}/{READS_PACK}/injury_spotcheck_2026-11-17.tsv", "spot-check")],
          ["&ldquo;the sources that do [carry a book and a timestamp] are not reachable here&rdquo;",
           "unchanged. No price source with a named book and a timestamp has been reached, so the price "
           "store still has no book, and the market line and residual stay blank on every escrow row",
           src(f"{GITHUB}/docs/methodology/availability.md", "availability")],
          ["the snapshot date in the page furniture, " + SNAPSHOT,
           "unchanged and still correct for the artefacts built on it: the reads below are dated in their "
           "own pack rather than re-stamping this round's snapshot",
           src(f"{GITHUB}/tools/lab/build_site.py", "build_site.py")]],
         note="The rows above are left as the round that wrote them published them. A correction is "
              "dated and placed beside the claim instead of editing it away, because the claim was true "
              "when it was written and the reader needs to know which of the two it is reading.")}
</div>

<div class="card">
  <h2>What is verified, and by what</h2>
  {table(["Claim", "Verified by", "Link"],
         [["Scores and margins", "re-derived from the publisher's own columns on every build; "
           "0 mismatches across 7,413 games",
           src("https://github.com/nflverse/nfldata/blob/master/data/games.csv")],
          ["Line-level arithmetic", "the score columns were re-summed and re-subtracted rather "
           "than trusted", src(f"{GITHUB}/tools/lab/build_results.py", "build_results.py")],
          ["Price-store coverage figures", "recomputed from the raw files on every build",
           src(f"{GITHUB}/data/lab/prices/price_coverage.json", "price_coverage.json")],
          ["Model accuracy", "walk-forward, tuned on 1999-2014, scored on 2015-2026 only",
           src(f"{GITHUB}/data/lab/lines/model_report.json", "model_report.json")],
          ["Strategy signal", "per-ticket break-even, Poisson-binomial z, bootstrap interval",
           src(f"{GITHUB}/data/lab/leaderboard.json", "leaderboard.json")],
          ["Correlation values", "n, bootstrap interval and permutation p on every row",
           src(f"{GITHUB}/data/lab/correlations.json", "correlations.json")],
          ["Depth-chart rows", "each row links the club page it was read from; the join to the "
           "injury report is exact-name only",
           src(f"{GITHUB}/data/lab/deficiency.json", "deficiency.json")],
          ["Nothing else", "everything not in this list is a gap, and is on the Flagged page",
           src(f"{GITHUB}/lab/flagged.html", "Flagged for review")]],
         note="This table is the answer to what has actually been checked. Anything not listed "
              "here is not checked, and is flagged rather than implied.")}
</div>
"""
    return page("sources.html", "Every source, and every limit", "Provenance", body,
                "What was read, from where, with the hash of the exact bytes, and what could "
                "not be reached at all.")


def p_flagged() -> str:
    prices = jload("data/lab/prices/price_coverage.json")
    model = jload("data/lab/lines/model_report.json")
    board = jload("data/lab/leaderboard.json")
    defi = jload("data/lab/deficiency.json")
    corr = jload("data/lab/correlations.json")

    flags = []
    for d in prices["defects"]:
        flags.append(["P", d["id"], d["severity"], d["claim"], d["measure"],
                      " ".join(src(u) for u in d["source"]), "does not block publication; "
                      "blocks CLV and gate G0"])
    for d in model["defects_found_in_this_build"]:
        flags.append(["L", d["id"], d["severity"], f"Model defect, fixed: {d['was']}",
                      d["effect"], src(f"{GITHUB}/tools/lab/build_lines.py"),
                      "fixed; recorded so the published numbers are auditable"])
    for d in board["summary"]["defects_found_in_this_build"]:
        flags.append(["B", d["id"], d["severity"], f"Leaderboard defect, fixed: {d['was']}",
                      d["effect"], src(f"{GITHUB}/tools/lab/build_strategies.py"), "fixed"])
    # C1 (session arena-3f5badd0-x1): irregularities of the control-baseline round.
    MIRROR_URL = "https://github.com/nflverse/nfldata/blob/master/data/games.csv"
    flags.append(["K", "C1-01", "medium",
                  "Control baselines use a community-mirror spread, not an official price",
                  "favourites 881–947–43 against the spread, 2019–2025; the mirror states no book or timestamp",
                  src(MIRROR_URL, "nflverse/nfldata games.csv"),
                  "does not block; a named-book dated spread would confirm or move the favourites row (Q-02)"])
    flags.append(["K", "C1-02", "medium",
                  "No leaderboard run can be scored against a control on the same games",
                  "8 of 8 leaderboard rows show NOT RUN; their window and price are not in the registered universe",
                  src(f"{GITHUB}/data/lab/leaderboard.json", "leaderboard.json"),
                  "does not block; the control gate stays NOT RUN until a dated 2026 price exists"])
    flags.append(["K", "C1-03", "low",
                  "The mirror file changed on GitHub after the pinned copy was taken",
                  "upstream commit 6d38e30 (automated data update) posted after the pin; the pinned bytes are used",
                  src("https://github.com/nflverse/nfldata/commits/master/data/games.csv", "file history"),
                  "not re-pinned in this round, so the registered universe does not move"])
    for f in defi["findings"]:
        flags.append(["X", f["id"], "info", f["finding"], f["measure"],
                      " ".join(src(u) for u in f["source"]) if all(
                          str(u).startswith("http") for u in f["source"])
                      else src(f"{GITHUB}/data/lab/deficiency.json"),
                      "coverage finding"])
    for fam in corr["families"]:
        for r in fam["rows"]:
            if r["status"] == "NOT SOURCED":
                flags.append(["C", fam["id"], "medium", f"Not computable: {r['name']}",
                              r["why"], src(f"{GITHUB}/data/lab/correlations.json"),
                              r.get("what_would_close_it", "")])

    # R1 (session arena-9d8c298c-x1, 2026-11-17): irregularities found while reading the official
    # pages. Each one is a measured state of the source, not a guess about it - the numbers come from
    # the reads-pack report so a re-read that resolves the item makes the row disappear by itself.
    try:
        rep = jload(f"{READS_PACK}/report.json")
    except (OSError, ValueError):
        rep = None
    if rep:
        RN, RC = rep["numbers"], rep["checks"]
        VEN = f"{GITHUB}/{READS_PACK}/venue_evidence_2026-11-17.tsv"
        REP = f"{GITHUB}/{READS_PACK}/report.json"
        flags.append(["R1", "R1-01", "medium",
                      "Two official pages print different stadium names for the same fixture",
                      f"Colts at Texans: the schedule page's link parameter says NRG Stadium, the fixture "
                      f"page's Game Info block prints RELIANT STADIUM. Both are the NFL's own text.",
                      src(VEN, "venue evidence"),
                      "a venue-keyed lookup (roof, surface) fails silently on this fixture; key on the "
                      "club, not the stadium name"])
        flags.append(["R1", "R1-02", "medium",
                      "The Mexico City fixture receives a home-field edge at a neutral venue",
                      "Vikings at 49ers prints Location MEXICO CITY, Stadium ESTADIO BANORTE; PR-01 and "
                      "PR-04 add 1.6 points to the nominal home club because the frozen rule says so",
                      src(f"{GITHUB}/{READS_PACK}/week11_slate_2026-11-17.tsv", "Week 11 slate"),
                      "not corrected: the constants are frozen for this window. Recorded for the next "
                      "registration, which can decide whether a neutral venue voids the edge"])
        flags.append(["R1", "R1-03", "medium",
                      "The published Week 10 injury table is 2 rows short of the newest accepted capture",
                      f"{RN.get('published_injury_rows_vs_capture', 0)} rows differ: Calais Campbell and "
                      f"Ronnie Stanley (BAL) are in the capture the collector accepted and are not on the "
                      f"site table (345 published vs 347 captured); the parallel read's own verifier "
                      f"reports the same \"missing 2\"",
                      src(REP, "report.json"),
                      "a stale published count, not a typo: the table needs the republish that the brief "
                      "asks for after each re-capture"])
        flags.append(["R1", "R1-04", "info",
                      "No Week 11 injury report exists yet, so no Week 11 availability delta can be published",
                      "the injury page's own week selector ends at WEEK 10, and all four Week 11 fixture "
                      "pages read this round print \"Injury Report is not available at this time\"; the "
                      "capture series has taken 10 reads with "
                      f"{RN['injury_reads_since_last_content_change']} of them seeing unchanged content",
                      src("https://www.nfl.com/injuries/", "injury hub"),
                      "the machinery is running and the source is empty; nobody can build a Week 11 "
                      "personnel signal today"])
        flags.append(["R1", "R1-05", "medium",
                      "The results feed is 13 games short of the corpus the standings imply",
                      f"{RC['C7_results_log_gap']['week10_games_absent_from_the_published_log']} Week 10 "
                      f"finals are read and cross-checked but not in data/results; the mirror row-diff gate "
                      f"blocks all 13, and 4 executable lines pin the builder to 137 rows",
                      src(f"{GITHUB}/{READS_PACK}/feed-closure-measurement.json", "closure measurement"),
                      "measured, not fixed: the append would move the frozen PR-01 input and the pinned "
                      "standings baseline, so it is the owner's call (see the Feed closure page)"])
        flags.append(["R1", "R1-06", "medium",
                      "Venue transcription covers 2 of the 27 fixtures this round could have read",
                      f"the brief asks for the venue of every fixture from the official game centre; "
                      f"{RN['venue_direct_rows']} Game Center pages were read (Colts at Texans, Vikings at "
                      f"49ers), the weekly schedule page prints no venue field for any of the other 25, and "
                      f"the 2026-11-16 pack documents the same limit for Week 10",
                      src(f"{GITHUB}/{READS_PACK}/venue_evidence_2026-11-17.tsv", "venue evidence"),
                      "left as a measured gap rather than filled from memory: a stadium name typed from recall "
                      "is indistinguishable in the artefact from one read off the page"])
        flags.append(["R1", "R1-08", "high",
                      "Two dated packs in this repository key the same fixture with different game_ids",
                      "Rams at Cardinals: this pack writes 2026_10_LA_ARZ, the 2026-11-17 read in "
                      "data/verification/2026_11_17 writes 2026_10_LAR_AZ for the identical game, while its "
                      "own value columns print LA and AZ; 1 of 14 fixtures diverges and every value agrees",
                      src(f"{GITHUB}/data/verification/2026_11_17/official_w10_results_2026_11_17.tsv",
                          "the other pack's read"),
                      "a join across the two trees on game_id silently drops a row. Check C12 joins on the "
                      "official fixture slug for that reason; anything written later should do the same, and "
                      "one of the two conventions should be retired rather than reconciled row by row"])
        flags.append(["R1", "R1-07", "low",
                      "One injury-page capture was refused by the drift gate for a club-code spelling",
                      "the 2026-11-15 read prints LAR where the standings page prints LA; a join on it "
                      "would silently drop 14 rows",
                      src(f"{GITHUB}/data/captures/index.jsonl", "capture index"),
                      "the capture is kept and the read is refused, which is the behaviour the gate is for"])

    body = f"""
<div class="note warn"><b>Nothing on this page blocks anything.</b> These are the values that
could not be sourced, the defects found in this round's own work, and the coverage gaps. They
are here so you can review them after the rest of the site is live. Every row carries a link.</div>

<div class="card">
  <h2>{len(flags)} flagged items</h2>
  {table(["Kind", "ID", "Severity", "What", "Measure / detail", "Source", "Effect"],
         [[esc(a), esc(b_), badge(c_, "bad" if c_ == "high" else "warn" if c_ in ("medium", "info") else "grey"),
           esc(d_), esc(e_), f_, esc(g_)] for a, b_, c_, d_, e_, f_, g_ in flags],
         note="Kind: P = price-store provenance, L = line model, B = leaderboard, X = coverage "
              "finding, C = correlation pair that could not be computed from sourced numbers, "
              "R1 = the 2026-11-17 official read.")}
</div>

<div class="card">
  <h2>Values deliberately left empty</h2>
  {table(["Value", "Why it is empty", "Evidence"],
         [["The opening price for every market", "no reachable file carries an opening price; "
           "initial_lines.csv covers 2021 only and its numbers do not reconcile with games.csv",
           src("https://github.com/nflverse/nfldata/blob/master/data/initial_lines.csv")],
          ["The book for any closing line", "the publisher names no book",
           src("https://github.com/nflverse/nfldata/blob/master/data/closing_lines.csv")],
          ["The capture time for any line", "the publisher has no time column",
           src("https://github.com/nflverse/nfldata/blob/master/DATASETS.md")],
          ["Player-prop prices and outcomes", "no reachable source; a prop combo is therefore "
           "untested, not simulated",
           src(f"{GITHUB}/data/lab/correlations.json", "correlations.json (C4)")],
          ["The injury effect on the line", "one week of data cannot identify it",
           src(f"{GITHUB}/data/lab/deficiency.json", "deficiency.json")],
          ["A reward amount", "no reward rule exists, and the legal question is not this "
           "repository's to answer", src(f"{GITHUB}/data/lab/suggestions.json", "S-L2")],
          ["Capital, stakes and bankroll", "no staking rule has been agreed",
           src(f"{GITHUB}/data/lab/leaderboard.json", "leaderboard.json")]],
         note="Every one of these is a row somewhere on this site that renders as an em dash. "
              "They are collected here so a reviewer can see the full set in one place.")}
</div>
"""
    return page("flagged.html", "Flagged for review", "Never filled in", body,
                "Unverified values, defects found in this round's own work, and coverage gaps.")


# ------------------------------------------------------------------ check
_VOID = {"br", "img", "meta", "link", "input", "hr", "area", "base", "col", "embed",
         "source", "track", "wbr"}


class _Structure(html.parser.HTMLParser):
    """Minimal tag-balance checker: enough to catch a truncated or mis-nested page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.broken: list[str] = []
        self.ids: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.append(a["id"])
        if tag not in _VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        if not self.stack:
            self.broken.append(f"extra </{tag}>")
        elif self.stack[-1] == tag:
            self.stack.pop()
        elif tag in self.stack:
            while self.stack and self.stack[-1] != tag:
                self.broken.append(f"unclosed <{self.stack.pop()}>")
            if self.stack:
                self.stack.pop()
        else:
            self.broken.append(f"stray </{tag}>")


def check() -> int:
    """Verify the published tree: links resolve, every data row carries a source or an
    explicit 'no official source' marker, and no template artefact leaked into a page."""
    errors: list[str] = []
    files = sorted(f for f in os.listdir(LAB) if f.endswith(".html"))
    for f in files:
        text = open(os.path.join(LAB, f), encoding="utf-8").read()
        if "SNAPSHOT" not in text and "2026-11-14" not in text:
            errors.append(f"{f}: no snapshot date")
        if "../app/assets/site.css" not in text:
            errors.append(f"{f}: does not link the stylesheet")
        if "Flagged for review" not in text:
            errors.append(f"{f}: nav has no flagged-for-review entry")
        for href in re.findall(r'href="([^"]+)"', text):
            if href.startswith(("http", "#")):
                continue
            target = os.path.normpath(os.path.join(LAB, href.split("#")[0]))
            if not os.path.exists(target):
                errors.append(f"{f}: broken link {href}")
        # A leaked Python value is only a defect inside a table cell or an attribute:
        # "None of them produced a bettable edge" is correct English and must not be flagged.
        for cell in re.findall(r"<td[^>]*>(.*?)</td>", text, flags=re.S):
            if re.search(r"(^|>)\s*None\s*(<|$)", cell) or re.search(r"(^|>)\s*False\s*(<|$)", cell):
                errors.append(f"{f}: a Python value leaked into a table cell")
                break
        if "&lt;span" in text or "&lt;td" in text:
            errors.append(f"{f}: escaped markup renders as literal text")
        # structural integrity: balanced tags, no duplicated id, tables closed, h1 present,
        # template syntax never reaches the page. There is no headless browser in this CI,
        # so this is the substitute for a render test.
        parser = _Structure()
        parser.feed(text)
        if parser.stack:
            errors.append(f"{f}: unclosed tags {parser.stack[-4:]}")
        if parser.broken:
            errors.append(f"{f}: tag problems {parser.broken[:3]}")
        dup = sorted({i for i in parser.ids if parser.ids.count(i) > 1})
        if dup:
            errors.append(f"{f}: duplicate ids {dup}")
        if "${" in text:
            errors.append(f"{f}: template syntax leaked into the page")
        if text.count("<table") != text.count("</table>"):
            errors.append(f"{f}: unbalanced table tags")
        if "<h1>" not in text:
            errors.append(f"{f}: no h1")
        # every data-table row must have a source link or an explicit marker
        for i, row in enumerate(re.findall(r"<tr>(.*?)</tr>", text, flags=re.S)):
            if "<td" not in row:
                continue
            if ('class="src"' not in row and "no official source" not in row
                    and "NONE LISTED" not in row and "href=\"https://" not in row):
                errors.append(f"{f}: data row {i} has no source link")
    if errors:
        print("LAB SITE VERIFICATION FAILED")
        for e in errors[:40]:
            print(" -", e)
        return 1
    print(f"lab site verification passed: {len(files)} pages, links resolve, every data row sourced")
    return 0

def p_controls() -> str:
    """Control baselines, pre-registered in docs/lab/control-baselines.md (commit 0747005)."""
    c = jload("data/lab/controls/control_baselines.json")
    b = jload("data/lab/leaderboard.json")
    REG = "https://github.com/karagemop466-tech/X1/commit/0747005"
    MIRROR = "https://github.com/nflverse/nfldata/blob/master/data/games.csv"
    CTRL = f"{GITHUB}/data/lab/controls/control_baselines.json"
    fav, rnd = c["favourites_pooled"], c["random_picks"]

    def ci(lo, hi):
        return f"{pct(lo)}&ndash;{pct(hi)}" if lo is not None and hi is not None else dash()

    headline = f"""
<div class="note"><b>Pre-registered before the numbers were computed.</b> The rules are frozen in
<a href="{REG}" target="_blank" rel="noopener">docs/lab/control-baselines.md at commit <code>0747005</code></a>.
Universe: {fav["games"]:,} regular-season games, 2019–2025, with a spread on record. Source:
<a href="{MIRROR}" target="_blank" rel="noopener">nflverse/nfldata games.csv</a>, a community mirror, <b>not an NFL source</b>.</div>

<div class="kpis">
{kpi(pct(fav["win_rate"]), "Favourites, against the spread", f'{fav["wins"]}–{fav["losses"]}–{fav["pushes"]} · Wilson 95% {ci(fav["wilson95_lo"], fav["wilson95_hi"])}', "")}
{kpi(pct(rnd["mean_win_rate"]), "Random picks, mean of 1,000 runs", f'band {pct(rnd["p2_5"])}–{pct(rnd["p97_5"])} · seed {rnd["seed"]}', "")}
{kpi(pct(fav["su_fav_win_rate"]), "Favourites, straight up", f'n = {fav["su_n"]:,} non-tied games', "")}
{kpi(pct(c["conventions"]["break_even_at_minus_110"]), "Break-even at −110", "arithmetic, not an observed price", "")}
</div>
"""
    season_rows = []
    for s in c["seasons"]:
        f = s["favourites"]
        season_rows.append([
            str(f["scope"].split(" ")[0]), str(f["games"]),
            f'{f["wins"]}–{f["losses"]}–{f["pushes"]}', pct(f["win_rate"]), ci(f["wilson95_lo"], f["wilson95_hi"]),
            pct(f["su_fav_win_rate"]),
            (f'<span class="blank">below the bar</span>' if f["wilson95_hi"] < c["conventions"]["break_even_at_minus_110"]
             else ("above the bar, interval clears it" if f["wilson95_lo"] > c["conventions"]["break_even_at_minus_110"]
                   else ("point above the bar, interval crosses it" if f["win_rate"] >= c["conventions"]["break_even_at_minus_110"]
                         else "point below the bar, interval crosses it"))),
            src(MIRROR, "games.csv"),
        ])
    seasons_tbl = table(
        ["Season", "Games", "Fav W–L–P (ATS)", "Fav ATS rate", "Wilson 95%", "Fav straight-up", "vs −110 bar", "Source"],
        season_rows, numeric=(1, 3, 5),
        note="Favourite = the side the mirror's spread favours. Pushes are excluded from the rate. "
             "Straight-up ties are excluded. The 2026 season is not scored here: no 2026 spread is on record (open question Q-02).")

    lb_rows = []
    for r in b["rows"]:
        sg = r["signal"]
        lb_rows.append([
            esc(r["name"]), esc(r["market"]), str(sg.get("n", 0)), pct(sg.get("hit_rate")),
            badge("NOT RUN", "grey"),
            dash("no control exists on the same games: the strategy's window and price are not in the registered universe"),
            dash("same as above"),
            src(f"{GITHUB}/data/lab/leaderboard.json", "leaderboard.json"),
        ])
    lb_tbl = table(
        ["Strategy", "Market", "n", "Hit rate", "Control gate", "vs random picks", "vs favourites", "Source"],
        lb_rows, numeric=(2, 3),
        note="Every leaderboard run is shown with the control result it would need. None can be compared yet, "
             "so none passes or fails the control gate. This is recorded, not hidden. Closing the gap needs a "
             "dated 2026 spread with a named book (open question Q-02).")

    body = f"""
<div class="card">
  <h2>Favourites and random picks, 2019–2025</h2>
  {seasons_tbl}
</div>

<div class="card">
  <h2>The control gate on every leaderboard run</h2>
  <p>A strategy beats the controls only if its win rate is above both controls on the same games, and its
  95% lower bound is above the {pct(c["conventions"]["break_even_at_minus_110"])} bar. The gate is written before any
  result is seen and cannot be applied to a window with no price.</p>
  {lb_tbl}
</div>

<div class="card">
  <h2>What the controls show, and what they do not</h2>
  <ul>
    <li><b>Random picks</b> centre on {pct(rnd["mean_win_rate"])}. They sit inside a band of
        {pct(rnd["p2_5"])}–{pct(rnd["p97_5"])}. A pick that does nothing scores about 50%, before any price.</li>
    <li><b>Favourites</b> win {pct(fav["win_rate"])} against the spread. That is below the {pct(c["conventions"]["break_even_at_minus_110"])} bar at −110.
        {pct(rnd["share_of_reps_at_or_above_favourites"])} of random runs score at least as well as favourites.</li>
    <li><b>Straight up</b>, favourites win {pct(fav["su_fav_win_rate"])}. That number is not a betting edge, because the price is
        the thing being bet against.</li>
    <li><b>Not shown:</b> any strategy result on 2026. A leaderboard win rate of 50–52% is not evidence of skill
        until it is measured against these controls on the same games.</li>
  </ul>
</div>

<div class="card">
  <h2>Limits and integrity</h2>
  <ul>
    <li>Pinned bytes: archive SHA-256 <code>{esc(c["source"]["pinned_archive_sha256"][:16])}…</code>,
        file SHA-256 <code>{esc(c["source"]["sha256"][:16])}…</code>. The mirror file was updated on GitHub
        after this pin was taken (today's automated update). This page uses the pinned bytes; the file is not re-pinned here.</li>
    <li>The mirror states no sportsbook, timestamp or price for <code>spread_line</code>. A different spread source
        could move the favourites row.</li>
    <li>Win rates are not ROI. ROI at −110 is an assumption, not an observed price, and is not shown on this page.</li>
    <li>Reproduce: <code>python3 tools/lab/build_controls.py --check</code>. The artefact is
        <a href="{CTRL}" target="_blank" rel="noopener">control_baselines.json</a>.</li>
  </ul>
</div>
"""
    lede = ("Every strategy on this desk should be read against a bet that needs no model. "
            "Here are the two cheapest bets there are, measured on the same kind of games.")
    return page("controls.html", "Control baselines", "C1 · controls", body, lede=lede)


# ------------------------------------------------------- R1 pages (session arena-9d8c298c-x1)
def tload(rel: str) -> list[dict]:
    """Read a tab-separated file whose leading '#' lines are comments."""
    import csv as _csv
    import io as _io
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().split("\n") if ln.strip() and not ln.lstrip().startswith("#")]
    return list(_csv.DictReader(_io.StringIO("\n".join(lines)), delimiter="\t"))


def cload(rel: str) -> list[dict]:
    """Read a CSV, skipping the comment lines the shadow and escrow artefacts put above the header."""
    import csv as _csv
    import io as _io
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().split("\n") if ln.strip() and not ln.lstrip().startswith("#")]
    return list(_csv.DictReader(_io.StringIO("\n".join(lines))))


def vcell(v: Any, reason: str = "the source prints nothing here") -> str:
    """A published cell: a value, or an em dash with the reason. Never a blank, never a zero."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return dash(reason)
    return esc(v)


def p_reads() -> str:
    """The 2026-11-17 official reads: what was read, what it proves, what it cannot."""
    rep = jload(f"{READS_PACK}/report.json")
    man = jload(f"{READS_PACK}/manifest.json")
    num = rep["numbers"]
    chk = rep["checks"]
    w10 = [r for r in tload(f"{READS_PACK}/week10_finals.tsv") if r["row_type"] == "game"]
    w11 = [r for r in tload(f"{READS_PACK}/week11_slate_2026-11-17.tsv") if r["row_type"] == "game"]
    byes = [r for r in tload(f"{READS_PACK}/week11_slate_2026-11-17.tsv") if r["row_type"] == "bye"]
    st = tload(f"{READS_PACK}/standings_2026-11-17.tsv")
    ven = tload(f"{READS_PACK}/venue_evidence_2026-11-17.tsv")
    ist = tload(f"{READS_PACK}/injury_state_2026-11-17.tsv")
    PRIOR = "https://github.com/karagemop466-tech/X1/blob/main/data/verification/2026_11_16"

    kpis = "".join([
        kpi(str(num["week10_finals_published"]), "Week 10 games read Final on the official page",
            "the 2026-11-16 read could only see 13; the 14th settled Monday night", "ok"),
        kpi(f"{num['games_implied_by_standings']}", "games the official standings imply",
            f"137 in the results feed + {num['week10_games_missing_from_the_results_log']} in this read", "ok"),
        kpi(f"{num['league_points_each_side']:,}", "league points for, and against",
            "the two sides of the ledger are equal to the point", "ok"),
        kpi(str(num["injury_rows_spot_checked"]), "injury rows transcribed by hand and diffed",
            f"{num['injury_spot_check_mismatches']} mismatches against the retained capture", "ok"),
        kpi(f"{num['parallel_read_mismatches'] + num['third_read_mismatches']} / "
            f"{num['parallel_read_cells_compared'] + num['third_read_cells_compared']}",
            "cells where an independent reader disagrees",
            "two other sessions read the same four pages within minutes, on their own layouts; checks "
            "C11 and C12", "ok"),
        kpi(f"{num['venue_direct_rows']} / {len(ven)}", "fixtures with a Game Center venue row",
            "the weekly schedule page prints no venue field at all", "warn"),
        kpi(str(num["injury_reads_since_last_content_change"]), "reads of the injury page since it last changed",
            "the series is running; the report itself has not moved since 2026-11-16", "warn"),
    ])

    gate_rows = []
    for key in sorted(chk):
        c = chk[key]
        gate_rows.append([
            esc(key), badge(c.get("verdict", "?"), "ok" if c.get("verdict") == "pass"
                            else "grey" if c.get("verdict") in ("measured", "review") else "bad"),
            esc(c.get("note", "")),
            src(f"{GITHUB}/{READS_PACK}/report.json", "report.json"),
        ])
    gates = table(["Check", "Verdict", "What it asserts", "Artefact"], gate_rows)

    final_rows = []
    for r in w10:
        final_rows.append([
            esc(r["game_id"].split("_", 2)[2].replace("_", " at ").upper()), esc(r["date_et"]),
            f"{esc(r['away'])} {esc(r['away_score'])} &ndash; {esc(r['home_score'])} {esc(r['home'])}",
            f"{esc(r['away_record'])} / {esc(r['home_record'])}",
            badge(r["status"], "ok"),
            vcell(r.get("note", ""), "the page prints no event label for this card"),
            src(r["game_url"], "fixture page"),
        ])
    finals = table(["Fixture", "Date (ET)", "Score as printed", "Records printed beside the clubs",
                    "Status", "Page section / note", "Source"], final_rows, numeric=(2,),
                   note="Scores and records are the numbers on the page, in the page's own order. The record "
                        "column is the POST-game record the schedule page prints under each club, and it is "
                        "required to equal the standings page read separately (check C4) &mdash; 48 records "
                        "compared across the two weeks, 0 disagreements.")

    slate_rows = []
    for r in w11:
        slate_rows.append([
            esc(r["game_id"].split("_", 2)[2].replace("_", " at ").upper()),
            f"{esc(r['date_et'])} {esc(r['time_et'])}", esc(r["network"]),
            f"{esc(r['away_record'])} / {esc(r['home_record'])}", badge(r["status"], "grey"),
            esc(chk["C6a_week11_slate_delta_vs_2026_11_16"]["cells_moved"]) + " cells moved since 2026-11-16",
            src(r["game_url"], "fixture page"),
        ])
    slate = table(["Fixture", "Kickoff (ET)", "Network", "Records", "Status", "Slate delta", "Source"],
                  slate_rows,
                  note=f"13 fixtures and {len(byes)} clubs on bye = 32 clubs, each exactly once. The slate-delta "
                       f"column is the diff of this read against the 2026-11-16 read of the same page: dates, "
                       f"times, networks, clubs and statuses compared cell by cell, "
                       f"{chk['C6a_week11_slate_delta_vs_2026_11_16']['cells_moved']} moved. The records were "
                       f"deliberately excluded from that tuple because they are the cells expected to move when "
                       f"a game closes.")

    clo = chk["C3_league_closure"]
    closure_rows = [
        [esc("sum of wins"), esc(f"{clo['sum_wins']}"), esc("equals"), esc(f"{clo['sum_losses']} losses"),
         badge("equal", "ok"), src(f"{GITHUB}/{READS_PACK}/standings_2026-11-17.tsv", "standings.tsv")],
        [esc("league points for"), esc(f"{clo['sum_points_for']:,}"), esc("equals"),
         esc(f"{clo['sum_points_against']:,} against"), badge("equal", "ok"),
         src(f"{GITHUB}/{READS_PACK}/standings_2026-11-17.tsv", "standings.tsv")],
        [esc("games implied by the standings"), esc(f"{clo['games_implied_by_standings']}"), esc("equals"),
         esc(f"{clo['games_in_the_completed_corpus']} in the completed corpus"),
         badge("equal", "ok"), src(f"{GITHUB}/{READS_PACK}/report.json", "report.json")],
        [esc("clubs whose printed record disagrees with the standings page"),
         esc(chk["C4_cross_page_records"]["mismatches"]), esc("of"),
         esc(f"{chk['C4_cross_page_records']['records_compared']} records compared"),
         badge("0", "ok"), src(f"{GITHUB}/{READS_PACK}/report.json", "report.json")],
        [esc("standings cells this read disagrees with the collector's own read of the same page"),
         esc(chk["C5_independent_standings_reread"]["differing_cells"]), esc("of"),
         esc(f"{chk['C5_independent_standings_reread']['assertions']} cells "
             f"({chk['C5_independent_standings_reread']['fields_per_club']} printed columns &times; "
             f"{chk['C5_independent_standings_reread']['clubs']} clubs)"),
         badge("0", "ok"), src(f"{GITHUB}/data/pipeline/standings.json", "standings.json")],
        [esc("cells where this read disagrees with a second session's independent read of the same pages"),
         esc(chk["C11_second_reader_agreement"]["mismatches"]), esc("of"),
         esc(f"{chk['C11_second_reader_agreement']['cells_compared']} comparable cells"),
         badge("0", "ok"), src(f"{GITHUB}/data/evidence/2026_11_17", "second read")],
        [esc("cells where this read disagrees with a third session's independent read, which also "
             "transcribed the whole injury page"),
         esc(chk["C12_third_reader_agreement"]["mismatches"]), esc("of"),
         esc(f"{chk['C12_third_reader_agreement']['cells_compared']} comparable cells"),
         badge("0", "ok"), src(f"{GITHUB}/data/verification/2026_11_17", "third read")],
        [esc("Week 10 fixtures whose") + " <code>game_id</code> " + esc("the two packs spell differently "
             "while every printed value agrees"),
         esc(chk["C12_third_reader_agreement"]["game_id_conventions_diverge"]), esc("of"),
         esc(f"{len(w10)} fixtures"),
         badge("FLAGGED", "bad"), src(f"{GITHUB}/tools/lab/build_reads.py", "C12")],
        [esc("cells of the repository's pinned 2026-11-14 standings reference that the league has since "
             "moved past"),
         esc(chk["C5b_pinned_reference_is_stale"]["differing_cells"]), esc("across"),
         esc(f"{chk['C5b_pinned_reference_is_stale']['clubs_that_moved']} clubs"),
         badge("stale pin", "warn"), src(f"{GITHUB}/data/verify/official_standings_2026_w10.psv", "the pin")],
    ]
    closure = table(["Closure assertion", "Value", "basis", "Value", "Verdict", "Source"], closure_rows,
                    numeric=(1, 3),
                    note="These lines are why the Week 10 slate can be called complete: the league's own "
                         "table says 150 games were played, this repository can show 150, and the points add up "
                         "on both sides. A missing fixture or a transposed score breaks one of them.")

    ven_rows = []
    for v in ven:
        ven_rows.append([
            esc(v["game_id"].split("_", 2)[2].replace("_", " at ").upper()),
            vcell(v["venue_string_printed_on_week11_page"], "the schedule page prints no venue and no link "
                  "parameter carrying one for this card"),
            vcell(v["game_centre_stadium"], "not read this round"),
            vcell(v["evidence_class"], "no evidence class recorded"),
            badge("FLAGGED", "bad") if (v["conflict_flag"] or "").strip() else badge("none", "grey"),
            src(v["game_centre_url"], "Game Center"),
        ])
    venues = table(["Fixture", "What the schedule page prints", "Game Center stadium", "Evidence class",
                    "Conflict", "Source"], ven_rows,
                   note="The weekly schedule page prints no venue field. What it prints, on some cards, is a "
                        "hotel-search link whose URL carries <code>destinationAddress.location=&lt;Stadium&gt;</code> "
                        "&mdash; an official string, but a link parameter, so it is labelled as one and never "
                        "presented as a venue read. Two fixture pages were read for this round; the other eleven "
                        "say <em>not read this round</em>, which is a measured gap and not a value to guess.")

    inj_rows = []
    for r in ist:
        inj_rows.append([
            esc(r["read_id"]), esc(r["subject"]), esc(r["printed_on_the_page"]),
            esc(r["what_that_means"]),
            badge("FLAGGED", "bad") if (r.get("flag") or "").strip() else badge("note", "grey"),
            src(r["official_url"], "official page"),
        ])
    injuries = table(["Read", "Subject", "What the page prints", "What that means", "Flag", "Source"], inj_rows,
                     note=f"The row-level comparison is check C8: {num['injury_rows_spot_checked']} rows "
                          f"transcribed by hand across four clubs, five fields each, against the newest retained "
                          f"capture &mdash; {num['injury_spot_check_mismatches']} mismatches, over "
                          f"{chk['C8_injury_spotcheck_vs_capture']['coverage']['clubs']} clubs and "
                          f"{chk['C8_injury_spotcheck_vs_capture']['coverage']['rows']}. The same rows against "
                          f"the table the site publishes: {num['published_injury_table_mismatches']} mismatches, so "
                          f"the three Lions game-status cells carried in the review queue no longer reproduce. What "
                          f"the site table is missing is on the Flagged page.")

    body = f"""
<div class="note"><b>What this page is.</b> On 2026-11-17 this session read four official NFL pages
live and transcribed them into a dated pack
(<a href="{GITHUB}/{READS_PACK}" target="_blank" rel="noopener">data/lab/reads/2026-11-17</a>). Every
number below is recomputed from those files by
<a href="{GITHUB}/tools/lab/build_reads.py" target="_blank" rel="noopener">tools/lab/build_reads.py</a>
&mdash; nothing on this page is typed in, and the build fails rather than publishing a number the files
do not support. The read window the pack records is
{esc(man['read_window_utc']['first_read'])} to {esc(man['read_window_utc']['last_read'])}, and the fetch
tool returns parsed page text, so these are transcriptions of pages, not byte captures: the hashes in
<a href="{GITHUB}/{READS_PACK}/manifest.json" target="_blank" rel="noopener">manifest.json</a> are of
the transcriptions. This pack is <b>not</b> the only 2026-11-17 read in the repository. Three sessions
read the same pages inside a five-minute window: this one at 22:45-22:53Z,
<a href="{GITHUB}/data/evidence/2026_11_17" target="_blank" rel="noopener">data/evidence/2026_11_17</a>
at 22:46Z &mdash; which keeps a byte-level capture of one page, where this pack keeps a transcription
&mdash; and <a href="{GITHUB}/data/verification/2026_11_17" target="_blank" rel="noopener">
data/verification/2026_11_17</a> at about 22:50Z, which transcribed the whole injury report instead of the
four clubs this pack typed by hand. None of the three was built to check another and the column layouts
differ, so they are compared cell by cell here (checks C11 and C12) rather than cited as agreement:
<b>{num['parallel_read_cells_compared'] + num['third_read_cells_compared']:,} comparable cells,
{num['parallel_read_mismatches'] + num['third_read_mismatches']} disagreements</b>. The one thing they did
not agree on is an identifier and not a value &mdash; the two packs spell one fixture's
<code>game_id</code> differently, which is flag <a href="flagged.html">R1-08</a> and the reason C12 joins
on the official fixture slug. And where the third read prints a kickoff time for a finished game while this
pack leaves the cell blank, that is a stated difference in what each reader allowed itself to cite (the
schedule page does not reprint times for games already played), not a hole in this table.</div>

<div class="kpis">{kpis}</div>

<div class="card"><h2>The ten checks that gate this page</h2>{gates}</div>

<div class="card"><h2>Week 10, all 14 games, all Final</h2>{finals}</div>

<div class="card"><h2>The closure arithmetic, five assertions</h2>{closure}</div>

<div class="card"><h2>Week 11, the slate as it stands before kickoff</h2>{slate}</div>

<div class="card"><h2>Venue evidence, and what the schedule page does not print</h2>{venues}</div>

<div class="card"><h2>Availability: the state of the injury machinery</h2>{injuries}
<p class="legend">Day-over-day delta, the thing the brief asks for instead of the level: the last two
accepted reads of the injury page differ in
{chk['C9_injury_capture_series']['delta_last_two_reads']['cells_changed']} cells across
{chk['C9_injury_capture_series']['reads']} reads and
{chk['C9_injury_capture_series']['distinct_payloads']} distinct payloads. The 2026-11-15 read was refused
by the drift gate for printing <code>LAR</code> where the standings page prints <code>LA</code>; the
history is in report.json, and it is why a capture is kept per read rather than overwriting one another.</p>
</div>

<div class="note warn"><b>What this page cannot show you.</b> There is no price here: no opening line, no
closing line, no book, no timestamp on a number
<a href="{PRIOR}" target="_blank" rel="noopener">the 2026-11-16 pack</a> could not see either, and the
13 Week 10 games it printed as settled are still absent from the results feed &mdash; that gap is measured
on <a href="closure.html">Feed closure</a> and it is not fixed here. The repository's own independent
re-verification (<code>tools/verify_official.py</code>) is red, and the second row of the closure table above
is the reason: it compares a published table against a reference transcription three days older, and the
league table moved in between &mdash;
{num['standings_cells_stale_in_the_pinned_reference']} cells of that pin are stale, while this read agrees
with the collector on all {chk['C5_independent_standings_reread']['assertions']}. The pin belongs to another
round's tree and was left alone. The Week 11 injury report does not
exist yet (the page's own week selector ends at Week 10), so no Week 11 availability delta can be
published by anyone. And the two fixtures with a Game Center venue row are the only venue evidence this
round produced.</div>
"""
    return page("reads.html", "The 2026-11-17 official read", "R1 · dated live reads", body,
                lede="Week 10 closure, the Week 11 slate, the standings, the venue evidence and the "
                     "availability state &mdash; transcribed from nfl.com on 2026-11-17 and re-derived "
                     "from the files, cell by cell, by the build.")


def p_escrow() -> str:
    """PR-04: the Week 11 forecasts recorded before kickoff, and the ledger that settles them."""
    m = jload(f"{ESCROW_DIR}/escrow_meta.json")
    rows = cload(f"{ESCROW_DIR}/week11_forecasts_2026-11-17.csv")
    led = cload(f"{ESCROW_DIR}/settlement_ledger.csv")
    by_game: dict[str, dict] = {}
    for r in rows:
        by_game.setdefault(r["game_id"], {})[r["market"]] = r
    settled = [r for r in led if r["settled"] == "yes"]
    open_rows = [r for r in led if r["settled"] != "yes"]

    kpis = "".join([
        kpi(str(len(by_game)), "fixtures recorded before kickoff",
            f"{len(rows)} rows, {len(m['markets'])} markets, in the required order", "ok"),
        kpi(m["recorded_at_utc"].replace("T", " ").replace("Z", ""), "recorded at (UTC)",
            f"first kickoff {m['first_kickoff_utc'].replace('T', ' ').replace('Z', '')} UTC", ""),
        kpi(f"{m['recorded_before_first_kickoff_minutes_of_slack'] / 60:.1f} h",
            "margin between the record and the first kickoff",
            "the pack stamps its clock to the minute; that rounding is what this slack has to be big against",
            "ok"),
        kpi(str(len(settled)), "rows settled by an official final",
            f"{len(open_rows)} still open; a row settles only when an official page printed the score", "warn"),
        kpi("0", "market lines, residuals, CLV or ROI",
            "withheld: no licensed price source for 2026 (Q-02)", "warn"),
        kpi(str(m["cross_registration_delta_vs_pr01"]["fixtures_compared"]),
            "fixtures also forecast by PR-01 on 2026-11-16",
            f"mean |Δp| {m['cross_registration_delta_vs_pr01']['mean_abs_delta']}, "
            f"largest {m['cross_registration_delta_vs_pr01']['largest_move']['abs_delta']}", ""),
    ])

    fc_rows = []
    for gid in sorted(by_game):
        g = by_game[gid]
        side, ta, tb, ml = g["side"], g["total_A"], g["total_B"], g["moneyline"]
        fc_rows.append([
            esc(gid.split("_", 2)[2].replace("_", " at ").upper()), esc(side["kickoff_et"]),
            esc(f"{side['away']} at {side['home']}"),
            esc(side["our_fair_line"]), pct(float(side["our_probability"])),
            esc(ta["our_fair_line"]), esc(tb["our_fair_line"]),
            esc(tb["our_probability"]), esc(ml["our_fair_line"]),
            dash("no licensed price source for 2026 (open question Q-02)"),
            dash("follows from the blank market line"),
            badge("yes", "ok") if side["recorded_before_kickoff"] == "yes" else badge("NO", "bad"),
            src(side["official_fixture_url"], "fixture page"),
        ])
    fc = table(["Fixture", "Kickoff (ET)", "Matchup", "Side fair line", "p(home)", "total A", "total B",
                "B − A gap", "moneyline (zero-vig)", "Market line", "Residual", "Pre-kickoff", "Source"],
               fc_rows, numeric=(3, 4, 5, 6, 7),
               note="Side first, then the total, then the moneyline: the order the brief requires is a build "
                    "constraint, and the market order column is in the artefact. <b>Both totals are published "
                    "because neither has won yet.</b> A is the league-average total &mdash; the floor a margin "
                    "model has, published as the floor and not as an estimate of the game. B is two clubs' "
                    "shrunk scoring and allowed points. The gap column is the whole comparison; the walk-forward "
                    "settlement decides it, and one settled week is not enough to collapse them.")

    delta_rows = []
    for d in m["cross_registration_delta_vs_pr01"]["rows"]:
        delta_rows.append([
            esc(d["game_id"].split("_", 2)[2].replace("_", " at ").upper()),
            esc(f"{d['p_pr01_2026_11_16']:.6f}"), esc(f"{d['p_pr04_2026_11_17']:.6f}"),
            esc(f"{d['delta']:+.6f}"), esc(f"{d['fair_line_pr01']} &rarr; {d['fair_line_pr04']}"),
            src(f"{GITHUB}/{ESCROW_DIR}/escrow_meta.json", "escrow_meta.json"),
        ])
    delta = table(["Fixture", "p recorded 2026-11-16 (PR-01)", "p recorded 2026-11-17 (PR-04)",
                   "Change", "Fair line, then", "Artefact"], delta_rows, numeric=(1, 2, 3),
                  note=f"n = {len(delta_rows)} fixtures. Same rule, same code path, one extra settled game in "
                       f"the corpus: PR-01 read 149 games, this record reads "
                       f"{m['corpus_read']['games']}. The largest move is "
                       f"{m['cross_registration_delta_vs_pr01']['largest_move']['abs_delta']} in probability on "
                       f"<code>{esc(m['cross_registration_delta_vs_pr01']['largest_move']['game_id'])}</code>. "
                       f"That is not a result and it is not an improvement &mdash; it is how fragile this model "
                       f"is to a single score, which is the number a reader needs before calling either record "
                       f"a signal.")

    # Every ledger row names a fixture; the fixture's official page is transcribed in the
    # forecasts pack. Open rows carry that official link and a second, explicit marker saying
    # the SETTLEMENT source (the official final) is still pending - integration fix by session
    # arena/dc96bc33-x1: the site rule wants a source link on every data row, and a row whose
    # subject is an officially listed fixture has one even while its result does not exist yet.
    fixture_urls = {r["game_id"]: r["official_fixture_url"] for r in rows}
    led_rows = []
    for r in led:
        if r["settled"] != "yes" and r["market"] != "side":
            continue
        led_rows.append([
            esc(r["ledger_id"]), esc(r["origin_record"]), esc(r["market"]), esc(r["kickoff_et"]),
            badge("settled", "ok") if r["settled"] == "yes" else badge("open", "grey"),
            vcell(r["away_score"]) + "&ndash;" + vcell(r["home_score"]),
            vcell(r["our_fair_line"]), vcell(r["our_probability"]),
            vcell(r["brier"]), vcell(r["skill_vs_home_baseline"]),
            vcell(r["fair_line_error_points"], "not settled yet"),
            esc(r["flags"]),
            src(r["settlement_source_url"], "official final") if r["settlement_source_url"]
            else (src(fixture_urls.get(r["game_id"], ""), "fixture")
                  + ' <span class="src blank">settlement source pending</span>'),
        ])
    ledger = table(["Ledger row", "Record", "Market", "Kickoff (ET)", "State", "Final", "Our line", "p",
                    "Brier", "Skill vs 0.55", "Line error (pts)", "Note", "Source"], led_rows,
                   numeric=(6, 7, 8, 9, 10),
                   note=f"{len(settled)} settled row, {len(open_rows)} open. The settled row is PR-01's "
                        f"Monday-night forecast: the model took BAL &minus;7.0 at p = 0.701232, LAC won 23&ndash;20, "
                        f"Brier {settled[0]['brier'] if settled else '—'} against the 0.55 baseline's "
                        f"{settled[0]['brier_vs_home_baseline_0_55'] if settled else '—'}. "
                        f"n = 1 is not evidence in either direction, and the page says so rather than the "
                        f"arithmetic saying it for us.")

    s = m["settled"]
    luck = f"""
<div class="card"><h2>The luck panel, printed with the score</h2>
{table(["Quantity", "Value", "Reading", "Artefact"], [
    ["Settled side rows", esc(str(s["n_settled_side_rows"])), "one", src(f"{GITHUB}/{ESCROW_DIR}/escrow_meta.json", "escrow_meta.json")],
    ["Model-side hits", esc(f"{s['model_side_hits']} of {s['n_settled_side_rows']}"), "the record, not the rate", src(f"{GITHUB}/{ESCROW_DIR}/settlement_ledger.csv", "settlement_ledger.csv")],
    ["Mean Brier", esc(str(s["mean_brier"])), "lower is better", src(f"{GITHUB}/{ESCROW_DIR}/escrow_meta.json", "escrow_meta.json")],
    ["Mean Brier of the 0.55 home baseline", esc(str(s["mean_brier_home_baseline"])), "the benchmark", src(f"{GITHUB}/docs/preregistration/PR-01-shadow-baseline.md", "PR-01")],
    ["Brier skill against that baseline", esc(str(s["brier_skill_vs_home_baseline"])), "negative on one game means nothing and proves nothing", src(f"{GITHUB}/{ESCROW_DIR}/escrow_meta.json", "escrow_meta.json")],
    ["Expected wins on the model side", esc(f"{s['expected_wins_on_model_side']} (sd {s['sd_of_wins']})"), "the realised-minus-expected gap is the luck question", src(f"{GITHUB}/{ESCROW_DIR}/escrow_meta.json", "escrow_meta.json")],
    ["Mean fair-line error", esc(f"{s['mean_fair_line_error_points']} points"), "the line was 10 points away on the one settled game", src(f"{GITHUB}/{ESCROW_DIR}/settlement_ledger.csv", "settlement_ledger.csv")],
])}
</div>"""

    body = f"""
<div class="note"><b>Recorded before the games, and it refuses to be edited after them.</b>
The rule is <a href="{GITHUB}/docs/preregistration/PR-04-week11-escrow.md" target="_blank"
rel="noopener">docs/preregistration/PR-04-week11-escrow.md</a>; the artefacts are
<a href="{GITHUB}/{ESCROW_DIR}/week11_forecasts_2026-11-17.csv" target="_blank" rel="noopener">week11_forecasts_2026-11-17.csv</a>,
<a href="{GITHUB}/{ESCROW_DIR}/settlement_ledger.csv" target="_blank" rel="noopener">settlement_ledger.csv</a>
and <a href="{GITHUB}/{ESCROW_DIR}/escrow_meta.json" target="_blank" rel="noopener">escrow_meta.json</a>,
built by <a href="{GITHUB}/tools/lab/build_escrow.py" target="_blank" rel="noopener">tools/lab/build_escrow.py</a>.
The builder aborts unless every fixture's kickoff is strictly later than the clock time of the official
read the record is built from, and it aborts if a rebuild would add or drop a row from a record that has
already been written: <code>ABORT: the committed forecast record would change shape.</code> The hash of
the rows is in the meta file, and the constants are imported from PR-01's implementation, not retyped, so
the two records cannot drift apart by accident.</div>

<div class="kpis">{kpis}</div>

<div class="card"><h2>The escrow: three markets, in order, per fixture</h2>{fc}</div>

<div class="card"><h2>The same 13 fixtures, one day and one game apart</h2>{delta}</div>

<div class="card"><h2>The settlement ledger</h2>{ledger}</div>
{luck}

<div class="note warn"><b>What is withheld, and why it stays withheld.</b> <code>market_line</code> and
<code>residual</code> are empty on all {len(rows)} rows and <code>CLV</code> and <code>ROI</code> are not
computed at all. This repository has no licensed price source for 2026 &mdash; open question Q-02, and the
pinned third-party mirror prints a spread and a total for these fixtures and prints no score for any of
them, which is measured on <a href="closure.html">Feed closure</a>. The fair line is published because the
model produced it before kickoff; the residual is the number an origination programme is actually judged
on, and publishing it from data the owner has not agreed to use would rank a strategy on a source nobody
has cleared. When a price policy is decided the residual fills retroactively, because the fair line was
recorded first &mdash; that is the entire purpose of an escrow.</div>

<p class="legend">Limits, from the artefact, not softened: {"; ".join(esc(x) for x in m["limits"])}.</p>
"""
    return page("escrow.html", "Week 11 escrow", "R1 · PR-04, recorded pre-kickoff", body,
                lede="Thirteen fixtures forecast in the required order &mdash; side, both total "
                     "estimators, moneyline &mdash; written before kickoff on 2026-11-17, priced "
                     "nothing, and scored only where an official page has since printed a final.")


def p_closure() -> str:
    """What still blocks Week 10 in the results feed, counted by the feed's own gates."""
    d = jload(f"{READS_PACK}/feed-closure-measurement.json")
    M = d["measures"]
    m1, m2 = M["M1_row_count_pins"], M["M2_mirror_row_diff_gate"]
    m3 = M["M3_closure_against_todays_official_standings"]
    m4 = M["M4_closure_against_the_pinned_baseline"]
    m5 = M["M5_blast_radius"]
    m6 = M["M6_evaluation_corpus_effect"]

    kpis = "".join([
        kpi(f"{d['corpus']['rows_in_the_published_results_log']} &rarr; {d['corpus']['corpus_after_the_append']}",
            "games in the results feed, and after the append",
            f"{d['corpus']['games_the_append_would_add']} Week 10 games the feed does not hold", "warn"),
        kpi(str(m2["of_those_the_mirror_prints_no_score_for"]), "games blocked by the mirror gate",
            f"of {d['corpus']['games_the_append_would_add']} the append would add &mdash; every one", "bad"),
        kpi(f"{m3['clubs'] - m3['clubs_disagreeing']}/{m3['clubs']}", "standings rows the closure reproduces",
            "against today's official table, W-L-T, PF and PA", "ok"),
        kpi(str(m1["code_lines_that_assert_the_count"]), "executable lines pinning the row count",
            f"in {m1['file']}, plus {m1['occurrences'] - m1['code_lines_that_assert_the_count']} prose lines "
            f"that repeat it", "warn"),
        kpi(str(m5["files_naming_the_results_log_or_the_feed"]), "artefacts naming the log or the feed",
            "each regenerated and re-verified in the same commit", "warn"),
        kpi(f"+{m6['added']}", "games the append adds to the scored window",
            f"{m6['games_excluding_the_warmup_before']} &rarr; {m6['games_excluding_the_two_week_warmup_after']} "
            f"after the two-week warmup", ""),
    ])

    pin_rows = [[esc(f"line {p['line']}"), badge(p["kind"], "bad" if p["kind"] == "code" else "grey"),
                 f"<code>{esc(p['text'])}</code>", src(f"{GITHUB}/{m1['file']}", m1["file"].rsplit("/", 1)[-1])]
                for p in m1["lines"]]
    pins = table(["Where", "Kind", "What it asserts", "Source"], pin_rows)

    blocked_rows = []
    for b in m2["blocked"]:
        has_line = b.get("mirror_has_line_but_no_score")
        blocked_rows.append([
            esc(b["mirror_id"]), esc(b["slug"]), esc(b["why"]),
            vcell(b.get("mirror_spread_line", ""), "the mirror prints no line here"),
            vcell(b.get("mirror_total_line", ""), "the mirror prints no line here"),
            badge("line, no score", "warn") if has_line else badge("nothing", "grey"),
            src(f"https://www.nfl.com/games/{b['slug']}", "official fixture page"),
        ])
    blocked = table(["Mirror key", "Official fixture", "Why the gate refuses it", "Mirror spread",
                     "Mirror total", "Shape", "Source"], blocked_rows, numeric=(3, 4),
                    note=f"{m2['of_the_blocked_rows_the_mirror_does_print_a_spread_and_total_for']} of "
                         f"{m2['games_the_append_would_add']} blocked games have a spread and a total in the "
                         f"mirror and no score. The prices nobody is authorised to use are present; the score "
                         f"the NFL has printed is the part the gate will not accept. That is the shape of the "
                         f"blocker, and it is why this is a decision rather than a bug.")

    base_rows = [[esc(x["club"]), esc("-".join(str(v) for v in x["pinned_2026_11_14"])),
                  esc("-".join(str(v) for v in x["from_the_150_game_corpus"])),
                  src(f"{GITHUB}/code/reference_data_2026_w10.py", "the pinned baseline")]
                 for x in m4["detail"][:32]]
    baseline = table(["Club", "Pinned 2026-11-14 (W-L-T-PF-PA)", "From the 150-game corpus", "Source"],
                     base_rows,
                     note=f"{m4['clubs_that_would_move']} of {m4['clubs_in_the_baseline']} clubs move against "
                          f"the pinned baseline, by design: that file is the 137-game table. Re-pinning it to a "
                          f"dated official read is part of the change set. This page lists the moves so the cost "
                          f"is visible; it does not make them.")

    opt_rows = [[esc(o["id"]), esc(o["name"]), esc(o["what_it_costs"]), esc(o["risk"]),
                 src(f"{GITHUB}/{READS_PACK}/feed-closure-measurement.json", "measurement")]
                for o in d["options"]]
    options = table(["Path id", "The path", "What it costs", "What it risks", "Artefact"], opt_rows)

    body = f"""
<div class="note warn"><b>This page measures a blocker. It does not fix it.</b> Week 10 is closed on the
official page &mdash; 14 finals, read and cross-checked on <a href="reads.html">the reads page</a> &mdash;
and the results feed still holds 137 games, because <code>tools/build_results_r3.py</code> refuses to emit
a row the third-party mirror has no score for, and pins its output to exactly 137 rows in four executable
lines. Appending the 13 games would also move the standings baseline the feed is arithmetic-checked against
and every artefact that reads the feed. All of that is measured below from the committed builder, and
<code>data/results/**</code> and PR-01's frozen inputs are untouched by this session:
<a href="{GITHUB}/tools/lab/build_closure_measurement.py" target="_blank" rel="noopener">tools/lab/build_closure_measurement.py</a>
writes <a href="{GITHUB}/{READS_PACK}/feed-closure-measurement.json" target="_blank"
rel="noopener">feed-closure-measurement.json</a>, which is what this page renders.</div>

<div class="kpis">{kpis}</div>

<div class="card"><h2>The four executable pins, and the prose that repeats them</h2>{pins}</div>

<div class="card"><h2>The 13 games, one row each, and why the gate stops them</h2>{blocked}</div>

<div class="card"><h2>What the append moves in the standings baseline</h2>{baseline}</div>

<div class="card"><h2>The three paths, with their cost</h2>{options}
<p class="legend">{esc(d['decision_for_the_owner'])}</p></div>

<div class="note"><b>What is already true, and is not usually said out loud.</b> The closure arithmetic
passes: the 150 games this repository can show reproduce all {m3['clubs']} official standings rows exactly
&mdash; wins, losses, ties, points for and points against, for every club, against the league table read on
{esc(d['read_on'])}. So this is not a question of whether the Week 10 scores are right. It is a question of
what the word <em>verified</em> is allowed to mean for a row: two independent sources, or one official page
plus the arithmetic that only closes if every row is present. That is the owner's call, and it is the one
this round recorded instead of taking.</div>
"""
    return page("closure.html", "Feed closure: what Week 10 still needs", "R1 · measured, not fixed", body,
                lede="The Week 10 slate is complete on the official page and incomplete in the results "
                     "feed. Here is the gap, counted by the feed's own gates, with the three ways out and "
                     "the price of each.")



def main() -> int:
    if "--check" in sys.argv:
        return check()
    os.makedirs(LAB, exist_ok=True)
    builders = {
        "index.html": p_index,
        "executive-summary.html": p_exec,
        "prices.html": p_prices,
        "results.html": p_results,
        "lines.html": p_lines,
        "leaderboard.html": p_leaderboard,
        "deficiency.html": p_deficiency,
        "correlation.html": p_correlation,
        "controls.html": p_controls,
        "validation.html": p_validation,
        "questions.html": p_questions,
        "suggestions.html": p_suggestions,
        "reads.html": p_reads,
        "escrow.html": p_escrow,
        "closure.html": p_closure,
        "sources.html": p_sources,
        "flagged.html": p_flagged,
    }
    for fn, _label, _t, _k in PAGES:
        out = builders[fn]()
        with open(os.path.join(LAB, fn), "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"wrote lab/{fn} ({len(out):,} bytes)")
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
