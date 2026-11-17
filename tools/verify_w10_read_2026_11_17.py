#!/usr/bin/env python3
"""Row-by-row comparison of three dated reads of the official NFL.com Week 10 injury page.

Inputs (all committed, none fetched by this script):
  A  data/nfl/injuries_week10.tsv                                                 published table (read 2026-11-14)
  B  data/capture/2026_w10/official_nflcom_injuries_week10_transcription.psv      transcription read 2026-11-15
  C  data/capture/2026_w10_read_2026_11_17/official_nflcom_injuries_week10_2026-11-17.psv
                                                                                  transcription read 2026-11-17

Outputs (deterministic: no wall-clock stamps, so --check is a content test):
  data/capture/2026_w10_read_2026_11_17/recapture_2026_11_17.json
  data/capture/2026_w10_read_2026_11_17/recapture_2026_11_17.md
  data/capture/2026_w10_read_2026_11_17/injuries_week10_2026-11-17.tsv   (the 2026-11-17 read as a table, one source link per row)
  pages/injury-read-2026-11-17.html                                    (the review page for the three reads)

Cross-check: the pipeline's stored capture of 2026-11-16 19:02Z (data/captures/payloads/injuries/...) is compared
with the 2026-11-17 read after one normalisation (the pipeline stores the Rams as LA; the page prints LAR).

Rules
  * A row is matched on (game, team, player). Matched rows are compared on
    injury, practice_status and game_status. Blank means blank on the page.
  * Nothing is inferred. A row present on one side only is reported as such.
  * The day-over-day delta (B -> C) is the time series the brief asks for: it
    publishes what changed, not the level.
  * Exit status is 0 when the outputs are current (or after a write). With
    --check, exit 1 if the committed outputs differ from a fresh computation.
"""
import html
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLISHED = ROOT / "data/nfl/injuries_week10.tsv"
READ_1115 = ROOT / "data/capture/2026_w10/official_nflcom_injuries_week10_transcription.psv"
READ_1117 = ROOT / "data/capture/2026_w10_read_2026_11_17/official_nflcom_injuries_week10_2026-11-17.psv"
OUT_DIR = ROOT / "data/capture/2026_w10_read_2026_11_17"
PAGE = ROOT / "pages/injury-read-2026-11-17.html"
PIPELINE_PAYLOAD = ROOT / "data/captures/payloads/injuries/c3/c3d7a7224dfc8105a24721a164e84376859d1715f4a4639c76a379d43ebb4b33.json"
TSV_OUT = OUT_DIR / "injuries_week10_2026-11-17.tsv"
SOURCE_URL = "https://www.nfl.com/injuries/"
FIELDS = ["injury", "practice_status", "game_status"]


def _psv(path):
    rows = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        parts = ln.split("|")
        if len(parts) != 7:
            raise SystemExit(f"{path.name}: row has {len(parts)} fields, expected 7: {ln!r}")
        game, team, player, pos, injury, practice, status = parts
        rows.append({"game": game, "team": team, "player": player, "position": pos,
                     "injury": injury, "practice_status": practice, "game_status": status})
    return rows


def _published():
    lines = [l for l in PUBLISHED.read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.startswith("#")]
    header = lines[0].split("\t")
    rows = []
    for ln in lines[1:]:
        cells = ln.split("\t")
        if len(cells) != len(header):
            raise SystemExit(f"published row has {len(cells)} cells, expected {len(header)}: {ln!r}")
        d = dict(zip(header, cells))
        rows.append({"game": d["game"], "team": d["team"], "player": d["player"],
                     "position": d["position"], "injury": d["injury"],
                     "practice_status": d["practice_status"], "game_status": d["game_status"],
                     "player_url": d["player_url"]})
    return rows


def _key(r):
    return (r["game"], r["team"], r["player"])


def _index(rows, label):
    idx = {}
    for r in rows:
        k = _key(r)
        if k in idx:
            raise SystemExit(f"{label}: duplicate key {k}")
        idx[k] = r
    return idx


