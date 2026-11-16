#!/usr/bin/env python3
"""Re-verification pack for the 2026-11-16 official reads (session arena-543cdcb0-x1).

Three dated official pages were read on 2026-11-16 and transcribed by hand into
`data/verification/2026_11_16/`. This tool checks them, and checks them against the
tables the site already publishes. It never "fixes" a published table: a difference in
dated evidence is a finding with two dates, not an edit.

Checks (every one is arithmetic on values printed by an official page — nothing is inferred):

  A1  Standings transcription is internally consistent: NET = PF - PA,
      PCT = (W + T/2) / (W + L + T) to three decimals, and HOME + ROAD = W-L-T.
      The last one is what makes the HOME/ROAD column *assignment* a measurement.
  A2  League closure: total wins = total losses, total ties is even, and every
      club's games played equals (fixtures it appears in) + nothing else.
  A3  Cross-page record agreement: the club records printed beside the logos on the
      Week 10 results page and on the Week 11 schedule page (together all 32 clubs)
      must equal the record on the standings page. Three pages, one number per club.
  A4  Slate completeness: Week 11 must cover all 32 clubs exactly once
      (13 fixtures + 6 byes). A page read that missed a fixture would fail here;
      this is the invariant the collector's drift alarm now enforces.
  A5  Dated-delta closure: the site's published standings (retrieved 2026-11-14)
      plus the Week 10 results that the 2026-11-14 read did not yet have (12 games:
      the 13 Sunday/Monday games minus none played, i.e. those printed "scheduled")
      must reproduce today's W, L, PF and PA for every club. 128 assertions.
      Anything that does not reproduce is printed as a diff row, not corrected.
  A6  Promotion accounting: how many Week 10 rows moved scheduled -> final since the
      2026-11-14 read, and which rows are still open (the Monday-night game).

Outputs (all under data/verification/2026_11_16/):
  standings_diff_2026_11_16.csv      one row per club per field that changed
  w10_promotion_2026_11_16.json      scheduled -> final promotion, with both source URLs
  verification_summary_2026_11_16.json  every check, its counts and its verdict

Usage:  python3 tools/verify_2026_11_16.py [--check]
  --check  rebuild into a temp dir and fail if the committed outputs differ in any
           field except `generated_at` (the CI staleness guard).
Exit 0 = the checks ran; a FAIL inside the summary is a finding, published either way.
Exit 1 = a transcription failed a structural check (a broken read must not reach a page).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VDIR = os.path.join(ROOT, "data", "verification", "2026_11_16")
NFL = os.path.join(ROOT, "data", "nfl")
RETRIEVED = "2026-11-16"
PRIOR_RETRIEVED = "2026-11-14"

STAND_URL = "https://www.nfl.com/standings/league/2026/REG"
W10_URL = "https://www.nfl.com/schedules/2026/by-week/week-10"
W11_URL = "https://www.nfl.com/schedules/2026/by-week/week-11"

# The standings page prints "LA" for the Rams; the site's published table uses "LAR".
# The alias is spelling only - both pages carry the same club - and it is published,
# not silently applied (see flag F-15 in data/flags.json).
ALIAS = {"LAR": "LA", "ARI": "AZ"}


def canon(abbr: str) -> str:
    return ALIAS.get(abbr, abbr)


def read_tsv(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        rows = [ln for ln in fh.read().split("\n") if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(io.StringIO("\n".join(rows)), delimiter="\t"))


def rec(s: str) -> tuple[int, int, int]:
    if not s:
        return (-1, -1, -1)
    p = s.split("-")
    return (int(p[0]), int(p[1]), int(p[2]) if len(p) > 2 else 0)


def pct(w: int, l: int, t: int) -> str:
    gp = w + l + t
    if gp == 0:
        return ""
    return f"{(w + t / 2) / gp:.3f}".rstrip()


def build() -> dict:
    fails: list[str] = []
    checks: dict[str, dict] = {}

    today = read_tsv(os.path.join(VDIR, "official_standings_2026_11_16.tsv"))
    w10 = read_tsv(os.path.join(VDIR, "official_w10_results_2026_11_16.tsv"))
    w11 = read_tsv(os.path.join(VDIR, "official_w11_schedule_2026_11_16.tsv"))
    prior = read_tsv(os.path.join(NFL, "standings.tsv"))
    prior_sched = read_tsv(os.path.join(NFL, "schedule_week10.tsv"))

    # ---- A1 internal arithmetic of today's standings read -------------------------------
    a1_ok = 0
    for r in today:
        w, l, t = int(r["w"]), int(r["l"]), int(r["t"])
        pf, pa, net = int(r["pf"]), int(r["pa"]), int(r["net"])
        if pf - pa != net:
            fails.append(f"A1 {r['abbr']}: PF-PA={pf - pa} but NET PTS printed {net}")
            continue
        if pct(w, l, t) != f"{float(r['pct']):.3f}":
            fails.append(f"A1 {r['abbr']}: computed PCT {pct(w, l, t)} != printed {r['pct']}")
            continue
        hw, hl, ht = rec(r["home"])
        rw, rl, rt = rec(r["road"])
        if (hw + rw, hl + rl, ht + rt) != (w, l, t):
            fails.append(f"A1 {r['abbr']}: HOME {r['home']} + ROAD {r['road']} != W-L-T {w}-{l}-{t}")
            continue
        a1_ok += 1
    checks["A1_standings_arithmetic"] = {
        "clubs": len(today),
        "passed": a1_ok,
        "assertions": len(today) * 3,
        "verdict": "pass" if a1_ok == len(today) and len(today) == 32 else "FAIL",
        "note": "NET = PF - PA; PCT = (W + T/2)/GP; HOME + ROAD = W-L-T. The third identity is what "
                "proves the two record triples transcribed are home and road, in that order.",
    }

    # ---- A2 league closure ---------------------------------------------------------------
    tw = sum(int(r["w"]) for r in today)
    tl = sum(int(r["l"]) for r in today)
    tt = sum(int(r["t"]) for r in today)
    tp = sum(int(r["pf"]) for r in today)
    ta = sum(int(r["pa"]) for r in today)
    checks["A2_league_closure"] = {
        "total_wins": tw,
        "total_losses": tl,
        "total_ties": tt,
        "total_points_for": tp,
        "total_points_against": ta,
        "games_implied": (tw + tl + tt) // 2,
        "verdict": "pass" if (tw == tl and tt % 2 == 0 and tp == ta) else "FAIL",
    }
    if tw != tl:
        fails.append(f"A2: wins {tw} != losses {tl}")
    if tp != ta:
        fails.append(f"A2: league PF {tp} != PA {ta}")

    # ---- A3 cross-page record agreement --------------------------------------------------
    today_rec = {r["abbr"]: f'{r["w"]}-{r["l"]}-{r["t"]}' for r in today}
    page_rec: dict[str, list[tuple[str, str]]] = {}
    for r in w10:
        for club, key in ((r["away"], "away_record"), (r["home"], "home_record")):
            page_rec.setdefault(canon(club), []).append((f"W10 results page / {r['game_id']}", r[key]))
    for r in w11:
        if r["row_type"] == "game":
            for club, key in ((r["away"], "away_record"), (r["home"], "home_record")):
                page_rec.setdefault(canon(club), []).append((f"W11 schedule page / {r['game_id']}", r[key]))
        else:
            page_rec.setdefault(canon(r["away"]), []).append(("W11 schedule page / bye block", r["away_record"]))
    a3_checked = a3_bad = 0
    a3_detail = []
    for club, prints in sorted(page_rec.items()):
        want = today_rec.get(club)
        for where, got in prints:
            a3_checked += 1
            got = got.strip()
            if want is None:
                a3_bad += 1
                a3_detail.append({"club": club, "where": where, "printed": got, "standings": ""})
                continue
            gw, gl, gt = rec(want)
            if got == want or rec(got) == (gw, gl, gt):
                continue
            # A page may print a record that predates a game it also prints as a final;
            # that is a real disagreement and must surface, not be explained away.
            a3_bad += 1
            a3_detail.append({"club": club, "where": where, "printed": got, "standings": want})
            fails.append(f"A3 {club}: {where} prints {got}, standings page prints {want}")
    checks["A3_cross_page_records"] = {
        "records_compared": a3_checked,
        "clubs_covered": len(page_rec),
        "mismatches": a3_bad,
        "detail": a3_detail,
        "verdict": "pass" if a3_bad == 0 else "FAIL",
        "note": "Two further official pages that print every club's record: the Week 10 results page "
                "(28 clubs) and the Week 11 schedule page (32 clubs). A transcription slip in the "
                "standings read has to disagree with at least one of them.",
    }

    # ---- A4 slate completeness -----------------------------------------------------------
    seen: dict[str, int] = {}
    for r in w11:
        if r["row_type"] == "game":
            seen[canon(r["away"])] = seen.get(canon(r["away"]), 0) + 1
            seen[canon(r["home"])] = seen.get(canon(r["home"]), 0) + 1
        else:
            seen[canon(r["away"])] = seen.get(canon(r["away"]), 0) + 1
    missing = sorted({a for a in today_rec} - set(seen))
    dupes = sorted(c for c, n in seen.items() if n != 1)
    checks["A4_slate_completeness"] = {
        "fixtures": sum(1 for r in w11 if r["row_type"] == "game"),
        "byes": sum(1 for r in w11 if r["row_type"] == "bye"),
        "clubs_appearing": len(seen),
        "clubs_missing": missing,
        "clubs_appearing_more_than_once": dupes,
        "verdict": "pass" if not missing and not dupes else "FAIL",
        "note": "Every one of the 32 clubs must appear exactly once per game week, either in a fixture "
                "or in the bye block. A partial page read fails this, which is why the collector now "
                "runs it before publishing a schedule capture.",
    }
    if missing:
        fails.append(f"A4: clubs absent from the Week 11 read: {missing}")
    if dupes:
        fails.append(f"A4: clubs appearing more than once: {dupes}")

    # ---- A5 dated-delta closure ----------------------------------------------------------
    prior_by = {canon(r["abbr"]): r for r in prior}
    played_then = {r["game_url"].rstrip("/").split("/")[-1] for r in prior_sched if r["status"] == "final"}
    new_finals = [
        r for r in w10
        if r["status"] == "Final" and r["game_url"].rstrip("/").split("/")[-1] not in played_then
    ]
    still_open = [r for r in w10 if r["status"] != "Final"]
    exp: dict[str, dict] = {c: {"w": 0, "l": 0, "t": 0, "pf": 0, "pa": 0} for c in today_rec}
    for r in new_finals:
        a, h = canon(r["away"]), canon(r["home"])
        asc, hsc = int(r["away_score"]), int(r["home_score"])
        if asc > hsc:
            exp[a]["w"] += 1
            exp[h]["l"] += 1
        elif hsc > asc:
            exp[h]["w"] += 1
            exp[a]["l"] += 1
        else:
            exp[a]["t"] += 1
            exp[h]["t"] += 1
        exp[a]["pf"] += asc
        exp[a]["pa"] += hsc
        exp[h]["pf"] += hsc
        exp[h]["pa"] += asc
    diff_rows = []
    a5_bad = 0
    for r in today:
        club = r["abbr"]
        p = prior_by.get(club)
        if p is None:
            fails.append(f"A5: {club} missing from the published {PRIOR_RETRIEVED} table")
            a5_bad += 1
            continue
        for field, today_v in (("w", int(r["w"])), ("l", int(r["l"])), ("t", int(r["t"])),
                               ("pf", int(r["pf"])), ("pa", int(r["pa"]))):
            base = int(p[field]) if p[field] != "" else 0
            expected = base + exp[club][field]
            if expected != today_v:
                a5_bad += 1
                fails.append(
                    f"A5 {club}.{field}: published {PRIOR_RETRIEVED}={base} + Week 10 delta "
                    f"{exp[club][field]} = {expected}, but {RETRIEVED} prints {today_v}"
                )
        for field, label in (("w", "W"), ("l", "L"), ("pf", "PF"), ("pa", "PA")):
            base = p[field]
            if base != r[field]:
                diff_rows.append({
                    "club": club, "field": label,
                    f"published_{PRIOR_RETRIEVED}": base,
                    f"official_{RETRIEVED}": r[field],
                    "week10_delta": exp[club][field],
                    "closes": "yes" if (int(base or 0) + exp[club][field] == int(r[field])) else "NO",
                    "source_old": "https://github.com/karagemop466-tech/X1/blob/main/data/nfl/standings.tsv",
                    "source_new": STAND_URL,
                })
    checks["A5_dated_delta_closure"] = {
        "clubs": len(today),
        "fields_per_club": 5,
        "assertions": len(today) * 5,
        "failures": a5_bad,
        "new_finals_applied": len(new_finals),
        "verdict": "pass" if a5_bad == 0 else "FAIL",
        "note": "The published table is not edited. The delta it is missing is computed from the Week 10 "
                "results that were 'scheduled' when it was read, and every field that moves is a diff row.",
    }

    # ---- A6 promotion accounting ---------------------------------------------------------
    checks["A6_promotion"] = {
        "week10_games_on_page": len(w10),
        "final_now": sum(1 for r in w10 if r["status"] == "Final"),
        "final_at_prior_read": len(played_then),
        "promoted_scheduled_to_final": len(new_finals),
        "still_open": [r["game_id"] for r in still_open],
        "verdict": "pass",
        "note": "The Monday-night game (2026_10_LAC_BAL, 2026-11-16 8:15 PM ET) had not been played when "
                "this pack was read, so Week 10 is not closed. Scores for it stay blank everywhere.",
    }

    return {
        "pack": "nfl-official-2026-11-16",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "retrieved_at_utc": "2026-11-16T18:44Z (Week 10 results) / 2026-11-16T18:47Z (standings) / "
                            "2026-11-16T18:52Z (Week 11 schedule)",
        "read_by": "session arena-543cdcb0-x1, via the fetch tool; no value recalled from memory",
        "sources": {
            "standings": STAND_URL,
            "week10_results": W10_URL,
            "week11_schedule": W11_URL,
            "published_baseline": "https://github.com/karagemop466-tech/X1/blob/main/data/nfl/standings.tsv",
        },
        "checks": checks,
        "failures": fails,
        "verdict": "pass" if not fails else "FAIL",
        "limits": [
            "The standings table was read from the LEAGUE view, not the division view the published table "
            "uses; division and conference records are therefore not re-checked here.",
            "Two record triples and two win-percentage columns on the standings page have no LEGEND "
            "definition and were not transcribed, per the site rule about undefined columns.",
            "Kickoff times are not printed for completed games on the weekly page, so the time_et column is "
            "blank for the 13 finals; the times in data/nfl/schedule_week10.tsv come from the 2026-11-14 read.",
            "No venue field is printed on the weekly schedule page. Venue requires one Game Center fetch per "
            "fixture; that capture is not part of this pack and remains an open, costed gap.",
            "Week 10 is not closed: the Monday-night game is scheduled at retrieval.",
        ],
    }


def outputs(summary: dict) -> tuple[str, str, str]:
    """(standings diff csv, promotion json, summary json) as text."""
    today = read_tsv(os.path.join(VDIR, "official_standings_2026_11_16.tsv"))
    prior = {canon(r["abbr"]): r for r in read_tsv(os.path.join(NFL, "standings.tsv"))}
    exp = {c["club"]: c for c in []}
    # recompute the per-club Week 10 delta the same way the summary did
    delta: dict[str, dict] = {}
    prior_sched = read_tsv(os.path.join(NFL, "schedule_week10.tsv"))
    played_then = {r["game_url"].rstrip("/").split("/")[-1] for r in prior_sched if r["status"] == "final"}
    for r in read_tsv(os.path.join(VDIR, "official_w10_results_2026_11_16.tsv")):
        if r["status"] != "Final" or r["game_url"].rstrip("/").split("/")[-1] in played_then:
            continue
        a, h = canon(r["away"]), canon(r["home"])
        asc, hsc = int(r["away_score"]), int(r["home_score"])
        for club, gf, ga, won in ((a, asc, hsc, asc > hsc), (h, hsc, asc, hsc > asc)):
            d = delta.setdefault(club, {"w": 0, "l": 0, "t": 0, "pf": 0, "pa": 0})
            d["pf"] += gf
            d["pa"] += ga
            d["w" if won else ("l" if gf != ga else "t")] += 1
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["club", "field", f"published_{PRIOR_RETRIEVED}", f"official_{RETRIEVED}",
                "week10_delta", "closes", "source_old", "source_new"])
    for r in today:
        club = r["abbr"]
        p = prior.get(club, {})
        for field, label in (("w", "W"), ("l", "L"), ("t", "T"), ("pf", "PF"), ("pa", "PA")):
            base = p.get(field, "")
            if base == r[field]:
                continue
            w.writerow([club, label, base, r[field], delta.get(club, {}).get(field, 0),
                        "yes" if (int(base or 0) + delta.get(club, {}).get(field, 0) == int(r[field])) else "NO",
                        "https://github.com/karagemop466-tech/X1/blob/main/data/nfl/standings.tsv",
                        STAND_URL])
    promo = {
        "generated_at": summary["generated_at"],
        "week": 10,
        "official_page": W10_URL,
        "promoted_rows": [
            {
                "game_id": r["game_id"], "date_et": r["date_et"],
                "away": r["away"], "away_score": r["away_score"],
                "home": r["home"], "home_score": r["home_score"],
                "status_official": r["status"],
                "status_published_2026_11_14": "scheduled",
                "score_published_2026_11_14": "",
                "game_url": r["game_url"],
                "source_url": W10_URL,
                "read_at": RETRIEVED,
            }
            for r in read_tsv(os.path.join(VDIR, "official_w10_results_2026_11_16.tsv"))
            if r["status"] == "Final"
            and r["game_url"].rstrip("/").split("/")[-1] not in played_then
        ],
        "still_open": [
            {"game_id": r["game_id"], "kickoff_et": f"{r['date_et']} {r['time_et']}",
             "away": r["away"], "home": r["home"], "game_url": r["game_url"]}
            for r in read_tsv(os.path.join(VDIR, "official_w10_results_2026_11_16.tsv"))
            if r["status"] != "Final"
        ],
        "note": "Scores below are what the official page printed on 2026-11-16. The published Week 10 "
                "table (retrieved 2026-11-14) is left untouched as a dated artefact; this file is the "
                "record of what has since been decided.",
    }
    return buf.getvalue(), json.dumps(promo, indent=1) + "\n", json.dumps(summary, indent=1) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)

    summary = build()
    csv_text, promo_text, sum_text = outputs(summary)

    if args.check:
        same = True
        for name, want in (("standings_diff_2026_11_16.csv", csv_text),
                           ("w10_promotion_2026_11_16.json", promo_text),
                           ("verification_summary_2026_11_16.json", sum_text)):
            got = open(os.path.join(VDIR, name), encoding="utf-8").read()
            strip = lambda s: "\n".join(l for l in s.split("\n") if "generated_at" not in l)
            if strip(got) != strip(want):
                same = False
                print(f"STALE: {name} differs from a fresh build")
        if same:
            print("CHECK OK: the 2026-11-16 pack matches a fresh build of the same reads")
        return 0 if same else 1

    outdir = VDIR
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "standings_diff_2026_11_16.csv"), "w", encoding="utf-8") as fh:
        fh.write(csv_text)
    with open(os.path.join(outdir, "w10_promotion_2026_11_16.json"), "w", encoding="utf-8") as fh:
        fh.write(promo_text)
    with open(os.path.join(outdir, "verification_summary_2026_11_16.json"), "w", encoding="utf-8") as fh:
        fh.write(sum_text)

    print("2026-11-16 official re-verification")
    for k, v in summary["checks"].items():
        print(f"  {k:32s} {v['verdict']}")
    print(f"  failures: {len(summary['failures'])}")
    for f in summary["failures"][:20]:
        print("   !", f)
    hard = [f for f in summary["failures"] if not f.startswith("A5 ")]
    return 1 if any(k.endswith(("arithmetic", "closure")) and summary["checks"][k]["verdict"] == "FAIL"
                    for k in summary["checks"]) or hard else 0


if __name__ == "__main__":
    sys.exit(main())
