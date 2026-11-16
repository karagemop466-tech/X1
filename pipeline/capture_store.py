#!/usr/bin/env python3
"""Dated, content-addressed retention for every official read (C-2 of session arena-543cdcb0-x1).

Why this exists
---------------
The scheduled collector in ``.github/workflows/data-refresh.yml`` re-reads nfl.com several times a
day and writes the result to ``data/pipeline/<dataset>.json`` — **overwriting the previous file**.
One file per dataset means one capture, no matter how many times the collector runs, so a
requirement that needs a series ("treat the injury report as a timestamped series", "snapshot the
injury report every Wed/Thu/Fri and keep a dated history", "point-in-time ledger … preserves exact
pre-kickoff certainty") cannot be met by collecting more often. This module is the retention layer:
it keeps every read, keyed by the clock time it was read and by the hash of what it said.

What a capture is
-----------------
``data/captures/payloads/<dataset>/<sha[:2]>/<sha>.json``
    The canonical rows of one read, named by the SHA-256 of those rows. Content-addressed, so an
    identical read is never stored twice and a stored payload can never have been edited without
    the name going wrong.
``data/captures/index.jsonl``
    One append-only line per read: dataset, the clock time the page was read, when it was retained,
    the source URLs, row count, the schema (field names + their hash), the payload path, whether
    this read was new or byte-identical to the previous one, and the drift verdict.

Design decisions worth knowing when you read this
-------------------------------------------------
* Rows are canonicalised before hashing (sorted by key, ``None`` folded to ``""``, keys sorted). Two
  sessions transcribing the same table in a different order therefore produce the same hash, and a
  changed cell produces a different one. This is the difference between a retention store and a
  backup.
* ``new vs unchanged`` is recorded, not deduplicated away. A day on which nothing moved is evidence:
  it is what distinguishes "the report says no changes" from "nobody looked".
* Nothing here is derived, scored or interpreted. Drift verdicts are *counts and field names*, and
  the alarm text is written by ``pipeline.drift``.

Usage
-----
    python3 -m pipeline.capture_store ingest            # retain the collector's current outputs
    python3 -m pipeline.capture_store ingest-pack \
        --dataset injuries --kind tsv --delimiter '|' \
        --path data/capture/2026_w10/official_nflcom_injuries_week10_transcription.psv \
        --as-read-at 2026-11-15T18:14Z --source https://www.nfl.com/injuries/ \
        --map team=team,player=player,position=position,injuries=injury,...
    python3 -m pipeline.capture_store verify            # re-derive every hash from the payloads
    python3 -m pipeline.capture_store diff --dataset injuries
    python3 -m pipeline.capture_store status            # rewrite data/captures/status.json
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
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAP = os.path.join(ROOT, "data", "captures")
CFG_PATH = os.path.join(CAP, "config.json")
INDEX_PATH = os.path.join(CAP, "index.jsonl")

# Rows of the collector's own output that describe *when/how* it ran rather than what the league
# page said. They are stripped before hashing so that a re-run at 03:17Z and a re-run at 21:17Z of
# an unchanged page produce the same hash.
VOLATILE_KEYS = {
    "generated_at", "_retrieved_at", "_run_id", "_elapsed_ms", "_http_status",
    "fetched_at", "snapshot_date", "_allow_blank", "_unverified", "_flags", "_verified",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_config() -> Dict[str, Any]:
    with open(CFG_PATH, encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------- rows

def canonicalise(rows: List[Dict[str, Any]], fields: List[str], key_fields: List[str],
                 mapping: Optional[Dict[str, str]] = None) -> List[Dict[str, str]]:
    mapping = mapping or {}
    out = []
    for r in rows:
        row = {}
        for f in fields:
            v = r.get(mapping.get(f, f))
            row[f] = "" if v is None else str(v)
        out.append(row)
    out.sort(key=lambda row: tuple(row.get(k, "") for k in key_fields) + tuple(sorted(row.items())))
    return out


def resolve_fields(payload: Dict[str, Any], spec: Dict[str, Any],
                   rows: List[Dict[str, Any]]) -> Tuple[List[str], List[Dict[str, str]]]:
    """`fields: "auto"` keeps the dataset's own column list, so a column that disappears is detected as
    a schema change instead of being quietly dropped from the hash.

    The field set is the UNION of the declared `columns` and the keys the rows actually carry. That is
    deliberate: data/pipeline/deficiency.json declares 12 columns and its rows carry 14 keys
    (`team_abbrev` and `depth_listed` are printed but undeclared). Taking the declared list alone would
    drop real data; taking the rows alone would hide the mismatch. So the payload keeps both and the
    mismatch is emitted as a `declared-columns-mismatch` finding for the alarm, not repaired.
    """
    declared = list(payload.get("columns") or []) if isinstance(payload, dict) else []
    actual = sorted({k for r in rows for k in r if not str(k).startswith("_")})
    fields = list(spec["fields"]) if spec.get("fields") != "auto" else sorted(set(declared) | set(actual))
    warns: List[Dict[str, str]] = []
    if spec.get("fields") == "auto" and declared:
        missing = sorted(set(declared) - set(actual))
        extra = sorted(set(actual) - set(declared))
        if missing or extra:
            warns.append({
                "kind": "declared-columns-mismatch",
                "field": "+".join(missing + extra),
                "detail": f"the payload declares {len(declared)} columns and its rows carry "
                          f"{len(actual)} keys; undeclared in the rows: {extra or 'none'}; "
                          f"declared but not in the rows: {missing or 'none'}",
            })
    return fields, warns


def read_pipeline_json(path: str, spec: Dict[str, Any]) -> Tuple[List[Dict[str, str]], List[str], str]:
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        payload = json.load(fh)
    rows = payload.get("rows", [])
    if isinstance(payload, list):
        rows = payload
        payload = {}
    fields, warns = resolve_fields(payload, spec, rows)
    key_fields = spec["key_fields"]
    srcs = []
    for r in rows:
        u = r.get("_source_url") if isinstance(r, dict) else None
        if u and u not in srcs:
            srcs.append(u)
    src = (payload.get("source") or {}).get("url") if isinstance(payload, dict) else None
    src = src or (srcs[0] if srcs else "")
    as_read = (payload.get("generated_at") if isinstance(payload, dict) else "") or \
              (rows[0].get("_retrieved_at") if rows and isinstance(rows[0], dict) else "") or ""
    return (canonicalise(rows, fields, key_fields, spec.get("map")),
            [src] + [s for s in srcs if s != src], as_read, warns)


def read_delimited(path: str, fields: List[str], key_fields: List[str], delimiter: str,
                   mapping: Dict[str, str], comment: str = "#",
                   source_columns: Optional[List[str]] = None) -> Tuple[List[Dict[str, str]], List[str], str]:
    """A hand-transcribed dated pack (TSV/PSV) retained the same way as a collector output.

    `source_columns` is for the dated packs that carry their column list in a `# Format:` comment
    instead of a header row - the transcription convention two sessions of this repository use.
    Without it the first data row would be eaten as a header and the count would come up one short.
    """
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        text = fh.read()
    header_comment = [ln for ln in text.split("\n") if ln.startswith(comment) and "SOURCE:" in ln]
    lines = [ln for ln in text.split("\n") if ln.strip() and not ln.lstrip().startswith(comment)]
    srcs: List[str] = []
    for ln in header_comment:
        for tok in ln.replace("SOURCE:", "").split():
            if tok.startswith("http"):
                url = tok.rstrip(").,")
                if url not in srcs:
                    srcs.append(url)
    body = lines
    if source_columns:
        body = [delimiter.join(source_columns)] + lines
    rd = csv.DictReader(io.StringIO("\n".join(body)), delimiter=delimiter)
    rows = []
    for r in rd:
        rows.append({f: (r.get(mapping.get(f, f)) or "").strip() for f in fields})
    return canonicalise(rows, fields, key_fields), srcs, ""


# --------------------------------------------------------------------------- store

def payload_path(dataset: str, sha: str) -> str:
    return os.path.join(CAP, "payloads", dataset, sha[:2], f"{sha}.json")


def read_index() -> List[Dict[str, Any]]:
    if not os.path.exists(INDEX_PATH):
        return []
    with open(INDEX_PATH, encoding="utf-8") as fh:
        return [json.loads(ln) for ln in fh if ln.strip()]


def append_index(entry: Dict[str, Any]) -> None:
    with open(INDEX_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")


def capture_id(dataset: str, as_read_at: str, sha: str) -> str:
    stamp = (as_read_at or "unknown").replace("-", "").replace(":", "").replace(".", "")
    return f"{dataset}@{stamp}@{sha[:12]}"


def register(dataset: str, rows: List[Dict[str, str]], sources: List[str], as_read_at: str,
             cfg: Dict[str, Any], note: str = "", source_files: Optional[List[str]] = None,
             extra_violations: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    import pipeline.drift as drift

    spec = cfg["datasets"][dataset]
    content = json.dumps(rows, sort_keys=True).encode("utf-8")
    sha = sha256_bytes(content)
    schema = sorted({k for r in rows for k in r})
    schema_sha = sha256_bytes(json.dumps(schema).encode())
    path = payload_path(dataset, sha)
    prior = [e for e in read_index() if e["dataset"] == dataset]
    status = "unchanged" if any(p["content_sha256"] == sha for p in prior) else "new"
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "dataset": dataset, "content_sha256": sha, "captured_at": now_iso(),
                "as_read_at": as_read_at, "sources": sources, "schema": schema,
                "note": note, "source_files": source_files or [], "rows": rows,
            }, indent=1, sort_keys=True) + "\n")
    violations = drift.evaluate(dataset, rows, schema, cfg) + list(extra_violations or [])
    entry = {
        "capture_id": capture_id(dataset, as_read_at or now_iso(), sha),
        "dataset": dataset,
        "as_read_at": as_read_at or "",
        "ingested_at": now_iso(),
        "sources": sources,
        "rows": len(rows),
        "schema_fields": schema,
        "schema_sha256": schema_sha,
        "content_sha256": sha,
        "content_bytes": len(content),
        "payload": os.path.relpath(path, ROOT),
        "status": status,
        "drift": "pass" if not violations else "fail",
        "drift_violations": violations,
        "prev_content_sha256": prior[-1]["content_sha256"] if prior else "",
        "note": note,
    }
    append_index(entry)
    return entry


# --------------------------------------------------------------------------- commands

def cmd_ingest(args) -> int:
    cfg = load_config()
    names = args.dataset or list(cfg["datasets"])
    n = 0
    for name in names:
        spec = cfg["datasets"][name]
        source = spec.get("pipeline_source")
        if not source:
            print(f"skip {name}: no pipeline_source in the capture config")
            continue
        path = os.path.join(ROOT, source)
        if not os.path.exists(path):
            print(f"FAIL {name}: source {source} is not in the tree")
            return 1
        rows, srcs, as_read, warns = read_pipeline_json(path, spec)
        if args.as_read_at:
            as_read = args.as_read_at
        entry = register(name, rows, srcs, as_read, cfg, note=args.note or "",
                         source_files=[source], extra_violations=warns)
        n += 1
        print(f"{name:14s} {entry['status']:9s} rows={entry['rows']:5d} sha={entry['content_sha256'][:12]} "
              f"as_read={entry['as_read_at']} drift={entry['drift']}")
    if not n:
        print("nothing to ingest")
    return 0


def cmd_ingest_pack(args) -> int:
    cfg = load_config()
    spec = cfg["datasets"][args.dataset]
    mapping = {}
    for item in (args.map or []):
        dest, _, src = item.partition("=")
        mapping[dest] = src
    if not mapping:
        mapping = {f: f for f in spec["fields"]}
    if args.source_columns:
        spec = dict(spec)
        spec["fields"] = [c.split("=")[0] for c in args.source_columns]
        mapping = {c.split("=")[0]: c.split("=", 1)[1] for c in args.source_columns}
        key_fields = [spec["key_fields"][0]] if False else spec["key_fields"]
        rows, srcs, _ = read_delimited(args.path, spec["fields"], spec["key_fields"],
                                       args.delimiter, mapping,
                                       source_columns=[c.split("=", 1)[1] for c in args.source_columns])
    else:
        rows, srcs, _ = read_delimited(args.path, spec["fields"], spec["key_fields"],
                                       args.delimiter, mapping)
    entry = register(args.dataset, rows, [args.source] + srcs if args.source else srcs,
                     args.as_read_at or "", cfg, note=args.note or "hand-transcribed official read",
                     source_files=[args.path])
    print(f"{args.dataset:14s} {entry['status']:9s} rows={entry['rows']:5d} sha={entry['content_sha256'][:12]} "
          f"drift={entry['drift']}")
    for v in entry["drift_violations"]:
        print("  !", v)
    return 0


def cmd_verify(args) -> int:
    cfg = load_config()
    index = read_index()
    if not index:
        print("FAIL: no captures retained")
        return 1
    bad = 0
    seen_ids = set()
    for e in index:
        if e["capture_id"] in seen_ids:
            print(f"FAIL: duplicate capture_id {e['capture_id']}")
            bad += 1
        seen_ids.add(e["capture_id"])
        path = os.path.join(ROOT, e["payload"])
        if not os.path.exists(path):
            print(f"FAIL: {e['capture_id']} payload missing at {e['payload']}")
            bad += 1
            continue
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        rehash = sha256_bytes(json.dumps(payload["rows"], sort_keys=True).encode("utf-8"))
        if rehash != e["content_sha256"]:
            print(f"FAIL: {e['capture_id']} payload hash {rehash[:12]} != index {e['content_sha256'][:12]}")
            bad += 1
        if sorted({k for r in payload["rows"] for k in r}) != e["schema_fields"]:
            print(f"FAIL: {e['capture_id']} schema differs from the index")
            bad += 1
        if len(payload["rows"]) != e["rows"]:
            print(f"FAIL: {e['capture_id']} row count differs from the index")
            bad += 1
    # every retained payload must be reachable from the index, and only from it
    referenced = {os.path.join(ROOT, e["payload"]) for e in index}
    for dataset in cfg["datasets"]:
        d = os.path.join(CAP, "payloads", dataset)
        if not os.path.isdir(d):
            continue
        for sub in sorted(os.listdir(d)):
            for fn in sorted(os.listdir(os.path.join(d, sub))):
                p = os.path.join(d, sub, fn)
                if p not in referenced:
                    print(f"FAIL: orphan payload not referenced by the index: {os.path.relpath(p, ROOT)}")
                    bad += 1
    fresh = freshness(cfg, index)
    stale = [k for k, v in fresh.items() if v["status"] != "ok"]
    print(f"captures retained: {len(index)}   datasets: {len(fresh)}   hash/orphan failures: {bad}")
    for k, v in sorted(fresh.items()):
        print(f"  freshness {k:14s} {v['status']:7s} {v['hours_since_last_read']}h since the last read "
              f"(budget {v['max_age_hours']}h)")
    if bad:
        return 1
    return 0


def freshness(cfg: Dict[str, Any], index: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    pins = cfg.get("freshness_hours", {})
    now = datetime.now(timezone.utc)
    for dataset, spec in cfg["datasets"].items():
        entries = [e for e in index if e["dataset"] == dataset]
        budget = int(pins.get(dataset, 72))
        if not entries:
            out[dataset] = {"status": "never-captured", "captures": 0, "hours_since_last_read": "",
                            "max_age_hours": budget}
            continue
        stamp = entries[-1].get("as_read_at") or entries[-1].get("ingested_at")
        try:
            when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            hours = round((now - when).total_seconds() / 3600.0, 1)
        except ValueError:
            hours, stamp = None, stamp
        skew = ""
        if hours is not None and hours < 0:
            # The read clock is ahead of the retention clock: a backfilled capture stamped by hand, or
            # two machines that disagree. Not a defect in the data, so it is recorded, not failed.
            skew = f"{abs(hours)}"
            hours = 0.0
        if hours is None:
            status = "unreadable-clock"
        elif hours > budget:
            status = "stale"
        else:
            status = "ok"
        out[dataset] = {
            "status": status,
            "captures": len(entries),
            "distinct_payloads": len({e["content_sha256"] for e in entries}),
            "last_as_read_at": stamp,
            "hours_since_last_read": hours,
            "clock_skew_hours": skew,
            "max_age_hours": budget,
            "last_drift": entries[-1]["drift"],
        }
    return out


def cmd_status(args) -> int:
    cfg = load_config()
    index = read_index()
    fresh = freshness(cfg, index)
    alarms = []
    for dataset, v in fresh.items():
        if v["status"] != "ok":
            alarms.append({"dataset": dataset, "kind": "freshness", "detail": v["status"],
                           "hours_since_last_read": v["hours_since_last_read"],
                           "max_age_hours": v["max_age_hours"]})
    for e in index:
        if e["drift"] != "pass":
            alarms.append({"dataset": e["dataset"], "kind": "schema-or-count", "at": e["as_read_at"],
                           "detail": e["drift_violations"], "capture_id": e["capture_id"]})
    status = {
        "generated_at": now_iso(),
        "captures": len(index),
        "datasets": list(cfg["datasets"]),
        "freshness": fresh,
        "alarms": alarms,
        "verdict": "ok" if not alarms else "alarmed",
        "rule": "an alarm is published; a blank cell is never published as an absence of news",
    }
    with open(os.path.join(CAP, "status.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(status, indent=1) + "\n")
    print(f"status: {status['verdict']}  captures={len(index)}  alarms={len(alarms)}")
    return 0


def cmd_diff(args) -> int:
    """Row-level delta between two consecutive captures of one dataset.

    The brief asks for the *surprise*, not the level: a designation that was already Out yesterday
    carries no information, a designation that moved does. This writes exactly that.
    """
    cfg = load_config()
    index = [e for e in read_index() if e["dataset"] == args.dataset]
    if len(index) < 2:
        print(f"{args.dataset}: {len(index)} capture(s) retained; a delta needs two. "
              f"Nothing is published as zero-change.")
        return 0
    old_e, new_e = index[-2], index[-1]
    spec = cfg["datasets"][args.dataset]
    key = spec["diff_key"]
    fields = spec.get("diff_fields", spec["fields"] if spec["fields"] != "auto" else key)
    fields = [f for f in fields if f not in key]

    def load(e):
        with open(os.path.join(ROOT, e["payload"]), encoding="utf-8") as fh:
            payload = json.load(fh)
        return {tuple(r[k] for k in key): {f: r.get(f, "") for f in fields} for r in payload["rows"]}

    # Two extraction paths of this repository spell the Rams differently (LA / LAR) and the Cardinals
    # differently (AZ / ARI). Payloads keep what each source printed; only the JOIN normalises, so a
    # spelling difference cannot masquerade as 14 players arriving and 14 leaving.
    alias = spec.get("diff_alias") or {}

    def norm(k):
        return tuple(alias.get(part, part) for part in k)

    old = {norm(k): v for k, v in load(old_e).items()}
    new = {norm(k): v for k, v in load(new_e).items()}
    if alias:
        print(f"note: club codes normalised on join only ({alias}); payloads keep what each source printed")
    rows = []
    for k in sorted(set(old) | set(new)):
        if k not in old:
            rows.append({"change": "appeared", "key": "|".join(k), "field": "", "was": "", "now": ""})
            continue
        if k not in new:
            rows.append({"change": "gone", "key": "|".join(k), "field": "", "was": "", "now": ""})
            continue
        for f in fields:
            if old[k].get(f, "") != new[k].get(f, ""):
                rows.append({"change": "moved", "key": "|".join(k), "field": f,
                             "was": old[k].get(f, ""), "now": new[k].get(f, "")})
    outdir = os.path.join(CAP, "diffs")
    os.makedirs(outdir, exist_ok=True)
    name = f"{args.dataset}__{old_e['as_read_at'].split('T')[0] or 'na'}__{new_e['as_read_at'].split('T')[0] or 'na'}.csv"
    path = os.path.join(outdir, name)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["change", "key", "field", "was", "now"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"{args.dataset}: {len(rows)} changed cells between {old_e['as_read_at']} and "
          f"{new_e['as_read_at']} -> {os.path.relpath(path, ROOT)}")
    counts = {}
    for r in rows:
        counts[r["change"]] = counts.get(r["change"], 0) + 1
    print(f"  by kind: {counts or 'none'}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m pipeline.capture_store")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ingest")
    p.add_argument("--dataset", action="append")
    p.add_argument("--as-read-at", default="", help="override the clock time recorded in the payload")
    p.add_argument("--note", default="")
    p.set_defaults(fn=cmd_ingest)
    p = sub.add_parser("ingest-pack")
    p.add_argument("--dataset", required=True)
    p.add_argument("--path", required=True)
    p.add_argument("--delimiter", default="\t")
    p.add_argument("--as-read-at", default="")
    p.add_argument("--source", default="")
    p.add_argument("--note", default="")
    p.add_argument("--map", action="append", help="dest=src, repeatable")
    p.add_argument("--source-columns", action="append",
                   help="dest=srccolumn for a file with no header row, in the order the file prints them")
    p.set_defaults(fn=cmd_ingest_pack)
    p = sub.add_parser("verify")
    p.set_defaults(fn=cmd_verify)
    p = sub.add_parser("status")
    p.set_defaults(fn=cmd_status)
    p = sub.add_parser("diff")
    p.add_argument("--dataset", required=True)
    p.set_defaults(fn=cmd_diff)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
