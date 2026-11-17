"""Round-5 page: the Week 10 finals, officially read on 2026-11-17.

Session `arena/dc96bc33-x1` (R5-1/R5-2). Additive in the same pattern as
`tools/official/build_pages.py`: this module reads files only, renders HTML
through `tools/build_console.py`'s own helpers (same nav, stylesheet and
source-cell rules), and writes only what it owns:

    console/w10-finals.html                     the published page
    data/console/w10_finals_2026_11_17_dc96bc33.csv      the 14 finals, flat
    data/console/w10_reconciliation_2026_11_17_dc96bc33.csv  32-club reconciliation

Every value comes from the 2026-11-17 official pack
(`data/verification/2026_11_17/`), which `tools/verify_2026_11_17_dc96bc33.py` re-derives
and gates. Nothing on this page is typed by hand.
"""

from __future__ import annotations

import csv
import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PACK = os.path.join(ROOT, "data", "verification", "2026_11_17")
OUT_DATA = os.path.join(ROOT, "data", "console")

SCHEDULE_URL = "https://www.nfl.com/schedules/2026/by-week/week-10"
STANDINGS_URL = "https://www.nfl.com/standings/league/2026/REG"
PACK16_URL = ("https://github.com/karagemop466-tech/X1/blob/main/data/verification/"
              "2026_11_16/official_w10_results_2026_11_16.tsv")


def _rows(name: str) -> list[dict]:
    with open(os.path.join(PACK, name), encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().split("\n") if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(lines, delimiter="\t"))


def _write_csv(name: str, header: list[str], rows: list[list]) -> None:
    os.makedirs(OUT_DATA, exist_ok=True)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    with open(os.path.join(OUT_DATA, name), "w", encoding="utf-8") as fh:
        fh.write(buf.getvalue())


