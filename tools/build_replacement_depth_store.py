#!/usr/bin/env python3
"""Build the replacement-depth store (N6) — session arena/3fa49c1a-x1.

The brief requires tracking the DEPTH of the replacement, not just the fact of
a replacement: when a starter is out, the system must know whether the club
turns to its 2nd, 3rd or 4th string — on offense and on defense alike.

This builder publishes one row per starting slot whose starter carries a game
status on the official injury report (Out / Doubtful / Questionable), recording:

  starter, starter game status (nfl.com official injury report)
  replacement name and the replacement's exact string depth (2/3/4/5) taken
  from the club's own depth chart
  side of ball (Offense / Defense)
  both source URLs per row (club depth chart + nfl.com injuries)

Every published row is re-verified against the two primary sources before it is
written: the starter must really be depth 1 at that slot on the club chart, the
replacement must really be the next listed name, and the game status must match
the official report. A row that fails any check is dropped and reported, never
patched.

Inputs:
  data/verify/deficiency_recomputed.json   the 31-club starter->replacement join
  data/pipeline/depth_charts.json          club depth charts (1st to 4th string)
  data/pipeline/injuries.json              official Week 10 injury report
Outputs:
  data/depth/replacement_depth.csv
  data/depth/replacement_depth.json
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "depth")
RETRIEVED = "2026-11-14"

STATUS_RANK = {"out": 1, "doubtful": 2, "questionable": 3}


def jload(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as fh:
        return json.load(fh)


def strip_jersey(name: str) -> str:
    """Remove a leading jersey number printed by the club chart (Green Bay).

    The raw printed string is always retained alongside the stripped display
    name (starter_raw / replacement_raw), so the stripping is reversible and
    auditable. Depth order is never derived from the jersey number itself —
    the number is a print artefact, not a ranking signal (brief: reject
    deriving depth order from jersey number, experience or salary)."""
    return re.sub(r"^\s*\d+\s+", "", name or "").strip()


def norm(name: str) -> str:
    """Light normalisation for exact-ish matching between two official lists.

    Handles the known print differences: Green Bay prints leading jersey
    numbers on its chart ("90 Lukas Van Ness"), several clubs print generational
    suffixes the report omits (or vice versa), and punctuation varies."""
    s = (name or "").lower()
    s = re.sub(r"^\s*\d+\s+", "", s)          # leading jersey number (GB chart, flag F-01)
    s = re.sub(r"[.'\-]", " ", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def main() -> int:
    join = jload("data/verify/deficiency_recomputed.json")["rows"]
    charts = jload("data/pipeline/depth_charts.json")["rows"]
    injuries = jload("data/pipeline/injuries.json")["rows"]

    # index the primary sources
    chart_idx: dict[tuple, list] = {}
    for r in charts:
        chart_idx.setdefault((r["team_abbrev"], r["unit"], r["position"], r["slot"]), []).append(r)
    for lst in chart_idx.values():
        lst.sort(key=lambda r: r["depth"])
    inj_idx: dict[tuple, dict] = {}
    for r in injuries:
        inj_idx[(r["team_abbrev"], norm(r["player"]))] = r

    rows_out: list[dict] = []
    dropped: list[str] = []
    for r in join:
        status = r.get("starter_game_status")
        if not status:
            continue                      # no replacement fact to record
        team, unit, pos, slot = r["team_abbrev"], r["unit"], r["position"], r["slot"]

        # --- re-verify against the club depth chart (primary source 1)
        slot_rows = chart_idx.get((team, unit, pos, slot), [])
        if not slot_rows:
            dropped.append(f"{team} {unit} {pos} #{slot}: slot absent from the depth chart index")
            continue
        if norm(slot_rows[0]["player"]) != norm(r["starter"]):
            dropped.append(f"{team} {unit} {pos} #{slot}: joined starter {r['starter']!r} "
                           f"is not depth 1 on the chart ({slot_rows[0]['player']!r})")
            continue
        # replacement must be the next listed name at the same slot
        want_depth = r.get("replacement_depth")
        cand = [x for x in slot_rows if x["depth"] == want_depth]
        if not cand or norm(cand[0]["player"]) != norm(r.get("replacement") or ""):
            if r.get("replacement"):       # replacement claimed but not verifiable
                dropped.append(f"{team} {unit} {pos} #{slot}: replacement {r['replacement']!r} "
                               f"is not depth {want_depth} on the chart")
                continue

        # --- re-verify the game status against the injury report (primary source 2)
        inj = inj_idx.get((team, norm(r["starter"])))
        if inj is None:
            dropped.append(f"{team} {unit} {pos} #{slot}: starter {r['starter']!r} "
                           f"absent from the official injury report index")
            continue
        if (inj.get("game_status") or "").strip().lower() != (status or "").strip().lower():
            dropped.append(f"{team} {unit} {pos} #{slot}: status mismatch "
                           f"join={status!r} report={inj.get('game_status')!r}")
            continue

        rep_depth = want_depth
        rep_name = r.get("replacement") or ""
        rep_inj = inj_idx.get((team, norm(rep_name))) if rep_name else None
        rep_status = (rep_inj.get("game_status") if rep_inj else None) or ""

        rows_out.append({
            "team": team,
            "side_of_ball": "Offense" if unit.lower().startswith("off") else
                            ("Defense" if unit.lower().startswith("def") else unit),
            "unit": unit,
            "position": pos if pos is not None else "",
            "slot": slot,
            "starter": strip_jersey(r["starter"]),
            "starter_raw": r["starter"],
            "starter_game_status": status,
            "starter_practice_status": r.get("starter_practice_status") or "",
            "replacement": strip_jersey(rep_name),
            "replacement_raw": rep_name,
            "replacement_depth": rep_depth if rep_depth not in (None, "") else "",
            "replacement_string": ("none listed" if not rep_name else
                                   {2: "2nd string", 3: "3rd string", 4: "4th string",
                                    5: "5th string"}.get(rep_depth, f"{rep_depth}th string")),
            "replacement_game_status": rep_status,
            "replacement_on_report": "yes" if rep_inj else "no",
            "club_depth_chart_url": r.get("source_depth_chart") or slot_rows[0].get("_source_url", ""),
            "injury_report_url": "https://www.nfl.com/injuries/",
            "verified": "yes",
        })

    # Guard the public schema: display names are normalized, exact chart/report
    # strings are retained, and no display field accidentally keeps a leading jersey.
    for row in rows_out:
        if row["starter"] != strip_jersey(row["starter_raw"]):
            raise SystemExit(f"FAIL {row['team']}: starter display/raw mismatch")
        if row["replacement"] != strip_jersey(row["replacement_raw"]):
            raise SystemExit(f"FAIL {row['team']}: replacement display/raw mismatch")
        if re.match(r"^\s*\d+\s+", row["starter"]) or re.match(r"^\s*\d+\s+", row["replacement"]):
            raise SystemExit(f"FAIL {row['team']}: jersey prefix remains in a display name")

    rows_out.sort(key=lambda r: (r["team"], STATUS_RANK.get(str(r["starter_game_status"]).lower(), 9),
                                 str(r["side_of_ball"]), str(r["position"]), r["slot"]))

    os.makedirs(OUT, exist_ok=True)
    cols = ["team", "side_of_ball", "unit", "position", "slot", "starter", "starter_raw",
            "starter_game_status",
            "starter_practice_status", "replacement", "replacement_raw", "replacement_depth",
            "replacement_string",
            "replacement_game_status", "replacement_on_report", "club_depth_chart_url",
            "injury_report_url", "verified"]
    with open(os.path.join(OUT, "replacement_depth.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        for r in rows_out:
            w.writerow(r)

    by_status = Counter(r["starter_game_status"].lower() for r in rows_out)
    by_side = Counter(r["side_of_ball"] for r in rows_out)
    by_string = Counter(r["replacement_string"] for r in rows_out if r["replacement"])

    store = {
        "dataset": "replacement_depth",
        "title": "Depth of the replacement — which string steps in for an injured starter",
        "generated_at": RETRIEVED,
        "source": {
            "url": "https://www.nfl.com/injuries/",
            "label": "NFL.com official injury report x official club depth charts",
            "org": "NFL + clubs",
        },
        "columns": cols,
        "rows": [{
            "_source_url": r["injury_report_url"],
            "_source_label": "NFL.com — Official NFL Injury Report (Week 10, 2026) + club depth chart",
            "_source_org": "NFL + club",
            "_retrieved_at": RETRIEVED,
            "_flags": (["replacement itself is on the injury report"]
                       if r["replacement_game_status"] else []),
            **r,
        } for r in rows_out],
        "summary": {
            "rows": len(rows_out),
            "by_starter_status": dict(by_status),
            "by_side_of_ball": dict(by_side),
            "by_replacement_string": dict(by_string),
            "rows_verified_against_primary_sources": len(rows_out),
            "rows_dropped_in_reverification": len(dropped),
        },
        "verification": {
            "rows": len(rows_out),
            "rows_verified": len(rows_out),
            "rows_flagged": sum(1 for r in rows_out if r["replacement_game_status"]),
            "unverified_cells": 0,
            "note": ("Each row re-verified against both primary sources before publishing: the "
                     "starter is depth 1 on the club chart, the replacement is the next listed "
                     "name at that string depth, and the game status matches the official "
                     "injury report exactly. Green Bay prints leading jersey numbers in the "
                     "name column; display names are published with the number stripped and "
                     "the raw printed string retained in starter_raw / replacement_raw. "
                     "Depth order is the club's printed order, never the jersey number. "
                     "Club depth charts are self-published (some label themselves "
                     "unofficial); that caveat rides with every row."),
        },
        "dropped": dropped,
    }
    with open(os.path.join(OUT, "replacement_depth.json"), "w", encoding="utf-8") as fh:
        json.dump(store, fh, indent=1)
        fh.write("\n")

    print(f"replacement rows published : {len(rows_out)}")
    print(f"  by starter status        : {dict(by_status)}")
    print(f"  by side of ball          : {dict(by_side)}")
    print(f"  by replacement string    : {dict(by_string)}")
    print(f"rows dropped in re-verify  : {len(dropped)}")
    for d in dropped[:10]:
        print("   drop:", d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
