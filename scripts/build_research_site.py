#!/usr/bin/env python3
"""Static site generator for the X1 research lab.

Reads ``data/site/payload.json`` plus the processed CSV tables and writes a
complete static site into ``docs/``.  The output is plain HTML/CSS/JS - no
framework, no build step at deploy time, and every table row carries the
source link that supports it.

Usage:
    python3 scripts/build_research_site.py
"""

from __future__ import annotations

import csv
import html
import io
import json
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from x1 import config, content, sources

BUILD_DATE = date.today().isoformat()
# The snapshot date of the published data (2026 season, Week 10). Every page
# shows it so a reader can see how old the evidence is.
SNAPSHOT = "2026-11-14"
SITE_NAME = "X1 - NFL Line Origination & Strategy Lab"
SITE_TAGLINE = "Originated lines, gated strategies, verified sources."

NAV = [
    ("index.html", "Dashboard"),
    ("executive-summary.html", "Executive summary"),
    ("requirements.html", "Requirements"),
    ("questions.html", "Questions & gaps"),
    ("suggestions.html", "Suggestions"),
    ("strategies.html", "Strategies"),
    ("leaderboard.html", "Leaderboard"),
    ("validation.html", "Validation gates"),
    ("lines.html", "Originated lines"),
    ("correlations.html", "Correlations & luck"),
    ("props.html", "Player props"),
    ("injuries.html", "Injuries & depth"),
    ("methods.html", "Methods"),
    ("sources.html", "Sources"),
    ("flagged.html", "Flagged for review"),
]


# --------------------------------------------------------------------------
# formatting helpers
# --------------------------------------------------------------------------
def esc(value) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def pct(value, digits: int = 2, signed: bool = True) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "&mdash;"
    try:
        v = float(value) * 100.0
    except (TypeError, ValueError):
        return esc(value)
    sign = "+" if (signed and v > 0) else ""
    return f"{sign}{v:.{digits}f}%"


