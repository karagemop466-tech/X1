#!/usr/bin/env python3
"""T10 — independent line-by-line re-verification of the Week 10 slate.

Official page: https://www.nfl.com/schedules/2026/by-week/week-10, re-fetched
2026-11-14.  Every committed schedule table is compared row by row.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW = os.path.join(ROOT, "data", "verification", "raw", "nfl_schedule_2026_week10.md")
URL = "https://www.nfl.com/schedules/2026/by-week/week-10"
RETRIEVED = "2026-11-14"

# Official club abbreviations as used by nfl.com standings / schedule pages.
ALIASES = {"LAR": "LA", "ARI": "AZ", "BAL": "BAL"}


def abbr(s):
    s = (s or "").strip().upper()
    return ALIASES.get(s, s)


def load_official():
    games, byes = [], []
    for line in open(RAW, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if parts[0] == "BYE":
            byes.append({"team": parts[1], "record": parts[2]})
            continue
        games.append({
            "date": parts[0], "time": parts[1], "network": parts[2],
            "away": parts[3], "home": parts[4], "designation": parts[5],
            "status": parts[6] or "Scheduled",
            "away_score": parts[7] if len(parts) > 7 else "",
            "home_score": parts[8] if len(parts) > 8 else "",
        })
    return games, byes


class Ledger:
    def __init__(self):
        self.rows = []

    def add(self, dataset, key, field, committed, official, ok, note=""):
        self.rows.append({"dataset": dataset, "key": key, "field": field,
                          "committed": str(committed), "official": str(official),
                          "result": "PASS" if ok else ("UNVERIFIED" if ok is None else "FAIL"),
                          "note": note})

    @property
    def fails(self):
        return [r for r in self.rows if r["result"] == "FAIL"]

    @property
    def unv(self):
        return [r for r in self.rows if r["result"] == "UNVERIFIED"]

    @property
    def passes(self):
        return [r for r in self.rows if r["result"] == "PASS"]


def main() -> int:
    games, byes = load_official()
    led = Ledger()
    print(f"official games parsed: {len(games)}   byes: {len(byes)}")
    assert len(games) == 14, len(games)
    assert len(byes) == 4, len(byes)

    off_by_key = {f"{g['away']}@{g['home']}": g for g in games}
    off_byes = {b["team"]: b["record"] for b in byes}

    # ---------- data/nfl/schedule_week10.tsv ----------
    p = os.path.join(ROOT, "data", "nfl", "schedule_week10.tsv")
    seen = set()
    for i, line in enumerate(open(p, encoding="utf-8")):
        if line.startswith("#") or not line.strip() or line.startswith("date_et\t"):
            continue
        (date, time, away, home, network, status, ascore, hscore, note, url) = \
            (line.rstrip("\n").split("\t") + [""] * 10)[:10]
        key = f"{abbr(away)}@{abbr(home)}"
        seen.add(key)
        g = off_by_key.get(key)
        if g is None:
            led.add("schedule_week10.tsv", key, "(row)", key, "(not on official page)", False)
            continue
        led.add("schedule_week10.tsv", key, "date", date, g["date"], date == g["date"])
        led.add("schedule_week10.tsv", key, "time", time, g["time"], time == g["time"])
        led.add("schedule_week10.tsv", key, "away", away, g["away"], abbr(away) == g["away"],
                "" if abbr(away) == g["away"] else "non-official club abbreviation")
        led.add("schedule_week10.tsv", key, "home", home, g["home"], abbr(home) == g["home"],
                "" if abbr(home) == g["home"] else "non-official club abbreviation")
        if g["network"] == "(not printed)":
            led.add("schedule_week10.tsv", key, "network", network, "(not printed by the page)", None,
                    "network is not printed for this game; value cannot be confirmed official")
        else:
            led.add("schedule_week10.tsv", key, "network", network, g["network"], network == g["network"])
        led.add("schedule_week10.tsv", key, "status", status, g["status"], status.lower() == g["status"].lower())
        led.add("schedule_week10.tsv", key, "away_score", ascore, g["away_score"], ascore == g["away_score"])
        led.add("schedule_week10.tsv", key, "home_score", hscore, g["home_score"], hscore == g["home_score"])
    for key in off_by_key:
        if key not in seen:
            led.add("schedule_week10.tsv", key, "(row)", "(missing)", key, False,
                    "official game absent from the committed table")

    # ---------- data/nfl/schedule_2026_week10.csv ----------
    p = os.path.join(ROOT, "data", "nfl", "schedule_2026_week10.csv")
    if os.path.exists(p):
        seen = set()
        for row in csv.DictReader(open(p, newline="", encoding="utf-8-sig")):
            key = f"{abbr(row['away'])}@{abbr(row['home'])}"
            seen.add(key)
            g = off_by_key.get(key)
            if g is None:
                led.add("schedule_2026_week10.csv", key, "(row)", key, "(not on official page)", False)
                continue
            led.add("schedule_2026_week10.csv", key, "date", row["date"], g["date"], row["date"] == g["date"])
            led.add("schedule_2026_week10.csv", key, "et_time", row["et_time"], g["time"],
                    row["et_time"].replace(" ET", "") == g["time"],
                    "official page renders kickoff in the viewer's local time; the page's own "
                    "flexible-scheduling note states the league windows in ET")
            led.add("schedule_2026_week10.csv", key, "weekday", row["weekday"],
                    "Thursday" if g["date"].endswith("-12") else
                    ("Monday" if g["date"].endswith("-16") else "Sunday"),
                    row["weekday"] == ("Thursday" if g["date"].endswith("-12")
                                       else ("Monday" if g["date"].endswith("-16") else "Sunday")))
            if g["network"] == "(not printed)":
                led.add("schedule_2026_week10.csv", key, "tv", row["tv"], "(not printed by the page)", None,
                        "network not printed for this game on the official page")
            else:
                ok = row["tv"].replace("/ABC", "") == g["network"]
                led.add("schedule_2026_week10.csv", key, "tv", row["tv"], g["network"], ok,
                        "" if ok else "official page prints the primary network only")
            led.add("schedule_2026_week10.csv", key, "result", row["result"],
                    f"{g['away_score']}-{g['home_score']}" if g["away_score"] else "",
                    row["result"] == (f"{g['away_score']}-{g['home_score']}" if g["away_score"] else ""))
            for fld in ("market_spread_away", "market_total", "market_ml_away", "market_ml_home"):
                v = (row.get(fld) or "").strip()
                if v:
                    led.add("schedule_2026_week10.csv", key, fld, v,
                            "(no official source)", None,
                            "market price; NFL.com publishes no betting prices. Sourced in this "
                            "dataset to the nflverse community mirror, not the league.")
            for fld in ("expected_qb_away", "expected_qb_home"):
                v = (row.get(fld) or "").strip()
                if v:
                    led.add("schedule_2026_week10.csv", key, fld, v,
                            "(no official starting-QB designation)", None,
                            "the NFL does not publish an official expected starting quarterback")
        for key in off_by_key:
            if key not in seen:
                led.add("schedule_2026_week10.csv", key, "(row)", "(missing)", key, False,
                        "official game absent from the committed table")

    # ---------- data/schedule_2026_week10.csv ----------
    p = os.path.join(ROOT, "data", "schedule_2026_week10.csv")
    if os.path.exists(p):
        for row in csv.DictReader(open(p, newline="", encoding="utf-8-sig")):
            key = f"{abbr(row['away'])}@{abbr(row['home'])}"
            g = off_by_key.get(key)
            if g is None:
                led.add("schedule_2026_week10.csv", key, "(row)", key, "(not on official page)", False)
                continue
            led.add("schedule_2026_week10.csv", key, "date", row["date"], g["date"], row["date"] == g["date"])
            led.add("schedule_2026_week10.csv", key, "kickoff_et", row["kickoff_et"], g["time"],
                    row["kickoff_et"] == g["time"])
            if g["network"] == "(not printed)":
                led.add("schedule_2026_week10.csv", key, "network", row["network"],
                        "(not printed by the page)", None)
            else:
                led.add("schedule_2026_week10.csv", key, "network", row["network"], g["network"],
                        row["network"].replace("/ABC", "") == g["network"])
            led.add("schedule_2026_week10.csv", key, "status", row["status"], g["status"],
                    row["status"].strip().lower() == g["status"].strip().lower())
            led.add("schedule_2026_week10.csv", key, "away_score", row["away_score"], g["away_score"],
                    row["away_score"] == g["away_score"])
            led.add("schedule_2026_week10.csv", key, "home_score", row["home_score"], g["home_score"],
                    row["home_score"] == g["home_score"])
            gurl = f"https://www.nfl.com/games/{row['game_slug']}"
            led.add("schedule_2026_week10.csv", key, "game_url", row["game_url"], gurl,
                    row["game_url"] == gurl)
            # records pre-game are shown on the official page next to each team
            led.add("schedule_2026_week10.csv", key, "away_record_pre", row["away_record_pre"],
                    "(printed on the page)", None,
                    "pre-game record is printed by the page but not captured in this raw fetch")

    # ---------- byes ----------
    for path, tcol, rcol in (
        (os.path.join(ROOT, "data", "nfl", "week10_byes.csv"), "team", None),
        (os.path.join(ROOT, "data", "schedule_2026_week10_byes.csv"), "team_abbr", "record"),
    ):
        if not os.path.exists(path):
            continue
        got = {}
        for row in csv.DictReader(open(path, newline="", encoding="utf-8-sig")):
            got[abbr(row[tcol])] = row.get(rcol) if rcol else f"{row['W']}-{row['L']}"
        for team, rec in off_byes.items():
            led.add(os.path.basename(path), f"BYE {team}", "team",
                    team if team in got else "(missing)", team, team in got)
            if team in got and rcol:
                led.add(os.path.basename(path), f"BYE {team}", "record", got[team], rec,
                        got[team] == rec)
        for team in got:
            if team not in off_byes:
                led.add(os.path.basename(path), f"BYE {team}", "team", team, "(not on official page)",
                        False, "team is not listed on bye by the official page")

    out = {
        "dataset": "schedule_week10",
        "official_source": URL,
        "retrieved": RETRIEVED,
        "verified_by": "arena-459b17e1-x1",
        "official_games": len(games),
        "official_byes": len(byes),
        "checks": len(led.rows),
        "pass": len(led.passes),
        "fail": len(led.fails),
        "unverified": len(led.unv),
        "rows": led.rows,
    }
    os.makedirs(os.path.join(ROOT, "data", "verification"), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, "data", "verification", "schedule.json"), "w", encoding="utf-8"), indent=1)

    print(f"checks {len(led.rows)}  PASS {len(led.passes)}  FAIL {len(led.fails)}  UNVERIFIED {len(led.unv)}")
    for r in led.fails:
        print(f"  FAIL {r['dataset']} {r['key']} {r['field']}: committed={r['committed']!r} official={r['official']!r} {r['note']}")
    seen_notes = set()
    for r in led.unv:
        sig = (r["dataset"], r["field"])
        if sig in seen_notes:
            continue
        seen_notes.add(sig)
        print(f"  UNVERIFIED {r['dataset']} {r['field']} x{sum(1 for x in led.unv if (x['dataset'],x['field'])==sig)}: {r['note']}")
    return 1 if led.fails else 0


if __name__ == "__main__":
    sys.exit(main())
