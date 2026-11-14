#!/usr/bin/env python3
"""T10/T12 — cross-check the derived deficiency register against the officially
designated players re-read from nfl.com/injuries on 2026-11-14, and emit the
Week 10 deficiency board used by the hub site.

The register itself (data/pipeline/deficiency.json) was built by another session
from the same two official sources.  This script does NOT rebuild it; it tests
whether every "starter Out / Doubtful / Questionable" claim it makes is one the
official injury report actually prints.
"""

from __future__ import annotations

import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW = os.path.join(ROOT, "data", "verification", "raw", "nfl_injuries_2026_week10.md")
URL = "https://www.nfl.com/injuries/"

ALIASES = {"LAR": "LA", "ARI": "AZ"}


def abbr(s):
    s = (s or "").strip().upper()
    return ALIASES.get(s, s)


def load_official():
    """Every officially designated player, keyed by (team, player)."""
    out = {}
    for line in open(RAW, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        team, player, pos, inj, prac, game = [p.strip() for p in line.split("|")]
        out[(abbr(team), player)] = {"position": pos, "injuries": inj,
                                     "practice_status": prac, "game_status": game}
    return out


def main() -> int:
    off = load_official()
    path = os.path.join(ROOT, "data", "pipeline", "deficiency.json")
    if not os.path.exists(path):
        print("no deficiency register present")
        return 0
    doc = json.load(open(path, encoding="utf-8"))
    rows = doc.get("rows", [])

    checks, fails = 0, []
    board = []
    for r in rows:
        key = (abbr(r.get("team_abbrev")), (r.get("starter") or "").strip())
        declared = (r.get("starter_game_status") or "").strip()
        listed = r.get("starter_on_report")
        if declared:
            checks += 1
            official = off.get(key)
            if official is None:
                fails.append({"team": key[0], "starter": key[1], "declared": declared,
                              "official": "(not designated on the official report)",
                              "why": "register says the starter carries a game status; the "
                                     "official report does not list this player at all"})
            elif official["game_status"].lower() != declared.lower():
                fails.append({"team": key[0], "starter": key[1], "declared": declared,
                              "official": official["game_status"], "why": "game status mismatch"})
        # NOTE: starter_on_report means "appears on the report at all", which is
        # true for players the page lists with a blank game status (full
        # participation, no designation).  It is therefore not comparable with
        # "has a game status" and is deliberately not asserted here.

        if declared.lower() in ("out", "doubtful", "questionable"):
            board.append({
                "team": abbr(r.get("team_abbrev")),
                "team_name": r.get("team_name"),
                "unit": r.get("unit"),
                "position": r.get("position"),
                "slot": r.get("slot"),
                "starter": r.get("starter"),
                "starter_game_status": declared,
                "starter_practice_status": r.get("starter_practice_status") or "",
                "injuries": (off.get(key) or {}).get("injuries", ""),
                "replacement": r.get("replacement") or "",
                "replacement_depth": r.get("replacement_depth") or "",
                "replacement_game_status": r.get("replacement_game_status") or "",
                "depth_listed": r.get("depth_listed") or "",
                "severity": r.get("severity"),
                "depth_chart_url": r.get("_source_urls", [r.get("_source_url")])[0]
                if r.get("_source_urls") else r.get("_source_url"),
                "injury_report_url": URL,
            })

    # 2nd/3rd/4th-string view: the brief asks specifically for which string has to play
    by_string = {}
    for b in board:
        if b["replacement_depth"]:
            by_string.setdefault(int(b["replacement_depth"]), []).append(b)

    out = {
        "dataset": "deficiency_crosscheck",
        "official_source": URL,
        "retrieved": "2026-11-14",
        "verified_by": "arena-459b17e1-x1",
        "register_rows": len(rows),
        "status_checks": checks,
        "fail": len(fails),
        "failures": fails,
        "designated_slots": len(board),
        "slots_by_replacement_string": {str(k): len(v) for k, v in sorted(by_string.items())},
        "board": board,
    }
    os.makedirs(os.path.join(ROOT, "data", "verification"), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, "data", "verification", "deficiency.json"), "w",
                        encoding="utf-8"), indent=1)
    with open(os.path.join(ROOT, "data", "verification", "deficiency_board.csv"), "w",
              newline="", encoding="utf-8") as fh:
        cols = ["team", "unit", "position", "slot", "starter", "starter_game_status",
                "starter_practice_status", "injuries", "replacement", "replacement_depth",
                "replacement_game_status", "severity", "depth_chart_url", "injury_report_url"]
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(board)

    print(f"register rows: {len(rows)}   status checks: {checks}   FAIL: {len(fails)}")
    for f in fails[:20]:
        print(f"  FAIL {f['team']} {f['starter']}: declared={f['declared']!r} "
              f"official={f['official']!r} -- {f['why']}")
    print(f"designated slots (starter Out/Doubtful/Questionable): {len(board)}")
    print("replacement string distribution:",
          {k: len(v) for k, v in sorted(by_string.items())})
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
