#!/usr/bin/env python3
"""verify_data.py - line-by-line integrity checks for every published table.

Exits non-zero on any failure, so CI and the release gate cannot ship a bad table.
These are internal-consistency and provenance checks. They do NOT replace reading the
official page; they catch transcription and join errors mechanically.
"""
import csv
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data/nfl")
errors, warnings, checks = [], [], []


def check(cond, msg):
    if cond:
        checks.append(msg)
    else:
        errors.append(msg)


def read(name):
    path = os.path.join(D, name)
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    r = csv.DictReader(lines, delimiter="\t")
    return list(r)


STANDINGS = read("standings.tsv")
SCHED = read("schedule_week10.tsv")
INJ = read("injuries_week10.tsv")
DEPTH = read("depth_chart_pilot.tsv")
AVAIL = read("availability_derived.tsv")

TEAMS = {r["abbr"] for r in STANDINGS}
CONF = {"AFC", "NFC"}
DIVS = {
    "AFC East", "AFC North", "AFC South", "AFC West",
    "NFC East", "NFC North", "NFC South", "NFC West",
}

# ---------- standings ----------
check(len(STANDINGS) == 32, f"standings has 32 rows (found {len(STANDINGS)})")
check(len(TEAMS) == 32, f"32 unique team abbreviations (found {len(TEAMS)})")

by_div = {}
for r in STANDINGS:
    by_div.setdefault(r["division"], []).append(r)
    check(r["division"] in DIVS, f"{r['abbr']}: division '{r['division']}' is a valid NFL division name")
    check(r["conference"] in CONF, f"{r['abbr']}: conference in {{AFC,NFC}}")
    check(r["division"].startswith(r["conference"]), f"{r['abbr']}: division prefix matches conference")
    w, l, t = int(r["w"]), int(r["l"]), int(r["t"])
    g = w + l + t
    check(g <= 10, f"{r['abbr']}: games played {g} <= 10 (2026 season is in Week 10)")
    pct = float(r["pct"])
    calc = round((w + 0.5 * t) / g, 3) if g else 0.0
    check(abs(pct - calc) < 5e-4, f"{r['abbr']}: pct {pct} == (W+0.5T)/G = {calc}")
    check(int(r["diff"]) == int(r["pf"]) - int(r["pa"]), f"{r['abbr']}: NET PTS == PF - PA")
    check(r["team_url"].startswith("https://www.nfl.com/teams/"), f"{r['abbr']}: team_url is an nfl.com official page")
    for col, pat in (("home", r"^\d+-\d+-\d+$"), ("road", r"^\d+-\d+-\d+$"),
                     ("div_record", r"^\d+-\d+-\d+$"), ("conf_record", r"^\d+-\d+-\d+$")):
        check(re.match(pat, r[col]) is not None, f"{r['abbr']}: {col} '{r[col]}' is a W-L-T triple")
    check(re.match(r"^\d+[WL]$", r["streak"]) is not None, f"{r['abbr']}: streak '{r['streak']}' is <n><W|L>")

for div, rows in by_div.items():
    check(len(rows) == 4, f"{div}: exactly 4 teams (found {len(rows)})")
    ranks = sorted(int(x["div_rank"]) for x in rows)
    check(ranks == [1, 2, 3, 4], f"{div}: div_rank covers 1..4 exactly once")
# NOTE: a division's home records do NOT have to balance, because clubs play most of
# their games outside the division. Only league-wide home/road totals must balance.
# (An earlier draft asserted per-division balance; that was a wrong assumption and the
#  gate correctly rejected it. Removed rather than weakened.)

# Every decided game credits one win to the winner's venue side and one loss to the
# opponent's venue side, so the identity is home W == road L (and vice versa).
# A tie is recorded as one T on each side and never as a W or an L.
check(sum(int(r["home"].split("-")[0]) for r in STANDINGS) ==
      sum(int(r["road"].split("-")[1]) for r in STANDINGS),
      "league-wide: total home wins == total road losses")
check(sum(int(r["road"].split("-")[0]) for r in STANDINGS) ==
      sum(int(r["home"].split("-")[1]) for r in STANDINGS),
      "league-wide: total road wins == total home losses")
check(sum(int(r["w"]) for r in STANDINGS) == sum(int(r["l"]) for r in STANDINGS),
      "league-wide: total W == total L")
check(sum(int(r["t"]) for r in STANDINGS) % 2 == 0,
      "league-wide: total T is even (a tie adds one T to each club)")
check(sum(sum(int(n) for n in r["home"].split("-")) for r in STANDINGS) ==
      sum(sum(int(n) for n in r["road"].split("-")) for r in STANDINGS),
      "league-wide: home decisions == road decisions")
check(sum(int(r["div_record"].split("-")[0]) for r in STANDINGS) ==
      sum(int(r["div_record"].split("-")[1]) for r in STANDINGS),
      "league-wide: division wins == division losses")
