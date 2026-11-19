#!/usr/bin/env python3
"""Week 11 official injury report: parse the fetch-tool transcription, check it,
and render a sourced page.

Input : data/capture/2026_w11/official_nflcom_injuries_week11_fetch.psv
Output: data/capture/2026_w11/summary.json            (counts, checks, anomalies, SHA-256 of the PSV)
        data/capture/2026_w11/injuries_week11.csv      (one row per player, source column)
        week11/index.html                              (sourced static page, deployed with the site)

Honesty rules enforced here:
  * Every published row carries the source URL https://www.nfl.com/injuries/ .
  * Nothing is inferred: a blank cell stays blank; the PSV is the only input.
  * Checks fail loudly (exit 1) on schema, vocabulary, duplicate or missing-section problems.
  * The PSV is a fetch-tool transcription, not raw HTTP bytes (bash cannot reach nfl.com);
    the SHA-256 recorded here is the hash of OUR transcription file.

Usage:
  python3 tools/official/capture_w11.py          # rebuild the outputs
  python3 tools/official/capture_w11.py --check  # rebuild in memory and fail if committed outputs differ
"""
import csv
import hashlib
import html
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAP = ROOT / "data" / "capture" / "2026_w11"
PSV = CAP / "official_nflcom_injuries_week11_fetch.psv"
SUMMARY = CAP / "summary.json"
CSV_OUT = CAP / "injuries_week11.csv"
PAGE = ROOT / "week11" / "index.html"
SOURCE_URL = "https://www.nfl.com/injuries/"

FIELDS = ["game", "listed_team", "player", "position", "injury",
          "practice_status", "game_status", "chunk", "fetched_utc"]
PRACTICE_OK = {"", "Full Participation in Practice", "Limited Participation in Practice",
               "Did Not Participate In Practice"}
GAME_OK = {"", "Questionable", "Doubtful", "Out"}
NO_INJ_MARK = "NO INJURIES REPORTED (section text)"
# The 32 clubs by abbreviation (NFL.com's listing abbreviations as shown on the page).
CLUBS_32 = {"ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB",
            "HOU", "IND", "JAX", "KC", "LV", "LAC", "LAR", "MIA", "MIN", "NE", "NO", "NYG",
            "NYJ", "PHI", "PIT", "SF", "SEA", "TB", "TEN", "WAS"}
# Club labels on the page use AZ for Arizona; map to the 32-club set.
PAGE_ABBR_TO_CLUB = {"AZ": "ARI"}
# Anomalies found while transcribing; published, not corrected. (player, listed_team, reason)
ANOMALIES = [
    ("Jaylen Waddle", "DEN Broncos",
     "Listed under the Broncos table on the Week 11 page. Club attribution not verified in this session; kept as shown and flagged for check against the official roster page."),
    ("Mike Evans", "SF 49ers",
     "Listed under the 49ers table on the Week 11 page. Club attribution not verified in this session; kept as shown and flagged for check against the official roster page."),
    ("Dee Alford", "BUF Bills",
     "Displayed name differs from the player profile link slug on the page (slug: deaundre-ford). Displayed name kept as shown."),
    ("Jacob Hummel", "HOU Texans",
     "Displayed name differs from the player profile link slug on the page (slug: jake-hummel). Displayed name kept as shown."),
]


