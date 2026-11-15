"""Four pages for the Week 10 official re-capture and the readiness table.

Session `arena-b03ced7c-x1`. Additive: this module reads files only, renders
HTML through `tools/build_console.py`'s own helpers (so the pages carry the
same navigation, stylesheet and source-cell rules as every other page in the
tree), and writes only the four files it owns:

    console/capture.html      the dated 2026-11-15 read, beside the 11-14 table
    console/depth-parse.html  the two parse failures, measured
    console/readiness.html    one row per requirement, its gate and its number
    console/official-flags.html  every irregularity found this session

Called from `tools/build_console.py::main()` after the built-in pages, through
`build(cfg)` where `cfg` exposes that module's helpers.
"""

from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "data", "console")

INJ = "https://www.nfl.com/injuries/league/2026/reg10"
STD = "https://www.nfl.com/standings/league/2026/REG"
PAC = "https://www.packers.com/team/depth-chart"
HOU = "https://www.houstontexans.com/team/depth-chart"
RAV = "https://www.baltimoreravens.com/team/depth-chart"
SEA = "https://www.seahawks.com/team/depth-chart/"
WAS = "https://www.commanders.com/team/depth-chart"
SCHED = "https://www.nfl.com/schedules/2026/by-week/week-10"


def _j(name):
    with open(os.path.join(OUT, name), encoding="utf-8") as fh:
        return json.load(fh)


