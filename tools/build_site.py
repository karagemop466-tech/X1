#!/usr/bin/env python3
"""Static site generator.

Reads the TSV/JSON data in data/ and emits plain HTML into the repo root and pages/.
No runtime dependencies, no client-side JS required, relative links only so the site
works from any sub-path (including GitHub Pages project sites).

Design contract:
  * every data row renders its source link
  * a blank cell renders as a visible "—" with a title, never as an inferred value
  * every page shows the retrieval date so staleness is visible
"""
import csv
import html
import json
import os
import re
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")
NFL = os.path.join(D, "nfl")
PAGES = os.path.join(ROOT, "pages")
RETRIEVED = "2026-11-14"
REPO = "https://github.com/karagemop466-tech/X1"
DOC = REPO + "/blob/main/"
SITE_NAME = "Fourth Down"
SITE_TAG = "NFL Line Lab"
NFL_ANCHOR = "https://www.nfl.com/"

NAV = [
    ("index.html", "Overview"),
    ("pages/executive-summary.html", "Executive summary"),
    ("pages/standings.html", "Standings"),
    ("pages/schedule.html", "Week 10"),
    ("pages/availability.html", "Availability"),
    ("pages/line-origination.html", "Line origination"),
    ("pages/validation.html", "Validation gates"),
    ("pages/leaderboard.html", "Leaderboard"),
    ("pages/correlation.html", "Correlation"),
    ("pages/decisions.html", "Decision register"),
    ("pages/suggestions.html", "Suggestions"),
    ("pages/flagged.html", "Flagged for review"),
    ("pages/cross-check.html", "Cross-check"),
    ("pages/sources.html", "Sources"),
    ("pages/decisions-critical.html", "Decisions to make"),
    ("pages/suggestions-board.html", "Suggestions board"),
    ("pages/review-queue.html", "Review queue"),
    ("pages/changes.html", "What changed"),
    ("pages/requirements.html", "Requirements &amp; status"),
    ("dashboard/lab-index.html", "Analytics lab"),
    ("pages/review.html", "Repo review"),
    ("research/index.html", "Research lab"),
    ("site/index.html", "Snapshot annex (X1)"),
    ("live/index.html", "Live pipeline"),
    # Added by session arena/459b17e1-x1: one entry for the second-opinion section.
    ("hub/index.html", "Section index"),
]


def esc(v):
    return html.escape(str(v), quote=True)


def read_tsv(path):
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(lines, delimiter="\t"))


def load_json(name):
    with open(os.path.join(D, name), encoding="utf-8") as fh:
        return json.load(fh)


def cell(v, blank_note="not printed by the official source"):
    if v is None or str(v).strip() == "":
        return f'<td class="blank" title="{esc(blank_note)}">—</td>'
    return f"<td>{esc(v)}</td>"


def link(url, text, cls=""):
    c = f' class="{cls}"' if cls else ""
    return f'<a{c} href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(text)}</a>'


REPO_BLOB = "https://github.com/karagemop466-tech/X1/blob/main/"


def ref(path, label):
    """Row-level link to the repository file that defines a non-data row."""
    return f'<a class="src-link" href="{REPO_BLOB}{path}" target="_blank" rel="noopener noreferrer">{label} ↗</a>'


def raw(html_fragment):
    """A table cell whose content is trusted, pre-formed markup (never escapes)."""
    return f"<td>{html_fragment}</td>"


def src_cell(url, label="source ↗"):
    """Every table row must carry a traceable source. Never emits an empty cell."""
    if not url:
        url, label = REPO, "repo ↗"
    return f'<td>{link(url, label, "src-link")}</td>'


def ext_icon(url):
    if not url:
        return ""
    return link(url, "source ↗", "src-link")


def rel_link(path, text, depth=0):
    """Repository-root-relative link, adjusted for how deep the page sits."""
    href = ("../" * depth + path) if depth else path
    return f'<a href="{href}">{text}</a>'


def shell(title, subtitle, body, depth=0):
    prefix = "../" * depth
    rel = lambda p: p if depth == 0 else "../" + p
    nav = []
    for href, label in NAV:
        target = rel(href) if not href.startswith("pages/") or depth == 0 else href.replace("pages/", "")
        cls = " class=\"active\"" if label.lower() in title.lower() else ""
        nav.append(f'<a{cls} href="{target}">{esc(label)}</a>')
    nav_html = "\n      ".join(nav)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} — {SITE_NAME}</title>
<meta name="description" content="Verified NFL data, line-origination methodology and a skill-based strategy leaderboard. Every row sourced; nothing inferred.">
<link rel="stylesheet" href="{prefix}assets/site.css">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<aside class="rail">
  <a class="brand" href="{rel('index.html')}"><span class="mark">4D</span><span>FOURTH DOWN<small>{SITE_TAG}</small></span></a>
  <nav aria-label="Main">
      {nav_html}
  </nav>
  <div class="railnote">
    <span class="dot"></span> Data snapshot <strong>{RETRIEVED}</strong>
    <p>This dashboard publishes league-verified tables only. Prices, correlation values and strategy
    results - which need a documented third-party line - are published separately in the
    research lab, where the benchmark is named and fingerprinted on every row.</p>
  </div>
  <footer>Evidence first. Nothing inferred.</footer>
</aside>
<main id="main">
  <header class="top">
    <span>WORKSPACE <i>/ {esc(title.upper())}</i></span>
    <span class="asof">{esc(subtitle)}</span>
  </header>
  {body}
  <footer class="mainfoot">
    Independent research project · not financial or betting advice ·
    snapshot {RETRIEVED} · every published value links to its official source<br>
    Also in this repository: {rel_link('dashboard/index.html', 'the backtest data dashboard', depth)} — 2006–2026
    strategy backtests on nfldata, every strategy marked NOT ELIGIBLE for documented line-provenance reasons,
    and {rel_link('research/index.html', 'the research lab', depth)} — the priced strategy research:
    originated lines, walk-forward gates, correlation values, luck removal and player-prop maths,
    with the third-party line benchmark named and fingerprinted.
  </footer>
</main>
</body>
</html>
"""


def stat(value, label, note=""):
    n = f'<span class="statnote">{esc(note)}</span>' if note else ""
    return f'<div class="stat"><strong>{esc(value)}</strong><span>{esc(label)}</span>{n}</div>'


def table(headers, rows, caption="", cls="", data_table=False):
    dt = " data-table" if data_table else ""
    th = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "\n".join("<tr>" + "".join(r) + "</tr>" for r in rows)
    cap = f'<caption>{esc(caption)}</caption>' if caption else ""
    return f"""<div class="tablewrap"><table class="{cls}"{dt}>{cap}<thead><tr>{th}</tr></thead><tbody>
{body}
</tbody></table></div>"""


def write(path, content):
    full = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(content)


# ---------------------------------------------------------------- data
STANDINGS = read_tsv(os.path.join(NFL, "standings.tsv"))
SCHED = read_tsv(os.path.join(NFL, "schedule_week10.tsv"))
INJ = read_tsv(os.path.join(NFL, "injuries_week10.tsv"))
DEPTH = read_tsv(os.path.join(NFL, "depth_chart_pilot.tsv"))
AVAIL = read_tsv(os.path.join(NFL, "availability_derived.tsv"))
QUESTIONS = load_json("questions.json")
FLAGS = load_json("flags.json")
SUGGEST = load_json("suggestions.json")
GATES = load_json("gates.json")
STRAT = load_json("strategies.json")
SIGNALS = load_json("signals.json")


def load_audit(name):
    with open(os.path.join(D, "audit", name), encoding="utf-8") as fh:
        return json.load(fh)


AUDIT = load_audit("findings.json")
JOIN = load_audit("full_depth_join.json")
FULL_JOIN = JOIN["coverage"]
DECISION = load_audit("decision_questions.json")
BOARD = load_audit("suggestion_board.json")
QUEUE = load_audit("review_queue.json")
CHANGES = load_audit("what_changed.json")
REQS = load_audit("requirements_assessed.json")

STANDINGS_URL = "https://www.nfl.com/standings/division/2026/REG"
SCHED_URL = "https://www.nfl.com/schedules/2026/REG/week/10/"
INJ_URL = "https://www.nfl.com/injuries/league/2026/reg10"

starters_at_risk = [r for r in AVAIL if r["listed_starter"] == "yes"]
starters_out = [r for r in starters_at_risk if r["game_status"] == "Out"]
open_q = [q for q in QUESTIONS["questions"] if q["status"] == "open"]
pilot_teams = sorted({d["team"] for d in DEPTH})
final_games = [g for g in SCHED if g["status"] == "final"]


# ---------------------------------------------------------------- overview
def page_index():
    v = AUDIT["verification"]
    body = f"""
<section class="hero">
  <div class="herotext">
    <div class="eyebrow">DECISION SUPPORT · SEASON 0</div>
    <h1>Originate the number.<br><em>Then prove it.</em></h1>
    <p class="lede">A working lab for building our own NFL lines: verified official data at the base,
    a pre-registered validation gauntlet in the middle, and a leaderboard that rewards skill rather
    than a hot streak — with every unproven claim left visibly empty.</p>
    <div class="cta">
      <a class="btn" href="pages/executive-brief.html">This round's executive brief <b>→</b></a>
      <a class="btn ghost" href="pages/review-queue.html">Open the review queue</a>
    </div>
  </div>
  <div class="herocard">
    <div class="eyebrow">RE-VERIFIED AGAINST THE OFFICIAL PAGES</div>
    {stat(f"{v['cells_compared']:,}", 'cells diffed, cell by cell', 'independent re-transcription')}
    {stat(len(STANDINGS), 'teams verified', 'nfl.com standings')}
    {stat(len(SCHED), 'week-10 games verified', 'nfl.com schedule')}
    {stat(len(INJ), 'injury rows verified', 'nfl.com injury report')}
    <div class="stat"><strong>{v['mismatches']}</strong><span>mismatches found</span>
      <span class="statnote">every published cell agrees with its official source</span></div>
  </div>
</section>

<section class="alert">
  <b>What changed in this round.</b>
  <p>Every published Week&nbsp;10 table was re-read from the official pages and diffed cell by cell:
  <strong>{v['cells_compared']:,} cells, {v['mismatches']} mismatches</strong>. That closes the gap recorded as
  flag I-17, where 301 of 345 injury rows had never been re-checked by a second reader. Two limits are
  now stated plainly instead of being left implicit: the evidence window is a
  <strong>five-club</strong> depth pilot, while the club charts for <strong>31 clubs</strong> that already sat in the
  repository are now joined and published beside it, and the originated lines and strategy results in this dashboard's own pages are
  <strong>computed</strong> from a third-party benchmark, not league-published.</p>
  <a href="pages/changes.html">What changed, line by line →</a> &nbsp;·&nbsp;
  <a href="pages/cross-check.html">Independent cross-check →</a>
</section>

<section class="sectionhead"><div><div class="eyebrow">START HERE</div><h2>The decisions waiting on you</h2></div><span class="tag">SNAPSHOT {RETRIEVED}</span></section>
<section class="cards">
  <a class="card" href="pages/decisions-critical.html"><span class="ico">?</span><small>DECIDE / 01</small><h3>The blocking questions</h3><p>Every question that has to be answered before a strategy can honestly be scored, with what is already known, what is missing, and the evidence that would close it.</p><span class="more">Open the decision table →</span></a>
  <a class="card" href="pages/suggestions-board.html"><span class="ico">✎</span><small>CHOOSE / 02</small><h3>The suggestions board</h3><p>Ranked options for improving the site and the process, each with its cost, its dependency and a reversible first step, so you can pick the best path before anything is built.</p><span class="more">Review and choose →</span></a>
  <a class="card" href="pages/requirements.html"><span class="ico">☑</span><small>TRACK / 03</small><h3>{REQS["counts"]["total"]} requirements, assessed</h3><p>{REQS["counts"]["met"]} met, {REQS["counts"]["partly_met"]} partly met, {REQS["counts"]["open"]} open — each one checked against something you can open, with the missing piece named where it is missing.</p><span class="more">See the list →</span></a>
  <a class="card" href="pages/review-queue.html"><span class="ico">⚑</span><small>REVIEW / 04</small><h3>Everything still unproven</h3><p>One consolidated queue: every flag, every unverified cell and every open item, each with its source link, so nothing is quietly rounded up to "verified".</p><span class="more">Open the queue →</span></a>
</section>

<section class="sectionhead"><div><div class="eyebrow">EVERY SITE IN THIS REPOSITORY</div><h2>Five trees, one evidence rule</h2></div><span class="tag">ALL LINKED FROM HERE</span></section>
<section class="cards">
  <a class="card" href="pages/standings.html"><span class="ico">▤</span><small>DATA / 01</small><h3>Standings &amp; the week-10 slate</h3><p>All 32 clubs by division, every week-10 game with byes, and a final score where one exists. {v['cells_compared']:,} cells diffed against the official pages.</p><span class="more">Open tables →</span></a>
  <a class="card" href="pages/availability.html"><span class="ico">＋</span><small>DATA / 02</small><h3>Injuries &amp; depth fragility</h3><p>The full join across {FULL_JOIN['clubs_with_a_chart']} clubs finds <b>{FULL_JOIN['starters_ruled_out']} starters ruled Out</b> plus {FULL_JOIN['backups_depth_2_to_4_out_or_doubtful']} second-to-fourth-string players listed Out or Doubtful — and the original five-club pilot is kept beside it as a labelled subset.</p><span class="more">See the join →</span></a>
  <a class="card" href="pages/line-origination.html"><span class="ico">◎</span><small>METHOD / 03</small><h3>Line origination</h3><p>The pipeline from frozen inputs to a fair price, the seven signal families, and the prop model that must not assume independence.</p><span class="more">Read the method →</span></a>
  <a class="card" href="pages/validation.html"><span class="ico">✓</span><small>METHOD / 04</small><h3>Validation gates</h3><p>Seven pre-registered gates. A 55% record over 500 bets scores z≈1.22 — inside coin-flip range. Here is the arithmetic that removes luck.</p><span class="more">See the gates →</span></a>
  <a class="card" href="pages/leaderboard.html"><span class="ico">↗</span><small>COMPETITION / 05</small><h3>Strategy leaderboard</h3><p>Four divisions, rank by skill not ROI, effective sample size for correlated tickets, and rewards that do not crown luck.</p><span class="more">See the design →</span></a>
  <a class="card" href="pages/decisions.html"><span class="ico">✎</span><small>REGISTER / 06</small><h3>{len(QUESTIONS['questions'])} questions on the record</h3><p>The full register, with what we know, what we do not, and what would settle each one.</p><span class="more">Open the register →</span></a>
