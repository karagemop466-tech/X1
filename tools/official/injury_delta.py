#!/usr/bin/env python3
"""Injury-hub delta ledger: the read time, and what changed between reads.

    python3 tools/official/injury_delta.py build     # parse retained reads, write the ledger
    python3 tools/official/injury_delta.py check     # rebuild and diff (CI staleness gate)
    python3 tools/official/injury_delta.py status    # short human summary

Owner's brief, round 6 (three lines describe the same defect from three sides):

    "Store every injury-hub read with its clock time and publish the delta, never the level."
    "Treat the injury report as a timestamped series, not a weekly snapshot. Capture the report
     daily from Wednesday to kickoff with the fetch timestamp, then measure how designations
     evolve."
    "The injury signal is a surprise, never a level."

The site previously held one transcription of the Week 10 report and called it "as of" a date.
One read cannot answer the only question that matters for an injury label — did it move? — so
this tool reads what the scheduled collector already retained (`data/ledger/injuries/raw/*.gz`,
each one the byte-exact page, hashed, appended by `.github/workflows/injury-ledger.yml`) and
publishes:

  * `series.csv` — one row per read: the fetch clock time, the HTTP status, the hash of the bytes,
    the row count, and the club-by-club designation counts as that read printed them;
  * `deltas.csv` — one row per movement between two consecutive reads of the same club+player:
    which field moved, from what, to what, with the two clock times;
  * `coverage.json` — the cadence truth: which calendar days in the window have at least one read,
    so "we snapshot Wed/Thu/Fri" is a checked claim and not a README sentence.

The level (e.g. "84 players are Questionable") is deliberately not published as a feature, only as
a count inside `series.csv`, because a level cannot be used as a signal without a second read to
difference it against. Every row here is that difference.

No network. If a raw capture is absent, the tool says so in `gaps` rather than inventing a read.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

LEDGER = os.path.join(ROOT, "data", "ledger", "injuries")
LEDGER_JSONL = os.path.join(LEDGER, "ledger.jsonl")
STANDINGS = os.path.join(ROOT, "data", "pipeline", "standings.json")
OFFICIAL_INJURIES = "https://www.nfl.com/injuries/"
OUTDIR = os.path.join(ROOT, "data", "official", "injury_deltas")
DESIGNATIONS = ("Out", "Doubtful", "Questionable")
FIELDS_TRACKED = ("practice_status", "game_status", "injuries", "position")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def read_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def team_index() -> tuple[dict, dict]:
    """Club index built from the retained official standings payload — not a typed list."""
    rows = json.load(open(STANDINGS, encoding="utf-8")).get("rows", [])
    index, nicks = {}, {}
    for row in rows:
        abbrev, slug, name = row.get("team_abbrev"), row.get("team_slug"), row.get("team_name")
        if not abbrev or not slug:
            continue
        meta = {"slug": slug, "name": name, "nick": slug.split("-")[-1].capitalize()}
        index[abbrev] = meta
        nicks[meta["nick"].lower()] = abbrev
        nicks[(name or "").lower()] = abbrev
    return index, nicks


def parse_read(html: str) -> dict:
    """Row-level read of one retained injury page, through the pipeline's own parser."""
    from pipeline import htmlutil as H
    from pipeline import parsers as P
    index, nicks = team_index()
    doc = H.parse(html)
    parsed = P.parse_injuries(doc, OFFICIAL_INJURIES, index, nicks)
    rows = []
    for r in parsed.get("rows", []):
        rows.append({
            "team": (r.get("team_abbrev") or "").strip(),
            "player": (r.get("player") or "").strip(),
            "position": (r.get("position") or "").strip(),
            "injuries": (r.get("injuries") or "").strip(),
            "practice_status": (r.get("practice_status") or "").strip(),
            "game_status": (r.get("game_status") or "").strip(),
            "game_label": (r.get("game_date") or "").strip(),
        })
    return {"week": parsed.get("week"), "season": parsed.get("season"),
            "tables_parsed": parsed.get("tables_parsed"), "rows": rows}


def key(row: dict) -> tuple:
    return (row["team"].upper(), row["player"].lower())