def page_capture(cfg):
    esc, table, pill, src_link, page = (cfg["esc"], cfg["table"], cfg["pill"],
                                        cfg["src_link"], cfg["page"])
    rec = _j("week10_reconcile.json")
    live = rec["captures"]["live_2026_11_15"]
    e1 = rec["captures"]["e1_2026_11_15"]
    pub = rec["captures"]["published_2026_11_14"]
    lc = rec["status_counts"]["live"]
    pc = rec["status_counts"]["published_2026_11_14"]

    kpis = [
        ("Rows printed today", f"{live['rows']}", f"{live['clubs']} clubs, {live['games']} games", ""),
        ("Read conflicts", f"{len(rec['conflicts'])}", "two reads, same day, same page", "good"),
        ("Rows missing from the 11-14 table", f"{len(rec['presence']['published_2026_11_14']['missing'])}",
         "print on the page, absent from the publication", "bad"),
        ("Cells that differ", f"{len(rec['cells'])}", "11-14 table vs the page today", "warn"),
        ("Raw bytes retained", "0", "transcription, not a byte capture", "bad"),
    ]

    # ---- the three reads -------------------------------------------------
    rows = []
    for key, meta in ((k, rec["captures"][k]) for k in
                      ("live_2026_11_15", "e1_2026_11_15", "published_2026_11_14")):
        rows.append([esc(meta["label"]), esc(meta["captured"]), f"{meta['rows']:,}",
                     f"{meta['clubs']}", f"{meta['games']}",
                     f'<code>{meta["sha256"][:16]}&hellip;</code>',
                     src_link(INJ, "nfl.com")])
    reads = table([("Read", 0), ("Captured (UTC)", 0), ("Rows", 1), ("Clubs", 1), ("Games", 1),
                   ("SHA-256 of the committed file", 0), ("Source", 0)], rows, "reads")

    # ---- status deltas ---------------------------------------------------
    order = ["Out", "Doubtful", "Questionable", "(none)"]
    drow = []
    for k in order:
        a, b = pc.get(k, 0), lc.get(k, 0)
        drow.append([esc(k), f"{a:,}", f"{b:,}",
                     pill(f"{b - a:+d}", "ok" if b == a else "mid"), src_link(INJ, "nfl.com")])
    deltas = table([("Game designation", 0), ("11-14 table", 1), ("Page today", 1),
                    ("Delta", 1), ("Source", 0)], drow, "deltas")

    # ---- missing rows ----------------------------------------------------
    miss = rec["presence"]["published_2026_11_14"]["missing"]
    mrows = [[esc(m["team"]), esc(m["player"]), esc(m["pos"]), esc(m["injury"]) or '<span class="mut">&mdash;</span>',
              esc(m["practice"]), esc(m["status"]) or '<span class="mut">&mdash;</span>',
              src_link(INJ, "nfl.com")] for m in miss]
    missing = (table([("Club", 0), ("Player", 0), ("Pos", 0), ("Injury", 0), ("Practice", 0),
                      ("Game status", 0), ("Source", 0)], mrows, "miss")
               if mrows else '<div class="note good">No row printed today is missing from the published table.</div>')

    # ---- cell diffs ------------------------------------------------------
    fname = {"injury": "Injury", "practice": "Practice status", "status": "Game status"}
    crows = []
    for c in rec["cells"]:
        if c["capture"] != "published_2026_11_14":
            continue
        crows.append([esc(c["team"]), esc(c["player"]), esc(c["game"]), esc(fname[c["field"]]),
                      esc(c["live_value"]) or '<span class="mut">blank</span>',
                      esc(c["other_value"]) or '<span class="mut">blank</span>',
                      src_link(INJ, "nfl.com")])
    cells = table([("Club", 0), ("Player", 0), ("Game", 0), ("Field", 0), ("Page today", 0),
                   ("11-14 table", 0), ("Source", 0)], crows, "cells",
                  filter_col=0, filter_label="Filter by club or player")

    body = (
        '<div class="note">The official injury report is a <b>daily series</b>, not a weekly '
        'snapshot. This page publishes the 2026-11-15T18:14Z read beside the 2026-11-14 table '
        'instead of replacing it: a designation that changed between the two is evidence, and '
        'overwriting the older read would destroy it.</div>'
        '<div class="note bad"><b>The honest limit.</b> nfl.com cannot be reached over TLS from '
        'this sandbox\'s bash (<code>curl</code> exit 35), so this capture is a <b>transcription</b> '
        'made through a text-extraction tool, not a byte capture. No raw bytes and no server '
        'ETag exist for it. The hashed byte ledger claimed by session '
        '<code>arena/c0461519-x1</code> (PR #50) is the fix; until it lands, every injury cell '
        'here is <i>transcribed</i>, not <i>byte-verified</i>.</div>'
        f'<h2>The three reads</h2>{reads}'
        f'<h2>Designation counts: the 11-14 table against the page today</h2>{deltas}'
        '<div class="note mid">The direction of the change is consistent with a report that '
        'firmed up between Friday and Sunday: <b>Out</b> and <b>Questionable</b> rose while the '
        'blank count fell. That is the expected shape. It is reported as a dated delta and never '
        'as a correction, because the repository cannot prove which cells changed and which were '
        'mis-transcribed on 11-14.</div>'
        f'<h2>Rows printed today but absent from the 11-14 table</h2>{missing}'
        f'<h2>Every cell that differs ({len(crows)})</h2>{cells}'
        '<div class="note good"><b>What did hold up.</b> Two independent reads of the same page '
        'on the same day — this session\'s and session <code>ed8c600d</code>\'s — agree on '
        f'<b>all {live["rows"]} rows</b>, all {live["clubs"]} clubs and every practice and game '
        'designation. Where two readers agree by construction, the residual risk is a shared '
        'misread of the page, which no transcription can rule out.</div>'
        '<h2>The brief items this closes</h2>'
        '<ul class="tight">'
        '<li><b>"Re-capture and republish the Week 10 injury tables"</b> — done here as a new '
        'dated read (347 rows) published beside the 345-row 11-14 table.</li>'
        '<li><b>"Populate the three missing Lions game-status designations"</b> — Kerby Joseph, '
        'Cade Mays and D.J. Reed all print <b>Out</b> on the page today and all three carry '
        '<b>Out</b> in the published table. That item was already closed; the real gap is the two '
        'Baltimore rows above.</li>'
        '<li><b>"The brief says 254 rows / 4 no-injury sections versus 279 live"</b> — that count '
        'does not describe anything in this repository today: the published table holds 345 rows '
        'and the page prints 347. The 254/279 pair is recorded on the '
        '<a href="official-flags.html">flags page</a> as a claim that could not be reproduced.</li>'
        '</ul>')
    return page("Week 10 official re-capture", "Official data", body,
                "The live nfl.com Week 10 injury report, read 2026-11-15T18:14Z, published beside "
                "the 2026-11-14 table rather than over it.", kpis)