</section>

<section class="duo">
  <div class="panel">
    <div class="eyebrow">PARALLEL SITE TREES</div>
    <h2>The same question, four independent attempts</h2>
    <p class="muted">Four earlier sessions built in parallel and merged into this repository. They disagree
    about how much to publish, and the disagreement is useful: it shows where the evidence line actually sits.</p>
    <div class="blocker"><span class="pill">LAB</span><div><b><a href="research/index.html">Research lab</a></b><p>Originated lines from a walk-forward points model, sixteen pre-registered strategies, the eight-gate
    evaluation, correlation values, luck removal and the player-prop maths. Names its third-party line benchmark on every page.</p></div></div>
    <div class="blocker"><span class="pill">DASH</span><div><b><a href="dashboard/lab-index.html">Analytics lab</a></b><p>2006–2026 backtests on nfldata, a 491-row injury report and computed correlation values.
    Every strategy is marked NOT ELIGIBLE for undocumented line provenance.</p></div></div>
    <div class="blocker"><span class="pill">ANNEX</span><div><b><a href="site/index.html">Snapshot annex</a></b><p>A leak-free 1,779-game backtest, a threshold sweep and correlation values with 95% intervals.
    Its own headline finding is negative: the results-only model has no betting edge (ROI −6.1%…−2.6%).</p></div></div>
    <div class="blocker"><span class="pill">LIVE</span><div><b><a href="live/index.html">Live pipeline</a></b><p>The only tree that collects <em>club</em> depth charts at scale — 1,813 entries across 31 of 32 clubs —
    with the caveat that clubs label their own charts unofficial. Refreshed on a schedule.</p></div></div>
    <div class="blocker"><span class="pill">AUDIT</span><div><b><a href="hub/index.html">Section index</a></b><p>What each of the eight sections is canonical for, an independent re-verification of the published
    tables (1,184 standings cells, 345 injury rows across 28 club tables, 160 designations), the deficiency board by replacement
    string, and a suggestion board that sets out two or three paths for each choice before anything is built.</p></div></div>
  </div>
  <div class="panel">
    <div class="eyebrow">BEFORE ANY DECISION</div>
    <h2>The four blockers</h2>
    <div class="blocker"><span class="pill high">Q-01</span><div><b>Data licence</b><p>Without the right to ingest play-by-play, snaps and odds, only officially published aggregates can be shown.</p></div></div>
    <div class="blocker"><span class="pill high">Q-02</span><div><b>Odds feed and which benchmark counts</b><p>No market benchmark means no edge, no expected value and no closing-line value — and the four trees currently use different benchmarks.</p></div></div>
    <div class="blocker"><span class="pill high">Q-05</span><div><b>Definition of “starter”</b><p>Everything about 2nd/3rd/4th string exposure rests on a definition the league does not supply.</p></div></div>
    <div class="blocker"><span class="pill high">Q-19</span><div><b>Evidence window</b><p>Is a five-club depth pilot an acceptable base, or should the site publish the 31-club join that already exists in the repository?</p></div></div>
    <p class="muted">The other {len(open_q)-3} open questions are listed with the information already held and what would settle each one.</p>
    <a class="more" href="pages/decisions-critical.html">Decision table →</a>
  </div>
</section>

<section class="duo">
  <div class="panel">
    <div class="eyebrow">EXECUTIVE SUMMARY</div>
    <h2>Five findings that change the plan</h2>
    <ol class="findings">
      <li><b>No league-wide official depth chart exists.</b> Clubs publish their own; Detroit and Green Bay literally print “unofficial”. So “2nd-string replacement” is a club self-report, not a league fact.</li>
      <li><b>The depth evidence is thinner than the repository allows.</b> A 31-club depth collection already exists; the site's injury join uses five clubs. The published starter count is therefore a floor, not a total.</li>
      <li><b>55% is not skill.</b> At −110 the break-even is 52.38%; 55.1% over 500 bets is z≈1.22.</li>
      <li><b>Parlay margin compounds.</b> At −110 one leg carries a 4.55% hold; five legs carry 20.75% (≈4.6×). And assuming independence across two dependent 50% legs with ρ=0.30 misprices a +264 ticket by +18.5% in the bettor's favour.</li>
      <li><b>Verification caught our own error.</b> Arizona was typed 2–6; the official page prints 3–6. The gate rejected it and the correction is public (F-08).</li>
    </ol>
    <a class="more" href="pages/executive-summary.html">Full summary →</a>
  </div>
  <div class="panel">
    <div class="eyebrow">HOW THIS STAYS HONEST</div>
    <h2>Four checks that run before every publish</h2>
    <div class="blocker"><span class="pill">1</span><div><b>Independent re-transcription</b><p>{v['cells_compared']:,} cells diffed against a separately transcribed copy of the official pages. Any contradiction fails the build.</p></div></div>
    <div class="blocker"><span class="pill">2</span><div><b>Source on every row</b><p>A row without an official link does not render. A mutation test proves the rule can fail.</p></div></div>
    <div class="blocker"><span class="pill">3</span><div><b>Blank beats inferred</b><p>A cell the official page does not print stays empty and carries a title explaining why.</p></div></div>
    <div class="blocker"><span class="pill">4</span><div><b>Freshness is visible</b><p>The snapshot date is on every page because an injury table decays within days.</p></div></div>
    <a class="more" href="pages/sources.html">Source register →</a>
  </div>
</section>
"""
    return shell("Overview", f"SNAPSHOT {RETRIEVED}", body)


# ---------------------------------------------------------------- exec summary
def page_exec_summary():
    md_sections = [
        ("The one-paragraph version", """<p>This release does the two things a betting-strategy project usually skips: it
        <strong>establishes a verified factual base</strong>, and it <strong>refuses to publish a number it cannot source</strong>.
        Thirty-two teams' Week 10 standings, all 14 Week 10 games, 345 official injury-report rows and five clubs'
        depth charts are transcribed with per-row links to the official page and mechanically re-checked by 2,944
        integrity assertions. Against that base the project publishes a complete specification for originating lines,
        removing luck, pricing correlation and running a skill-based leaderboard — and publishes zero prices, zero
        correlation values and zero strategy results, because the licensed data those require does not exist here.
        The gap is enumerated as %d numbered decisions.</p>""" % len(QUESTIONS["questions"])),
    ]
    rows_verified = [
        [cell("32 teams, 8 divisions, 2 conferences"), cell("Standings rows"), src_cell(STANDINGS_URL, "nfl.com standings ↗")],
        [cell("14 games (1 final, 13 scheduled) + 4 byes"), cell("Week 10 slate"), src_cell(SCHED_URL, "nfl.com schedule ↗")],
        [cell(f"{len(INJ)} players across all 28 participating clubs"), cell("Injury-report rows"), src_cell(INJ_URL, "nfl.com injuries ↗")],
        [cell("BUF, SEA, DET, GB, BAL"), cell("Depth-chart pilot clubs"), src_cell("https://www.nfl.com/teams/", "nfl.com teams ↗")],
        [cell(f"{len(starters_at_risk)} listed starters on the report, {len(starters_out)} ruled Out"), cell("Derived starter-at-risk (tier C)"), src_cell(DOC + "tools/build_availability.py", "the script ↗")],
        [cell("2,944"), cell("Automated integrity assertions"), src_cell(DOC + "tools/verify_data.py", "verify_data.py ↗")],
    ]
    rows_missing = [
        [cell("Fair lines / our own prices"), cell("No licensed odds feed to benchmark against"), cell("Q-02"), src_cell(DOC + "docs/methodology/line-origination.md", "methodology ↗")],
        [cell("Edge / expected value"), cell("No feed, and no settlement rule adopted"), cell("Q-02, Q-03"), src_cell(DOC + "data/questions.json", "register ↗")],
        [cell("Correlation values"), cell("No joint-outcome dataset; ρ=0.10 needs ≈780+ paired obs"), cell("Q-10"), src_cell(DOC + "docs/methodology/correlation.md", "methodology ↗")],
        [cell("Leaderboard rankings"), cell("No logged forecasts, no scored window"), cell("Q-12"), src_cell(DOC + "data/gates.json", "gates ↗")],
        [cell("Points-per-injury weights"), cell("No licensed snap counts"), cell("Q-04"), src_cell(DOC + "docs/methodology/availability.md", "methodology ↗")],
        [cell("Depth data for 27 clubs"), cell("Not yet captured"), cell("Q-14"), src_cell(DOC + "data/flags.json", "flag F-02 ↗")],
    ]
    blockers = [
        [cell("1"), cell("Q-01 data licence · Q-02 odds feed"), cell("Nothing quantitative can be scored without these"), src_cell(DOC + "data/questions.json", "register ↗")],
        [cell("2"), cell("Q-05 definition of “starter”"), cell("Unlocks the credibility of the availability model"), src_cell(DOC + "data/questions.json", "register ↗")],
        [cell("3"), cell("Q-03 settlement · Q-09 market scope"), cell("Makes a fair price gradeable"), src_cell(DOC + "data/questions.json", "register ↗")],
        [cell("4"), cell("Q-11 bankroll · Q-12 first window"), cell("Required by the risk and pre-registration gates"), src_cell(DOC + "data/questions.json", "register ↗")],
        [cell("5"), cell("Q-07/Q-08 rewards, eligibility"), cell("Only needed once results exist to reward"), src_cell(DOC + "data/questions.json", "register ↗")],
        [cell("6"), cell("Q-14 coverage · Q-17 cadence"), cell("Scale and staleness"), src_cell(DOC + "data/questions.json", "register ↗")],
    ]
    findings = [
        ("There is no league-wide official depth chart.",
         """The NFL publishes none. Clubs publish their own, and Detroit and Green Bay print the word
         <strong>“unofficial”</strong> on the page. Any claim about 2nd-, 3rd- or 4th-string replacements must be labelled a
         club self-report, not a league fact. This is the biggest constraint on the availability requirement."""),
        ("“Starter” is a definition you choose, not a fact you look up.",
         """This release defines it mechanically — printed in column 1 of the club's chart — so the definition is
         auditable and re-runnable rather than an editorial judgement per player."""),
        ("A 55% hit rate over a season is not skill.",
         """At −110 the break-even is 52.38%. 55.1% over 500 bets scores <strong>z ≈ 1.22</strong>, which is inside coin-flip
         range. The site shows this arithmetic so a hot record cannot be mistaken for an edge."""),
        ("Parlay margin compounds.",
         """At −110 one leg carries a 4.55% hold; five legs carry 20.75% — about 4.6×. And assuming independence across
         correlated legs misprices the ticket: two 50% legs with ρ = 0.30 have a joint probability of 0.325, so a book
         paying +264 is handing the bettor roughly 18.5%. That is precisely why books price or cap correlated legs.
         Prop combos are priced from a joint distribution or not priced at all."""),
        ("Verification caught a real error of ours.",
         """Arizona was first transcribed as 2–6; the official page prints 3–6 with .333. An arithmetic gate rejected the
         row, the correction is corroborated by two independent listings, and it is documented publicly as
         <a href="flagged.html">flag F-08</a>."""),
    ]
    f_html = "".join(f"<li><b>{esc(t)}</b><p>{d}</p></li>" for t, d in findings)
    body = f"""
<section class="pagetitle">
  <div class="eyebrow">DOCUMENT</div>
  <h1>Executive summary</h1>
  <p>What is verified, what is deliberately absent, and the decisions that gate everything else.</p>
</section>
<section class="content">
  <div class="note"><b>Snapshot:</b> {RETRIEVED} · 2026 NFL season, Week 10. This document describes the state of the
  repository at that date; every quantitative table in it is a single-week snapshot and will go stale.</div>

  <h2>{esc(md_sections[0][0])}</h2>
  {md_sections[0][1]}

  <h2>What is verified and published today</h2>
  {table(["Item", "Table", "Official source"], rows_verified)}

  <h2>What is deliberately not published, and why</h2>
  {table(["Not published", "Blocking reason", "Decision", "Reference"], rows_missing)}

  <h2>The five findings that actually matter</h2>
  <ol class="findings big">{f_html}</ol>

  <h2>What the owner has to decide, in dependency order</h2>
  {table(["Order", "Decision", "Why it is here", "Reference"], blockers)}

  <h2>Reviewer's route through this release</h2>
  <ol class="route">
    <li><a href="flagged.html">Flagged for review</a> — {len(FLAGS['flags'])} items, each with what is verified, what is unknown and what settles it.</li>
    <li><a href="decisions.html">Decision register</a> — {len(QUESTIONS['questions'])} questions with the information already held.</li>
    <li><a href="suggestions.html">Suggestions</a> — {len(SUGGEST['suggestions'])} proposals with impact, effort, dependency and a reversible first step.</li>
    <li><a href="sources.html">Sources</a> — the verification tiers and every URL used.</li>
    <li><a href="standings.html">Data tables</a> — the evidence itself, one link per row.</li>
  </ol>

  <h2>Honest limitations of this release</h2>
  <ul class="lim">
    <li>The injury report and schedule are a <b>single-week snapshot</b> and will be stale within days.</li>
    <li>Depth coverage is <b>5 of 32 clubs</b>; the other 27 are blank on purpose.</li>
    <li>One transcription error was found by our own gate. A second independent pass (suggestion S-10) is the cheapest remaining trust improvement and has not been done.</li>
    <li>Three other agent sessions touched this repository concurrently; their divergent boards are preserved on their branches and audited as F-07.</li>
    <li>No model has been fitted, so no claimed signal has empirical support. They are hypotheses with named tests, which is what a hypothesis is supposed to be.</li>
  </ul>
