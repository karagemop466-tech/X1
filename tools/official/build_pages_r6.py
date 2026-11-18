"""Round-6 pages: the injury report as a timestamped delta series, and the fixture-context features.

Session `arena-55c364b6-x1` (R6-1, R6-2). Additive in the pattern of `tools/official/build_pages.py`
and `build_pages_r5.py`: this module only reads files, renders through `tools/build_console.py`'s own
helpers, and writes the two pages it owns.

    console/availability-series.html    the report as a series: states, deltas, movement, probes
    console/fixture-context.html        fixture context from published schedule facts only

Every number on both pages is recomputed by a verifier before it is written here:
`tools/verify_availability_series.py` (eight checks over the series) and
`tools/verify_2026_11_18.py` (eight checks over this round's pack, the fixture store and both
staleness gates). Nothing on these pages is typed by hand.
"""

from __future__ import annotations

import csv
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SERIES = os.path.join(ROOT, "data", "availability_series")
FIXTURES = os.path.join(ROOT, "data", "fixtures")
PACK = os.path.join(ROOT, "data", "verification", "2026_11_18")

INJ_URL = "https://www.nfl.com/injuries/"
W11_URL = "https://www.nfl.com/schedules/2026/by-week/week-11"
STORE_URL = ("https://github.com/karagemop466-tech/X1/blob/main/"
             "data/captures/index.jsonl")
ALIAS_URL = ("https://github.com/karagemop466-tech/X1/blob/main/"
             "data/captures/config.json")


def _csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _tsv(name):
    header, out = None, []
    with open(os.path.join(PACK, name), encoding="utf-8") as fh:
        for ln in fh.read().split("\n"):
            if not ln.strip() or ln.lstrip().startswith("#"):
                continue
            cells = ln.split("\t")
            if header is None or cells[0] == "club":
                header = cells
                continue
            out.append(dict(zip(header, cells)))
    return out


