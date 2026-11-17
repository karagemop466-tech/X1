#!/usr/bin/env python3
"""One-shot, attributed edit of tools/build_site.py (session arena-e1436334-x1, group "site-verify").

Renders the dated 2026-11-17 re-verification pack as its own page, so the evidence that closed Week 10 is
a table a reader can check rather than a directory of files. Additive: a loader block, one page function,
one NAV entry, one write() call.

The anchor must match EXACTLY once or the patch aborts without writing. A signature check in main() makes
double application impossible (some replacements contain their own anchor, so counting alone would not).
Generated HTML is never hand-edited: run tools/build_site.py after this.

Usage:  python3 tools/patch_page_verification_e1436334.py
        python3 tools/patch_page_verification_e1436334.py --revert
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "tools", "build_site.py")
SIGNATURE = "def page_verification_2026_11_17()"

LOADER_OLD = '''PACK1616 = load_json("verification/2026_11_16/verification_summary_2026_11_16.json")'''

LOADER_NEW = '''PACK1616 = load_json("verification/2026_11_16/verification_summary_2026_11_16.json")
# Added by session arena-e1436334-x1 (additive): the 2026-11-17 re-verification pack and its checker's
# verdicts, rendered on pages/verification-2026-11-17.html. The pack is the transcription; the summary is
# the arithmetic over it; the page shows both, so a reader can see which number was checked how.
PACK17 = load_json("verification/2026_11_17/verification_summary_2026_11_17.json")
STANDINGS17 = read_rows("data/verification/2026_11_17/official_standings_2026_11_17.tsv", "\\t")
W10_17 = read_rows("data/verification/2026_11_17/official_w10_results_2026_11_17.tsv", "\\t")
W11_17 = read_rows("data/verification/2026_11_17/official_w11_slate_2026_11_17.tsv", "\\t")'''

PAGE_OLD = '''def page_index():'''

PAGE_NEW = '''def page_verification_2026_11_17():
    """The dated re-verification: three official pages read on one date, and the checks run over them.

    Everything on the page is read out of the artefacts. The prose interprets the numbers; it never
    restates one as a second figure that could drift away from the first.
    """
    checks = []
    for name, v in PACK17["checks"].items():
        counts = "; ".join(f"{k}={x}" for k, x in sorted(v.items())
                           if isinstance(x, int) and not isinstance(x, bool))
        fails = v.get("failures") or []
        checks.append([
            f'<td><b>{esc(name)}</b></td>',
            f'<td><span class="pill {"ok" if v["verdict"] == "PASS" else "high"}">'
            f'{esc(v["verdict"])}</span></td>',
            cell(counts, "this check publishes no counts"),
            (f'<td>{esc(fails[0])}' + (f' <span class="muted">(+{len(fails) - 1} more)</span>'
                                       if len(fails) > 1 else "") + "</td>") if fails
            else cell("none"),
            src_cell(repo_blob("tools/verify_2026_11_17.py"), "check code \\u2197"),
        ])

    _STANDINGS_URL = PACK17["reads"][1]["page"]
    st_rows = [[
        f'<td>{esc(r["rank"])}</td>',
        f'<td><b>{esc(r["team_name"])}</b> <span class="muted">{esc(r["abbr"])}</span></td>',
        f'<td>{esc(r["w"])}-{esc(r["l"])}'
        + (f'-{esc(r["t"])}' if r["t"] not in ("", "0") else "") + '</td>',
        cell(r["pct"]), cell(r["pf"]), cell(r["pa"]), cell(r["net_pts"]),
        cell(r["home"], "not printed by the source"), cell(r["road"], "not printed by the source"),
        cell(r["div"], "not printed by the source"), cell(r["conf"], "not printed by the source"),
        cell(r["strk"], "not printed by the source"), cell(r["last5"], "not printed by the source"),
        # the pack carries one source URL for the whole page (it is in the file header, not a column), so
        # every row links that page rather than inventing a per-club URL the read does not have
        src_cell(_STANDINGS_URL, "standings page \\u2197"),
    ] for r in STANDINGS17]

    res_rows = [[
        f'<td>{esc(r["game_id"])}</td>',
        cell(r["date_et"]), cell(r["time_et"], "not printed on a Final row"),
        cell(r["network"], "not printed by the source"), cell(r["note"], "no label printed"),
        f'<td><b>{esc(r["away"])} {cell_v(r["away_score"])}</b> <span class="muted">({esc(r["away_record"])})</span>'
        f' at <b>{esc(r["home"])} {cell_v(r["home_score"])}</b> <span class="muted">({esc(r["home_record"])})</span></td>',
        f'<td><span class="pill {"ok" if r["status"] == "Final" else "warn"}">{esc(r["status"])}</span></td>',
        src_cell(r["source_url"], "Week 10 page \\u2197"),
    ] for r in W10_17]

    sl_rows = [[
        f'<td>{esc(r["game_id"])}</td>',
        cell(f'{r["date_et"]} {r["time_et"]}'.strip(), "not printed by the source"),
        cell(r["network"], "not printed by the source"),
        (f'<td><b>{esc(r["away"])}</b> ({esc(r["away_record"])}) at <b>{esc(r["home"])}</b> '
         f'({esc(r["home_record"])})</td>' if r["row_type"] == "game"
         else f'<td><b>{esc(r["away"])}</b> on bye ({esc(r["away_record"])})</td>'),
        f'<td>{esc(r["status"])}</td>',
        cell(r["note"], "no label printed"),
        src_cell(r["source_url"], "Week 11 page \\u2197"),
    ] for r in W11_17]

    read_rows = [[
        src_cell(x["page"], x["page"]),
        f'<td><code>{esc(x["file"])}</code></td>',
        f'<td>{x["rows"]}</td>',
        cell(x.get("clock_noted_by_reader", ""), "no clock recorded"),
        src_cell(x["page"], "official page \u2197"),
    ] for x in PACK17["reads"]]

    # no bespoke class names here on purpose: `tools/check_links.py` fails the build when markup uses a
    # class the shared stylesheet does not define, and assets/site.css is not this session's file.
    _HASH_PATHS = {
        "official_w10_results_2026_11_17.tsv": "data/verification/2026_11_17/official_w10_results_2026_11_17.tsv",
        "official_standings_2026_11_17.tsv": "data/verification/2026_11_17/official_standings_2026_11_17.tsv",
        "official_w11_slate_2026_11_17.tsv": "data/verification/2026_11_17/official_w11_slate_2026_11_17.tsv",
        "reads.tsv": "data/results/_raw/reads.tsv",
        "mirror_games.csv": "data/raw/nflverse/games.csv",
    }
    hashes = [[f'<td><code>{esc(k)}</code></td>', f'<td><code>{esc(v)}</code></td>',
               cell("sha256 of the committed bytes, so a reader diffing the pack diffs these"),
               src_cell(repo_blob(_HASH_PATHS.get(k, "data/verification/2026_11_17/")), "file \u2197")]
              for k, v in PACK17["transcription_hashes"].items()]

    passed = sum(1 for v in PACK17["checks"].values() if v["verdict"] == "PASS")
    body = f"""