def page_depth_parse(cfg):
    esc, table, pill, src_link, page = (cfg["esc"], cfg["table"], cfg["pill"],
                                        cfg["src_link"], cfg["page"])
    dp = _j("depth_parse.json")
    s = dp["packers_summary"]
    t = dp["texans"]

    kpis = [
        ("Green Bay rows with a jersey number", f"{s['published_contaminated']} of {s['published_rows']}",
         "every published row", "bad"),
        ("Injury join, raw string", f"{s['join_hits_with_raw_string']} of {s['injury_rows_gb']}",
         "GB injury rows matched", "bad"),
        ("Injury join, number stripped", f"{s['join_hits_after_number_strip']} of {s['injury_rows_gb']}",
         f"+{s['join_gain']} recovered", "good"),
        ("Live chart vs the store", f"{s['diffs']} cells", "differ", "bad"),
        ("Houston slots", f"{t['slots_in_store']}", "the chart is an image", "bad"),
    ]

    # the demonstration rows come from the measurement file, not from memory
    rows = []
    for r in dp.get("live_rows") or []:
        if not r["raw"]:
            continue
        rows.append([esc(r["unit"]), esc(r["position"]), str(r["slot"]), str(r["depth"]),
                     f'<code>{esc(r["raw"])}</code>', esc(r["name"]),
                     esc(r["jersey"]) or '<span class="mut">&mdash;</span>',
                     pill("stripped", "mid") if r["stripped"] else pill("clean", "ok"),
                     src_link(PAC, "packers.com")])
    strip = table([("Unit", 0), ("Pos", 0), ("Slot", 1), ("Depth", 1), ("Printed cell", 0),
                   ("Name after stripping", 0), ("Jersey", 1), ("Action", 0), ("Source", 0)],
                  rows, "strip", filter_col=4)

    kind_label = {"value": "printed cell differs", "missing_named_in_published":
                  "named player missing from the store", "not_on_live_chart":
                  "in the store, not on the live chart", "missing_empty_cell":
                  "empty cell with no row in the store"}
    drows = [[esc(d["unit"]), esc(d["position"]), esc(d["slot"]), esc(d["depth"]),
              esc(kind_label.get(d["kind"], d["kind"])),
              f'<code>{esc(d["live"])}</code>' if d["live"] else '<span class="mut">empty</span>',
              f'<code>{esc(d["published"])}</code>' if d["published"] else '<span class="mut">(no row)</span>',
              src_link(PAC, "packers.com")] for d in dp["diffs"]]
    diffs = table([("Unit", 0), ("Pos", 0), ("Slot", 1), ("Depth", 1), ("What kind of difference", 0),
                   ("Live chart", 0), ("Published store", 0), ("Source", 0)], drows, "dpdiff",
                  filter_col=4)

    body = (
        '<div class="note"><b>The brief, verbatim.</b> "The Texans publish depth as an image and the '
        'Packers prepend jersey numbers. Number stripping plus storing the raw string recovers the '
        'Packers rows; the Texans image needs an authorized structured source, not transcription by '
        'eye." Both halves are checked below against the two club pages as they stand today.</div>'
        '<h2>Green Bay: the defect is real and larger than "rows are missing"</h2>'
        '<p>Every one of the published Packers rows stores the name as the club prints it, with the '
        'jersey number inside the string: <code>75 Sean Rhyan</code>, not <code>Sean Rhyan</code>. '
        'A join to the official injury report on the player name therefore returns <b>zero</b> '
        f'rows — {s["join_hits_with_raw_string"]} of {s["injury_rows_gb"]}. Stripping a leading '
        f'number and keeping the raw string recovers <b>{s["join_gain"]}</b>, which is what the '
        'table below measures row by row.</p>'
        f'{strip}'
        '<div class="note mid"><b>Stripping the number is necessary, not sufficient.</b> The live '
        f'chart and the published store disagree on {s["diffs"]} cells. Three of them are names '
        'the live chart no longer prints (Coleman Owen at receiver, kick return and punt return); '
        'one is a named player the store never captured (Kaleb Johnson, running back, fourth '
        'string); the rest are <b>empty cells the store cannot express at all</b>. The store is '
        'also missing the position label on two rows, so both arrive with <code>position: null</code> '
        'and cannot be placed on a unit.</div>'
        f'<h2>Every difference between the live chart and the store ({s["diffs"]})</h2>{diffs}'
        f'<h3>The three Green Bay players who appear on the injury report and nowhere on the chart</h3>'
        '<p>' + ", ".join(f"<b>{esc(n)}</b>" for n in s["unjoined_not_on_chart"]) + '. '
        'The source does not say why. They may be on reserve, on the practice squad, or simply '
        'omitted from an "unofficial" chart. <b>No reason is recorded</b>, because none is '
        'published: the absence is published as an absence.</p>'
        '<h2>Houston: an image is not a source</h2>'
        f'<div class="note bad"><b>{esc(t["page_title"])}</b> — heading "{esc(t["heading_on_page"])}". '
        f'{esc(t["evidence"])} <br><br><b>Decision: {esc(t["decision"])}</b><br><br>'
        f'<b>To close it:</b> {esc(t["required_to_close"])} '
        f'<a href="{esc(t["url"])}" target="_blank" rel="noopener">houstontexans.com depth chart</a></div>'
        '<h2>What this means for the deficiency register</h2>'
        '<ul class="tight">'
        '<li><b>31 of 32 clubs</b> have a parsed chart. Houston does not. That is a '
        '<b>coverage hole, not a finding of health</b>: the register is silent on Houston and '
        'silence must never be read as "no deficiency".</li>'
        '<li><b>Jersey numbers are stripped for joining and never used for ordering.</b> The '
        'brief rejects deriving depth from jersey number, experience or salary; nothing in this '
        'pipeline uses them. The number is evidence of the club\'s print format, not of rank.</li>'
        '<li><b>Every club chart is marked "Unofficial".</b> Green Bay prints the date it means: '
        '"Unofficial, Nov. 10, 2026". A depth row is therefore a dated club self-report — it must '
        'carry the club\'s date, not the date we fetched it.</li>'
        '</ul>')
    return page("Depth parse defects", "Official data", body,
                "The two depth-chart parsing failures named in the brief, measured against the live "
                "club pages: Green Bay's jersey-number prefix and Houston's image-only chart.", kpis)


