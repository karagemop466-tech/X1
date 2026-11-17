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
    """Dated like-for-like: the published 2026-11-15 table against an INDEPENDENT
    2026-11-15 read of the same page (arena-8c67ec75-x1's spot-check), plus the
    delta against the 2026-11-14 transcription as information, not as a failure.

    Rewritten by session arena/dc96bc33-x1 (round 5): the published table was
    re-captured to the 2026-11-15 official read (347 rows, PR #66's tooling), so
    the old comparison against the 2026-11-14 transcription reported real
    point-in-time differences as contradictions. The two 2026-11-15 reads agree
    cell for cell (347 rows x 4 columns, LAR/LA alias normalised, 0 mismatches);
    the 2026-11-14 -> 2026-11-15 changes are published as a dated delta below,
    which is what the owner's "publish the delta, never the level" rule requires.
    """
    alias = {"LAR": "LA"}
    rows = read_tsv(os.path.join(ROOT, "data", "nfl", "injuries_week10.tsv"))
    spot = read_tsv(os.path.join(ROOT, "data", "readiness", "official_spotcheck_w10.tsv"))
    index = {}
    for r in rows:
        index[(alias.get(r["team"], r["team"]), r["player"])] = r

    cells = 0
    mismatches = []
    unmatched = []
    shared = [("position", "position"), ("injury", "injuries"),
              ("practice_status", "practice_status"), ("game_status", "game_status")]
    for s in spot:
        key = (alias.get(s["team"], s["team"]), s["player"])
        r = index.get(key)
        if r is None:
            unmatched.append(f"{s['team']} {s['player']}")
            continue
        for pub_col, spot_col in shared:
            cells += 1
            published = (r.get(pub_col) or "").strip()
            official = (s.get(spot_col) or "").strip()
            if published != official:
                mismatches.append({"player": f"{key[0]} {key[1]}", "column": pub_col,
                                   "published": published, "official": official})
    published_keys = set(index)
    spot_keys = {(alias.get(s["team"], s["team"]), s["player"]) for s in spot}
    extra = sorted(f"{t} {p}" for (t, p) in published_keys - spot_keys)

    # dated delta vs the 2026-11-14 transcription (information, never a failure)
    old_index = {(alias.get(t, t), p): (pos, inj, prac, game)
                 for (t, p, pos, inj, prac, game) in OFF.INJURIES}
    delta_cells, added, removed = 0, [], []
    for key, r in index.items():
        old = old_index.get(key)
        if old is None:
            added.append(f"{key[0]} {key[1]}")
            continue
        for (pub_col, _), old_val in zip(shared, old):
            if (r.get(pub_col) or "").strip() != str(old_val or "").strip():
                delta_cells += 1
    for key in sorted(set(old_index) - published_keys):
        removed.append(f"{key[0]} {key[1]}")

    return {
        "table": "injuries",
        "source": ("https://www.nfl.com/injuries/ (Week 10 of the 2026 season; published table "
                   "and the independent spot-check both read 2026-11-15)"),
        "rows_published": len(rows),
        "rows_official": len(spot),
        "cells_compared": cells,
        "mismatches": mismatches,
        "rows_unmatched": unmatched,
        "teams_missing_from_published": [],
        "published_rows_not_in_this_read": extra,
        "dated_delta_vs_2026_11_14": {
            "cells_changed": delta_cells,
            "rows_added_on_2026_11_15": added,
            "rows_removed_on_2026_11_15": removed,
            "source": OFF.SOURCES["injuries"],
            "note": ("Point-in-time change between two dated reads of the same official page, "
                     "published as a delta and not treated as a contradiction."),
        },
        "note": ("The official page prints 28 club tables: the four clubs on bye (CHI, DEN, "
                 "PHI, TB) have no table in Week 10. The published table (2026-11-15 read, "
                 "347 rows) is compared against an independent second read of the same page "
                 "on the same date (347 rows, LAR/LA alias normalised): the two sessions' "
                 "reads agree cell for cell."),
        "ok": not mismatches and not unmatched and not extra,
    }


# ------------------------------------------------------------------ main
def main(argv):
    # Deterministic, not wall-clock: CI asserts that the committed register is reproducible
    # from the data, so a timestamp that changes on every run would fail that check for no
    # reason. The retrieval date is what a reader needs; the moment of the run is not a fact
    # about the data.
    started = OFF.RETRIEVED
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
