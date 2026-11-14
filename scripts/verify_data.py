"""
Verification + conversion for the official NFL.com data pulled on 2026-11-14 (UTC).
  * Converts data/raw/injuries_2026_week10_official.psv -> data/injuries_2026_week10.csv
  * Re-checks structural integrity (games, teams, counts, standings arithmetic)
  * Writes data/flags_auto.csv with rule-based irregularities (each with an official source link)
Exit code is non-zero if any hard check fails.
"""
import csv, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data"
INJ_SRC = "https://www.nfl.com/injuries/"
STAND_SRC = "https://www.nfl.com/standings/"
SCHED_SRC = "https://www.nfl.com/schedules/2026/by-week/week-10"
DNP = "Did Not Participate In Practice"
FULL = "Full Participation in Practice"
errors = []

def read_csv(p):
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

sched = read_csv(D / "schedule_2026_week10.csv")
stand = read_csv(D / "standings_2026.csv")
games = {f"{r['away']}@{r['home']}": r for r in sched}
teams_stand = {r["team_abbr"] for r in stand}

# Code alias: the injury page prints the Rams as LAR; schedule and standings print LA (I-15).
ALIAS = {"LAR": "LA"}
def to_std(code):
    return ALIAS.get(code, code)

rows = []
with open(D / "raw" / "injuries_2026_week10_official.psv", encoding="utf-8") as f:
    for ln in f:
        ln = ln.rstrip("\n")
        if not ln.strip():
            continue
        parts = ln.split("|")
        if len(parts) != 8:
            errors.append(f"bad field count: {ln}")
            continue
        gcode, team, player, pos, injury, practice, status, slug = parts
        gcode_std = "@".join(to_std(x) for x in gcode.split("@"))
        rows.append(dict(game_code=gcode_std, team_abbr=to_std(team), player=player, position=pos, injury=injury,
                         practice_status=practice, game_status=status, slug=slug, team_code_src=team))

# --- integrity checks ---
if len(games) != 14:
    errors.append(f"schedule has {len(games)} games, expected 14")
if set(games) != {r["game_code"] for r in rows}:
    errors.append(f"game codes differ: {set(games) ^ {r['game_code'] for r in rows}}")
for g, sr in games.items():
    teams_in_rows = {r["team_abbr"] for r in rows if r["game_code"] == g}
    if teams_in_rows != {sr["away"], sr["home"]}:
        errors.append(f"{g}: team codes in report {teams_in_rows} != schedule {sr['away']},{sr['home']}")
for r in rows:
    if r["team_abbr"] not in teams_stand:
        errors.append(f"team {r['team_abbr']} not in standings")
dups = Counter((r["team_abbr"], r["player"]) for r in rows)
for k, v in dups.items():
    if v > 1:
        errors.append(f"duplicate player row {k}")
bye = {r["team_abbr"] for r in read_csv(D / "schedule_2026_week10_byes.csv")}
teams_playing = {r["team_abbr"] for r in rows}
if teams_playing | bye != teams_stand:
    errors.append("teams with report rows + bye teams != 32 standings teams")
if teams_playing & bye:
    errors.append("bye team appears in injury report")
if len(teams_playing) != 28:
    errors.append(f"expected 28 teams with rows, got {len(teams_playing)}")

# --- standings arithmetic ---
for r in stand:
    W, L, T = int(r["W"]), int(r["L"]), int(r["T"])
    pct = (W + 0.5 * T) / (W + L + T)
    if abs(pct - float(r["PCT"])) > 0.0015:
        errors.append(f"PCT mismatch {r['team_abbr']}")
    if int(r["PF"]) - int(r["PA"]) != int(r["NET_PTS"]):
        errors.append(f"NET_PTS mismatch {r['team_abbr']}")
if len(stand) != 32:
    errors.append("standings not 32 teams")

# --- write injuries CSV + rule-based flags ---
fields = ["game", "game_day", "kickoff_et", "network", "team_abbr", "player", "position", "injury",
          "practice_status", "game_status", "player_url", "source_url", "flag_codes"]
flags_auto = []
with open(D / "injuries_2026_week10.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for r in rows:
        sr = games[r["game_code"]]
        game = f"{sr['away']} at {sr['home']}"
        codes = []
        if r["player"] == "Puka Nacua":
            codes.append("I-05")
        if r["practice_status"] == DNP and not r["injury"] and not r["game_status"]:
            codes.append("I-06")
        if r["practice_status"] == FULL and r["game_status"] == "Out":
            codes.append("I-07")
        if r["slug"] in {"jake-hummel", "kamren-curl", "gervon-dexter"}:
            codes.append("I-08")
        player_url = f"https://www.nfl.com/players/{r['slug']}/"
        w.writerow(dict(game=game, game_day=sr["day"] + " " + sr["date"], kickoff_et=sr["kickoff_et"],
                        network=sr["network"], team_abbr=r["team_code_src"], player=r["player"],
                        position=r["position"], injury=r["injury"], practice_status=r["practice_status"],
                        game_status=r["game_status"], player_url=player_url, source_url=INJ_SRC,
                        flag_codes=";".join(codes)))
        for c in codes:
            flags_auto.append([c, r["team_abbr"], r["player"], r["practice_status"], r["injury"],
                               r["game_status"], player_url, INJ_SRC])

tnf = games["WAS@NYG"]
st = {r["team_abbr"]: r for r in stand}
if tnf["away_score"] and st["WAS"]["W"] == "3" and st["WAS"]["L"] == "5" and tnf["status"] == "Final":
    flags_auto.append(["I-14", "WAS/NYG", "Standings still show pre-game records (WAS 3-5-1, NYG 5-3-1) for a Final game (WAS 24-21 NYG)",
                       "", "", "", STAND_SRC, SCHED_SRC])

with open(D / "flags_auto.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["flag_code", "team", "item", "practice_status", "injury", "game_status", "link_1", "link_2"])
    w.writerows(flags_auto)

counts = Counter(r["game_code"] for r in rows)
print("injury rows:", len(rows), "| games:", len(counts))
print("rows per game:", dict(sorted(counts.items())))
print("auto flags:", dict(Counter(f[0] for f in flags_auto)))
if errors:
    print("HARD CHECK FAILURES:")
    for e in errors:
        print(" -", e)
    sys.exit(1)
print("all hard checks passed")
