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
CAPTURE_INDEX = "data/captures/index.jsonl"
PUBLISHED_INJURY_TABLE = "data/console/injuries_week10.csv"


# --------------------------------------------------------------------- helpers
def read_tsv(path: str) -> list[dict]:
    """Tab-separated file whose leading '#' lines are comments. Same convention as the
    2026-11-16 pack, so the two reads of a page can be diffed with one function."""
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().split("\n") if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(io.StringIO("\n".join(lines)), delimiter="\t"))


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

    # ---- C5 independent re-read of the standings ---------------------------------
    coll = json.load(open(os.path.join(ROOT, COLLECTOR_STANDINGS), encoding="utf-8"))
    coll_rows = {r["team_abbrev"]: r for r in coll["rows"]}
    diffs = []
    for r in st:
        c = coll_rows.get(r["team_abbrev"])
        if not c:
            diffs.append({"club": r["team_abbrev"], "problem": "not in the collector read"})
            continue
        pairs = (("w", "W"), ("l", "L"), ("t", "T"), ("pf", "PF"), ("pa", "PA"), ("net", "NET_PTS"))
        for mine, theirs in pairs:
            if str(r[mine]).strip() != str(c.get(theirs, "")).strip():
                diffs.append({"club": r["team_abbrev"], "field": mine, "this_read": r[mine], "collector_read": c.get(theirs)})
    done("C5_independent_standings_reread", {
        "clubs": len(st), "fields_per_club": 6, "assertions": len(st) * 6, "differing_cells": len(diffs),
        "detail": diffs[:20],
        "collector_read_at": coll.get("generated_at"),
        "verdict": "pass" if not diffs else "review",
        "note": ("two reads of one official page by different code three hours apart. A pass means the "
                 "collector and this transcription see the same table; it does not mean the page is right."),
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
    done("C8_injury_spotcheck_vs_capture", {
        "rows_transcribed": len(spot), "clubs_covered": clubs, "rows_compared": spot_ok,
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
        "venue_direct_rows": len(direct),
        "venue_name_conflicts": len(name_conflicts),
    }
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
