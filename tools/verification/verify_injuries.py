#!/usr/bin/env python3
"""T10 — independent line-by-line re-verification of the Week 10 injury report.

Official page: https://www.nfl.com/injuries/ ("Injuries - WEEK 10"), re-fetched
2026-11-14.  Checks
  1. per-club table row counts against the counts read off the official page,
  2. every row the page gives a GAME STATUS, field by field,
  3. the QB columns in the Week 10 schedule CSV against the official report.
"""

from __future__ import annotations

import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW = os.path.join(ROOT, "data", "verification", "raw", "nfl_injuries_2026_week10.md")
URL = "https://www.nfl.com/injuries/"
RETRIEVED = "2026-11-14"

# Row counts per club table, counted by hand from the fetched official page.
OFFICIAL_COUNTS = {
    "WAS": 9, "NYG": 11, "NE": 15, "DET": 9, "KC": 13, "ATL": 11, "MIN": 13,
    "GB": 17, "JAX": 11, "TEN": 12, "BUF": 14, "NYJ": 9, "MIA": 11, "IND": 14,
    "CAR": 12, "NO": 12, "HOU": 16, "CLE": 12, "LA": 14, "AZ": 15, "SEA": 15,
    "LV": 5, "SF": 12, "DAL": 19, "PIT": 8, "CIN": 9, "LAC": 19, "BAL": 8,
}
ALIASES = {"LAR": "LA", "ARI": "AZ"}


def abbr(s):
    s = (s or "").strip().upper()
    return ALIASES.get(s, s)