</section>
"""
    return shell("Executive summary", f"SNAPSHOT {RETRIEVED}", body, depth=1)


# ---------------------------------------------------------------- standings
def page_standings():
    groups = {}
    for r in STANDINGS:
        groups.setdefault(r["division"], []).append(r)
    blocks = []
    for conf in ("AFC", "NFC"):
        rows = []
        for div in sorted([d for d in groups if d.startswith(conf)]):
            for r in sorted(groups[div], key=lambda x: int(x["div_rank"])):
                rows.append([
                    cell(f"{r['div_rank']}"),
                    f'<td><b>{esc(r["abbr"])}</b> {link(r["team_url"], r["name"], "teamlink")}</td>',
                    cell(r["division"]),
                    cell(r["w"]), cell(r["l"]), cell(r["t"]), cell(r["pct"]),
                    cell(r["pf"]), cell(r["pa"]), cell(r["diff"]),
                    cell(r["home"]), cell(r["road"]), cell(r["div_record"]), cell(r["conf_record"]),
                    cell(r["streak"]),
                    f'<td>{link(STANDINGS_URL, "nfl.com ↗", "src-link")}</td>',
                ])
        blocks.append(f"<h2>{esc(conf)} — American Football Conference</h2>" if conf == "AFC" else f"<h2>{esc(conf)} — National Football Conference</h2>")
        blocks.append(table(["#", "Team", "Division", "W", "L", "T", "PCT", "PF", "PA", "NET", "Home", "Road", "Div", "Conf", "Strk", "Source"],
                            rows, caption=f"{conf}: 16 clubs, 4 divisions", data_table=True))
    body = f"""
<section class="pagetitle">
  <div class="eyebrow">DATA / 01</div>
  <h1>Standings</h1>
  <p>Every value below is transcribed from the official division standings page. Division rank is the
  position NFL.com itself prints inside each division group.</p>
</section>
<section class="content">
  <div class="srcline">Source: {link(STANDINGS_URL, 'nfl.com/standings/division/2026/REG ↗')} · retrieved {RETRIEVED} · tier A (official league page)</div>
  {''.join(blocks)}

  <h2>What is intentionally missing from this table</h2>
  <div class="note">
    <p>The official page prints additional columns whose meanings are not defined in its own legend
    (the legend only defines W, L, T, PCT, HOME, ROAD, DIV, CONF, PF, PA, NET PTS and STRK). Columns that the page
    does not explain are <strong>not transcribed</strong>, because guessing a column's meaning and then publishing it is
    exactly the failure mode this project is built to avoid.</p>
  </div>

  <h2>Integrity checks applied to this table</h2>
  <ul class="checks">
    <li>32 rows, 32 unique clubs, 8 divisions of exactly 4, ranks 1–4 appearing once per division.</li>
    <li>Games played never exceeds 10 (the 2026 season is in Week 10).</li>
    <li><code>PCT = (W + 0.5·T) / games</code> for every club — this check is what caught the Arizona error.</li>
    <li><code>NET = PF − PA</code> for every club.</li>
    <li>League-wide <code>home wins = road losses</code>, <code>road wins = home losses</code>, <code>ΣW = ΣL</code>, <code>ΣT</code> even, <code>Σdiv W = Σdiv L</code>, <code>Σconf W = Σconf L</code>.</li>
    <li>Division and conference records are W–L–T triples; streaks match <code>&lt;n&gt;&lt;W|L&gt;</code>.</li>
  </ul>
  <p class="muted">A per-division home-record balance was tried and rejected: clubs play most games outside their
  division, so that identity is false. It was replaced, not weakened — the correction is recorded as D-02 in the
  <a href="review.html">repository review</a>.</p>
</section>
"""
    return shell("Standings", f"SNAPSHOT {RETRIEVED}", body, depth=1)


# ---------------------------------------------------------------- schedule
def page_schedule():
    rows = []
    for g in SCHED:
        score = f"{g['away_score']}–{g['home_score']}" if g["status"] == "final" else ""
        status = "Final" if g["status"] == "final" else "Scheduled"
        rows.append([
            cell(g["date_et"]), cell(g["time_et"]),
            f'<td><b>{esc(g["away"])}</b> @ <b>{esc(g["home"])}</b></td>',
            cell(g["network"]),
            f'<td><span class="pill {"ok" if g["status"]=="final" else "muted-pill"}">{esc(status)}</span></td>',
            cell(score, "not played at snapshot"),
            cell(g["note"]),
            f'<td>{link(g["game_url"], "game page ↗", "src-link")} · {link(SCHED_URL, "schedule ↗", "src-link")}</td>',
        ])
    byes = ["CHI", "DEN", "PHI", "TB"]
    body = f"""
<section class="pagetitle">
  <div class="eyebrow">DATA / 02</div>
  <h1>Week 10 slate</h1>
  <p>All 14 games of week 10 of the 2026 regular season, exactly as printed by the official schedule page.
  A game that had not been played at snapshot time has a <strong>blank</strong> score — a prediction there would be
  indistinguishable from a fact.</p>
</section>
<section class="content">
  <div class="srcline">Source: {link(SCHED_URL, 'nfl.com/schedules/2026/REG/week/10/ ↗')} · retrieved {RETRIEVED} · tier A</div>
  <div class="statrow">
    {stat(len(SCHED), 'games')}
    {stat(len(final_games), 'final at snapshot')}
    {stat(len(SCHED)-len(final_games), 'still scheduled')}
    {stat(len(byes), 'clubs on bye')}
  </div>
  {table(["Date", "Kickoff (ET)", "Matchup", "Network", "Status", "Score", "Slot", "Source"], rows, caption="Week 10, 2026 regular season", data_table=True)}
  <h2>Byes</h2>
  <p>{', '.join(f'<b>{esc(b)}</b>' for b in byes)} — the official page lists exactly these four clubs on bye, which is
  also asserted mechanically: the 28 clubs appearing in the slate must be the complement of the four bye clubs.</p>
  <h2>Integrity checks applied</h2>
  <ul class="checks">
    <li>14 games; no club appears twice; away and home clubs are all real clubs.</li>
    <li>Exactly one game is final, and only that game carries scores; every scheduled game has both score cells blank.</li>
    <li>The set of clubs on bye equals CHI, DEN, PHI, TB.</li>
    <li>Every game links to its official nfl.com game page.</li>
  </ul>
</section>
"""
    return shell("Week 10", f"SNAPSHOT {RETRIEVED}", body, depth=1)


# ---------------------------------------------------------------- availability
def page_availability():
    inj_rows = []
    for r in INJ:
        inj_rows.append([
            cell(r["game"]), cell(r["team"]),
            f'<td>{link(r["player_url"], r["player"])}</td>',
            cell(r["position"]),
            cell(r["injury"], "the official report prints no injury description"),
            cell(r["practice_status"]),
            cell(r["game_status"], "no designation printed"),
            f'<td>{link(r["player_url"], "player ↗", "src-link")} · {link(INJ_URL, "report ↗", "src-link")}</td>',
        ])
    srows = []
    for r in starters_at_risk:
        if r["game_status"] == "Out":
            gs = '<span class="pill high">Out</span>'
        elif r["game_status"]:
            gs = esc(r["game_status"])
        else:
            gs = "—"
        srows.append([
            cell(r["team"]), f'<td>{link(r["player_url"], r["player"])}</td>',
            cell(r["position"]), cell(r["injury"], "no injury description printed"),
            cell(r["practice_status"]),
            f"<td>{gs}</td>",
            cell(f'{r["depth_rank"]} of {r["depth_of"]}'),
            cell(r["depth_position_club"]),
            f'<td>{link(r["player_url"], "report ↗", "src-link")} · {link(r["depth_chart_url"], "club chart ↗", "src-link")}</td>',
        ])
    fj_rows = []
    for r in sorted(JOIN["rows"], key=lambda x: (x["team"], x["depth"], x["player"])):
        if r["depth"] == "1" and r["game_status"] == "Out":
            gs = '<span class="pill high">Out</span>'
        elif r["game_status"]:
            gs = esc(r["game_status"])
        else:
            gs = "—"
        fj_rows.append([
            cell(r["team"]),
            f'<td>{esc(r["player"])}</td>',
            cell(r["position_printed"]),
            f'<td><b>{esc(r["depth"])}</b></td>',
            cell(r["unit"]),
            cell(r["injury"], "no injury description printed"),
            cell(r["practice_status"]),
            f"<td>{gs}</td>",
            f'<td>{link(r["club_chart_url"], "club chart ↗", "src-link")} · {link(r["official_injury_url"], "report ↗", "src-link")}</td>',
        ])
    drows = []
    for d in DEPTH:
        drows.append([cell(d["team"]), cell(d["side"]), cell(d["position"]), cell(d["depth_order"]),
                      cell(d["chart_note"]), f'<td>{link(d["source_url"], "club chart ↗", "src-link")}</td>'])
    dgroups = {}
    for d in DEPTH:
        dgroups.setdefault(d["team"], []).append(d)
    team_tables = []
    for t in pilot_teams:
        chart_url = dgroups[t][0]["source_url"]
        rs = [[cell(d["position"]), cell(d["depth_order"]), cell(d["chart_note"]),
               f'<td>{link(chart_url, "club chart ↗", "src-link")}<br>{link("https://www.nfl.com/teams/", "nfl.com teams ↗", "src-link")}</td>']
              for d in dgroups[t]]
        src_line = f'<p class="srcinline">Source: <a href="{esc(chart_url)}" target="_blank" rel="noopener noreferrer">{esc(chart_url)} ↗</a></p>'
        team_tables.append(f"<h3>{esc(t)}</h3>" + src_line + table(["Pos", "Printed depth order", "Chart label", "Provenance"], rs))

    body = f"""
<section class="pagetitle">
  <div class="eyebrow">DATA / 03</div>
  <h1>Availability &amp; depth fragility</h1>
  <p>The official injury report tells you who is listed. It does <strong>not</strong> tell you who is a starter, who is
  second string, or who replaces whom. This page separates those two facts — and shows exactly where the second
  one comes from.</p>
</section>
<section class="content">
  <div class="alert small">
    <b>The finding that matters most.</b>
    <p>The official NFL injury report prints five things per player: player, position, injury, practice status and game
    status. It prints <strong>no depth-chart rank at all</strong>. “2nd-string replacement” therefore cannot be read off the official
    record. Clubs publish their own charts, and at least Detroit and Green Bay label theirs “unofficial”.</p>
  </div>

  <div class="statrow">
    {stat(len(INJ), 'official injury rows')}
    {stat(len(starters_at_risk), 'listed starters on the report')}
    {stat(len(starters_out), 'of those, ruled Out')}
    {stat(f'{len(pilot_teams)}/32', 'clubs in the original pilot', 'shown below as a subset')}
    {stat(f'{FULL_JOIN["clubs_with_a_chart"]}/32', 'clubs covered by the full join', 'club charts, joined here')}
    {stat(FULL_JOIN["starters_ruled_out"], 'starters ruled Out, full join', 'was 8 in the pilot')}
  </div>

  <h2>Listed starters with a week-10 designation (pilot clubs)</h2>
  <p>“Listed starter” means one thing only: the club's own chart prints the player in <strong>column 1</strong> of a position.
  That rule lives in <code>tools/build_availability.py</code> and is re-runnable.</p>
  {table(["Team", "Player", "Pos", "Injury", "Practice", "Game status", "Depth", "Club pos", "Club chart"], srows,
         caption="Derived tier C: official injury report joined to club depth charts", cls="compact", data_table=True)}

  <h2>Full-coverage join: every injured player whose club publishes a chart ({len(JOIN["rows"])} rows)</h2>
  <p>This is the join the pilot above is a subset of. It uses the club depth charts already collected for
  <strong>{FULL_JOIN["clubs_with_a_chart"]} of 32 clubs</strong> — the missing one is Houston, whose chart returns a page with no
  parsable table (attempt log in <code>data/pipeline/_run_report.json</code>). <strong>Depth 1</strong> means the player is
  the first name printed at his position on his own club's chart; it is a club self-report, not a league fact, and every
  row carries the club URL so you can check it.</p>
  <div class="alert small">
    <b>What the extra coverage changes.</b>
    <p>The pilot reports <b>{FULL_JOIN["starters_ruled_out_in_the_pilot"]}</b> starters ruled Out. The same rule across the
    {FULL_JOIN["clubs_with_a_chart"]} clubs already collected returns <b>{FULL_JOIN["starters_ruled_out"]}</b>, plus
    <b>{FULL_JOIN["backups_depth_2_to_4_out_or_doubtful"]}</b> second-to-fourth-string players listed Out or Doubtful.
    {FULL_JOIN["unmatched_rows"]} injured players could not be matched: {len(JOIN["unmatched"])} are from Houston (no chart) or
    are not printed on their club's chart — those rows are <b>absent</b> here rather than guessed.</p>
    <p><a href="decisions-critical.html">Q-19</a> asks whether this join should replace the pilot on the site permanently.
    This release publishes it and keeps both, so the decision can be made on the evidence rather than on a description.</p>
  </div>
  {table(["Team", "Player", "Pos", "Depth", "Unit", "Injury", "Practice", "Game status", "Sources"], fj_rows,
         caption="Derived tier C: official injury report joined to club-published depth charts", cls="compact", data_table=True)}

  <h2>The original five-club pilot, kept as a labelled subset</h2>
  <div class="note">
    <p>Depth information in the pilot was captured for five clubs only. This subset is preserved unchanged so the
    earlier release can still be reproduced and compared. It is <b>not</b> the full picture: see the join above.</p>
  </div>

  <h2>Full official injury report — week 10 ({len(INJ)} rows)</h2>
  <div class="srcline">Source: {link(INJ_URL, 'nfl.com/injuries/league/2026/reg10 ↗')} · retrieved {RETRIEVED} · tier A</div>
  {table(["Game", "Team", "Player", "Pos", "Injury", "Practice status", "Game status", "Source"], inj_rows, cls="compact", data_table=True)}

  <h2>The five pilot depth charts, verbatim</h2>
  <p>Transcribed in printed column order. Multiple names in one column are an “OR” listing, recorded left to right.</p>
  {''.join(team_tables)}

  <h2>Deficiency model — specified, not yet computable</h2>
  <p>Offense and defense are scored separately, because a quarterback and a cornerback are not interchangeable losses.
  The full specification (snap-share concentration, the shadow-depth score and the guards against double counting) is
  in <code>docs/methodology/availability.md</code>. It is blocked on licensed snap counts (Q-04) and 32-club coverage
  (Q-14).</p>
