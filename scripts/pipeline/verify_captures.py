#!/usr/bin/env python3
"""CI gate over the capture store (C-3 of session arena-543cdcb0-x1).

Run by `.github/workflows/data-refresh.yml` between "collect" and "commit", and by `verify.yml` on
every push. It answers two questions and no others:

  1. Is the evidence we are about to publish internally sound?  Every retained payload must hash to
     the name it is stored under, every index line must point at a payload that exists, no payload
     may be unreferenced, and no capture may be recorded twice.
  2. Is the latest read of each dataset shaped the way the pins say it is shaped?  A gate failure
     here means the *build* is wrong, so it stops a commit. Alarms in `alarm_only` kinds are written
     to `data/captures/status.json` and published, and do not stop anything — the split is pinned in
     `data/captures/config.json` with the reason for each side.

    python3 scripts/pipeline/verify_captures.py            # gate
    python3 scripts/pipeline/verify_captures.py --self-test  # prove the gate can fail

Exit codes: 0 pass, 1 gate failure (a real defect), 2 the store is missing or unreadable.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from pipeline import capture_store as store  # noqa: E402
from pipeline import drift  # noqa: E402


def gate(check_freshness: bool = True) -> tuple[list[str], list[str]]:
    cfg = store.load_config()
    index = store.read_index()
    hard: list[str] = []
    soft: list[str] = []
    if not index:
        return ["no captures retained: the store is empty, so nothing can be verified"], soft

    seen: set[str] = set()
    for e in index:
        if e["capture_id"] in seen:
            hard.append(f"duplicate capture_id {e['capture_id']}")
        seen.add(e["capture_id"])
        path = os.path.join(ROOT, e["payload"])
        if not os.path.exists(path):
            hard.append(f"{e['capture_id']}: payload file missing at {e['payload']}")
            continue
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        rehash = store.sha256_bytes(json.dumps(payload["rows"], sort_keys=True).encode("utf-8"))
        if rehash != e["content_sha256"]:
            hard.append(f"{e['capture_id']}: payload bytes hash {rehash[:12]} != index {e['content_sha256'][:12]}")
        if len(payload["rows"]) != e["rows"]:
            hard.append(f"{e['capture_id']}: row count {len(payload['rows'])} != index {e['rows']}")

    referenced = {os.path.join(ROOT, e["payload"]) for e in index}
    for dataset in cfg["datasets"]:
        d = os.path.join(store.CAP, "payloads", dataset)
        if not os.path.isdir(d):
            continue
        for sub in sorted(os.listdir(d)):
            for fn in sorted(os.listdir(os.path.join(d, sub))):
                if os.path.join(d, sub, fn) not in referenced:
                    hard.append(f"orphan payload not referenced by the index: {dataset}/{sub}/{fn}")

    fail_kinds = set(cfg.get("gate_policy", {}).get("fail_the_build", []))
    alarm_kinds = set(cfg.get("gate_policy", {}).get("alarm_only", []))
    for dataset in cfg["datasets"]:
        latest = [e for e in index if e["dataset"] == dataset][-1:]
        for e in latest:
            for v in e.get("drift_violations", []):
                line = f"{dataset}: [{v['kind']}] {v['detail']}"
                if v["kind"] in fail_kinds:
                    hard.append(line)
                elif v["kind"] in alarm_kinds or not fail_kinds:
                    soft.append(line)
                else:
                    soft.append(line)

    if check_freshness:
        fresh = store.freshness(cfg, index)
        for dataset, v in sorted(fresh.items()):
            if v["status"] == "never-captured":
                hard.append(f"{dataset}: never captured - the collector has produced no read for this dataset")
            elif v["status"] == "stale":
                hard.append(f"{dataset}: last read {v['hours_since_last_read']}h ago, budget {v['max_age_hours']}h "
                            f"- the collector is not landing, or the source stopped answering")
    else:
        print("note: freshness not gated here (a PR build cannot fix a missed collector run); "
              "data-refresh.yml gates it after it collects")
    return hard, soft


def self_test() -> int:
    """Prove the pins can fail. An alarm nobody has seen fire is a decoration.

    Three deliberate corruptions of a real captured read, each expected to produce one violation kind.
    """
    cfg = store.load_config()
    rows, srcs, as_read, warns = store.read_pipeline_json("data/pipeline/standings.json",
                                                           cfg["datasets"]["standings"])
    cases = 0
    ok = 0

    def expect(label, want, mutations):
        nonlocal cases, ok
        cases += 1
        kinds = {v["kind"] for v in mutations}
        if want in kinds:
            ok += 1
            print(f"  ok   {label:34s} -> {want}")
        else:
            print(f"  FAIL {label:34s} -> {sorted(kinds) or 'nothing'} (expected {want})")

    expect("drop a required column", "missing-field",
           drift.evaluate("standings", [{k: v for k, v in r.items() if k != "pf"} for r in rows],
                          [f for f in rows[0] if f != "pf"], cfg))
    expect("truncate to 31 clubs", "row-count-out-of-range",
           drift.evaluate("standings", rows[:31], sorted(rows[0]), cfg))
    dup = rows + [dict(rows[0])]
    expect("duplicate a club", "duplicate-key", drift.evaluate("standings", dup, sorted(rows[0]), cfg))
    bent = [dict(r) for r in rows]
    bent[0]["w"] = str(int(bent[0]["w"]) + 1)
    expect("one extra win in the league", "standings-closure",
           drift.evaluate("standings", bent, sorted(rows[0]), cfg))
    sched_rows = [{"row_type": "game", "game_id": f"g{i}", "away": c, "home": h, "status": "Scheduled",
                   "game_url": "u", "date_et": "2026-11-22", "time_et": "1:00 PM", "network": "CBS",
                   "away_record": "0-0", "home_record": "0-0", "note": "", "source_url": "u"}
                  for i, (c, h) in enumerate(zip([r["abbr"] for r in rows[:30:2]],
                                                 [r["abbr"] for r in rows[1:31:2]]))]
    expect("a slate that omits two clubs", "slate-closure",
           drift.evaluate("week_schedule", sched_rows, sorted(sched_rows[0]), cfg))
    print(f"self-test: {ok}/{cases} corruption cases caught by the pins")
    return 0 if ok == cases else 1


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--self-test" in argv:
        return self_test()
    try:
        hard, soft = gate(check_freshness="--no-freshness" not in argv)
    except FileNotFoundError as exc:
        print(f"cannot read the capture store: {exc}")
        return 2
    class _A:
        pass
    store.cmd_status(_A())  # rewrite data/captures/status.json so the site publishes what the gate saw
    print(f"capture gate: {len(hard)} build-failing problem(s), {len(soft)} published alarm(s)")
    for h in hard:
        print("  FAIL", h)
    for s in soft:
        print("  alarm", s)
    idx = store.read_index()
    print(f"  {len(idx)} captures retained; "
          f"{len({e['content_sha256'] for e in idx})} distinct payloads")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