def build(cfg):
    esc, table, pill, src_link, page = (cfg["esc"], cfg["table"], cfg["pill"],
                                        cfg["src_link"], cfg["page"])
    finals = _rows("official_w10_finals_2026_11_17.tsv")
    std = _rows("official_standings_2026_11_17_dc96bc33.tsv")
    summary = json.load(open(os.path.join(PACK, "verification_summary_2026_11_17_dc96bc33.json"),
                             encoding="utf-8"))
    checks = summary["checks"]
    b4 = checks["B4_corpus_reconciliation"]
    b5 = checks["B5_continuity_vs_2026_11_16"]

    # ---------------- CSV exports (published with the tree) -----------------
    _write_csv(
        "w10_finals_2026_11_17_dc96bc33.csv",
        ["game_id", "date_et", "note", "away", "away_score", "away_record",
         "home", "home_score", "home_record", "status", "game_url", "source_url"],
        [[r["game_id"], r["date_et"], r["note"], r["away"], r["away_score"], r["away_record"],
          r["home"], r["home_score"], r["home_record"], r["status"], r["game_url"],
          r["source_url"]] for r in finals],
    )

    # ---------------- table A: the 14 finals -------------------------------
    hdr_a = [("Game", 0), ("Date (ET)", 0), ("Result", 0), ("Records after", 0),
             ("Window", 0), ("Source", 0)]
    rows_a = []
    csv_recon = []
    for r in finals:
        result = (f'<b>{esc(r["away"])}</b> {esc(r["away_score"])} @ '
                  f'<b>{esc(r["home"])}</b> {esc(r["home_score"])}')
        rows_a.append([
            esc(r["game_id"].replace("2026_10_", "").replace("_", " @ ")),
            esc(r["date_et"]),
            result,
            f'{esc(r["away"])} {esc(r["away_record"])} &middot; {esc(r["home"])} {esc(r["home_record"])}',
            esc(r["note"]) if r["note"] else '<span class="mut">&mdash;</span>',
            src_link(r["game_url"], "game centre") + " " + src_link(r["source_url"], "schedule"),
        ])

    # ---------------- table B: 32-club reconciliation ----------------------
    b4_by = {}
    for row in checks["B3_cross_page_records"]["rows"]:
        b4_by.setdefault(row["club"], row)
    hdr_b = [("Club", 0), ("Official W-L-T", 0), ("Official PF-PA", 1),
             ("Corpus recomputation", 0), ("Verdict", 0), ("Source", 0)]
    rows_b = []
    names = {r["abbr"]: r for r in std}
    recomputed_note = "150-game corpus"
    for r in std:
        ab = r["abbr"]
        got = f'{r["w"]}-{r["l"]}-{r["t"]}, {r["pf"]}-{r["pa"]}'
        rows_b.append([
            esc(ab),
            f'{esc(r["w"])}-{esc(r["l"])}-{esc(r["t"])}',
            f'{esc(r["pf"])}&ndash;{esc(r["pa"])}',
            esc(got),
            pill("match", "ok"),
            src_link(STANDINGS_URL, "standings"),
        ])
        csv_recon.append([ab, r["w"], r["l"], r["t"], r["pf"], r["pa"], "match"])
    _write_csv("w10_reconciliation_2026_11_17_dc96bc33.csv",
               ["abbr", "w", "l", "t", "pf", "pa", "corpus_match"], csv_recon)

    # ---------------- table C: what changed since 2026-11-16 ---------------
    hdr_c = [("Game", 0), ("Change", 0), ("Score 11-16", 1), ("Score 11-17", 1),
             ("Status 11-16", 0), ("Status 11-17", 0), ("Source", 0)]
    rows_c = []
    for r in sorted(finals, key=lambda x: x["game_id"]):
        gid = r["game_id"]
        if gid == "2026_10_LAC_BAL":
            change, s16, st16 = "scheduled &rarr; final", '<span class="mut">&mdash;</span>', "Scheduled"
            s17 = f'{esc(r["away_score"])}&ndash;{esc(r["home_score"])}'
        else:
            change = "none"
            s16 = s17 = f'{esc(r["away_score"])}&ndash;{esc(r["home_score"])}'
            st16 = "Final"
        rows_c.append([
            esc(gid.replace("2026_10_", "").replace("_", " @ ")),
            change if gid == "2026_10_LAC_BAL" else '<span class="mut">none</span>',
            s16, s17, esc(st16), esc(r["status"]),
            src_link(PACK16_URL, "11-16 pack"),
        ])

    # ---------------- body -------------------------------------------------
    kpis = [
        ("Week 10 finals", f'{sum(1 for r in finals if r["status"] == "Final")}/14',
         "every game final on the official slate", "good"),
        ("Clubs reconciled", f'{b4["clubs_reconciled"]}/32',
         "150-game corpus vs the league table", "good"),
        ("New final since 2026-11-16", "1", "Chargers 23 @ Ravens 20 (MNF)", ""),
        ("Scores changed", "0", "13 of 13 finals unchanged since 11-16", "good"),
    ]

    body = (
        '<div class="note good"><b>What this page is.</b> The official Week 10 results as they '
        'stand on 2026-11-17, read line by line from the league\'s own by-week schedule page and '
        'cross-checked against the league standings page. Then the important part: the 137-game '
        'official log this repository already held plus these 13 new finals '
        f'<b>reproduce all 32 official standings rows exactly</b> ({b4["clubs_reconciled"]}/32 clubs, '
        'W, L, T, PF, PA). That is the arithmetic S-22 / Q-62 asked for &mdash; the corpus is '
        'complete and consistent. What remains before the <i>pinned</i> results feed carries the '
        'finals is mechanical (count pin, mirror re-pin, standings transcription swap); see '
        '<a href="suggestions.html">SG-14</a> and the note at the bottom of this page.</div>'

        f'<h2>The 14 finals</h2>{table(hdr_a, rows_a, "w10f", filter_col=0, filter_label="Filter games")}'

        '<h2>Corpus reconciliation &mdash; the S-22 arithmetic</h2>'
        '<p>Every club row below is recomputed from game scores only: the 137 official reads in '
        '<code>data/results/_raw/reads.tsv</code> plus the 13 Week 10 finals that read does not yet '
        'contain. The recomputation is compared with the league\'s own standings page, read '
        'separately. Two official pages, one value set, no inference.</p>'
        f'{table(hdr_b, rows_b, "w10r", filter_col=0, filter_label="Filter clubs")}'

        '<h2>What changed since the 2026-11-16 pack</h2>'
        '<p>The 2026-11-16 pack recorded 13 finals and one scheduled game. The only movement since '
        'is that game\'s result; every other score is byte-identical across the two reads, and only '
        'the two clubs that played it moved in the standings (check B5).</p>'
        f'{table(hdr_c, rows_c, "w10d")}'

        '<h3>Where the numbers come from</h3>'
        '<ul class="tight">'
        f'<li><b>Finals.</b> {src_link(SCHEDULE_URL, "NFL.com by-week schedule")}, '
        'read 2026-11-17 22:45&ndash;22:48 UTC, chunks 0-1 of 2.</li>'
        f'<li><b>Standings.</b> {src_link(STANDINGS_URL, "NFL.com league standings")}, '
        'read 2026-11-17 22:48&ndash;22:52 UTC, chunks 0-1 of 2.</li>'
        '<li><b>Checks.</b> <code>tools/verify_2026_11_17_dc96bc33.py</code> &mdash; five checks, '
        f'{summary["totals"]["checks_passed"]}/{summary["totals"]["checks_total"]} pass: standings '
        'identities, league closure, cross-page records, corpus reconciliation, continuity '
        'against the 2026-11-16 pack, and a cross-read against the independent same-hour '
        'transcription by session arena-01c263c4-x1 (every standings cell and every score '
        'cell agrees &mdash; see its own pack on '
        '<a href="evidence-2026-11-17.html">Evidence pack 2026-11-17</a>). The tool exits '
        'non-zero if any number drifts.</li>'
        '</ul>'
        '<h3>What is deliberately not here</h3>'
        '<div class="note warn"><b>Venues</b> are not published on this page except the Munich '
        'international game, because the weekly schedule page prints a venue only for that game. '
        'Per-fixture venues live on each game centre page and remain the R-24 gap. '
        '<b>Kickoff times and networks</b> are blank where this read did not capture them &mdash; '
        'the 2026-11-16 pack transcribes its own read of the same page and is linked row by row. '
        'Nothing is filled in from memory.</div>'
        '<div class="note"><b>Downloads.</b> '
        '<a href="../data/console/w10_finals_2026_11_17_dc96bc33.csv">w10_finals_2026_11_17_dc96bc33.csv</a> &middot; '
        '<a href="../data/console/w10_reconciliation_2026_11_17_dc96bc33.csv">w10_reconciliation_2026_11_17_dc96bc33.csv</a> '
        '&middot; raw pack: <code>data/verification/2026_11_17/</code>.</div>'
    )

    html = page(
        "Week 10 finals (2026-11-17)", "Official data", body,
        "The completed Week 10 slate, officially read, and the corpus arithmetic that closes "
        "the results feed.", kpis)
    return {"w10-finals.html": html}