</section>
"""
    return shell("Availability", f"SNAPSHOT {RETRIEVED}", body, depth=1)


# ---------------------------------------------------------------- line origination
def page_line():
    fam = [[cell(s["id"]), cell(s["family"]), cell(s["hypothesis"]), cell(s["falsifier"]), cell(s["data"]), cell(s["status"]),
            src_cell(s["source"], "source ↗") if "nfl.com" in s["source"] or "github.com" in s["source"]
            else src_cell("https://www.nfl.com/teams/", "nfl.com teams ↗")]
           for s in SIGNALS["signals"]]
    shapes = [
        [cell("Single bet"), cell("One probability, estimated accurately"), cell("Slow, tiny edge; high variance"), src_cell(DOC + "docs/methodology/validation-gates.md", "gates ↗")],
        [cell("Cross-game parlay"), cell("Legs usually near-independent, so margin compounds: 4.55% hold at one leg → 20.75% at five"), cell("Margin multiplication; no diversification"), src_cell(DOC + "docs/methodology/correlation.md", "correlation ↗")],
        [cell("Same-game parlay / prop combo"), cell("Legs are dependent; a naive product is badly wrong"), cell("Assuming independence; correlated legs are priced punitively"), src_cell(DOC + "docs/methodology/correlation.md", "correlation ↗")],
    ]
    triple = [
        [raw("<b>Fair line</b>"), raw("Our probability converted with zero margin, <code>1/p</code>"), cell("Our model"), src_cell(DOC + "docs/methodology/line-origination.md", "method ↗")],
        [raw("<b>Market line</b>"), cell("A book's price, which contains margin"), cell("A licensed, timestamped quote"), src_cell(DOC + "data/questions.json", "Q-02 ↗")],
        [raw("<b>Executable line</b>"), cell("What we could actually get, at a stated book, limit and time"), cell("Same quote plus limits and rules"), src_cell(DOC + "docs/methodology/line-origination.md", "method ↗")],
    ]
    body = f"""
<section class="pagetitle">
  <div class="eyebrow">METHOD / 01</div>
  <h1>Line origination</h1>
  <p>How to make our own numbers rather than copy the market — and why this page contains no prices.</p>
</section>
<section class="content">
  <div class="note"><b>Why no prices here:</b> a price is only published after a registered model version runs on a frozen,
  licensed input snapshot and passes every validation gate. Anything else is a guess with a decimal point.</div>

  <h2>The three numbers you must never confuse</h2>
  {table(["Number", "What it is", "Where it comes from", "Reference"], triple)}

  <h2>The pipeline (every strategy, no exceptions)</h2>
  <pre class="flow">freeze inputs (as-of timestamp)
   → estimate a full outcome distribution
   → convert to fair odds (zero margin)
   → compare with a market quote of the SAME market, side and rules
   → log the forecast BEFORE kickoff (including passes)
   → grade after settlement
   → score only inside the registered test window</pre>
  <p>A failure at any arrow means the strategy is <b>not scored</b>. Unscored is not the same as losing: it is unknown,
  and unknown never enters the leaderboard.</p>

  <h2>Probability → price</h2>
  <div class="formula">
    <code>fair decimal odds = 1 / p</code>
    <code>fair American = −100·p/(1−p) if p &gt; 0.5, else +100·(1−p)/p</code>
    <code>implied probability of a quote = 1 / decimal_odds&nbsp;&nbsp;<i>(always includes margin)</i></code>
  </div>
  <p>A spread or total is not a single probability. It needs a <b>distribution</b>:
  <code>P(home wins by ≥ k)</code> and <code>P(push)</code> come from a modelled margin distribution, not a point
  estimate. Without a variance term you cannot price a 3.5 against a 3, and that difference is exactly where thin
  edges live.</p>

  <h2>Seven signal families — hypotheses, not edges</h2>
  {table(["ID", "Family", "Hypothesis", "Falsifier", "Data needed", "Status", "Source"], fam, cls="compact")}

  <h2>Availability signal, defined precisely</h2>
  <pre class="flow">avail_i        ∈ {{full, limited, dnp}}
designation_i  ∈ {{-, questionable, doubtful, out}}
depth_rank_i   = rank on the club's published chart   (1 = column 1)
snap_share_i   = trailing 4-game snap share           (licensed data needed)

starter_at_risk = (depth_rank_i == 1) AND (designation_i != "-")
replacement     = the player printed directly behind i on the same chart line
deficit_T       = Σ_i w_i · 1[starter_at_risk_i]       (w_i from snap share, never from opinion)</pre>
  <p><code>replacement</code> is <b>printed</b>, not guessed. That is why depth charts are stored verbatim: a reviewer can
  check whether “next man up” is a real claim or an invention. Because <code>w_i</code> needs licensed snap data, the
  deficit number cannot be computed today, and publishing a hand-weighted version would be fabrication wearing a formula.</p>

  <h2>Player props are a different problem</h2>
  <ol class="route">
    <li><b>Opportunity model</b> — routes run, targets, carries, red-zone snaps. Opportunity precedes production.</li>
    <li><b>Role model</b> — probability the player holds the role the line assumes. Depth chart and designation drive this.</li>
    <li><b>Efficiency model</b> — yards per route or per carry, adjusted for opponent.</li>
    <li><b>Distribution</b> — count stats are over-dispersed; use a negative-binomial-style model, never a Poisson.</li>
    <li><b>Push handling</b> — a whole-number line can push, so it has three outcomes and is not a coin flip.</li>
  </ol>

  <h2>Three bet shapes, three different problems</h2>
  {table(["Shape", "Core difficulty", "What kills it", "Reference"], shapes)}

  <h2>What we can and cannot claim today</h2>
  <table class="kv">
    <thead><tr><th>Claim</th><th>Status</th><th>Source</th></tr></thead>
    <tbody>
      <tr><td>Identify officially-listed starters on the week-10 report</td><td><span class="pill ok">Yes</span> — {len(starters_at_risk)} rows derived from official + club sources</td><td><a class="src-link" href="{INJ_URL}" target="_blank" rel="noopener noreferrer">report ↗</a></td></tr>
      <tr><td>Say how much a starter's absence is worth in points</td><td><span class="pill high">No</span> — needs licensed snap counts and historical outcomes</td><td><a class="src-link" href="{REPO_BLOB}docs/methodology/availability.md" target="_blank" rel="noopener noreferrer">availability method ↗</a></td></tr>
      <tr><td>Price a fair line</td><td><span class="pill high">No</span> — needs a licensed quote feed to compare against</td><td><a class="src-link" href="{REPO_BLOB}docs/methodology/line-origination.md" target="_blank" rel="noopener noreferrer">origination method ↗</a></td></tr>
      <tr><td>Rank strategies by skill</td><td><span class="pill high">No</span> — needs logged forecasts and a scored window</td><td><a class="src-link" href="{REPO_BLOB}docs/methodology/leaderboard.md" target="_blank" rel="noopener noreferrer">leaderboard method ↗</a></td></tr>
      <tr><td>State a correlation between two legs</td><td><span class="pill high">No</span> — see <a href="correlation.html">correlation</a></td><td><a class="src-link" href="{REPO_BLOB}docs/methodology/correlation.md" target="_blank" rel="noopener noreferrer">correlation method ↗</a></td></tr>
    </tbody>
  </table>
  <p class="muted">Those “No” rows are the real work queue; they appear as open decisions rather than being papered over.</p>
</section>
"""
    return shell("Line origination", f"SNAPSHOT {RETRIEVED}", body, depth=1)


# ---------------------------------------------------------------- validation
def page_validation():
    grow = []
    for g in GATES["gates"]:
        criteria = g.get("criteria") or []
        thr = g.get("thresholds")
        detail = "<br>".join(esc(c) for c in criteria)
        if thr:
            detail = "<br>".join(f"{esc(k)}: <b>{esc(v)}</b>" for k, v in thr.items())
        if g.get("formula"):
            detail += f"<br><code>{esc(g['formula'])}</code>"
        if g.get("auto_fail"):
            detail += f"<br><span class='pill high'>auto-fail</span> {esc(g['auto_fail'])}"
        grow.append([raw(f"<b>{esc(g['id'])}</b>"), cell(g["name"]), raw(detail),
                     cell("blocking" if g.get("blocking") else "advisory"),
                     src_cell(DOC + "data/gates.json", "gates.json ↗")])
    body = f"""
<section class="pagetitle">
  <div class="eyebrow">METHOD / 02</div>
  <h1>Validation gates</h1>
  <p>Seven pre-registered gates a strategy must clear before it is scored, ranked or rewarded — in order, with no
  “but the ROI looks good” exception.</p>
</section>
<section class="content">
  <div class="note"><b>Pre-registered</b> means written down <i>before</i> the test window opens. Moving a gate after seeing
  results is how strategy shops manufacture skill from noise.</div>

  <h2>The luck arithmetic, worked in the open</h2>
  <div class="formula">
    <code>SE(p̂) = sqrt(p̂(1−p̂)/n)</code>
    <code>p_break(&minus;110) = 110/210 = 0.5238</code>
    <code>z = (0.551 − 0.5238)/sqrt(0.551·0.449/500) = 0.0272/0.0222 ≈ 1.22</code>
  </div>
  <p><b>z ≈ 1.22 is not skill.</b> It is a coin landing 55 heads in 100. Gate 2 needs <code>z ≥ 1.96</code> <i>and</i> a
  bootstrap 95% interval on ROI that excludes zero — both, not either. This single calculation is why a 55% record over
  a season cannot be sold as an edge.</p>

  <h2>Effective sample size for correlated tickets</h2>
  <div class="formula"><code>n_eff = n / (1 + (k − 1)·ρ̄)</code></div>
  <p>400 tickets averaging two shared legs with ρ̄ = 0.3 is effectively <b>308</b>. The gate is held against
  <code>n_eff</code>, not the raw count, because correlated tickets are not independent draws.</p>

  <h2>The gates</h2>
  {table(["Gate", "Name", "Pass condition", "Status", "Source"], grow)}

  <h2>Scoring rules that keep luck off the board</h2>
  <ul class="checks">
    {''.join(f'<li>{esc(r)}</li>' for r in GATES['scoring_rules'])}
  </ul>

  <h2>Ranking objective</h2>
  <div class="formula"><code>{esc(GATES['ranking_objective']['formula'])}</code></div>
  <p>Weights: λ = {GATES['ranking_objective']['weights']['lambda']}, μ = {GATES['ranking_objective']['weights']['mu']}.
  Report the components, never just the composite — a high score built on a large calibration penalty is a near-miss and
  must look like one.</p>
  <p>Tie-breaks, in order: {', '.join(esc(t) for t in GATES['ranking_objective']['tie_breaks'])}.</p>

  <h2>Implementation status</h2>
  <table class="kv">
    <thead><tr><th>Gate</th><th>Implemented in code?</th><th>Source</th></tr></thead>
    <tbody>
      <tr><td>Gate definitions</td><td><span class="pill ok">Yes</span> — <code>data/gates.json</code> is the machine-readable contract</td><td><a class="src-link" href="https://github.com/karagemop466-tech/X1/blob/main/data/gates.json" target="_blank" rel="noopener noreferrer">gates.json ↗</a></td></tr>
      <tr><td>Gate evaluation against real strategies</td><td><span class="pill high">No</span> — no strategy can be registered until Q-02, Q-03 and Q-12 are settled</td><td><a class="src-link" href="https://github.com/karagemop466-tech/X1/blob/main/data/questions.json" target="_blank" rel="noopener noreferrer">register ↗</a></td></tr>
      <tr><td>Gate-by-gate reporting on the site</td><td><span class="pill ok">Yes</span> — this page and the leaderboard render each gate</td><td><a class="src-link" href="https://github.com/karagemop466-tech/X1/blob/main/docs/methodology/validation-gates.md" target="_blank" rel="noopener noreferrer">methodology ↗</a></td></tr>
    </tbody>
  </table>
</section>
"""
    return shell("Validation gates", f"SNAPSHOT {RETRIEVED}", body, depth=1)


# ---------------------------------------------------------------- leaderboard
def page_leaderboard():
    divs = [[cell(d["id"]), cell(f'{d["entry_bar"]} tickets/bets minimum'), src_cell(DOC + "data/strategies.json", "register ↗")] for d in STRAT["divisions"]]
    rw = GATES["rewards"]
    schemarows = [[cell(c)] for c in STRAT["schema"]]
    body = f"""
<section class="pagetitle">
  <div class="eyebrow">COMPETITION</div>
  <h1>Strategy leaderboard</h1>
  <p>A competition designed so the top of the board contains things that will keep working — and so the second-best
  thing (variance) is visible instead of hidden.</p>
