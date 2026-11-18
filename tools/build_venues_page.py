#!/usr/bin/env python3
"""Render venues/index.html from data/nfl/venues_2026_week10.csv (brief row 24).

Session arena/5433abad-x1. The page is generated, not hand-edited. Every value comes from the CSV;
every row links to the official NFL Game Centre page the value was read from. The page is
published by the Pages workflow (additive copy step) and is checked by --check.

    python3 tools/build_venues_page.py          # write venues/index.html
    python3 tools/build_venues_page.py --check  # fail if the committed page is stale
"""
import csv
import html
import sys

SRC = "data/nfl/venues_2026_week10.csv"
OUT = "venues/index.html"
SCHED = "https://www.nfl.com/schedules/2026/by-week/week-10"

FLAGS = [
    "<strong>Label difference, NE @ DET (Munich).</strong> The Game Centre prints "
    "<code>FC BAYERN MUNICH STADIUM</code>; the schedule file prints "
    "<code>FC Bayern Munich Arena, Munich, Germany</code>. The Game Centre string is what this page publishes. "
    "Sources: <a href=\"https://www.nfl.com/games/patriots-at-lions-2026-reg-10\">Game Centre</a>.",
    "<strong>Scope.</strong> Week 10 only: 14 of 272 regular-season games (the count in the NFL's 2026 schedule "
    "announcement, media.nfl.com, 2026-05-14). 258 venues are not yet transcribed.",
    "<strong>Schedule file incomplete.</strong> In <code>data/nfl/schedule_2026_week10.csv</code>, 13 of 14 venue "
    f"cells are blank and only one final score is filled. The <a href=\"{SCHED}\">official Week 10 page</a> is the reference.",
]


def build() -> str:
    rows = list(csv.DictReader(open(SRC, encoding="utf-8")))
    body = []
    for r in rows:
        note = r["schedule_csv_venue_note"] or "&mdash;"
        flag = "" if not r["label_check"].startswith("differs") else (
            f' <span class="tag warn">{html.escape(r["label_check"])}</span>')
        body.append(
            "<tr>"
            f"<td>{html.escape(r['date'])}</td>"
            f"<td>{html.escape(r['away'])} @ {html.escape(r['home'])}</td>"
            f"<td>{html.escape(r['away_score'])}&ndash;{html.escape(r['home_score'])}</td>"
            f"<td>{html.escape(r['location_as_printed'])}</td>"
            f"<td>{html.escape(r['stadium_as_printed'])}</td>"
            f"<td>{html.escape(note) if r['schedule_csv_venue_note'] else note}{flag}</td>"
            f"<td><a href=\"{html.escape(r['game_center_url'])}\" rel=\"noopener\">Game Centre</a></td>"
            "</tr>")
    flags = "".join(f"<li>{f}</li>" for f in FLAGS)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Week 10 venues - official NFL Game Centre</title>
<link rel="stylesheet" href="../assets/site.css">
</head>
<body>
<main class="wide">
<p class="eyebrow"><a href="../">&larr; Home</a> &middot; Brief row 24 &middot; Week 10 only</p>
<h1 class="pagetitle">Week 10 venues, from the official NFL Game Centre</h1>
<p class="muted">Site snapshot 2026-11-14. Venue reads retrieved 2026-11-18. Each venue is copied from the <em>Game Info</em> block of the official Game Centre page for that game, as printed. Nothing is inferred. Machine-readable copy: <a href="../data/nfl/venues_2026_week10.csv">venues_2026_week10.csv</a>. Verifier: <code>tools/verify_venues_w10.py</code>.</p>
<div class="tablewrap"><table>
<thead><tr><th>Date</th><th>Game (away @ home)</th><th>Final (away&ndash;home)</th><th>Location</th><th>Stadium</th><th>Schedule file venue note</th><th>Source</th></tr></thead>
<tbody>
{chr(10).join(body)}
</tbody></table></div>
<div class="card"><h2>Flagged for review</h2><ol>{flags}</ol>
<p class="muted">Official reference for the fixture list: <a href="{SCHED}">NFL 2026 Week 10 schedule</a>.</p></div>
</main></body></html>
"""


def main() -> int:
    text = build()
    if "--check" in sys.argv:
        try:
            cur = open(OUT, encoding="utf-8").read()
        except FileNotFoundError:
            print(f"FAIL: {OUT} missing"); return 1
        if cur != text:
            print(f"FAIL: {OUT} is stale; run python3 tools/build_venues_page.py"); return 1
        print(f"ok: {OUT} matches a fresh build")
        return 0
    import os
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(text)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
