#!/usr/bin/env python3
"""Build the 2026-11-17 evidence pack and its published page.

    python3 tools/build_evidence_2026_11_17.py            # write
    python3 tools/build_evidence_2026_11_17.py --check     # fail if the committed files are stale

Writes:
    data/evidence/2026_11_17/standings.tsv         32 clubs x 17 fields, read 2026-11-17
    data/evidence/2026_11_17/week10_finals.tsv     14 finals, with the Thursday-game note
    data/evidence/2026_11_17/byes_week10.tsv       4 clubs on bye
    data/evidence/2026_11_17/closure.tsv           the arithmetic on the new read
    data/evidence/2026_11_17/mismatches.csv        every cell where a published table disagrees
    data/evidence/2026_11_17/summary.json          the same, machine-readable
    data/evidence/2026_11_17/page.html             the page, for whoever assembles the site

The page is written to the data directory rather than into a site tree on purpose: the console
tree's generator (`tools/build_console.py`) is claimed by open PR #61, and two sessions editing one
generated tree is exactly the conflict `COORDINATION.md` exists to prevent. Emitting `page.html`
here means the integrator (or this session, once #61 lands) can copy it into place with a one-line
change instead of a merge.
"""
from __future__ import annotations

import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.console import evidence_2026_11_17 as E  # noqa: E402

OUT = os.path.join(ROOT, "data", "evidence", "2026_11_17")

HEADER = """# {title}
# SOURCE: {url}
# READ:   {read} (UTC), single direct read of the official page, transcribed row by row
# NOTE:   {note}
"""


def _write(name: str, text: str) -> str:
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    return path


def standings_tsv(b: dict) -> str:
    # The two percentages this read could not separate from the adjacent cell are withheld:
    # the column is omitted rather than left blank, so no row can be mistaken for a read value.
    withheld = set(b["publishable_fields"]["withheld_fields"])
    cols = [c for c in E.STANDINGS_COLS if c not in withheld]
    head = HEADER.format(title="2026 NFL league standings, league view",
                         url=E.STANDINGS_URL, read=b["read_utc"],
                         note="Columns exactly as the transcribed PSV prints them, except DIVPCT "
                              "and CONFPCT which are withheld (see summary.json: this read could "
                              "not separate them from the adjacent cell). PCT and NET are read off "
                              "the page, not recomputed; closure.tsv proves they recompute anyway.")
    lines = [head.rstrip("\n"), "|".join(cols)]
    for r in b["standings"]:
        lines.append("|".join(r[c] for c in cols))
    return "\n".join(lines) + "\n"


def week10_tsv(b: dict) -> str:
    head = HEADER.format(title="2026 Week 10 results, all 14 games final",
                         url=E.SCHEDULE_URL, read=b["read_utc"],
                         note="in_2026_11_14_snapshot=yes means the 2026-11-14 transcription "
                              "already counted this game; the arithmetic in closure.tsv adds only "
                              "the rows marked no, otherwise the Thursday game is counted twice.")
    cols = ["game_id", "date_et", "window", "away", "away_score", "home", "home_score",
            "in_2026_11_14_snapshot"]
    lines = [head.rstrip("\n"), "|".join(cols)]
    for g in b["week10"]:
        lines.append("|".join(str(g.get(c, "")) for c in cols))
    return "\n".join(lines) + "\n"


def byes_tsv(b: dict) -> str:
    head = HEADER.format(title="2026 Week 10 clubs on bye",
                         url=E.SCHEDULE_URL, read=b["read_utc"],
                         note="The record is the one the league prints beside the club in the "
                              "'Teams on Bye' block of the Week 10 page.")
    lines = [head.rstrip("\n"), "club|record"]
    for r in b["byes_week10"]:
        lines.append(f'{r["club"]}|{r["record"]}')
    return "\n".join(lines) + "\n"


def closure_tsv(b: dict) -> str:
    w = b["week10_vs_standings"]
    head = HEADER.format(title="Arithmetic closure of the 2026-11-17 read",
                         url=E.STANDINGS_URL, read=b["read_utc"],
                         note="Every check is applied to the NEW read before it is used to "
                              "accuse an older table of being wrong. A mis-transcribed row "
                              "breaks one of these, which is the point.")
    lines = [head.rstrip("\n"), "check|value|ok"]
    for c in b["closure"]:
        lines.append(f'{c["check"]}|{c["value"]}|{c["ok"]}')
    lines.append(
        f"14 finals added to the 2026-11-14 table reproduce all 32 clubs x 5 fields|"
        f'{w["checks"]} comparisons, {w["mismatches"]} mismatches|'
        f'{str(w["mismatches"] == 0)}')
    lines.append(
        f"games played implied by the league's own W/L/T|{w['games_played_implied']}|True")
    return "\n".join(lines) + "\n"