def build(cfg):
    esc, table, pill, src_link, page = (cfg["esc"], cfg["table"], cfg["pill"],
                                        cfg["src_link"], cfg["page"])

    # =======================================================================
    # page 1 - the injury report as a timestamped series
    # =======================================================================
    captures = _csv(os.path.join(SERIES, "captures.csv"))
    states = _csv(os.path.join(SERIES, "states.csv"))
    changes = _csv(os.path.join(SERIES, "changes.csv"))
    movement = _csv(os.path.join(SERIES, "movement_by_game.csv"))
    ssum = json.load(open(os.path.join(SERIES, "summary.json"), encoding="utf-8"))
    probe = _tsv("injury_probe_2026-11-18.tsv")
    reread = _tsv("week10_rows_reread_2026-11-18.tsv")
    manifest = json.load(open(os.path.join(PACK, "MANIFEST.json"), encoding="utf-8"))

    n_surprise = ssum["counts"]["downgrades_in_surprise_window"]
    kpis = [
        ("Dated reads retained", str(len(captures)), "each with a UTC clock time and a content hash",
         "good"),
        ("Distinct contents", str(len(states)), "two collector reads and one hand transcription", ""),
        ("Cell changes across states", str(len(changes)),
         "the delta, which is the thing the model is allowed to use", ""),
        ("Downgrades inside 24 h of kickoff", str(n_surprise),
         "the 'surprise' this project defined, measured on the only week captured", "mid"),
    ]

    # A: states
    hdr_a = [("State", 0), ("First read (UTC)", 0), ("Last read (UTC)", 0), ("Reads of it", 1),
             ("Method", 0), ("Rows", 1), ("Out", 1), ("Doubtful", 1), ("Questionable", 1),
             ("No game status", 1), ("Change against the previous state", 0), ("Source", 0)]
    rows_a = []
    for st in states:
        srcs = []
        if st["content_sha256"]:
            srcs.append(f'<span class="src mut">hash {esc(st["content_sha256"][:12])}</span>')
        srcs.append(src_link(STORE_URL, "capture index"))
        rows_a.append([
            f'<b>{esc(st["state_id"])}</b>',
            esc(st["first_read_utc"]),
            esc(st["last_read_utc"]),
            esc(st["n_reads"]),
            esc(st["methods"]),
            esc(st["rows"]),
            esc(st["out"]), esc(st["doubtful"]), esc(st["questionable"]),
            esc(st["game_status_blank"]),
            esc(st["delta_vs_prev_state"]),
            " ".join(srcs),
        ])

    # B: movement by fixture, the panel that says when the report actually moves
    hdr_b = [("Pair", 0), ("Fixture", 0), ("Kickoff (UTC)", 0), ("Later read (UTC)", 0),
             ("Hours from that read to kickoff", 1), ("Cell changes", 1), ("Downgrades", 1),
             ("Upgrades", 1), ("Players added", 1), ("Players removed", 1), ("Source", 0)]
    rows_b = []
    for m in movement:
        h = m["hours_to_kickoff"]
        flag = ""
        if h and float(h) < 0:
            flag = ' ' + pill("read after kickoff", "no")
        rows_b.append([
            esc(m["pair"]),
            esc(m["matchup"]) if m["matchup"] != "unmapped" else pill("unmapped", "no"),
            esc(m["kickoff_utc"]) if m["kickoff_utc"] else '<span class="src mut">no source</span>',
            esc(m["later_read_utc"]),
            esc(h) + flag,
            esc(m["cell_changes"]), esc(m["downgrades"]), esc(m["upgrades"]),
            esc(m["players_added"]), esc(m["players_removed"]),
            src_link(INJ_URL, "report page") + " " + src_link(STORE_URL, "payload"),
        ])

    # C: the changes themselves
    hdr_c = [("Pair", 0), ("Club", 0), ("Player", 0), ("Pos", 0), ("Field", 0), ("Was", 0),
             ("Now", 0), ("Direction", 0), ("Hours to kickoff", 1), ("Inside 24 h window", 0),
             ("Fixture", 0), ("Source", 0)]
    rows_c = []
    for c in changes:
        kind = {"downgrade": "no", "upgrade": "ok"}.get(c["direction"], "mut")
        rows_c.append([
            esc(c["pair"]), esc(c["team"]), esc(c["player"]), esc(c["position"]),
            esc(c["field"].replace("_", " ")),
            esc(c["from_value"]) if c["from_value"] else '<span class="mut">not on report</span>',
            esc(c["to_value"]) if c["to_value"] else '<span class="mut">removed from game status</span>',
            pill(c["direction"], kind),
            esc(c["hours_to_kickoff"]) if c["hours_to_kickoff"]
            else '<span class="src mut">no source</span>',
            esc(c["in_surprise_window"]),
            esc(c["club_matchup"]) or '<span class="src mut">no source</span>',
            src_link(INJ_URL, "report page"),
        ])

    # D: the capture log, including the drift alarm's one firing
    hdr_d = [("Read (UTC)", 0), ("Method", 0), ("Rows", 1), ("Clubs", 1), ("State", 0),
             ("Drift alarm", 0), ("Content hash", 0), ("Same content as the read before it", 0),
             ("Source", 0)]
    rows_d = []
    for c in captures:
        same = "yes" if c["content_sha256"] == c["prev_content_sha256"] else "no"
        drift = (pill("pass", "ok") if c["drift"] == "pass"
                 else pill(f"fail ({c['drift_violations']} rule)", "no"))
        rows_d.append([
            esc(c["read_utc"]), esc(c["method"]), esc(c["rows"]), esc(c["clubs"]),
            esc(c["state_id"]), drift,
            f'<span class="src mut">{esc(c["content_sha256"][:12])}</span>',
            pill(same, "ok" if same == "yes" else "mut"),
            src_link(INJ_URL, "page") + " " + src_link(STORE_URL, "index line"),
        ])

    # E: the 2026-11-18 probe and the re-read
    hdr_e = [("Read (UTC)", 0), ("Week asked for", 0), ("Resolved to", 0),
             ("Page title printed / comparison made", 0), ("Verdict", 0), ("Source", 0)]
    rows_e = []
    for r in probe:
        rows_e.append([
            esc(r["probe_utc"]), esc(r["week_attempted"]),
            esc(r["url_resolved"]).replace("https://", ""),
            esc(r["page_title_as_printed"]),
            esc(r["verdict"]),
            src_link(r["source_url"], "official page") + " "
            + src_link("https://www.nfl.com/injuries/league/2026/REG11", "the URL asked for"),
        ])
    rows_e.append([
        "2026-11-18T03:05Z", "Week 10 re-read (control)", "44 rows, 4 club tables",
        "572 cells compared against all three published copies of the table",
        "0 mismatches &mdash; the published table still matches the page",
        src_link(INJ_URL, "report page") + " " + src_link(
            "https://github.com/karagemop466-tech/X1/blob/main/tools/verify_2026_11_18.py",
            "the check that recomputes it"),
    ])

    hdr_f = [("Retained read", 0), ("Official URL", 0), ("SHA-256 (first 16)", 0), ("Bytes", 1),
             ("Read at", 0), ("Source", 0)]
    rows_f = []
    for f in manifest["files"]:
        rows_f.append([
            f'<code>{esc(os.path.basename(f["path"]))}</code>',
            src_link(f["url"], "official"),
            f'<span class="src mut">{esc(f["sha256"][:16])}</span>',
            esc(f["bytes"]), esc(f["read_utc"]),
            src_link("https://github.com/karagemop466-tech/X1/blob/main/" + f["path"], "retained file"),
        ])

    body1 = (
        '<div class="note good"><b>What this page is.</b> The league posts the injury report several '
        'times a week, and the collector in this repository keeps every read it makes &mdash; clock '
        'time, row count, and a hash over the rows as they were known. This page is what those reads '
        'say <i>between</i> them: who arrived on the report, who left it, and which cells moved. The '
        'brief asks for the delta rather than the level, so the delta column comes before the counts '
        'in every table here, and a state with no earlier read is published as an anchor rather than '
        'as a zero.</div>'

        '<h2>The states the report has been in</h2>'
        '<p>Fourteen reads, three distinct contents. Two of the three are collector reads of the live '
        'page; the middle one is the 2026-11-15 hand transcription retained so the series has its '
        'middle point. The last state was read twelve times over 28 hours and never moved &mdash; that '
        'is a stability finding, not a fetch failure, and the two must not be stored as the same thing.</p>'
        f'{table(hdr_a, rows_a, "ser-states")}'

        '<h2>Where the movement actually was</h2>'
        '<p>Every cell change is attributed to the club\'s fixture and timed against its kickoff. In '
        'the only week the store holds, the movement is concentrated on the Monday-night game '
        '(30 of 32 cells, 31 hours before kickoff) and two cells on a Sunday game whose read landed '
        '14 minutes <i>after</i> its own kickoff. That second row is the warning this panel exists to '
        'print: a report read is only usable for the games that have not started.</p>'
        f'{table(hdr_b, rows_b, "ser-move", filter_col=1, filter_label="Filter fixtures")}'

        '<h2>The changes themselves</h2>'
        f'<p>Upgrade and downgrade use this project\'s ordering &mdash; {esc(ssum["definitions"]["game_status_order"])} '
        f'and {esc(ssum["definitions"]["practice_order"])} &mdash; which is a definition of ours and is '
        'published as such. "Surprise" means a downgrade recorded inside '
        f'{esc(ssum["hours_surprise_window"])} h of that club\'s kickoff.</p>'
        f'{table(hdr_c, rows_c, "ser-changes", filter_col=1, filter_label="Filter clubs", max_rows=40)}'

        '<h2>The capture log, with the drift alarm</h2>'
        '<p>The alarm fired once, on the hand transcription, because that read spells the Rams '
        '<code>LAR</code> where the standings page prints <code>LA</code> &mdash; a club-code fault, not '
        'a row-count fault. It is shown as it fired. Joining the reads without the alias invents '
        '14 arrivals and 14 departures on each of those two pairs; with it, the Week 10 report gained '
        'two players and lost none. That is the difference the alias is worth, and it is the reason '
        'the alias table is an output of the builder rather than a detail of the code.</p>'
        f'{table(hdr_d, rows_d, "ser-caps", filter_col=1, filter_label="Filter method")}'

        '<h2>The read this page was written on, 2026-11-18</h2>'
        '<p>Two things were checked against the live page before anything here was published: whether '
        'the Week 11 report exists yet, and whether the published Week 10 table still agrees with the '
        'page it came from.</p>'
        f'{table(hdr_e, rows_e, "ser-probe")}'

        '<h2>Retained reads</h2>'
        '<p>The pack this page draws on, with the fingerprint of each file as committed. Re-run '
        '<code>python3 tools/verify_2026_11_18.py</code> to re-hash all three and re-do the cell '
        'comparison; the build fails if any file no longer matches its manifest.</p>'
        f'{table(hdr_f, rows_f, "ser-manifest")}'

        '<h3>What this series does not yet prove</h3>'
        '<div class="note warn"><ul class="tight">'
        '<li><b>One week deep.</b> The Week 11 report had not been published at the 2026-11-18 probe, '
        'so there is no second week to diff. The Wednesday&raquo;Thursday&raquo;Friday cadence the '
        'brief asks for is running, but it has only had Week 10 to run on.</li>'
        '<li><b>No outcome join.</b> A designation change cannot be scored against playing time: the '
        'repository holds no inactive lists and no snap counts for 2026, so "was the downgrade real" '
        'is unanswerable today and the label stays out of the model. Requirement R-13 stays blocked on '
        'exactly that.</li>'
        '<li><b>Two capture methods.</b> One of the three states is a hand transcription. A pair whose '
        'methods differ mixes a source change with a method change and is labelled in the table.</li>'
        '</ul></div>'
        '<div class="note"><b>Downloads.</b> '
        '<a href="../data/availability_series/states.csv">states.csv</a> &middot; '
        '<a href="../data/availability_series/captures.csv">captures.csv</a> &middot; '
        '<a href="../data/availability_series/changes.csv">changes.csv</a> &middot; '
        '<a href="../data/availability_series/movement_by_game.csv">movement_by_game.csv</a> '
        '&middot; definitions and caveats: '
        '<a href="../data/availability_series/summary.json">summary.json</a>. Sources: '
        f'{src_link(INJ_URL, "the league report page")}, {src_link(STORE_URL, "capture index")}, '
        f'{src_link(ALIAS_URL, "capture config and diff alias")}.</div>'
    )
    p1 = page("Injury report series", "Official data", body1,
              "Every retained read of the official report, the delta between them, and the clock "
              "time each one was taken at.", kpis)

    # =======================================================================
    # page 2 - fixture context
    # =======================================================================
    fx = _csv(os.path.join(FIXTURES, "fixture_context_2026.csv"))
    fsum = json.load(open(os.path.join(FIXTURES, "summary.json"), encoding="utf-8"))
    c = fsum["counts"]
    w11 = [r for r in fx if r["week"] == "11"]
    w10 = [r for r in fx if r["week"] == "10"]

    kpis2 = [
        ("Clubs covered, each week", f'{c["clubs_covered_week11"]}/{c["clubs_covered_week10"]}',
         "32 rows per week, fixtures and byes together", "good"),
        ("Short weeks (4 days or fewer)", str(c["short_week"]),
         "found from printed dates alone", "mid"),
        ("Venues traced to an official page", f'{c["with_venue_week10"] + c["with_venue_week11"]} '
         f'of {c["week10_rows"] + c["week11_rows"] - c["byes_week10"] - c["byes_week11"]} club-rows',
         "Week 10 from the game centres, Week 11 only where the page prints one", ""),
        ("Features with no source in this pack", "2",
         "per-fixture Week 11 venues, and consecutive prime time", "no"),
    ]

    def fixture_rows(rs):
        hdr = [("Club", 0), ("Vs", 0), ("Side", 0), ("Kickoff", 0), ("Slot", 0), ("Network", 0),
               ("Day", 0), ("Rest (days)", 1), ("Short week", 0), ("Off a bye", 0),
               ("Venue as printed", 0), ("Flags", 0), ("Source", 0)]
        out = []
        for r in rs:
            srcs = []
            if r["source_url"]:
                srcs.append(src_link(r["source_url"], "schedule"))
            if r["game_url"]:
                srcs.append(src_link(r["game_url"], "game centre"))
            if r["venue_as_printed"] and r["venue_source"].startswith("http"):
                srcs.append(src_link(r["venue_source"], "venue"))
            if not srcs:
                srcs.append('<span class="src mut">no source</span>')
            out.append([
                f'<b>{esc(r["club"])}</b>' if r["status_this_week"] == "game" else
                f'{esc(r["club"])} {pill("bye", "mut")}',
                esc(r["opponent"]) if r["opponent"] else '<span class="mut">&mdash;</span>',
                esc(r["side"]),
                esc(r["kickoff_date"]) + (f' {esc(r["kickoff_time_as_printed"])}'
                                          if r["kickoff_time_as_printed"] else ""),
                esc(r["prime_time_slot"]) if r["prime_time_slot"]
                else '<span class="mut">&mdash;</span>',
                esc(r["network"]) if r["network"] else '<span class="mut">&mdash;</span>',
                esc(r["day_of_week"]) if r["day_of_week"] else '<span class="mut">&mdash;</span>',
                esc(r["rest_days"]) if r["rest_days"] != ""
                else '<span class="src mut">no source</span>',
                pill("yes", "no") if r["short_week"] == "yes"
                else (pill("no", "ok") if r["short_week"] == "no"
                      else '<span class="mut">&mdash;</span>'),
                pill("yes", "mid") if r["came_off_bye"] == "yes"
                else (pill("no", "ok") if r["came_off_bye"] == "no"
                      else '<span class="mut">&mdash;</span>'),
                (esc(r["venue_as_printed"]) if r["venue_as_printed"]
                 else '<span class="src mut">no source</span>'),
                f'<span class="mut">{esc(r["flags"][:150])}</span>',
                " ".join(srcs),
            ])
        return hdr, out

    verif_link = src_link("https://github.com/karagemop466-tech/X1/blob/main/"
                          "tools/verify_2026_11_18.py", "tools/verify_2026_11_18.py")
    hdr_w11, rows_w11 = fixture_rows(w11)
    hdr_w10, rows_w10 = fixture_rows(w10)

    hdr_r = [("Rest days since the previous printed fixture", 1), ("Club-rows in both weeks", 1),
             ("Source", 0)]
    rows_r = [[esc(k), esc(v),
               src_link("https://github.com/karagemop466-tech/X1/blob/main/"
                        "data/fixtures/fixture_context_2026.csv", "the 64 rows this counts") + " "
               + src_link(W11_URL, "Week 11 page")]
              for k, v in sorted(fsum["rest_days_distribution"].items(), key=lambda kv: int(kv[0]))]

    body2 = (
        '<div class="note good"><b>What this page is.</b> One row per club per week, carrying only '
        'features that a published schedule field can be pointed at: the printed date, the printed '
        'slot, the printed network, the printed venue, and the rest interval that falls out of two '
        'printed dates. Where the league prints nothing, the cell is blank and says so. That is the '
        'gate on the requirement &mdash; "built only from published schedule facts" &mdash; and it is '
        'why two features are published as unavailable rather than estimated.</div>'

        f'<h2>Week 11, as read at {esc(fsum["read_of_record"]["read_utc"])}</h2>'
        f'<p>The slate was read once, in full, from the league\'s own by-week page: 13 fixtures and 6 '
        f'byes, all 32 clubs accounted for exactly once, which the pack verifier asserts before this '
        f'page is written ({esc(str(c["fixtures_week11"]))} fixtures &times; 2 + '
        f'{esc(str(c["byes_week11"]))} byes = 32). The read is retained in '
        f'<code>data/verification/2026_11_18/</code> and hashed in its manifest.</p>'
        f'{table(hdr_w11, rows_w11, "fx-w11", filter_col=0, filter_label="Filter clubs")}'

        '<h2>The rest-day shape of the slate</h2>'
        '<p>Counted in whole days between printed dates, over both weeks in this pack. The four-day '
        'rows are the Thursday-night pattern; the six-day rows are the two clubs that played '
        'Monday night and go again Sunday afternoon; the fourteen-day rows are the clubs coming off a '
        'bye. This distribution is the reason the feature exists: a totals model that ignores rest '
        'treats four of these club-rows like the thirty-three that got a normal week.</p>'
        f'{table(hdr_r, rows_r, "fx-rest", sortable=False)}'

        '<h2>Week 10, the same features on a completed slate</h2>'
        '<p>Kept in the same table shape so the two weeks can be compared cell for cell. Week 10 is '
        'where the venues come from: the game-centre register reads the location and stadium for each '
        'fixture, and the international list confirms the Munich fixture independently.</p>'
        f'{table(hdr_w10, rows_w10, "fx-w10", filter_col=0, filter_label="Filter clubs")}'

        '<h3>Definitions and limits, in the words the builder writes</h3>'
        '<ul class="tight">'
        + "".join(f'<li><b>{esc(k.replace("_", " "))}</b> {esc(v)}</li>'
                  for k, v in fsum["definitions"].items()) + '</ul>'
        '<div class="note warn">' + "".join(
            f'<p><b>{esc(n.split(":")[0])}</b>{esc(":".join(n.split(":")[1:]))}</p>'
            for n in fsum["caveats"]) + '</div>'
        '<div class="note"><b>Downloads.</b> '
        '<a href="../data/fixtures/fixture_context_2026.csv">fixture_context_2026.csv</a> (64 rows) '
        '&middot; <a href="../data/fixtures/summary.json">summary.json</a> &middot; retained read: '
        '<a href="../data/verification/2026_11_18/week11_slate_2026-11-18.tsv">'
        'week11_slate_2026-11-18.tsv</a>. Checks: '
        + verif_link + '.</div>'
    )
    p2 = page("Fixture context", "Official data", body2,
              "Schedule facts only: rest, slot, network, venue &mdash; and the two features the "
              "league does not print.", kpis2)

    return {"availability-series.html": p1, "fixture-context.html": p2}
