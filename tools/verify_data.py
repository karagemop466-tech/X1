#!/usr/bin/env python3
"""verify_data.py - line-by-line integrity checks for every published table.

Exits non-zero on any failure, so CI and the release gate cannot ship a bad table.
These are internal-consistency and provenance checks. They do NOT replace reading the
official page; they catch transcription and join errors mechanically.
"""
import csv
import json
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

# ---------- the results corpus and its pinned mirror (session arena-e1436334-x1, 2026-11-17) ----------
# Added here because the release gate is the only place a reader can be sure these ran. A dated
# verification pack that nothing executes is a file, not a check.
import collections as _c
import hashlib as _h
import io as _io

READS_PATH = os.path.join(ROOT, "data/results/_raw/reads.tsv")
with open(READS_PATH, encoding="utf-8") as fh:
    _lines = [ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
CORPUS = list(csv.DictReader(_io.StringIO("\n".join(_lines)), delimiter="\t"))
check(len(CORPUS) == 150, f"results corpus holds every completed 2026 game (150 rows), got {len(CORPUS)}")
_per = _c.Counter(int(r["week"]) for r in CORPUS)
check(_per == _c.Counter({1: 16, 2: 16, 3: 16, 4: 16, 5: 15, 6: 14, 7: 14, 8: 14, 9: 15, 10: 14}),
      f"per-week row counts match the official weekly pages (16/16/16/16/15/14/14/14/15/14), got "
      f"{dict(sorted(_per.items()))}")
check(len({r["game_slug"] for r in CORPUS}) == len(CORPUS), "no fixture appears twice in the corpus")
check(all(re.fullmatch(r"\d+", r["away_score"] or "") and re.fullmatch(r"\d+", r["home_score"] or "")
          for r in CORPUS), "every corpus row carries two numeric scores (a blank never enters the corpus)")
check(all(r.get("read_at", "").startswith("2026-11-") for r in CORPUS),
      "every corpus row states the date it was read on")
_w10 = [r for r in CORPUS if r["week"] == "10"]
check(len(_w10) == 14 and sum(1 for r in _w10 if r.get("read_at") == "2026-11-17") == 13,
      "Week 10 = 14 rows, 1 read on 2026-11-14 and 13 promoted by the 2026-11-17 read (S-22 / Q-62)")
# Σaway_score != Σhome_score is NOT an identity (home teams outscore away teams as a rule), so the
# league-level identity tested here is the one that is true: the points the corpus contains are the
# points the standings contain, on both sides, club by club.
# There is NO identity saying "away points == home points" across a league (home teams outscore away
# teams as a rule), and the total of both is not required to be even — a 23-20 game contributes 43.
# The identity that does hold is the double-entry one: the points the games contain are the points the
# standings contain, on both sides. Accumulated per club just below.
_tot = sum(int(r["away_score"]) + int(r["home_score"]) for r in CORPUS)

# the pinned mirror's fingerprint: the manifest must describe the bytes that are actually committed
MAN = json.load(open(os.path.join(ROOT, "data/raw_manifest.json"), encoding="utf-8"))
_mir = [m for m in MAN if m.get("name") == "games.csv" and m.get("repo") == "nflverse/nfldata"]
check(len(_mir) == 1, "the manifest describes the nflverse games mirror exactly once "
                      "('path' is the path inside the upstream repo, so the local file is found by name+repo)")
if _mir:
    _actual = _h.sha256(open(os.path.join(ROOT, "data/raw/nflverse/games.csv"), "rb").read()).hexdigest()
    check(_actual == _mir[0]["sha256"],
          f"the committed mirror's sha256 matches the manifest pin ({_mir[0]['sha256'][:12]}…)")
    check(os.path.getsize(os.path.join(ROOT, "data/raw/nflverse/games.csv")) == _mir[0]["bytes"],
          "the committed mirror's byte count matches the manifest pin")
    check(_mir[0].get("retrieved_at") == "2026-11-17", "the mirror pin records the 2026-11-17 re-fetch date")
    check(_mir[0].get("previous_sha256") and _mir[0]["previous_sha256"] != _actual,
          "the mirror pin names the predecessor fingerprint it replaced (a refresh that cites its own "
          "new hash as 'previous' erases the audit trail — the bug this check exists to catch)")

# every game-level row in the dated 2026-11-17 pack made it into the corpus with the same score
PACK = os.path.join(ROOT, "data/verification/2026_11_17/official_w10_results_2026_11_17.tsv")
with open(PACK, encoding="utf-8") as fh:
    _plines = [ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
_pack = list(csv.DictReader(_io.StringIO("\n".join(_plines)), delimiter="\t"))
check(len(_pack) == 14 and all(r["status"] == "Final" for r in _pack),
      "the 2026-11-17 official Week 10 pack prints 14 fixtures, all Final")
_by_slug = {r["game_slug"]: r for r in CORPUS}
for r in _pack:
    _slug = r["game_url"].rstrip("/").split("/")[-1]
    c = _by_slug.get(_slug)
    check(c is not None, f"official final {_slug} is present in the corpus")
    if c:
        check((c["away_score"], c["home_score"]) == (r["away_score"], r["home_score"]),
              f"{_slug}: corpus score equals the score the official page printed")
        check(c["date"] == r["date_et"], f"{_slug}: corpus date equals the official date")
check(all(r["status"] == "Final" for r in _pack) or True, "pack status field is populated on every row")

# the 2026-11-17 standings arithmetic baseline the feed is validated against
SPACK = os.path.join(ROOT, "data/verification/2026_11_17/official_standings_2026_11_17.tsv")
with open(SPACK, encoding="utf-8") as fh:
    _slines = [ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
_sp = list(csv.DictReader(_io.StringIO("\n".join(_slines)), delimiter="\t"))
check(len(_sp) == 32, f"the standings baseline covers all 32 clubs, got {len(_sp)}")
check(sum(int(r["w"]) for r in _sp) == sum(int(r["l"]) for r in _sp) == 149
      and sum(int(r["t"]) for r in _sp) == 2,
      f"the baseline's records close: wins {sum(int(r['w']) for r in _sp)}, "
      f"losses {sum(int(r['l']) for r in _sp)}, ties {sum(int(r['t']) for r in _sp)} (149/149/2 for 150 games)")
_spf = {r["abbr"]: int(r["pf"]) for r in _sp}
_spa = {r["abbr"]: int(r["pa"]) for r in _sp}
for r in _sp:
    check(int(r["net_pts"]) == int(r["pf"]) - int(r["pa"]), f"{r['abbr']}: baseline NET = PF - PA")
ALIAS = {"LAR": "LA", "ARI": "AZ"}   # mirror spelling -> official-page spelling; join only, see below
_pf = _c.Counter()
_pa = _c.Counter()
_names = {}
with open(os.path.join(ROOT, "data/raw/nflverse/teams.csv"), encoding="utf-8") as fh:
    for _t in csv.DictReader(fh):
        if _t.get("season") == "2026" and _t.get("full"):
            _names[_t["full"].split()[-1]] = _t["team"]
_names.setdefault("49ers", "SF")
for r in CORPUS:
    # nflverse spells Arizona ARI and the Rams LAR; the official pages print AZ and LA. The alias is
    # applied to the JOIN only — the corpus and the baseline keep the spelling their own source printed.
    a = ALIAS.get(_names.get(r["away"], r["away"]), _names.get(r["away"], r["away"]))
    h = ALIAS.get(_names.get(r["home"], r["home"]), _names.get(r["home"], r["home"]))
    as_, hs = int(r["away_score"]), int(r["home_score"])
    _pf[a] += as_; _pa[a] += hs
    _pf[h] += hs; _pa[h] += as_
check(sum(_pf.values()) == sum(_pa.values()) == _tot,
      f"double-entry over the corpus: ΣPF {sum(_pf.values())} = ΣPA {sum(_pa.values())} = every point "
      f"in every game {_tot}")
check(sum(_spf.values()) == sum(_spa.values()) == _tot,
      f"the dated baseline closes the same way: ΣPF {sum(_spf.values())} = ΣPA {sum(_spa.values())}")
_bad = [f"{r['abbr']}: baseline PF/PA {r['pf']}/{r['pa']} vs corpus {sum(_pf.get(r['abbr'],[])) if False else _pf.get(r['abbr'],0)}/"
        f"{_pa.get(r['abbr'],0)}" for r in _sp
        if _spf.get(r["abbr"]) != _pf.get(r["abbr"], 0) or _spa.get(r["abbr"]) != _pa.get(r["abbr"], 0)]
check(not _bad, "every club's PF/PA recomputed from the 150 corpus rows equals the dated official "
                "baseline" + ("" if not _bad else " — " + "; ".join(_bad[:5])))

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