check(sum(int(r["conf_record"].split("-")[0]) for r in STANDINGS) ==
      sum(int(r["conf_record"].split("-")[1]) for r in STANDINGS),
      "league-wide: conference wins == conference losses")

# ---------- week 10 schedule ----------
check(len(SCHED) == 14, f"week 10 has 14 games (found {len(SCHED)})")
seen = []
for g in SCHED:
    check(g["away"] in TEAMS, f"{g['game_url']}: away {g['away']} is a real team")
    check(g["home"] in TEAMS, f"{g['game_url']}: home {g['home']} is a real team")
    check(g["status"] in {"final", "scheduled"}, f"{g['game_url']}: status in {{final,scheduled}}")
    if g["status"] == "final":
        check(g["away_score"].isdigit() and g["home_score"].isdigit(),
              f"{g['game_url']}: final game has both scores")
    else:
        check(g["away_score"] == "" and g["home_score"] == "",
              f"{g['game_url']}: unplayed game leaves scores blank (no prediction)")
    seen += [g["away"], g["home"]]
check(len(seen) == len(set(seen)), "no team plays twice in week 10")
byes = sorted(TEAMS - set(seen))
check(byes == ["CHI", "DEN", "PHI", "TB"], f"bye teams == CHI,DEN,PHI,TB (found {byes})")

# ---------- injuries ----------
PRACTICE = {
    "Full Participation in Practice",
    "Limited Participation in Practice",
    "Did Not Participate In Practice",
}
STATUS = {"Out", "Doubtful", "Questionable", ""}
games = {f"{g['away']}@{g['home']}" for g in SCHED}
for r in INJ:
    check(r["game"] in games, f"{r['player']}: game '{r['game']}' is on the week 10 schedule")
    check(r["team"] in TEAMS, f"{r['player']}: team {r['team']} is a real team")
    check(r["practice_status"] in PRACTICE, f"{r['player']}: practice status is an NFL designation")
    check(r["game_status"] in STATUS, f"{r['player']}: game status is an NFL designation")
    check(r["player_url"].startswith("https://www.nfl.com/players/"),
          f"{r['player']}: player link is an nfl.com official player page")
inj_teams = {r["team"] for r in INJ}
check(inj_teams == set(seen), f"every team playing in week 10 appears in the injury report "
                              f"(missing: {sorted(set(seen) - inj_teams)})")
per_game = {}
for r in INJ:
    per_game[r["game"]] = per_game.get(r["game"], 0) + 1
check(len(per_game) == 14, f"all 14 week-10 games have injury rows (found {len(per_game)})")

# ---------- depth chart pilot ----------
check(len(DEPTH) > 0, "depth chart pilot is non-empty")
pilot = {r["team"] for r in DEPTH}
check(pilot <= TEAMS, f"depth pilot teams are real teams (bad: {sorted(pilot - TEAMS)})")
check(len(pilot) == 5, f"pilot scope is 5 clubs (found {len(pilot)}: {sorted(pilot)})")
for r in DEPTH:
    orders = [int(m.group(1)) for m in re.finditer(r"(\d+)\.\s*[^|]+", r["depth_order"])]
    check(orders == list(range(1, len(orders) + 1)),
          f"{r['team']} {r['position']}: depth order is 1..n in printed order")
    check(r["side"] in {"Offense", "Defense", "Special Teams"}, f"{r['team']}: side label valid")
    check("://" in r["source_url"], f"{r['team']} {r['position']}: has a source URL")

# ---------- derived availability ----------
check(len(AVAIL) == len(INJ), f"derived availability has one row per injury row "
                              f"({len(AVAIL)} vs {len(INJ)})")
key = lambda r: (r["game"], r["team"], r["player"])
check({key(r) for r in AVAIL} == {key(r) for r in INJ}, "derived rows match injury rows 1:1")
for r in AVAIL:
    if r["listed_starter"] == "yes":
        check(r["depth_rank"] == "1", f"{r['player']}: listed_starter=yes implies depth_rank 1")
        check(r["depth_chart_url"] != "", f"{r['player']}: starter flag carries a club chart URL")
    if r["depth_rank"]:
        check(r["listed_starter"] in {"yes", "no"}, f"{r['player']}: starter flag is yes/no")
    if r["depth_status"] == "not in pilot scope (club chart not collected)":
        check(r["depth_rank"] == "" and r["listed_starter"] == "",
              f"{r['player']}: out-of-pilot player has blank depth fields")
starters_out = [r for r in AVAIL if r["listed_starter"] == "yes" and r["game_status"] == "Out"]
warnings.append(f"INFO listed starters ruled OUT in week 10: {len(starters_out)} "
                f"({', '.join(r['team'] + ' ' + r['player'] for r in starters_out)})")

# ---------- report ----------
print(f"checks passed : {len(checks)}")
for w in warnings:
    print(w)
if errors:
    print(f"\nFAILURES ({len(errors)}):")
    for e in errors:
        print(f"  FAIL  {e}")
    sys.exit(1)
print("all integrity checks passed")