def page_readiness(cfg):
    esc, table, pill, src_link, page = (cfg["esc"], cfg["table"], cfg["pill"],
                                        cfg["src_link"], cfg["page"])
    rd = _j("readiness.json")
    rows = []
    for r in rd["rows"]:
        rows.append([
            f'<a href="#{esc(r["id"])}">{esc(r["id"])}</a>',
            esc(r["category"]),
            esc(r["requirement"]),
            esc(r["gate"]),
            esc(r["needs"]),
            esc(r["today"]),
            esc(r["clears"]),
            src_link(r["source"], "official"),
        ])
    tbl = table([("ID", 0), ("Category", 0), ("Requirement", 0), ("The gate that blocks it", 0),
                 ("The number that would clear it", 0), ("Where that number stands today", 0),
                 ("What clears it", 0), ("Source", 0)], rows, "ready",
                filter_col=1, filter_label="Filter by category",
                note="One row per requirement in the owner's brief.")

    cats = rd["counts"]["by_category"]
    kpis = [("Requirements", f"{rd['counts']['total']}", f"{len(cats)} categories", ""),
            ("Measured, not typed", f"{sum(1 for r in rd['rows'] if r['measurement'] is not None)}",
             "rows whose 'today' value comes from a file", "good"),
            ("Availability items", f"{cats.get('Availability', 0)}", "the largest block", "warn")]
    body = ('<div class="note"><b>How to read this table.</b> Read left to right: the requirement, '
            'then the <b>gate</b> that is failing today, then the <b>number</b> that would clear it, '
            'then <b>where that number actually stands</b>, taken from the file named in the last '
            'column. No value in the fifth column is typed by hand: each one is produced by a '
            'measurement function in <code>tools/official/readiness.py</code>. If a measurement '
            'cannot run, the cell says so instead of guessing.</div>'
            f'{tbl}')
    return page("Decision readiness", "Overview", body,
                "One row per requirement: the gate that blocks it, the number that would clear it, "
                "and where that number stands today.", kpis)


