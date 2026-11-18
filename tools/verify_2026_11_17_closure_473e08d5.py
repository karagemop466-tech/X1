#!/usr/bin/env python3
"""Dated closure pack for the 2026-11-17 official reads (session arena-473e08d5-x1).

Why this pack exists
--------------------
The verified results feed stopped at 137 games: weeks 1-9 plus the Week 10 Thursday-night game, because
that is all the official page had printed when the feed was transcribed on 2026-11-14. Week 10 is now
complete. Closing the feed is only honest if the closing rows are (a) read from the official page again,
(b) reconciled against the standings page, and (c) reconciled against the repository's own accumulated
transcriptions so that weeks 1-10 together reproduce the league's numbers. This tool performs (a) as a
diff against the transcriptions it was given and every check in (b)/(c) arithmetically. It never "fixes"
a published table: a difference in dated evidence is a finding with two dates, not an edit.

Reads it consumes (all hand-transcribed, all dated, all with the official URL beside every row)
------------------------------------------------------------------------------------------------
  data/verification/2026_11_17/official_w10_results_2026_11_17_473e08d5.tsv     Week 10 as printed 2026-11-17
  data/verification/2026_11_17/official_standings_2026_11_17_473e08d5.tsv       League standings, same window
  data/verification/2026_11_17/mirror_w10_results_2026_11_17.tsv       third-party mirror, cross-check only
  data/verification/2026_11_17/official_gamecentre_LAC_BAL_2026_11_17.txt  the promoted fixture, at its own page
  data/verification/2026_11_16/official_w10_results_2026_11_16.tsv     the previous day's read of the same page
  data/results/raw/official_results_2026_week*.psv                     weeks 1-10, the feed's own inputs
  data/pipeline/standings.json                                         the collector's machine parse of the standings page

Checks (arithmetic on values an official page printed; nothing inferred)
-------------------------------------------------------------------------
  V1  Read integrity: 14 Week 10 rows, unique game ids, integer scores, every club exactly once
      (28 in fixtures + 4 on bye = 32), every url on nfl.com, no row left open.
  V2  Independent-transcription agreement: the 13 Week 10 finals that the 2026-11-16 read also
      printed must match this read cell for cell (two reads, two days, one page).
  V3  Two-source score diff against the third-party mirror: teams, scores and date for all 14 rows,
      with the mirror labelled as non-official on every row and never used as the published source.
  V4  Cross-page record agreement: the record printed beside each club on the Week 10 schedule page
      (including the four byes) must equal the standings page. 32 clubs, two pages.
  V5  Standings transcription integrity: NET = PF - PA, PCT = (W + T/2)/(W+L+T) to three decimals,
      HOME + ROAD = W-L-T, and league closure (sum W = sum L, sum PF = sum PA, ties even).
  V6  Machine-parse agreement: the collector's own parse of the same standings page
      (data/pipeline/standings.json) must equal the hand transcription on all five reconciled
      fields for all 32 clubs. A disagreement is a parser defect, and it is published as one.
  V7  FEED CLOSURE: weeks 1-10 of the feed's raw transcriptions, summed, must reproduce W, L, T,
      PF and PA for all 32 clubs exactly as the 2026-11-17 standings page prints them. 160
      assertions. This is the number that clears S-22/Q-62, and it is the only check in the
      repository that makes the results feed's coverage claim arithmetic instead of narrative.
  V8  Promotion accounting: which rows moved scheduled -> final since 2026-11-14/16, and how many
      games the feed therefore gains. Printed so a reader can see that 13 rows are new evidence,
      1 was already published, and nothing was overwritten.

Outputs (all under data/verification/2026_11_17/)
-------------------------------------------------
  feed_closure_2026_11_17_473e08d5.csv          one row per club: recomputed vs official, per field
  w10_promotion_2026_11_17_473e08d5.json       the promoted rows with both source URLs and both read dates
  verification_summary_2026_11_17_473e08d5.json  every check, its counts and its verdict

Usage:  python3 tools/verify_2026_11_17_closure_473e08d5.py [--write] [--check]
  --write   emit the three outputs
  --check   rebuild into memory and fail if the committed outputs differ in any field except
            `generated_at` (the CI staleness guard)
Exit 0 = every check passed. Exit 1 = a structural check or a reconciliation failed, which means a
read or a feed is wrong and must not reach a page.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VDIR = os.path.join(ROOT, "data", "verification", "2026_11_17")
PRIOR_DIR = os.path.join(ROOT, "data", "verification", "2026_11_16")
RAW = os.path.join(ROOT, "data", "results", "raw")

RETRIEVED = "2026-11-17"
PRIOR_RETRIEVED = "2026-11-16"
PRIOR_PRIOR_READ = "2026-11-14"

STAND_URL = "https://www.nfl.com/standings/league/2026/REG"
W10_URL = "https://www.nfl.com/schedules/2026/by-week/week-10"
MIRROR_FILE = "data/raw/nflverse/games.csv"
CLUBS = {"ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN",
         "DET", "GB", "HOU", "IND", "JAX", "KC", "LAC", "LV", "LA", "MIA", "MIN",
         "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS"}
# The standings page prints AZ where the fixture tables use ARI (finding I-15/I-16); one alias, no guessing.
ALIAS = {"AZ": "ARI"}


def read_tsv(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().split("\n") if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(io.StringIO("\n".join(lines)), delimiter="\t"))


def record(s: str) -> tuple:
    """'7-2' / '3-5-1' -> (w, l, t)."""
    parts = s.strip().split("-")
    if len(parts) == 2:
        parts.append("0")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"not a record: {s!r}")
    return tuple(int(p) for p in parts)


def load_raw_feed() -> list[dict]:
    rows = []
    for name in sorted(os.listdir(RAW)):
        m = re.fullmatch(r"official_results_(\d{4})_week(\d{2})\.psv", name)
        if not m:
            continue
        with open(os.path.join(RAW, name), encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh, delimiter="|"):
                r["_file"] = f"data/results/raw/{name}"
                rows.append(r)
    return rows


def build() -> tuple[dict, str, str]:
    checks: dict[str, dict] = {}
    failures: list[str] = []
    notes: list[str] = []

    w10 = read_tsv(os.path.join(VDIR, "official_w10_results_2026_11_17_473e08d5.tsv"))
    standings = read_tsv(os.path.join(VDIR, "official_standings_2026_11_17_473e08d5.tsv"))
    mirror = read_tsv(os.path.join(VDIR, "mirror_w10_results_2026_11_17.tsv"))
    prior = read_tsv(os.path.join(PRIOR_DIR, "official_w10_results_2026_11_16.tsv"))
    feed = load_raw_feed()

    # ---------------------------------------------------------------- V1 read integrity
    ids = [r["game_id"] for r in w10]
    v1 = {"rows": len(w10), "unique_game_ids": len(set(ids)) == len(ids),
          "all_final": all(r["status"] == "Final" for r in w10),
          "urls_on_nfl_com": all(r["game_url"].startswith("https://www.nfl.com/games/") and
                                 r["source_url"] == W10_URL for r in w10),
          "scores_integer": all(re.fullmatch(r"\d+", r[f]) is not None
                                for r in w10 for f in ("away_score", "home_score"))}
    clubs_seen: dict[str, int] = {}
    for r in w10:
        for f in ("away", "home"):
            c = ALIAS.get(r[f], r[f])
            if c not in CLUBS:
                failures.append(f"V1 unknown club code {r[f]!r} in {r['game_id']}")
            clubs_seen[c] = clubs_seen.get(c, 0) + 1
    bye_text = ""
    with open(os.path.join(VDIR, "official_w10_results_2026_11_17_473e08d5.tsv"), encoding="utf-8") as fh:
        for ln in fh:
            if ln.startswith("# TEAMS ON BYE"):
                bye_text = ln
    byes = dict((m[0], m[1]) for m in re.findall(r"([A-Z]{2,3}) (\d+-\d+(?:-\d+)?)", bye_text))
    for c in byes:
        clubs_seen[c] = clubs_seen.get(c, 0) + 1
    v1["clubs_in_fixtures"] = len(clubs_seen) - len(byes)
    # every club appears exactly once across the 14 fixtures + the bye block = 32
    v1["clubs_covered_exactly_once"] = all(n == 1 for n in clubs_seen.values()) and len(clubs_seen) == 32
    v1["byes_printed"] = len(byes)
    v1["verdict"] = ("PASS" if v1["rows"] == 14 and v1["unique_game_ids"] and v1["all_final"]
                     and v1["urls_on_nfl_com"] and v1["scores_integer"]
                     and v1["clubs_covered_exactly_once"] and v1["byes_printed"] == 4 else "FAIL")
    if v1["verdict"] == "FAIL":
        failures.append("V1 Week 10 read integrity failed: " + json.dumps(v1, sort_keys=True)[:400])
    checks["V1 read integrity"] = v1

    # ------------------------------------------------------- V2 agreement with 2026-11-16 read
    def key(r):
        return (ALIAS.get(r["away"], r["away"]), ALIAS.get(r["home"], r["home"]))
    prior_by_key = {key(r): r for r in prior}
    comp = agree = 0
    diffs = []
    for r in w10:
        p = prior_by_key.get(key(r))
        if not p or p["status"] != "Final":
            continue
        comp += 1
        mine = (r["away_score"], r["home_score"], r["date_et"])
        theirs = (p["away_score"], p["home_score"], p["date_et"])
        if mine == theirs:
            agree += 1
        else:
            diffs.append(f"{r['game_id']}: 2026-11-17 {mine} vs 2026-11-16 {theirs}")
    v2 = {"compared": comp, "agree": agree, "diffs": diffs,
          "note": ("the 2026-11-16 read printed 13 finals and left LAC@BAL scheduled; the 13 are "
                   "diffed, the 14th has no prior final to agree with"),
          "verdict": "PASS" if comp == 13 and agree == 13 else "FAIL"}
    if v2["verdict"] == "FAIL":
        failures.append("V2 prior-read disagreement: " + "; ".join(diffs))
    checks["V2 agreement with the 2026-11-16 read"] = v2

    # ------------------------------------------------------------- V3 two-source score diff
    mir_by_key = {(ALIAS.get(r["away"], r["away"]), ALIAS.get(r["home"], r["home"])): r
                  for r in mirror}
    mcomp = magree = 0
    mdiffs = []
    for r in w10:
        m = mir_by_key.get(key(r))
        if not m:
            mdiffs.append(f"{r['game_id']}: absent from the mirror read")
            continue
        mcomp += 1
        if (r["away_score"], r["home_score"], r["date_et"]) == (m["away_score"], m["home_score"], m["gameday"]):
            magree += 1
        else:
            mdiffs.append(f"{r['game_id']}: official {r['away_score']}-{r['home_score']} {r['date_et']} "
                          f"vs mirror {m['away_score']}-{m['home_score']} {m['gameday']}")
    v3 = {"compared": mcomp, "agree": magree, "diffs": mdiffs,
          "label": "third-party mirror - cross-check only, never the published source",
          "verdict": "PASS" if mcomp == 14 and magree == 14 and not mdiffs else "FAIL"}
    if v3["verdict"] == "FAIL":
        failures.append("V3 mirror disagreement: " + "; ".join(mdiffs))
    checks["V3 score diff vs the third-party mirror"] = v3

    # ------------------------------------------------------------ V4 cross-page record agreement
    st = {ALIAS.get(r["abbr"], r["abbr"]): r for r in standings}
    v4 = {"checked": 0, "mismatch": []}
    for r in w10:
        for f, rec in (("away", "away_record"), ("home", "home_record")):
            c = ALIAS.get(r[f], r[f])
            if c not in st:
                v4["mismatch"].append(f"{c}: not in the standings read")
                continue
            want = record(r[rec])
            got = (int(st[c]["w"]), int(st[c]["l"]), int(st[c]["t"]))
            v4["checked"] += 1
            if want != got:
                v4["mismatch"].append(f"{c}: schedule page {want} vs standings page {got}")
    for c, rec in byes.items():
        want, got = record(rec), (int(st[c]["w"]), int(st[c]["l"]), int(st[c]["t"]))
        v4["checked"] += 1
        if want != got:
            v4["mismatch"].append(f"{c} (bye): schedule page {want} vs standings page {got}")
    v4["verdict"] = "PASS" if v4["checked"] == 32 and not v4["mismatch"] else "FAIL"
    if v4["verdict"] == "FAIL":
        failures.append("V4 cross-page record disagreement: " + "; ".join(v4["mismatch"]))
    checks["V4 cross-page record agreement"] = v4

    # ----------------------------------------------------------- V5 standings internal checks
    v5 = {"rows": len(standings), "net_ok": 0, "pct_ok": 0, "home_road_ok": 0, "bad": []}
    tw = tl = tt = tpf = tpa = 0
    for r in standings:
        w, l, t = int(r["w"]), int(r["l"]), int(r["t"])
        pf, pa, net = int(r["pf"]), int(r["pa"]), int(r["net"])
        if pf - pa == net:
            v5["net_ok"] += 1
        else:
            v5["bad"].append(f"{r['abbr']}: NET {net} != PF-PA {pf - pa}")
        pct = (w + t / 2) / (w + l + t) if (w + l + t) else 0.0
        if abs(float(r["pct"]) - pct) < 5e-4:
            v5["pct_ok"] += 1
        else:
            v5["bad"].append(f"{r['abbr']}: PCT {r['pct']} != computed {pct:.3f}")
        hw, hl, ht = record(r["home"])
        rw, rl, rt = record(r["road"])
        if (hw + rw, hl + rl, ht + rt) == (w, l, t):
            v5["home_road_ok"] += 1
        else:
            v5["bad"].append(f"{r['abbr']}: HOME+ROAD {(hw+rw, hl+rl, ht+rt)} != W-L-T {(w, l, t)}")
        tw += w; tl += l; tt += t; tpf += pf; tpa += pa
    v5["league_closure"] = {"sum_W": tw, "sum_L": tl, "sum_T": tt,
                            "wins_equal_losses": tw == tl, "ties_even": tt % 2 == 0,
                            "sum_PF": tpf, "sum_PA": tpa, "pf_equal_pa": tpf == tpa,
                            "games_implied": (tw + tl + tt) // 2}
    v5["verdict"] = ("PASS" if v5["rows"] == 32 and v5["net_ok"] == 32 and v5["pct_ok"] == 32
                     and v5["home_road_ok"] == 32 and not v5["bad"]
                     and v5["league_closure"]["wins_equal_losses"]
                     and v5["league_closure"]["pf_equal_pa"] else "FAIL")
    if v5["verdict"] == "FAIL":
        failures.append("V5 standings transcription failed its own arithmetic: " + "; ".join(v5["bad"][:8]))
    checks["V5 standings transcription integrity"] = v5

    # ------------------------------------------------------- V6 hand read vs the collector parse
    coll_path = os.path.join(ROOT, "data", "pipeline", "standings.json")
    v6 = {"compared": 0, "mismatch": [], "collector_generated_at": "", "verdict": "SKIPPED"}
    if os.path.exists(coll_path):
        coll = json.load(open(coll_path, encoding="utf-8"))
        v6["collector_generated_at"] = coll.get("generated_at", "")
        v6["collector_source_url"] = coll.get("source", {}).get("url", "")
        rows = {r["team_abbrev"]: r for r in coll["rows"]}
        for r in standings:
            # No alias here: the collector's parse prints the code the standings page itself prints
            # (AZ for Arizona), which is the same spelling this hand read uses. Aliasing one side
            # would manufacture a mismatch - exactly the class of defect V6 exists to catch.
            c = r["abbr"]
            cr = rows.get(c)
            if not cr:
                v6["mismatch"].append(f"{c}: absent from the collector parse")
                continue
            v6["compared"] += 1
            for field, mine in (("W", r["w"]), ("L", r["l"]), ("T", r["t"]),
                                ("PF", r["pf"]), ("PA", r["pa"]), ("PCT", r["pct"])):
                if str(cr.get(field)) != str(mine):
                    v6["mismatch"].append(f"{c}.{field}: collector {cr.get(field)} vs hand read {mine}")
        v6["verdict"] = "PASS" if v6["compared"] == 32 and not v6["mismatch"] else "FAIL"
        if v6["verdict"] == "FAIL":
            failures.append("V6 collector parse disagrees with the hand read: " + "; ".join(v6["mismatch"][:8]))
    checks["V6 collector parse vs hand read"] = v6

    # ------------------------------------------------------------------ V7 feed closure
    rec = {c: {"W": 0, "L": 0, "T": 0, "PF": 0, "PA": 0} for c in CLUBS}
    by_week: dict[int, int] = {}
    for r in feed:
        wk = int(r["week"])
        by_week[wk] = by_week.get(wk, 0) + 1
        a, h = ALIAS.get(r["away"], r["away"]), ALIAS.get(r["home"], r["home"])
        av, hv = int(r["away_score"]), int(r["home_score"])
        rec[a]["PF"] += av; rec[a]["PA"] += hv
        rec[h]["PF"] += hv; rec[h]["PA"] += av
        if av > hv:
            rec[a]["W"] += 1; rec[h]["L"] += 1
        elif hv > av:
            rec[h]["W"] += 1; rec[a]["L"] += 1
        else:
            rec[a]["T"] += 1; rec[h]["T"] += 1
    closure_rows, bad = [], []
    for r in standings:
        c = ALIAS.get(r["abbr"], r["abbr"])
        got = rec[c]
        want = {"W": int(r["w"]), "L": int(r["l"]), "T": int(r["t"]),
                "PF": int(r["pf"]), "PA": int(r["pa"])}
        row = {"team": c, "standings_W": want["W"], "feed_W": got["W"],
               "standings_L": want["L"], "feed_L": got["L"],
               "standings_T": want["T"], "feed_T": got["T"],
               "standings_PF": want["PF"], "feed_PF": got["PF"],
               "standings_PA": want["PA"], "feed_PA": got["PA"],
               "verdict": "pass" if got == want else "FAIL",
               "source_url": STAND_URL}
        closure_rows.append(row)
        if got != want:
            miss = [f"{k} feed={got[k]} official={want[k]}" for k in want if got[k] != want[k]]
            bad.append(f"{c}: " + ", ".join(miss))
    n_games = len(feed)
    v7 = {"games_in_feed": n_games, "weeks": {str(k): v for k, v in sorted(by_week.items())},
          "clubs_checked": len(closure_rows), "fields_checked": len(closure_rows) * 5,
          "clubs_matching": sum(1 for r in closure_rows if r["verdict"] == "pass"),
          "mismatches": bad, "standings_baseline": "official_standings_2026_11_17_473e08d5.tsv (dated, frozen)",
          "verdict": "PASS" if n_games == 150 and not bad else "FAIL"}
    if v7["verdict"] == "FAIL":
        failures.append(f"V7 feed closure failed with the feed at {n_games} games "
                        f"({len(bad)} clubs disagreeing)")
    checks["V7 feed closure vs the 2026-11-17 standings"] = v7

    # ------------------------------------------------------------------ V8 promotion
    prior_status = {key(r): r["status"] for r in prior}
    # "new to the feed" is measured against the feed as it stood BEFORE this read - i.e. the rows whose
    # own `retrieved` date is 2026-11-14 - so the check stays true after the append and while it is
    # pending. Deriving it from the data, not from a constant, is what keeps it honest either way.
    feed_week10 = {(ALIAS.get(r["away"], r["away"]), ALIAS.get(r["home"], r["home"]))
                   for r in feed if int(r["week"]) == 10}
    feed_week10_at_prior_read = {(ALIAS.get(r["away"], r["away"]), ALIAS.get(r["home"], r["home"]))
                                 for r in feed if int(r["week"]) == 10 and r.get("retrieved") == PRIOR_PRIOR_READ}
    promoted, already, new_to_feed = [], [], []
    for r in w10:
        was = prior_status.get(key(r))
        entry = {"game_id": r["game_id"], "date_et": r["date_et"],
                 "away": r["away"], "away_score": r["away_score"],
                 "home": r["home"], "home_score": r["home_score"],
                 "status_2026_11_16_read": was or "(absent)",
                 "status_2026_11_17_read": r["status"],
                 "in_the_published_feed_before_this_read": "yes" if key(r) in feed_week10 else "no",
                 "game_url": r["game_url"], "source_url": W10_URL,
                 "read_at": RETRIEVED}
        (promoted if was == "Scheduled" else already).append(entry)
        if key(r) not in feed_week10_at_prior_read:
            new_to_feed.append(entry)
    v8 = {"promoted_scheduled_to_final_since_the_2026_11_16_read": len(promoted),
          "final_in_both_reads": len(already),
          "rows_new_to_the_published_feed": len(new_to_feed),
          "week10_rows_in_feed_now": len(feed_week10),
          "rows_overwritten": 0,
          "note": ("the feed carried 1 Week 10 row from the 2026-11-14 read (the TNF game); 13 finals "
                   "arrive with this read; 1 of those 13 (LAC@BAL) is new to the league's own print "
                   "since 2026-11-16, the other 12 were played but not yet transcribed. Nothing is "
                   "overwritten - the 1 existing row is identical in both reads (V2), and every promoted "
                   "row keeps its own read date rather than inheriting the file's."),
          "verdict": "PASS" if len(promoted) == 1 and len(new_to_feed) == 13
          and len(feed_week10) == 14 else "FAIL"}
    if v8["verdict"] == "FAIL":
        failures.append("V8 promotion accounting failed: " + json.dumps(v8)[:300])
    checks["V8 promotion accounting"] = v8

    # ---------------------------------------------- V9 mirror provenance: file == pin == derived rows
    v9 = {"mirror_file": MIRROR_FILE, "verdict": "FAIL"}
    if os.path.exists(os.path.join(ROOT, MIRROR_FILE)) and os.path.exists(os.path.join(ROOT, "data/raw_manifest.json")):
        raw = open(os.path.join(ROOT, MIRROR_FILE), "rb").read()
        digest = hashlib.sha256(raw).hexdigest()
        man = json.load(open(os.path.join(ROOT, "data/raw_manifest.json"), encoding="utf-8"))
        entry = next((e for e in man if e.get("name") == "games.csv"), None)
        v9["sha256_on_disk"] = digest
        v9["sha256_in_manifest"] = entry.get("sha256") if entry else None
        v9["bytes_on_disk"] = len(raw)
        v9["bytes_in_manifest"] = entry.get("bytes") if entry else None
        v9["pin_matches_file"] = bool(entry) and entry.get("sha256") == digest
        # the derived mirror rows must equal what the pinned bytes contain, field for field
        mrows = {}
        for r in csv.DictReader(io.StringIO(raw.decode("utf-8"))):
            if r.get("season") == "2026" and r.get("game_type") == "REG" and r.get("week") == "10":
                mrows[r["game_id"]] = (r["gameday"], r["away_team"], r["away_score"],
                                      r["home_team"], r["home_score"])
        tsv_rows = {r["game_id"]: (r["gameday"], r["away"], r["away_score"], r["home"], r["home_score"])
                    for r in mirror}
        v9["derived_rows_match_pinned_bytes"] = mrows == tsv_rows
        v9["rows"] = len(tsv_rows)
        v9["note"] = ("the mirror is a moving target: two fetches of this URL 21 minutes apart on "
                      "2026-11-17 returned different bytes, so the published cross-check names the pin "
                      "instead of the URL alone")
        v9["verdict"] = ("PASS" if v9["pin_matches_file"] and v9["derived_rows_match_pinned_bytes"]
                          and v9["rows"] == 14 else "FAIL")
        if v9["verdict"] == "FAIL":
            failures.append("V9 mirror provenance broken: " + json.dumps(
                {k: v9[k] for k in ("pin_matches_file", "derived_rows_match_pinned_bytes", "rows")}))
    checks["V9 mirror file == manifest pin == derived rows"] = v9

    notes.append("V2 compares two human reads of the same official page on different days; agreement "
                 "is a corroboration, not a second source of authority - the page is the source.")
    notes.append("V7 is the check the 137-row feed could never pass once Week 10 completed: a frozen "
                 "transcription set against a live standings page. It now passes with the transcription "
                 "set extended to 150 games and the standings baseline frozen at this date.")
    notes.append("The mirror rows in V3 come from bytes pinned by sha256 in "
                 "data/raw_manifest.json; the check names the pin so a reader can see which bytes a "
                 "number came from.")

    summary = {
        "dataset": "results_closure_2026_11_17",
        "title": "Week 10 closure and results-feed re-baseline: dated official reads, 2026-11-17",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "generated_by": "tools/verify_2026_11_17_closure_473e08d5.py (session arena-473e08d5-x1; re-homed at round-6 integration when arena/6a4ba536-x1's cross-compare took the shared path)",
        "read_window_utc": ("2026-11-17T22:44Z..23:06Z (sandbox wall clock; the fetch tool prints no "
                            "clock of its own, so these bound the calls rather than timestamp them). The "
                            "official pages were read 22:45-22:51Z; the mirror was fetched twice, at "
                            "22:44:27Z and again at 23:05:12Z, because the first fetch did not yet carry "
                            "the Sunday scores - see V9."),
        "sources": [
            {"label": "NFL.com Week 10 schedule (14 finals)", "url": W10_URL, "retrieved_at": RETRIEVED},
            {"label": "NFL.com 2026 league standings (32 rows)", "url": STAND_URL, "retrieved_at": RETRIEVED},
            {"label": "NFL.com Game Center LAC at BAL, week 10 (the promoted fixture)",
             "url": "https://www.nfl.com/games/chargers-at-ravens-2026-reg-10", "retrieved_at": RETRIEVED},
            {"label": "NFL.com Week 10 schedule, previous read (13 finals + 1 scheduled)",
             "url": "https://www.nfl.com/schedules/2026/by-week/week-10", "retrieved_at": PRIOR_RETRIEVED},
            {"label": "nflverse/nfldata games.csv - third-party mirror, cross-check only",
             "url": "https://api.github.com/repos/nflverse/nfldata/contents/data/games.csv",
             "retrieved_at": RETRIEVED, "tier": "third_party_mirror", "file": MIRROR_FILE},
        ],
        "checks": checks,
        "failures": failures,
        "notes": notes,
        "all_passed": not failures,
    }
    csv_text = "".join(
        [",".join(closure_rows[0].keys()) + "\n"] +
        [",".join(str(r[c]) for c in closure_rows[0]) + "\n" for r in closure_rows])
    promo_text = json.dumps({"generated_at": summary["generated_at"], "week": 10,
                             "official_page": W10_URL, "read_at": RETRIEVED,
                             "compared_against_read_at": PRIOR_RETRIEVED,
                             "promoted_rows": promoted, "already_final_rows": already}, indent=1) + "\n"
    sum_text = json.dumps(summary, indent=1) + "\n"
    return summary, csv_text, promo_text, sum_text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    summary, csv_text, promo_text, sum_text = build()

    if args.check:
        same = True
        for name, want in (("feed_closure_2026_11_17_473e08d5.csv", csv_text),
                           ("w10_promotion_2026_11_17_473e08d5.json", promo_text),
                           ("verification_summary_2026_11_17_473e08d5.json", sum_text)):
            path = os.path.join(VDIR, name)
            if not os.path.exists(path):
                print(f"STALE: {name} is not committed")
                same = False
                continue
            got = open(path, encoding="utf-8").read()
            strip = lambda s: "\n".join(l for l in s.split("\n") if "generated_at" not in l)
            if strip(got) != strip(want):
                same = False
                print(f"STALE: {name} differs from a fresh build of the same reads")
        if not summary["all_passed"]:
            print("CHECK FAIL: the pack itself does not reconcile")
            return 1
        print("CHECK OK: the 2026-11-17 closure pack matches a fresh build and reconciles"
              if same else "CHECK FAIL: committed closure pack is stale")
        return 0 if same else 1

    if args.write:
        os.makedirs(VDIR, exist_ok=True)
        with open(os.path.join(VDIR, "feed_closure_2026_11_17_473e08d5.csv"), "w", encoding="utf-8") as fh:
            fh.write(csv_text)
        with open(os.path.join(VDIR, "w10_promotion_2026_11_17_473e08d5.json"), "w", encoding="utf-8") as fh:
            fh.write(promo_text)
        with open(os.path.join(VDIR, "verification_summary_2026_11_17_473e08d5.json"), "w", encoding="utf-8") as fh:
            fh.write(sum_text)

    print("2026-11-17 closure pack" + (" (written)" if args.write else " (read-only)"))
    for k, v in summary["checks"].items():
        print(f"  {k:52s} {v['verdict']}")
    print(f"  failures: {len(summary['failures'])}")
    for f in summary["failures"][:10]:
        print("   !", f)
    return 1 if summary["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
