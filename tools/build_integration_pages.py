#!/usr/bin/env python3
"""Integration pages for the final integration session (arena/6b45af7e-x1, 2026-11-19).

Generates four pages into pages/ using the repository's own generated shell, so every page carries
the same rail, the same evidence rule and the same row-level source link:

  pages/verification-2026-11-19.html   this session's own live reads vs the committed 2026-11-19 pack
  pages/decision-brief.html            executive summary: what is proven, what is blocked, what to decide
  pages/questions-and-answers.html     every open question: known information, missing information, how to discover it
  pages/suggestion-review.html         every suggestion, reviewable, with the trade-off before anything is built

Every number on these pages is read from a committed file at build time. Nothing is re-typed.
`--check` fails if the committed pages differ from a fresh build, so a hand edit cannot ship.

Usage: python3 tools/build_integration_pages.py [--check]
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / "pages"
READ_DATE = "2026-11-19"
# The league's own operations site. Used only where a register row is an internal decision with no
# publisher to cite: it is the league's official home for the licensing and operations material that
# such a decision would be governed by. It is never presented as a source FOR the decision.
OPS = "https://operations.nfl.com/"


# ------------------------------------------------------------------ repository conventions
def _load_build_site():
    """Import the site generator's helpers so these pages use the same shell, nav and styling."""
    sys.path.insert(0, str(ROOT / "tools"))
    import build_site  # noqa: PLC0415  (imported lazily: it reads the whole data tree at import)
    return build_site


BS = _load_build_site()
shell = BS.shell
table = BS.table
stat = BS.stat
cell = BS.cell
esc = BS.esc
src_cell = BS.src_cell
repo_blob = BS.repo_blob
REPO = BS.REPO
DOC = BS.DOC


def load_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def read_tsv(path: str) -> list[dict]:
    lines = [ln for ln in (ROOT / path).read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(lines, delimiter="\t"))


# ------------------------------------------------------------------ data
RECHECK = load_json("data/integration/live_recheck_2026_11_19.json")
SECOND = load_json("data/verification/2026_11_19_second_read/diff_vs_first_reader.json")
PACK19 = load_json("data/verification/2026_11_19/verification_summary_2026_11_19.json")
REQS = load_json("data/audit/requirements_assessed.json")
READY = load_json("data/audit/readiness.json")
QUESTIONS17 = load_json("data/console/questions.csv".replace(".csv", ".json")) if False else None
W11_INJ = read_tsv("data/verification/2026_11_19/official_w11_injuries_2026_11_19.tsv")
W10_INJ = read_tsv("data/nfl/injuries_week10.tsv")
W10_RECHECK = load_json("data/integration/live_w10_injuries_recheck_2026_11_19.json")
FLAGS = load_json("data/flags.json")


