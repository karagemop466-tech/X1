#!/usr/bin/env python3
"""Gate for the injury-report delta series.

    python3 tools/verify_availability_series.py            # run the checks
    python3 tools/verify_availability_series.py --check     # same, for CI (also fails on stale files)

Eight checks. Each one fails loudly with the number it expected and the number it found, so a
drift in the series is a build failure rather than a quietly published table.

  A  retained payloads still hash to the content hash the capture store published
  B  the series covers every injury capture in the store, and no invented ones
  C  every state-to-state delta reproduces from the payloads
  D  every change row is a real change (from != to) on a compared field for a known club
  E  the alias claim reproduces: the raw-team join really does invent the phantom churn it says
  F  the surprise window contains exactly the downgrades inside it, by definition
  G  no state after the anchor is published without a delta
  H  the committed files are exactly what the builder writes (staleness)
"""
from __future__ import annotations

import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import tools.build_availability_series as B  # noqa: E402

SERIES = os.path.join(ROOT, "data", "availability_series")
IDX = os.path.join(ROOT, "data", "captures", "index.jsonl")

CLUBS = set()
with open(os.path.join(ROOT, "data", "console", "w10_finals_2026_11_17.csv"), encoding="utf-8") as fh:
    for r in csv.DictReader(fh):
        CLUBS.add(B.CLUB_ALIAS.get(r["away"], r["away"]))
        CLUBS.add(B.CLUB_ALIAS.get(r["home"], r["home"]))


