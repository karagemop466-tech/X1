#!/usr/bin/env python3
"""Verify data/nfl/venues_2026_week10.csv (brief row 24, session arena/5433abad-x1).

The venue values were read by hand from the "Game Info" block of each official NFL
Game Centre page (fetched 2026-11-18). This script does not use the network. It checks:

  * exactly one venue row for each of the 14 fixtures in data/nfl/schedule_2026_week10.csv,
    with the same date and the same away/home pair, and no extra or missing fixtures;
  * every row has a location, a stadium, two integer scores, a retrieved-on date and a source;
  * every link is a https://www.nfl.com/games/<slug>-2026-reg-10 Game Centre URL whose slug
    matches the away/home pair printed in the row;
  * where the schedule file already prints a final score (column `result`), the Game Centre
    score agrees with it;
  * the label_check column is recomputed and must match (no hand-edited agreement);
  * no value is blank that the brief requires to be filled.

Exit status 1 on any failure. Run from the repository root:
    python3 tools/verify_venues_w10.py
"""
import csv
import re
import sys

VENUES = "data/nfl/venues_2026_week10.csv"
SCHEDULE = "data/nfl/schedule_2026_week10.csv"
REQUIRED = ["week", "date", "away", "home", "away_score", "home_score", "game_center_slug",
            "game_center_url", "location_as_printed", "stadium_as_printed",
            "schedule_csv_venue_note", "label_check", "retrieved_on", "source"]
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*-2026-reg-10$")
URL_RE = re.compile(r"^https://www\.nfl\.com/games/([a-z0-9-]+-2026-reg-10)$")
# Schedule team abbreviations differ from the Game Centre slug's nickname, so the slug is
# checked against the printed pair through the team-name list below.
TEAM_NICK = {"WAS": "commanders", "NYG": "giants", "NE": "patriots", "DET": "lions",
             "KC": "chiefs", "ATL": "falcons", "HOU": "texans", "CLE": "browns",
             "MIN": "vikings", "GB": "packers", "MIA": "dolphins", "IND": "colts",
             "CAR": "panthers", "NO": "saints", "BUF": "bills", "NYJ": "jets",
             "JAX": "jaguars", "TEN": "titans", "LA": "rams", "AZ": "cardinals",
             "SEA": "seahawks", "LV": "raiders", "SF": "49ers", "DAL": "cowboys",
             "PIT": "steelers", "CIN": "bengals", "LAC": "chargers", "BAL": "ravens"}


def main() -> int:
    fails = []
    venues = list(csv.DictReader(open(VENUES, encoding="utf-8")))
    sched = list(csv.DictReader(open(SCHEDULE, encoding="utf-8-sig")))
    sched_pairs = {(r["away"], r["home"]): r for r in sched}

    if len(venues) != 14:
        fails.append(f"expected 14 venue rows, found {len(venues)}")
    if len(sched) != 14:
        fails.append(f"schedule file has {len(sched)} rows, expected 14")

    seen = set()
    for v in venues:
        key = (v["away"], v["home"])
        tag = f"{v['away']} @ {v['home']}"
        if key in seen:
            fails.append(f"{tag}: duplicate venue row")
        seen.add(key)
        s = sched_pairs.get(key)
        if s is None:
            fails.append(f"{tag}: not a fixture in {SCHEDULE}")
            continue
        if s["date"] != v["date"]:
            fails.append(f"{tag}: date {v['date']} != schedule {s['date']}")
        for col in REQUIRED:
            if col == "schedule_csv_venue_note":
                continue  # blank is a legitimate value here, recorded in label_check
            if not (v.get(col) or "").strip():
                fails.append(f"{tag}: blank required field {col}")
        for col in ("away_score", "home_score"):
            if not re.fullmatch(r"\d+", v.get(col, "")):
                fails.append(f"{tag}: {col} is not an integer")
        m = URL_RE.match(v["game_center_url"])
        if not m:
            fails.append(f"{tag}: not an nfl.com Game Centre URL: {v['game_center_url']}")
        elif m.group(1) != v["game_center_slug"]:
            fails.append(f"{tag}: slug column does not match URL")
        if not SLUG_RE.match(v["game_center_slug"]):
            fails.append(f"{tag}: malformed slug {v['game_center_slug']}")
        else:
            a_nick = TEAM_NICK[v["away"]]
            h_nick = TEAM_NICK[v["home"]]
            if not v["game_center_slug"].startswith(f"{a_nick}-at-{h_nick}-"):
                fails.append(f"{tag}: slug {v['game_center_slug']} does not name {a_nick} at {h_nick}")
        if s["result"].strip():
            m2 = re.fullmatch(r"(\d+)-(\d+)", s["result"].strip())
            # Schedule `result` is written away-first: "24-21" is WAS 24, NYG 21 (checked against the file).
            if m2 and (int(m2.group(1)), int(m2.group(2))) != (int(v["away_score"]), int(v["home_score"])):
                fails.append(f"{tag}: schedule result {s['result']} disagrees with Game Centre "
                             f"{v['away_score']}-{v['home_score']}")
        # Recompute the label check rather than trusting the stored value.
        note = v["schedule_csv_venue_note"].strip()
        if not note:
            expect = "blank in schedule CSV"
        elif v["stadium_as_printed"].upper() in note.upper():
            expect = "matches"
        else:
            expect = "differs from Game Centre label"
        if v["label_check"] != expect:
            fails.append(f"{tag}: label_check '{v['label_check']}' should be '{expect}'")

    missing = set(sched_pairs) - seen
    for a, h in sorted(missing):
        fails.append(f"{a} @ {h}: fixture has no venue row")

    print(f"venue rows checked : {len(venues)}")
    print(f"fixtures in schedule: {len(sched_pairs)}")
    print(f"label_check counts : " + ", ".join(
        f"{k}={sum(1 for v in venues if v['label_check'] == k)}"
        for k in sorted({v['label_check'] for v in venues})))
    if fails:
        print("FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("PASS: 14 of 14 fixtures have one official venue row; every value is sourced")
    return 0


if __name__ == "__main__":
    sys.exit(main())
