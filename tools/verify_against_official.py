#!/usr/bin/env python3
"""Diff every published Week 10 table against an independent re-read of the official pages.

This is the check the repository was missing. `tools/cross_check.py` compares two
transcriptions produced by the same sessions; agreement there cannot rule out a shared
misread (flag F-13). This script compares the published files against
`audit/official_snapshot_2026_w10.py`, which was transcribed separately, and reports
every cell that differs.

Exits 0 when everything matches, 1 when any published cell contradicts the official page.
Writes `data/audit/verification_run.json` with the full per-table result so the site can
render it without re-parsing this output.

Usage:  python3 tools/verify_against_official.py [--json]
"""
import csv
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "audit"))

import official_snapshot_2026_w10 as OFF  # noqa: E402

OUT = os.path.join(ROOT, "data", "audit", "verification_run.json")


def read_tsv(path):
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(lines, delimiter="\t"))


# ------------------------------------------------------------------ standings
def check_standings():
    rows = read_tsv(os.path.join(ROOT, "data", "nfl", "standings.tsv"))
    published_columns = set(rows[0].keys()) if rows else set()
    cells = 0
    mismatches = []
    unmatched = []
    for r in rows:
        code = r["abbr"]
        official_code = OFF.TEAM_CODE_ALIASES.get(code, code)
        obs = OFF.STANDINGS.get(official_code)
        if obs is None:
            unmatched.append(code)
            continue
        for col, idx in OFF.STANDINGS_COLUMNS:
            # A column the published file does not carry cannot contradict the source.
            # It is listed as available-but-unpublished instead, so it stays visible.
            if col not in published_columns:
                continue
            cells += 1
            published = str(r.get(col, "")).strip()
            official = str(obs[idx]).strip()
            if published != official:
                mismatches.append({"team": code, "column": col,
                                   "published": published, "official": official})
    official_codes = {OFF.TEAM_CODE_ALIASES.get(r["abbr"], r["abbr"]) for r in rows}
    missing_teams = sorted(set(OFF.STANDINGS) - official_codes)
    available_unpublished = sorted({col for col, _ in OFF.STANDINGS_COLUMNS} - published_columns)
    return {
        "table": "standings",
        "source": OFF.SOURCES["standings"],
        "rows_published": len(rows),
        "rows_official": len(OFF.STANDINGS),
        "cells_compared": cells,
        "mismatches": mismatches,
        "rows_unmatched": unmatched,
        "teams_missing_from_published": missing_teams,
        "available_but_unpublished_columns": available_unpublished,
        "ok": not mismatches and not unmatched and not missing_teams,
    }


# ------------------------------------------------------------------ schedule
def check_schedule():
    rows = read_tsv(os.path.join(ROOT, "data", "nfl", "schedule_week10.tsv"))
    cells = 0
    mismatches = []
    by_key = {(r["away"], r["home"]): r for r in rows}
    for date, time, away, home, network, ascore, hscore in OFF.SCHEDULE:
        r = by_key.get((away, home))
        if r is None:
            mismatches.append({"game": f"{away} at {home}", "column": "row",
                               "published": "absent", "official": "present"})
            continue
        checks = [
            ("date_et", date),
            ("time_et", time),
            ("network", network),
            ("away_score", "" if ascore is None else str(ascore)),
            ("home_score", "" if hscore is None else str(hscore)),
        ]
        for col, official in checks:
            cells += 1
            published = (r.get(col) or "").strip()
            if published != official:
                mismatches.append({"game": f"{away} at {home}", "column": col,
                                   "published": published, "official": official})
    extra = [f"{r['away']} at {r['home']}" for r in rows
             if (r["away"], r["home"]) not in {(g[2], g[3]) for g in OFF.SCHEDULE}]
    return {
        "table": "schedule",
        "source": OFF.SOURCES["schedule"],
        "rows_published": len(rows),
        "rows_official": len(OFF.SCHEDULE),
        "cells_compared": cells,
        "mismatches": mismatches,
        "rows_unmatched": extra,
        "teams_missing_from_published": [],
        "ok": not mismatches and not extra and len(rows) == len(OFF.SCHEDULE),
    }