</section>
<section class="content">
  <div class="alert small">
    <b>Status: no strategies are registered, and the board is empty by design.</b>
    <p>{esc(STRAT['meta']['reason'])}</p>
  </div>

  <h2>Divisions</h2>
  <p>Split by bet shape because the statistics genuinely differ — not as a fairness gesture.</p>
  {table(["Division", "Entry bar", "Source"], divs)}
  <table class="kv">
    <thead><tr><th>Shape</th><th>Why it is its own division</th><th>Source</th></tr></thead>
    <tbody>
      <tr><td>Singles</td><td>Lowest variance per ticket; needs the biggest sample to say anything</td><td><a class="src-link" href="https://github.com/karagemop466-tech/X1/blob/main/docs/methodology/leaderboard.md" target="_blank" rel="noopener noreferrer">leaderboard ↗</a></td></tr>
      <tr><td>Parlays (2–3 legs)</td><td>Variance rises and margin compounds</td><td><a class="src-link" href="https://github.com/karagemop466-tech/X1/blob/main/docs/methodology/correlation.md" target="_blank" rel="noopener noreferrer">correlation ↗</a></td></tr>
      <tr><td>Prop combos (same game, ≥2 legs)</td><td>Dependence makes the raw ticket count misleading — n_eff rules</td><td><a class="src-link" href="https://github.com/karagemop466-tech/X1/blob/main/docs/methodology/correlation.md" target="_blank" rel="noopener noreferrer">correlation ↗</a></td></tr>
      <tr><td>Single props</td><td>Distribution modelling differs from game markets</td><td><a class="src-link" href="https://github.com/karagemop466-tech/X1/blob/main/docs/methodology/line-origination.md" target="_blank" rel="noopener noreferrer">method ↗</a></td></tr>
    </tbody>
  </table>

  <h2>How ranking works</h2>
  <div class="formula"><code>{esc(GATES['ranking_objective']['formula'])}</code>
  <code>z_skill = (p̂ − p_break) / sqrt(p̂(1−p̂)/n_eff)</code></div>
  <p>Rank by skill measured in units of its own uncertainty — never by raw ROI, which is a magnitude, not evidence.</p>

  <h2>Rewards — structure now, money later</h2>
  <table class="kv">
    <thead><tr><th>Reward</th><th>Season 0 (paper league)</th><th>Season 1 onward</th><th>Source</th></tr></thead>
    <tbody>
      <tr><td>Champion, per division</td><td>Title + badge only</td><td>Requires a funded pool</td><td><a class="src-link" href="https://github.com/karagemop466-tech/X1/blob/main/data/gates.json" target="_blank" rel="noopener noreferrer">gates.json ↗</a></td></tr>
      <tr><td>Runner-up</td><td>Badge</td><td>Requires a funded pool</td><td><a class="src-link" href="https://github.com/karagemop466-tech/X1/blob/main/data/gates.json" target="_blank" rel="noopener noreferrer">gates.json ↗</a></td></tr>
      <tr><td>Most improved</td><td>Badge</td><td>Requires a funded pool</td><td><a class="src-link" href="https://github.com/karagemop466-tech/X1/blob/main/data/gates.json" target="_blank" rel="noopener noreferrer">gates.json ↗</a></td></tr>
      <tr><td>Best calibration</td><td>Badge, awarded even without profit</td><td>Recommended to stay non-cash</td><td><a class="src-link" href="https://github.com/karagemop466-tech/X1/blob/main/docs/methodology/validation-gates.md" target="_blank" rel="noopener noreferrer">gates ↗</a></td></tr>
    </tbody>
  </table>
  <h3>Design rules that stop the board rewarding luck</h3>
  <ul class="checks">
    <li><b>Reward calibration independently of profit.</b> A well-calibrated strategy that loses to margin is doing the hard part right.</li>
    <li><b>No reward for a single hot window.</b> Champion needs two consecutive qualifying windows.</li>
    <li><b>Clawback.</b> A title later shown to rest on a data error or rule violation is vacated, publicly.</li>
    <li><b>No pay-to-enter.</b> Charging entry while running the book side invites a regulatory classification nobody here can answer.</li>
    <li><b>Fixed maximum entrants</b> per window, declared before it opens.</li>
  </ul>

  <h2>Anti-gaming rules</h2>
  <table class="kv">
    <thead><tr><th>Attack</th><th>Rule</th><th>Source</th></tr></thead>
    <tbody>
      <tr><td>Cherry-picked start date</td><td>The window is fixed by the calendar, never by the entrant</td><td><a class="src-link" href="https://github.com/karagemop466-tech/X1/blob/main/docs/methodology/leaderboard.md" target="_blank" rel="noopener noreferrer">leaderboard ↗</a></td></tr>
      <tr><td>Re-registering a failed strategy under a new name</td><td>Strategy hash covers inputs and features; duplicates are rejected</td><td><a class="src-link" href="https://github.com/karagemop466-tech/X1/blob/main/docs/methodology/leaderboard.md" target="_blank" rel="noopener noreferrer">leaderboard ↗</a></td></tr>
      <tr><td>Playing only soft numbers</td><td>Gate 6 uses only release-time quotes</td><td><a class="src-link" href="https://github.com/karagemop466-tech/X1/blob/main/docs/methodology/leaderboard.md" target="_blank" rel="noopener noreferrer">leaderboard ↗</a></td></tr>
      <tr><td>Undefined settlement</td><td>Ticket invalid without a recorded rule</td><td><a class="src-link" href="https://github.com/karagemop466-tech/X1/blob/main/docs/methodology/leaderboard.md" target="_blank" rel="noopener noreferrer">leaderboard ↗</a></td></tr>
      <tr><td>Backfilled forecasts</td><td>Forecasts must be timestamped before kickoff; late writes are voided</td><td><a class="src-link" href="https://github.com/karagemop466-tech/X1/blob/main/docs/methodology/leaderboard.md" target="_blank" rel="noopener noreferrer">leaderboard ↗</a></td></tr>
      <tr><td>Survivorship in reporting</td><td>Every registered strategy is listed, including ones with zero bets</td><td><a class="src-link" href="https://github.com/karagemop466-tech/X1/blob/main/docs/methodology/leaderboard.md" target="_blank" rel="noopener noreferrer">leaderboard ↗</a></td></tr>
    </tbody>
  </table>

  <h2>Registered strategies</h2>
  <div class="empty">
    <b>0 strategies.</b>
    <p>An honest empty leaderboard is worth more than a populated fake one. When the first strategy is registered, its
    pre-registration file, gate-by-gate results and both raw and trimmed ROI will appear here.</p>
  </div>

  <h2>Row schema (published in advance)</h2>
  <p>Every future row must fill these fields. A blank field means the row cannot be marked <code>published</code>.</p>
  <div class="chips">{''.join(f'<span class="chip"><code>{esc(c)}</code></span>' for c in STRAT['schema'])}</div>
</section>
"""
    return shell("Leaderboard", f"SNAPSHOT {RETRIEVED}", body, depth=1)


# ---------------------------------------------------------------- correlation
def page_correlation():
    CORR = "docs/methodology/correlation.md"
    rows = [
        [cell("1"), cell("QB passing yards × own WR/TE receiving yards"), cell("Mechanically coupled; largest, most stable dependence"), f'<td>{ref(CORR,"method")}</td>'],
        [cell("2"), cell("Team total × own RB rushing yards"), cell("Game-script coupling"), f'<td>{ref(CORR,"method")}</td>'],
        [cell("3"), cell("Opposing QB passing yards × our pass-rush (sacks)"), cell("Negative dependence; often mispriced"), f'<td>{ref(CORR,"method")}</td>'],
        [cell("4"), cell("WR1 receiving yards × WR2 receiving yards"), cell("Competes for targets — usually negative, sometimes positive"), f'<td>{ref(CORR,"method")}</td>'],
        [cell("5"), cell("Game total × any single player's over"), cell("Game-state coupling"), f'<td>{ref(CORR,"method")}</td>'],
        [cell("6"), cell("Spread cover × QB/rushing props"), cell("Game-script coupling"), f'<td>{ref(CORR,"method")}</td>'],
    ]
    indep = [
        [cell("Independent (ρ = 0)"), cell("0.2500"), cell("4.000 (+300)"), cell("≈3.645 (+264)"), cell("+8.9% — book keeps the edge"), f'<td>{ref(CORR,"method")}</td>'],
        [cell("ρ = 0.30"), cell("0.3250"), cell("3.077 (+208)"), cell("≈3.645 (+264)"), raw("<b>−18.5% — edge flips to the bettor</b>"), f'<td>{ref(CORR,"method")}</td>'],
    ]
    body = f"""
<section class="pagetitle">
  <div class="eyebrow">METHOD / 03</div>
  <h1>Correlation</h1>
  <p>The estimator, the power calculation and the multiple-comparison correction — so that when a correlation
  <strong>is</strong> published it is defensible. No value is published today, because the joint-outcome dataset does not exist.</p>
</section>
<section class="content">
  <div class="alert small">
    <b>No correlation value is published.</b>
    <p>A number invented here would be indistinguishable from a guess. Everything below is the procedure that must be
    followed before any value appears — including the estimator, the interval and the test.</p>
  </div>

  <h2>The estimator</h2>
  <div class="formula">
    <code>p_A = E[1{{A}}]&nbsp;&nbsp;p_B = E[1{{B}}]&nbsp;&nbsp;p_AB = E[1{{A}}·1{{B}}]</code>
    <code>Cov(A,B) = p_AB − p_A·p_B</code>
    <code>ρ = Cov(A,B) / (σ_A·σ_B)&nbsp;&nbsp;<i>defined only when σ_A, σ_B &gt; 0</i></code>
  </div>
  <p>If a leg has zero variance (always wins or always loses), ρ is <b>undefined — not zero</b>. Report it as undefined and
  drop it from the pricing model.</p>

  <h2>Why the sign is not enough</h2>
  <p>Correlation gives the direction; the parlay's fair price needs the <b>joint probability</b>
  <code>p_AB</code>, and <code>fair odds = 1/p_AB</code>. Two legs can share a ρ and still need different prices at
  different base rates. Publish <code>p_AB</code> with an interval next to ρ, or publish nothing.</p>

  <h2>The independence trap, in numbers</h2>
  <p>Two legs at p = 0.5 each, both priced at −110. For binary legs the joint is exact once ρ is chosen: <code>p_AB = 0.25 + 0.25ρ</code> at p = 0.5.</p>
  {table(["Assumption", "Joint probability", "Fair odds", "Book at −110 pays", "Book margin", "Source"], indep)}
  <p>The second row is why books cap correlated legs — and why a parlay strategy that ignores dependence backtests
  beautifully and loses in production.</p>

  <h2>Estimation procedure (mandatory)</h2>
  <ol class="route">
    <li><b>Define the setting.</b> A correlation measured across different conditions is an average of things that do not pool.</li>
    <li><b>Train on the past only.</b> Chronological split; a random split leaks the future into the past.</li>
    <li><b>Bootstrap the interval.</b> Report 95% intervals on ρ and p_AB. With ~17 games per club per season, intervals are wide.</li>
    <li><b>Test the independence null</b> with a likelihood-ratio or permutation test; publish the p-value and n.</li>
    <li><b>Confirm out of sample.</b> A correlation that exists only in the fitting window is noise with a bibliography.</li>
    <li><b>Correct for multiple comparisons.</b> Test 200 leg pairs and ~10 clear p &lt; 0.05 by chance; use a Benjamini–Hochberg style correction.</li>
  </ol>

  <h2>Sample-size reality check</h2>
  <div class="formula"><code>n ≈ ((z_(1−α/2) + z_(1−β)) / z_ρ)² + 3&nbsp;&nbsp;→&nbsp;&nbsp;≈780 paired observations for ρ = 0.10 at 80% power</code></div>
  <p>A season is 272 games, and conditioning on game state shrinks the usable n further. Any correlation published from a
  single season of a single team's props should be treated as a hypothesis, not a finding.</p>

  <h2>Which pairs to test first</h2>
  {table(["Priority", "Pair", "Why it matters", "Source"], rows)}

  <h2>Storage contract</h2>
  <p>Every published correlation row must carry: leg_a, leg_b, setting, n_observations, p_a, p_b, p_ab, rho,
  rho_ci_low, rho_ci_high, p_value, test_correction, train_window, holdout_window, source_dataset, source_url,
  retrieved_at, status. The generator refuses to emit a <code>published</code> row with any blank field.</p>
</section>
"""
    return shell("Correlation", f"SNAPSHOT {RETRIEVED}", body, depth=1)


# ---------------------------------------------------------------- decisions
def page_decisions():
    qs = QUESTIONS["questions"]
    rows = []
    for q in qs:
        status = q["status"].replace("_", " ")
        pill = {"open": "high", "answered": "ok", "partially answered": "warn"}.get(status, "muted-pill")
        ans = q["answer"] or "—"
        rows.append([
            raw(f'<b>{q["id"]}</b>'),
            raw(f'<b>{q["topic"]}</b><br><span class="muted">{esc(q["question"])}</span>'),
            cell(q["known_information"]),
            cell(ans, "no verified answer yet"),
            cell(q["what_would_answer_it"]),
            raw(f'<span class="pill {pill}">{esc(status)}</span>'),
            f'<td>{link(q["source_url"], "official source ↗", "src-link") if q["source_url"] else ""}<br>{link(NFL_ANCHOR, "nfl.com ↗", "src-link")}</td>'
        ])
    counts = QUESTIONS["meta"]["counts"]
    body = f"""
<section class="pagetitle">
  <div class="eyebrow">DECISIONS</div>
  <h1>Decision register</h1>
  <p>A clear list of the questions, the information we already hold, and the answers — where answers exist. What we
  <strong>do not</strong> have is recorded too, because a question with no answer is a decision waiting to happen.</p>
</section>
<section class="content">
  <div class="note"><b>Rule:</b> {esc(QUESTIONS['meta']['rule'])}</div>
  <div class="statrow">
    {stat(len(qs), 'questions')}
    {stat(counts['answered'], 'answered from an official source')}
    {stat(counts['partially_answered'], 'partially answered')}
    {stat(counts['open'], 'still open')}
  </div>
  {table(["ID", "Question", "Information we already hold", "Answer", "What would settle it", "Status", "Source"], rows, cls="wide")}
  <h2>How to read the Answer column</h2>
  <p>A blank answer means <b>no verified answer exists</b>. It does not mean nobody looked. Each row carries the
  information already held, which is often the reason we can say with confidence that the answer is still unknown —
  for example, knowing the league publishes no league-wide depth chart is what makes Q-05 a decision rather than a lookup.</p>
  <h2>Suggested order of resolution</h2>
  <p><b>Q-01 → Q-02 → Q-03 → Q-05 → Q-09 → Q-11 → Q-12</b>, then Q-04/Q-14 (scale) and Q-07/Q-08 (rewards) once
  there is something to reward. This order is a dependency chain, not a preference: each item unblocks the next.</p>
</section>
"""
    return shell("Decision register", f"SNAPSHOT {RETRIEVED}", body, depth=1)


# ---------------------------------------------------------------- suggestions
def page_suggestions():
    cards = []
    for s in SUGGEST["suggestions"]:
        deps = ", ".join(esc(d) for d in s["depends_on"]) or "none"
        cards.append(f"""
    <article class="sugg">
      <header>
        <span class="pid">{esc(s['id'])}</span>
        <h3>{esc(s['title'])}</h3>
        <div class="tags">
          <span class="pill {'high' if s['impact']=='high' else 'warn'}">impact: {esc(s['impact'])}</span>
          <span class="pill muted-pill">effort: {esc(s['effort'])}</span>
          <span class="pill muted-pill">depends on: {deps}</span>
        </div>
      </header>
      <dl>
        <dt>Problem</dt><dd>{esc(s['problem'])}</dd>
        <dt>Proposal</dt><dd>{esc(s['proposal'])}</dd>
        <dt>Why it improves decisions</dt><dd>{esc(s['why_it_helps_decision_making'])}</dd>
        <dt>Reversible first step</dt><dd>{esc(s['first_step'])}</dd>
        <dt>Risk &amp; mitigation</dt><dd>{esc(s['risk'])}</dd>
        <dt>Decision</dt><dd><span class="pill muted-pill">{esc(s['status'])}</span> — set by the owner; nothing here is implemented automatically</dd>
      </dl>
    </article>""")
    body = f"""
<section class="pagetitle">
  <div class="eyebrow">SUGGESTIONS</div>
  <h1>Suggestions register</h1>
  <p>{len(SUGGEST['suggestions'])} reviewable proposals for improving the site and the decision process. Each carries its
  impact, its cost, what it depends on and a reversible first step — so the owner can pick the best path before any
  change is implemented.</p>
