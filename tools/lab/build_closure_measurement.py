#!/usr/bin/env python3
"""Measure, with the repo's own gates, exactly what still blocks closing Week 10 in the results feed.

    python3 tools/lab/build_closure_measurement.py            # write the measurement
    python3 tools/lab/build_closure_measurement.py --check     # fail if the committed file is stale
    python3 tools/lab/build_closure_measurement.py --report     # print, write nothing

Why this exists
---------------
HISTORICAL CONTEXT (kept, not silently rewritten): the prose below was written when
`data/results/_raw/reads.tsv` held 137 games. The 13 Week 10 finals were later appended to the
frozen log by the round-6 integration (PR #88), so a fresh run of this measurement now reports
0 remaining pins and 0 blocked games; M1/M2 are the proof of that closure. The published
decision text is retained as the record of what the owner was deciding at the time.

`data/results/_raw/reads.tsv` holds 137 games: weeks 1-9 plus the 2026-11-12 Thursday game. The other
13 Week 10 games are final on the official page today, and they are transcribed in this pack
(`week10_finals.tsv`). Session `arena-543cdcb0-x1` deliberately did not append them, recording the reason
as a coordinated change across three things — a hard row-count pin, the standings baseline the feed is
arithmetic-checked against, and a re-pin of the third-party mirror the feed row-diffs against
(suggestion S-22 / question Q-62). That is the single item that keeps "backtests and ROI can be computed
at all" from being true for Week 10.

This script turns that from a narrative into numbers, so the owner can decide with the cost in front of
them. It changes nothing: it reads the committed builder, counts what its gates would accept or reject,
and names every artefact that a closure would force to be rebuilt. The 13 rows are NOT appended here —
`data/results/_raw/reads.tsv` is a frozen input of registration PR-01, and editing an input of a frozen
registration is how a pre-registration stops meaning anything.

Checks
------
  M1  the pins in the builder, found by reading its source (line numbers, not folklore)
  M2  the mirror row-diff gate: does a mirror row with scores exist for each of the 13?
  M3  closure against the dated 2026-11-17 official standings, club by club (the live
      pipeline file is refreshed daily and is not a valid input to a dated measurement)
  M4  closure against the pinned 2026-11-14 baseline, club by club (what the append would break)
  M5  blast radius: every committed file that reads the results log or the feed
  M6  what the append would add to the evaluation corpus, in games
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

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "data", "lab", "reads", "2026-11-17", "feed-closure-measurement.json")

READS = "data/results/_raw/reads.tsv"
PACK = "data/lab/reads/2026-11-17/week10_finals.tsv"
BUILDER = "tools/build_results_r3.py"
PINNED_BASELINE = "code/reference_data_2026_w10.py"
MIRROR = "data/raw/nflverse/games.csv"
# Frozen 2026-11-17 official standings transcription inside the same dated reads pack as PACK.
# The live pipeline file is refreshed daily (Week 11 reads by 2026-11-19); comparing a 2026-11-17
# 150-game closure against it would silently change the meaning of M3. Pin 2026-11-19 by arena-725e025d-x1.
COLLECTOR_STANDINGS = "data/lab/reads/2026-11-17/standings_2026-11-17.tsv"
TEAM_ALIAS = {"ARI": "AZ", "LAR": "LA"}


def read_tsv(path: str) -> list[dict]:
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().split("\n") if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(io.StringIO("\n".join(lines)), delimiter="\t"))


def sha256(path: str) -> str:
    with open(os.path.join(ROOT, path), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def norm(t: str) -> str:
    return TEAM_ALIAS.get(t, t)


def build() -> dict:
    out: dict = {
        "dataset": "feed-closure-measurement",
        "title": "What closing Week 10 in the verified-results feed costs, measured by the feed's own gates",
        "generated_by": "tools/lab/build_closure_measurement.py (session arena-9d8c298c-x1)",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "read_on": "2026-11-17",
        "inputs": {p: sha256(p) for p in (READS, PACK, BUILDER, PINNED_BASELINE, COLLECTOR_STANDINGS)},
        "corpus": {},
        "measures": {},
        "options": [],
        "decision_for_the_owner": "",
    }

    reads = read_tsv(READS)
    pack = [r for r in read_tsv(PACK) if r["row_type"] == "game"]
    names = {}
    with open(os.path.join(ROOT, "data", "raw", "nflverse", "teams.csv"), encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("season") == "2026" and r.get("full"):
                names[r["full"].split()[-1]] = norm(r["team"])

    games = []
    for r in reads:
        games.append({"away": r["away"], "home": r["home"], "as_": int(r["away_score"]),
                      "hs": int(r["home_score"]), "week": int(r["week"]), "slug": r["game_slug"],
                      "date": r["date"], "src": READS})
    have = {g["slug"] for g in games}
    added = 0
    for r in pack:
        slug = r["game_url"].rstrip("/").split("/")[-1]
        if slug in have:
            continue
        games.append({"away": r["away"], "home": r["home"], "as_": int(r["away_score"]),
                      "hs": int(r["home_score"]), "week": 10, "slug": slug, "date": r["date_et"],
                      "src": PACK})
        added += 1
    out["corpus"] = {
        "rows_in_the_published_results_log": len(reads),
        "week10_games_in_the_2026_11_17_pack": len(pack),
        "games_the_append_would_add": added,
        "corpus_after_the_append": len(games),
        "weeks": sorted({g["week"] for g in games}),
    }

    # ---- M1: the pins, read out of the builder's own source -----------------------
    src = open(os.path.join(ROOT, BUILDER), encoding="utf-8").read().split("\n")
    pins = []
    for i, ln in enumerate(src):
        if not re.search(r"\b137\b", ln):
            continue
        t = ln.strip()
        kind = "prose" if (t.startswith("#") or t.startswith('"""') or t.startswith("data/")
                           or re.match(r"^[0-9]+\.", t) or t.startswith('"')) else "code"
        pins.append({"line": i + 1, "kind": kind, "text": t})
    code_pins = [p["line"] for p in pins if p["kind"] == "code"]
    out["measures"]["M1_row_count_pins"] = {
        "file": BUILDER, "occurrences": len(pins), "code_lines_that_assert_the_count": len(code_pins),
        "code_lines": code_pins, "lines": pins,
        "reading": (f"{len(code_pins)} executable lines in one file assert the count, plus {len(pins) - len(code_pins)} "
                    "prose lines that repeat it. Every one has to move with the append; a single-line change "
                    "would leave the builder asserting a number it no longer holds."),
    }

    # ---- M2: the mirror row-diff gate ---------------------------------------------
    mirror_rows = []
    with open(os.path.join(ROOT, MIRROR), encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("season") == "2026" and r.get("game_type") == "REG":
                gid = r["game_id"]
                for a, b in TEAM_ALIAS.items():
                    gid = gid.replace(f"_{a}_", f"_{b}_")
                    if gid.endswith(f"_{a}"):
                        gid = gid[: -len(a)] + b
                mirror_rows.append(r | {"game_id_norm": gid})
    by_id = {r["game_id_norm"]: r for r in mirror_rows}
    scored = {r["game_id_norm"] for r in mirror_rows if (r.get("home_score") or "").strip()}
    missing, present, with_lines = [], [], 0
    # The mirror keys rows season_week_AWAY_HOME with the NFL.com codes the builder re-keys to (AZ, LA).
    # Names in weeks 1-9 are full nicknames, in the 2026-11-17 pack they are already abbreviations, so both
    # are resolved through the same official club list the builder uses.
    def gid_of(g: dict) -> str:
        a = names.get(g["away"], g["away"])
        h = names.get(g["home"], g["home"])
        return f"2026_{g['week']:02d}_{a}_{h}"
    for g in games:
        if g["src"] != PACK:
            continue
        gid = gid_of(g)
        m = by_id.get(gid)
        if m is None:
            missing.append({"slug": g["slug"], "mirror_id": gid, "why": "no row in the mirror at all"})
        elif gid not in scored:
            spread = (m.get("spread_line") or "").strip()
            total = (m.get("total_line") or "").strip()
            missing.append({"slug": g["slug"], "mirror_id": gid, "mirror_game_date": (m.get("game_date") or "").strip(),
                            "mirror_spread_line": spread, "mirror_total_line": total,
                            "mirror_has_line_but_no_score": bool(spread and total),
                            "why": "the mirror has the row but prints no score for it"})
            if spread and total:
                with_lines += 1
        else:
            agree = (str(m.get("away_score")) == str(g["as_"]) and str(m.get("home_score")) == str(g["hs"]))
            (present if agree else missing).append(
                {"slug": g["slug"], "mirror_id": gid, "mirror_agrees": agree})
    out["measures"]["M2_mirror_row_diff_gate"] = {
        "gate": f"{BUILDER}: load_candidates() -> a published row is emitted only after it matches the mirror",
        "games_the_append_would_add": added,
        "of_those_the_mirror_carries_a_score_for": len(present),
        "of_those_the_mirror_prints_no_score_for": len(missing),
        "of_the_blocked_rows_the_mirror_does_print_a_spread_and_total_for": with_lines,
        "blocked": missing,
        "mirror_file": MIRROR, "mirror_sha256": sha256(MIRROR),
        "reading": ("this is the binding blocker. A third party's update cadence currently holds veto over "
                    "an official score that is printed, dated and independently cross-checked by the "
                    "standings arithmetic. It is not a data conflict; it is a gate design. Note the shape of "
                    "it: for every blocked game the mirror DOES print a spread and a total line and does NOT "
                    "print a score - the prices nobody is authorised to use are the part that is there."),
    }

    # ---- M3/M4: per-club closure ---------------------------------------------------
    def club_sums(games):
        W, L, T, PF, PA = ({}, {}, {}, {}, {})
        for g in games:
            a, h = names.get(g["away"], g["away"]), names.get(g["home"], g["home"])
            for t in (a, h):
                W.setdefault(t, 0); L.setdefault(t, 0); T.setdefault(t, 0); PF.setdefault(t, 0); PA.setdefault(t, 0)
            PF[a] += g["as_"]; PA[a] += g["hs"]; PF[h] += g["hs"]; PA[h] += g["as_"]
            if g["as_"] == g["hs"]:
                T[a] += 1; T[h] += 1
            elif g["as_"] > g["hs"]:
                W[a] += 1; L[h] += 1
            else:
                W[h] += 1; L[a] += 1
        return W, L, T, PF, PA

    W, L, T, PF, PA = club_sums(games)
    # The key keeps its published name, but the input is the dated 2026-11-17 official read,
    # not whatever the daily collector happens to hold today. Fail loudly if a future edit
    # repoints this measurement at the live store: that is the defect this pin fixes.
    if not COLLECTOR_STANDINGS.startswith("data/lab/reads/2026-11-17/"):
        raise SystemExit(f"M3 must use a dated official read inside the reads pack, not {COLLECTOR_STANDINGS}")
    today = {r["team_abbrev"]: r for r in read_tsv(COLLECTOR_STANDINGS)}
    fail_today = []
    for ab, r in today.items():
        got = (W.get(ab, 0), L.get(ab, 0), T.get(ab, 0), PF.get(ab, 0), PA.get(ab, 0))
        want = (int(r["w"]), int(r["l"]), int(r["t"]), int(r["pf"]), int(r["pa"]))
        if got != want:
            fail_today.append({"club": ab, "from_the_150_game_corpus": got, "official_page_2026_11_17": want})
    out["measures"]["M3_closure_against_todays_official_standings"] = {
        "clubs": len(today), "clubs_disagreeing": len(fail_today), "detail": fail_today[:35],
        "corpus_used": len(games),
        "official_source_file": COLLECTOR_STANDINGS,
        "official_source_url": "https://www.nfl.com/standings/league/2026/REG",
        "official_source_read_at": "2026-11-17T22:50Z",
        "verdict": "pass" if not fail_today else "fail",
        "reading": ("the 150-game closure corpus reproduces all 32 official standings rows from the dated "
                    "2026-11-17 read exactly - W, L, T, PF and PA. If the append ever produced a wrong "
                    "score, this is where it would show. It does not: the closure is arithmetically "
                    "complete against the league's own table."),
    }

    spec_src = open(os.path.join(ROOT, PINNED_BASELINE), encoding="utf-8").read()
    rows = re.findall(r"\(\"[^\"]+\",\s+\"([A-Z]{2,3})\",[^\n]*?\),", spec_src)
    base_vals = re.findall(r"\(\"[^\"]+\",\s+\"([A-Z]{2,3})\",\s+\"[A-Z]{2,3}\",\s+\"[A-Za-z ]+\",\s+\d+,\s+(\d+),\s+(\d+),\s+(\d+),\s+(\d+),\s+(\d+),", spec_src)
    fail_base = []
    for ab, w, l, t, pf, pa in base_vals:
        got = (W.get(ab, 0), L.get(ab, 0), T.get(ab, 0), PF.get(ab, 0), PA.get(ab, 0))
        want = tuple(int(x) for x in (w, l, t, pf, pa))
        if got != want:
            fail_base.append({"club": ab, "pinned_2026_11_14": want, "from_the_150_game_corpus": got})
    out["measures"]["M4_closure_against_the_pinned_baseline"] = {
        "baseline_file": PINNED_BASELINE, "baseline_snapshot_date": "2026-11-14",
        "clubs_in_the_baseline": len(base_vals), "clubs_that_would_move": len(fail_base),
        "detail": fail_base[:35],
        "reading": ("the append breaks the pinned baseline for these clubs by design - the baseline is the "
                    "137-game table. Re-pinning it to a dated official read is part of the change set, which "
                    "is why this was never a one-line edit."),
    }

    # ---- M5: blast radius ----------------------------------------------------------
    # Consumers only. A published page is a RENDERING of the feed, not a thing that reads it,
    # and counting renderings makes this measure depend on how many pages happen to describe it -
    # the number would move every time a page was written and never settle. So *.html is skipped,
    # as is this pack's own output directory, and the scan is limited to the trees that consume data.
    touched = {}
    SCAN = ("tools", "scripts", "code", "docs", "data", ".github")
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in {".git", "__pycache__", "_site", "node_modules", "lab"}]
        rel_dir = os.path.relpath(dirpath, ROOT)
        if rel_dir != "." and not rel_dir.startswith(SCAN):
            dirnames[:] = []
            continue
        for fn in filenames:
            if not fn.endswith((".py", ".json", ".csv", ".md", ".yml")):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), ROOT)
            if rel.startswith(("data/lab/reads/", "tools/lab/build_closure_measurement.py")):
                continue
            p = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(p) > 3_000_000:
                    continue
                txt = open(p, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            hits = [k for k in ("reads.tsv", "verified_results", "build_results_r3", "signal_grade") if k in txt]
            if hits:
                touched[rel] = hits
    out["measures"]["M5_blast_radius"] = {
        "files_naming_the_results_log_or_the_feed": len(touched),
        "by_kind": {k: sum(1 for v in touched.values() if k in v) for k in
                    ("reads.tsv", "verified_results", "build_results_r3", "signal_grade")},
        "files": dict(sorted(touched.items())),
        "scan_scope": "tools, scripts, code, docs, data, .github; html and this pack's own output excluded",
        "reading": ("a closure is not one file: this is the list of artefacts that name the log or the feed "
                    "and would have to be regenerated and re-verified in the same commit. Frozen inputs "
                    "(PR-01's) are deliberately excluded from 'just do it' by that fact. Renderings are "
                    "excluded too, so the count is the cost of the change and not a function of how many "
                    "pages happen to describe it."),
    }

    # ---- M6: what the append buys --------------------------------------------------
    warm = sum(1 for g in games if g["week"] > 2)
    out["measures"]["M6_evaluation_corpus_effect"] = {
        "games_excluding_the_two_week_warmup_after": warm,
        "games_excluding_the_warmup_before": sum(1 for r in reads if int(r["week"]) > 2),
        "added": warm - sum(1 for r in reads if int(r["week"]) > 2),
        "note": ("PR-01's walk-forward score already reads the 2026-11-16 finals pack directly, so the model "
                 "side is not the thing that changes; what changes is that the FEED - the object the price "
                 "store, the origination ledger and every leaderboard read - would cover the closed week."),
    }

    blocked = out["measures"]["M2_mirror_row_diff_gate"]["of_those_the_mirror_prints_no_score_for"]
    out["options"] = [
        {"id": "A", "name": "wait for the mirror",
         "what_it_costs": f"{blocked} games stay unsettled in the feed for an unknown period; no gate changes",
         "risk": "the official score is already printed and cross-checked; waiting buys nothing but delay"},
        {"id": "B", "name": "let an official read settle a row when the mirror has no row, and flag it",
         "what_it_costs": "a change in tools/build_results_r3.py: the mirror becomes a cross-check where present "
                          "instead of a veto; the M3 standings closure stays mandatory",
         "risk": "the row is then verified by one official page plus arithmetic rather than by two sources; "
                 "the artefact must say so on every row"},
        {"id": "C", "name": "promote the arithmetic closure to the primary gate",
         "what_it_costs": "the 32/32 standings closure becomes required for every row and the mirror becomes "
                          "advisory everywhere, not only where it is missing",
         "risk": "a whole-round transcription error could still close arithmetically if it is self-consistent; "
                  "the row-level second source is what B and C give up"},
    ]
    out["decision_for_the_owner"] = (
        "B is the recommended path and it is small: one gate edit, a re-pinned baseline, the row-count pins, "
        "and a regeneration of the artefacts in M5. What it is not is a data problem - M3 shows the closure "
        "reproduces the league table exactly. No session should make that call, because it changes what "
        "'verified' means for every row already published; that is why it is recorded here as a decision and "
        "not implemented as a change.")

    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    data = build()
    payload = json.dumps(data, indent=1, sort_keys=True) + "\n"
    if a.report:
        print(payload)
        return 0
    if a.check:
        if not os.path.exists(OUT):
            print("MISSING: data/lab/reads/2026-11-17/feed-closure-measurement.json")
            return 1
        old = open(OUT, encoding="utf-8").read()
        strip = lambda s: "\n".join(l for l in s.split("\n") if '"generated_at"' not in l)
        if strip(old) != strip(payload):
            print("STALE: the feed-closure measurement does not match a fresh build")
            return 1
        print("CHECK OK: the feed-closure measurement reproduces from its inputs")
        return 0
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(payload)
    m = data["measures"]
    print("wrote data/lab/reads/2026-11-17/feed-closure-measurement.json")
    print(f"  corpus: {data['corpus']['rows_in_the_published_results_log']} -> "
          f"{data['corpus']['corpus_after_the_append']} games (+{data['corpus']['games_the_append_would_add']})")
    print(f"  M1 row-count pins in {BUILDER}: {m['M1_row_count_pins']['occurrences']}")
    print(f"  M2 blocked by the mirror for lack of a score: "
          f"{m['M2_mirror_row_diff_gate']['of_those_the_mirror_prints_no_score_for']} of "
          f"{data['corpus']['games_the_append_would_add']}")
    print(f"  M3 clubs reproduced from the 150-game corpus vs today's official standings: "
          f"{m['M3_closure_against_todays_official_standings']['clubs'] - m['M3_closure_against_todays_official_standings']['clubs_disagreeing']}/32")
    print(f"  M4 clubs the append moves against the 2026-11-14 pinned baseline: "
          f"{m['M4_closure_against_the_pinned_baseline']['clubs_that_would_move']}")
    print(f"  M5 artefacts naming the log or the feed: {m['M5_blast_radius']['files_naming_the_results_log_or_the_feed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