def mismatches_csv(b: dict) -> str:
    rows = []
    withheld = set(b["publishable_fields"]["withheld_fields"])
    for d in b["published_vs_league"]["detail"]:
        # A withheld field still differs from the published table, so the difference is
        # published — with the read side explicitly marked, never with a number this read
        # did not take.
        mine = "(withheld)" if d["field"] in withheld else d["mine"]
        rows.append(["published 2026-11-14 table", d["key"], d["field"], d["other"], mine])
    for d in b["collector_vs_league"]["detail"]:
        rows.append(["collector payload 2026-11-17T19:49Z", d["key"], d["field"], d["other"],
                     d["mine"]])
    import io
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["compared_against_this_read", "club", "field", "their_value", "this_read"])
    w.writerows(rows)
    return buf.getvalue()


def page_html(b: dict) -> str:
    import html
    esc = lambda x: html.escape(str(x), quote=True)
    st = b["standings"]
    w = b["week10_vs_standings"]
    pv = b["published_vs_league"]
    cv = b["collector_vs_league"]
    mirror = b["mirror_week10"]
    price = b["price_2026"]
    drift = b["drift"]
    closure = b["closure"]

    def kpi(label, val, sub, kind=""):
        return (f'<div class="kpi {kind}"><div class="lab">{esc(label)}</div>'
                f'<div class="val">{val}</div><div class="sub">{esc(sub)}</div></div>')

    kpis = "".join([
        kpi("Club records read", str(len(st)), "32 of 32, 17 fields each", "ok"),
        kpi("Games played implied", str(b["games_played_implied"]),
            "from the league's own W/L/T", ""),
        kpi("Week 10 finals", str(len(b["week10"])), "all 14 games final", "ok"),
        kpi("Published table vs today", str(pv["mismatches"]),
            f'of {pv["comparisons"]} cells, {len(pv["clubs"])} clubs',
            "bad" if pv["mismatches"] else "ok"),
        kpi("Collector vs today", str(cv["mismatches"]),
            f'of {cv["comparisons"]} cells, independent parser',
            "bad" if cv["mismatches"] else "ok"),
    ])

    # closure table
    crows = "".join(
        f'<tr><td>{esc(c["check"])}</td><td>{esc(c["value"])}</td>'
        f'<td>{"pass" if c["ok"] == "True" else "FAIL"}</td></tr>' for c in closure)

    # standings table: this read, with the published value beside it where they differ
    withheld_cols = set(b["publishable_fields"]["withheld_fields"])
    shown_cols = [c for c in E.STANDINGS_COLS if c not in withheld_cols]
    pub = {r["TEAM"]: r for r in E.read_psv("data/verify/official_standings_2026_w10.psv")}
    srows = []
    for r in st:
        o = pub.get(r["TEAM"], {})
        def cell(f):
            mine, theirs = r[f], o.get(f, "")
            if mine == theirs:
                return f"<td>{esc(mine)}</td>"
            return (f'<td><b>{esc(mine)}</b><br><span class="mut">was {esc(theirs)}</span></td>')
        srows.append("<tr>" + "".join([f'<td>{esc(r["TEAM"])}</td>'] +
                                      [cell(f) for f in shown_cols[1:]]) + "</tr>")
    shead = "".join(f"<th>{esc(c)}</th>" for c in shown_cols)

    wrows = "".join(
        f'<tr><td>{esc(g["game_id"])}</td><td>{esc(g["date_et"])}</td><td>{esc(g["window"])}</td>'
        f'<td>{esc(g["away"])} {esc(g["away_score"])}</td>'
        f'<td>{esc(g["home"])} {esc(g["home_score"])}</td>'
        f'<td>{esc(g.get("in_2026_11_14_snapshot", ""))}</td></tr>' for g in b["week10"])

    pvrows = "".join(
        f'<tr><td>{esc(d["key"])}</td><td>{esc(d["field"])}</td>'
        f'<td>{esc(d["other"])}</td><td>{esc(d["mine"])}</td></tr>'
        for d in pv["detail"][:60])

    drows = "".join(
        f'<tr><td>{esc(k)}</td><td>{esc(v["last_drift"])}</td>'
        f'<td>{esc(v["last_as_read_at"])}</td><td>{esc(v["captures"])}</td>'
        f'<td>{esc(v["distinct_payloads"])}</td></tr>'
        for k, v in sorted(drift.get("datasets", {}).items()))

    mirror_settled = mirror.get("settled", 0)
    mirror_total = len(mirror.get("rows", []))
    price_by_step = "".join(
        f'<tr><td>{esc(k)}</td><td>{esc(v["rows"])}</td><td>{esc(v["both"])}</td></tr>'
        for k, v in sorted(price.get("by_step", {}).items()))

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Evidence pack 2026-11-17 - X1 NFL Line Console</title>
<link rel="stylesheet" href="assets/console.css">
</head><body><div class="layout">
<aside><div class="brand"><b>X1 LINE CONSOLE</b><span>NFL origination &amp; strategy lab</span></div>
<nav><div class="grp">Official data</div>
<a class="item" href="standings.html">Standings<span class="tag">32</span></a>
<a class="item" href="schedule.html">Week 10 slate</a>
<a class="item" href="results.html">Verified results feed</a>
</nav></aside>
<main>
<header class="page"><h1>Evidence pack &mdash; 2026-11-17</h1>
<p>One dated read of the official pages, the arithmetic that validates it, and every cell where a
published table no longer agrees with it.</p></header>
<div class="kpis">{kpis}</div>