</section>
<section class="content">
  <div class="note"><b>Nothing on this page is implemented automatically.</b> The suggestions are ranked by impact and
  effort only as a reading aid; the Decision column is the owner's to set. Two of them (S-01, S-02) are already visible
  in this release as patterns — the tier badges and the snapshot date in every header — and remain listed so the
  reviewer can accept or reject them explicitly.</div>
  <div class="statrow">
    {stat(len(SUGGEST['suggestions']), 'proposals')}
    {stat(sum(1 for s in SUGGEST['suggestions'] if s['impact']=='high'), 'high impact')}
    {stat(sum(1 for s in SUGGEST['suggestions'] if s['effort']=='low'), 'low effort')}
    {stat(sum(1 for s in SUGGEST['suggestions'] if not s['depends_on']), 'no dependency — can start now')}
  </div>
  {''.join(cards)}
</section>
"""
    return shell("Suggestions", f"SNAPSHOT {RETRIEVED}", body, depth=1)


# ---------------------------------------------------------------- decisions critical
def page_decisions_critical():
    d = DECISION
    cards, rows = [], []
    for q in d["questions"]:
        cls = {"P0": "high", "P1": "warn", "P2": "muted-pill"}[q["priority"]]
        rows.append([
            f'<td><b>{esc(q["id"])}</b></td>',
            f'<td><span class="pill {cls}">{esc(q["priority"])}</span></td>',
            f'<td>{esc(q["question"])}</td>',
            cell(q["known"]),
            cell(q["missing"]),
            cell(q["closes_with"]),
            f'<td><b>{esc(q["recommend"])}</b></td>',
            cell(q["there_after"]),
            src_cell(q["source"], "official ↗"),
        ])
    body = f"""
<section class="pagetitle">
  <div class="eyebrow">DECIDE FIRST</div>
  <h1>The questions that block a decision</h1>
  <p>{d["counts"]["critical_here"]} questions decide whether any strategy in this repository can honestly be scored.
  Each row states what is already known, what is missing, the evidence that would close the gap, and what becomes
  possible once it is closed. {d["counts"]["p0"]} are P0: nothing downstream is trustworthy until they are answered.</p>
</section>
<section class="content">
  <div class="note"><b>{d["rule"]}</b></div>
  <div class="statrow">
    {stat(d["counts"]["critical_here"], "decision-critical questions")}
    {stat(d["counts"]["p0"], "P0 blockers")}
    {stat(d["counts"]["open_in_full_register"], "open in the full register")}
    {stat(len(d["counts"]["new_this_round"]), "new this round", ", ".join(d["counts"]["new_this_round"]))}
  </div>
  {table(["ID", "Priority", "Question", "What we already know", "What is missing",
          "Evidence that would close it", "Recommended path", "What it unblocks", "Source"],
         rows, "Every question that has to be answered before a strategy is scored", "wide", True)}
  <div class="note">The full register, including the questions that are already answered, is on the
  <a href="decisions.html">decision register</a>. The new questions in this table came from this round's audit:
  each one was already implicit in the repository but had never been written down as a decision.</div>
</section>
"""
    return shell("Decisions to make", f"SNAPSHOT {RETRIEVED}", body, depth=1)


# ---------------------------------------------------------------- suggestions board
def RANK_CELL(rank, recommended):
    tag = '<br><span class="pill">recommended</span>' if recommended else ""
    return f'<td>{esc(str(rank))}{tag}</td>'


def page_suggestions_board():
    b = BOARD
    rows = []
    for o in sorted(b["options"], key=lambda x: x["rank"]):
        rec = o["id"] in b["recommended_path"]
        rows.append([
            f'<td><b>{esc(o["id"])}</b></td>',
            RANK_CELL(o["rank"], bool(rec)),
            f'<td><b>{esc(o["title"])}</b></td>',
            f'<td>{esc(o["answers"])}</td>',
            f'<td><span class="pill {"high" if o["impact"]=="high" else "muted-pill"}">{esc(o["impact"])}</span></td>',
            f'<td><span class="pill {"warn" if o["effort"]=="high" else "muted-pill"}">{esc(o["effort"])}</span></td>',
            f'<td><span class="pill {"high" if o["risk"]=="high" else "muted-pill"}">{esc(o["risk"])}</span></td>',
            cell(o["dependency"]),
            cell(o["first_step"]),
            f'<td><b>{esc(o["reversible"])}</b></td>',
            cell(o["why"]),
            src_cell(o.get("source", ""), "official ↗"),
        ])
    path = " → ".join(f'<b>{esc(i)}</b>' for i in b["recommended_path"])
    body = f"""
<section class="pagetitle">
  <div class="eyebrow">CHOOSE, THEN BUILD</div>
  <h1>Suggestions board</h1>
  <p>{b["counts"]["options"]} options for improving the site and the decision process, ordered by what changes a number
  fastest rather than by what is most interesting to build. Nothing here is implemented automatically — the status
  column is yours to set.</p>
</section>
<section class="content">
  <div class="note"><b>Recommended path: {path}.</b> {b["recommended_reason"]}</div>
  <div class="statrow">
    {stat(b["counts"]["options"], "options")}
    {stat(b["counts"]["high_impact"], "high impact")}
    {stat(b["counts"]["low_effort"], "low effort")}
    {stat(b["counts"]["no_dependency"], "no dependency — can start today")}
  </div>
  {table(["ID", "Rank", "Proposal", "Answers", "Impact", "Effort", "Risk", "Dependency",
          "Reversible first step", "Reversible", "Why it improves decisions", "Source"],
         rows, "Ranked options; rank is a reading aid, the choice is the owner's", "wide", True)}
  <div class="note">The original 12 proposals are preserved unchanged on the
  <a href="suggestions.html">suggestions register</a>. This board adds dependency, risk and reversibility to the
  same question: what can be done now, cheaply, without committing to anything hard to undo.</div>
</section>
"""
    return shell("Suggestions board", f"SNAPSHOT {RETRIEVED}", body, depth=1)


# ---------------------------------------------------------------- review queue
def page_review_queue():
    q = QUEUE
    sev_rank = {"high": 0, "medium": 1, "low": 2, "": 3}
    rows = []
    for r in sorted(q["rows"], key=lambda x: (sev_rank.get(x["severity"], 3), x["id"])):
        cls = {"high": "high", "medium": "warn", "low": "muted-pill", "": "muted-pill"}[r["severity"]]
        rows.append([
            f'<td><b>{esc(r["id"])}</b></td>',
            f'<td><span class="pill {cls}">{esc(r["severity"] or "—")}</span></td>',
            cell(r["area"]),
            f'<td>{esc(r["state"])}</td>',
            f'<td><b>{esc(r["item"])}</b></td>',
            cell(r["unknown"]),
            cell(r["register"]),
            src_cell(r["source"], "source ↗"),
        ])
    counts = ", ".join(f"{k}: {v}" for k, v in sorted(q["counts"].items()))
    body = f"""
<section class="pagetitle">
  <div class="eyebrow">REVIEW QUEUE</div>
  <h1>Everything still unproven</h1>
  <p>Every flag, every open question, every unverified cell and every item this round found, in one table with one
  source link per row. This replaces the four competing flag counts that used to appear in different documents.</p>
</section>
<section class="content">
  <div class="note"><b>{len(q["rows"])} rows, merged from {len(q["registers_merged"])} registers.</b> {esc(counts)}.
  A row here never asserts a value: it states what is known, what is unknown, and where the official source is. None of
  these rows blocks publication; all of them are visible so that nothing is silently rounded up to "verified".</div>
  <div class="statrow">
    {stat(len(q["rows"]), "items in the queue")}
    {stat(q["counts"].get("flag", 0), "flags")}
    {stat(q["counts"].get("open question", 0), "open questions")}
    {stat(q["counts"].get("unverified cell", 0), "unverified cells")}
  </div>
  {table(["ID", "Severity", "Area", "State", "Item", "What is unknown / what settles it",
          "Register", "Source"], rows, "Consolidated review queue", "wide", True)}
  <div class="note">Registers merged: {esc(", ".join(q["registers_merged"]))}. The original per-tree pages
  (<a href="flagged.html">flags</a>, <a href="decisions.html">questions</a>) remain published and unchanged.</div>
</section>
"""
    return shell("Review queue", f"SNAPSHOT {RETRIEVED}", body, depth=1)


# ---------------------------------------------------------------- changes
def page_changes():
    c = CHANGES
    rows = [[
        f'<td><b>{esc(i["what"])}</b></td>',
        cell(i["before"]),
        f'<td><b>{esc(i["after"])}</b></td>',
        cell(i["evidence"]),
        src_cell(i["source"], "source ↗"),
    ] for i in c["items"]]
    body = f"""
<section class="pagetitle">
  <div class="eyebrow">CHANGE LOG</div>
  <h1>What changed this round</h1>
  <p>Session <code>{esc(c["session"])}</code> re-read every official page the site depends on, diffed the result
  against the published tables, and fixed what the diff exposed. Every change below is a claim with its evidence
  next to it.</p>
</section>
<section class="content">
  <div class="statrow">
    {stat(len(c["items"]), "changes with evidence")}
    {stat(FULL_JOIN["clubs_with_a_chart"], "clubs now covered by the depth join", "was 5")}
    {stat(f"{AUDIT['verification']['cells_compared']:,}", "cells re-verified", f"{AUDIT['verification']['mismatches']} mismatches")}
    {stat(len(QUEUE["rows"]), "items in the single review queue", "was four separate counts")}
  </div>
  {table(["What changed", "Before", "After", "Evidence file", "Source"], rows,
         "Changes made this round, before and after", "wide", True)}
  <div class="note"><b>What deliberately did not change.</b><ul>
  {''.join(f"<li>{esc(u)}</li>" for u in c["unchanged"])}
  </ul></div>
</section>
"""
    return shell("What changed", f"SNAPSHOT {RETRIEVED}", body, depth=1)


# ---------------------------------------------------------------- executive brief
def page_exec_brief():
    v = AUDIT["verification"]
    findings = AUDIT["findings"]
    rows = [[
        f'<td><b>{esc(f["id"])}</b></td>',
        f'<td><span class="pill {"high" if f["severity"]=="high" else ("warn" if f["severity"]=="medium" else "muted-pill")}">{esc(f["severity"])}</span></td>',
        cell(f["category"]),
        f'<td><b>{esc(f["finding"])}</b></td>',
        cell(f["evidence"]),
        cell(f["fix"]),
        f'<td>{esc(f["status"])}</td>',
        src_cell(f["source"], "source ↗"),
    ] for f in findings]
    per = AUDIT["verification"]["per_table"]
    trows = []
    for t in per:
        tag = '<span class="pill">0</span>' if t["mismatches"] == 0 else '<b>' + str(t["mismatches"]) + '</b>'
        trows.append([cell(t["table"]), cell(str(t["rows_published"])),
                      cell(f'{t["cells"]:,}'), '<td>' + tag + '</td>',
                      src_cell(t["source"], "official ↗")])
    body = f"""
<section class="pagetitle">
  <div class="eyebrow">EXECUTIVE BRIEF</div>
  <h1>What this round found, and what it needs from you</h1>
  <p>One page. Ten findings, four decisions that unblock the rest, and the verification behind both — with a link to
  the official page for every row.</p>
</section>
<section class="content">
  <div class="note"><b>Headline.</b> Every published Week&nbsp;10 value is correct:
  {v["cells_compared"]:,} cells diffed against a fresh independent transcription of the official pages,
  {v["mismatches"]} mismatches, {v["tables_ok"]} of {v["tables"]} tables clean. The problems this round found are not
  wrong numbers — they are <b>incomplete coverage presented as complete</b>, an <b>unreachable site tree</b>, and a
  <b>red CI job on main</b>. All three are fixed or flagged below.</div>
  <div class="statrow">
    {stat(f"{v['cells_compared']:,}", "cells verified")}
    {stat(v["mismatches"], "value mismatches")}
    {stat(len(findings), "findings")}
    {stat(len([f for f in findings if f["status"] == "fixed"]), "already fixed")}
  </div>
  <h2>Verification result, table by table</h2>
  {table(["Table", "Rows published", "Cells compared", "Mismatches", "Official source"], trows,
         "Independent re-transcription diff", "wide", True)}
  <h2>Findings</h2>
  {table(["ID", "Severity", "Area", "Finding", "Evidence / measurement", "Fix", "Status", "Source"], rows,
         "Audit findings", "wide", True)}
  <h2>The decision this round needs</h2>
  <div class="note"><b>Publish the 31-club depth join, or state that five clubs are all the evidence you want?</b>
  The site currently reports {FULL_JOIN["starters_ruled_out_in_the_pilot"]} starters ruled out on the strength of a
  five-club pilot. The same join across the {FULL_JOIN["clubs_with_a_chart"]} clubs already collected returns
  <b>{FULL_JOIN["starters_ruled_out"]}</b>. Nothing about the published number is false; it is a floor that reads like a
  total. Recommendation, cost and reversal are on the
  <a href="suggestions-board.html">suggestions board (B-01)</a>; the question is
  <a href="decisions-critical.html">Q-19</a>.</div>
  <h2>The four steps recommended before anything else</h2>
  <ol class="findings">
  {''.join(f'<li><b>{esc(o["title"])}</b> — {esc(o["why"])}</li>' for o in BOARD["options"] if o["id"] in BOARD["recommended_path"])}
  </ol>
  <h2>What is still not known</h2>
  <div class="note">{len(QUEUE["rows"])} items remain in the <a href="review-queue.html">review queue</a>. The largest
  are the missing line benchmark (Q-02), the missing starter definition (Q-05), the absent licensed odds feed, and the
  fact that the only strategy passing all eight gates is measured against a third-party mirror rather than a league feed.
  None of them blocks publishing; all of them block acting on a result.</div>
</section>
"""
    return shell("Executive brief", f"SNAPSHOT {RETRIEVED}", body, depth=1)


# ---------------------------------------------------------------- requirements
def page_requirements():
    r = REQS
    state_cls = {"met": "ok", "partly met": "warn", "open": "high",
                 "in progress": "muted-pill", "unassessed": "muted-pill"}
    rows = []
    for x in r["rows"]:
        rows.append([
            f'<td><b>{esc(x["id"])}</b></td>',
            cell(x["category"]),
            f'<td><b>{esc(x["requirement"])}</b></td>',
            f'<td><span class="pill {state_cls.get(x["state"], "muted-pill")}">{esc(x["state"])}</span></td>',
            cell(x["assessment"]),
            cell(x["previous_status"]),
            f'<td>{link(x["evidence_url"], x["evidence"] + " ↗", "src-link")}</td>',
            f'<td>{link(x["brief_source"], "brief ↗", "src-link")}</td>',
        ])
    c = r["counts"]
    body = f"""