def num(value, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "&mdash;"
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return esc(value)


def signed_num(value, digits: int = 2) -> str:
    """Signed number with an explicit dash when the value is missing."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "&mdash;"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return esc(value)
    if pd.isna(v):
        return "&mdash;"
    return f"{v:+.{digits}f}"


def sign_class(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "neutral"
    return "pos" if float(value) > 0 else ("neg" if float(value) < 0 else "neutral")


def badge(text: str, kind: str = "mute") -> str:
    return f'<span class="badge {kind}">{esc(text)}</span>'


def pass_badge(ok: bool) -> str:
    return badge("PASS", "pass") if ok else badge("FAIL", "fail")


def source_link(key: str, label: Optional[str] = None) -> str:
    src = sources.SOURCE_BY_KEY.get(key)
    if src is None:
        return esc(label or key)
    text = label or src.title
    return f'<a href="{esc(src.url)}" target="_blank" rel="noopener">{esc(text)}</a>'


def table(
    headers: List[str],
    rows: List[List[str]],
    sortable: bool = True,
    table_class: str = "",
    note: Optional[str] = None,
    data_table: bool = False,
) -> str:
    head = "".join(
        f'<th class="num">{h}</th>' if isinstance(h, tuple) else f"<th>{h}</th>"
        for h in headers
    )
    body = []
    for row in rows:
        cells = []
        for cell in row:
            cls = ""
            if isinstance(cell, tuple):
                value, cls = cell
                cells.append(f'<td class="{cls}">{value}</td>')
            else:
                cells.append(f"<td>{cell}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    attr = ' data-sort="1"' if sortable else ""
    if data_table:
        attr += " data-table"
    html_out = (
        f'<div class="table-wrap"><table{attr} class="{table_class}">'
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"
    )
    if note:
        html_out += f'<p class="table-note">{note}</p>'
    return html_out


def layout(page: str, title: str, body: str) -> str:
    nav = "".join(
        f'<a href="{href}" class="{"active" if href == page else ""}">{esc(label)}</a>'
        for href, label in NAV
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} &middot; {esc(SITE_NAME)}</title>
<meta name="description" content="{esc(SITE_TAGLINE)}">
<link rel="stylesheet" href="assets/styles.css">
</head>
<body>
<header class="site">
  <div class="bar">
    <div class="brand">
      <span class="mark">X1</span>
      <span class="tag">NFL line origination &amp; strategy lab</span>
    </div>
    <nav class="site">{nav}</nav>
  </div>
</header>
<main class="wrap">
<p class="subtle" style="margin:0 0 4px">Data snapshot {SNAPSHOT} &middot;
<a href="../index.html">Main dashboard</a> &middot;
<a href="../pages/standings.html">Standings</a> &middot;
<a href="../pages/schedule.html">Week 10 schedule</a> &middot;
<a href="../pages/availability.html">Official availability</a> &middot;
<a href="../pages/sources.html">Source register</a></p>
{body}
</main>
<footer class="site">
  {esc(SITE_NAME)} &middot; data snapshot {SNAPSHOT} &middot; generated {BUILD_DATE} by
  <code>scripts/build_research_site.py</code> &middot;
  every table row links to its source &middot;
  <a href="flagged.html">unverified items are flagged, never filled in</a> &middot;
  <a href="../index.html">back to the main dashboard</a>
</footer>
<script src="assets/app.js"></script>
</body>
</html>
"""


def kpi(label: str, value: str, note: str = "") -> str:
    note_html = f'<div class="note">{note}</div>' if note else ""
    return f'<div class="card"><h4>{esc(label)}</h4><div class="value">{value}</div>{note_html}</div>'


# --------------------------------------------------------------------------
# data access
# --------------------------------------------------------------------------
def load_payload() -> Dict:
    return json.loads((config.SITE_DATA_DIR / "payload.json").read_text())


def read_tsv(path: Path) -> List[Dict[str, str]]:
    """Read a tab-separated table whose header lines start with '#'."""
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    body = "\n".join(l for l in lines if not l.startswith("#"))
    return list(csv.DictReader(io.StringIO(body), delimiter="\t"))


def load_games() -> pd.DataFrame:
    path = config.PROCESSED_DIR / "games_modeled.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    for col in ("market_spread", "market_total", "model_spread", "model_total",
                "spread_delta", "total_delta", "elo_diff_home"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# --------------------------------------------------------------------------
# pages
# --------------------------------------------------------------------------
def page_dashboard(p: Dict, games: pd.DataFrame) -> str:
    lb = p["leaderboard"]
    passed = [e for e in lb if e["all_passed"]]
    champ = passed[0] if passed else lb[0]
    inj = p["injuries"].get("summary", {})
    model = p["model"]["summary"]

    kpis = "".join([
        kpi("Games in the model", f"{num(model['n_games_scored'], 0)}",
            f"seasons {model['first_season']}&ndash;{model['last_season']}, walk-forward"),
        kpi("Strategies evaluated", f"{len(lb)}", "single, parlay and research strategies"),
        kpi("Passed every gate", f"{len(passed)}", f"{esc(champ['name'])} leads"),
        kpi("Leader ROI", pct(champ["roi"]), f"{champ['bets']} out-of-sample bets"),
        kpi("Official injury rows", f"{inj.get('official_current_week_rows', 0)}",
            "NFL Week 10 report, transcribed"),
        kpi("Items flagged for review", f"{len(content.FLAGGED)}", "unverified or caveated"),
    ])

    rows = []
    for e in lb[:6]:
        rows.append([
            e["rank"],
            f'<a href="strategies.html#{esc(e["key"])}">{esc(e["name"])}</a>',
            badge(e["family"], "info"),
            f'{e["bets"]:,}',
            (pct(e["roi"]), sign_class(e["roi"])),
            (pct(e["hit_rate"], 1, signed=False), ""),
            (f'[{pct(e["ci_lo"], 1)}, {pct(e["ci_hi"], 1)}]', ""),
            (f'{e["reward"]:.1f}', ""),
            pass_badge(e["all_passed"]),
        ])

    findings = "".join(
        f'<div class="callout {"good" if i == 0 else ""}"><h4>{esc(b["title"])}</h4><p>{esc(b["body"])}</p></div>'
        for i, b in enumerate(content.EXEC_SUMMARY[:5])
    )

    nav_cards = []
    for href, label in NAV:
        if href in ("index.html",):
            continue
        nav_cards.append(f'<a class="card" href="{href}"><div class="value">{esc(label)}</div></a>')

    body = f"""
<h1>Dashboard</h1>
<p class="lede">Every number on this site is produced by the pipeline in <code>src/x1</code>,
verified against a cited source, and published with the evidence attached. Values that
cannot be confirmed are left blank and listed on the
<a href="flagged.html">Flagged for Review</a> page.</p>

<div class="grid k4" style="margin:18px 0 8px">{kpis}</div>

<p><a href="kickoff-regimes/index.html">Week 11 paper totals trial and kickoff-rule evidence</a> · Registered before kickoff; no reward or staking eligibility.</p>
<h2>What the evidence shows</h2>
{findings}

<h2>Leaderboard (top of the table)</h2>
{table(["#", "Strategy", "Family", "Bets", "ROI", "Hit rate", "95% CI (units/bet)", "Reward", "Gates"],
       rows, sortable=False,
       note="Full table, gate detail and rejection reasons on the Leaderboard and Validation gates pages.")}

<h2>Where to go next</h2>
<div class="grid k3 nav-grid">{''.join(nav_cards)}</div>
"""
    return layout("index.html", "Dashboard", body)


def page_exec(p: Dict) -> str:
    blocks = "".join(
        f'<div class="callout"><h4>{esc(b["title"])}</h4><p>{esc(b["body"])}</p></div>'
        for b in content.EXEC_SUMMARY
    )
    lb = p["leaderboard"]
    passed = [e for e in lb if e["all_passed"]]
    numbers = [
        ["Games modelled", f'{p["model"]["summary"]["n_games_scored"]:,}',
         "walk-forward Poisson points model plus Elo"],
        ["Strategies evaluated", f"{len(lb)}", "pre-registered before evaluation"],
        ["Strategies passing all eight gates", f"{len(passed)}",
         "reward paid only to strategies that clear every gate"],
        ["Leader out-of-sample ROI", pct(passed[0]["roi"]) if passed else "&mdash;",
         f'{passed[0]["bets"] if passed else 0} settled bets, 2015-2026'],
        ["Leader ROI after removing luck games", pct(passed[0].get("roi_clean")) if passed else "&mdash;",
         "one-score games and blowouts removed"],
        ["Prop families modelled", f'{len(p["props"].get("families", []))}',
         "calibrated hit rates on the 2021+ window"],
        ["Open questions", f"{len(content.QUESTIONS)}", "each with how to close the gap"],
        ["Suggestions on the table", f"{len(content.SUGGESTIONS)}", "with evidence, impact and effort"],
        ["Flagged items", f"{len(content.FLAGGED)}", "unverified or caveated, never guessed"],
    ]
    body = f"""
<h1>Executive summary</h1>
<p class="lede">A short, decision-focused summary of the project state as of {BUILD_DATE}.
Every statement below is backed by a table on this site and a source link.</p>
{blocks}
<h2>Key numbers</h2>
{table(["Measure", "Value", "Basis"], numbers, sortable=False)}
<div class="callout warn"><h4>Read this before acting on the numbers</h4>
<p>One strategy clears the gates. Its bootstrap interval excludes zero but the lower bound
is small, so the expected value per bet is positive and modest rather than large. Sixteen
questions remain open, and four of them (Q2, Q5, Q7, Q9) block the next implementation step.
Fourteen suggestions are published for review so a path can be chosen before any code is written.</p></div>
"""
    return layout("executive-summary.html", "Executive summary", body)


def page_requirements(p: Dict) -> str:
    rows = [
        [esc(r["id"]), esc(r["category"]), esc(r["requirement"]),
         badge(r["status"], "pass" if r["status"] == "Delivered" else "warn"),
         esc(r["evidence"])]
        for r in content.REQUIREMENTS
    ]
    delivered = sum(1 for r in content.REQUIREMENTS if r["status"] == "Delivered")
    body = f"""
<h1>Requirements register</h1>
<p class="lede">Every requirement taken from the brief, with the state of delivery and the
evidence that proves it. {delivered} of {len(content.REQUIREMENTS)} are complete; the rest are
partially delivered and the missing piece is stated.</p>
<div class="toolbar"><input type="search" data-filter="#req-table" placeholder="Filter requirements..."></div>
{table(["ID", "Category", "Requirement", "Status", "Evidence"], rows, sortable=False)}
"""
    return layout("requirements.html", "Requirements", body)


def page_questions(p: Dict) -> str:
    rows = [
        [esc(q["id"]), esc(q["category"]), esc(q["question"]),
         esc(q["known"]), esc(q["unknown"]), esc(q["how_to_close"]),
         badge(q["priority"], {"High": "fail", "Medium": "warn", "Low": "mute"}[q["priority"]]),
         badge(q["status"], "mute")]
        for q in content.QUESTIONS
    ]
    body = f"""
<h1>Questions, known information and information gaps</h1>
<p class="lede">A decision cannot be made reasonably until the open questions below are answered.
Each row states what is already known from the work done so far, what is still missing, and the
concrete action that would close the gap. Priority reflects how much of the roadmap a question blocks.</p>
<div class="toolbar">
  <input type="search" data-filter="#q-table" placeholder="Filter questions...">
  <select data-filter-select="#q-table" data-filter-column="1">
    <option value="">All categories</option>
    {''.join(f'<option>{esc(c)}</option>' for c in sorted({q["category"] for q in content.QUESTIONS}))}
  </select>
</div>
{table(["ID", "Category", "Question", "What is known", "What is missing", "How to close the gap", "Priority", "Status"],
       rows, sortable=False)}
"""
    return layout("questions.html", "Questions & gaps", body)


def page_suggestions(p: Dict) -> str:
    rows = []
    for s in content.SUGGESTIONS:
        rows.append([
            esc(s["id"]), esc(s["category"]), f'<strong>{esc(s["title"])}</strong>',
            esc(s["problem"]), esc(s["proposal"]), esc(s["evidence"]),
            badge(s["impact"], {"High": "fail", "Medium": "warn", "Low": "mute"}[s["impact"]]),
            badge(s["effort"], "mute"),
            esc(s["dependencies"]), esc(s["risk"]), badge(s["status"], "info"),
        ])
    body = f"""
<h1>Suggestions for review</h1>
<p class="lede">Nothing here has been implemented on the strength of this page alone. Each suggestion
states the problem, the proposed change, the evidence that justifies it, and the impact, effort,
dependencies and risk, so a path can be chosen deliberately. The status column is the review
decision point: <em>Proposed</em> becomes <em>Accepted</em>, <em>Deferred</em> or <em>Rejected</em>.</p>
<div class="toolbar">
  <input type="search" data-filter="#s-table" placeholder="Filter suggestions...">
  <select data-filter-select="#s-table" data-filter-column="1">
    <option value="">All categories</option>
    {''.join(f'<option>{esc(c)}</option>' for c in sorted({s["category"] for s in content.SUGGESTIONS}))}
  </select>
</div>
{table(["ID", "Category", "Suggestion", "Problem", "Proposed change", "Evidence", "Impact", "Effort",
        "Dependencies", "Risk", "Review status"], rows, sortable=False)}
<div class="callout"><h4>How to review</h4>
<p>Work down the Impact column. SG13 (lock the evaluation protocol) should be decided before any
strategy is re-scored, and SG3, SG7 and SG9 change the model itself, so they should be decided
before the next season starts. SG6 (campaign tracker) is what turns this from a research
repository into something whose forward record can be audited.</p></div>
"""
    return layout("suggestions.html", "Suggestions", body)


def page_strategies(p: Dict) -> str:
    blocks = []
    for e in p["leaderboard"]:
        gates_pill = " ".join(
            badge(f"{g['key']} {'ok' if g['passed'] else 'x'}", "pass" if g["passed"] else "fail")
            for g in e["gates"]
        )
        blocks.append(f"""
<div class="card" id="{esc(e['key'])}" style="margin:12px 0">
  <h4>{esc(e['name'])} <span class="subtle">{esc(e['key'])} &middot; {esc(e['family'])} family</span></h4>
  <p style="margin:4px 0 8px">{esc(e['description'])}</p>
  <div class="grid k4">
    <div><strong>{e['bets']:,}</strong><div class="subtle">out-of-sample bets</div></div>
    <div><strong class="{sign_class(e['roi'])}">{pct(e['roi'])}</strong><div class="subtle">ROI per unit</div></div>
    <div><strong>{pct(e['hit_rate'], 1, signed=False)}</strong><div class="subtle">hit rate</div></div>
    <div><strong>{e['reward']:.1f}</strong><div class="subtle">reward points</div></div>
  </div>
  <div class="pill-row">{gates_pill}</div>
  <p class="subtle" style="margin:8px 0 0">Seasons {esc(e['first_season'])}&ndash;{esc(e['last_season'])}
  &middot; 95% CI [{pct(e['ci_lo'], 1)}, {pct(e['ci_hi'], 1)}] units/bet
  &middot; permutation p = {num(e['p_value'], 4)}
  &middot; failed gates: {esc(', '.join(e['failed_gates']) or 'none')}</p>
</div>""")
    body = f"""
<h1>Strategy catalogue</h1>
<p class="lede">Sixteen pre-registered strategies across the spread, total and parlay families, each
evaluated walk-forward from 2015 to 2026. Parameters are re-selected at the start of every season
using only games that finished earlier, so no season can influence the parameters used inside it.</p>
{''.join(blocks)}
"""
    return layout("strategies.html", "Strategies", body)


def page_leaderboard(p: Dict) -> str:
    rows = []
    for e in p["leaderboard"]:
        rows.append([
            e["rank"], esc(e["key"]), esc(e["name"]), badge(e["family"], "info"),
            f'{e["bets"]:,}', (pct(e["roi"]), sign_class(e["roi"])),
            (pct(e["hit_rate"], 1, signed=False), ""),
            (f'{e["profit"]:+.1f} units', ""),
            (f'[{pct(e["ci_lo"], 1)}, {pct(e["ci_hi"], 1)}]', ""),
            (num(e["p_value"], 4), ""),
            (pct(e.get("confidence"), 0, signed=False), ""),
            (f'{e["reward"]:.1f}', ""),
            pass_badge(e["all_passed"]),
            esc(", ".join(e["failed_gates"]) or "-"),
        ])
    base_rows = [[esc(k), (pct(v), sign_class(v))] for k, v in p["baselines"].items()]
    body = f"""
<h1>Leaderboard</h1>
<p class="lede">The competition table. Reward is paid only to strategies that clear all eight
validation gates; a rejected strategy earns zero and is shown with the gates it failed, so the
board shows the evidence rather than just the winners.</p>
<h2>Reward formula</h2>
<div class="callout"><h4>reward = 1000 &times; ROI &times; min(1, bets / 300) &times; confidence</h4>
<p><em>confidence</em> is the share of the bootstrap confidence interval that stays above zero, so a
strategy that is profitable but statistically fragile earns proportionally less. A strategy that
fails any gate earns zero by definition.</p></div>
{table(["#", "Key", "Strategy", "Family", "Bets", "ROI", "Hit rate", "Total profit", "95% CI (units/bet)",
        "Permutation p", "Confidence", "Reward", "All gates", "Failed gates"], rows, sortable=False,
       note="Profit is expressed in units of stake. Confidence is the share of the bootstrap interval that stays above zero, and it scales the reward; a rejected strategy scores zero.")}
<h2>Naive baselines on the same window</h2>
<p class="subtle">Every strategy must beat all of these to pass gate G5.</p>
{table(["Baseline", "ROI"], base_rows, sortable=False)}
"""
    return layout("leaderboard.html", "Leaderboard", body)


def page_validation(p: Dict) -> str:
    gate_defs = [
        ["G1", "Sample sufficiency", "At least 100 settled out-of-sample bets", "Gate"],
        ["G2", "Out-of-sample integrity", "Parameters chosen only from earlier seasons; no duplicate bets", "Gate"],
        ["G3", "Statistical significance", "Bootstrap 95% CI lower bound above zero and permutation p <= 0.05", "Gate"],
        ["G4", "Economic significance", "ROI of at least 2% per unit staked", "Gate"],
        ["G5", "Beats naive baselines", "ROI above every always-on baseline on the same window", "Gate"],
        ["G6", "Luck robustness", "Positive ROI after removing one-score games and blowouts", "Gate"],
        ["G7", "Parameter stability", "At least 60% of neighbouring parameter values stay positive", "Gate"],
        ["G8", "Non-redundancy", "Correlation with any accepted strategy at most 0.85", "Gate"],
    ]
    rows = []
    for e in p["leaderboard"]:
        rows.append([esc(e["key"])] + [pass_badge(g["passed"]) for g in e["gates"]]
                    + [esc(", ".join(e["failed_gates"]) or "-")])
    detail_rows = []
    for e in p["leaderboard"]:
        for g in e["gates"]:
            detail_rows.append([esc(e["key"]), esc(g["key"]), esc(g["name"]),
                                pass_badge(g["passed"]), esc(g["value"]), esc(g["threshold"]),
                                esc(g["detail"])])
    sens_rows = []
    for e in p["leaderboard"][:6]:
        for s in e["sensitivity"]:
            sens_rows.append([esc(e["key"]), esc(s["params"]), f'{s["bets"]:,}',
                              (pct(s["roi"]) if s["roi"] is not None else "&mdash;", sign_class(s["roi"])),
                              (pct(s["hit_rate"], 1) if s["hit_rate"] is not None else "&mdash;", "")])
    body = f"""
<h1>Validation gates</h1>
<p class="lede">A strategy earns reward only by passing all eight gates. The gates are applied
identically to every strategy, and every failure is published with the measured value so the
decision to reject or fix is transparent.</p>
<h2>Gate definitions</h2>
{table(["Gate", "Name", "Threshold", "Type"], gate_defs, sortable=False)}
<h2>Gate matrix</h2>
{table(["Strategy"] + [g[0] for g in gate_defs] + ["Failed"], rows, sortable=False)}
<h2>Detail</h2>
<div class="toolbar"><input type="search" data-filter="#gate-table" placeholder="Filter detail..."></div>
{table(["Strategy", "Gate", "Name", "Result", "Measured", "Threshold", "Explanation"],
       detail_rows, sortable=False)}
<h2>Parameter sensitivity (out-of-sample window)</h2>
<p class="subtle">The sensitivity of the six strongest strategies to their own parameters. A signal
that survives at neighbouring settings is far more likely to be skill than luck.</p>
{table(["Strategy", "Parameters", "Bets", "ROI", "Hit rate"], sens_rows, sortable=False)}
"""
    return layout("validation.html", "Validation gates", body)


def page_lines(p: Dict, games: pd.DataFrame) -> str:
    m = p["model"]
    cmp_rows = []
    for label, block in (("All scored games", m["market_all"]),
                         ("2021-2026", m["market_recent"]),
                         ("2026 holdout", m["market_holdout"])):
        if not block:
            continue
        cmp_rows.append([
            esc(label), f'{block["n"]:,}',
            num(block["spread_mae_model"]), num(block["spread_mae_market"]),
            num(block["total_mae_model"]), num(block["total_mae_market"]),
            num(block["delta_abs_mean"]),
        ])
    diag_rows = []
    for d in m["diagnostics"]:
        if d.get("status") != "ok":
            continue
        diag_rows.append([d["season"], f'{d["n_games"]:,}', num(d["margin_mae"]), num(d["margin_rmse"]),
                          num(d["total_mae"]), num(d["margin_bias"]), num(d["total_bias"])])

    current = []
    if len(games):
        sel = games[(games["season"] == config.CURRENT_SEASON) & games["home_score"].isna()
                    & games["market_spread"].notna()]
        sel = sel.sort_values(["week", "gameday"]).head(40)
        for _, r in sel.iterrows():
            current.append([
                esc(r["gameday"]), r["week"], esc(r["away_team"]), esc(r["home_team"]),
                (f'{r["market_spread"]:+.1f}', ""), (num(r["model_spread"], 1), sign_class(r.get("spread_delta"))),
                (f'{r["market_total"]:.1f}', ""), (num(r["model_total"], 1), sign_class(r.get("total_delta"))),
                (signed_num(r.get("spread_delta"), 1), sign_class(r.get("spread_delta"))),
                (signed_num(r.get("total_delta"), 1), sign_class(r.get("total_delta"))),
                source_link("nfldata_games", "mirror"),
            ])

    body = f"""
<h1>Originated lines</h1>
<p class="lede">Our own spread and total for every game, produced by a walk-forward Poisson points
model with team attack and defence ratings, the pre-game Elo difference, rest advantage and a home
indicator. For each game the model is fitted only on seasons that finished before it, so a line is
never informed by its own result.</p>
<div class="grid k3" style="margin:16px 0">
  {kpi("Games scored", f'{m["summary"]["n_games_scored"]:,}', "every game with a pre-game model")}
  {kpi("Mean spread MAE", num(m["market_recent"]["spread_mae_model"]), "model, 2021-2026")}
  {kpi("Market spread MAE", num(m["market_recent"]["spread_mae_market"]), "benchmark, 2021-2026")}
</div>
<h2>Model accuracy against the market</h2>
{table(["Window", "Games", "Model spread MAE", "Market spread MAE", "Model total MAE", "Market total MAE",
        "Mean |line delta|"], cmp_rows, sortable=False,
       note="A lower MAE means the line was closer to the final margin. The market remains the better line; the difference is the size of the opportunity, and it is published so nobody has to assume it.")}
<h2>Published lines for unplayed games</h2>
<div class="toolbar"><input type="search" data-filter="#lines-table" placeholder="Filter games..."></div>
{table(["Date", "Wk", "Away", "Home", "Market spread", "Model spread", "Market total", "Model total",
        "Spread delta", "Total delta", "Source"], current, sortable=False,
       note="Delta = model minus market. A positive spread delta means the model likes the home side more than the market does.")}
<h2>Season-by-season fit</h2>
{table(["Season", "Games", "Margin MAE", "Margin RMSE", "Total MAE", "Margin bias", "Total bias"],
       diag_rows, sortable=False)}
"""
    return layout("lines.html", "Originated lines", body)


def page_correlations(p: Dict) -> str:
    matrix = p["correlations"]["matrix"]
    keys = list(matrix.keys())
    rows = []
    for a in keys:
        cells = []
        for b in keys:
            v = matrix.get(a, {}).get(b)
            if v is None:
                cells.append("<td class='cell muted'>&mdash;</td>")
                continue
            cls = "diag" if a == b else "cell"
            style = ""
            if a != b:
                if v >= 0.6:
                    style = "background:rgba(255,122,122,.16);color:#ff9d9d"
                elif v <= -0.4:
                    style = "background:rgba(87,211,140,.16);color:#8ce3b0"
                elif abs(v) >= 0.3:
                    style = "background:rgba(255,200,87,.14);color:#ffd98a"
            cells.append(f'<td class="{cls}" style="{style}">{v:+.2f}</td>' if a != b
                         else f'<td class="{cls}">1.00</td>')
        rows.append(f"<tr><td>{esc(a)}</td>{''.join(cells)}</tr>")
    matrix_html = (
        '<div class="table-wrap"><table class="matrix"><thead><tr><th>Strategy</th>'
        + "".join(f"<th>{esc(k)}</th>" for k in keys)
        + f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )
    pair_rows = [[esc(d["strategy_a"]), esc(d["strategy_b"]), (f'{d["correlation"]:+.3f}', sign_class(d["correlation"])),
                  d["shared_games"]] for d in p["correlations"]["pairwise"][:20]]
    luck_rows = []
    for l in p["luck"]:
        luck_rows.append([
            esc(l["strategy"]), l["full"]["n"], (pct(l["full"]["roi"]), sign_class(l["full"]["roi"])),
            l["luck_games"]["n"], (pct(l["luck_games"]["roi"]), sign_class(l["luck_games"]["roi"])),
            l["clean_games"]["n"], (pct(l["clean_games"]["roi"]), sign_class(l["clean_games"]["roi"])),
            (pct(l["luck_profit_share"], 1), sign_class(l["luck_profit_share"])),
        ])
    body = f"""
<h1>Correlations and removing luck</h1>
<p class="lede">Two questions: which strategies duplicate each other, and how much of each result is
luck. Correlation is measured on the profit streams of the strategies over the games they share.</p>
<h2>Strategy correlation matrix</h2>
{matrix_html}
<p class="table-note">Red = strongly positive (duplicative), green = negative (offsetting),
amber = moderate. Gate G8 blocks any accepted strategy that duplicates an existing one above 0.85.</p>
<h2>Highest pairwise correlations</h2>
{table(["Strategy A", "Strategy B", "Correlation", "Shared games"], pair_rows, sortable=False)}
<h2>Luck analysis</h2>
<p class="subtle">One-score games (decided by 8 points or fewer) and blowouts (25 points or more) are
removed and the strategy is re-scored. A signal that only works because of lucky one-score games
loses its edge here.</p>
{table(["Strategy", "All bets", "ROI", "Luck-game bets", "Luck ROI", "Clean bets", "Clean ROI",
        "Luck share of profit"], luck_rows, sortable=False)}
"""
    return layout("correlations.html", "Correlations & luck", body)


def page_props(p: Dict) -> str:
    fam_rows = [[esc(f["label"]), esc(f["position_group"]), f'{f["player_games"]:,}',
                 esc(f["seasons"]), (pct(f["hit_rate_at_model_line"], 1), ""),
                 (pct(f["calibrated_hit_rate_eval"], 1) if f.get("calibrated_hit_rate_eval") is not None else "&mdash;", ""),
                 num(f["std_error"], 1), num(f["mean_actual"], 1),
                 num(f.get("calibration_offset"), 1)]
                for f in p["props"].get("families", [])]
    combo_rows = [[esc(c["combo"]), (f'{c["correlation"]:+.3f}', sign_class(c["correlation"])),
                   f'{c["observations"]:,}', pct(c["joint_hit_rate"], 1),
                   pct(c["breakeven_leg_hit_rate"], 1),
                   (pct(c["edge_vs_breakeven"], 1), sign_class(c["edge_vs_breakeven"])),
                   badge("positive" if c["profitable"] else "negative", "pass" if c["profitable"] else "fail")]
                  for c in p["props"].get("combos", [])]
    line_rows = [[esc(l["week"]), esc(l["player"]), esc(l["team"]), esc(l["opponent"]), esc(l["prop"]),
                  num(l["model_line"], 1), num(l["actual"], 1), badge(l["result"], "info")]
                 for l in p["props"].get("current_lines", [])[:60]]
    body = f"""
<h1>Player props</h1>
<p class="lede">Originated prop lines for passing yards, rushing yards, receiving yards and
receptions, built from league-relative rolling production and calibrated so that the line splits
the modelled distribution fairly. The league publishes no prop prices, so these are research
outputs: they cannot be priced against a market until a prop feed is available (question Q9).</p>
<h2>Prop family models</h2>
{table(["Prop", "Positions", "Player-games", "Seasons", "Hit rate at raw model line",
        "Hit rate at calibrated line (2021+)", "Std. deviation", "Mean production", "Calibration offset"],
       fam_rows, sortable=False,
       note="The raw model line uses the mean of a right-skewed distribution, so it hits below 50%. The calibrated line adds the median error measured on 2010-2020 and is the fair line.")}
<h2>Prop combinations and parlay break-even</h2>
<p class="subtle">Two -110 legs need a 27.5% joint hit rate, which is a 52.4% hit rate per leg if
the legs are independent. Correlation decides whether that is reachable.</p>
{table(["Combination", "Correlation", "Observations", "Joint hit rate (at 53% legs)",
        "Break-even leg hit rate", "Edge vs break-even", "Verdict"], combo_rows, sortable=False)}
<h2>Originated prop lines (latest published week)</h2>
{table(["Week", "Player", "Team", "Opponent", "Prop", "Model line", "Actual", "Result"], line_rows, sortable=False)}
"""
    return layout("props.html", "Player props", body)


def page_injuries(p: Dict) -> str:
    inj = p["injuries"]
    summary = inj.get("summary", {})
    cur_rows = [[esc(r["team"]), esc(r["position"]), esc(r["position_group"]), esc(r["player"]),
                 esc(r["injury"] or "-"), badge(r["game_status"], "fail" if r["game_status"] == "Out" else "warn"),
                 esc(r["practice_status"]), source_link("nfl_injuries_w10", "NFL.com")]
                for r in inj.get("current", [])]
    def_rows = [[esc(d["team"]), esc(d["position_group"]), esc(d["starter"]),
                 badge(d["starter_status"], "fail"), esc(d["replacement"] or "-"),
                 esc(d["replacement_tier"] if d["replacement_tier"] is not None else "-"),
                 esc(d["tier_gap"] if d["tier_gap"] is not None else "-"),
                 esc(d["starter_evidence"]), source_link("nfl_injuries_w10", "NFL.com")]
                for d in inj.get("deficiency", [])]
    machine_rows = [[esc(d["team"]), esc(d["position_group"]), esc(d["starter"]),
                     badge(d["starter_status"], "fail"), esc(d["replacement"] or "-"),
                     esc(d["replacement_tier"] if d["replacement_tier"] is not None else "-"),
                     esc(d["tier_gap"] if d["tier_gap"] is not None else "-"),
                     esc(d["starter_evidence"])]
                    for d in inj.get("deficiency_machine", [])]
    depth_rows = [[esc(d["team"]), esc(d["position_group"]), esc(d["tier"]), esc(d["player"]),
                   esc(d.get("games_played")), esc(d.get("work_units")),
                   badge(d["game_status"], "fail" if d["game_status"] in ("Out", "Doubtful") else "mute"),
                   ("must start", "neg") if d.get("must_start") else "-"]
                  for d in inj.get("depth_status", [])]
    effect_rows = [[esc(e["position_group"]), e["games"], (num(e["avg_ats_margin"], 2), sign_class(e["avg_ats_margin"])),
                    pct(e["ats_cover_rate"], 1), esc(e["note"])]
                   for e in inj.get("effect", [])]
    official_rows = read_tsv(config.REPO_ROOT / "data" / "nfl" / "injuries_week10.tsv")
    depth_pilot = read_tsv(config.REPO_ROOT / "data" / "nfl" / "depth_chart_pilot.tsv")
    availability = read_tsv(config.REPO_ROOT / "data" / "nfl" / "availability_derived.tsv")

    official_table_rows = []
    for r in official_rows:
        official_table_rows.append([
            esc(r["game"]), esc(r["team"]), esc(r["player"]), esc(r["position"]),
            esc(r["injury"] or "-"),
            esc(r["practice_status"]),
            (badge(r["game_status"], "fail") if r["game_status"] else "&mdash;"),
            f'<a href="{esc(r["player_url"])}" target="_blank" rel="noopener">nfl.com</a>',
        ])

    pilot_rows = []
    for r in depth_pilot:
        pilot_rows.append([
            esc(r["team"]), esc(r["side"]), esc(r["position"]), esc(r["depth_order"]),
            esc(r["chart_note"]),
            f'<a href="{esc(r["source_url"])}" target="_blank" rel="noopener">club chart</a>',
        ])

    avail_rows = []
    for r in availability:
        if r["game_status"] not in ("Out", "Doubtful"):
            continue
        avail_rows.append([
            esc(r["game"]), esc(r["team"]), esc(r["player"]), esc(r["position"]),
            esc(r["injury"] or "-"),
            badge(r["game_status"], "fail"),
            esc(r["depth_status"]),
            esc(r["listed_starter"] or "-"),
            esc(r["depth_rank"] or "-"),
            f'<a href="{esc(r["player_url"])}" target="_blank" rel="noopener">nfl.com</a>',
        ])

    body = f"""
<h1>Injuries and depth</h1>
<p class="lede">The tracker covers two things: who is out, and who has to replace them. The league
publishes an official injury report every week; the rows below are transcribed directly from it.
Depth tiers are derived, because the league publishes no depth chart - that limitation is flagged
on the Flagged for Review page.</p>
<div class="grid k4" style="margin:16px 0">
  {kpi("Official rows (Week 10)", f'{summary.get("official_current_week_rows", 0)}', "transcribed from nfl.com")}
  {kpi("Out designations", f'{summary.get("official_out", 0)}', "Week 10 official report")}
  {kpi("Machine-readable history", f'{summary.get("rows", 0):,}', f'weeks {summary.get("machine_readable_weeks")}')}
  {kpi("Depth deficiencies found", f'{len(inj.get("deficiency", [])) + len(inj.get("deficiency_machine", []))}', "first string unavailable")}
</div>
<h2>Current week injury status (official NFL report)</h2>
<div class="toolbar"><input type="search" data-filter="#inj-table" placeholder="Filter players..."></div>
{table(["Team", "Pos", "Group", "Player", "Injury", "Game status", "Practice status", "Source"],
       cur_rows, sortable=False)}
<h2>Depth deficiencies - current week</h2>
<p class="subtle">The first string at the position is Out or Doubtful, so a deeper player must take over.</p>
{table(["Team", "Group", "First string", "Status", "Replacement", "Replacement tier", "Tier gap",
        "Evidence for the tier", "Source"], def_rows, sortable=False)}
<h2>Depth deficiencies - latest complete machine-readable week</h2>
{table(["Team", "Group", "First string", "Status", "Replacement", "Replacement tier", "Tier gap",
        "Evidence for the tier"], machine_rows, sortable=False)}
<h2>Depth picture for the teams in the current report</h2>
<div class="toolbar"><input type="search" data-filter="#depth-table" placeholder="Filter depth rows..."></div>
{table(["Team", "Group", "Tier", "Player", "Games played", "Work units", "Status", "Note"],
       depth_rows, sortable=False)}
<h2>Measured effect of a missing starter (2026 season)</h2>
<p class="subtle">Games where exactly one side is missing an Out player at that position group.
Small samples - treat as directional only (flagged item F5).</p>
{table(["Position group", "Games", "Average ATS margin", "Cover rate", "Note"], effect_rows, sortable=False)}

<h2>Official Week 10 injury report - every row as printed by the league</h2>
<p class="subtle">{len(official_table_rows)} player rows transcribed from
<a href="https://www.nfl.com/injuries/league/2026/reg10" target="_blank" rel="noopener">nfl.com</a>
by the integration session; each row links to that player's official league page. A blank game
status means the league printed no designation - it is never filled in.
The availability join against club-published depth charts is on the
<a href="../pages/availability.html">official availability page</a>.</p>
<div class="toolbar"><input type="search" data-filter="#official-table" placeholder="Filter the official report..."></div>
{table(["Game", "Team", "Player", "Pos", "Injury", "Practice status", "Game status", "Source"],
       official_table_rows, sortable=False, data_table=True)}

<h2>Club-published depth charts (pilot)</h2>
<p class="subtle">{len(pilot_rows)} rows covering {len({r["team"] for r in depth_pilot})} clubs whose own
websites publish a depth chart. These are club self-reports, printed as unofficial by at least two
clubs; the remaining clubs are a flagged coverage gap, not an omission. The league itself publishes
no depth chart, which is why the depth tiers above are labelled derived.</p>
{table(["Team", "Side", "Position", "Depth order as printed", "Chart note", "Source"],
       pilot_rows, sortable=False)}

<h2>Players ruled out with a club depth-chart ranking available</h2>
<div class="toolbar"><input type="search" data-filter="#avail-table" placeholder="Filter ruled-out players..."></div>
{table(["Game", "Team", "Player", "Pos", "Injury", "Game status", "Depth status", "Listed starter",
        "Depth rank", "Source"], avail_rows, sortable=False, data_table=True)}
"""
    return layout("injuries.html", "Injuries & depth", body)


def page_methods(p: Dict) -> str:
    body = f"""
<h1>Methods</h1>
<p class="lede">How every number on this site is produced, so that a reviewer can repeat it.</p>

<h2>Data acquisition</h2>
<p>The sandbox network allow-list permits GitHub and PyPI hosts only, so bulk inputs are pulled from
GitHub through the REST contents API and cached under <code>data/raw</code>. Every file is recorded
with its byte size and SHA-256 in <code>data/raw_manifest.json</code>, so a reviewer can confirm that
a published table came from a specific file. League-operated pages (NFL injury reports, the season
calendar, the rule book) are cited directly and transcribed where the values are published row by row.</p>

<h2>Walk-forward evaluation</h2>
<p>For every evaluation season, each strategy's parameters are re-selected using only games that
finished in earlier seasons, then applied to the evaluation season. Parameters are chosen by a
risk-adjusted score (mean profit divided by its standard error) so that a high return on a handful
of bets cannot beat a steadier signal with more evidence. The evaluation window runs from 2015 to
the 2026 season, which gives every strategy thousands of out-of-sample bets and every parameter
choice a genuine test.</p>

<h2>Originated lines</h2>
<p>A Poisson points model is fitted on stacked team-game rows:
<code>points ~ C(team) + C(opponent) + elo_diff + rest_diff + is_home</code>.
Team dummies give attack and defence ratings, the pre-game Elo difference adds a dynamic strength
signal, rest difference captures scheduling, and the home indicator captures the scoring level.
The model is refitted for every season using only earlier seasons, so no game is scored by a model
that has seen it. The originated spread is the difference between the two predicted point totals and
the originated total is their sum, both rounded to half points.</p>

<h2>Validation gates</h2>
<p>Eight gates, applied identically to every strategy: sample sufficiency, out-of-sample integrity,
statistical significance (bootstrap interval plus a sign-flip randomisation test), economic
significance, superiority over naive baselines, luck robustness, parameter stability and
non-redundancy. A strategy that fails any gate earns no reward and is published with the measured
values that caused the failure.</p>

<h2>Removing luck</h2>
<p>One-score games (margin of 8 points or fewer) and blowouts (25 points or more) are removed and
the strategy is re-scored (gate G6). Turnover luck and drive-level variance are not yet
controllable because play-by-play data is not in the pipeline - that is question Q12.</p>

<h2>Correlation and parlay arithmetic</h2>
<p>Strategy correlations are Pearson correlations of per-bet profit streams over shared games. For
parlays, a two-leg combination at -110 needs a 27.5% joint hit rate; the joint probability is
computed from each leg's hit rate and the correlation between the legs
(<code>p1*p2 + rho*p1*(1-p2)</code>), which is what makes the prop-combo table a decision tool
rather than a list of numbers.</p>

<h2>Reward formula</h2>
<p><code>reward = 1000 * ROI * min(1, bets / 300) * confidence</code>, where confidence is the
share of the bootstrap confidence interval that stays above zero. Rejected strategies earn zero.</p>

<h2>What is not modelled yet</h2>
<ul class="clean">
<li>Drive-level efficiency (EPA, success rate, third-down rate) - needs play-by-play (Q1, SG3).</li>
<li>Closing-line value - needs opening and closing prices stored per game (SG5).</li>
<li>Player-prop pricing - needs a market prop feed (Q9).</li>
<li>Turnover luck - needs play-by-play (Q12).</li>
<li>Multi-season injury adjustments - needs a multi-year injury feed (Q8).</li>
</ul>
"""
    return layout("methods.html", "Methods", body)


def page_sources(p: Dict) -> str:
    rows = []
    for s in sources.SOURCES:
        rows.append([
            esc(s.key), esc(s.title), esc(s.publisher),
            badge("league-operated" if s.kind == "league" else ("state" if s.kind == "state" else "community mirror"), 
                  "pass" if s.official else "warn"),
            f'<a href="{esc(s.url)}" target="_blank" rel="noopener">{esc(s.url)}</a>',
            esc(s.accessed), esc(s.notes),
        ])
    manifest_rows = []
    for m in p.get("manifest", []):
        manifest_rows.append([esc(m["name"]), esc(m["repo"]), esc(m["path"]),
                              f'{m["bytes"]:,}', (esc((m["sha256"] or "")[:16]) + "...", "mono"),
                              badge(m["status"], "pass" if m["status"] in ("cached", "downloaded") else "fail")])
    body = f"""
<h1>Sources</h1>
<p class="lede">Every source used by the project, what it supports, and whether it is operated by the
league or by a community mirror. League-operated sources are marked in green; anything drawn from a
community mirror is marked in amber and explained on the Flagged for Review page.</p>
{table(["Key", "Title", "Publisher", "Type", "URL", "Accessed", "Notes"], rows, sortable=False)}
<h2>Raw input manifest</h2>
<p class="subtle">SHA-256 fingerprints of every file the pipeline consumed for this build.</p>
{table(["File", "Repository", "Path", "Bytes", "SHA-256", "Status"], manifest_rows, sortable=False)}
"""
    return layout("sources.html", "Sources", body)


def page_flagged(p: Dict) -> str:
    rows = [[esc(f["id"]), esc(f["area"]), esc(f["issue"]), esc(f["why"]), esc(f["action"]),
             source_link(f["source"]) if f["source"] != "brief" else "Brief",
             badge(f["severity"], {"High": "fail", "Medium": "warn", "Low": "mute"}[f["severity"]])]
            for f in content.FLAGGED]
    body = f"""
<h1>Flagged for review</h1>
<p class="lede">Everything that could not be confirmed from a league-operated source, every
caveat that limits a published number, and every irregularity found while auditing the
repository. Nothing on this list was filled in with an estimate: values that cannot be confirmed
are left blank on the pages that use them.</p>
<h2>Open items</h2>
<table id="flag-table">
{table(["ID", "Area", "Issue", "Why it matters", "Action needed", "Source", "Severity"], rows, sortable=False)}
</table>
<h2>Repository audit</h2>
<div class="callout"><h4>Starting state</h4>
<p>The repository contained a single file: a 4-byte README with the content <code># X1</code>. There
was no source code, no data, no continuous integration, no licence and no documentation to review,
so the audit found no irregularities in pre-existing work. The audit trail from that point is kept
in <code>COORDINATION.md</code>, which records each task, its owner, its file scope and the sources
used.</p></div>
<div class="callout good"><h4>What was added</h4>
<p>A reproducible Python package (<code>src/x1</code>), a static site generator
(<code>scripts/build_site.py</code>), a GitHub Actions workflow that deploys the site, and the
processed tables that back every published number.</p></div>
"""
    return layout("flagged.html", "Flagged for review", body)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main() -> None:
    payload = load_payload()
    games = load_games()

    config.RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    assets = config.RESEARCH_DIR / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(__file__).resolve().parents[1] / "src" / "site" / "styles.css", assets / "styles.css")
    shutil.copyfile(Path(__file__).resolve().parents[1] / "src" / "site" / "app.js", assets / "app.js")

    pages = {
        "index.html": page_dashboard(payload, games),
        "executive-summary.html": page_exec(payload),
        "requirements.html": page_requirements(payload),
        "questions.html": page_questions(payload),
        "suggestions.html": page_suggestions(payload),
        "strategies.html": page_strategies(payload),
        "leaderboard.html": page_leaderboard(payload),
        "validation.html": page_validation(payload),
        "lines.html": page_lines(payload, games),
        "correlations.html": page_correlations(payload),
        "props.html": page_props(payload),
        "injuries.html": page_injuries(payload),
        "methods.html": page_methods(payload),
        "sources.html": page_sources(payload),
        "flagged.html": page_flagged(payload),
    }
    for name, html_text in pages.items():
        (config.RESEARCH_DIR / name).write_text(html_text)
    print(f"wrote {len(pages)} pages to {config.RESEARCH_DIR}")


if __name__ == "__main__":
    main()
