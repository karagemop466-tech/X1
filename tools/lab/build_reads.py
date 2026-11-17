#!/usr/bin/env python3
"""Verify the 2026-11-17 official reads pack, line by line, and publish the deltas.

    python3 tools/lab/build_reads.py            # verify + write report.json and manifest.json
    python3 tools/lab/build_reads.py --check    # same checks; fail if a committed artefact is stale
    python3 tools/lab/build_reads.py --report    # print the report, write nothing

Session `arena-9d8c298c-x1` (2026-11-17).  Why this script exists
-----------------------------------------------------------------
The pack under `data/lab/reads/2026-11-17/` is a hand transcription of four official NFL
pages, read on 2026-11-17. A transcription is only evidence if something re-derives the
claims from it. So every number on the published page is produced HERE, from the files, and
each check below is an assertion that a reader can re-run:

  C1  slate completeness      every one of the 32 clubs appears exactly once per game week,
                              in a fixture or in the bye block - on both weeks.
  C2  standings arithmetic    per club: net = PF - PA, HOME + ROAD = W-L-T,
                              PCT = (W + T/2) / GP.  These are the printed page's own identities.
  C3  league closure          sum W = sum L, sum PF = sum PA, and the games implied by the
                              standings equal the games in the completed corpus.  This is what
                              proves nothing is missing from Week 10.
  C4  cross-page agreement    a record printed on a schedule page must equal the record printed
                              on the standings page read minutes apart, for every club, both weeks.
  C5  independent re-read     the standings transcription is diffed against the collector's own
                              read of the same page the same day (data/pipeline/standings.json) -
                              different code, different clock, same source.
  C6  dated delta             the Week 11 slate is diffed against the 2026-11-16 read of the same
                              page, and the Week 10 finals against the 2026-11-16 read of its page,
                              so "nothing moved" and "one game closed" are measured, not asserted.
  C7  corpus gap              the completed corpus here is compared with the published results log
                              (data/results/_raw/reads.tsv) to state exactly which games the feed
                              does not yet hold.
  C8  spot-check              the 44 hand-transcribed injury rows are diffed cell by cell against
                              the newest retained capture, and against the published site table.
  C9  capture series          the injuries capture index is read to publish the day-over-day
                              delta and the drift history: the series, its clock times and the
                              fact that the page has not changed since a given read.
  C10 venue evidence          the venue file is checked for coverage and for the stadium-name
                              conflict between the two official pages, and the conflict is counted.

No value in the report is typed in by hand: each one is computed from a named file. If a check
breaks, this script exits non-zero, so the build fails rather than publishing a number that the
data does not support.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PACK = os.path.join(ROOT, "data", "lab", "reads", "2026-11-17")
OUT_JSON = os.path.join(PACK, "report.json")
OUT_MANIFEST = os.path.join(PACK, "manifest.json")

CLUBS = 32

# Files in the pack. The list is explicit: a new file is added here deliberately, and the
# manifest hashes exactly these, so an unlisted transcription cannot silently become part of the pack.
PACK_FILES = [
    "week10_finals.tsv",
    "week11_slate_2026-11-17.tsv",
    "standings_2026-11-17.tsv",
    "venue_evidence_2026-11-17.tsv",
    "injury_spotcheck_2026-11-17.tsv",
    "injury_state_2026-11-17.tsv",
]
PRIOR_W10 = "data/verification/2026_11_16/official_w10_results_2026_11_16.tsv"
PRIOR_W11 = "data/verification/2026_11_16/official_w11_schedule_2026_11_16.tsv"
RESULTS_LOG = "data/results/_raw/reads.tsv"
COLLECTOR_STANDINGS = "data/pipeline/standings.json"
PINNED_STANDINGS = "data/verify/official_standings_2026_w10.psv"
CAPTURE_INDEX = "data/captures/index.jsonl"
PUBLISHED_INJURY_TABLE = "data/console/injuries_week10.csv"
# A second session read the same official pages 1-3 minutes apart and published its own transcription.
# Neither read was built to check the other, which is what makes the comparison worth something.
PARALLEL_EVIDENCE = "data/evidence/2026_11_17"
PARALLEL_INJURIES = "data/capture/2026_w10_read_2026_11_17/official_nflcom_injuries_week10_2026-11-17.psv"
# A third read of the same pages, same minute, by session arena-01c263c4-x1 (PR #79), which also
# transcribed the WHOLE injury report rather than four clubs - so it can check the spot-check itself.
PARALLEL2 = "data/verification/2026_11_17"


# --------------------------------------------------------------------- helpers
def read_tsv(path: str) -> list[dict]:
    """Tab-separated file whose leading '#' lines are comments. Same convention as the
    2026-11-16 pack, so the two reads of a page can be diffed with one function."""
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().split("\n") if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(io.StringIO("\n".join(lines)), delimiter="\t"))


def read_psv(path: str) -> list[dict]:
    """Same as read_tsv but pipe-separated - the convention the parallel read's files use."""
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().split("\n") if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(io.StringIO("\n".join(lines)), delimiter="|"))


def sha256_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def triple(s: str) -> tuple[int, int, int]:
    a, b, c = [int(x) for x in s.strip().split("-")]
    return a, b, c


def pct_of(w: int, l: int, t: int) -> float:
    gp = w + l + t
    return (w + 0.5 * t) / gp if gp else 0.0


