#!/usr/bin/env python3
"""Week 11 official injury report: parse the fetch-tool transcription, check it,
and render a sourced page.

Input : data/capture/2026_w11/official_nflcom_injuries_week11_fetch.psv
Output: data/capture/2026_w11/summary.json            (counts, checks, anomalies, SHA-256 of the PSV)
        data/capture/2026_w11/injuries_week11.csv      (one row per player, source column)
        data/capture/2026_w11/crossread.json           (only with --compare PATH: row-by-row cross-read)

The public Week 11 page is NOT built here: PR #132 (arena-2d1ba329-x1) publishes it as app/week11.html.

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
CROSSREAD = CAP / "crossread.json"
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
    ("Charlie Heck", "IND Colts",
     "Cross-read divergence. PR #132's read at 2026-11-19T13:16:57Z shows Injury 'Not injury related - personal matter' and Game Status 'Questionable'. This transcription and a re-fetch of the page at about 22:10Z show both cells blank. Not resolved here; needs a dated capture series."),
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



def compare(rows, other: Path):
    """Row-by-row comparison of this transcription with another read of the same page.
    Key = (club, player, position, injury, practice status, game status)."""
    import csv as _csv
    mine = Counter((r["listed_team"].split(" ")[0], r["player"], r["position"], r["injury"],
                    r["practice_status"], r["game_status"]) for r in rows)
    theirs_rows = []
    with other.open(encoding="utf-8") as f:
        for rec in _csv.DictReader(f, delimiter="\t"):
            theirs_rows.append((rec["club"], rec["player"], rec["position"], rec["injury"],
                                rec["practice_status"], rec["game_status"]))
    theirs = Counter(theirs_rows)
    return {
        "compared_on": "2026-11-19 (UTC)",
        "this_transcription": PSV.relative_to(ROOT).as_posix(),
        "this_transcription_sha256": sha256(PSV),
        "other_read_file": other.name,
        "other_read_sha256": sha256(other),
        "other_read_source": "PR #132 head e70ae63560be17dbb6f35cbfd71b228b5049bf33, data/week11/latest_read.tsv (capture_utc 2026-11-19T13:16:57Z), read via the GitHub contents API; not committed to this branch",
        "rows_here": sum(mine.values()),
        "rows_there": len(theirs_rows),
        "identical_rows": sum((mine & theirs).values()),
        "only_in_this_transcription": [list(k) for k in (mine - theirs).elements()],
        "only_in_other_read": [list(k) for k in (theirs - mine).elements()],
        "note": "A difference is not resolved here. Either the official page changed between the two read times, or one transcription is wrong; a dated capture series is needed to tell which.",
    }


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
    if s["checks_failed"]:
        print("CHECKS FAILED:")
        for p in s["checks_failed"]:
            print("  -", p)
        return 1
    if "--compare" in argv:
        other = Path(argv[argv.index("--compare") + 1])
        result = compare(rows, other)
        CROSSREAD.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"cross-read: identical={result['identical_rows']} only_here={result['only_in_this_transcription']} only_there={result['only_in_other_read']}")
        return 0
    if "--check" in argv:
        ok = True
        for path, text in [(SUMMARY, summary_text), (CSV_OUT, csv_text)]:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                print("STALE:", path.relative_to(ROOT).as_posix())
                ok = False
        print("PASS" if ok else "FAIL", f"player_rows={s['player_rows']} sections={s['no_injury_sections']} games={s['games_listed']}")
        return 0 if ok else 1
    SUMMARY.write_text(summary_text, encoding="utf-8")
    CSV_OUT.write_text(csv_text, encoding="utf-8")
    print(f"wrote summary and csv ({len(csv_rows)} rows); checks passed; player_rows={s['player_rows']} sections={s['no_injury_sections']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