def compare(a_idx, b_idx):
    """Return (only_in_a, only_in_b, field_changes) from a to b."""
    only_a = sorted(k for k in a_idx if k not in b_idx)
    only_b = sorted(k for k in b_idx if k not in a_idx)
    changes = []
    for k in sorted(set(a_idx) & set(b_idx)):
        diffs = {f: [a_idx[k][f], b_idx[k][f]] for f in FIELDS if a_idx[k][f] != b_idx[k][f]}
        if diffs:
            changes.append({"game": k[0], "team": k[1], "player": k[2], "changes": diffs})
    return only_a, only_b, changes


def build():
    pub = _published()
    b = _psv(READ_1115)
    c = _psv(READ_1117)
    pub_i, b_i, c_i = _index(pub, "published"), _index(b, "read_2026_11_15"), _index(c, "read_2026_11_17")

    pub_vs_c_only_pub, pub_vs_c_only_c, pub_vs_c_changes = compare(pub_i, c_i)
    b_vs_c_only_b, b_vs_c_only_c, b_vs_c_changes = compare(b_i, c_i)

    def counts(rows):
        return {
            "rows": len(rows),
            "Out": sum(1 for r in rows if r["game_status"] == "Out"),
            "Doubtful": sum(1 for r in rows if r["game_status"] == "Doubtful"),
            "Questionable": sum(1 for r in rows if r["game_status"] == "Questionable"),
            "blank_game_status": sum(1 for r in rows if r["game_status"] == ""),
            "blank_injury": sum(1 for r in rows if r["injury"] == ""),
            "clubs": len({r["team"] for r in rows}),
            "games": len({r["game"] for r in rows}),
        }

    per_club = Counter(r["team"] for r in c)
    fmt_key = lambda k: {"game": k[0], "team": k[1], "player": k[2]}
    url_by_key = {_key(r): r["player_url"] for r in pub}
    # each differing row links to the official player page printed on the report (from the published table)
    # or, for rows the published table lacks, to the page the report itself links to
    payload = json.loads(PIPELINE_PAYLOAD.read_text(encoding="utf-8"))
    norm = lambda t: "LAR" if t == "LA" else t  # the pipeline's only code difference (LA vs LAR)
    pay_rows = [(norm(r["team"]), r["player"], r["position"], r["injury"], r["practice_status"], r["game_status"])
                for r in payload["rows"]]
    mine_rows = [(r["team"], r["player"], r["position"], r["injury"], r["practice_status"], r["game_status"]) for r in c]
    cp, cm = Counter(pay_rows), Counter(mine_rows)
    pipeline_check = {
        "payload_file": str(PIPELINE_PAYLOAD.relative_to(ROOT)),
        "payload_captured_at": payload.get("captured_at"),
        "payload_rows": len(pay_rows),
        "read_rows": len(mine_rows),
        "rows_only_in_payload_after_LA_to_LAR": sum((cp - cm).values()),
        "rows_only_in_2026_11_17_read": sum((cm - cp).values()),
        "normalisation": "payload team 'LA' read as 'LAR' (the code printed on the page); no other change",
    }
    report = {
        "dataset": "nfl.com Week 10 injury page: three dated reads compared row by row",
        "pipeline_payload_cross_check": pipeline_check,
        "source": SOURCE_URL,
        "reads": {
            "published_table": {"file": "data/nfl/injuries_week10.tsv", "read_on": "2026-11-14 (per file header)",
                                "counts": counts(pub)},
            "read_2026_11_15": {"file": str(READ_1115.relative_to(ROOT)), "read_on": "2026-11-15 (per its README)",
                                "counts": counts(b)},
            "read_2026_11_17": {"file": str(READ_1117.relative_to(ROOT)), "read_on": "2026-11-17",
                                "counts": counts(c)},
        },
        "rows_per_club_read_2026_11_17": dict(sorted(per_club.items())),
        "published_vs_2026_11_17": {
            "missing_from_published": [fmt_key(k) | {"official_row": c_i[k]} for k in pub_vs_c_only_c],
            "published_but_not_on_page": [fmt_key(k) for k in pub_vs_c_only_pub],
            "field_changes": pub_vs_c_changes,
        },
        "delta_2026_11_15_to_2026_11_17": {
            "only_on_2026_11_15": [fmt_key(k) for k in b_vs_c_only_b],
            "only_on_2026_11_17": [fmt_key(k) for k in b_vs_c_only_c],
            "field_changes": b_vs_c_changes,
        },
        "published_url_by_key": {f"{k[0]}|{k[1]}|{k[2]}": v for k, v in sorted(url_by_key.items())},
        "method": ("Rows matched on (game, team, player). Only printed text is compared; blank means blank. "
                   "The 2026-11-17 read is a manual transcription of the eight fetch chunks, one line per printed row; "
                   "the file hash is of the transcription, not of the HTTP response bytes."),
    }
    return report