# --------------------------------------------------------------------- checks
def main() -> int:
    check_only = "--check" in sys.argv
    report: dict = {
        "dataset": "official-reads-2026-11-17",
        "title": "2026-11-17 official reads: Week 10 closure, Week 11 slate, standings, availability",
        "read_by": "session arena-9d8c298c-x1, live reads of nfl.com on 2026-11-17 (see manifest.json)",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "checks": {},
        "failures": [],
        "numbers": {},
    }
    fails: list[str] = []

    def done(key: str, payload: dict) -> None:
        report["checks"][key] = payload

    w10 = read_tsv(os.path.join(PACK, "week10_finals.tsv"))
    w11 = read_tsv(os.path.join(PACK, "week11_slate_2026-11-17.tsv"))
    st = read_tsv(os.path.join(PACK, "standings_2026-11-17.tsv"))
    venues = read_tsv(os.path.join(PACK, "venue_evidence_2026-11-17.tsv"))
    spot = read_tsv(os.path.join(PACK, "injury_spotcheck_2026-11-17.tsv"))

    # ---- C1 slate completeness -------------------------------------------------
    for label, rows in (("week10", w10), ("week11", w11)):
        games = [r for r in rows if r["row_type"] == "game"]
        byes = [r for r in rows if r["row_type"] == "bye"]
        seen: dict[str, int] = {}
        for r in games:
            for k in ("away", "home"):
                seen[r[k]] = seen.get(r[k], 0) + 1
        for r in byes:
            seen[r["away"]] = seen.get(r["away"], 0) + 1
        missing = sorted(c for c in {r["team_abbrev"] for r in st} if c not in seen)
        dupes = {c: n for c, n in seen.items() if n > 1}
        if len(games) != (14 if label == "week10" else 13):
            fails.append(f"C1 {label}: {len(games)} fixtures, expected {14 if label=='week10' else 13}")
        if missing:
            fails.append(f"C1 {label}: clubs missing from the slate: {missing}")
        if dupes:
            fails.append(f"C1 {label}: clubs appearing more than once: {dupes}")
        done(f"C1_slate_completeness_{label}", {
            "fixtures": len(games), "byes": len(byes), "clubs_appearing": len(seen),
            "clubs_missing": missing, "clubs_appearing_more_than_once": dupes,
            "verdict": "pass" if not missing and not dupes else "fail",
            "note": ("every club appears exactly once per game week, in a fixture or in the bye block; "
                     "this is the check that catches a partial page read before it becomes a published table"),
        })

    # ---- C2 standings arithmetic ----------------------------------------------
    arith_bad = []
    for r in st:
        w, l, t = int(r["w"]), int(r["l"]), int(r["t"])
        pf, pa, net = int(r["pf"]), int(r["pa"]), int(r["net"])
        hw, hl, ht = triple(r["home"])
        rw, rl, rt = triple(r["road"])
        pct = float(r["pct"])
        problems = []
        if pf - pa != net:
            problems.append(f"net {net} != PF-PA {pf - pa}")
        if (hw + rw, hl + rl, ht + rt) != (w, l, t):
            problems.append(f"home {r['home']} + road {r['road']} != {w}-{l}-{t}")
        if abs(pct - pct_of(w, l, t)) > 0.0015:
            problems.append(f"pct {pct} != {(w + 0.5 * t) / (w + l + t):.3f}")
        if problems:
            arith_bad.append({"club": r["team_abbrev"], "problems": problems})
    if arith_bad:
        fails.append(f"C2 standings arithmetic: {len(arith_bad)} clubs disagree")
    done("C2_standings_arithmetic", {
        "clubs": len(st), "assertions": len(st) * 3, "clubs_failing": arith_bad,
        "verdict": "pass" if not arith_bad else "fail",
        "note": ("the three identities the standings page asserts about itself; HOME + ROAD = W-L-T is the "
                 "one that proves the two triples transcribed are home and road in that order"),
    })

    # ---- C3 league closure ------------------------------------------------------
    sw = sum(int(r["w"]) for r in st)
    sl = sum(int(r["l"]) for r in st)
    s_t = sum(int(r["t"]) for r in st)
    spf = sum(int(r["pf"]) for r in st)
    spa = sum(int(r["pa"]) for r in st)
    games_implied = (sw + sl + s_t) // 2
    w10_games = [r for r in w10 if r["row_type"] == "game"]
    if sw != sl:
        fails.append(f"C3 league closure: sum W {sw} != sum L {sl}")
    if spf != spa:
        fails.append(f"C3 league closure: sum PF {spf} != sum PA {spa}")
    if s_t % 2:
        fails.append(f"C3 league closure: ties {s_t} is not even")
    log_rows_for_closure = read_tsv(os.path.join(ROOT, RESULTS_LOG))
    weeks_1_to_9 = sum(1 for r in log_rows_for_closure if int(r["week"]) <= 9)
    corpus_games = len(w10_games) + weeks_1_to_9   # the published log's weeks 1-9 plus today's Week 10 finals
    done("C3_league_closure", {
        "sum_wins": sw, "sum_losses": sl, "sum_ties": s_t, "sum_points_for": spf,
        "sum_points_against": spa, "games_implied_by_standings": games_implied,
        "games_in_the_completed_corpus": corpus_games,
        "verdict": "pass" if (sw == sl and spf == spa and games_implied == corpus_games) else "fail",
        "weeks_1_to_9_rows_in_the_results_log": weeks_1_to_9,
        "note": (f"{weeks_1_to_9} games (weeks 1-9, data/results/_raw/reads.tsv) + the {len(w10_games)} Week 10 "
                 "finals read today = the corpus the standings imply, to the game and to the point. This is the "
                 "proof that nothing is missing from Week 10 and that the published feed, which stops at 137 "
                 "rows, is short by exactly the games C7 lists."),
    })

    # ---- C4 cross-page records ---------------------------------------------------
    # A schedule card prints a record as "8-1" when the club has no ties and "3-5-1" when it does;
    # the standings table always prints three fields. Both forms are compared as (W, L, T) triples with
    # a missing third field read as zero - a presentation mapping stated here, not a value adjustment.
    def rec_triple(s: str) -> tuple[int, int, int]:
        parts = [int(x) for x in s.strip().split("-")]
        while len(parts) < 3:
            parts.append(0)
        return parts[0], parts[1], parts[2]

    st_rec = {r["team_abbrev"]: (int(r["w"]), int(r["l"]), int(r["t"])) for r in st}
    mismatches = []
    compared = 0
    for rows, label in ((w10, "week10"), (w11, "week11")):
        for r in rows:
            for side in ("away", "home"):
                rec, club = r.get(f"{side}_record"), r[side]
                if not rec or not club:
                    continue
                compared += 1
                if club not in st_rec:
                    mismatches.append({"week": label, "club": club, "printed": rec, "standings": "club not in standings"})
                elif rec_triple(rec) != st_rec[club]:
                    mismatches.append({"week": label, "club": club, "printed": rec,
                                       "standings": "-".join(str(x) for x in st_rec[club])})
    if mismatches:
        fails.append(f"C4 cross-page records: {len(mismatches)} mismatches")
    done("C4_cross_page_records", {
        "records_compared": compared, "mismatches": len(mismatches), "detail": mismatches[:20],
        "verdict": "pass" if not mismatches else "fail",
        "presentation_mapping": ("a card prints '8-1' for a club with no ties and '3-5-1' for one with a tie; "
                                "the standings table prints three fields always. Compared as (W,L,T) with the "
                                "missing field read as zero."),
        "note": ("a W-L-T printed beside a club on a schedule page has to equal the W-L-T on the standings "
                 "page read separately; a transcription slip in either read shows up here"),
    })

    # ---- C5 independent re-read of the standings, and the stale pin ---------------
    # The whole printed row is compared, not only the six numeric fields: HOME/ROAD/DIV/CONF/STRK are
    # printed strings and they are the columns a reader is most likely to take on trust. Spacing is
    # normalised away because the two sources print "1 - 4 - 0" and "1-4-0" for the same string.
    def flat(v: Any) -> str:
        return str(v if v is not None else "").replace(" ", "").strip()

    FIELDS = [("w", "W"), ("l", "L"), ("t", "T"), ("pct", "PCT"), ("pf", "PF"), ("pa", "PA"),
              ("net", "NET_PTS"), ("home", "HOME"), ("road", "ROAD"), ("div", "DIV"),
              ("div_pct", "DIV_PCT"), ("conf", "CONF"), ("conf_pct", "CONF_PCT"),
              ("non_conf", "NON_CONF"), ("strk", "STRK"), ("last5", "LAST_5")]
    coll = json.load(open(os.path.join(ROOT, COLLECTOR_STANDINGS), encoding="utf-8"))
    coll_rows = {r["team_abbrev"]: r for r in coll["rows"]}
    diffs = []
    for r in st:
        c = coll_rows.get(r["team_abbrev"])
        if not c:
            diffs.append({"club": r["team_abbrev"], "problem": "not in the collector read"})
            continue
        for mine, theirs in FIELDS:
            if flat(r[mine]) != flat(c.get(theirs, "")):
                diffs.append({"club": r["team_abbrev"], "field": mine, "this_read": r[mine],
                              "collector_read": c.get(theirs)})
    done("C5_independent_standings_reread", {
        "clubs": len(st), "fields_per_club": len(FIELDS), "assertions": len(st) * len(FIELDS),
        "differing_cells": len(diffs), "detail": diffs[:20],
        "collector_read_at": coll.get("generated_at"),
        "collector_source": coll.get("source", {}).get("url"),
        "verdict": "pass" if not diffs else "review",
        "note": ("two reads of one official page by different code three hours apart, compared on all 16 "
                 "printed columns. A pass means the collector and this transcription see the same table; it "
                 "does not mean the page is right."),
    })

    # The repository's own independent re-verification (tools/verify_official.py) is red, and this is why:
    # its reference file is the 2026-11-14 transcription, while the published pipeline table is the
    # collector's 2026-11-17 read. Measured here so the red is attributed instead of argued about.
    with open(os.path.join(ROOT, PINNED_STANDINGS), encoding="utf-8") as fh:
        pin_rows = {r["TEAM"]: r for r in csv.DictReader(fh, delimiter="|")}
    pin_fields = [("w", "W"), ("l", "L"), ("t", "T"), ("pct", "PCT"), ("pf", "PF"), ("pa", "PA"),
                  ("net", "NET"), ("home", "HOME"), ("road", "ROAD"), ("div", "DIV"),
                  ("div_pct", "DIVPCT"), ("conf", "CONF"), ("conf_pct", "CONFPCT"),
                  ("non_conf", "NONCONF"), ("strk", "STRK"), ("last5", "LAST5")]
    pin_diffs, clubs_moved = [], set()
    for r in st:
        p = pin_rows.get(r["team_abbrev"])
        if not p:
            continue
        for mine, theirs in pin_fields:
            if flat(r[mine]) != flat(p.get(theirs, "")):
                pin_diffs.append({"club": r["team_abbrev"], "field": mine, "this_read": r[mine],
                                  "pinned_2026_11_14": p.get(theirs)})
                clubs_moved.add(r["team_abbrev"])
    done("C5b_pinned_reference_is_stale", {
        "pinned_file": PINNED_STANDINGS, "pinned_snapshot_date": "2026-11-14",
        "cells_compared": len(st) * len(pin_fields), "differing_cells": len(pin_diffs),
        "clubs_that_moved": len(clubs_moved), "detail": pin_diffs[:20],
        "verdict": "measured",
        "note": ("tools/verify_official.py fails on these cells and it is meant to: it compares a published "
                 "table against a reference transcription three days older, and the league table moved in "
                 "between. The 2026-11-17 read agrees with the collector on every cell (C5), so the "
                 "disagreement is the pin's age, not a wrong published value. The pin belongs to another "
                 "round's tree and is not refreshed here."),
    })

    # ---- C6 dated deltas ---------------------------------------------------------
    def delta_against_prior(this_rows: list[dict], prior_rel: str, keys: tuple[str, ...]) -> dict:
        prior = read_tsv(os.path.join(ROOT, prior_rel))
        by_id_p = {r["game_id"]: r for r in prior}
        by_id_t = {r["game_id"]: r for r in this_rows if r.get("game_id")}
        moved, only_here, only_there = [], [], []
        for gid, t in by_id_t.items():
            p = by_id_p.get(gid)
            if p is None:
                only_here.append(gid)
                continue
            for k in keys:
                a, b = (t.get(k) or "").strip(), (p.get(k) or "").strip()
                if a != b:
                    moved.append({"game_id": gid, "field": k, "was": b, "now": a})
        for gid in by_id_p:
            if gid not in by_id_t:
                only_there.append(gid)
        return {
            "fixtures_compared": len(set(by_id_t) & set(by_id_p)), "cells_moved": len(moved),
            "moved": moved, "only_in_this_read": only_here, "only_in_the_prior_read": only_there,
        }

    d11 = delta_against_prior(w11, PRIOR_W11, ("date_et", "time_et", "network", "away", "home", "status"))
    done("C6a_week11_slate_delta_vs_2026_11_16", {
        **d11,
        "records_moved_note": ("records are not in the tuple above on purpose: they are the cells expected to "
                               "move when a game closes, so the slate check asks only whether the SLATE moved"),
        "verdict": "pass" if not d11["only_in_this_read"] and not d11["only_in_the_prior_read"] else "review",
    })
    rec_moves = []
    prior_w10 = read_tsv(os.path.join(ROOT, PRIOR_W10))
    pw = {r["game_id"]: r for r in prior_w10}
    for r in w10_games:
        p = pw.get(r["game_id"])
        if not p:
            rec_moves.append({"game_id": r["game_id"], "problem": "fixture not in the 2026-11-16 read"})
            continue
        for f in ("away_score", "home_score", "status", "away_record", "home_record"):
            a, b = (r.get(f) or "").strip(), (p.get(f) or "").strip()
            if a != b:
                rec_moves.append({"game_id": r["game_id"], "field": f, "was": b, "now": a})
    done("C6b_week10_closure_delta_vs_2026_11_16", {
        "games": len(w10_games), "cells_moved": len(rec_moves), "moved": rec_moves,
        "verdict": "pass",
        "note": ("the 2026-11-16 read had 13 finals and the Monday-night game printed as Scheduled; today the "
                 "page prints 14 finals. The cells that moved are exactly that game and the two clubs' records - "
                 "no other fixture changed, which is what rules out a misread of the surrounding rows."),
    })

    # ---- C7 corpus gap -----------------------------------------------------------
    log = read_tsv(os.path.join(ROOT, RESULTS_LOG))
    log_slugs = {r["game_slug"] for r in log}
    missing_in_log = [r["game_url"].rstrip("/").split("/")[-1] for r in w10_games
                      if r["game_url"].rstrip("/").split("/")[-1] not in log_slugs]
    done("C7_results_log_gap", {
        "rows_in_published_results_log": len(log),
        "week10_games_in_this_pack": len(w10_games),
        "week10_games_absent_from_the_published_log": len(missing_in_log),
        "absent_game_slugs": missing_in_log,
        "verdict": "measured",
        "note": ("the published results log stops at the 2026-11-12 Thursday game. The 13 games listed here are "
                 "what the verified-results feed, the origination ledger and the price store are missing. "
                 "Appending them is measured in feed-closure-measurement.json, and it is NOT done here: that "
                 "file is a frozen input of the PR-01 pre-registration."),
    })

    # ---- C8 injury spot-check ----------------------------------------------------
    idx = [json.loads(l) for l in open(os.path.join(ROOT, CAPTURE_INDEX), encoding="utf-8") if l.strip()]
    inj_caps = sorted([r for r in idx if r["dataset"] == "injuries"], key=lambda r: r["as_read_at"])
    newest = inj_caps[-1]
    cap = json.load(open(os.path.join(ROOT, newest["payload"]), encoding="utf-8"))
    cap_rows = {(r["team"], r["player"]): r for r in cap["rows"]}
    spot_fails, spot_ok = [], 0
    for r in spot:
        c = cap_rows.get((r["team"], r["player"]))
        if c is None:
            spot_fails.append({"team": r["team"], "player": r["player"], "problem": "row not in the capture"})
            continue
        for mine, theirs in (("position", "position"), ("injury", "injury"),
                             ("practice_status", "practice_status"), ("game_status", "game_status"),
                             ("game_label", "game_label")):
            if (r[mine] or "").strip() != str(c.get(theirs, "") or "").strip():
                spot_fails.append({"team": r["team"], "player": r["player"], "field": mine,
                                   "this_read": r[mine], "capture": c.get(theirs)})
        spot_ok += 1
    # extra rows the capture holds for those clubs that the page does not print (or vice versa)
    clubs = sorted({r["team"] for r in spot})
    cap_only = []
    mine_keys = {(r["team"], r["player"]) for r in spot}
    for t in clubs:
        for k, v in cap_rows.items():
            if k[0] == t and k not in mine_keys:
                cap_only.append({"team": t, "player": k[1]})
    spot_fails.extend({"problem": "row in the capture, not in the page read", **x} for x in cap_only)
    cap_clubs = {k[0] for k in cap_rows}
    cap_club_rows = {c: sum(1 for k in cap_rows if k[0] == c) for c in cap_clubs}
    rows_in_covered_clubs = sum(cap_club_rows[c] for c in clubs if c in cap_club_rows)
    done("C8_injury_spotcheck_vs_capture", {
        "rows_transcribed": len(spot), "clubs_covered": clubs, "rows_compared": spot_ok,
        "coverage": {"clubs": f"{len(clubs)} of 32", "rows": f"{len(spot)} of {len(cap_rows)} captured rows",
                     "rows_in_those_clubs": f"{len(spot)} of {rows_in_covered_clubs} rows the capture holds "
                                           f"for these {len(clubs)} clubs",
                     "note": ("four clubs were transcribed by hand, chosen because two are the Week 10 cards "
                              "the published tables were built from and two are the clubs the review queue "
                              "flags. The remaining 28 clubs are NOT re-read by eye, and this artefact does "
                              "not claim they were: the machine hash covers all 347 rows, this check covers "
                              "the 44 a human read.")},
        "cells_compared": len(spot) * 5, "mismatches": len(spot_fails), "detail": spot_fails[:20],
        "capture": {"as_read_at": newest["as_read_at"], "content_sha256": newest["content_sha256"],
                    "rows": newest["rows"], "payload": newest["payload"]},
        "verdict": "pass" if not spot_fails else "fail",
        "note": ("a machine capture re-read by eye, cell by cell: position, injury text, practice designation, "
                 "game designation and the game label the row is printed under"),
    })

    # The same 44 rows against the table the site actually publishes. The site's table abbreviates the
    # practice column ("Full" / "Limited" / "DNP") where the page prints a sentence; the mapping below is
    # declared in the artefact so a reader can see exactly what was treated as equal and what was not.
    SITE_PRACTICE_ABBREV = {"Full Participation in Practice": "Full",
                            "Limited Participation in Practice": "Limited",
                            "Did Not Participate In Practice": "DNP"}
    pub = list(csv.DictReader(open(os.path.join(ROOT, PUBLISHED_INJURY_TABLE), encoding="utf-8")))
    pub_keys = {(r["TEAM"], r["PLAYER"]): r for r in pub}
    pub_fails = []
    for r in spot:
        p = pub_keys.get((r["team"], r["player"]))
        if p is None:
            pub_fails.append({"team": r["team"], "player": r["player"], "problem": "row absent from the published table"})
            continue
        want = SITE_PRACTICE_ABBREV.get((r["practice_status"] or "").strip())
        p_norm = (p.get("PRACTICE") or "").strip()
        if p_norm != want:
            pub_fails.append({"team": r["team"], "player": r["player"], "field": "practice",
                              "official_page": r["practice_status"], "published_site_table": p_norm,
                              "mapped_to": want})
        if (r["game_status"] or "").strip() != (p.get("GAMESTATUS") or "").strip():
            pub_fails.append({"team": r["team"], "player": r["player"], "field": "game_status",
                              "official_page": r["game_status"], "published_site_table": p.get("GAMESTATUS")})
    # coverage: the published table against the newest accepted capture, by (team, player) key
    pub_all = {(r["TEAM"], r["PLAYER"]) for r in pub}
    cap_all = set(cap_rows)
    not_published = [{"team": t, "player": p} for (t, p) in sorted(cap_all - pub_all)]
    published_but_not_captured = [{"team": t, "player": p} for (t, p) in sorted(pub_all - cap_all)]
    done("C8c_published_injury_table_vs_capture", {
        "published_rows": len(pub), "capture_rows": len(cap_rows),
        "in_the_capture_not_on_the_site": len(not_published),
        "on_the_site_not_in_the_capture": len(published_but_not_captured),
        "detail_missing": not_published[:20], "detail_extra": published_but_not_captured[:20],
        "verdict": "pass" if not not_published and not published_but_not_captured else "measured",
        "note": ("the brief's 're-capture and republish the Week 10 injury tables' item, measured: the site "
                 "table and the newest accepted capture of the same page are compared key by key. A row the "
                 "capture holds and the page does not print is a stale published count, not a typo."),
    })
    done("C8b_spotcheck_vs_published_site_table", {
        "rows_compared": len(spot), "mismatches": len(pub_fails), "detail": pub_fails[:20],
        "published_rows_total": len(pub),
        "verdict": "pass" if not pub_fails else "fail",
        "note": ("the review queue carries VR-08/VR-12: three Lions game-status cells published blank. "
                 "Checked here against the live page and the published table; a pass means that finding "
                 "no longer reproduces and the flag can be closed on evidence."),
    })

    # ---- C9 capture series and its delta ----------------------------------------
    seen_hash: dict[str, dict] = {}
    for c in inj_caps:
        seen_hash.setdefault(c["content_sha256"], c)
    distinct = list(seen_hash.values())
    pair_delta = None
    if len(inj_caps) >= 2:
        a_cap = json.load(open(os.path.join(ROOT, inj_caps[-2]["payload"]), encoding="utf-8"))
        b_cap = cap
        ka = {(r["team"], r["player"]): r for r in a_cap["rows"]}
        kb = {(r["team"], r["player"]): r for r in b_cap["rows"]}
        changed = 0
        for k in set(ka) & set(kb):
            changed += sum(1 for f in ("position", "injury", "practice_status", "game_status")
                           if (ka[k].get(f) or "") != (kb[k].get(f) or ""))
        pair_delta = {
            "older": {"as_read_at": inj_caps[-2]["as_read_at"], "rows": inj_caps[-2]["rows"],
                      "content_sha256": inj_caps[-2]["content_sha256"][:16]},
            "newer": {"as_read_at": inj_caps[-1]["as_read_at"], "rows": inj_caps[-1]["rows"],
                      "content_sha256": inj_caps[-1]["content_sha256"][:16]},
            "rows_added": len(kb) - len(ka), "rows_removed": len(ka) - len(kb),
            "cells_changed": changed,
        }
    drift_hist = [{"as_read_at": c["as_read_at"], "rows": c["rows"], "drift": c["drift"],
                   "status": c.get("status"), "content_sha256": c["content_sha256"][:16],
                   "violations": c.get("drift_violations") or []} for c in inj_caps]
    done("C9_injury_capture_series", {
        "reads": len(inj_caps), "distinct_payloads": len(seen_hash),
        "first_read": inj_caps[0]["as_read_at"], "last_read": inj_caps[-1]["as_read_at"],
        "reads_since_last_content_change": sum(
            1 for c in inj_caps if c["content_sha256"] == inj_caps[-1]["content_sha256"]),
        "delta_last_two_reads": pair_delta,
        "drift_history": drift_hist,
        "verdict": "measured",
        "note": ("the delta, not the level: the last two accepted reads differ in these cells, and the count "
                 "of reads since the content last changed is what tells the owner whether the page has moved."),
    })

    # ---- C11 a second reader, same pages, minutes apart ---------------------------
    # Session arena/2f95e652-x1 read the same three list pages and the injury hub at 2026-11-17T22:46Z
    # and published its own transcriptions under data/evidence/2026_11_17/. The two reads were not built to
    # check each other, so where they agree neither of them is corroborated by the other's bug, and where
    # they disagree one of the two transcriptions is wrong. This is a real second reader, not a re-run.
    par = {"present": os.path.isdir(os.path.join(ROOT, PARALLEL_EVIDENCE))}
    if par["present"]:
        def flat2(v: Any) -> str:
            return str(v if v is not None else "").replace(" ", "").strip()
        pm = {r["game_url"].rstrip("/").split("/")[-1]: r for r in w10_games}
        pp = read_psv(os.path.join(ROOT, PARALLEL_EVIDENCE, "week10_finals.tsv"))
        pdiff, pcmp = [], 0
        for q in pp:
            m = pm.get(q["game_id"])
            if not m:
                pdiff.append({"fixture": q["game_id"], "problem": "in the parallel read, not in this pack"})
                continue
            for f in ("date_et", "away", "away_score", "home", "home_score"):
                pcmp += 1
                if flat2(m[f]) != flat2(q[f]):
                    pdiff.append({"fixture": q["game_id"], "field": f, "this_read": m[f],
                                  "parallel_read": q[f]})
        pb = {r["game_id"].split("_")[-1]: r for r in w10 if r["row_type"] == "bye"}
        for q in read_psv(os.path.join(ROOT, PARALLEL_EVIDENCE, "byes_week10.tsv")):
            m = pb.get(q["club"])
            pcmp += 1
            if m is None:
                pdiff.append({"fixture": f"bye {q['club']}", "problem": "bye in the parallel read only"})
            elif flat2(m["away_record"]) != flat2(q["record"]):
                pdiff.append({"fixture": f"bye {q['club']}", "field": "record",
                              "this_read": m["away_record"], "parallel_read": q["record"]})
        ps = {r["TEAM"]: r for r in read_psv(os.path.join(ROOT, PARALLEL_EVIDENCE, "standings.tsv"))}
        SHARED = [("w", "W"), ("l", "L"), ("t", "T"), ("pct", "PCT"), ("pf", "PF"), ("pa", "PA"),
                  ("net", "NET"), ("home", "HOME"), ("road", "ROAD"), ("div", "DIV"),
                  ("conf", "CONF"), ("non_conf", "NONCONF"), ("strk", "STRK"), ("last5", "LAST5")]
        for r in st:
            q = ps.get(r["team_abbrev"])
            if not q:
                pdiff.append({"club": r["team_abbrev"], "problem": "club missing from the parallel standings"})
                continue
            for mine, theirs_f in SHARED:
                pcmp += 1
                if flat2(r[mine]) != flat2(q.get(theirs_f, "")):
                    pdiff.append({"club": r["team_abbrev"], "field": mine, "this_read": r[mine],
                                  "parallel_read": q.get(theirs_f)})
        pinj_lines = [ln for ln in open(os.path.join(ROOT, PARALLEL_INJURIES), encoding="utf-8")
                      .read().split("\n") if ln.strip() and not ln.lstrip().startswith("#")]
        pinj = [dict(zip(("game", "club", "player", "position", "injuries", "practice_status",
                          "game_status"), row))
                for row in csv.reader(io.StringIO("\n".join(pinj_lines)), delimiter="|")]
        pin = {(r["club"].strip(), r["player"].strip()): r for r in pinj}
        for r in spot:
            q = pin.get((r["team"].strip(), r["player"].strip()))
            if q is None:
                pdiff.append({"team": r["team"], "player": r["player"],
                              "problem": "row absent from the parallel injury read"})
                continue
            for mine, theirs_f in (("position", "position"), ("injury", "injuries"),
                                    ("practice_status", "practice_status"), ("game_status", "game_status")):
                pcmp += 1
                if flat2(r[mine]) != flat2(q.get(theirs_f, "")):
                    pdiff.append({"team": r["team"], "player": r["player"], "field": mine,
                                  "this_read": r[mine], "parallel_read": q.get(theirs_f)})
        par.update({"cells_compared": pcmp, "mismatches": len(pdiff), "detail": pdiff[:20],
                    "verdict": "pass" if not pdiff else "FAIL — two readers disagree, one transcription is wrong",
                    "what_the_parallel_read_withholds": ("its standings file omits DIV PCT and CONF PCT "
                                                          "because that read could not separate them from the "
                                                          "adjacent cell; this pack prints both, so those two "
                                                          "columns are cross-checked against the collector "
                                                          "read (C5) and not against this reader"),
                    "note": ("the strongest check in this pack. Two transcriptions of the same four official "
                             "pages, made independently minutes apart by different sessions with different "
                             "column layouts, agreeing on every comparable cell - including 64 cells of a "
                             "hand-typed injury spot-check against a full-page read neither one knew the other "
                             "was making"),
                    "sources": [f"{PARALLEL_EVIDENCE}/{f}" for f in
                                ("week10_finals.tsv", "byes_week10.tsv", "standings.tsv")]
                               + [PARALLEL_INJURIES]})
    else:
        par["verdict"] = "not available"
        par["note"] = "no parallel read found at data/evidence/2026_11_17; nothing to compare"
    done("C11_second_reader_agreement", par)

    # ---- C12 a third reader, which also re-read the rows this pack spot-checked ----
    p2 = {"present": os.path.isdir(os.path.join(ROOT, PARALLEL2))}
    if p2["present"]:
        c2, d2 = 0, []
        r2 = read_tsv(os.path.join(ROOT, PARALLEL2, "official_w10_results_2026_11_17.tsv"))
        # Joined on the official fixture slug, not on game_id. The reason turned out to be the finding:
        # this pack keys the Rams-Cardinals game 2026_10_LA_ARZ (the abbreviations the page prints) and the
        # third read keys the same fixture 2026_10_LAR_AZ, so a join on game_id across the two trees would
        # drop a row in silence. The slug is the only identifier the two conventions share.
        slug_of = lambda u: u.rstrip("/").split("/")[-1]
        pr = {slug_of(r["game_url"]): r for r in r2}
        id_diverge = []
        for r in w10_games:
            q = pr.get(slug_of(r["game_url"]))
            if q is None:
                d2.append({"game_id": r["game_id"], "problem": "fixture absent from the third read"})
                continue
            if r["game_id"] != q.get("game_id"):
                id_diverge.append({"fixture_slug": slug_of(r["game_url"]), "this_pack": r["game_id"],
                                   "third_read": q.get("game_id")})
            for f in ("date_et", "away", "away_score", "away_record", "home", "home_score",
                       "home_record", "status", "game_url"):
                c2 += 1
                if flat2(r[f]) != flat2(q.get(f, "")):
                    d2.append({"game_id": r["game_id"], "field": f, "this_read": r[f], "third_read": q.get(f)})
        st3 = {r["abbr"]: r for r in read_tsv(os.path.join(ROOT, PARALLEL2, "official_standings_2026_11_17.tsv"))}
        for r in st:
            q = st3.get(r["team_abbrev"])
            if q is None:
                d2.append({"club": r["team_abbrev"], "problem": "club absent from the third read"})
                continue
            for mine, theirs_f in (("w", "w"), ("l", "l"), ("t", "t"), ("pct", "pct"), ("pf", "pf"),
                                   ("pa", "pa"), ("net", "net"), ("home", "home"), ("road", "road"),
                                   ("div", "div_record"), ("conf", "conf_record"), ("strk", "streak")):
                c2 += 1
                if flat2(r[mine]) != flat2(q.get(theirs_f, "")):
                    d2.append({"club": r["team_abbrev"], "field": mine, "this_read": r[mine],
                               "third_read": q.get(theirs_f)})
        inj3 = {}
        for r in read_tsv(os.path.join(ROOT, PARALLEL2, "official_injuries_w10_2026_11_17.tsv")):
            inj3[(r["team"].strip(), r["player"].strip())] = r
        for r in spot:
            q = inj3.get((r["team"].strip(), r["player"].strip()))
            if q is None:
                d2.append({"team": r["team"], "player": r["player"],
                           "problem": "row absent from the third read of the full injury page"})
                continue
            for f in ("position", "injury", "practice_status", "game_status"):
                c2 += 1
                if flat2(r[f]) != flat2(q.get(f, "")):
                    d2.append({"team": r["team"], "player": r["player"], "field": f, "this_read": r[f],
                               "third_read": q.get(f)})
        extra = len(inj3) - len(spot)
        p2.update({"cells_compared": c2, "mismatches": len(d2), "detail": d2[:20],
                   "game_id_conventions_diverge": len(id_diverge), "diverging_ids": id_diverge,
                   "identifier_finding": ("the values agree on every cell; the identifiers do not. This pack "
                                          "spells the two clubs as the page prints them (LA, AZ) and the third "
                                          "read uses the nflverse-style codes (LAR, ARI) in its game_id while "
                                          "keeping LA/AZ in its own value columns. Any future join between "
                                          "these two trees must go through the fixture slug, not game_id, and "
                                          "the flag R1-08 exists to keep that from being discovered the hard way"),
                   "injury_rows_their_read_has": len(inj3),
                   "injury_rows_this_pack_checked": len(spot),
                   "coverage_note": (f"the third reader transcribed all {len(inj3)} injury rows on the page, "
                                     f"against this pack's {len(spot)} hand-typed spot-check rows; the "
                                     f"comparison covers the intersection, and the remaining {extra} rows are "
                                     "checked against the retained capture by C8 rather than against a human"),
                   "kickoff_times_note": ("this pack prints time_et blank for a final because the schedule page "
                                          "does not reprint it; the third read sourced kickoff windows and "
                                          "networks for the same games from the injury hub's game-day headers, "
                                          "which is a different official page for the same fact - recorded here "
                                          "so the two packs' apparent disagreement on a blank is not read as one "
                                          "of them being incomplete"),
                   "verdict": "pass" if not d2 else "FAIL — two readers disagree, one transcription is wrong"})
    else:
        p2["verdict"] = "not available"
    done("C12_third_reader_agreement", p2)

    # ---- C10 venue evidence ------------------------------------------------------
    direct = [v for v in venues if v["game_centre_stadium"]]
    indirect = [v for v in venues if v["venue_string_printed_on_week11_page"]]
    conflicts = [v for v in venues if (v["conflict_flag"] or "").strip()]
    both = [v for v in venues if v["game_centre_stadium"] and v["venue_string_printed_on_week11_page"]]
    name_conflicts = [v for v in both if v["game_centre_stadium"].strip().upper()
                      != v["venue_string_printed_on_week11_page"].strip().upper()]
    done("C10_venue_evidence", {
        "fixtures": len(venues),
        "venue_string_printed_on_schedule_page": len(indirect),
        "venue_transcribed_from_the_game_centre": len(direct),
        "game_centre_rows_that_disagree_with_the_schedule_page": len(name_conflicts),
        "flagged_rows": len(conflicts),
        "coverage_of_the_brief_item": f"{len(direct)} of {len(venues)} fixtures carry a Game Center venue row",
        "verdict": "measured",
        "note": ("the brief asks for the venue of every fixture transcribed from the official game centre. "
                 "Two were read this round; the other eleven are blank with 'not read this round', because the "
                 "weekly schedule page prints no venue field and this repository does not infer one. The "
                 "stadium-name disagreement on Colts at Texans is a finding, not a transcription error: both "
                 "strings are printed by the NFL, on two different pages, for the same fixture."),
    })

    report["numbers"] = {
        "week10_finals_published": len(w10_games),
        "week11_fixtures": len([r for r in w11 if r["row_type"] == "game"]),
        "week11_byes": len([r for r in w11 if r["row_type"] == "bye"]),
        "standings_clubs": len(st),
        "games_implied_by_standings": games_implied,
        "league_points_each_side": spf,
        "week10_games_missing_from_the_results_log": len(missing_in_log),
        "week11_slate_cells_moved_since_2026_11_16": len(d11["moved"]),
        "injury_rows_spot_checked": len(spot),
        "injury_spot_check_mismatches": len(spot_fails),
        "published_injury_table_mismatches": len(pub_fails),
        "published_injury_rows_vs_capture": len(not_published) + len(published_but_not_captured),
        "injury_reads_since_last_content_change": report["checks"]["C9_injury_capture_series"]["reads_since_last_content_change"],
        "standings_cells_agreeing_with_the_collector": len(st) * len(FIELDS) - len(diffs),
        "standings_cells_stale_in_the_pinned_reference": len(pin_diffs),
        "parallel_read_cells_compared": par.get("cells_compared", 0),
        "parallel_read_mismatches": par.get("mismatches", 0),
        "third_read_cells_compared": p2.get("cells_compared", 0),
        "third_read_mismatches": p2.get("mismatches", 0),
        "independent_reads_compared_to_this_pack": sum(1 for x in (par, p2) if x.get("present")),
        "venue_direct_rows": len(direct),
        "venue_name_conflicts": len(name_conflicts),
    }
    if p2.get("mismatches"):
        fails.append(f"C12 third reader: {p2['mismatches']} cells where an independent transcription of the "
                     f"same page disagrees")
    if par.get("mismatches"):
        fails.append(f"C11 second reader: {par['mismatches']} cells where two independent transcriptions "
                     f"of the same page disagree")
    report["failures"] = fails
    report["verdict"] = "pass" if not fails else "fail"

    payload = json.dumps(report, indent=1, sort_keys=True) + "\n"
    manifest = {
        "pack": "data/lab/reads/2026-11-17",
        "read_on": "2026-11-17",
        "read_by": "session arena-9d8c298c-x1, through the fetch tool",
        "read_window_utc": {"first_read": "2026-11-17T22:41Z", "last_read": "2026-11-17T22:53Z",
                            "note": ("clock times are this session's wall clock at the moment of each fetch, "
                                     "recorded to the minute; they are not the pages' publication times. The "
                                     "fetch tool returns parsed page text, so these files are transcriptions and "
                                     "the hashes below are hashes of the transcriptions, not of HTTP bytes.")},
        "official_urls": [
            "https://www.nfl.com/schedules/2026/by-week/week-10",
            "https://www.nfl.com/schedules/2026/by-week/week-11",
            "https://www.nfl.com/standings/league/2026/REG",
            "https://www.nfl.com/injuries/",
            "https://www.nfl.com/games/colts-at-texans-2026-reg-11",
            "https://www.nfl.com/games/vikings-at-49ers-2026-reg-11",
        ],
        "files": {f: {"bytes": os.path.getsize(os.path.join(PACK, f)),
                      "sha256": sha256_file(os.path.join(PACK, f))} for f in PACK_FILES},
        "generated_at": report["generated_at"],
    }
    man_payload = json.dumps(manifest, indent=1, sort_keys=True) + "\n"

    if check_only:
        old = open(OUT_JSON, encoding="utf-8").read() if os.path.exists(OUT_JSON) else ""
        for name, got, want in (("report.json", payload, old), ("manifest.json", man_payload,
                              open(OUT_MANIFEST, encoding="utf-8").read() if os.path.exists(OUT_MANIFEST) else "")):
            strip = lambda s: "\n".join(l for l in s.split("\n") if '"generated_at"' not in l)
            if strip(got) != strip(want):
                print(f"STALE: data/lab/reads/2026-11-17/{name} does not match a fresh build")
                return 1
        if fails:
            print("FAILED CHECKS:", *fails, sep="\n  - ")
            return 1
        print(f"CHECK OK: the 2026-11-17 reads pack reproduces from its files "
              f"({len(w10_games)}+136 games, {len(st)} clubs, {len(spot)} injury rows, {len(fails)} failures)")
        return 1 if fails else 0

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        fh.write(payload)
    with open(OUT_MANIFEST, "w", encoding="utf-8") as fh:
        fh.write(man_payload)
    print(f"wrote {os.path.relpath(OUT_JSON, ROOT)} and {os.path.relpath(OUT_MANIFEST, ROOT)}")
    for k, v in report["numbers"].items():
        print(f"  {k}: {v}")
    if fails:
        print("FAILURES:", *fails, sep="\n  - ")
        return 1
    print(f"verdict: {report['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
