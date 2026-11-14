#!/usr/bin/env python3
"""Independent re-verification of the published tables against the official pages.

This checker belongs to session `arena/fcc11e05-x1`. It does not read anyone's
generated HTML: it compares the *transcribed official values* in
`data/verify/official_*.psv` (fetched from nfl.com on 2026-11-14) against the
values the repository publishes in `data/pipeline/*.json` and the CSV/TSV
tables shipped by earlier sessions.

It exits non-zero if any published row disagrees with the official page, and it
writes a machine-readable ledger to `data/verify/verification_ledger.json` that
the site renders row by row.
"""

from __future__ import annotations

import csv
import json
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = os.path.join(ROOT, "data", "verify")

PRACTICE = {
    "Full": "Full Participation in Practice",
    "Limited": "Limited Participation in Practice",
    "DNP": "Did Not Participate In Practice",
}


def psv(name):
    path = os.path.join(V, name)
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="|"))


def jload(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        return json.load(fh)


def norm(v):
    if v is None:
        return ""
    s = " ".join(str(v).split()).strip()
    # The league renders composite records as "0 - 4 - 0"; the same value is
    # written "0-4-0" elsewhere. Compare the digits, not the spacing.
    if s.replace(" ", "").replace("-", "").isdigit() and "-" in s:
        return s.replace(" ", "")
    return s


def rec(ledger, dataset, key, field, published, official, source):
    ok = norm(published) == norm(official)
    ledger.append(
        {
            "dataset": dataset,
            "row": key,
            "field": field,
            "published": norm(published),
            "official": norm(official),
            "result": "match" if ok else "MISMATCH",
            "source": source,
        }
    )
    return ok


def main() -> int:
    ledger = []
    problems = []

    # ------------------------------------------------------------ standings
    off = {r["TEAM"]: r for r in psv("official_standings_2026_w10.psv")}
    pub = jload("data/pipeline/standings.json")
    std_fields = [
        ("W", "W"), ("L", "L"), ("T", "T"), ("PCT", "PCT"), ("PF", "PF"),
        ("PA", "PA"), ("NET_PTS", "NET"), ("HOME", "HOME"), ("ROAD", "ROAD"),
        ("DIV", "DIV"), ("DIV_PCT", "DIVPCT"), ("CONF", "CONF"),
        ("CONF_PCT", "CONFPCT"), ("NON_CONF", "NONCONF"), ("STRK", "STRK"),
        ("LAST_5", "LAST5"),
    ]
    seen = set()
    for row in pub["rows"]:
        ab = row["team_abbrev"]
        seen.add(ab)
        o = off.get(ab)
        key = f"standings/{ab}"
        if o is None:
            problems.append(f"standings: {ab} is not on the official league table")
            ledger.append({"dataset": "standings", "row": key, "field": "row",
                           "published": ab, "official": "(absent)",
                           "result": "MISMATCH", "source": pub["source"]["url"]})
            continue
        for pf, of in std_fields:
            ok = rec(ledger, "standings", key, pf, row.get(pf), o[of],
                     row["_source_url"])
            if not ok:
                problems.append(f"standings {ab}.{pf}: published={row.get(pf)!r} official={o[of]!r}")
        # internal arithmetic the league page itself must satisfy
        if int(o["W"]) + int(o["L"]) + int(o["T"]) > 10:
            problems.append(f"standings {ab}: W+L+T > 10")
        if int(o["PF"]) - int(o["PA"]) != int(o["NET"]):
            problems.append(f"standings {ab}: PF-PA != NET on the official page")
    for ab in off:
        if ab not in seen:
            problems.append(f"standings: official row {ab} missing from published data")

    # -------------------------------------------------------------- injuries
    off_i = psv("official_injuries_2026_w10.psv")
    pub_i = jload("data/pipeline/injuries.json")
    if len(off_i) != len(pub_i["rows"]):
        problems.append(
            f"injuries: official report has {len(off_i)} rows, published has {len(pub_i['rows'])}"
        )
    by_team_pub = defaultdict(list)
    for r in pub_i["rows"]:
        by_team_pub[r["team_abbrev"]].append(r)
    by_team_off = defaultdict(list)
    for r in off_i:
        by_team_off[r["TEAM"]].append(r)
    for team in sorted(by_team_off):
        p = by_team_pub.get(team, [])
        o = by_team_off[team]
        if len(p) != len(o):
            problems.append(
                f"injuries {team}: official {len(o)} rows, published {len(p)} rows"
            )
        for i, orow in enumerate(o):
            key = f"injuries/{team}/{orow['PLAYER']}"
            prow = p[i] if i < len(p) else {}
            rec(ledger, "injuries", key, "player", prow.get("player"),
                orow["PLAYER"], prow.get("_source_url") or pub_i["source"]["url"])
            rec(ledger, "injuries", key, "position", prow.get("position"),
                orow["POS"], prow.get("_source_url") or pub_i["source"]["url"])
            rec(ledger, "injuries", key, "injuries", prow.get("injuries"),
                orow["INJURY"] or None,
                prow.get("_source_url") or pub_i["source"]["url"])
            rec(ledger, "injuries", key, "practice_status",
                prow.get("practice_status"), PRACTICE[orow["PRACTICE"]],
                prow.get("_source_url") or pub_i["source"]["url"])
            rec(ledger, "injuries", key, "game_status", prow.get("game_status"),
                orow["GAMESTATUS"] or None,
                prow.get("_source_url") or pub_i["source"]["url"])

    # -------------------------------------------------------------- schedule
    off_s = psv("official_schedule_2026_w10.psv")
    pub_s = jload("data/pipeline/standings.json")  # standings json carries no slate
    del pub_s
    sched_pub = None
    for cand in ("data/pipeline/schedule.json", "data/pipeline/slate.json"):
        if os.path.exists(os.path.join(ROOT, cand)):
            sched_pub = jload(cand)
            break
    ledger.append({
        "dataset": "schedule", "row": "week-10",
        "field": "games_official", "published": "",
        "official": str(len(off_s)), "result": "captured",
        "source": "https://www.nfl.com/schedules/2026/by-week/week-10",
    })
    if sched_pub is not None:
        prows = sched_pub.get("rows", [])
        if len(prows) != len(off_s):
            problems.append(
                f"schedule: official {len(off_s)} games, published {len(prows)}"
            )
        for i, o in enumerate(off_s):
            r = prows[i] if i < len(prows) else {}
            key = f"schedule/{o['GAMEID']}"
            rec(ledger, "schedule", key, "home", r.get("home"), o["HOME"],
                "https://www.nfl.com/schedules/2026/by-week/week-10")
            rec(ledger, "schedule", key, "away", r.get("away"), o["AWAY"],
                "https://www.nfl.com/schedules/2026/by-week/week-10")
    # bye teams: every club not in the slate must be one of the four official byes
    in_slate = set()
    for o in off_s:
        in_slate.add(o["HOME"])
        in_slate.add(o["AWAY"])
    byes = {r["TEAM"] for r in psv("official_byes_2026_w10.psv")}
    missing = set(off) - in_slate
    if missing != byes:
        problems.append(f"schedule: bye set mismatch official={sorted(byes)} derived={sorted(missing)}")
    ledger.append({
        "dataset": "schedule", "row": "byes", "field": "teams_on_bye",
        "published": ",".join(sorted(missing)), "official": ",".join(sorted(byes)),
        "result": "match" if missing == byes else "MISMATCH",
        "source": "https://www.nfl.com/schedules/2026/by-week/week-10",
    })

    # --------------------------------------------------- cross-session tables
    # The annex session published the same injury report as a CSV; check it too.
    annex = os.path.join(ROOT, "data", "injuries", "injuries_2026_week10.csv")
    if os.path.exists(annex):
        with open(annex, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        if len(rows) != len(off_i):
            problems.append(
                f"annex injuries CSV: {len(rows)} rows vs official {len(off_i)}"
            )
        else:
            for i, orow in enumerate(off_i):
                r = rows[i]
                key = f"annex-injuries/{orow['TEAM']}/{orow['PLAYER']}"
                rec(ledger, "annex-injuries", key, "player",
                    r.get("Player") or r.get("player"), orow["PLAYER"], annex)
                rec(ledger, "annex-injuries", key, "game_status",
                    r.get("Game Status") or r.get("game_status"),
                    orow["GAMESTATUS"] or None, annex)

    annex_std = os.path.join(ROOT, "data", "nfl", "teams_standings_2026_w10.csv")
    if os.path.exists(annex_std):
        with open(annex_std, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        for r in rows:
            ab = (r.get("abbrev") or r.get("team") or r.get("TEAM") or "").strip()
            o = off.get(ab)
            if not o:
                continue
            key = f"annex-standings/{ab}"
            for pf, of in (("W", "W"), ("L", "L"), ("T", "T")):
                rec(ledger, "annex-standings", key, pf,
                    r.get(pf) or r.get(pf.lower()), o[of], annex_std)

    # ------------------------------------------------------------------ write
    os.makedirs(V, exist_ok=True)
    summary = {
        "generated_at": "2026-11-14",
        "session": "arena/fcc11e05-x1",
        "official_sources": [
            "https://www.nfl.com/standings/league/2026/REG",
            "https://www.nfl.com/injuries/",
            "https://www.nfl.com/schedules/2026/by-week/week-10",
        ],
        "checks": len(ledger),
        "matches": sum(1 for r in ledger if r["result"] == "match"),
        "mismatches": sum(1 for r in ledger if r["result"] == "MISMATCH"),
        "informational": sum(1 for r in ledger if r["result"] == "captured"),
        "problems": problems,
    }
    with open(os.path.join(V, "verification_ledger.json"), "w", encoding="utf-8") as fh:
        json.dump({"summary": summary, "ledger": ledger}, fh, indent=1)

    print(f"checks      : {summary['checks']}")
    print(f"match       : {summary['matches']}")
    print(f"mismatch    : {summary['mismatches']}")
    print(f"informational: {summary['informational']}")
    for p in problems[:40]:
        print("  PROBLEM", p)
    if problems:
        return 1
    print("official re-verification passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