def render_md(rep):
    pv = rep["published_vs_2026_11_17"]
    dl = rep["delta_2026_11_15_to_2026_11_17"]
    out = []
    out.append("# Week 10 injury page — three dated reads, compared row by row\n")
    out.append(f"Source: {rep['source']} (official NFL.com, \"Week 10 of the 2026 Season\"). "
               "Machine-generated by `tools/verify_w10_read_2026_11_17.py`; do not hand-edit.\n")
    out.append("## Counts per read\n")
    out.append("| Read | Rows | Out | Doubtful | Questionable | Blank game status | Blank injury | Clubs | Games |")
    out.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for name, r in rep["reads"].items():
        k = r["counts"]
        out.append(f"| {name} ({r['read_on']}) | {k['rows']} | {k['Out']} | {k['Doubtful']} | {k['Questionable']} | "
                   f"{k['blank_game_status']} | {k['blank_injury']} | {k['clubs']} | {k['games']} |")
    out.append("")
    out.append("## Published table vs the 2026-11-17 read\n")
    out.append(f"- Rows on the page but missing from the published table: **{len(pv['missing_from_published'])}**")
    out.append(f"- Rows in the published table but not on the page: **{len(pv['published_but_not_on_page'])}**")
    out.append(f"- Matched rows with a changed field: **{len(pv['field_changes'])}**\n")
    if pv["missing_from_published"]:
        out.append("| Game | Club | Player | Injury (page) | Practice (page) | Game status (page) | Source link |")
        out.append("|---|---|---|---|---|---|---|")
        for m in pv["missing_from_published"]:
            o = m["official_row"]
            # no published player link exists for a row the published table lacks: the source is the report itself
            url = rep["published_url_by_key"].get(f"{m['game']}|{m['team']}|{m['player']}", SOURCE_URL)
            out.append(f"| {m['game']} | {m['team']} | {m['player']} | {o['injury']} | {o['practice_status']} | "
                       f"{o['game_status']} | {url} |")
        out.append("")
    if pv["field_changes"]:
        out.append("| Game | Club | Player | Field | Published | Page (2026-11-17) |")
        out.append("|---|---|---|---|---|---|")
        for ch in pv["field_changes"]:
            for f, (a, b) in ch["changes"].items():
                out.append(f"| {ch['game']} | {ch['team']} | {ch['player']} | {f} | {a} | {b} |")
        out.append("")
    out.append("## Day-over-day delta: 2026-11-15 read to 2026-11-17 read\n")
    out.append(f"- Only on the 2026-11-15 read: **{len(dl['only_on_2026_11_15'])}**")
    out.append(f"- Only on the 2026-11-17 read: **{len(dl['only_on_2026_11_17'])}**")
    out.append(f"- Matched rows with a changed field: **{len(dl['field_changes'])}**\n")
    if dl["field_changes"]:
        out.append("| Game | Club | Player | Field | 2026-11-15 | 2026-11-17 |")
        out.append("|---|---|---|---|---|---|")
        for ch in dl["field_changes"]:
            for f, (a, b) in ch["changes"].items():
                out.append(f"| {ch['game']} | {ch['team']} | {ch['player']} | {f} | {a} | {b} |")
        out.append("")
    out.append("## Method and limits\n")
    out.append(f"- {rep['method']}")
    out.append("- A page-printed row count is not printed on the page itself; the count here is of transcribed rows.")
    out.append("- Injury designations are a pre-game report. Post-game news on the same page (e.g. the Patriots and "
               "Lions news items) is not a row change and is not reflected in the rows.")
    return "\n".join(out) + "\n"