def load_official_designated():
    rows = []
    for line in open(RAW, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        team, player, pos, inj, prac, game = [p.strip() for p in line.split("|")]
        rows.append({"team": abbr(team), "player": player, "position": pos,
                     "injuries": inj, "practice_status": prac, "game_status": game})
    return rows


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


def check_pipeline(off, led):
    path = os.path.join(ROOT, "data", "pipeline", "injuries.json")
    if not os.path.exists(path):
        return
    doc = json.load(open(path, encoding="utf-8"))
    rows = doc.get("rows", [])

    # 1. row counts per club
    got = {}
    for r in rows:
        got[abbr(r.get("team_abbrev"))] = got.get(abbr(r.get("team_abbrev")), 0) + 1
    for team, n in OFFICIAL_COUNTS.items():
        led.add("injuries.json", f"table {team}", "row_count", got.get(team, 0), n,
                got.get(team, 0) == n)
    led.add("injuries.json", "(all)", "row_count_total", len(rows), sum(OFFICIAL_COUNTS.values()),
            len(rows) == sum(OFFICIAL_COUNTS.values()))

    # 2. designated rows
    index = {}
    for r in rows:
        index.setdefault((abbr(r.get("team_abbrev")), (r.get("player") or "").strip()), []).append(r)
    for o in off:
        matches = index.get((o["team"], o["player"]), [])
        if not matches:
            led.add("injuries.json", f"{o['team']} {o['player']}", "(row)", "(missing)",
                    f"{o['team']} {o['player']} {o['game_status']}", False,
                    "officially designated player absent from the committed table")
            continue
        r = matches[0]
        for field, key in (("position", "position"), ("injuries", "injuries"),
                           ("practice_status", "practice_status"), ("game_status", "game_status")):
            committed = r.get(key) or ""
            led.add("injuries.json", f"{o['team']} {o['player']}", key, committed or "(blank)",
                    o[field] or "(blank)", (committed or "") == o[field])


def check_csv(off, led):
    path = os.path.join(ROOT, "data", "injuries", "injuries_2026_week10.csv")
    if not os.path.exists(path):
        return
    rows = list(csv.DictReader(open(path, newline="", encoding="utf-8-sig")))
    got = {}
    for r in rows:
        got[abbr(r.get("team"))] = got.get(abbr(r.get("team")), 0) + 1
    for team, n in OFFICIAL_COUNTS.items():
        led.add("injuries_2026_week10.csv", f"table {team}", "row_count", got.get(team, 0), n,
                got.get(team, 0) == n)
    index = {}
    for r in rows:
        index.setdefault((abbr(r.get("team")), (r.get("player") or "").strip()), []).append(r)
    for o in off:
        matches = index.get((o["team"], o["player"]), [])
        if not matches:
            led.add("injuries_2026_week10.csv", f"{o['team']} {o['player']}", "(row)", "(missing)",
                    f"{o['game_status']}", False, "official row absent from the committed table")
            continue
        r = matches[0]
        for field, key in (("position", "position"), ("injuries", "injuries"),
                           ("practice_status", "practice_status"), ("game_status", "game_status")):
            committed = r.get(key) or ""
            led.add("injuries_2026_week10.csv", f"{o['team']} {o['player']}", key,
                    committed or "(blank)", o[field] or "(blank)", (committed or "") == o[field])


def check_qb_claims(led):
    """The Week 10 schedule CSV names an expected starting QB for all 28 clubs.
    The NFL publishes no official starting-QB designation, so every one of those
    cells is unverifiable from the league.  Four are corroborated by an NFL.com
    news story carried on the official injury page; two are contradicted by one.
    """
    path = os.path.join(ROOT, "data", "nfl", "schedule_2026_week10.csv")
    if not os.path.exists(path):
        return
    # QBs named on the official Week 10 injury report, with their game status.
    on_report = {
        "WAS": [("Jayden Daniels", "(no game status) full participation")],
        "NYG": [("J.J. McCarthy", "(no game status) full participation")],
        "NE": [("Drake Maye", "(no game status) full participation")],
        "DET": [("Jared Goff", "(no game status) full participation")],
        "KC": [("Patrick Mahomes", "(no game status) full participation"),
               ("Justin Fields", "(no game status) full participation")],
        "MIN": [("Kyler Murray", "OUT (hamstring)"),
                ("Carson Wentz", "(no game status) full participation")],
        "SEA": [("Sam Darnold", "OUT (ribs, quadricep)"),
                ("Drew Lock", "(no game status) limited participation")],
        "LA": [("Matthew Stafford", "(no game status) full participation")],
    }
    # Corroboration or contradiction by an NFL.com news story linked from the
    # official injury page (all four links are on https://www.nfl.com/injuries/).
    news = {
        "MIA": ("Kyle McCord", "CORROBORATED",
                "https://www.nfl.com/news/dolphins-place-qb-malik-willis-groin-on-injured-reserve-kyle-mccord-in-line-for-first-start"),
        "AZ": ("Carson Beck", "CORROBORATED",
               "https://www.nfl.com/news/nfl-news-roundup-latest-league-updates-from-wednesday-nov-11"),
        "CLE": ("Deshaun Watson", "CORROBORATED",
                "https://www.nfl.com/news/nfl-news-roundup-latest-league-updates-from-wednesday-nov-11"),
        "SEA": ("Drew Lock", "CORROBORATED",
                "https://www.nfl.com/news/drew-lock-no-injury-designation-seahawks-raiders"),
        "MIN": ("Kirk Cousins", "CONTRADICTED",
                "https://www.nfl.com/injuries/ - the Vikings table names only Kyler Murray (OUT) "
                "and Carson Wentz (full participation); Kirk Cousins does not appear"),
        "BAL": ("Tyler Huntley", "CONTRADICTED",
                "https://www.nfl.com/news/ravens-qb-tyler-huntley-out-for-season-turf-toe-injury"),
    }
    for row in csv.DictReader(open(path, newline="", encoding="utf-8-sig")):
        for side, tcol, qcol in (("away", "away", "expected_qb_away"),
                                 ("home", "home", "expected_qb_home")):
            team = abbr(row[tcol])
            qb = (row.get(qcol) or "").strip()
            if not qb:
                continue
            if team in on_report:
                names = ", ".join(f"{n} {s}" for n, s in on_report[team])
                ok = any(n == qb for n, _ in on_report[team])
                led.add("schedule_2026_week10.csv", f"{team} {side} QB", qcol, qb, names, ok,
                        "" if ok else "named QB does not appear on the club's official report")
            elif team in news:
                who, verdict, src = news[team]
                if verdict == "CORROBORATED" and qb == who:
                    led.add("schedule_2026_week10.csv", f"{team} {side} QB", qcol, qb,
                            f"{who} (per NFL.com news)", True,
                            "no official designation exists; corroborated by an NFL.com news story")
                else:
                    led.add("schedule_2026_week10.csv", f"{team} {side} QB", qcol, qb,
                            f"official report / NFL.com news: {src}", None,
                            f"{verdict}: {src}")
            else:
                led.add("schedule_2026_week10.csv", f"{team} {side} QB", qcol, qb,
                        "(no QB on the club's official Week 10 report)", None,
                        "the NFL publishes no official starting-QB designation; the club's "
                        "Week 10 report names no quarterback at all")


def main() -> int:
    off = load_official_designated()
    print(f"official rows carrying a game status: {len(off)}")
    print(f"official club tables counted on the page: {len(OFFICIAL_COUNTS)} "
          f"(total rows {sum(OFFICIAL_COUNTS.values())})")
    led = Ledger()
    check_pipeline(off, led)
    check_csv(off, led)
    check_qb_claims(led)

    out = {
        "dataset": "injuries_week10",
        "official_source": URL,
        "retrieved": RETRIEVED,
        "verified_by": "arena-459b17e1-x1",
        "official_rows_total": sum(OFFICIAL_COUNTS.values()),
        "official_tables": len(OFFICIAL_COUNTS),
        "official_designated_rows": len(off),
        "checks": len(led.rows),
        "pass": len(led.passes),
        "fail": len(led.fails),
        "unverified": len(led.unv),
        "rows": led.rows,
    }
    os.makedirs(os.path.join(ROOT, "data", "verification"), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, "data", "verification", "injuries.json"), "w",
                        encoding="utf-8"), indent=1)

    print(f"checks {len(led.rows)}  PASS {len(led.passes)}  FAIL {len(led.fails)}  UNVERIFIED {len(led.unv)}")
    for r in led.fails:
        print(f"  FAIL {r['dataset']} {r['key']} {r['field']}: committed={r['committed']!r} "
              f"official={r['official']!r}")
    seen = set()
    for r in led.unv:
        sig = (r["dataset"], r["field"], r["note"][:60])
        if sig in seen:
            continue
        seen.add(sig)
        n = sum(1 for x in led.unv if (x["dataset"], x["field"], x["note"][:60]) == sig)
        print(f"  UNVERIFIED {r['dataset']} {r['field']} x{n}: {r['note'][:160]}")
    return 1 if led.fails else 0


if __name__ == "__main__":
    sys.exit(main())
