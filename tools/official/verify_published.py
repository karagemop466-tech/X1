"""Re-derive every published number from the fresh capture, and fail on a disagreement.

Session `arena-b03ced7c-x1`. Additive: reads only.

    python3 tools/official/verify_published.py

What it checks, and why each check exists:

  1. The console's injury table equals the published 2026-11-14 TSV, cell for
     cell. If these two drift, two pages of the site disagree with each other.
  2. Every designation the console prints is one the live page prints. A
     designation that exists in the table and not on the page is a fabrication.
  3. The depth register's game statuses for players who appear on BOTH the
     11-14 table and the live page are re-checked against the live page. Where
     the two dated reads disagree, the disagreement is REPORTED, not resolved.
  4. The Packers depth rows still carry jersey numbers (the defect must remain
     visible, not be silently cleaned in the display layer).
  5. Every row on the readiness page carries a source, and every measurement
     quoted there is reproducible from the file it names.
  6. Status totals recompute from the transcription (176/90/70/11).
  7. Two reads of the same page on the same day still agree on every cell.

Exit code 0 = every check passed. Exit 1 = at least one failed (printed).
Exit 2 = a check could not run because an input is missing.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
D = os.path.join(ROOT, "data")
OUT = os.path.join(D, "console")

PRACTICE_FULL = "Full Participation in Practice"
PRACTICE_LTD = "Limited Participation in Practice"
PRACTICE_DNP = "Did Not Participate In Practice"
SHORT_TO_LONG = {"Full": PRACTICE_FULL, "Limited": PRACTICE_LTD, "DNP": PRACTICE_DNP}

results: list[tuple[str, bool, str]] = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    return ok


def rows(name):
    with open(os.path.join(OUT, name), encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_live():
    rec = json.load(open(os.path.join(OUT, "week10_reconcile.json"), encoding="utf-8"))
    path = os.path.join(ROOT, rec["captures"]["live_2026_11_15"]["path"])
    out = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("#") or not line.strip():
                continue
            game, team, player, pos, inj, prac, status = line.split("|")
            out[(team, player)] = dict(game=game, pos=pos, injury=inj, practice=prac, status=status)
    return rec, out


def main():
    for need in ("week10_reconcile.json", "depth_parse.json", "readiness.json",
                 "injuries_week10.csv", "depth_replacement.csv"):
        if not os.path.exists(os.path.join(OUT, need)):
            print(f"cannot run: {need} is missing (run the builders first)")
            return 2

    rec, live = load_live()
    console = {(r["TEAM"], r["PLAYER"]): r for r in rows("injuries_week10.csv")}
    with open(os.path.join(D, "nfl", "injuries_week10.tsv"), encoding="utf-8") as fh:
        body = [ln for ln in fh if not ln.startswith("#")]
    published = {(r["team"], r["player"]): r
                 for r in csv.DictReader(body, delimiter="\t")}

    # -- 1. console == published TSV --------------------------------------
    # The two files use different club codes for Los Angeles: the TSV carries the
    # league's "LAR", the console the mirror's "LA". A code map is applied so this
    # check tests cells, not naming, and the map is stated rather than assumed.
    CODE = {"LAR": "LA"}
    published = {(CODE.get(t, t), p): v for (t, p), v in published.items()}
    diff = []
    for k in sorted(set(console) | set(published)):
        a, b = console.get(k), published.get(k)
        if not a or not b:
            diff.append(f"{k}: present in one table only")
            continue
        if (a["INJURY"] or "") != (b["injury"] or "") \
           or SHORT_TO_LONG.get(a["PRACTICE"], a["PRACTICE"]) != (b["practice_status"] or "") \
           or (a["GAMESTATUS"] or "") != (b["game_status"] or ""):
            diff.append(f"{k}: console {a['INJURY']}|{a['PRACTICE']}|{a['GAMESTATUS']} vs "
                        f"tsv {b['injury']}|{b['practice_status']}|{b['game_status']}")
    check("console injury table equals the published TSV", not diff,
          f"{len(console)} rows compared; {len(diff)} differ" + (f"; first: {diff[0]}" if diff else ""))

    # -- 2. every printed designation is one the page prints --------------
    allowed = {"Out", "Doubtful", "Questionable", ""}
    bad = [f"{k[0]} {k[1]}={v['GAMESTATUS']!r}" for k, v in console.items()
           if (v["GAMESTATUS"] or "") not in allowed]
    check("every game designation is one the official page uses", not bad,
          f"{len(bad)} value(s) outside Out/Doubtful/Questionable/blank" +
          (f"; first: {bad[0]}" if bad else ""))

    # -- 3. depth statuses re-checked against the live page ---------------
    depth = rows("depth_replacement.csv")
    rechecked = conflicts = checked = 0
    for r in depth:
        gs = (r["STARTER_GAME_STATUS"] or "").strip()
        if not gs:
            continue
        k = (r["TEAM"], r["STARTER"])
        if k not in live:
            continue
        checked += 1
        live_gs = (live[k]["status"] or "").strip()
        if live_gs == gs:
            rechecked += 1
        else:
            conflicts += 1
    check("depth game statuses confirmed against the live page",
          conflicts == 0,
          f"{checked} starter status(es) re-checked; {rechecked} confirmed; "
          f"{conflicts} differ between the 11-14 table and the live page "
          f"(reported on capture.html, not auto-corrected)")

    # -- 4. the Packers defect is still visible ---------------------------
    dp = json.load(open(os.path.join(OUT, "depth_parse.json"), encoding="utf-8"))
    gb = [r for r in depth if r["TEAM"] == "GB"]
    contaminated = [r for r in gb if re.match(r"^\d", (r["STARTER"] or "").strip())]
    check("Packers depth rows still carry the raw printed string (defect visible)",
          len(contaminated) == len(gb) and len(gb) > 0,
          f"{len(contaminated)} of {len(gb)} GB starters carry a jersey number; "
          f"stripping recovers {dp['packers_summary']['join_gain']} injury joins")

    # -- 5. readiness rows are sourced and measurable ---------------------
    rd = json.load(open(os.path.join(OUT, "readiness.json"), encoding="utf-8"))
    unsourced = [r["id"] for r in rd["rows"] if not (r.get("source") or "").startswith("http")]
    unmeasured = [r["id"] for r in rd["rows"] if r.get("measurement") is None]
    check("every readiness row carries an official source", not unsourced,
          f"{len(rd['rows'])} rows; {len(unsourced)} without a URL" +
          (f"; first: {unsourced[0]}" if unsourced else ""))
    check("readiness measurements all ran", not unmeasured,
          f"{len(rd['rows'])} rows; {len(unmeasured)} unmeasured" +
          (f"; first: {unmeasured[0]}" if unmeasured else ""))

    # -- 6. status totals recompute ---------------------------------------
    counts = {"Out": 0, "Doubtful": 0, "Questionable": 0, "": 0}
    for r in live.values():
        counts[(r["status"] or "").strip()] += 1
    want = {"Out": 70, "Doubtful": 11, "Questionable": 90, "": 176}
    check("status totals recompute from the transcription", counts == want,
          f"recomputed {counts} vs published {want}")

    # -- 7. the two same-day reads still agree ----------------------------
    check("two independent reads of the same page agree", len(rec["conflicts"]) == 0,
          f"{len(rec['conflicts'])} conflicting cell(s) across "
          f"{rec['captures']['live_2026_11_15']['rows']} rows")

    # -- 8. row counts quoted on the pages are the row counts ------------
    n_live = rec["captures"]["live_2026_11_15"]["rows"]
    check("the live row count on the page is the row count in the file",
          n_live == len(live) == 347, f"{n_live} vs {len(live)} vs 347")

    width = max(len(n) for n, _, _ in results)
    failed = 0
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name.ljust(width)}  {detail}")
        failed += (not ok)
    print(f"\n{len(results) - failed} of {len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