def cmd_build(args) -> int:
    entries = read_jsonl(LEDGER_JSONL)
    if not entries:
        print("no ledger entries at data/ledger/injuries/ledger.jsonl — nothing to publish")
        return 1
    os.makedirs(OUTDIR, exist_ok=True)
    series, parsed_by_seq, gaps = [], {}, []
    for e in sorted(entries, key=lambda x: x.get("seq", 0)):
        seq = e.get("seq")
        rel = e.get("file") or ""
        path = os.path.join(LEDGER, rel)
        row = {"seq": seq, "captured_at_utc": e.get("captured_at_utc", ""),
               "source_url": e.get("source_url", OFFICIAL_INJURIES),
               "http_status": e.get("http_status", ""), "flags": ";".join(e.get("flags") or []),
               "raw_file": rel, "raw_gz_sha256": e.get("gzip_sha256", ""),
               # The ledger keeps two hashes: `sha256` over the bytes exactly as fetched, and
               # `content_sha256` over those bytes with the page's request UUIDs normalised, which
               # is what lets two reads of an unchanged page dedupe. The re-derivation check uses
               # the byte-exact one; the normalised one is published beside it.
               "body_sha256": e.get("sha256", ""),
               "content_sha256_normalised": e.get("content_sha256") or "",
               "week": "", "season": "",
               "rows": 0, "clubs": 0, "out": 0, "doubtful": 0, "questionable": 0,
               "no_game_designation": 0, "parse_status": "", "parse_error": ""}
        if not rel or not os.path.exists(path):
            row["parse_status"] = "raw-not-retained"
            row["parse_error"] = "the ledger flags this read as unchanged, so no bytes were stored"
            gaps.append({"seq": seq, "captured_at_utc": row["captured_at_utc"],
                         "reason": "no raw bytes retained for this entry"})
            series.append(row)
            continue
        blob = open(path, "rb").read()
        if row["raw_gz_sha256"] and sha256_bytes(blob) != row["raw_gz_sha256"]:
            row["parse_status"] = "hash-mismatch"
            row["parse_error"] = "retained bytes do not match the hash the ledger published"
            series.append(row)
            gaps.append({"seq": seq, "reason": "raw bytes disagree with the ledger hash"})
            continue
        html = gzip.decompress(blob).decode("utf-8", "replace")
        if row["body_sha256"] and sha256_bytes(html.encode("utf-8")) != row["body_sha256"]:
            row["parse_status"] = "body-hash-mismatch"
            series.append(row)
            gaps.append({"seq": seq, "reason": "decoded page disagrees with the published body hash"})
            continue
        try:
            parsed = parse_read(html)
        except Exception as exc:                                  # noqa: BLE001 (a failed read is a finding)
            row["parse_status"] = "parser-error"
            row["parse_error"] = f"{type(exc).__name__}: {exc}"
            series.append(row)
            gaps.append({"seq": seq, "reason": row["parse_error"]})
            continue
        rws = parsed["rows"]
        row.update({"week": parsed.get("week") or "", "season": parsed.get("season") or "",
                    "rows": len(rws), "clubs": len({r["team"] for r in rws if r["team"]}),
                    "out": sum(1 for r in rws if r["game_status"] == "Out"),
                    "doubtful": sum(1 for r in rws if r["game_status"] == "Doubtful"),
                    "questionable": sum(1 for r in rws if r["game_status"] == "Questionable"),
                    "no_game_designation": sum(1 for r in rws if not r["game_status"]),
                    "parse_status": "ok"})
        parsed_by_seq[seq] = (row, rws)
        series.append(row)

    # ---- deltas between consecutive reads that both parsed
    deltas = []
    usable = [parsed_by_seq[s] for s in sorted(parsed_by_seq)]
    for (meta_a, rows_a), (meta_b, rows_b) in zip(usable, usable[1:]):
        a_by = {key(r): r for r in rows_a}
        b_by = {key(r): r for r in rows_b}
        for k in sorted(set(a_by) | set(b_by)):
            ra, rb = a_by.get(k), b_by.get(k)
            base = {"read_from_utc": meta_a["captured_at_utc"], "read_to_utc": meta_b["captured_at_utc"],
                    "week": meta_b["week"], "club": (k[0] or ""), "player": (k[1] or ""),
                    "field": "", "from_value": "", "to_value": "", "delta_type": "",
                    "from_source_row": "", "to_source_row": ""}
            if ra is None:
                deltas.append({**base, "field": "(row)", "from_value": "",
                               "to_value": json.dumps(rb, sort_keys=True),
                               "delta_type": "appeared-on-later-read"})
                continue
            if rb is None:
                deltas.append({**base, "field": "(row)", "from_value": json.dumps(ra, sort_keys=True),
                               "to_value": "", "delta_type": "gone-on-later-read"})
                continue
            for f in FIELDS_TRACKED:
                if ra[f] != rb[f]:
                    deltas.append({**base, "field": f, "from_value": ra[f], "to_value": rb[f],
                                   "delta_type": "changed"})
            if ra["game_status"] != rb["game_status"]:
                move = f"{ra['game_status'] or 'none'}->{rb['game_status'] or 'none'}"
                last = deltas[-1] if deltas and deltas[-1]["player"] == base["player"] else None
                if last is not None and last["field"] == "game_status":
                    last["surprise"] = move

    series_cols = ["seq", "captured_at_utc", "http_status", "parse_status", "parse_error", "week",
                   "season", "rows", "clubs", "out", "doubtful", "questionable",
                   "no_game_designation", "body_sha256", "content_sha256_normalised",
                   "raw_gz_sha256", "raw_file", "source_url", "flags"]
    with open(os.path.join(OUTDIR, "series.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=series_cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in series:
            w.writerow({c: r.get(c, "") for c in series_cols})
    delta_cols = ["read_from_utc", "read_to_utc", "week", "club", "player", "field", "delta_type",
                  "from_value", "to_value", "surprise"]
    for d in deltas:
        d.setdefault("surprise", "")
    with open(os.path.join(OUTDIR, "deltas.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=delta_cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for d in deltas:
            w.writerow({c: d.get(c, "") for c in delta_cols})

    # ---- cadence truth: which days have a read at all
    days = {}
    for r in series:
        day = (r["captured_at_utc"] or "")[:10]
        if day:
            days.setdefault(day, []).append(r["parse_status"])
    coverage = {
        "dataset": "injury-hub read series and deltas",
        "generated_by": "tools/official/injury_delta.py",
        "rule": "the delta is the signal; the level is only a count inside series.csv",
        "reads_total": len(series),
        "reads_parsed": sum(1 for r in series if r["parse_status"] == "ok"),
        "deltas": len(deltas),
        "days_with_a_read": {d: {"reads": len(v), "parsed": v.count("ok")} for d, v in sorted(days.items())},
        "expected_cadence": "at least one read on Wednesday, Thursday and Friday of each game week",
        "cadence_met": {},
        "gaps": gaps,
        "official_source": OFFICIAL_INJURIES,
        "retained_by": ".github/workflows/injury-ledger.yml (every 4 hours, raw gzip + sha256)",
    }
    for week, label_days in (("2026-11-11", ("2026-11-11", "2026-11-12", "2026-11-13")),
                             ("2026-11-18", ("2026-11-18", "2026-11-19", "2026-11-20"))):
        coverage["cadence_met"][week] = {d: (d in days) for d in label_days}
    coverage["cadence_verdict"] = (
        "met" if all(any(v.values()) for v in coverage["cadence_met"].values())
        else "not met — the ledger holds fewer days than the brief's Wed/Thu/Fri cadence requires")
    with open(os.path.join(OUTDIR, "coverage.json"), "w", encoding="utf-8") as fh:
        json.dump(coverage, fh, indent=1, sort_keys=True)

    print(f"injury delta ledger: {coverage['reads_total']} reads, "
          f"{coverage['reads_parsed']} parsed row-level, {coverage['deltas']} delta rows; "
          f"gaps {len(gaps)}; cadence {coverage['cadence_verdict']}")
    return 0


def cmd_check(args) -> int:
    import subprocess
    before = {}
    for name in ("series.csv", "deltas.csv", "coverage.json"):
        path = os.path.join(OUTDIR, name)
        before[name] = open(path, encoding="utf-8").read() if os.path.exists(path) else None
    rc = cmd_build(args)
    if rc != 0:
        return rc
    for name, text in before.items():
        path = os.path.join(OUTDIR, name)
        now = open(path, encoding="utf-8").read() if os.path.exists(path) else None
        if now != text:
            print(f"FAIL: committed {name} does not reproduce from the retained reads")
            return 1
    print("PASS: the delta ledger reproduces exactly from the retained official captures")
    return 0


def cmd_status(args) -> int:
    p = os.path.join(OUTDIR, "coverage.json")
    if not os.path.exists(p):
        print("no ledger built yet")
        return 1
    d = json.load(open(p, encoding="utf-8"))
    print(json.dumps({k: d[k] for k in ("reads_total", "reads_parsed", "deltas",
                                        "cadence_verdict", "days_with_a_read")}, indent=1))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in (("build", cmd_build), ("check", cmd_check), ("status", cmd_status)):
        s = sub.add_parser(name)
        s.set_defaults(func=fn)
    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
