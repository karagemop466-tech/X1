#!/usr/bin/env python3
"""Round-6 pack gate for the 2026-11-18 dated reads, the fixture-context store and the series.

    python3 tools/verify_2026_11_18.py            # run every check
    python3 tools/verify_2026_11_18.py --check    # same, for CI

This is the one file a reviewer should run to decide whether the 2026-11-18 pack can be believed.
It re-derives the published numbers from the retained reads rather than trusting the builder, and it
fails on the two failure modes this repository has actually hit before: a transcription that drifts
from the file it claims to describe, and a feature built on a field the source never printed.

Checks
  A  retained read files still hash to the manifest            (the pack's own immutability)
  B  the 2026-11-18 re-read of the Week 10 report matches the published injury table cell for cell
  C  the Week 11 slate is a complete, self-consistent 32-club slate
  D  every fixture-context row's arithmetic reproduces from its inputs
  E  every published venue has an official source; every blank venue says why
  F  the probe file states a verdict for the week it probed
  G  both round-6 stores are exactly what their builders write (staleness), and the delta series
     passes its own eight-check gate
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")
PACK = os.path.join(D, "verification", "2026_11_18")
sys.path.insert(0, ROOT)

OFFICIAL_HOSTS = re.compile(r"^https://([a-z0-9.-]*\.)?(nfl\.com|operations\.nfl\.com)$")
ALIAS = {"ARZ": "AZ", "LAR": "LA"}
CLUBS32 = {"ARI": "AZ", "ATL": "ATL", "BAL": "BAL", "BUF": "BUF", "CAR": "CAR", "CHI": "CHI",
           "CIN": "CIN", "CLE": "CLE", "DAL": "DAL", "DEN": "DEN", "DET": "DET", "GB": "GB",
           "HOU": "HOU", "IND": "IND", "JAX": "JAX", "KC": "KC", "LAC": "LAC", "LV": "LV",
           "MIA": "MIA", "MIN": "MIN", "NE": "NE", "NO": "NO", "NYG": "NYG", "NYJ": "NYJ",
           "PHI": "PHI", "PIT": "PIT", "SEA": "SEA", "SF": "SF", "TB": "TB", "TEN": "TEN",
           "WAS": "WAS", "LA": "LA"}


def _alias(c):
    return ALIAS.get((c or "").upper(), (c or "").upper())


def _read_tsv(path):
    header, rows, out = None, None, []
    with open(path, encoding="utf-8") as fh:
        for ln in fh.read().split("\n"):
            if not ln.strip() or ln.lstrip().startswith("#"):
                continue
            cells = ln.split("\t")
            if header is None or cells[0] in ("club",):
                header = cells
                continue
            out.append(dict(zip(header, cells)))
    return out


PRACTICE_EXPAND = {"full": "Full Participation in Practice",
                   "full participation": "Full Participation in Practice",
                   "limited": "Limited Participation in Practice",
                   "dnp": "Did Not Participate In Practice"}


def norm_practice(value: str) -> str:
    v = (value or "").strip()
    return PRACTICE_EXPAND.get(v.lower(), v)


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def main() -> int:
    fails, notes = [], []

    # ---- A: manifest -------------------------------------------------------
    man = json.load(open(os.path.join(PACK, "MANIFEST.json"), encoding="utf-8"))
    checked = 0
    for entry in man["files"]:
        p = os.path.join(ROOT, entry["path"])
        if not os.path.exists(p):
            fails.append(f"A: retained read missing: {entry['path']}")
            continue
        got = sha(p)
        if got != entry["sha256"]:
            fails.append(f"A: {entry['path']} hashes {got[:12]} != manifest {entry['sha256'][:12]}")
        else:
            checked += 1
    notes.append(f"A: {checked}/{len(man['files'])} retained read files reproduce their manifest hash")

    # ---- B: the re-read vs the published table, and the published copies vs each other
    #
    # Three files carry the same 347-row Week 10 report in three vocabularies: the console table
    # abbreviates the practice column ("Full"), the data/injuries copy prints the page's wording and
    # links each player, and the root copy adds game columns. Cells are compared after expanding the
    # known abbreviations, so a difference left over is a content drift and not a spelling.
    reread = _read_tsv(os.path.join(PACK, "week10_rows_reread_2026-11-18.tsv"))
    console = {(_alias(r["TEAM"]), r["PLAYER"]): r for r in csv.DictReader(
        open(os.path.join(D, "console", "injuries_week10.csv"), encoding="utf-8"))}
    snap = {(_alias(r["team"]), r["player"]): r for r in csv.DictReader(
        open(os.path.join(D, "injuries", "injuries_2026_week10.csv"), encoding="utf-8"))}
    root = {(_alias(r["team_abbr"]), r["player"]): r for r in csv.DictReader(
        open(os.path.join(D, "injuries_2026_week10.csv"), encoding="utf-8"))}

    mism, cells = [], 0
    for r in reread:
        k = (_alias(r["team_abbr"]), r["player"])
        for name, table, cols in (("console", console, ("POS", "INJURY", "PRACTICE", "GAMESTATUS")),
                                  ("data/injuries", snap, ("position", "injuries",
                                                           "practice_status", "game_status")),
                                  ("root", root, ("position", "injury", "practice_status",
                                                  "game_status"))):
            if k not in table:
                mism.append(f"{name}: {r['team_abbr']} {r['player']} is on the 2026-11-18 read but "
                            f"absent from that published copy")
                continue
            got = table[k]
            for mine, theirs in zip((r["position"], r["injury"], r["practice_status"], r["game_status"]),
                                    (got[c] for c in cols)):
                cells += 1
                if (mine or "").strip() != norm_practice(theirs).strip():
                    mism.append(f"{name}: {r['team_abbr']} {r['player']} "
                                f"{(mine or '(blank)')!r} vs published {(theirs or '(blank)')!r}")
        cells += 1
        slug = (snap.get(k, {}).get("player_page", "") or "").rstrip("/").split("/")[-1]
        if k in snap and slug != r["player_slug"]:
            mism.append(f"data/injuries: {r['team_abbr']} {r['player']} player link: read "
                        f"{r['player_slug']} vs published {slug}")
    if mism:
        fails.append(f"B: {len(mism)} cell(s) disagree between the 2026-11-18 read and the published tables")
        for m in mism[:10]:
            fails.append("   " + m)
    games = {}
    for r in reread:
        games.setdefault(r["game"], set()).add(r["team_abbr"].upper())

    # the three copies must agree with each other, cell for cell, once the vocabulary is normalised
    raw = {
        "console": {(r["TEAM"].upper(), r["PLAYER"]) for r in csv.DictReader(
            open(os.path.join(D, "console", "injuries_week10.csv"), encoding="utf-8"))},
        "data/injuries": {(r["team"].upper(), r["player"]) for r in csv.DictReader(
            open(os.path.join(D, "injuries", "injuries_2026_week10.csv"), encoding="utf-8"))},
        "root": {(r["team_abbr"].upper(), r["player"]) for r in csv.DictReader(
            open(os.path.join(D, "injuries_2026_week10.csv"), encoding="utf-8"))},
    }
    # rows that exist in one copy only because the club is spelled two ways on the same site
    alias_cost = len(raw["console"] ^ raw["data/injuries"]) + len(raw["console"] ^ raw["root"])
    drift = []
    for k in sorted(console):
        if k not in snap or k not in root:
            drift.append((k, "missing from a copy"))
            continue
        a = (norm_practice(console[k]["PRACTICE"]), console[k]["GAMESTATUS"], console[k]["POS"])
        b = (norm_practice(snap[k]["practice_status"]), snap[k]["game_status"], snap[k]["position"])
        c = (norm_practice(root[k]["practice_status"]), root[k]["game_status"], root[k]["position"])
        if not (a == b == c):
            drift.append((k, f"{a} / {b} / {c}"))
    if drift:
        fails.append(f"B2: the three published copies of the Week 10 table disagree on {len(drift)} "
                     f"player rows (first: {drift[0]})")
    notes.append(f"B: {len(reread)} rows re-read on 2026-11-18 across {len(games)} games "
                 f"({', '.join(sorted(games))}); {cells} cells compared against all three copies, "
                 f"{len(mism)} mismatches")
    notes.append(f"B2: {len(console)} rows in each published copy; {alias_cost} row-keys differ "
                 f"between copies on the club spelling alone (the LA/LAR split, flag F-15); after the "
                 f"join alias and the practice vocabulary are normalised, {len(drift)} rows still "
                 f"disagree")

    # ---- C: the Week 11 slate is a complete 32-club slate -------------------
    slate = _read_tsv(os.path.join(PACK, "week11_slate_2026-11-18.tsv"))
    games11 = [r for r in slate if r.get("game_url")]
    byes11 = [r for r in slate if r.get("club") and not r.get("game_url")]
    in_games = {_alias(r["away"]) for r in games11} | {_alias(r["home"]) for r in games11}
    in_byes = {_alias(r["club"]) for r in byes11}
    if len(games11) * 2 + len(byes11) != 32:
        fails.append(f"C: slate has {len(games11)} games and {len(byes11)} byes, "
                     f"{len(games11) * 2 + len(byes11)} club slots, not 32")
    if in_games & in_byes:
        fails.append(f"C: a club is both scheduled and on bye: {sorted(in_games & in_byes)}")
    if (in_games | in_byes) != set(CLUBS32.values()):
        fails.append(f"C: slate clubs do not cover the 32: missing {sorted(set(CLUBS32.values()) - (in_games | in_byes))}, "
                     f"unknown {sorted((in_games | in_byes) - set(CLUBS32.values()))}")
    dupes = {}
    for r in games11:
        for c in (_alias(r["away"]), _alias(r["home"])):
            dupes[c] = dupes.get(c, 0) + 1
    if [c for c, n in dupes.items() if n > 1]:
        fails.append(f"C: a club appears twice in the Week 11 slate: {dupes}")
    for r in games11:
        d0 = dt.date.fromisoformat(r["kickoff_date_local"])
        if d0.strftime("%A") not in ("Thursday", "Sunday", "Monday"):
            fails.append(f"C: {r['game_url']} kickoff date {r['kickoff_date_local']} is a {d0.strftime('%A')}")
        if not re.match(r"^\d{1,2}:\d{2} (AM|PM)$", r["kickoff_time_local"]):
            fails.append(f"C: {r['game_url']} kickoff time is not printed as a clock time: {r['kickoff_time_local']!r}")
        if not OFFICIAL_HOSTS.match(r["game_url"].split("/games/")[0]):
            fails.append(f"C: {r['game_url']} is not on an official host")
    notes.append(f"C: {len(games11)} fixtures + {len(byes11)} byes = 32 clubs, each appearing once; "
                 f"every fixture links its official game centre")

    # ---- D: fixture-context arithmetic --------------------------------------
    fx = list(csv.DictReader(open(os.path.join(D, "fixtures", "fixture_context_2026.csv"),
                                  encoding="utf-8")))
    bad = 0
    for r in fx:
        if r["status_this_week"] == "game" and r["kickoff_date"]:
            d0 = dt.date.fromisoformat(r["kickoff_date"])
            if d0.strftime("%A") != r["day_of_week"]:
                fails.append(f"D: {r['week']} {r['club']} day_of_week {r['day_of_week']} != {d0.strftime('%A')}")
                bad += 1
            if r["kickoff_utc"]:
                t = dt.datetime.strptime(r["kickoff_time_as_printed"].replace(" ", ""), "%I:%M%p")
                want = (dt.datetime.combine(d0, dt.time(t.hour, t.minute), tzinfo=dt.timezone.utc)
                        + dt.timedelta(hours=5))
                got = r["kickoff_utc"]
                if want.strftime("%Y-%m-%dT%H:%MZ") != got:
                    fails.append(f"D: {r['week']} {r['club']} kickoff_utc {got} != recomputed "
                                 f"{want.strftime('%Y-%m-%dT%H:%MZ')}")
                    bad += 1
        if r["rest_days"]:
            if not r["prior_fixture_date"]:
                fails.append(f"D: {r['week']} {r['club']} has rest_days without a prior fixture date")
                bad += 1
            else:
                want = (dt.date.fromisoformat(r["kickoff_date"])
                        - dt.date.fromisoformat(r["prior_fixture_date"])).days
                if want != int(r["rest_days"]):
                    fails.append(f"D: {r['week']} {r['club']} rest_days {r['rest_days']} != recomputed {want}")
                    bad += 1
        if r["rest_days"] and r["short_week"] != ("yes" if int(r["rest_days"]) <= 4 else "no"):
            fails.append(f"D: {r['week']} {r['club']} short_week disagrees with rest_days")
            bad += 1
    per_week = {}
    for r in fx:
        per_week.setdefault(r["week"], set()).add(r["club"])
    for wk, clubs in per_week.items():
        if clubs != set(CLUBS32.values()):
            fails.append(f"D: week {wk} covers {len(clubs)} clubs, not 32")
    notes.append(f"D: {len(fx)} fixture rows, {bad} arithmetic faults; both weeks cover all 32 clubs "
                 f"once each")

    # ---- E: venue traceability ----------------------------------------------
    no_venue = with_venue = 0
    for r in fx:
        v, vs = r["venue_as_printed"].strip(), r["venue_source"].strip()
        if v:
            with_venue += 1
            base = vs.split("/games/")[0].split("/programs")[0]
            if not OFFICIAL_HOSTS.match(base):
                fails.append(f"E: {r['week']} {r['club']} venue source is not official: {vs}")
        else:
            no_venue += 1
            if "no source" not in vs and "no venue" not in v and "no fixture" not in vs:
                if not re.search(r"R-24|no source|blank", r["flags"] + vs, re.I):
                    fails.append(f"E: {r['week']} {r['club']} has a blank venue with no stated reason")
    notes.append(f"E: {with_venue} rows carry a venue traced to an official source; {no_venue} blank "
                 f"rows each state why")

    # ---- F: the probe -------------------------------------------------------
    probe = _read_tsv(os.path.join(PACK, "injury_probe_2026-11-18.tsv"))
    if not probe:
        fails.append("F: no probe row retained")
    for r in probe:
        if not r.get("verdict"):
            fails.append(f"F: probe {r.get('probe_utc')} publishes no verdict")
        if r.get("week_attempted") and "Week 11" in r["week_attempted"]:
            if "no Week 11 report" not in r["verdict"]:
                fails.append("F: the Week 11 probe's verdict does not say what was absent")
    hours = None
    for r in probe:
        if r.get("first_kickoff_utc") and r["first_kickoff_utc"][:2].isdigit():
            ko = dt.datetime.fromisoformat(r["first_kickoff_utc"].replace("Z", "+00:00"))
            rd = dt.datetime.fromisoformat(r["probe_utc"].replace("Z", "+00:00"))
            hours = round((ko - rd).total_seconds() / 3600, 1)
            if abs(hours - float(r["hours_from_probe_to_first_kickoff"])) > 0.15:
                fails.append(f"F: probe says {r['hours_from_probe_to_first_kickoff']} h to kickoff, "
                             f"recomputed {hours}")
    notes.append(f"F: {len(probe)} probe row(s); {hours} h from probe to the week's first kickoff")

    # ---- G: staleness of both stores + the series gate ----------------------
    for cmd in (["python3", "tools/build_fixture_context.py", "--check"],
                ["python3", "tools/build_availability_series.py", "--check"],
                ["python3", "tools/verify_availability_series.py"]):
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            fails.append("G: " + " ".join(cmd[1:]) + " failed: " + (r.stdout + r.stderr).strip()[-400:])
    notes.append("G: both stores reproduce byte for byte; the delta series passes its own eight checks")

    print(f"[round-6 pack] {len(notes)} checks run")
    for n in notes:
        print("   " + n)
    if fails:
        print("\nFAIL")
        for f in fails:
            print("  - " + f)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