def _load(name):
    with open(os.path.join(SERIES, name), encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    fails, notes = [], []

    captures, states, changes, movement, summary = B.build()
    pub_captures = _load("captures.csv")
    pub_states = _load("states.csv")
    pub_changes = _load("changes.csv")

    # ---- A: payload immutability, recomputed from the files on disk -----------
    n_a = 0
    for c in pub_captures:
        path = os.path.join(ROOT, c["payload_file"])
        if not os.path.exists(path):
            fails.append(f"A: payload missing for {c['capture_id']}: {c['payload_file']}")
            continue
        rows = B._rows_of(dict(payload=c["payload_file"]))
        rehash = B._content_sha(rows)
        if rehash != c["content_sha256"]:
            fails.append(f"A: {c['capture_id']} payload now hashes {rehash[:12]} != published "
                         f"{c['content_sha256'][:12]}")
        elif B._sha_file(path) != c["payload_sha256_file"]:
            fails.append(f"A: {c['capture_id']} payload file bytes changed (file sha mismatch)")
        else:
            n_a += 1
    notes.append(f"A: {n_a}/{len(pub_captures)} retained payloads reproduce their published hash")

    # ---- B: coverage of the capture store ------------------------------------
    idx_inj = [e for e in B._read_jsonl(IDX) if e.get("dataset") == B.DATASET]
    if len(idx_inj) != len(pub_captures):
        fails.append(f"B: store holds {len(idx_inj)} injury captures, series publishes "
                     f"{len(pub_captures)}")
    if len({e["content_sha256"] for e in idx_inj}) != len(pub_states):
        fails.append(f"B: store holds {len({e['content_sha256'] for e in idx_inj})} distinct contents, "
                     f"series publishes {len(pub_states)} states")
    sum_states = sum(int(s["n_reads"]) for s in pub_states)
    if sum_states != len(pub_captures):
        fails.append(f"B: states account for {sum_states} reads, captures.csv has {len(pub_captures)}")
    notes.append(f"B: {len(pub_captures)} captures / {len(pub_states)} distinct contents, "
                 f"all reads accounted for")

    # ---- C: deltas reproduce --------------------------------------------------
    for pub, mine in zip(pub_states, states):
        if pub["delta_vs_prev_state"] != mine["delta_vs_prev_state"]:
            fails.append(f"C: {pub['state_id']} delta does not reproduce: published "
                         f"{pub['delta_vs_prev_state']!r}, recomputed {mine['delta_vs_prev_state']!r}")
    notes.append(f"C: {len(pub_states)} state deltas recomputed from the payloads")

    # ---- D: change rows -------------------------------------------------------
    bad = [c for c in pub_changes if c["from_value"] == c["to_value"]
           or c["field"] not in B.CHANGE_FIELDS
           or c["team"] not in CLUBS]
    if bad:
        fails.append(f"D: {len(bad)} change rows are not real changes for known clubs "
                     f"(first: {bad[0]['team']} {bad[0]['player']} {bad[0]['field']})")
    if len(pub_changes) != int(summary["counts"]["cell_changes"]):
        fails.append(f"D: summary says {summary['counts']['cell_changes']} changes, table has "
                     f"{len(pub_changes)}")
    notes.append(f"D: {len(pub_changes)} change rows, all from!=to on a compared field for a known club")

    # ---- E: the alias claim ---------------------------------------------------
    prev_rows = None
    by_capture_id = {c["capture_id"]: c for c in pub_captures}
    for s in states:
        first = by_capture_id.get(s["first_capture_id"])
        if first is None:
            fails.append(f"E: state {s['state_id']} cites a capture the store does not hold")
            continue
        rows = B._rows_of(dict(payload=first["payload_file"]))
        if prev_rows is not None:
            d = B.diff(prev_rows, rows)
            pub = by_capture_id and next(x for x in pub_states if x["state_id"] == s["state_id"])
            if int(pub["phantom_added_if_joined_on_raw_team"] or 0) != d["phantom"]["added"] \
                    or int(pub["phantom_removed_if_joined_on_raw_team"] or 0) != d["phantom"]["removed"]:
                fails.append(f"E: {s['state_id']} phantom churn does not reproduce "
                             f"(published +{pub['phantom_added_if_joined_on_raw_team']}/"
                             f"-{pub['phantom_removed_if_joined_on_raw_team']}, recomputed "
                             f"+{d['phantom']['added']}/-{d['phantom']['removed']})")
            elif pub["phantom_added_if_joined_on_raw_team"]:
                ex_a = d["phantom"]["added"] - len(d["added"])
                ex_r = d["phantom"]["removed"] - len(d["removed"])
                notes.append(f"E: {s['state_id']} a raw-team join would invent "
                             f"+{d['phantom']['added']}/-{d['phantom']['removed']} where the "
                             f"alias-normalised join finds +{len(d['added'])}/-{len(d['removed'])} "
                             f"- the alias is worth {ex_a} phantom arrivals and {ex_r} phantom "
                             f"departures on this pair")
        prev_rows = rows

    # ---- F: surprise window ---------------------------------------------------
    in_win = [c for c in pub_changes if c["in_surprise_window"] == "yes"]
    if any(c["direction"] != "downgrade" for c in in_win):
        fails.append("F: a row is inside the surprise window without being a downgrade")
    for c in pub_changes:
        if c["hours_to_kickoff"]:
            h = float(c["hours_to_kickoff"])
            if c["in_surprise_window"] == "yes" and not (0 < h <= B.SURPRISE_WINDOW_H):
                fails.append(f"F: {c['player']} hours_to_kickoff {h} is outside the window but flagged inside")
            if c["direction"] == "downgrade" and 0 < h <= B.SURPRISE_WINDOW_H \
                    and c["in_surprise_window"] != "yes":
                fails.append(f"F: {c['player']} is a downgrade {h} h before kickoff and is not flagged")
    if len(in_win) != int(summary["counts"]["downgrades_in_surprise_window"]):
        fails.append(f"F: summary says {summary['counts']['downgrades_in_surprise_window']} downgrades "
                     f"in window, table has {len(in_win)}")
    notes.append(f"F: {len(in_win)} downgrades inside {B.SURPRISE_WINDOW_H:.0f} h of kickoff "
                 f"(definition published in summary.json)")

    # ---- G: no state without a delta -----------------------------------------
    for s in pub_states[1:]:
        if "cell changes" not in s["delta_vs_prev_state"]:
            fails.append(f"G: state {s['state_id']} is published without a computed delta: "
                         f"{s['delta_vs_prev_state']!r}")
    if "anchor" not in pub_states[0]["delta_vs_prev_state"]:
        fails.append("G: the first state must say it is an anchor, not claim a zero delta")
    notes.append(f"G: {len(pub_states) - 1} state(s) carry a delta; the anchor says so explicitly")

    # ---- H: staleness ---------------------------------------------------------
    if B.write(captures, states, changes, movement, summary, check=True) != 0:
        fails.append("H: the committed series files are not what the builder writes")
    else:
        notes.append("H: series files reproduce byte for byte")

    print("[availability-series] " + f"{len(states)} states, {len(changes)} cell changes, "
          f"{len(movement)} game groups")
    for n in notes:
        print("   " + n)
    if fails:
        print("\nFAIL")
        for f in fails:
            print("  - " + f)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