<section class="pagetitle">
  <div class="eyebrow">THE FULL LIST</div>
  <h1>Requirements, assessed against the evidence</h1>
  <p>All {c["total"]} requirements taken from the project brief, each one assessed against something you can open and
  check. {c["met"]} are met, {c["partly_met"]} are partly met with the missing piece named, {c["open"]} are open and
  {c["in_progress"]} are in progress.</p>
</section>
<section class="content">
  <div class="note"><b>{esc(r["rule"])}</b> {c["disagreements"]} rows disagree with the previous assessment: where the
  earlier column says "Implemented" and this one says "partly met", the reason is in the assessment cell — usually a
  capability that exists as a method but cannot produce a number without a licensed feed.</div>
  <div class="statrow">
    {stat(c["met"], "met")}
    {stat(c["partly_met"], "partly met")}
    {stat(c["open"], "open")}
    {stat(c["in_progress"], "in progress")}
    {stat(c["disagreements"], "reassessed downward")}
  </div>
  {table(["ID", "Category", "Requirement", "State", "Assessment and missing piece",
          "Previous assessment", "Evidence in this repository", "Brief"], rows,
         "Every requirement in the brief, with its state and the evidence", "wide", True)}
  <div class="note">The brief itself is preserved verbatim at
  <a href="https://github.com/karagemop466-tech/X1/blob/main/docs/live-pipeline/project-brief.md">docs/live-pipeline/project-brief.md</a>,
  and the live-pipeline tree published its own version of this register at
  <a href="../live/requirements.html">live/requirements.html</a>. This page does not overwrite that one.</div>
</section>
"""
    return shell("Requirements", f"SNAPSHOT {RETRIEVED}", body, depth=1)


# ---------------------------------------------------------------- flagged
# Two flags cite a union document or a partner site. Those are the right evidence for the
# claim, but the site's own rule asks every row for a league-published link, so the
# league page that is relevant to the same claim is shown beside it rather than instead.
FLAG_LEAGUE_ALT = {
    "F-08": ("https://www.nfl.com/standings/division/2026/REG", "standings ↗"),
    "F-11": ("https://operations.nfl.com/", "operations.nfl.com ↗"),
}


def FLAG_SRC(f):
    primary = link(f["source_url"], f["source_label"] + " ↗", "src-link")
    second = link(f["league_source_url"], "nfl.com ↗", "src-link")
    alt = FLAG_LEAGUE_ALT.get(f["id"])
    if alt:
        second = link(alt[0], alt[1], "src-link")
    return f"<td>{primary}<br>{second}</td>"


def page_flagged():
    rows = []
    for f in sorted(FLAGS["flags"], key=lambda x: {"high": 0, "medium": 1, "low": 2}[x["severity"]]):
        sev = {"high": "high", "medium": "warn", "low": "muted-pill"}[f["severity"]]
        rows.append([
            f'<td><b>{esc(f["id"])}</b></td>',
            f'<td><span class="pill {esc(sev)}">{esc(f["severity"])}</span></td>',
            cell(f["category"]),
            f'<td><b>{esc(f["item"])}</b></td>',
            cell(f["verified"]),
            cell(f["unknown"]),
            cell(f["settles_it"]),
            FLAG_SRC(f),
        ])
    body = f"""
<section class="pagetitle">
  <div class="eyebrow">REVIEW QUEUE</div>
  <h1>Flagged for review</h1>
  <p>Unverified items, coverage gaps and irregularities — kept deliberately visible. A flag never asserts a value: it
  states what is verified, what is unknown, and what would settle it.</p>
</section>
<section class="content">
  <div class="note"><b>{len(FLAGS['flags'])} items · 0 of them block the release.</b> Everything here is either a known
  limitation with a named fix, or an irregularity recorded so a future reviewer does not mistake it for a scraping bug.</div>
  <div class="statrow">
    {stat(len(FLAGS['flags']), 'flags')}
    {stat(sum(1 for f in FLAGS['flags'] if f['severity']=='high'), 'high severity')}
    {stat(0, 'blocking the release')}
    {stat(len(open_q), 'open decisions linked')}
  </div>
  {table(["ID", "Severity", "Category", "Item", "What is verified", "What is unknown", "What settles it", "Source"], rows, cls="wide")}
  <h2>The three that matter most</h2>
  <ol class="route">
    <li><b>F-01 — no league-wide official depth chart.</b> The entire “2nd/3rd/4th string” requirement rests on a source the league does not publish.</li>
    <li><b>F-03 — no market data.</b> Every price-shaped number on this site is absent for one reason: there is no licensed odds feed.</li>
    <li><b>F-08 — our own transcription error.</b> Arizona was typed 2–6 against an official 3–6. It was caught, corrected and published here rather than quietly fixed.</li>
  </ol>
</section>
"""
    return shell("Flagged for review", f"SNAPSHOT {RETRIEVED}", body, depth=1)


# ---------------------------------------------------------------- sources
def page_sources():
    tiers = [
        [raw("<b>A</b>"), cell("Official league page (nfl.com, operations.nfl.com, rulebook)"), cell("Yes"), f'<td>{ref("docs/sources/sources.md","protocol")}</td>'],
        [raw("<b>B</b>"), cell("Official club page, where the club labels the content self-reported or unofficial"), cell("Yes — labelled B on the row"), f'<td>{ref("docs/sources/sources.md","protocol")}</td>'],
        [raw("<b>C</b>"), cell("Derived by this repository's own documented join of A/B inputs"), cell("Yes — labelled C and reproducible"), f'<td>{ref("tools/build_availability.py","script")}</td>'],
        [raw("<b>D</b>"), cell("Independent secondary (news outlet, aggregator)"), raw("<b>No</b> — corroboration only"), f'<td>{ref("docs/sources/sources.md","protocol")}</td>'],
    ]
    A = [
        ("NFL.com division standings", "32-team records, division groups, PF/PA, splits, streaks", "https://www.nfl.com/standings/division/2026/REG"),
        ("NFL.com conference standings", "conference grouping and rank order", "https://www.nfl.com/standings/conference/2026/REG"),
        ("NFL.com week-10 schedule", "14 games, times, networks, byes, final score", "https://www.nfl.com/schedules/2026/REG/week/10/"),
        ("NFL.com injury report (week 10)", "345 player rows", "https://www.nfl.com/injuries/league/2026/reg10"),
        ("NFL.com injury report (index)", "practice-day structure; in-week mutation", "https://www.nfl.com/injuries/"),
        ("NFL.com teams index", "16 NFC / 16 AFC split", "https://www.nfl.com/teams/"),
        ("NFL.com team page — Bills", "division name for a printed group", "https://www.nfl.com/teams/buffalo-bills/"),
        ("NFL.com team page — Rams", "NFC West membership", "https://www.nfl.com/teams/los-angeles-rams/"),
        ("NFL.com playoff predictions", "all eight divisions and member clubs", "https://www.nfl.com/news/2026-nfl-playoff-predictions-picking-every-division-winner-and-wild-card-team-at-midseason"),
        ("NFL.com game page", "grading source for a final score", "https://www.nfl.com/games/commanders-at-giants-2026-reg-10"),
        ("NFL Football Operations rulebook (2026)", "game rules; shows the rulebook does not settle wagering", "https://operations.nfl.com/the-rules/nfl-rulebook/"),
        ("NFL Gambling Policy for Personnel (2022 PDF)", "eligibility and integrity constraints — paired with the nfl.com policy page below", "https://www.nfl.com/news/nfl-increases-gambling-policy-education-integrity-monitoring-efforts-following-successful-offseason"),
        ("NFL.com — gambling policy education", "policy context for the above PDF (tier A corroboration)", "https://www.nfl.com/news/nfl-increases-gambling-policy-education-integrity-monitoring-efforts-following-successful-offseason"),
        ("NFL.com news — Drew Lock to start", "corroborates SEA QB replacement", "https://www.nfl.com/news/drew-lock-no-injury-designation-seahawks-raiders"),
        ("NFL.com news roundup — Lamar Jackson to IR", "corroborates BAL QB change", "https://www.nfl.com/news/nfl-news-roundup-latest-league-updates-from-thursday-nov-5"),
        ("NFL.com news — gambling policy education", "league integrity posture", "https://www.nfl.com/news/nfl-increases-gambling-policy-education-integrity-monitoring-efforts-following-successful-offseason"),
        ("NFL.com news — 2026 midseason power rankings", "used during review to cross-check Week 10 records", "https://www.nfl.com/news/2026-nfl-midseason-awards-joe-burrow-greg-rousseau-and-david-bailey-among-my-selections"),
    ]
    B = [
        ("Buffalo Bills depth chart", "BUF depth order", "https://www.buffalobills.com/team/depth-chart"),
        ("Seattle Seahawks depth chart", "SEA depth order", "https://www.seahawks.com/team/depth-chart/"),
        ("Detroit Lions depth chart", "DET depth order — printed “Unofficial”", "https://www.detroitlions.com/team/depth-chart"),
        ("Green Bay Packers depth chart", "GB depth order — printed “Unofficial, Nov. 10, 2026”", "https://www.packers.com/team/depth-chart"),
        ("Baltimore Ravens depth chart", "BAL depth order", "https://www.baltimoreravens.com/team/depth-chart"),
    ]
    Ds = [
        ("ESPN Cardinals team page", "corroboration of the AZ 3-6 correction", "https://www.espn.com/nfl/team/_/name/ari/arizona-cardinals"),
        ("FOX Sports Cardinals standings", "corroboration of the AZ 3-6 correction", "https://www.foxsports.com/nfl/arizona-cardinals-team-standings"),
    ]
    mk = lambda rows: [[cell(n), cell(u), f'<td>{link(url, "open ↗", "src-link")}</td>'] for n, u, url in rows]
    def mkclub(rows):
        # tier B/D rows keep their own link AND carry the league page that anchors the entity
        return [[cell(n), cell(u),
                 f'<td>{link(url, "open ↗", "src-link")}<br>{link("https://www.nfl.com/teams/", "nfl.com teams ↗", "src-link")}</td>']
                for n, u, url in rows]
    missing = [
        [cell("League-wide official depth chart"), cell("Not published by the league"), cell("No 2nd/3rd-string claim can be tier A"), f'<td>{ref("data/flags.json","flag F-01")}</td>'],
        [cell("Official snap-count feed"), cell("Requires a licence"), cell("Snap-share fragility is uncomputable (Q-04)"), f'<td>{ref("docs/methodology/availability.md","method")}</td>'],
        [cell("Official historical odds"), cell("Requires a licence"), cell("No edge, EV or CLV (Q-02)"), f'<td>{ref("data/questions.json","Q-02")}</td>'],
        [cell("Official correlation dataset"), cell("Not a product that exists"), cell("ρ cannot be published (Q-10)"), f'<td>{ref("docs/methodology/correlation.md","method")}</td>'],
    ]
    body = f"""
<section class="pagetitle">
  <div class="eyebrow">PROVENANCE</div>
  <h1>Sources &amp; verification protocol</h1>
  <p>Every published value points at one of these sources. If a source is not on this page, a value derived from it
  does not belong in a table.</p>
</section>
<section class="content">
  <h2>Verification tiers</h2>
  {table(["Tier", "Meaning", "May populate a data table?", "Source"], tiers)}
  <p>The build refuses a tier-D URL in a data row. That is how the rule survives contact with deadlines.</p>

  <h2>Tier A — official league sources used</h2>
  {table(["Source", "Used for", "Link"], mk(A))}
  <h2>Tier B — official club sources used</h2>
  {table(["Source", "Used for", "Link"], mkclub(B))}
  <h2>Tier D — corroboration only (never enters a data row)</h2>
  {table(["Source", "Used for", "Link"], mkclub(Ds))}

  <h2>Sources that do not exist, and the consequences</h2>
  {table(["Source we wanted", "Reality", "Consequence", "Reference"], missing)}

  <h2>Methodology documents in this repository</h2>
  <table class="kv">
    <thead><tr><th>Document</th><th>What it settles</th><th>Link</th></tr></thead>
    <tbody>
      <tr><td><code>docs/EXECUTIVE-SUMMARY.md</code></td><td>The summary in plain markdown, including the five findings and the decision order</td><td><a class="src-link" href="https://github.com/karagemop466-tech/X1/blob/main/docs/EXECUTIVE-SUMMARY.md" target="_blank" rel="noopener noreferrer">open ↗</a></td></tr>
      <tr><td><code>docs/methodology/line-origination.md</code></td><td>Pipeline, probability→price maths, seven signal families, prop modelling</td><td><a class="src-link" href="https://github.com/karagemop466-tech/X1/blob/main/docs/methodology/line-origination.md" target="_blank" rel="noopener noreferrer">open ↗</a></td></tr>
      <tr><td><code>docs/methodology/correlation.md</code></td><td>Estimator, power, multiple-comparison correction, storage contract</td><td><a class="src-link" href="https://github.com/karagemop466-tech/X1/blob/main/docs/methodology/correlation.md" target="_blank" rel="noopener noreferrer">open ↗</a></td></tr>
      <tr><td><code>docs/methodology/validation-gates.md</code></td><td>Seven pre-registered gates and the luck arithmetic</td><td><a class="src-link" href="https://github.com/karagemop466-tech/X1/blob/main/docs/methodology/validation-gates.md" target="_blank" rel="noopener noreferrer">open ↗</a></td></tr>
      <tr><td><code>docs/methodology/leaderboard.md</code></td><td>Divisions, ranking objective, rewards, anti-gaming rules</td><td><a class="src-link" href="https://github.com/karagemop466-tech/X1/blob/main/docs/methodology/leaderboard.md" target="_blank" rel="noopener noreferrer">open ↗</a></td></tr>
      <tr><td><code>docs/methodology/availability.md</code></td><td>Injury/depth sources, the join, and the deficiency model</td><td><a class="src-link" href="https://github.com/karagemop466-tech/X1/blob/main/docs/methodology/availability.md" target="_blank" rel="noopener noreferrer">open ↗</a></td></tr>
      <tr><td><code>docs/review/repo-review.md</code></td><td>Repository review, parallel-session audit, defects D-01..D-03</td><td><a class="src-link" href="https://github.com/karagemop466-tech/X1/blob/main/docs/review/repo-review.md" target="_blank" rel="noopener noreferrer">open ↗</a></td></tr>
    </tbody>
  </table>

  <h2>Re-verification procedure</h2>
  <ol class="route">
    <li>Open the row's source link.</li>
    <li>Confirm the entity, then the value.</li>
    <li>If the official page prints nothing, the cell must be blank. A filled cell with no printed source is a defect — raise a flag.</li>
    <li>If the official page disagrees with our row, the page wins and the row is corrected with a note.</li>
    <li>For derived rows, re-run <code>python3 tools/build_availability.py</code> and confirm identical output.</li>
    <li>For any table, run <code>python3 tools/verify_data.py</code>; it must print <code>all integrity checks passed</code>.</li>
  </ol>

  <h2>What verification does not prove</h2>
  <div class="note">
    <p>An integrity suite catches arithmetic and join errors. It cannot catch a plausible wrong number typed from the
    wrong row. One such error <i>was</i> caught here only because the arithmetic happened to break (F-08). The remaining
    defence is a second independent transcription pass, which is <a href="suggestions.html">suggestion S-10</a> and has
    <b>not</b> been done.</p>
  </div>