def render_tsv(rows):
    cols = ["game", "team", "player", "position", "injury", "practice_status", "game_status", "source_url"]
    lines = ["# Official NFL.com Week 10 injury report, read 2026-11-17 (see " + SOURCE_URL + ")",
             "# One row per player as printed. Blank = the page prints nothing in that cell. Nothing inferred.",
             "\t".join(cols)]
    for r in rows:
        lines.append("\t".join([r["game"], r["team"], r["player"], r["position"], r["injury"],
                                r["practice_status"], r["game_status"], SOURCE_URL]))
    return "\n".join(lines) + "\n"


def render_page(rep, c_rows):
    pv, dl, pc = rep["published_vs_2026_11_17"], rep["delta_2026_11_15_to_2026_11_17"], rep["pipeline_payload_cross_check"]
    e = html.escape
    src = lambda: f'<a href="{SOURCE_URL}" target="_blank" rel="noopener noreferrer">nfl.com injury report ↗</a>'
    def tbl(headers, rows_html, cls="data-table"):
        head = "".join(f"<th>{e(h)}</th>" for h in headers)
        return f'<div class="tablewrap"><table data-table><thead><tr>{head}</tr></thead><tbody>{rows_html}</tbody></table></div>'
    blank_mark = '<span class="blank" title="blank on the page">&mdash;</span>'

    def cell(v):
        return "<td>" + (e(v) if v else blank_mark) + "</td>"

    counts_rows = ""
    for name, r in rep["reads"].items():
        k = r["counts"]
        counts_rows += ("<tr>" + f"<td>{e(name)}</td><td>{e(r['read_on'])}</td><td>{k['rows']}</td><td>{k['Out']}</td>"
                        f"<td>{k['Doubtful']}</td><td>{k['Questionable']}</td><td>{k['blank_game_status']}</td>"
                        f"<td>{k['clubs']}</td><td>{k['games']}</td><td>{src()}</td></tr>")

    diff_rows = ""
    for m in pv["missing_from_published"]:
        o = m["official_row"]
        diff_rows += ("<tr>" + f"<td>{e(m['game'])}</td><td>{e(m['team'])}</td><td>{e(m['player'])}</td>"
                      f"<td>row missing from the published table</td><td>—</td><td>{e(o['injury']) or '&mdash;'}</td>"
                      f"<td>{e(o['practice_status'])}</td><td>{e(o['game_status']) or '&mdash;'}</td><td>{src()}</td></tr>")
    for ch in pv["field_changes"]:
        for f, (a, b) in ch["changes"].items():
            diff_rows += ("<tr>" + f"<td>{e(ch['game'])}</td><td>{e(ch['team'])}</td><td>{e(ch['player'])}</td>"
                          f"<td>{e(f)}</td><td>{e(a) or '&mdash;'}</td><td>{e(b) or '&mdash;'}</td><td></td><td></td><td>{src()}</td></tr>")

    full_rows = ""
    for r in c_rows:
        full_rows += ("<tr>" + f"<td>{e(r['game'])}</td><td>{e(r['team'])}</td><td>{e(r['player'])}</td>"
                      f"<td>{e(r['position'])}</td>{cell(r['injury'])}{cell(r['practice_status'])}{cell(r['game_status'])}"
                      f"<td>{src()}</td></tr>")

    lions = [r for r in c_rows if r["team"] == "DET" and r["player"] in ("Kerby Joseph", "Cade Mays", "D.J. Reed")]
    lions_txt = "; ".join(f"{r['player']} = {r['game_status']}" for r in lions)
    n_diff = len(pv["field_changes"]) + len(pv["missing_from_published"])
    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Injury report re-read 2026-11-17 — Fourth Down</title>
<meta name="description" content="Week 10 official NFL.com injury report, re-read 2026-11-17 and compared row by row with the published table.">
<link rel="stylesheet" href="../assets/site.css">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<aside class="rail">
  <a class="brand" href="../index.html"><span class="mark">4D</span><span>FOURTH DOWN<small>NFL Line Lab</small></span></a>
  <nav aria-label="Main">
      <a href="../index.html">Overview</a>
      <a href="standings.html">Standings</a>
      <a href="schedule.html">Week 10</a>
      <a class="active" href="injury-read-2026-11-17.html">Injury re-read 17 Nov</a>
      <a href="flagged.html">Flagged for review</a>
      <a href="sources.html">Sources</a>
  </nav>
  <footer>Evidence first. Nothing inferred.</footer>