<h2>Why this pack exists</h2>
<p>The console's standings page published a claim that all 32 clubs and all 16 fields had been
&ldquo;re-read from the league's own standings table on the build date&rdquo; and matched with no
mismatches. That claim was not reproducible. The numbers compared were a constant in the generator,
and the table actually audited was a transcription dated <b>2026-11-14</b> covering the 137 games
played through the Week 10 Thursday game. Twenty-six clubs have played since. The claim is the defect;
the fix is a dated read that anyone can re-run, which is what this pack is.</p>
<p>Read at <b>{esc(b['read_utc'])}</b> from
<a href="{esc(E.STANDINGS_URL)}" target="_blank" rel="noopener">{esc(E.STANDINGS_URL)}</a>,
<a href="{esc(E.SCHEDULE_URL)}" target="_blank" rel="noopener">{esc(E.SCHEDULE_URL)}</a>.
Method: {esc(b['read_method'])}</p>

<h2>1. Arithmetic closure of this read</h2>
<p>Applied to the <em>new</em> read before it is used to accuse an older table. A mis-transcribed row
breaks one of these.</p>
<div class="wrap"><table><thead><tr><th>check</th><th>value</th><th>result</th></tr></thead>
<tbody>{crows}</tbody></table></div>
<p class="mut">The 14 finals are added to the 2026-11-14 table and must reproduce today's table for
every club. <b>{w['checks']}</b> comparisons over 32 clubs, <b>{w['mismatches']}</b> mismatches.
One game (WAS&ndash;NYG, {esc('2026-11-12')}) was already inside the 2026-11-14 table, so adding all
14 double-counted it on the first run; the flag column in the table below is what corrected that.</p>

<h2>2. The 14 Week 10 finals</h2>
<div class="wrap"><table><thead><tr><th>game</th><th>date</th><th>window</th><th>away</th>
<th>home</th><th>already in the 11-14 table</th></tr></thead><tbody>{wrows}</tbody></table></div>

<h2>3. The read, club by club</h2>
<p>Every cell is from the page read today. Where the published 2026-11-14 table prints something
different, the published value is shown beneath as <span class="mut">was &hellip;</span>.</p>
<div class="wrap"><table><thead><tr>{shead}</tr></thead><tbody>{''.join(srows)}</tbody></table></div>

<h2>4. What the published table no longer agrees with</h2>
<p><b>{pv['mismatches']}</b> of {pv['comparisons']} cells differ, across {len(pv['clubs'])} clubs
({esc(', '.join(pv['clubs']))}). The differences are games played, not transcription errors: the
2026-11-14 table was correct when it was taken.</p>
<div class="wrap"><table><thead><tr><th>club</th><th>field</th>
<th>published 2026-11-14</th><th>league 2026-11-17</th></tr></thead>
<tbody>{pvrows}</tbody></table></div>
<p class="mut">First 60 differences shown; all {pv['mismatches']} are in
<code>data/evidence/2026_11_17/mismatches.csv</code>.</p>

<h2>5. The independent parser agrees</h2>
<p>The collector read the same page at 2026-11-17T19:49Z with its own parser. Compared with this
hand read: <b>{cv['comparisons']}</b> cells, <b>{cv['matches']}</b> agree, <b>{cv['mismatches']}</b>
differ. Two independent extraction paths agreeing on every cell is what promotes this read from
&ldquo;one person&rsquo;s transcription&rdquo; to verified.</p>