def page_flags(cfg):
    esc, table, pill, src_link, page = (cfg["esc"], cfg["table"], cfg["pill"],
                                        cfg["src_link"], cfg["page"])
    rec = _j("week10_reconcile.json")
    dp = _j("depth_parse.json")
    flags = json.load(open(os.path.join(ROOT, "data", "official", "flags_2026_11_15.json"),
                           encoding="utf-8"))["flags"]
    rows = []
    for f in flags:
        rows.append([esc(f["id"]),
                     pill(f["severity"], {"red": "no", "amber": "mid", "green": "ok"}.get(f["severity"], "mut")),
                     esc(f["area"]), esc(f["finding"]), esc(f["effect"]),
                     esc(f.get("verify") or ""),
                     src_link(f["source"], "official")])
    tbl = table([("ID", 0), ("Severity", 0), ("Area", 0), ("Finding", 0), ("What it blocks", 0),
                 ("How to check it yourself", 0), ("Source", 0)], rows, "oflags", filter_col=2,
                filter_label="Filter by area")
    n_red = sum(1 for f in flags if f["severity"] == "red")
    n_amber = sum(1 for f in flags if f["severity"] == "amber")
    body = ('<div class="note"><b>Nothing here blocks the build, and nothing here is hidden.</b> '
            f'Each item was found by comparing a published value with the official page it cites. '
            f'{n_red} are red (a published value cannot be confirmed or is contradicted) and '
            f'{n_amber} amber (a value is confirmed but the evidence has a stated limit). The '
            'reconciliation that produced the first block is on '
            '<a href="capture.html">the re-capture page</a>; the depth defects on '
            '<a href="depth-parse.html">the depth-parse page</a>.</div>'
            '<div class="note mid"><b>Claims in the brief that could not be reproduced</b> are listed '
            'with the same prominence as the ones that could. A claim that does not reproduce is a '
            'finding, not a failure to be quietly dropped.</div>'
            f'{tbl}')
    return page("Official-source flags", "Governance", body,
                "Every irregularity found this session, with the source line needed to check it.")


PAGES = [
    ("capture.html", "Week 10 re-capture", "Official data", page_capture, ""),
    ("depth-parse.html", "Depth parse", "Official data", page_depth_parse, ""),
    ("readiness.html", "Readiness", "Overview", page_readiness, ""),
    ("official-flags.html", "Official flags", "Governance", page_flags, ""),
]


def build(cfg):
    """Return {filename: html} for the pages this module owns."""
    out = {}
    for name, _label, _grp, fn, _tag in PAGES:
        out[name] = fn(cfg)
    return out