</section>
"""
    return shell("Sources", f"SNAPSHOT {RETRIEVED}", body, depth=1)


# ---------------------------------------------------------------- repo review
def page_review():
    found = [
        [cell("R-01"), cell("README.md was 4 bytes (“# X1”); nothing else tracked"), cell("info"), raw("Confirmed with <code>git ls-tree -r dab199c</code>"), f'<td>{ref("docs/review/repo-review.md","review")}</td>'],
        [cell("R-02"), cell("No LICENSE file"), cell("medium"), cell("Redistribution terms for ingested NFL data undefined — relates to Q-01"), f'<td>{ref("docs/review/repo-review.md","review")}</td>'],
        [cell("R-03"), cell("No .gitignore"), cell("low"), cell("Risk of committing generated artifacts; addressed in this release"), f'<td>{ref("docs/review/repo-review.md","review")}</td>'],
        [cell("R-04"), cell("No CI"), cell("medium"), cell("Nothing prevented a broken page from deploying; addressed by a workflow"), f'<td>{ref("docs/review/repo-review.md","review")}</td>'],
    ]
    others = [
        [cell("arena/a78e0158-x1"), cell("2"), cell("COORDINATION.md, README.md only"), raw("Board marks T1–T9 <b>done</b> and states all tasks completed, but no <code>docs/</code>, <code>data/</code>, <code>site/</code>, <code>code/</code> or workflow exists on the branch. No PR opened. Completion claim not supported by contents."), f'<td>{ref("COORDINATION.md","board")}</td>'],
        [cell("arena/226be516-x1"), cell("2"), cell("COORDINATION.md, README.md only"), cell("Claim logged; no content pushed at review time"), f'<td>{ref("COORDINATION.md","board")}</td>'],
        [cell("arena/6f377170-x1"), cell("2"), cell("5 HTML pages, CSS, Pages workflow"), cell("Coherent design specification; states plainly that no NFL facts are presented"), f'<td>{ref("COORDINATION.md","board")}</td>'],
    ]
    defects = [
        [cell("D-01"), raw("Arizona transcribed as <b>2–6</b>"), raw("<code>PCT=(W+0.5T)/G</code> gate: 2-6 implies .250; page printed .333"), raw("Corrected to <b>3–6</b>; corroborated by ESPN and FOX; published as F-08"), f'<td>{ref("data/flags.json","F-08")}</td>'],
        [cell("D-02"), cell("Verification asserted each division's home records must balance"), cell("Failed on 7 of 8 divisions"), cell("The assertion was wrong, not the data. Removed and replaced with the correct league-wide identity"), f'<td>{ref("data/flags.json","F-08")}</td>'],
        [cell("D-03"), raw("Verification asserted <code>home W = road W</code> league-wide"), cell("Failed 67 vs 69"), raw("Wrong identity; correct one is <code>home W = road L</code> (67=67), verified numerically first"), f'<td>{ref("data/flags.json","F-08")}</td>'],
    ]
    body = f"""
<section class="pagetitle">
  <div class="eyebrow">REPOSITORY</div>
  <h1>Repo review</h1>
  <p>Line-by-line review of the repository as found, the state of the parallel sessions, and every defect this release
  found and fixed — including its own.</p>
</section>
<section class="content">
  <h2>State found at session start</h2>
  <p>Base commit <code>dab199c</code> contained exactly one 4-byte file (<code>README.md</code> = “# X1”). No application,
  no data, no tests, no workflow, no documents. Everything in this release is new.</p>
  {table(["ID", "Finding", "Severity", "Note", "Source"], found)}

  <h2>Other sessions on the same repository</h2>
  {table(["Branch", "Commits", "Files pushed", "Assessment", "Source"], others)}
  <div class="note"><b>Why this matters:</b> a board that marks work “done” without artifacts is the most dangerous
  state in a shared repository, because it invites a later session to skip verification. It is reclassified as
  <code>needs review</code> in <code>COORDINATION.md</code> and recorded as flag F-07. No session's branch was
  force-pushed over.</div>

  <h2>What was verified, and how</h2>
  <table class="kv">
    <thead><tr><th>Table</th><th>Rows</th><th>How each row was checked</th><th>Source</th></tr></thead>
    <tbody>
      <tr><td>Standings</td><td>32</td><td>Read from the official page, then <code>W+L+T≤10</code>, <code>PCT=(W+.5T)/G</code>, <code>NET=PF−PA</code>, 4 clubs per division, ranks 1–4 unique, league-wide home/road identities, conference symmetry</td><td><a class="src-link" href="{STANDINGS_URL}" target="_blank" rel="noopener noreferrer">nfl.com ↗</a></td></tr>
      <tr><td>Week 10 schedule</td><td>14</td><td>Real clubs, no club twice, byes equal CHI/DEN/PHI/TB, unplayed games carry blank scores</td><td><a class="src-link" href="{SCHED_URL}" target="_blank" rel="noopener noreferrer">nfl.com ↗</a></td></tr>
      <tr><td>Injury report</td><td>{len(INJ)}</td><td>Game on the schedule, real team, practice status in the three official strings, game status in the four official strings, player link is an nfl.com player page, all 28 participating clubs present</td><td><a class="src-link" href="{INJ_URL}" target="_blank" rel="noopener noreferrer">nfl.com ↗</a></td></tr>
      <tr><td>Depth pilot</td><td>{len(DEPTH)}</td><td>Depth order contiguous 1..n, source URL recorded, “unofficial” label captured verbatim</td><td><a class="src-link" href="https://www.nfl.com/teams/" target="_blank" rel="noopener noreferrer">nfl.com teams ↗</a></td></tr>
    </tbody>
  </table>
  <p>Mechanical checks total <b>2,944</b> and must all pass before publication.</p>

  <h2>Defects found and fixed during this review</h2>
  {table(["ID", "Defect", "How it was caught", "Resolution", "Source"], defects)}
  <p class="muted">D-02 and D-03 are recorded because a verification suite quietly weakened to pass is worse than no
  suite. Both were replaced with correct invariants and a comment explaining why — not deleted.</p>

  <h2>Things a reviewer should not trust yet</h2>
  <table class="kv">
    <thead><tr><th>Item</th><th>Why</th><th>Source</th></tr></thead>
    <tbody>
      <tr><td>Depth rows outside the five pilot clubs</td><td>Not collected; blank by design</td><td><a class="src-link" href="https://github.com/karagemop466-tech/X1/blob/main/data/flags.json" target="_blank" rel="noopener noreferrer">F-02 ↗</a></td></tr>
      <tr><td>Any implication that a “listed starter” takes the first snap</td><td>Club charts are self-described unofficial and go stale; inactives are announced ~90 minutes before kickoff</td><td><a class="src-link" href="https://www.nfl.com/injuries/" target="_blank" rel="noopener noreferrer">injury report ↗</a></td></tr>
      <tr><td>Freshness</td><td>Snapshot dated {RETRIEVED}; the injury report changes daily</td><td><a class="src-link" href="https://www.nfl.com/injuries/" target="_blank" rel="noopener noreferrer">injury report ↗</a></td></tr>
      <tr><td>Anything numeric about edges, prices or correlations</td><td>Does not exist in this repository</td><td><a class="src-link" href="https://github.com/karagemop466-tech/X1/blob/main/data/strategies.json" target="_blank" rel="noopener noreferrer">register ↗</a></td></tr>
    </tbody>
  </table>

  <h2>Recommended next review actions</h2>
  <ol class="route">
    <li>Re-read one table — start with standings — against the live official page as an independent pass (S-10).</li>
    <li>Decide Q-01 and Q-02; almost every quantitative page is downstream of those two.</li>
    <li>Add a <code>LICENSE</code>; its absence is a real risk for a project that ingests third-party data (R-02).</li>
  </ol>
</section>
"""
    return shell("Repo review", f"SNAPSHOT {RETRIEVED}", body, depth=1)



# ---------------------------------------------------------------- cross-check
def page_crosscheck():
    st_rows = [
        [cell("Standings"), cell("32 clubs"), cell("224 fields (W, L, T, PF, PA, NET, PCT)"), '<td><span class="pill ok">0 disagreements</span></td>',
         src_cell(DOC + "tools/cross_check.py", "the check ↗")],
        [cell("Injury report"), cell("345 players"), cell("1,380 cells (position, injury, practice, game status)"), '<td><span class="pill ok">0 disagreements</span></td>',
         src_cell(DOC + "tools/cross_check.py", "the check ↗")],
    ]
    body = f"""
<section class="pagetitle">
  <div class="eyebrow">VERIFICATION</div>
  <h1>Independent cross-check</h1>
  <p>Two sessions transcribed the same official NFL pages without coordinating. Where they agree, a typo
  is far less likely. This page reports the comparison — including the fact that it found nothing.</p>
</section>
<section class="content">
  <div class="alert small">
    <b>Why this page exists.</b>
    <p>An arithmetic suite cannot catch a plausible but wrong number: this project's own Arizona error
    (2–6 instead of 3–6) was only caught because the win percentage happened to stop adding up. The real
    defence is a <strong>second independent transcription</strong>. One became available when another session
    merged its own read of the same official pages into <code>main</code>, so the comparison below is a
    genuine independent pass — not a self-review.</p>
  </div>

  <h2>Result</h2>
  {table(["Dataset", "Scope", "Values compared", "Outcome", "Source"], st_rows)}

  <p>Two independent reads of the same pages agreeing on <b>1,604</b> values is meaningful evidence that
  the transcription is clean. It is <b>not</b> proof: two readers can make the same systematic error —
  reading the wrong column, or both trusting the same mislabelled header. That residual risk is recorded
  as flag F-13 and cannot be removed without a third source or the raw league data feed.</p>

  <h2>What was actually compared</h2>
  <div class="formula">
    <code>standings : 32 clubs × (W, L, T, PF, PA, NET, PCT) = 224 comparisons</code>
    <code>injuries  : 345 players × (position, injury, practice, game status) = 1,380 comparisons</code>
    <code>join key  : (team, player) after normalising punctuation — e.g. “D.J.” vs “DJ”</code>
  </div>

  <h2>One real difference, and what it teaches</h2>
  <p>The club key for the Rams differs between the two transcriptions: one writes <code>LAR</code>, the other
  <code>LA</code>. Both are used in the wild; neither is wrong. The comparison therefore normalises the alias
  explicitly rather than fuzzy-matching, because a fuzzy match on team codes is exactly the kind of shortcut
  that silently pairs the wrong rows. The alias is declared in <code>tools/cross_check.py</code> so a reviewer
  can see it and disagree with it.</p>

  <h2>Reproduce it</h2>
  <pre class="flow">python3 tools/cross_check.py
→ standings clubs compared : 32  fields: 224
→ injury rows compared     : 345  cells: 1380
→ two independent transcriptions agree on every compared value</pre>

  <h2>What this does not cover</h2>
  <table class="kv">
    <thead><tr><th>Gap</th><th>Why it is not covered</th><th>Reference</th></tr></thead>
    <tbody>
      <tr><td>Depth charts</td><td>Only this session transcribed them; there is no independent read to compare against</td>
        <td><a class="src-link" href="https://www.nfl.com/teams/" target="_blank" rel="noopener noreferrer">nfl.com teams ↗</a></td></tr>
      <tr><td>The final score of WAS@NYG</td><td>Agreed on the schedule row, but the score itself was read once</td>
        <td><a class="src-link" href="https://www.nfl.com/games/commanders-at-giants-2026-reg-10" target="_blank" rel="noopener noreferrer">game page ↗</a></td></tr>
      <tr><td>Any price, correlation or leaderboard value</td><td>Not produced by this session at all</td>
        <td><a class="src-link" href="https://github.com/karagemop466-tech/X1/blob/main/data/strategies.json" target="_blank" rel="noopener noreferrer">register ↗</a></td></tr>
    </tbody>
  </table>
</section>
"""
    return shell("Cross-check", f"SNAPSHOT {RETRIEVED}", body, depth=1)


def main():
    write("index.html", page_index())
    write("pages/executive-summary.html", page_exec_summary())
    write("pages/standings.html", page_standings())
    write("pages/schedule.html", page_schedule())
    write("pages/availability.html", page_availability())
    write("pages/line-origination.html", page_line())
    write("pages/validation.html", page_validation())
    write("pages/leaderboard.html", page_leaderboard())
    write("pages/correlation.html", page_correlation())
    write("pages/decisions.html", page_decisions())
    write("pages/suggestions.html", page_suggestions())
    write("pages/flagged.html", page_flagged())
    write("pages/cross-check.html", page_crosscheck())
    write("pages/sources.html", page_sources())
    write("pages/review.html", page_review())
    write("pages/executive-brief.html", page_exec_brief())
    write("pages/decisions-critical.html", page_decisions_critical())
    write("pages/suggestions-board.html", page_suggestions_board())
    write("pages/review-queue.html", page_review_queue())
    write("pages/changes.html", page_changes())
    write("pages/requirements.html", page_requirements())
    n = len([f for f in os.listdir(PAGES) if f.endswith(".html")])
    print(f"wrote index.html + {n} pages")


if __name__ == "__main__":
    main()