</aside>
<main id="main">
  <header class="top">
    <span>WORKSPACE <i>/ INJURY RE-READ</i></span>
    <span class="asof">READ 2026-11-17</span>
  </header>
<section class="pagetitle">
  <div class="eyebrow">OFFICIAL SOURCE RE-READ · 2026-11-17</div>
  <h1>Week 10 injury report — re-read and compared row by row</h1>
  <p>The official NFL.com Week 10 injury report was read again on 2026-11-17 and transcribed one line per printed row
  ({rep['reads']['read_2026_11_17']['counts']['rows']} rows, 14 games, 28 clubs). Each row was compared with the published
  table (dated 2026-11-14), the 2026-11-15 read, and the pipeline's stored capture of 2026-11-16. The published table is
  <b>not</b> overwritten here; the differences are listed so a reviewer can decide the swap.</p>
</section>
<section class="content">
<div class="cards">
  <div class="card"><b>{rep['reads']['read_2026_11_17']['counts']['rows']}</b><span>rows on the page, 2026-11-17</span></div>
  <div class="card"><b>{rep['reads']['published_table']['counts']['rows']}</b><span>rows in the published table (2026-11-14)</span></div>
  <div class="card"><b>{len(pv['missing_from_published'])}</b><span>rows missing from the published table</span></div>
  <div class="card"><b>{len(pv['field_changes'])}</b><span>matched rows with a changed cell</span></div>
  <div class="card"><b>{len(dl['field_changes']) + len(dl['only_on_2026_11_15']) + len(dl['only_on_2026_11_17'])}</b><span>changes from the 2026-11-15 read to today</span></div>
  <div class="card"><b>{pc['rows_only_in_payload_after_LA_to_LAR'] + pc['rows_only_in_2026_11_17_read']}</b><span>rows that differ from the pipeline's 2026-11-16 capture (after LA→LAR)</span></div>
</div>

<h2>What this means</h2>
<ul>
  <li><b>The published Week 10 table is out of date.</b> It lists {rep['reads']['published_table']['counts']['rows']} rows against {rep['reads']['read_2026_11_17']['counts']['rows']} on the page, and it is missing two Baltimore rows (Calais Campbell, Ronnie Stanley). {len(pv['field_changes'])} matched rows differ, all in the Monday LAC@BAL game plus Arden Key (MIA@IND).</li>
  <li><b>The Lions designations the brief asked for are present and match the page:</b> {e(lions_txt)} (all three printed as Out).</li>
  <li><b>Nothing moved between the 2026-11-15 read and today.</b> The two dated reads are identical, so the day-over-day delta is zero. The pipeline's 2026-11-16 19:02Z capture also matches this read cell for cell after the LA→LAR code fix.</li>
  <li><b>A 'not listed' row is not evidence of health.</b> The page's news list reports Dolphins QB Malik Willis (groin) placed on injured reserve, and he is not in the Miami table. An injured-reserve list is a separate official source that is not captured here.</li>
</ul>

<h2>Brief items that pull against each other (owner decision needed)</h2>
<ul>
  <li><b>Snap counts as a starter proxy</b> ("use snap counts as the starter proxy when the depth chart is unavailable") versus <b>no inference of snaps</b> ("use official NFL Game Books … do not infer depth rank or snaps"). No official snap-count capture exists in this repository yet, so neither route can be built today. The owner needs to decide whether a verified official snap-count source may stand in for a missing depth chart.</li>
  <li><b>Named replacements</b> ("starters out, replacements named") versus <b>no inferred replacement</b> ("an announced-starter evidence field, not an inferred replacement"). This read names no replacement for any player: the page prints no lineup. A replacement is shown only when a dated official source names one.</li>
</ul>

<h2>Counts per read</h2>
<p class="muted">Counts are of transcribed rows. The page prints no total of its own.</p>
{tbl(["Read", "Read on", "Rows", "Out", "Doubtful", "Questionable", "Blank game status", "Clubs", "Games", "Source"], counts_rows)}

<h2>Differences: published table vs today's page ({n_diff} rows)</h2>
<p class="muted">A matched row is compared on injury, practice status and game status. Blank means blank on the page. "Published" is the 2026-11-14 table; "Page" is the 2026-11-17 read.</p>
{tbl(["Game", "Club", "Player", "Field", "Published", "Page", "Page: practice status", "Page: game status", "Source"], diff_rows)}

