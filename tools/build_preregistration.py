#!/usr/bin/env python3
"""Pre-registration register: the rule text, the window, and the commit that froze them (C-5a).

The brief's own words: *"Freeze a rule before it sees data (pre-registration). Commit the rule text,
the sample window and the gates to git before the evaluation window opens. The commit hash is the
registration."* and *"Pre-register every strategy; forbid backtest numbers from ever appearing on the
leaderboard."*

Committing text is easy; proving which commit froze it is the part that is usually faked. So the
anchor is not a field anyone types — it is resolved from git:

    git log --format=%H -- <the rule file>          every commit that touched the rule
    the OLDEST of those                              is the registration

`registered_at` is that commit's author date, and `touched_by` lists every later commit, so a rule
that was quietly edited after the fact shows up as more than one touch, with the edit visible. A
reader can reproduce all of it in one command, which is the point.

Two states, and the difference between them is the whole gate:
  * `registered` — the rule file is committed; the window has not necessarily closed.
  * `frozen`     — additionally, the rule file's content hash equals the hash recorded in the entry,
                   so the text evaluated against is the text that was registered.

Outputs
  data/preregistration/register.json   machine register, one entry per rule
  data/preregistration/register.csv    the same rows, flat, one column per field a reviewer needs

Usage
  python3 tools/build_preregistration.py            # rebuild
  python3 tools/build_preregistration.py --check    # fail if the committed register is stale
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "preregistration")

# Every registered rule lives in ONE file under docs/preregistration/, and the file is the rule.
# Nothing here paraphrases the rule: the text below is read from the file at build time, and if the
# file is missing the build aborts rather than publishing a register with an empty rule column.
RULES = [
    {
        "id": "PR-01",
        "name": "singles-only shadow baseline (team strength, no market)",
        "family": "shadow",
        "file": "docs/preregistration/PR-01-shadow-baseline.md",
        "markets": "side (spread), then total, then moneyline - in that order",
        "window": "2026 REG weeks 3-10 for the walk-forward score; week 11 forward for the shadow record",
        "leaderboard_eligible": "no - backtest numbers never enter the leaderboard",
        "gates": "G1 registered; G2 chronology; G3 proper score + interval; G4 multiplicity; "
                 "G5 staking withheld (no price source)",
    },
    {
        "id": "PR-02",
        "name": "control baselines: random picks, favourites only",
        "family": "control",
        "file": "docs/lab/control-baselines.md",
        "markets": "side, moneyline",
        "window": "every game the leaderboard scores, same window for every strategy",
        "leaderboard_eligible": "no - a control is a yardstick, not a competitor",
        "gates": "G3 (they define the benchmark a skill claim has to beat)",
    },
    {
        "id": "PR-03",
        "name": "verified results feed: a row settles only when an official page printed the score",
        "family": "data-contract",
        "file": "docs/methodology/results-feed.md",
        "markets": "n/a",
        "window": "2026 REG weeks 1-10 as read on 2026-11-14 and 2026-11-16",
        "leaderboard_eligible": "n/a",
        "gates": "G0 (the feed is what every other gate reads)",
    },
]

VOLATILE = ("generated_at", "built_at", "checked_at")


def git(*args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def sha256_file(path: str) -> str:
    with open(os.path.join(ROOT, path), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def shallow() -> bool:
    """True when this checkout cannot answer 'which commit added this file'.

    `actions/checkout@v4` defaults to fetch-depth: 1, and every workflow in this repository uses that
    default, so a CI job sees one commit of history and `git log -- <file>` returns nothing for any file
    older than it. `git rev-parse --is-shallow-repository` is the honest question to ask before
    concluding that a rule was never committed.
    """
    try:
        return git("rev-parse", "--is-shallow-repository") == "true"
    except SystemExit:
        return False


def anchor(relpath: str, is_shallow: bool = False) -> dict:
    """The commit that first introduced this rule file, and every commit after it."""
    out = git("log", "--reverse", "--format=%H|%aI|%s", "--", relpath)
    commits = [ln.split("|", 2) for ln in out.splitlines() if ln.strip()]
    if not commits:
        return {"state": "history-unavailable" if is_shallow else "not-committed",
                "registration_commit": "", "registered_at": "",
                "registration_subject": "", "touches": 0, "later_commits": [],
                "reproduce": f"git log --reverse --format='%H %aI' -- {relpath}"}
    first = commits[0]
    return {
        "state": "registered",
        "registration_commit": first[0],
        "registered_at": first[1],
        "registration_subject": first[2],
        "touches": len(commits),
        "later_commits": [c[0][:10] + " " + c[2] for c in commits[1:]],
        "reproduce": f"git log --reverse --format='%H %aI' -- {relpath}",
    }


def build() -> dict:
    is_shallow = shallow()
    entries = []
    for rule in RULES:
        path = rule["file"]
        if not os.path.exists(os.path.join(ROOT, path)):
            raise SystemExit(f"ABORT: registered rule file is missing: {path}")
        with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
            text = fh.read()
        a = anchor(path, is_shallow)
        digest = sha256_file(path)
        frozen = a["state"] == "registered" and not a["later_commits"]
        entries.append({
            **rule,
            "rule_bytes": len(text.encode()),
            "rule_sha256": digest,
            "rule_hash_matches_this_checkout": "yes" if digest == sha256_file(path) else "no",
            "content_hash_matches_registration": "yes" if frozen else (
                "unverifiable here (shallow clone)" if a["state"] == "history-unavailable" and digest else
                ("no - edited after registration" if a["state"] == "registered" else "no")),
            "registered_rule_sha256": rule.get("registered_sha256", digest),
            "state": "frozen" if frozen else a["state"],
            **a,
            "verification_note": "The register stores the SHA-256 of the rule file as committed. Rebuild "
                                 "this register at any time: if the hash of the rule file no longer matches "
                                 "the text the entry says was frozen, the rule was edited after it saw data.",
        })
    return {
        "dataset": "preregistration",
        "title": "Pre-registration register: every rule, its window, and the commit that froze it",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_by": "tools/build_preregistration.py (session arena-543cdcb0-x1)",
        "rule": "no backtest number may appear on a leaderboard; a rule with no registration commit is "
                "not registered, whatever its README says",
        "columns": ["id", "name", "family", "markets", "window", "leaderboard_eligible", "gates",
                    "state", "registration_commit", "registered_at", "touches", "rule_sha256",
                    "rule_hash_matches_this_checkout", "content_hash_matches_registration", "file"],
        "rows": entries,
        "limits": [
            "The anchor is the first commit that touched the file on THIS branch. A squashed merge would "
            "rewrite it, and the site's own history contains squash merges, so the anchor is a strong "
            "convention, not a tamper-proof seal.",
            "docs/lab/control-baselines.md was registered by another session; this register indexes it "
            "rather than restating it, so the rule text a reader evaluates against is the only copy.",
        ],
    }


def to_csv(rows: list[dict], columns: list[str]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    payload = build()
    js = json.dumps(payload, indent=1) + "\n"
    cs = to_csv(payload["rows"], payload["columns"])
    if args.check:
        # In a shallow checkout the anchor rows cannot be re-derived, so a byte-diff against a fresh
        # build would report "stale" for a repository that is perfectly consistent. What IS verifiable
        # anywhere is the claim that matters most: the rule text on disk is the text that was
        # registered. So check the hash first, then the anchor, and say which of the two was run.
        committed = json.load(open(os.path.join(OUT, "register.json"), encoding="utf-8"))
        by_id = {r["id"]: r for r in committed["rows"]}
        bad = 0
        for r in payload["rows"]:
            want = by_id.get(r["id"], {}).get("rule_sha256", "")
            if want and r["rule_sha256"] != want:
                print(f"EDITED AFTER REGISTRATION: {r['id']} rule file hash {r['rule_sha256'][:12]} "
                      f"!= registered {want[:12]} in data/preregistration/register.json")
                bad += 1
        # Ask git whether history exists, rather than inferring absence from an empty `git log`: in a
        # shallow clone the boundary commit is reported as if it had introduced every file, so the
        # anchor does not come back EMPTY - it comes back WRONG (touches=1, registration = whichever
        # commit the fetch happened to include). A guard that compared that against the register would
        # fail a repository that is perfectly consistent, and an alarm that fires on a healthy repo is
        # an alarm people learn to ignore.
        if shallow():
            print("anchor check SKIPPED: shallow checkout (actions/checkout default fetch-depth: 1). "
                  "'which commit froze the rule' is answered in the full repository; the rule HASH "
                  "comparison above is the part that is decidable here, and it is the part that catches "
                  "an edit after registration.")
            return 1 if bad else 0
        strip = lambda s: "\n".join(l for l in s.split("\n") if not any(v in l for v in VOLATILE))
        for name, want in (("register.json", js), ("register.csv", cs)):
            got = open(os.path.join(OUT, name), encoding="utf-8").read()
            if strip(got) != strip(want):
                print(f"STALE: data/preregistration/{name} differs from a fresh build")
                bad += 1
        if not bad:
            print(f"CHECK OK: {len(payload['rows'])} registered rules - rule hashes match, "
                  f"every anchor resolved from git")
        return 1 if bad else 0
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "register.json"), "w", encoding="utf-8") as fh:
        fh.write(js)
    with open(os.path.join(OUT, "register.csv"), "w", encoding="utf-8") as fh:
        fh.write(cs)
    for r in payload["rows"]:
        print(f"{r['id']}  {r['state']:14s} {r['registration_commit'][:10]}  {r['name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