# Observations (not errors): stated so a blank cell is never read as "available".
OBSERVATIONS = [
    "Game Status is populated only for the Thursday game (IND-HOU) in this read. Every Sunday and Monday Game Status cell is blank. The page does not say why. A blank Game Status is NOT evidence that a player is available; it is not inferred either way.",
    "Six clubs (ATL, CLE, GB, LAR, NE, SEA) do not appear on this page. The page does not state byes, so the reason is not inferred here.",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse():
    rows, markers, errors = [], [], []
    for n, line in enumerate(PSV.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("|")
        if len(parts) != len(FIELDS):
            errors.append(f"line {n}: {len(parts)} fields, expected {len(FIELDS)}")
            continue
        rec = dict(zip(FIELDS, parts))
        if rec["player"] == NO_INJ_MARK:
            markers.append(rec)
            continue
        rows.append(rec)
    return rows, markers, errors


def check(rows, markers, errors):
    problems = list(errors)
    seen = Counter((r["game"], r["listed_team"], r["player"]) for r in rows)
    for key, c in seen.items():
        if c > 1:
            problems.append(f"duplicate row {key} x{c}")
    for r in rows:
        if r["practice_status"] not in PRACTICE_OK:
            problems.append(f"unknown practice status {r['practice_status']!r} for {r['player']}")
        if r["game_status"] not in GAME_OK:
            problems.append(f"unknown game status {r['game_status']!r} for {r['player']}")
        if not r["player"].strip() or not r["listed_team"].strip():
            problems.append("blank player or team")
    # Each listed team must have either player rows or a 'no injuries reported' marker.
    teams = defaultdict(list)
    for r in rows:
        teams[r["listed_team"]].append(r)
    for m in markers:
        teams.setdefault(m["listed_team"], [])
    games = defaultdict(set)
    for r in rows + markers:
        games[r["game"]].add(r["listed_team"])
    for g, ts in games.items():
        if len(ts) != 2:
            problems.append(f"game {g} has {len(ts)} listed teams, expected 2")
    club_codes = set()
    for t in teams:
        code = t.split(" ")[0]
        code = PAGE_ABBR_TO_CLUB.get(code, code)
        club_codes.add(code)
        if code not in CLUBS_32:
            problems.append(f"unknown club code {code!r} in {t!r}")
    total = sum(len(v) for v in teams.values())
    if total != len(rows):
        problems.append(f"per-team sum {total} != player rows {len(rows)}")
    return problems, teams, games, club_codes


def build():
    rows, markers, parse_errors = parse()
    problems, teams, games, club_codes = check(rows, markers, parse_errors)
    status = Counter(r["game_status"] or "(blank)" for r in rows)
    practice = Counter(r["practice_status"] or "(blank)" for r in rows)
    designated = [r for r in rows if r["game_status"]]
    summary = {
        "source_url": SOURCE_URL,
        "source_title": "Official Latest NFL Injury Report for Players - Week 11 of the 2026 Season | NFL.com",
        "capture_kind": "fetch-tool transcription (7 chunks read 2026-11-19 UTC). Not raw HTTP bytes: bash cannot reach nfl.com.",
        "transcription_file": PSV.relative_to(ROOT).as_posix(),
        "transcription_sha256": sha256(PSV),
        "player_rows": len(rows),
        "no_injury_sections": len(markers),
        "listed_teams": len(teams),
        "clubs_listed": len(club_codes),
        "clubs_not_listed": sorted(CLUBS_32 - club_codes),
        "games_listed": len(games),
        "game_headers": sorted(games.keys()),
        "rows_per_team": {t: len(v) for t, v in sorted(teams.items())},
        "game_status_counts": dict(sorted(status.items())),
        "practice_status_counts": dict(sorted(practice.items())),
        "designated_rows": len(designated),
        "observations": OBSERVATIONS,
        "anomalies": [{"player": p, "listed_team": t, "reason": why} for p, t, why in ANOMALIES],
        "checks_failed": problems,
        "checks_passed": not problems,
    }
    return rows, markers, summary


def render_csv(rows):
    out = []
    for r in rows:
        out.append({"source_url": SOURCE_URL, "game": r["game"], "listed_team": r["listed_team"],
                    "player": r["player"], "position": r["position"], "injury": r["injury"],
                    "practice_status": r["practice_status"], "game_status": r["game_status"],
                    "fetched_utc": r["fetched_utc"]})
    return out


def render_html(rows, markers, s):
    esc = html.escape
    tr = []
    anomaly_players = {a["player"] for a in s["anomalies"]}
    for r in rows:
        flag = " <span class='flag'>flag</span>" if r["player"] in anomaly_players else ""
        tr.append(
            "<tr><td>{g}</td><td>{t}</td><td>{p}{f}</td><td>{pos}</td><td>{inj}</td>"
            "<td>{pr}</td><td>{gs}</td><td><a href='{u}' target='_blank' rel='noopener'>nfl.com</a></td></tr>".format(
                g=esc(r["game"]), t=esc(r["listed_team"]), p=esc(r["player"]), f=flag,
                pos=esc(r["position"]), inj=esc(r["injury"]), pr=esc(r["practice_status"]),
                gs=esc(r["game_status"]), u=SOURCE_URL))
    for m in markers:
        tr.append("<tr><td>{g}</td><td>{t}</td><td colspan='5'><i>No Injuries Reported (section text on the official page)</i></td>"
                  "<td><a href='{u}' target='_blank' rel='noopener'>nfl.com</a></td></tr>".format(
                      g=esc(m["game"]), t=esc(m["listed_team"]), u=SOURCE_URL))
    anom = "".join("<li><b>{p}</b> ({t}): {r}</li>".format(p=esc(a["player"]), t=esc(a["listed_team"]), r=esc(a["reason"]))
                   for a in s["anomalies"])
    gs = s["game_status_counts"]
    kpis = "".join(
        "<div class='kpi'><div class='lab'>{l}</div><div class='val'>{v}</div></div>".format(l=esc(l), v=esc(str(v)))
        for l, v in [("Player rows", s["player_rows"]), ("Teams listed", s["listed_teams"]),
                     ("Games listed", s["games_listed"]), ("Out", gs.get("Out", 0)),
                     ("Questionable", gs.get("Questionable", 0)), ("Doubtful", gs.get("Doubtful", 0)),
                     ("Clubs not listed", len(s["clubs_not_listed"]))])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Week 11 official injury report — captured 2026-11-19</title>
<link rel="stylesheet" href="../assets/site.css">
<style>.kpis{{display:flex;gap:12px;flex-wrap:wrap;margin:12px 0}}.kpi{{border:1px solid #ddd;border-radius:8px;padding:10px 14px;min-width:120px}}
.kpi .lab{{font-size:12px;color:#555}}.kpi .val{{font-size:22px;font-weight:600}}.flag{{background:#fff3cd;border-radius:4px;padding:0 4px;font-size:12px}}
table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{border-bottom:1px solid #e5e5e5;padding:6px 8px;text-align:left;vertical-align:top}}</style>
</head><body>
<p><a href="../index.html">&larr; Landing page</a> · <a href="../console/flagged.html">Flagged for review</a></p>
<p>Site data snapshot: 2026-11-14 (Week 10 tables, unchanged). This page is the Week 11 read dated 2026-11-19 (UTC).</p>
<h1>Week 11 official injury report</h1>
<p>Source: <a href="{SOURCE_URL}" target="_blank" rel="noopener">{SOURCE_URL}</a> (NFL.com, read 2026-11-19 UTC).
Every row links to this page. The table is a <b>fetch-tool transcription</b> of the seven page chunks, not raw HTTP bytes; a second independent read is still pending.
Blank cells are blank on the official page. Nothing is inferred.</p>
<div class="kpis">{kpis}</div>
<p>Transcription SHA-256 (of the file this table was built from): <code>{s['transcription_sha256']}</code>
· Clubs not listed on this page: {esc(', '.join(s['clubs_not_listed']) or 'none')} (the page omits clubs without a game in the report; byes are not stated on this page).</p>
<h2>What this read does and does not show</h2>
<ul>{''.join('<li>' + esc(o) + '</li>' for o in s['observations'])}</ul>
<h2>Irregularities flagged for review</h2>
<ul>{anom}</ul>
<h2>All listed players</h2>
<table><thead><tr><th>Game (as listed)</th><th>Team</th><th>Player</th><th>Pos</th><th>Injury</th><th>Practice status</th><th>Game status</th><th>Source</th></tr></thead>
<tbody>{''.join(tr)}</tbody></table>
</body></html>
"""


def main(argv):
    rows, markers, s = build()
    csv_rows = render_csv(rows)
    csv_text = ""
    if csv_rows:
        import io
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=list(csv_rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(csv_rows)
        csv_text = buf.getvalue()
    summary_text = json.dumps(s, indent=2, ensure_ascii=False) + "\n"
    page_text = render_html(rows, markers, s)
    if s["checks_failed"]:
        print("CHECKS FAILED:")
        for p in s["checks_failed"]:
            print("  -", p)
        return 1
    if "--check" in argv:
        ok = True
        for path, text in [(SUMMARY, summary_text), (CSV_OUT, csv_text), (PAGE, page_text)]:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                print("STALE:", path.relative_to(ROOT).as_posix())
                ok = False
        print("PASS" if ok else "FAIL", f"player_rows={s['player_rows']} sections={s['no_injury_sections']} games={s['games_listed']}")
        return 0 if ok else 1
    SUMMARY.write_text(summary_text, encoding="utf-8")
    CSV_OUT.write_text(csv_text, encoding="utf-8")
    PAGE.parent.mkdir(parents=True, exist_ok=True)
    PAGE.write_text(page_text, encoding="utf-8")
    print(f"wrote summary, csv ({len(csv_rows)} rows) and page; checks passed; player_rows={s['player_rows']} sections={s['no_injury_sections']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
