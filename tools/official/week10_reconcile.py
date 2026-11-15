"""Reconcile every published read of the official Week 10 injury report.

Session `arena-b03ced7c-x1`. Additive: this module never rewrites another
session's files, and it never fills a value. It compares the official page as
it stands today (2026-11-15) against **every** read of the same page that this
repository has published, and writes the disagreements down.

Reads (all four are committed in the repository, so the comparison is
reproducible without network access):

  1. `data/official/2026_w10_capture_2026-11-15T1814z/official_injuries_week10_2026-11-15T1814z.psv`
       this session's independent read of https://www.nfl.com/injuries/league/2026/reg10
       (read 2026-11-15T18:14Z, 8 of 8 chunks)
  2. `data/capture/2026_w10/official_nflcom_injuries_week10_transcription.psv`
       session arena-ed8c600d-x1's read of the same page, same day (PR #49)
  3. `data/nfl/injuries_week10.tsv`
       the published 2026-11-14 table (345 data rows)
  4. `data/console/injuries_week10.csv`
       the table the console renders (345 data rows, derived from 3)

Outputs (all new):
  data/console/week10_reconcile.json   machine-readable, one record per finding
  data/console/week10_reconcile.csv    row-level diff matrix

A "read conflict" — two reads of the same page, same day, that disagree on a
cell — is reported separately from a "stale read" (the 11-14 table versus the
live page). Conflating them would let a transcription slip hide inside a
genuinely-dated change, which is the failure mode this file exists to catch.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SRC_URL = "https://www.nfl.com/injuries/league/2026/reg10"
TODAY = "2026-11-15"

PRACTICE_FULL = "Full Participation in Practice"
PRACTICE_LTD = "Limited Participation in Practice"
PRACTICE_DNP = "Did Not Participate In Practice"
PRACTICE_SHORT = {PRACTICE_FULL: "Full", PRACTICE_LTD: "Limited", PRACTICE_DNP: "DNP"}

# Captures, newest first. `kind` drives how a disagreement is reported.
CAPTURES = [
    dict(
        key="live_2026_11_15",
        label="This session's read of the live page, 2026-11-15T18:14Z",
        path="data/official/2026_w10_capture_2026-11-15T1814z/"
             "official_injuries_week10_2026-11-15T1814z.psv",
        fmt="psv_game_team",
        captured="2026-11-15T18:14Z",
        kind="live",
    ),
    dict(
        key="e1_2026_11_15",
        label="Session ed8c600d's read of the live page, 2026-11-15 (PR #49)",
        path="data/capture/2026_w10/official_nflcom_injuries_week10_transcription.psv",
        fmt="psv_game_team",
        captured="2026-11-15",
        kind="live",
    ),
    dict(
        key="published_2026_11_14",
        label="The published 2026-11-14 table",
        path="data/nfl/injuries_week10.tsv",
        fmt="tsv_published",
        captured="2026-11-14",
        kind="published",
    ),
]


def _sha(path):
    with open(os.path.join(ROOT, path), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _read(key, path, fmt):
    """Return {(team, player): row} plus the file's own metadata."""
    full = os.path.join(ROOT, path)
    rows = []
    meta = {}
    if fmt == "psv_game_team":
        with open(full, encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if line.startswith("#"):
                    if "SOURCE:" in line and "source" not in meta:
                        meta["source_line"] = line.lstrip("# ").strip()
                    continue
                if not line.strip():
                    continue
                parts = line.split("|")
                if len(parts) != 7:
                    raise SystemExit(f"{path}: expected 7 fields, got {len(parts)}: {line!r}")
                game, team, player, pos, inj, prac, status = parts
                rows.append(dict(game=game, team=team, player=player, pos=pos,
                                 injury=inj, practice=prac, status=status))
    elif fmt == "tsv_published":
        with open(full, encoding="utf-8") as fh:
            body = [ln for ln in fh if not ln.startswith("#")]
        for r in csv.DictReader(body, delimiter="\t"):
            rows.append(dict(game=r["game"], team=r["team"], player=r["player"],
                             pos=r["position"], injury=r["injury"],
                             practice=r["practice_status"], status=r["game_status"]))
    else:  # pragma: no cover - guarded by the table above
        raise SystemExit(f"unknown format {fmt!r}")

    idx = {}
    dupes = []
    for r in rows:
        k = (r["team"], r["player"])
        if k in idx:
            dupes.append(k)
        idx[k] = r
    meta.update(rows=len(rows), clubs=len({r["team"] for r in rows}),
                games=len({r["game"] for r in rows}), duplicates=dupes,
                sha256=_sha(path))
    return idx, meta


def _norm_status(s):
    s = (s or "").strip()
    return {"": "(none)", "Full": PRACTICE_FULL, "Limited": PRACTICE_LTD,
            "DNP": PRACTICE_DNP}.get(s, s)


def build():
    caps = {}
    metas = {}
    for c in CAPTURES:
        idx, meta = _read(c["key"], c["path"], c["fmt"])
        caps[c["key"]] = idx
        metas[c["key"]] = dict(meta, **{k: c[k] for k in ("label", "path", "captured", "kind")})

    live = caps["live_2026_11_15"]
    live_keys = set(live)

    # ---- 1. row-level presence vs the live page -------------------------
    presence = {}
    for c in CAPTURES[1:]:
        have = set(caps[c["key"]])
        presence[c["key"]] = dict(
            missing=[{"team": t, "player": p, **{k: live[(t, p)][k] for k in ("game", "pos", "injury", "practice", "status")}}
                     for (t, p) in sorted(live_keys - have)],
            extra=[{"team": t, "player": p} for (t, p) in sorted(have - live_keys)],
        )

    # ---- 2. cell-level disagreements ------------------------------------
    FIELDS = ("injury", "practice", "status")
    cells = []
    for c in CAPTURES[1:]:
        other = caps[c["key"]]
        for k in sorted(live_keys & set(other)):
            for f in FIELDS:
                a = live[k][f]
                b = other[k][f]
                if f == "practice":
                    a2, b2 = _norm_status(a), _norm_status(b)
                else:
                    a2, b2 = (a or "").strip(), (b or "").strip()
                if a2 != b2:
                    cells.append(dict(
                        capture=c["key"], captured=c["captured"], kind=c["kind"],
                        team=k[0], player=k[1], game=live[k]["game"], field=f,
                        live_value=a, other_value=b,
                    ))

    # ---- 3. status-count deltas -----------------------------------------
    def counts(idx):
        return Counter(_norm_status(r["status"]) if r["status"] else "(none)" for r in idx.values())

    live_counts = counts(live)

    # ---- 4. read conflicts: same-day independent reads of one page ------
    e1 = caps["e1_2026_11_15"]
    conflicts = []
    for k in sorted(live_keys | set(e1)):
        if k not in live or k not in e1:
            conflicts.append(dict(team=k[0], player=k[1], field="presence",
                                  this_session="printed" if k in live else "absent",
                                  other_session="printed" if k in e1 else "absent"))
            continue
        for f in FIELDS:
            a, b = live[k][f], e1[k][f]
            if f == "practice":
                a, b = _norm_status(a), _norm_status(b)
            else:
                a, b = (a or "").strip(), (b or "").strip()
            if a != b:
                conflicts.append(dict(team=k[0], player=k[1], field=f,
                                      this_session=live[k][f], other_session=e1[k][f]))

    # ---- 5. what the published page's own summary claims ----------------
    published = caps["published_2026_11_14"]
    pub_counts = counts(published)

    findings = []
    f_n = 0

    def add(severity, area, finding, effect, source_url=SRC_URL):
        nonlocal f_n
        f_n += 1
        findings.append(dict(id=f"R10-{f_n:02d}", severity=severity, area=area,
                             finding=finding, effect=effect, source=source_url))

    miss345 = presence["published_2026_11_14"]["missing"]
    if miss345:
        add("amber", "Injury report rows",
            f"The published 2026-11-14 table is missing {len(miss345)} row(s) that the live page prints: "
            + "; ".join(f"{m['team']} {m['player']}" for m in miss345) + ".",
            "A player absent from the table cannot be joined to a depth slot, so a real replacement "
            "at those slots is invisible to the availability model.")
    live_vs_pub = [c for c in cells if c["capture"] == "published_2026_11_14"]
    if live_vs_pub:
        add("amber", "Injury report cells",
            f"{len(live_vs_pub)} cell(s) differ between the published 2026-11-14 table and the live page "
            f"across {len({(c['team'], c['player']) for c in live_vs_pub})} player(s).",
            "Either the designations changed between the two dates (expected: the report is a daily "
            "series) or the 11-14 read carries transcription errors. The two cannot be told apart from "
            "the data alone — which is why the dated capture matters more than the row count.")
    if conflicts:
        add("red", "Read conflict",
            f"This session's read and session ed8c600d's read of the SAME page on the SAME day disagree "
            f"on {len(conflicts)} cell(s).",
            "At most one of the two can be right. Until a byte-level capture exists, every conflicting "
            "cell must be treated as unverified rather than resolved by preference.")
    else:
        add("green", "Read conflict",
            "This session's read and session ed8c600d's read of the same page on the same day agree on "
            "every cell, every row and every club.",
            "Two independent reads agreeing is the strongest evidence this repository can produce "
            "without retaining raw response bytes.")
    add("amber", "Provenance",
        "No raw response bytes are retained for any injury-report read in this repository: nfl.com is "
        "unreachable over TLS from the sandbox's bash (curl exit 35), so every capture is a transcription "
        "made through a text-extraction tool.",
        "A transcription cannot prove that no cell was dropped or altered in extraction. The hashed "
        "byte ledger claimed by session arena/c0461519-x1 is the fix; until it lands, every injury cell "
        "is 'transcribed', not 'byte-verified'.")

    # ---- 6. published-page consistency ----------------------------------
    console_path = "data/console/injuries_week10.csv"
    console_rows = []
    with open(os.path.join(ROOT, console_path), encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            console_rows.append(r)
    console_idx = {(r["TEAM"], r["PLAYER"]): r for r in console_rows}
    console_diff = []
    short = {"Full": PRACTICE_FULL, "Limited": PRACTICE_LTD, "DNP": PRACTICE_DNP}
    for k in sorted(set(published) & set(console_idx)):
        c = console_idx[k]
        p = published[k]
        if (c["INJURY"] or "") != (p["injury"] or "") \
           or short.get(c["PRACTICE"], c["PRACTICE"]) != _norm_status(p["practice"]) \
           or (c["GAMESTATUS"] or "") != (p["status"] or ""):
            console_diff.append(k)

    out = dict(
        generated_for=TODAY,
        source_url=SRC_URL,
        rule=("A disagreement is published, never resolved by preference. 'Read conflict' means two "
              "reads of the same page on the same day disagree; 'stale read' means the published "
              "table predates the page. The two are reported apart because only the first is a "
              "transcription risk."),
        captures=metas,
        status_counts=dict(live=dict(live_counts), published_2026_11_14=dict(pub_counts)),
        presence=presence,
        cells=cells,
        conflicts=conflicts,
        console_vs_published=dict(rows=len(console_rows), differing=len(console_diff)),
        findings=findings,
    )
    return out


def main():
    out = build()
    data_dir = os.path.join(ROOT, "data", "console")
    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, "week10_reconcile.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=False)
        fh.write("\n")
    with open(os.path.join(data_dir, "week10_reconcile.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["CAPTURE", "CAPTURED", "KIND", "TEAM", "PLAYER", "GAME", "FIELD",
                    "LIVE_VALUE", "OTHER_VALUE", "SOURCE"])
        for c in out["cells"]:
            w.writerow([c["capture"], c["captured"], c["kind"], c["team"], c["player"],
                        c["game"], c["field"], c["live_value"], c["other_value"], SRC_URL])
    live_meta = out["captures"]["live_2026_11_15"]
    print(f"[reconcile] live read: {live_meta['rows']} rows, {live_meta['clubs']} clubs, "
          f"{live_meta['games']} games")
    for k, m in out["captures"].items():
        if k == "live_2026_11_15":
            continue
        p = out["presence"][k]
        print(f"[reconcile] {k}: rows={m['rows']} missing={len(p['missing'])} "
              f"extra={len(p['extra'])} cell_diffs={sum(1 for c in out['cells'] if c['capture'] == k)}")
    print(f"[reconcile] read conflicts (same page, same day): {len(out['conflicts'])}")
    print(f"[reconcile] console table vs published table: "
          f"{out['console_vs_published']['differing']} differing of "
          f"{out['console_vs_published']['rows']}")
    print(f"[reconcile] status counts live: {dict(out['status_counts']['live'])}")
    print(f"[reconcile] status counts published: {dict(out['status_counts']['published_2026_11_14'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