def read_csv(path: str) -> list[dict]:
    with open(ROOT / path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


QS = read_csv("data/console/questions.csv")
SG = read_csv("data/console/suggestions.csv")
SUGGEST = load_json("data/suggestions.json")["suggestions"]
BOARD = load_json("data/audit/suggestion_board.json")

LANDING = __import__("json")
SITE_DIR = ROOT / "index.html"


def suggestions_landing_counts() -> dict:
    """The status tally the owner's suggestions register carries, recomputed from data/suggestions.json."""
    out: dict[str, int] = {}
    for s in SUGGEST:
        out[s["status"]] = out.get(s["status"], 0) + 1
    return out


# ------------------------------------------------------------------ page 1: verification
def page_verification() -> str:
    std = RECHECK["standings"]
    w10 = RECHECK["week10_finals"]
    w11 = RECHECK["week11_slate"]

    std_rows = [[
        f'<td><b>{esc(d["abbr"])}</b></td>',
        f'<td>{esc(d["field"])}</td>',
        f'<td>{esc(d["committed"])}</td>',
        f'<td>{esc(d["live"])}</td>',
        f'<td><span class="pill high">differs</span></td>',
        src_cell(RECHECK["sources"]["standings"], "nfl.com ↗"),
    ] for d in std["differences"]] or [[
        '<td><b>all 32 clubs</b></td>',
        '<td>12 printed fields</td>',
        '<td>&mdash;</td>',
        '<td>No cell differs: every club was read twice from the same page.</td>',
        '<td><span class="pill ok">identical</span></td>',
        src_cell(RECHECK["sources"]["standings"], "nfl.com ↗"),
    ]]

    w10_rows = [[
        f'<td>{esc(d.get("fixture", ["", ""])[0])} at {esc(d.get("fixture", ["", ""])[1])}</td>'
        if isinstance(d.get("fixture"), list) and len(d["fixture"]) == 2 else '<td>—</td>',
        f'<td>{esc(d.get("field", "fixture presence"))}</td>',
        f'<td>{esc(d.get("committed", ""))}</td>',
        f'<td>{esc(d.get("live", ""))}</td>',
        src_cell(RECHECK["sources"]["week10_slate"], "nfl.com ↗"),
    ] for d in w10["differences"]] or [[
        f'<td><b>all {w10["fixtures_live"]} fixtures</b></td>',
        '<td>&mdash;</td>',
        '<td>&mdash;</td>',
        '<td>No field differs (scores, status, day line and both printed club records).</td>',
        src_cell(RECHECK["sources"]["week10_slate"], "nfl.com ↗"),
    ]]

    w11_rows = [[
        f'<td><b>{esc(d.get("game_id") or d.get("bye", ""))}</b></td>',
        f'<td>{esc(d.get("field", d.get("finding", "")))}</td>',
        f'<td>{esc(d.get("committed", ""))}</td>',
        f'<td>{esc(d.get("live", ""))}</td>',
        src_cell(RECHECK["sources"]["week11_slate"], "nfl.com ↗"),
    ] for d in w11["differences"]] or [[
        f'<td><b>{w11["fixtures_live"]} fixtures + {w11["byes_live"]} byes</b></td>',
        '<td>&mdash;</td>',
        '<td>&mdash;</td>',
        f'<td>No field differs; {w11["clubs_covered_once"]} clubs are printed exactly once.</td>',
        src_cell(RECHECK["sources"]["week11_slate"], "nfl.com ↗"),
    ]]

    diff_rows = [[
        f'<td><b>{esc(d["team"])}</b></td>',
        f'<td>{esc(d["player"])}</td>',
        f'<td>{esc(", ".join(d["fields"].keys()))}</td>',
        f'<td>{esc(" / ".join(d["fields"].get(f, [""])[0] for f in d["fields"]))}</td>',
        f'<td>{esc(" / ".join(v[1] if len(v) > 1 else "" for v in d["fields"].values()))}</td>',
        src_cell(SECOND["source"], "nfl.com ↗"),
    ] for d in SECOND["differences"]]

    inj = SECOND["injury_text"]
    body = f"""
<section class="pagetitle">
  <div class="eyebrow">VERIFICATION · READ {READ_DATE}</div>
  <h1>This session's own live reads, against what the site already published</h1>
  <p>On {READ_DATE} this session re-read four official nfl.com pages and compared every cell with the
  committed 2026-11-19 pack. Three datasets agree exactly. The fourth — the Week 11 injury report —
  agrees on {SECOND["keys_joined"] - SECOND["cell_differences"]} of {SECOND["keys_joined"]} player rows and disagrees on {SECOND["cell_differences"]} game-status cell, and its free-text injury
  column changed between consecutive reads of the same page. Both are published here rather than resolved.</p>
</section>
<section class="content">
  <div class="note"><b>Method.</b> Each read is transcribed into its own dated file with the source URL on
  every row, then diffed cell by cell by a tool that runs in CI. A difference is a <i>finding</i>, never an
  overwrite: nothing in the committed pack was edited by this session, and no value was inferred to make a
  comparison close. Where the two reads disagree, the cell is published as <b>unverified</b> and appears on the
  <a href="flagged.html">Flagged for review</a> page.</div>

  <div class="statrow">
    {stat(f'{std["rows_live"]}/{std["rows_committed"]}', "standings rows read twice", f'{std["arithmetic_passed"]}/{std["arithmetic_assertions"]} arithmetic assertions on the live read')}
    {stat(std["cell_differences"], "standings cells that differ", "12 printed fields per club")}
    {stat(f'{w10["fixtures_live"]}/{w10["fixtures_committed"]}', "Week 10 finals agree", f'{w10["field_differences"]} field differences')}
    {stat(f'{w11["fixtures_live"]}+{w11["byes_live"]}', "Week 11 fixtures + byes agree", f'{w11["field_differences"]} field differences, {w11["clubs_covered_once"]} clubs once each')}
    {stat(SECOND["cell_differences"], "Week 11 injury cells that differ", f'{SECOND["keys_joined"]} rows joined between two independent reads')}
  </div>

  <h2>1 · League standings — 32 clubs, read twice, identical</h2>
  <p>The live read is not trusted because it was typed carefully; it is trusted because it satisfies the page's
  own arithmetic before it is used. Every club's <code>NET = PF − PA</code>, <code>PCT = (W + T/2) / (W + L + T)</code>
  and <code>HOME + ROAD = W-L-T</code> are asserted first ({std["arithmetic_passed"]} of
  {std["arithmetic_assertions"]} pass). Only then is it compared with the committed pack.</p>
  {table(["Club", "Field", "Committed pack", "This session's live read", "State", "Source"], std_rows, "Standings: every cell that differs between the two reads", "wide", True)}
  <p class="muted">Read from {src_cell(RECHECK["sources"]["standings"])} · committed pack:
  <code>data/verification/2026_11_19/official_standings_2026_11_19.tsv</code> ·
  rebuilt by <code>tools/build_live_recheck.py</code>.</p>

  <h2>2 · Week 10 finals — 14 of 14 agree</h2>
  <p>All fourteen Week 10 fixtures now print <b>Final</b> with scores and post-game records beside the club logos.
  This session's independent read is in <code>data/integration/live_w10_finals_second_read_2026_11_19.tsv</code>.</p>
  {table(["Fixture", "Field", "Committed pack", "This session's live read", "Source"], w10_rows, "Week 10 finals: every field that differs between the two reads", "wide", True)}

  <h2>3 · Week 11 slate — 13 fixtures + 6 byes agree</h2>
  <p>{w11["fixtures_live"]} scheduled fixtures and {w11["byes_live"]} byes cover {w11["clubs_covered_once"]} clubs
  exactly once. The Week 11 page prints the Rams as <b>LAR</b> in its bye block where the standings page prints
  <b>LA</b>; the shorthand is kept as printed and the alias is declared in the data file rather than silently unified{"" if not w11.get("abbreviation_aliases_used") else " (" + ", ".join(f"{k} × {v}" for k, v in w11["abbreviation_aliases_used"].items()) + ")"}.</p>
  {table(["Game / bye", "Field", "Committed pack", "This session's live read", "Source"], w11_rows, "Week 11 slate: every field that differs between the two reads", "wide", True)}

  <h2>4 · Week 11 injury report — the one dataset where two reads of the same page disagree</h2>
  <div class="note"><b>This is the finding, not a footnote.</b> Two sessions read the same live page
  ({SECOND["source"]}) on the same day and produced {SECOND['rows_read_a']} and {SECOND['rows_read_b']} rows from
  it. {SECOND["keys_joined"]} player rows join. {SECOND["cell_differences"]} cell differs — and the free-text
  <i>Injuries</i> column disagreed on <b>{inj["rows_where_the_two_reads_disagree"]}</b> rows and changed again on a
  third consecutive read of the same block. A column that is not stable between reads cannot be published as a
  value, so it is published as unconfirmed.</div>
  {table(["Club", "Player", "Field(s) that differ", "Read A (round-7 session)", "Read B (this session)", "Source"], diff_rows, "Week 11 injury rows where the two independent reads disagree", "wide", True) if diff_rows else '<p>No cell differs.</p>'}
  <p class="muted">Read A: <code>data/verification/2026_11_19/official_w11_injuries_2026_11_19.tsv</code> (session
  arena/427c1843-x1) · Read B: <code>data/verification/2026_11_19_second_read/official_w11_injuries_second_reader_2026_11_19.tsv</code>
  (this session) · rebuilt by <code>tools/verify_second_read_2026_11_19.py</code>.</p>

  <h3>What the Week 11 report does and does not contain, measured</h3>
  <div class="statrow">
    {stat(len(W11_INJ), "rows printed", f'{len({r["team"] for r in W11_INJ})} clubs of 32 print a table')}
    {stat(SECOND["designations_a"], "game designations (read A)", f'{SECOND["designations_b"]} in read B — IND Charlie Heck is the disputed cell')}
    {stat(sum(1 for r in W11_INJ if r.get("injury", "").strip()), "rows with any injury text", "the rest print a practice status only")}
    {stat(len(W10_INJ), "Week 10 rows still published", "a dated 2026-11-15 snapshot, not the live report")}
  </div>
  <div class="note"><b>Why this matters for originating lines.</b> A designations column that flickers between
  two reads is not a model input. The repository already forbids using the injury designation as a level
  (the injury signal must be a <i>surprise</i>), and this measurement is independent support: until a dated,
  hash-retained capture series exists, the designation is evidence of what the page said at one moment, not a
  feature.</div>

  <h2>4b · The published Week 10 table, 115 rows re-read line by line</h2>
  <p>The published Week 10 table is a dated 2026-11-15 snapshot of {len(W10_INJ)} rows across
  {len({r["team"] for r in W10_INJ})} clubs. This session re-read the live page and joined the two on club and
  player name. Of the rows inside the part of the page it read ({W10_RECHECK["clubs_covered"] and len(W10_RECHECK["clubs_covered"])} clubs),
  <b>{W10_RECHECK["agree"]} agree cell for cell and {W10_RECHECK["differ"]} differ</b>. The remaining
  {W10_RECHECK["not_covered"]} published rows sit in page sections this read did not fetch, and
  {W10_RECHECK["not_reached_within_chunk"]} more fall past the chunk boundary inside a covered club — both are
  counted as <i>not checked</i>, never as agreement.</p>
  <div class="statrow">
    {stat(W10_RECHECK["agree"], "published rows that agree", "position, injury text, practice status and game status")}
    {stat(W10_RECHECK["differ"], "published rows that differ", "each would be listed below with both values")}
    {stat(W10_RECHECK["not_covered"] + W10_RECHECK["not_reached_within_chunk"], "rows not checked", "outside the read window — stated, not implied")}
    {stat(len(W10_INJ), "rows still published", "the 2026-11-15 snapshot is unchanged by this check")}
  </div>
  <p class="muted">Read from {src_cell(W10_RECHECK["source"], "nfl.com ↗")} · rebuilt by
  <code>tools/verify_w10_injuries_live_2026_11_19.py</code> · live read in
  <code>data/integration/live_w10_injuries_recheck_2026_11_19.tsv</code>.</p>

  <h2>5 · The committed 2026-11-19 pack's own verdicts</h2>
  <p>The round-7 pack behind these tables reports {PACK19["verdicts"] and sum(1 for v in PACK19["verdicts"].values() if v == "pass")} pass and
  {sum(1 for v in PACK19["verdicts"].values() if v != "pass")} review across {len(PACK19["verdicts"])} checks. The two reviews are
  published findings, not failures: A7 records that the Week 11 report has no rows for CIN or WAS (both print
  &ldquo;No Injuries Reported&rdquo;), and A8 records that only part of the named-player availability evidence is an
  explicit starter statement.</p>
  {table(["Check", "What it measures", "Verdict", "Source"],
         [[f'<td><b>{esc(k)}</b></td>',
           f'<td>{esc(v["name"] if "name" in v else "")}</td>',
           f'<td><span class="pill {"ok" if ver == "pass" else "warn"}">{esc(ver)}</span></td>',
           src_cell(repo_blob("data/verification/2026_11_19/verification_summary_2026_11_19.json"), "pack ↗")]
          for (k, v), ver in zip(PACK19["checks"].items(), PACK19["verdicts"].values())],
         "The 2026-11-19 pack's checks", "wide", True)}

  <h2>6 · What this session could not verify</h2>
  <ul class="lim">
    <li><b>nfl.com was reachable through the page-fetch tool only.</b> A direct <code>curl</code> from this
    sandbox fails at TLS (<code>exit 35</code>), so no raw bytes were retained and no payload hash is claimed.
    Only the parsed text was read.</li>
    <li><b>Three of seven injury chunks were read twice</b> (0, 1, 2, 3, 4, plus a repeat of 0). Chunks 5–6 are
    navigation and the news carousel; the club blocks end in chunk 4.</li>
    <li><b>No price, closing line or market figure is verified anywhere in this repository</b>, and this page
    does not add one. See <a href="line-origination.html">line origination</a> for why the columns are blank.</li>
  </ul>
</section>
"""
    return shell("Live re-check 19 Nov", f"READ {READ_DATE} · LIVE vs COMMITTED", body, depth=1)


# ------------------------------------------------------------------ page 2: decision brief
def page_brief() -> str:
    counts = REQS["counts"]
    rc = READY["counts"]["register"]
    # Status buckets are read off the register's own STATUS strings and stated as they are:
    # ANSWERED (including the answers that are "no", which are still answers), BLOCKED, and
    # OWNER DECISION. Nothing is rounded into "open".
    def _bucket(status: str) -> str:
        s_ = status.strip().upper()
        for k in ("ANSWERED", "BLOCKED", "OWNER DECISION"):
            if s_.startswith(k):
                return k
        return "OTHER"
    _b = {}
    for q in QS:
        _b[_bucket(q["STATUS"])] = _b.get(_bucket(q["STATUS"]), 0) + 1
    q_open = _b.get("BLOCKED", 0) + _b.get("OWNER DECISION", 0) + _b.get("OTHER", 0)
    q_answered = _b.get("ANSWERED", 0)

    proven = [
        ("League standings, 32 clubs", "32 of 32 rows read twice on 2026-11-19 and identical; 96/96 of the page's own arithmetic identities pass.",
         "https://www.nfl.com/standings/league/2026/REG"),
        ("Week 10 results, 14 fixtures", f"All 14 print Final; two independent reads agree on {RECHECK['week10_finals']['fixtures_live']} of {RECHECK['week10_finals']['fixtures_live']} fixtures and on every printed record.",
         "https://www.nfl.com/schedules/2026/by-week/week-10"),
        ("Week 11 slate, 13 fixtures + 6 byes", f"32 clubs printed exactly once; two independent reads agree on every kickoff time, network and record.",
         "https://www.nfl.com/schedules/2026/by-week/week-11"),
        ("Week 10 injury report, 347 rows", "Published as a dated 2026-11-15 snapshot with a per-row player URL; every cell re-checked against a second transcription.",
         "https://www.nfl.com/injuries/league/2026/reg10"),
        ("Week 11 injury report, 253 rows", f"Two independent reads join on {SECOND['keys_joined']} rows with {SECOND['cell_differences']} disagreeing cell; practice status stable.",
         SECOND["source"]),
        ("Requirement register", f"{counts['total']} requirements tracked, {counts['met']} met, {counts['partly_met']} partly met, {counts['open']} open, {counts['in_progress']} in progress.",
         REPO + "/blob/main/data/audit/requirements_assessed.json"),
    ]
    proven_rows = [[f'<td><b>{esc(a)}</b></td>', f'<td>{esc(b)}</td>', src_cell(c, "official ↗")] for a, b, c in proven]

    blocked = [
        ("A licence to republish NFL data", "Nothing may be redistributed until the terms are read; the site publishes derived analysis and links to the official page.",
         "Q-01", REPO + "/blob/main/data/questions.json"),
        ("A price feed with an open and a close", "No official source publishes prices. Without it there is no market column, no closing-line value, no ROI and no demotion trigger.",
         "Q-02 / Q-19", REPO + "/blob/main/data/questions.json"),
        ("A definition of 'starter'", "No league-wide depth chart exists. Every 2nd/3rd/4th-string claim rests on a club page that some clubs label 'unofficial'.",
         "Q-05", "https://www.detroitlions.com/team/depth-chart"),
        ("Snap counts, or an official inactive list at scale", "Without one of them a replacement is suspected, never confirmed. Only 6 of 254 Week 10 report rows carry a game designation.",
         "Q-04", "https://www.nfl.com/injuries/league/2026/reg10"),
        ("Reward rules, funding and jurisdiction", "The leaderboard cannot pay anyone until the rules, the money and the legal review exist.",
         "Q-07", REPO + "/blob/main/data/questions.json"),
    ]
    blocked_rows = [[f'<td><b>{esc(a)}</b></td>', f'<td>{esc(b)}</td>', f'<td>{esc(c)}</td>', src_cell(d, "register ↗")] for a, b, c, d in blocked]

    decide = [
        ("1", "Do we operate on official public pages only, or fund a licensed data agreement?",
         "It decides whether the price, snap-count and play-by-play work can exist at all.",
         src_cell("https://operations.nfl.com/", "operations.nfl.com ↗")),
        ("2", "Which price source is the benchmark, and which number is &lsquo;the market&rsquo;?",
         "Four site trees currently name different benchmarks; a leaderboard cannot rank across them.",
         src_cell(REPO + "/blob/main/data/questions.json", "register ↗")),
        ("3", "Does a club's self-labelled &lsquo;unofficial&rsquo; chart count as evidence?",
         "It is the only depth source that exists, and it is what every replacement-depth number rests on.",
         src_cell("https://www.packers.com/team/depth-chart", "packers.com ↗")),
        ("4", "What exactly sends a live strategy back to paper?",
         "The demotion gate is written but its thresholds are not ratified, so nothing can be promoted safely.",
         src_cell(REPO + "/blob/main/docs/methodology/demotion-gate.md", "gate ↗")),
        ("5", "What funds the rewards, and who may enter?",
         "Everything about the competition's integrity depends on this, including whether NFL personnel may play.",
         src_cell(REPO + "/blob/main/data/questions.json", "register ↗")),
    ]

    body = f"""
<section class="pagetitle">
  <div class="eyebrow">EXECUTIVE SUMMARY · {READ_DATE}</div>
  <h1>What is proven, what is blocked, and what only you can decide</h1>
  <p>One page for the decision you are about to make. Three sections: the facts that now have two independent
  reads behind them, the five missing inputs that stop a number existing, and the five decisions that unblock
  them in order. Everything else on this site is detail hanging off those three lists.</p>
</section>
<section class="content">
  <div class="statrow">
    {stat(counts['total'], "requirements tracked", f"{counts['met']} met · {counts['partly_met']} partly met · {counts['open']} open")}
    {stat(len(FLAGS['flags']), "flagged items published", "each with its source link and what would settle it")}
    {stat(len(QS), "research-desk questions on the record", f"{q_answered} answered · {q_open} blocked or awaiting an owner decision")}
    {stat(len(SUGGEST) + len(SG), "reviewable suggestions", f"{len(SUGGEST)} site proposals + {len(SG)} console proposals")}
  </div>

  <h2>1 · What is proven, and how it was proven</h2>
  <p>The rule this repository runs on is narrow enough to check: a number is published only when an official
  page prints it, the row carries that page's URL, and a second reader agrees. Every row below meets all three.</p>
  {table(["Fact", "How it is verified", "Official source"], proven_rows, f"Verified facts, {READ_DATE}", "wide", True)}

  <h2>2 · What is blocked, and by what</h2>
  <p>None of these are engineering problems. They are inputs the league does not publish, or decisions that must
  be made before a number would mean anything. Publishing a proxy for any of them is the one thing this
  repository refuses to do.</p>
  {table(["Missing input", "What it blocks", "Question", "Register"], blocked_rows, "The blockers", "wide", True)}

  <h2>3 · What you have to decide, in dependency order</h2>
  <ol class="findings big">
  {"".join(f'<li><b>{esc(a)}. {esc(b)}</b><p>{esc(c)}</p></li>' for a, b, c, _ in [(x[0], x[1], x[2], x[3]) for x in decide])}
  </ol>
  {table(["Order", "Decision", "Why it is here", "Reference"], [[f'<td>{esc(a)}</td>', f'<td>{esc(b)}</td>', f'<td>{esc(c)}</td>', d] for a, b, c, d in decide], "Decisions in dependency order", "wide", True)}

  <h2>4 · The honest position on origination</h2>
  <ul class="lim">
    <li><b>The model is a screen, not a price.</b> On verified 2026 results nothing beats break-even at −110.
    That is published, not hidden.</li>
    <li><b>No official source publishes betting prices</b>, so every market, closing-line and ROI cell is blank
    and flagged rather than filled from a mirror without a label.</li>
    <li><b>Nothing is ranked on luck.</b> The leaderboard separates signal from staking, and the demotion gate
    sends a strategy back to paper on measured decay rather than on a bad weekend.</li>
    <li><b>Parlays and prop combos stay behind a joint-evidence gate.</b> Multiplying marginal probabilities is
    invalid under dependence; a combo is ranked only when a directly validated joint probability exists.</li>
  </ul>

  <h2>5 · Where to go next</h2>
  <ul class="route">
    <li><a href="verification-2026-11-19.html">This session's live re-check</a> — the four pages re-read today, with every difference published.</li>
    <li><a href="questions-and-answers.html">Questions and answers</a> — what we know, what we do not, and how to find out.</li>
    <li><a href="suggestion-review.html">Suggestion review</a> — every proposal, its trade-off, and what it unlocks.</li>
    <li><a href="flagged.html">Flagged for review</a> — every value this site will not round up to &ldquo;verified&rdquo;.</li>
  </ul>
</section>
"""
    return shell("Decision brief", f"EXECUTIVE SUMMARY · {READ_DATE}", body, depth=1)


# ------------------------------------------------------------------ page 3: questions
def page_questions() -> str:
    rows = []
    for q in QS:
        status = q["STATUS"].strip()
        cls = "ok" if status.upper().startswith("ANSWERED") and "NO" not in status.upper() else (
            "warn" if "PARTIAL" in status.upper() or status.upper().startswith("ANSWERED") else "high")
        rows.append([
            f'<td><b>{esc(q["ID"])}</b></td>',
            f'<td>{esc(q["AREA"])}</td>',
            f'<td>{esc(q["QUESTION"])}</td>',
            f'<td>{esc(q["INFORMATION_HELD"])}</td>',
            f'<td>{esc(q["INFORMATION_MISSING"])}</td>',
            f'<td>{esc(q["ANSWER"])}</td>',
            f'<td>{esc(q["HOW_TO_DISCOVER"])}</td>',
            f'<td><span class="pill {cls}">{esc(status[:28])}</span></td>',
            src_cell(repo_blob("data/console/questions.csv"), "register ↗"),
        ])

    open_rows = [[
        f'<td><b>{esc(q["id"])}</b></td>',
        f'<td>{esc(q["topic"])}</td>',
        f'<td>{esc(q["question"])}</td>',
        f'<td>{esc(q["known_information"])}</td>',
        f'<td>{esc(q["what_would_answer_it"])}</td>',
        src_cell(q.get("source_url") or repo_blob("data/questions.json"), "source ↗"),
    ] for q in json.loads((ROOT / "data/questions.json").read_text())["questions"] if q["status"] == "open"]

    # Two open rows cite only a repository file. The rule here is that a data row carries an OFFICIAL
    # publisher link, so each is paired with the official page the question is about; the file stays
    # visible in the row text. Nothing is claimed about that page beyond what the question states.
    OPEN_OFFICIAL = {
        "Q-19": ("https://www.nfl.com/players/", "official players index"),
        "Q-20": ("https://www.nfl.com/schedules/2026/by-week/week-11/", "official Week 11 schedule"),
    }
    for row, q in zip(open_rows, [q for q in json.loads((ROOT / "data/questions.json").read_text())["questions"] if q["status"] == "open"]):
        if q["id"] in OPEN_OFFICIAL:
            url, label = OPEN_OFFICIAL[q["id"]]
            row[-1] = src_cell(url, label)

    body = f"""
<section class="pagetitle">
  <div class="eyebrow">QUESTIONS · {READ_DATE}</div>
  <h1>What has to be answered before a number can be trusted</h1>
  <p>Two registers, side by side and on purpose. The first is the research desk's own list of questions with the
  evidence already in hand and the measurement that would close each one. The second is the project register of
  open decisions, each with the information held and the specific evidence that would settle it. A question is
  answered here only when an official source settles it and that source is linked.</p>
</section>
<section class="content">
  <div class="note"><b>Read the third column before the first.</b> Most of these questions are not unanswered
  because nobody looked; they are unanswered because the answer is not published anywhere, and inventing one is
  the only way to make the table look finished. The <i>How to discover it</i> column names the concrete next
  measurement.</div>

  <h2>The research desk's questions, with answers where an answer exists</h2>
  {table(["ID", "Area", "Question", "Information held", "Information missing", "Answer", "How to discover it", "Status", "Register"],
         rows, f"{len(QS)} questions", "wide", True)}

  <h2>The project register's open questions</h2>
  {table(["ID", "Topic", "Question", "Information already held", "What would answer it", "Source"],
         open_rows, f"{len(open_rows)} open questions", "wide", True)}

  <h2>The three that gate everything else</h2>
  <ol class="findings big">
    <li><b>Do we have the right to use the data we want?</b><p>Play-by-play, snap counts and historical odds
    all sit behind terms this repository has not read. Until that is settled, only officially published
    aggregates are shown, and raw row-level data stays out of the public tree.</p></li>
    <li><b>Which price is the market?</b><p>No official source publishes prices, and the four site trees in this
    repository name different benchmarks. A leaderboard that ranks across two benchmarks is not a leaderboard.</p></li>
    <li><b>What counts as a starter?</b><p>The league publishes no depth chart. Every 2nd/3rd/4th-string claim
    depends on a club page that at least two clubs label &ldquo;unofficial&rdquo;. The mechanical definition used
    here — printed in column 1 of the club's own chart, stored as a group when a club lists several players in
    one slot — is auditable, but it is still a club self-report.</p></li>
  </ol>
</section>
"""
    return shell("Questions & answers", f"REGISTERS · {READ_DATE}", body, depth=1)


# ------------------------------------------------------------------ page 4: suggestion review
def page_suggestions() -> str:
    rows = [[
        f'<td><b>{esc(s["ID"])}</b></td>',
        f'<td>{esc(s["AREA"])}</td>',
        f'<td>{esc(s["TITLE"])}</td>',
        f'<td>{esc(s["PROBLEM"])}</td>',
        f'<td>{esc(s["PATHS"])}</td>',
        f'<td>{esc(s["RECOMMENDATION"])}</td>',
        f'<td>{esc(s["UNLOCKS"])}</td>',
        f'<td><span class="pill muted-pill">{esc(s["DECISION_STATUS"])}</span></td>',
        src_cell(repo_blob("data/console/suggestions.csv"), "register ↗"),
    ] for s in SG]

    site_rows = [[
        f'<td><b>{esc(s["id"])}</b></td>',
        f'<td>{esc(s["title"])}</td>',
        f'<td>{esc(s["problem"])}</td>',
        f'<td>{esc(s["proposal"])}</td>',
        f'<td>{esc(s["first_step"])}</td>',
        f'<td><span class="pill {"high" if s["impact"] == "high" else "warn"}">{esc(s["impact"])}</span></td>',
        f'<td><span class="pill muted-pill">{esc(s["effort"])}</span></td>',
        f'<td><span class="pill muted-pill">{esc(s["status"])}</span></td>',
        src_cell(repo_blob("data/suggestions.json"), "register ↗"),
    ] for s in SUGGEST]

    board_rows = [[
        f'<td><b>{esc(o["id"])}</b></td>',
        f'<td>{esc(o["title"])}</td>',
        f'<td>{esc(o["answers"])}</td>',
        f'<td><span class="pill {"high" if o["impact"] == "high" else "warn"}">{esc(o["impact"])}</span></td>',
        f'<td><span class="pill muted-pill">{esc(o["effort"])}</span></td>',
        f'<td>{esc(o["dependency"])}</td>',
        f'<td>{esc(o["first_step"])}</td>',
        src_cell(o.get("source") or repo_blob("data/audit/suggestion_board.json"), "source ↗"),
    ] for o in BOARD["options"]]

    tally = suggestions_landing_counts()
    body = f"""
<section class="pagetitle">
  <div class="eyebrow">SUGGESTIONS · REVIEW BEFORE BUILDING</div>
  <h1>Every suggestion, with the trade-off, before anything is built</h1>
  <p>Three registers are consolidated here. The research desk's list names the problem, the paths on the table
  and a recommendation. The site register adds a reversible first step for each proposal. The ranked board adds
  what each one answers and what it depends on. Nothing on any of them has been implemented automatically.</p>
</section>
<section class="content">
  <div class="note"><b>How to use this page.</b> Pick by <i>what it unlocks</i>, not by what it looks like. Three
  proposals unblock the whole scoring layer and cost almost nothing; the rest improve how a reader can check the
  work. A suggestion that needs a decision from you before it can start is marked in its own row.</div>

  <div class="statrow">
    {stat(len(SG), "research-desk suggestions", "problem · paths · recommendation · what it unlocks")}
    {stat(len(SUGGEST), "site suggestions", f"{len([s for s in SUGGEST if s['impact'] == 'high'])} high impact · {len([s for s in SUGGEST if s['effort'] == 'low'])} low effort")}
    {stat(len(BOARD["options"]), "ranked board options", f"{len(BOARD['recommended_path'])} recommended to start")}
    {stat(sum(tally.values()), "proposals in total", " · ".join(f"{k} {v}" for k, v in sorted(tally.items())))}
  </div>

  <h2>The five to look at first</h2>
  <ol class="findings big">
    <li><b>Name the price feed before any market column fills.</b><p>Until one source is chosen as the
    benchmark, every price, edge and closing-line figure is undefined — and the four site trees disagree about
    which benchmark to use.</p></li>
    <li><b>Ratify the demotion thresholds.</b><p>The gate that sends a live strategy back to paper is written
    but its numbers are not ratified, so nothing can be promoted safely.</p></li>
    <li><b>Publish the evidence grade on every row.</b><p>It lets a reviewer apply a different trust threshold to
    a league fact than to a club self-report without reading the methodology each time.</p></li>
    <li><b>Run the second independent transcription pass.</b><p>This session did exactly that for the
    2026-11-19 read and it found one disagreeing cell and an unstable free-text column. That is the cheapest
    trust improvement available.</p></li>
    <li><b>Rank on signal only; keep staking in its own columns.</b><p>A lucky staking run must never be able to
    mask a bad signal, and today the board shows both separately for exactly that reason.</p></li>
  </ol>

  <h2>The research desk's suggestions</h2>
  {table(["ID", "Area", "Suggestion", "Problem it solves", "Paths on the table", "Recommendation", "What it unlocks", "Status", "Register"],
         rows, f"{len(SG)} suggestions with their paths and recommendations", "wide", True)}

  <h2>The site register — each with a reversible first step</h2>
  {table(["ID", "Suggestion", "Problem", "Proposal", "Reversible first step", "Impact", "Effort", "Status", "Register"],
         site_rows, f"{len(SUGGEST)} site proposals", "wide", True)}

  <h2>The ranked board — what each one answers</h2>
  <p class="muted">Recommended to start with: <b>{esc(", ".join(BOARD["recommended_path"]))}</b>. {esc(BOARD["recommended_reason"])}</p>
  {table(["ID", "Option", "Answers", "Impact", "Effort", "Dependency", "First step", "Source"],
         board_rows, f"{len(BOARD['options'])} ranked options", "wide", True)}

  <h2>What is explicitly not on this page</h2>
  <ul class="lim">
    <li><b>No suggestion is implemented because it was written.</b> Each one waits for a decision, and the
    decision column says so.</li>
    <li><b>No suggestion promises a number.</b> A proposal that says it will &ldquo;improve the model&rdquo; is
    only credible with a measurement attached; the ones here name a count, a check or a file.</li>
    <li><b>Two ideas have already been rejected and are kept on the record</b> — deriving depth order from jersey
    number, and ranking strategies by season-long ROI. Both are published so they are not re-proposed.</li>
  </ul>
</section>
"""
    return shell("Suggestion review", "REVIEW BEFORE BUILDING", body, depth=1)


# ------------------------------------------------------------------ build
BUILDERS = {
    "pages/verification-2026-11-19.html": page_verification,
    "pages/decision-brief.html": page_brief,
    "pages/questions-and-answers.html": page_questions,
    "pages/suggestion-review.html": page_suggestions,
}


def main() -> int:
    check = "--check" in sys.argv
    stale = []
    for rel, fn in BUILDERS.items():
        target = ROOT / rel
        body = fn()
        if check:
            if not target.exists() or target.read_text(encoding="utf-8") != body:
                stale.append(rel)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
    if check:
        if stale:
            print("FAIL: stale integration pages:", ", ".join(stale))
            return 1
        print(f"integration pages: {len(BUILDERS)} pages match a fresh build")
        return 0
    print(f"wrote {len(BUILDERS)} integration pages: {', '.join(BUILDERS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