<section class="pagetitle">
  <div class="eyebrow">VERIFICATION &middot; READ {esc(PACK17["reads"][0]["read_on"])}</div>
  <h1>The 2026-11-17 re-verification: three official pages, {len(PACK17["checks"])} checks, one verdict each</h1>
  <p>Week 10 closed on this date, so every published number that keys off the 2026 corpus had to be
  re-derived rather than extended. This page is the re-derivation: the dated transcriptions, the arithmetic
  <code>tools/verify_2026_11_17.py</code> runs over them, and the list of what that command deliberately
  does <b>not</b> check. A pack nothing executes is a file, not a check, so the same tool is a CI gate
  (<code>--check</code>), and its committed summary is reproducible from the reads alone &mdash; it holds no
  wall-clock field.</p>
</section>

<section class="content">
  <div class="statrow">
    {stat(len(PACK17["checks"]), "checks run", "each one arithmetic over a printed value")}
    {stat(f"{passed}/{len(PACK17['checks'])}", "checks passed", f"overall verdict {PACK17['verdict']}")}
    {stat(len(STANDINGS17), "clubs transcribed", "the standings page, in the page's own order")}
    {stat(len(W10_17), "Week 10 fixtures", "every one printed Final on this read")}
  </div>

  <h2>The three reads</h2>
  {table(["Official page", "Committed transcription", "Rows", "Reader's own clock note", "Source"], read_rows,
         "hand transcriptions; the page reader stamps no timestamp, hence the last column", "", True)}
  <div class="note"><b>On the two clocks.</b> {esc(PACK17["read_clock_note"])}</div>

  <h2>Checks</h2>
  {table(["Check", "Verdict", "Counts it publishes", "First failure", "Code"], checks,
         "tools/verify_2026_11_17.py over data/verification/2026_11_17/", "wide", True)}
  <p class="muted">Every check is arithmetic on a value an official page printed: standings identities
  (NET = PF &minus; PA, PCT = (W + T/2)/GP, HOME + ROAD = W&ndash;L&ndash;T), league closure, three-page
  record agreement, corpus admission, the fingerprinted mirror as a cross-check, the sealed ledger re-derived
  at its own record time, the price-discipline rule, the forward slate's 13 + 6 = 32, and a second
  independent read of the standings page. No check reads a model output, so no model can validate itself.</p>

  <h2>What this pack does not check</h2>
  <ul>
  {chr(10).join(f"    <li>{esc(x)}</li>" for x in PACK17["not_checked_here"])}
  </ul>

  <h2>League standings, as printed ({esc(PACK17["reads"][1]["read_on"])})</h2>
  {table(["#", "Club", "W-L-T", "PCT", "PF", "PA", "NET", "Home", "Road", "Div", "Conf", "Streak",
          "Last 5", "Source"], st_rows,
         "32 clubs in the order the page prints; the split columns are the ones no earlier round had diffed "
         "(check B11 compares them with the automated capture, 512 cells, 0 disagreements)", "wide", True)}

  <h2>Week 10, as printed</h2>
  {table(["Game", "Date (ET)", "Kickoff (ET)", "Network", "Label", "Score (records as printed)", "Status",
          "Source"], res_rows,
         "transcribed exactly as the by-week page prints them", "wide", True)}
  <p class="muted"><b>Venue is not on this table, because it is not on that page.</b> The weekly schedule
  page prints no venue for any fixture, so a venue column would be blank 14 times over &mdash; which is a
  fact about the page, not about the games. The one venue this session read is recorded in the pack's header
  and on the fixture's own Game Center page:
  <a href="https://www.nfl.com/games/chargers-at-ravens-2026-reg-10" target="_blank" rel="noopener">
  M&amp;T Bank Stadium, Baltimore MD ↗</a> &mdash; printed there, and it is the venue of the Monday-night
  game that closed the week.</p>

  <h2>Week 11 slate, as printed</h2>
  {table(["Game", "Date &amp; kickoff (ET)", "Network", "Matchup (printed records)", "Status", "Label",
          "Source"], sl_rows,
         "13 fixtures + 6 byes: 32 clubs exactly once, and no score printed for any of them", "wide", True)}

  <h2>Fingerprints</h2>
  {table(["File", "sha256", "Why it is published", "Source"], hashes,
         "so the pack a reader audits is provably the pack that was checked", "", True)}