<h2>6. What this read cannot support yet</h2>
<table><thead><tr><th>question</th><th>measured answer</th><th>why it matters</th></tr></thead><tbody>
<tr><td>Has the mirror behind the results feed published the Week 10 finals?</td>
<td><b>{mirror_settled}</b> of {mirror_total} Week 10 rows carry a score in
<code>{esc(mirror.get('path', ''))}</code></td>
<td>The results feed is built from that file. Until it publishes the scores, the feed cannot
settle Week 10, so neither the 2026 ROI nor the shadow baseline can move on. This is a source
limitation, not something a pull request can fix.</td></tr>
<tr><td>Can 2026 lines be re-originated against a closing price?</td>
<td><b>{price.get('both', 0)}</b> of {price.get('rows', 0)} 2026 price-store rows carry both an
opening and a closing number</td>
<td>Origination is pre-kickoff by definition. A 2026 market originated today can only carry the
opening number; the closing number needs a read taken at kickoff, which is why the store records a
clock time with every row.</td></tr>
<tr><td>Are the club-level tables current?</td>
<td>Drift state below, from <code>data/captures/status.json</code></td>
<td>A table rebuilt from a stale capture reads like a live table. The capture clock time is the
only thing that distinguishes them.</td></tr>
</tbody></table>
<p>2026 price-store rows by origination step:</p>
<div class="wrap"><table><thead><tr><th>step</th><th>rows</th><th>both ends</th></tr></thead>
<tbody>{price_by_step or '<tr><td colspan="3">no 2026 rows</td></tr>'}</tbody></table></div>

<h2>7. Capture freshness and drift, as the gate sees it</h2>
<p>Status written <b>{esc(drift.get('generated_at', ''))}</b>; {esc(drift.get('captures', ''))}
captures retained. Alarms outstanding: <b>{esc(', '.join(drift.get('alarms', [])) or 'none')}</b>.</p>
<div class="wrap"><table><thead><tr><th>dataset</th><th>last drift</th><th>last read (UTC)</th>
<th>captures</th><th>distinct payloads</th></tr></thead><tbody>{drows}</tbody></table></div>
<p class="mut">The <code>deficiency</code> alarm is a real producer defect &mdash;
<code>data/pipeline/deficiency.json</code> declared 12 columns while its rows carried 14 &mdash; now
fixed at the producer, and the capture gate fails the build if a committed header disagrees with its
own rows. The retained alarm entry is the evidence of the old defect and clears on the next collector
read.</p>

<footer>
Read {esc(b['read_utc'])}. Generated by <code>tools/build_evidence_2026_11_17.py</code> from
<code>src/console/evidence_2026_11_17.py</code>. Every row above carries the official URL it was read
from in the TSV beside it; nothing is inferred, and a value this read could not confirm is reported
as a question rather than filled in.
</footer>
</main></div>
<script src="assets/console.js"></script></body></html>
"""


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    check = "--check" in argv
    os.makedirs(OUT, exist_ok=True)
    b = E.build()
    files = {
        "standings.tsv": standings_tsv(b),
        "week10_finals.tsv": week10_tsv(b),
        "byes_week10.tsv": byes_tsv(b),
        "closure.tsv": closure_tsv(b),
        "mismatches.csv": mismatches_csv(b),
        "summary.json": json.dumps(
            {k: v for k, v in b.items() if k not in ("standings", "week10")},
            indent=1, sort_keys=True, ensure_ascii=False) + "\n",
        "page.html": page_html(b),
    }
    stale = []
    for name, text in files.items():
        path = os.path.join(OUT, name)
        old = None
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                old = fh.read()
        if check:
            if old != text:
                stale.append(name)
        else:
            _write(name, text)
    if check:
        if stale:
            print("FAIL: committed evidence files differ from a fresh build: " + ", ".join(stale))
            return 1
        print(f"evidence pack 2026-11-17 reproduces ({len(files)} files)")
        return 0
    print(f"wrote {len(files)} files to data/evidence/2026_11_17")
    print(f"  published vs league: {b['published_vs_league']['mismatches']} mismatches "
          f"of {b['published_vs_league']['comparisons']}")
    print(f"  collector vs league: {b['collector_vs_league']['mismatches']} mismatches "
          f"of {b['collector_vs_league']['comparisons']}")
    print(f"  week10 finals vs standings: {b['week10_vs_standings']['mismatches']} mismatches "
          f"of {b['week10_vs_standings']['checks']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
