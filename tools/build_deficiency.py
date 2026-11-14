#!/usr/bin/env python3
"""Rebuild the lineup-deficiency register with a name normaliser, and report
every place the published register disagrees with it.

Session `arena/fcc11e05-x1`. Reads the pipeline outputs in `data/pipeline/`
read-only and writes to `data/verify/`. It never edits the pipeline's files.

Two defects this corrects, both found by re-fetching the official pages:

  1. Green Bay's club depth chart prints jersey numbers in the name column
     ("75 Sean Rhyan"). The published register joins the chart to the official
     injury report on the raw string, so every Green Bay row silently fails to
     match - including the three starters the league lists as Out.
  2. Houston's club depth chart returns no parsable table, so Houston has no
     depth rows and therefore no deficiency rows at all. That is recorded as a
     coverage gap, not filled in.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE = os.path.join(ROOT, "data", "pipeline")
OUT = os.path.join(ROOT, "data", "verify")

STATUS_WEIGHT = {"out": 3, "doubtful": 2, "questionable": 1}
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v", "x"}


def norm(name: str) -> str:
    """Fold a player name to a join key: drop the jersey number, punctuation,
    case, accents and generational suffix."""
    s = unicodedata.normalize("NFKD", name or "")
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace("\u02bc", "'")
    s = re.sub(r"^\s*\d+\s+", "", s)          # leading jersey number
    s = re.sub(r"[^A-Za-z' ]+", " ", s)
    s = " ".join(s.split()).lower().strip()
    parts = [p for p in s.split(" ") if p and p not in SUFFIXES]
    return " ".join(parts)


def status_rank(status) -> int:
    return STATUS_WEIGHT.get((status or "").strip().lower(), 0)


def main() -> int:
    depth = json.load(open(os.path.join(PIPE, "depth_charts.json"), encoding="utf-8"))
    inj = json.load(open(os.path.join(PIPE, "injuries.json"), encoding="utf-8"))
    defc = json.load(open(os.path.join(PIPE, "deficiency.json"), encoding="utf-8"))

    injury_by_player = {}
    for r in inj["rows"]:
        injury_by_player[(r["team_abbrev"], norm(r.get("player")))] = r

    by_slot = {}
    for r in depth["rows"]:
        by_slot.setdefault(
            (r["team_abbrev"], r["unit"], r["position"], r["slot"]), []
        ).append(r)

    rows = []
    for (ab, unit, pos, slot), entries in sorted(
        by_slot.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]), str(kv[0][2]), kv[0][3] or 0)
    ):
        entries = sorted(entries, key=lambda r: r.get("depth") or 99)
        starter = entries[0]
        s_inj = injury_by_player.get((ab, norm(starter.get("player"))))
        s_status = (s_inj or {}).get("game_status")

        replacement = None
        repl_status = None
        for c in entries[1:]:
            st = (injury_by_player.get((ab, norm(c.get("player")))) or {}).get("game_status")
            if status_rank(st) >= 3:
                continue
            replacement, repl_status = c, st
            break
        if replacement is None and len(entries) > 1:
            replacement = entries[1]
            repl_status = (injury_by_player.get((ab, norm(replacement.get("player")))) or {}).get("game_status")

        rows.append({
            "team_abbrev": ab,
            "unit": unit,
            "position": pos,
            "slot": slot,
            "starter": starter.get("player"),
            "starter_display": re.sub(r"^\s*\d+\s+", "", starter.get("player") or ""),
            "starter_on_report": bool(s_inj),
            "starter_game_status": s_status,
            "starter_practice_status": (s_inj or {}).get("practice_status"),
            "replacement": (replacement or {}).get("player"),
            "replacement_display": re.sub(r"^\s*\d+\s+", "", (replacement or {}).get("player") or ""),
            "replacement_depth": (replacement or {}).get("depth"),
            "replacement_game_status": repl_status,
            "depth_listed": len(entries),
            "severity": status_rank(s_status),
            "source_depth_chart": starter.get("_source_url"),
            "source_injury": "https://www.nfl.com/injuries/",
        })

    # ------------------------------------------------------------- comparison
    pub_index = {
        (r["team_abbrev"], r["unit"], r["position"], r["slot"]): r for r in defc["rows"]
    }
    diffs = []
    for r in rows:
        p = pub_index.get((r["team_abbrev"], r["unit"], r["position"], r["slot"]))
        if p is None:
            diffs.append({"row": f"{r['team_abbrev']}/{r['unit']}/{r['position']}/{r['slot']}",
                          "issue": "missing from the published register"})
            continue
        for f in ("starter_on_report", "starter_game_status", "replacement", "severity"):
            if (p.get(f) or None) != (r.get(f) or None):
                diffs.append({
                    "row": f"{r['team_abbrev']}/{r['unit']}/{r['position']}/{r['slot']}",
                    "field": f,
                    "published": p.get(f),
                    "corrected": r.get(f),
                })

    # teams that play this week (so they have an injury report) but matched
    # zero starters: a join-quality signal, not automatically an error.
    teams_on_report = sorted({r["team_abbrev"] for r in inj["rows"]})
    hit = {}
    for r in rows:
        h = hit.setdefault(r["team_abbrev"], [0, 0])
        h[0] += 1
        if r["starter_on_report"]:
            h[1] += 1
    quality = []
    for t in sorted(hit):
        n, k = hit[t]
        quality.append({
            "team": t,
            "slots": n,
            "starters_on_report": k,
            "on_injury_report_this_week": t in teams_on_report,
            "note": (
                "club is on bye in Week 10; the league publishes no report for it"
                if t not in teams_on_report else
                "no depth-chart starter appears on the official report"
                if k == 0 else ""
            ),
        })

    summary = {
        "session": "arena/fcc11e05-x1",
        "built_from": [
            "https://www.nfl.com/injuries/",
            "official club depth charts (one per club site)",
        ],
        "slots": len(rows),
        "teams_covered": len({r["team_abbrev"] for r in rows}),
        "teams_missing": sorted({r["team_abbrev"] for r in inj["rows"]} - {r["team_abbrev"] for r in rows}),
        "starters_on_report": sum(1 for r in rows if r["starter_on_report"]),
        "starters_out": sum(1 for r in rows if (r["starter_game_status"] or "").lower() == "out"),
        "starters_doubtful": sum(1 for r in rows if (r["starter_game_status"] or "").lower() == "doubtful"),
        "starters_questionable": sum(1 for r in rows if (r["starter_game_status"] or "").lower() == "questionable"),
        "deltas_vs_published": len(diffs),
    }

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "deficiency_recomputed.json"), "w", encoding="utf-8") as fh:
        json.dump({"summary": summary, "join_quality": quality, "diffs": diffs, "rows": rows}, fh, indent=1)

    print(json.dumps(summary, indent=1))
    print(f"join-quality rows: {len(quality)}")
    print(f"deltas vs published register: {len(diffs)}")
    for d in diffs[:12]:
        print("  ", d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