</section>
"""
    return shell("Re-verification 2026-11-17", "OFFICIAL READS + CHECKS", body, depth=1)


def page_index():'''

NAV_OLD = '''    ("pages/next-decisions.html", "Suggestions & questions"),'''
NAV_NEW = '''    ("pages/next-decisions.html", "Suggestions & questions"),
    # Added by session arena-e1436334-x1: the dated re-verification behind Week 10's closure.
    ("pages/verification-2026-11-17.html", "Re-verification 11-17"),'''

WRITE_OLD = '''    write("pages/next-decisions.html", page_next_decisions())'''

LANDING_OLD = '''  <a href="pages/cross-check.html">Independent cross-check \u2192</a>'''

LANDING_NEW = '''  <a href="pages/cross-check.html">Independent cross-check \u2192</a> &nbsp;\u00b7&nbsp;
  <a href="pages/verification-2026-11-17.html">This round&#39;s re-verification \u2192</a>'''

WRITE_NEW = '''    write("pages/next-decisions.html", page_next_decisions())
    write("pages/verification-2026-11-17.html", page_verification_2026_11_17())'''

EDITS = [
    (LOADER_OLD, LOADER_NEW),
    (LANDING_OLD, LANDING_NEW),
    (PAGE_OLD, PAGE_NEW),
    (NAV_OLD, NAV_NEW),
    (WRITE_OLD, WRITE_NEW),
]


def main() -> int:
    revert = "--revert" in sys.argv
    src = open(TARGET, encoding="utf-8").read()
    if (SIGNATURE in src) and not revert:
        print("already applied (signature present) — refusing to edit twice")
        return 0
    for old, new in EDITS:
        want, repl = (new, old) if revert else (old, new)
        n = src.count(want)
        if n != 1:
            print(f"ABORT: anchor occurs {n} times (expected exactly 1): {want[:70]!r}")
            return 1
        src = src.replace(want, repl, 1)
    with open(TARGET, "w", encoding="utf-8") as fh:
        fh.write(src)
    print(f"{'rolled back' if revert else 'applied'}: {len(EDITS)} edits to tools/build_site.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