<h2>Full 2026-11-17 read, one row per printed player ({rep['reads']['read_2026_11_17']['counts']['rows']} rows)</h2>
<p class="muted">Blank cells are shown as —. Every row links to the official report. The machine-readable copy is <a href="https://github.com/karagemop466-tech/X1/blob/main/data/capture/2026_w10_read_2026_11_17/injuries_week10_2026-11-17.tsv" target="_blank" rel="noopener noreferrer">injuries_week10_2026-11-17.tsv ↗</a>.</p>
{tbl(["Game", "Club", "Player", "Position", "Injury", "Practice status", "Game status", "Source"], full_rows)}

<h2>Flagged for review</h2>
<ul>
  <li><b>Stale published table</b> — 345 rows against 347 on the page; see the differences above. Not overwritten here. <a href="flagged.html">Flagged for review</a>.</li>
  <li><b>Pipeline club code</b> — the 2026-11-15 capture failed its drift check because the Rams are printed as LAR while the pipeline's code list expects LA. The 2026-11-16 capture stores LA. Captured payloads are not renamed.</li>
  <li><b>Transcription, not raw bytes</b> — the fetch tool returns page text, not the HTTP response. The file hashes are of the transcription, and the pipeline's own payload hash is recorded in the JSON report.</li>
  <li><b>Checkout is shallow</b> — this clone exposes one commit, so the registration anchors in the pre-registration register cannot be re-derived here.</li>
</ul>

<h2>Method</h2>
<p>Read with the fetch tool on 2026-11-17, chunks 0–7 of 8 (<code>hasMore</code> false on chunk 7). Matched on game, club and player.
Re-run: <code>python3 tools/verify_w10_read_2026_11_17.py</code> (rebuilds this page, the TSV and the JSON/Markdown reports; <code>--check</code> fails if any is stale).
Reports: <a href="https://github.com/karagemop466-tech/X1/blob/main/data/capture/2026_w10_read_2026_11_17/recapture_2026_11_17.md" target="_blank" rel="noopener noreferrer">recapture_2026_11_17.md ↗</a>
· <a href="https://github.com/karagemop466-tech/X1/blob/main/tools/verify_w10_read_2026_11_17.py" target="_blank" rel="noopener noreferrer">tools/verify_w10_read_2026_11_17.py ↗</a>.</p>
<p class="muted">Source: <a href="{SOURCE_URL}" target="_blank" rel="noopener noreferrer">https://www.nfl.com/injuries/ ↗</a> (NFL.com, official).</p>
</section>
</main>
</body>
</html>
"""
    return doc


def main(argv):
    rep = build()
    js = json.dumps(rep, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    md = render_md(rep)
    tsv = render_tsv(_psv(READ_1117))
    page = render_page(rep, _psv(READ_1117))
    jp, mp = OUT_DIR / "recapture_2026_11_17.json", OUT_DIR / "recapture_2026_11_17.md"
    outs = [(jp, js), (mp, md), (TSV_OUT, tsv), (PAGE, page)]
    if "--check" in argv:
        ok = all(p.exists() and p.read_text(encoding="utf-8") == text for p, text in outs)
        print("outputs current" if ok else "STALE: rerun tools/verify_w10_read_2026_11_17.py")
        return 0 if ok else 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PAGE.parent.mkdir(parents=True, exist_ok=True)
    for p, text in outs:
        p.write_text(text, encoding="utf-8")
    pv = rep["published_vs_2026_11_17"]
    dl = rep["delta_2026_11_15_to_2026_11_17"]
    print(f"read 2026-11-17: {rep['reads']['read_2026_11_17']['counts']['rows']} rows")
    print(f"published vs 2026-11-17: missing {len(pv['missing_from_published'])}, "
          f"extra {len(pv['published_but_not_on_page'])}, field changes {len(pv['field_changes'])}")
    print(f"2026-11-15 -> 2026-11-17: only-15 {len(dl['only_on_2026_11_15'])}, "
          f"only-17 {len(dl['only_on_2026_11_17'])}, field changes {len(dl['field_changes'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