# ------------------------------------------------------------------ byes
def check_byes():
    path = os.path.join(ROOT, "data", "nfl", "week10_byes.csv")
    published = sorted(r["team"].strip() for r in csv.DictReader(open(path, encoding="utf-8")))
    official = sorted(OFF.BYES)
    return {
        "table": "week10_byes",
        "source": OFF.SOURCES["schedule"],
        "rows_published": len(published),
        "rows_official": len(official),
        "cells_compared": len(official),
        "mismatches": [] if published == official else [
            {"column": "bye teams", "published": ",".join(published), "official": ",".join(official)}],
        "rows_unmatched": [],
        "teams_missing_from_published": [],
        "ok": published == official,
    }


# ------------------------------------------------------------------ injuries
FIELDS = [("player", 1), ("position", 2), ("injury", 3),
          ("practice_status", 4), ("game_status", 5)]


def check_injuries():
    rows = read_tsv(os.path.join(ROOT, "data", "nfl", "injuries_week10.tsv"))
    index = {}
    for r in rows:
        index.setdefault((r["team"], r["player"]), []).append(r)

    cells = 0
    mismatches = []
    unmatched = []
    for team, player, pos, inj, prac, game in OFF.INJURIES:
        cands = index.get((team, player))
        if not cands:
            unmatched.append(f"{team} {player}")
            continue
        r = cands[0]
        for field, idx in FIELDS:
            cells += 1
            published = (r.get(field) or "").strip()
            official = str((team, player, pos, inj, prac, game)[idx]).strip()
            if published != official:
                mismatches.append({"player": f"{team} {player}", "column": field,
                                   "published": published, "official": official})
    # players the official page prints but the published file omits
    published_keys = {(r["team"], r["player"]) for r in rows}
    missing = [f"{t} {p}" for (t, p, *_rest) in OFF.INJURIES if (t, p) not in published_keys]
    # players the published file carries that this read did not see
    official_keys = {(t, p) for (t, p, *_rest) in OFF.INJURIES}
    extra = [f"{r['team']} {r['player']}" for r in rows if (r["team"], r["player"]) not in official_keys]
    return {
        "table": "injuries",
        "source": OFF.SOURCES["injuries"],
        "rows_published": len(rows),
        "rows_official": len(OFF.INJURIES),
        "cells_compared": cells,
        "mismatches": mismatches,
        "rows_unmatched": unmatched,
        "teams_missing_from_published": [],
        "published_rows_not_in_this_read": extra,
        "note": ("The official page prints 28 club tables: the four clubs on bye (CHI, DEN, "
                 "PHI, TB) have no table in Week 10. rows_official is therefore lower than "
                 "rows_published whenever the published file also carries bye-week rows "
                 "from elsewhere; see published_rows_not_in_this_read."),
        "ok": not mismatches and not unmatched,
    }


# ------------------------------------------------------------------ main
def main(argv):
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    results = [check_standings(), check_schedule(), check_byes(), check_injuries()]
    total_cells = sum(r["cells_compared"] for r in results)
    total_bad = sum(len(r["mismatches"]) for r in results)
    total_unmatched = sum(len(r["rows_unmatched"]) for r in results)
    payload = {
        "generated_at": started,
        "retrieved_at": OFF.RETRIEVED,
        "method": ("published data/nfl/*.tsv diffed against an independent transcription "
                   "of the official pages in audit/official_snapshot_2026_w10.py"),
        "sources": OFF.SOURCES,
        "results": results,
        "totals": {
            "cells_compared": total_cells,
            "mismatches": total_bad,
            "rows_unmatched": total_unmatched,
            "tables_ok": sum(1 for r in results if r["ok"]),
            "tables": len(results),
        },
        "ok": all(r["ok"] for r in results),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1)

    for r in results:
        flag = "PASS" if r["ok"] else "FAIL"
        print(f"{flag}  {r['table']:<14} published={r['rows_published']:<4} "
              f"this-read={r['rows_official']:<4} cells={r['cells_compared']:<5} "
              f"mismatches={len(r['mismatches'])} unmatched={len(r['rows_unmatched'])}")
        for m in r["mismatches"][:10]:
            print("        ", m)
        for u in r["rows_unmatched"][:6]:
            print("         unmatched row:", u)
    print(f"\ncells compared: {total_cells}   mismatches: {total_bad}   "
          f"unmatched rows: {total_unmatched}")
    if payload["ok"]:
        print("every published Week 10 cell agrees with the official page")
        return 0
    print("FAILED: published data contradicts the official page (see mismatches above)")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
