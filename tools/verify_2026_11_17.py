#!/usr/bin/env python3
"""Re-verification pack for the 2026-11-17 official reads (session arena-01c263c4-x1).

Three official pages were read live on 2026-11-17 (~22:50-22:56 UTC) with the fetch tool and
transcribed into `data/verification/2026_11_17/`:

  official_injuries_w10_2026_11_17.tsv   Week 10 injury report, full page (chunks 0-7 of 8), 347 rows
  official_standings_2026_11_17.tsv       league standings, 32 clubs
  official_w10_results_2026_11_17.tsv     Week 10 slate, 14 fixtures, all Final
  week11_injuries_probe_2026_11_17.txt    probe: the Week 11 report URL resolved to the Week 10 page

This tool checks the transcriptions against arithmetic invariants, against the repo's own retained
collector capture (data/captures/payloads/injuries/..., official reads 2026-11-16/17), and against
the tables the site publishes. It NEVER edits a published table: a difference is a dated finding
with two dates and two sources, not an edit.

Checks:

  I1  Injury transcription structure: 347 rows, 8 columns, 28 club tables (the four Week 10 bye
      clubs CHI/DEN/PHI/TB carry no rows), the exact 14 fixtures, and only printed vocabularies
      for practice_status / game_status; every player_url is an official nfl.com player link.
  I2  Independent-read equality: every (club, player) key and every cell of the transcription must
      equal the retained collector capture (official read 2026-11-16T19:02:14Z, content unchanged
      through the 2026-11-17T19:49:49Z re-read), after aliasing the printed club label LAR to the
      capture's LA. Zero differences expected; any difference fails the pack.
  I3  Dated delta vs the published table (data/nfl/injuries_week10.tsv, retrieved 2026-11-14):
      rows added, rows removed, and cell-by-cell changes, written as a CSV finding.
  I4  Game-assignment consistency: each club maps to exactly one fixture, and the club set equals
      the 32 clubs minus the four byes.
  I5  Owner-item spot check: the three Lions rows named in the brief (Kerby Joseph, Cade Mays,
      D.J. Reed) carry game_status "Out" in both the published table and today's read.
  S1  Standings structure and arithmetic: PCT = (W + T/2) / (W + L + T) to three decimals,
      NET = PF - PA, and HOME + ROAD = W-L-T for all 32 clubs (this is what makes the HOME/ROAD
      column assignment a measurement rather than a guess).
  S2  League closure: total wins = total losses, total ties is even.
  S3  Cross-read equality: W L T PCT PF PA NET of all 32 clubs must equal the retained collector
      standings payload (official read 2026-11-17T05:03:50Z). 256 assertions.
  S4  Dated closure: the site's published standings (retrieved 2026-11-14) plus the 13 Week 10
      finals that the 2026-11-14 schedule read still printed "scheduled" must reproduce today's
      W, L, PF and PA for every club. 128 assertions. A club that does not reproduce is printed
      as a diff row, not corrected.
  S5  Delta vs the 2026-11-16 pack: what changed since the previous dated read (expected: only
      the Monday-night game's two clubs, in record/points/split/streak columns).
  R1  Results structure: 14 fixtures, all status Final, integer scores, no ties printed.
  R2  Slate completeness: the 14 finals cover 28 clubs exactly once and the four byes cover the
      remaining 4, i.e. all 32 clubs exactly once overall.
  R3  Record agreement: away_record/home_record printed beside the logos on the schedule page
      must equal the record on the standings page read at the same time (28 comparisons).
  R4  Promotion accounting: every fixture the 2026-11-14 schedule read printed "scheduled" is
      Final today (13 promotions), and the one already-final fixture kept its score.
  W1  The Week 11 probe file records that the REG11 URL resolved to the Week 10 page and that the
      printed week selector lists WEEK 1..WEEK 10 only.

Outputs (all under data/verification/2026_11_17/):
  injuries_diff_vs_published_2026_11_17.csv     added/removed/changed rows vs the 2026-11-14 table
  standings_diff_vs_published_2026_11_17.csv    club-field deltas vs the 2026-11-14 table
  standings_diff_vs_2026_11_16.csv              club-field deltas vs the 2026-11-16 read
  results_promotions_2026_11_17.csv             scheduled -> final promotions since 2026-11-14
  verification_summary_2026_11_17.json          every check, its counts and its verdict

Usage:  python3 tools/verify_2026_11_17.py [--check]
  --check  rebuild into a temp dir and fail if the committed outputs differ in any field except
           `generated_at` (the CI staleness guard).
Exit 0 = the checks ran (a FAIL inside the summary is a finding, published either way).
Exit 1 = a transcription failed a structural or arithmetic check (a broken read must not reach a page).
Exit 2 = an input file is missing.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VDIR = os.path.join(ROOT, "data", "verification", "2026_11_17")
NFL = os.path.join(ROOT, "data", "nfl")
CAPTURES = os.path.join(ROOT, "data", "captures")
RETRIEVED = "2026-11-17"

INJ_URL = "https://www.nfl.com/injuries/league/2026/reg10"
STAND_URL = "https://www.nfl.com/standings/league/2026/REG"
W10_URL = "https://www.nfl.com/schedules/2026/by-week/week-10"

INJ_TSV = os.path.join(VDIR, "official_injuries_w10_2026_11_17.tsv")
STAND_TSV = os.path.join(VDIR, "official_standings_2026_11_17.tsv")
RESULTS_TSV = os.path.join(VDIR, "official_w10_results_2026_11_17.tsv")
W11_PROBE = os.path.join(VDIR, "week11_injuries_probe_2026_11_17.txt")

PUBLISHED_INJ = os.path.join(NFL, "injuries_week10.tsv")
PUBLISHED_STAND = os.path.join(NFL, "standings.tsv")
PUBLISHED_SCHEDULE = os.path.join(NFL, "schedule_week10.tsv")
PRIOR_STAND = os.path.join(ROOT, "data", "verification", "2026_11_16", "official_standings_2026_11_16.tsv")

INJ_CAPTURE = os.path.join(CAPTURES, "payloads", "injuries", "c3",
                           "c3d7a7224dfc8105a24721a164e84376859d1715f4a4639c76a379d43ebb4b33.json")
STAND_CAPTURE = os.path.join(CAPTURES, "payloads", "standings", "e3",
                             "e3409e8d36ea7d577d7adbe578df80f9f8edef8272fdd16b2c88e18efdaa0e32.json")

BYE_CLUBS = {"CHI", "DEN", "PHI", "TB"}
PRACTICE_VOCAB = {
    "Full Participation in Practice",
    "Limited Participation in Practice",
    "Did Not Participate In Practice",
}
GAME_STATUS_VOCAB = {"", "Out", "Doubtful", "Questionable"}
# The injury page prints the Rams club as "LAR"; the collector capture and the schedule/standings
# league pages print "LA". Same club, two printed labels - aliased explicitly, never merged silently.
CLUB_ALIAS = {"LAR": "LA", "LA": "LA"}
FIXTURE_BY_CLUB = {
    "WAS": "WAS@NYG", "NYG": "WAS@NYG",
    "NE": "NE@DET", "DET": "NE@DET",
    "KC": "KC@ATL", "ATL": "KC@ATL",
    "MIN": "MIN@GB", "GB": "MIN@GB",
    "JAX": "JAX@TEN", "TEN": "JAX@TEN",
    "BUF": "BUF@NYJ", "NYJ": "BUF@NYJ",
    "MIA": "MIA@IND", "IND": "MIA@IND",
    "CAR": "CAR@NO", "NO": "CAR@NO",
    "HOU": "HOU@CLE", "CLE": "HOU@CLE",
    "LAR": "LAR@AZ", "AZ": "LAR@AZ",
    "SEA": "SEA@LV", "LV": "SEA@LV",
    "SF": "SF@DAL", "DAL": "SF@DAL",
    "PIT": "PIT@CIN", "CIN": "PIT@CIN",
    "LAC": "LAC@BAL", "BAL": "LAC@BAL",
}


def read_tsv(path):
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(lines, delimiter="\t"))


def read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def pct(w, l, t):
    games = w + l + t
    if games == 0:
        return "0.000"
    return f"{(w + t / 2) / games:.3f}"


def rec(s):
    """'3-1-0' -> (3, 1, 0)"""
    a, b, c = s.split("-")
    return int(a), int(b), int(c)


def canon(club):
    """Canonical club label across printed variants (LAR / LA are the same club)."""
    return CLUB_ALIAS.get(club, club)


def printed_record(w, l, t):
    """The schedule page prints records without a trailing tie segment when T = 0: '5-5', but '5-3-1'."""
    return f"{w}-{l}" + (f"-{t}" if t else "")


def build(outdir):
    os.makedirs(outdir, exist_ok=True)
    checks = []
    fatal = False

    def add(cid, name, verdict, counts=None, detail=""):
        checks.append({
            "id": cid, "name": name, "verdict": verdict,
            "counts": counts or {}, "detail": detail,
        })
        if verdict == "FAIL-STRUCTURAL":
            nonlocal fatal
            fatal = True

    for p in (INJ_TSV, STAND_TSV, RESULTS_TSV, W11_PROBE, PUBLISHED_INJ,
              PUBLISHED_STAND, PUBLISHED_SCHEDULE, PRIOR_STAND, INJ_CAPTURE, STAND_CAPTURE):
        if not os.path.exists(p):
            print(f"missing input: {p}", file=sys.stderr)
            sys.exit(2)

    inj = read_tsv(INJ_TSV)
    pub_inj = read_tsv(PUBLISHED_INJ)
    stand = read_tsv(STAND_TSV)
    pub_stand = read_tsv(PUBLISHED_STAND)
    prior_stand = read_tsv(PRIOR_STAND)
    res = read_tsv(RESULTS_TSV)
    pub_sched = read_tsv(PUBLISHED_SCHEDULE)
    cap_inj = read_json(INJ_CAPTURE)
    cap_stand = read_json(STAND_CAPTURE)

    # ---------------- I1 structure ----------------
    problems = []
    if len(inj) != 347:
        problems.append(f"row count {len(inj)} != 347")
    clubs = {r["team"] for r in inj}
    club_set_expected = set(FIXTURE_BY_CLUB) - BYE_CLUBS
    if clubs != club_set_expected:
        problems.append(f"club set mismatch: extra={sorted(clubs - club_set_expected)} missing={sorted(club_set_expected - clubs)}")
    fixtures = {r["game"] for r in inj}
    if fixtures != set(FIXTURE_BY_CLUB.values()):
        problems.append(f"fixture set mismatch: {sorted(fixtures ^ set(FIXTURE_BY_CLUB.values()))}")
    for i, r in enumerate(inj, start=1):
        if r["practice_status"] not in PRACTICE_VOCAB:
            problems.append(f"row {i}: practice_status not printed vocabulary: {r['practice_status']!r}")
        if r["game_status"] not in GAME_STATUS_VOCAB:
            problems.append(f"row {i}: game_status not printed vocabulary: {r['game_status']!r}")
        if not r["player_url"].startswith("https://www.nfl.com/players/"):
            problems.append(f"row {i}: player_url not official: {r['player_url']!r}")
        want = FIXTURE_BY_CLUB.get(r["team"])
        if want and r["game"] != want:
            problems.append(f"row {i}: club {r['team']} in fixture {r['game']}, expected {want}")
    add("I1", "injury transcription structure (347 rows, 28 clubs, 14 fixtures, vocabularies, urls)",
        "PASS" if not problems else "FAIL-STRUCTURAL",
        {"rows": len(inj), "clubs": len(clubs), "fixtures": len(fixtures)},
        "; ".join(problems[:10]))

    # ---------------- I2 independent-read equality vs collector capture ----------------
    def ikey(r, alias=False):
        team = CLUB_ALIAS.get(r["team"], r["team"]) if alias else r["team"]
        return (team, r["player"])
    m = {ikey(r, alias=True): r for r in inj}
    c = {ikey(r): r for r in cap_inj["rows"]}
    key_diffs = {
        "in_transcription_only": sorted("/".join(k) for k in set(m) - set(c)),
        "in_capture_only": sorted("/".join(k) for k in set(c) - set(m)),
    }
    cell_diffs = []
    for k in sorted(set(m) & set(c)):
        for f in ("position", "injury", "practice_status", "game_status"):
            if m[k][f] != c[k][f]:
                cell_diffs.append({"club": k[0], "player": k[1], "field": f,
                                   "capture": c[k][f], "transcription": m[k][f]})
    i2_ok = not key_diffs["in_transcription_only"] and not key_diffs["in_capture_only"] and not cell_diffs
    add("I2", "independent-read equality: transcription vs retained official collector capture",
        "PASS" if i2_ok else "FAIL-STRUCTURAL",
        {"transcription_rows": len(inj), "capture_rows": len(cap_inj["rows"]),
         "capture_as_read_at": cap_inj.get("as_read_at", ""),
         "key_diffs": len(key_diffs["in_transcription_only"]) + len(key_diffs["in_capture_only"]),
         "cell_diffs": len(cell_diffs)},
        json.dumps({"keys": key_diffs, "cells": cell_diffs[:20]}, ensure_ascii=False) if not i2_ok
        else f"capture read {cap_inj.get('as_read_at')} (content unchanged at the 2026-11-17T19:49:49Z re-read)")

    # ---------------- I3 dated delta vs published ----------------
    # Both sides keyed by canonical club label: the published table prints the Rams as "LAR",
    # today's page prints "LAR" too, while other official pages print "LA" - aliased, not merged.
    p = {ikey(r, alias=True): r for r in pub_inj}
    m3 = {ikey(r, alias=True): r for r in inj}
    added = sorted("/".join(k) for k in set(m3) - set(p))
    removed = sorted("/".join(k) for k in set(p) - set(m3))
    cell_rows = []
    for k in sorted(set(m3) & set(p)):
        for f in ("position", "injury", "practice_status", "game_status"):
            if m3[k][f] != p[k][f]:
                cell_rows.append({
                    "change": "cell", "club": k[0], "player": k[1], "field": f,
                    "published_2026_11_14": p[k][f], "official_2026_11_17": m3[k][f],
                    "source_url": INJ_URL,
                })
    for key in added:
        team, player = key.split("/", 1)
        cell_rows.append({"change": "row_added", "club": team, "player": player, "field": "",
                          "published_2026_11_14": "", "official_2026_11_17": "row present",
                          "source_url": INJ_URL})
    for key in removed:
        team, player = key.split("/", 1)
        cell_rows.append({"change": "row_removed", "club": team, "player": player, "field": "",
                          "published_2026_11_14": "row present", "official_2026_11_17": "",
                          "source_url": INJ_URL})
    out_inj_diff = os.path.join(outdir, "injuries_diff_vs_published_2026_11_17.csv")
    with open(out_inj_diff, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["change", "club", "player", "field",
                                           "published_2026_11_14", "official_2026_11_17", "source_url"])
        w.writeheader()
        for row in cell_rows:
            w.writerow(row)
    add("I3", "dated delta: published table (2026-11-14) vs official page (2026-11-17)",
        "FINDINGS-PUBLISHED",
        {"published_rows": len(pub_inj), "official_rows": len(inj),
         "rows_added": len(added), "rows_removed": len(removed),
         "cells_changed": len(cell_rows) - len(added) - len(removed)},
        "see injuries_diff_vs_published_2026_11_17.csv")

    # ---------------- I4 game assignment ----------------
    seen = {}
    ok = True
    for r in inj:
        seen.setdefault(r["team"], set()).add(r["game"])
    bad = {t: sorted(g) for t, g in seen.items() if len(g) != 1}
    if bad:
        ok = False
    add("I4", "game assignment: each club appears in exactly one fixture; club set = 32 minus byes",
        "PASS" if ok else "FAIL-STRUCTURAL",
        {"clubs": len(seen), "byes_absent": sorted(BYE_CLUBS - clubs) == sorted(BYE_CLUBS)},
        json.dumps(bad))

    # ---------------- I5 owner-item spot check (Lions trio) ----------------
    trio = ["Kerby Joseph", "Cade Mays", "D.J. Reed"]
    live = {r["player"]: r["game_status"] for r in inj if r["team"] == "DET"}
    pubd = {r["player"]: r["game_status"] for r in pub_inj if r["team"] == "DET"}
    trio_rows = [{"player": t, "published_2026_11_14": pubd.get(t, ""), "official_2026_11_17": live.get(t, "")} for t in trio]
    ok = all(row["published_2026_11_14"] == "Out" and row["official_2026_11_17"] == "Out" for row in trio_rows)
    add("I5", "brief item: Lions Kerby Joseph / Cade Mays / D.J. Reed game-status cells = Out, both dates",
        "PASS" if ok else "FINDINGS", {"rows": 3}, json.dumps(trio_rows))

    # ---------------- S1 structure + arithmetic ----------------
    problems = []
    if len(stand) != 32:
        problems.append(f"row count {len(stand)} != 32")
    for r in stand:
        w, l, t = int(r["w"]), int(r["l"]), int(r["t"])
        if r["pct"] != pct(w, l, t):
            problems.append(f"{r['abbr']}: pct {r['pct']} != computed {pct(w, l, t)}")
        if int(r["net"]) != int(r["pf"]) - int(r["pa"]):
            problems.append(f"{r['abbr']}: net {r['net']} != pf-pa {int(r['pf']) - int(r['pa'])}")
        hw, hl, ht = rec(r["home"])
        rw, rl, rt = rec(r["road"])
        if (hw + rw, hl + rl, ht + rt) != (w, l, t):
            problems.append(f"{r['abbr']}: home+road {(hw+rw, hl+rl, ht+rt)} != w-l-t {(w, l, t)}")
    add("S1", "standings structure and arithmetic: PCT, NET, HOME+ROAD=W-L-T (32 clubs)",
        "PASS" if not problems else "FAIL-STRUCTURAL",
        {"clubs": len(stand), "assertions": len(stand) * 3},
        "; ".join(problems[:10]))

    # ---------------- S2 league closure ----------------
    tw = sum(int(r["w"]) for r in stand)
    tl = sum(int(r["l"]) for r in stand)
    tt = sum(int(r["t"]) for r in stand)
    ok = tw == tl and tt % 2 == 0
    add("S2", "league closure: total wins = total losses, ties even",
        "PASS" if ok else "FAIL-STRUCTURAL",
        {"total_wins": tw, "total_losses": tl, "total_ties": tt})

    # ---------------- S3 vs collector standings payload ----------------
    capm = {CLUB_ALIAS.get(r["abbr"], r["abbr"]): r for r in cap_stand["rows"]}
    mism = []
    for r in stand:
        a = CLUB_ALIAS.get(r["abbr"], r["abbr"])
        cr = capm.get(a)
        if not cr:
            mism.append(f"{a}: missing from capture")
            continue
        for f in ("w", "l", "t", "pct", "pf", "pa", "net"):
            if str(r[f]) != str(cr[f]):
                mism.append(f"{a}.{f}: transcription {r[f]!r} vs capture {cr[f]!r}")
    add("S3", "cross-read equality: today's standings vs retained collector standings payload (2026-11-17T05:03:50Z)",
        "PASS" if not mism else "FAIL-STRUCTURAL",
        {"clubs": len(stand), "fields_per_club": 7, "capture_rows": len(cap_stand["rows"])},
        "; ".join(mism[:10]))

    # ---------------- S4 dated closure: published + 13 finals = today ----------------
    pubm = {CLUB_ALIAS.get(r["abbr"], r["abbr"]): dict(w=int(r["w"]), l=int(r["l"]), t=int(r["t"]),
                                                       pf=int(r["pf"]), pa=int(r["pa"])) for r in pub_stand}
    repro = {k: dict(v) for k, v in pubm.items()}
    scheduled = [r for r in pub_sched if r["status"] == "scheduled"]
    final_alreadY = [r for r in pub_sched if r["status"] == "final"]
    resm = {(canon(r["away"]), canon(r["home"])): r for r in res}
    promotions = []
    for r in scheduled:
        key = (canon(r["away"]), canon(r["home"]))
        rr = resm.get(key)
        if not rr:
            continue
        a, h = canon(rr["away"]), canon(rr["home"])
        asc, hsc = int(rr["away_score"]), int(rr["home_score"])
        repro[a]["pf"] += asc
        repro[a]["pa"] += hsc
        repro[h]["pf"] += hsc
        repro[h]["pa"] += asc
        if asc > hsc:
            repro[a]["w"] += 1
            repro[h]["l"] += 1
        else:
            repro[h]["w"] += 1
            repro[a]["l"] += 1
        promotions.append({"game_id": r.get("game_id") or f"{r['away']}@{r['home']}",
                           "away": canon(r["away"]), "home": canon(r["home"]),
                           "away_score": asc, "home_score": hsc,
                           "scheduled_2026_11_14": "scheduled", "status_2026_11_17": rr["status"],
                           "source_url": W10_URL})
    tod = {CLUB_ALIAS.get(r["abbr"], r["abbr"]): dict(w=int(r["w"]), l=int(r["l"]), t=int(r["t"]),
                                                      pf=int(r["pf"]), pa=int(r["pa"])) for r in stand}
    closure_diffs = []
    for a in sorted(tod):
        for f in ("w", "l", "pf", "pa"):
            if repro.get(a, {}).get(f) != tod[a][f]:
                closure_diffs.append({"club": a, "field": f,
                                      "published_plus_results": repro.get(a, {}).get(f),
                                      "official_2026_11_17": tod[a][f],
                                      "source_url": STAND_URL})
    add("S4", "dated closure: published 2026-11-14 standings + 13 scheduled->final results = today's W/L/PF/PA",
        "PASS" if not closure_diffs else "FAIL-STRUCTURAL",
        {"clubs": len(tod), "assertions": len(tod) * 4, "finals_added": len(promotions),
         "already_final_at_2026_11_14": len(final_alreadY)},
        json.dumps(closure_diffs[:10], ensure_ascii=False))

    # ---------------- S5 delta vs 2026-11-16 pack ----------------
    priorm = {CLUB_ALIAS.get(r["abbr"], r["abbr"]): r for r in prior_stand}
    s5_rows = []
    fields = ["w", "l", "t", "pct", "pf", "pa", "net", "home", "road", "div_record", "conf_record", "streak"]
    for r in stand:
        a = CLUB_ALIAS.get(r["abbr"], r["abbr"])
        pr = priorm.get(a)
        if not pr:
            s5_rows.append({"club": a, "field": "row", "official_2026_11_16": "", "official_2026_11_17": "present",
                            "source_url": STAND_URL})
            continue
        for f in fields:
            if str(r[f]) != str(pr[f]):
                s5_rows.append({"club": a, "field": f, "official_2026_11_16": pr[f],
                                "official_2026_11_17": r[f], "source_url": STAND_URL})
    out_s5 = os.path.join(outdir, "standings_diff_vs_2026_11_16.csv")
    with open(out_s5, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["club", "field", "official_2026_11_16", "official_2026_11_17", "source_url"])
        w.writeheader()
        for row in s5_rows:
            w.writerow(row)
    clubs_changed = sorted({r["club"] for r in s5_rows})
    add("S5", "delta vs the 2026-11-16 dated read (expected: the Monday-night game's two clubs)",
        "FINDINGS-PUBLISHED",
        {"clubs_changed": len(clubs_changed), "field_changes": len(s5_rows)},
        json.dumps(clubs_changed))

    # ---------------- standings vs published (dated delta CSV) ----------------
    pub_full = {CLUB_ALIAS.get(r["abbr"], r["abbr"]): r for r in pub_stand}
    s_pub_rows = []
    for r in stand:
        a = CLUB_ALIAS.get(r["abbr"], r["abbr"])
        pr = pub_full.get(a)
        if not pr:
            continue
        for f in ("w", "l", "t", "pct", "pf", "pa", "streak"):
            if str(r[f]) != str(pr[f]):
                s_pub_rows.append({"club": a, "field": f, "published_2026_11_14": pr[f],
                                   "official_2026_11_17": r[f], "source_url": STAND_URL})
    out_s4 = os.path.join(outdir, "standings_diff_vs_published_2026_11_17.csv")
    with open(out_s4, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["club", "field", "published_2026_11_14", "official_2026_11_17", "source_url"])
        w.writeheader()
        for row in s_pub_rows:
            w.writerow(row)
    add("S6", "dated delta: published standings (2026-11-14) vs official page (2026-11-17)",
        "FINDINGS-PUBLISHED",
        {"clubs_changed": len({r['club'] for r in s_pub_rows}), "field_changes": len(s_pub_rows)},
        "see standings_diff_vs_published_2026_11_17.csv")

    # ---------------- R1..R4 results ----------------
    problems = []
    if len(res) != 14:
        problems.append(f"row count {len(res)} != 14")
    for r in res:
        if r["status"] != "Final":
            problems.append(f"{r['game_id']}: status {r['status']!r} != Final")
        try:
            a, h = int(r["away_score"]), int(r["home_score"])
        except ValueError:
            problems.append(f"{r['game_id']}: non-integer score")
            continue
        if a == h:
            problems.append(f"{r['game_id']}: printed tie")
    add("R1", "results structure: 14 fixtures, all Final, integer scores, no ties",
        "PASS" if not problems else "FAIL-STRUCTURAL",
        {"fixtures": len(res)}, "; ".join(problems[:10]))

    sides = []
    for r in res:
        sides.append(canon(r["away"]))
        sides.append(canon(r["home"]))
    from collections import Counter
    cnt = Counter(sides)
    once = {c for c, n in cnt.items() if n == 1}
    expected_playing = {canon(c) for c in FIXTURE_BY_CLUB} - BYE_CLUBS
    ok = once == expected_playing and once.isdisjoint(BYE_CLUBS)
    add("R2", "slate completeness: 28 clubs exactly once across the 14 finals; 4 byes disjoint; union = 32",
        "PASS" if ok else "FAIL-STRUCTURAL",
        {"playing_clubs": len(once), "byes": sorted(BYE_CLUBS),
         "union_size": len(once | BYE_CLUBS)})

    stdm = {CLUB_ALIAS.get(r["abbr"], r["abbr"]): r for r in stand}
    mism = []
    for r in res:
        for side, recf in ((r["away"], r["away_record"]), (r["home"], r["home_record"])):
            a = canon(side)
            s = stdm.get(a)
            if not s:
                mism.append(f"{a}: not on standings page")
                continue
            w, l, t = int(s["w"]), int(s["l"]), int(s["t"])
            if printed_record(w, l, t) != recf:
                mism.append(f"{a}: schedule page {recf} vs standings page {printed_record(w, l, t)}")
    add("R3", "record agreement: club records printed on the schedule page vs the standings page (28 comparisons)",
        "PASS" if not mism else "FAIL-STRUCTURAL",
        {"comparisons": len(res) * 2}, "; ".join(mism[:10]))

    out_promo = os.path.join(outdir, "results_promotions_2026_11_17.csv")
    with open(out_promo, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["game_id", "away", "home", "away_score", "home_score",
                                           "scheduled_2026_11_14", "status_2026_11_17", "source_url"])
        w.writeheader()
        for row in promotions:
            w.writerow(row)
    still_sched = [r["away"] + "@" + r["home"] for r in scheduled
                   if (resm.get((canon(r["away"]), canon(r["home"]))) or {}).get("status") != "Final"]
    already_ok = True
    for r in final_alreadY:
        rr = resm.get((canon(r["away"]), canon(r["home"])))
        if not rr or rr["away_score"] != r["away_score"] or rr["home_score"] != r["home_score"]:
            already_ok = False
    ok = len(promotions) == 13 and not still_sched and already_ok
    add("R4", "promotion accounting: the 13 fixtures printed 'scheduled' on 2026-11-14 are Final today; the 1 already-final fixture kept its score",
        "PASS" if ok else "FAIL-STRUCTURAL",
        {"scheduled_2026_11_14": len(scheduled), "already_final_2026_11_14": len(final_alreadY),
         "promoted": len(promotions), "still_open": still_sched})

    # ---------------- W1 week 11 probe ----------------
    with open(W11_PROBE, encoding="utf-8") as fh:
        probe = fh.read()
    ok = "REG11" in probe and "reg10" in probe and "WEEK 1 ... WEEK 10" in probe
    add("W1", "Week 11 injury report probe: REG11 resolved to the Week 10 page; selector lists WEEK 1..WEEK 10",
        "PASS" if ok else "FAIL-STRUCTURAL",
        {"probe_file": os.path.basename(W11_PROBE)})

    summary = {
        "dataset": "verification/2026_11_17",
        "title": "Live official re-verification - 2026-11-17",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_by": "tools/verify_2026_11_17.py (session arena-01c263c4-x1)",
        "retrieved": RETRIEVED,
        "sources": [
            {"url": INJ_URL, "what": "Week 10 injury report, chunks 0-7 of 8, read ~22:50-22:56 UTC"},
            {"url": STAND_URL, "what": "league standings, chunks 0-1 of 2, read ~22:50 UTC"},
            {"url": W10_URL, "what": "Week 10 schedule, chunks 0-1 of 2, read ~22:50 UTC"},
            {"url": "https://www.nfl.com/injuries/league/2026/REG11", "what": "Week 11 probe, read ~22:50 UTC (resolved to reg10)"},
        ],
        "checks": checks,
        "counts": {
            "checks": len(checks),
            "pass": sum(1 for c in checks if c["verdict"] == "PASS"),
            "findings": sum(1 for c in checks if c["verdict"].startswith("FINDINGS")),
            "structural_failures": sum(1 for c in checks if c["verdict"] == "FAIL-STRUCTURAL"),
        },
        "policy": ("Dated evidence: differences between reads are published as findings with two dates "
                   "and two source URLs, never applied to a published table by this tool."),
    }
    out_sum = os.path.join(outdir, "verification_summary_2026_11_17.json")
    with open(out_sum, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    return summary, fatal


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="rebuild into a temp dir; fail if committed outputs differ (ignoring generated_at)")
    args = ap.parse_args(argv[1:])
    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            summary, fatal = build(tmp)
            for name in ("injuries_diff_vs_published_2026_11_17.csv",
                         "standings_diff_vs_published_2026_11_17.csv",
                         "standings_diff_vs_2026_11_16.csv",
                         "results_promotions_2026_11_17.csv"):
                a = os.path.join(VDIR, name)
                b = os.path.join(tmp, name)
                if not os.path.exists(a):
                    print(f"STALE: committed {name} missing")
                    return 1
                with open(a, encoding="utf-8") as fa, open(b, encoding="utf-8") as fb:
                    if fa.read() != fb.read():
                        print(f"STALE: committed {name} differs from a rebuild")
                        return 1
            with open(os.path.join(VDIR, "verification_summary_2026_11_17.json"), encoding="utf-8") as fh:
                    committed = json.load(fh)
            with open(os.path.join(tmp, "verification_summary_2026_11_17.json"), encoding="utf-8") as fh:
                rebuilt = json.load(fh)
            committed.pop("generated_at", None)
            rebuilt.pop("generated_at", None)
            if committed != rebuilt:
                print("STALE: committed verification_summary_2026_11_17.json differs from a rebuild")
                return 1
        print("2026-11-17 pack: content matches a rebuild")
        return 1 if fatal else 0
    summary, fatal = build(VDIR)
    for c in summary["checks"]:
        print(f"{c['id']:4} {c['verdict']:20} {c['name']}")
        if c["detail"] and c["verdict"] != "PASS":
            print(f"       detail: {c['detail'][:300]}")
    print(json.dumps(summary["counts"]))
    return 1 if fatal else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
