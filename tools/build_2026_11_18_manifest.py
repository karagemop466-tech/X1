#!/usr/bin/env python3
"""Write (and check) the manifest for the 2026-11-18 dated read pack.

    python3 tools/build_2026_11_18_manifest.py            # write
    python3 tools/build_2026_11_18_manifest.py --check     # fail if a read file drifted from it

The manifest is what makes the pack auditable after the fact: each retained read is a transcription
of one rendered fetch of one official URL at one clock time, and the SHA-256 is over the bytes of the
file as committed. Anyone can re-hash it; tools/verify_2026_11_18.py check A does exactly that, so a
later edit to a read file is a build failure rather than a silent rewrite of history.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACK = os.path.join(ROOT, "data", "verification", "2026_11_18")

READ_UTC = "2026-11-18T03:05Z"
METHOD = ("rendered read of the live official page through the agent's fetch tool; not raw HTTP "
          "bytes. The raw-bytes path in this repository is the CI ledger "
          "(.github/workflows/injury-ledger.yml -> data/ledger/injuries/), which keeps gzipped "
          "responses. Both are recorded as what they are.")

FILES = [
    dict(path="data/verification/2026_11_18/week11_slate_2026-11-18.tsv",
         url="https://www.nfl.com/schedules/2026/by-week/week-11",
         describes="Week 11 slate: 13 fixtures, 6 byes, kickoff slots, networks, event labels",
         chunks="0-1 of 2"),
    dict(path="data/verification/2026_11_18/week10_rows_reread_2026-11-18.tsv",
         url="https://www.nfl.com/injuries/",
         describes="Week 10 injury rows re-read four club tables deep (WAS, NYG, NE, DET)",
         chunks="0 of 8"),
    dict(path="data/verification/2026_11_18/injury_probe_2026-11-18.tsv",
         url="https://www.nfl.com/injuries/league/2026/REG11",
         describes="Week 11 report availability probe: the requested week resolves to Week 10",
         chunks="0 of 1"),
]


def main() -> int:
    entries = []
    for f in FILES:
        p = os.path.join(ROOT, f["path"])
        if not os.path.exists(p):
            print(f"FAIL: retained read missing: {f['path']}")
            return 1
        body = open(p, "rb").read()
        entries.append(dict(f, sha256=hashlib.sha256(body).hexdigest(),
                            bytes=len(body), lines=body.count(b"\n") + 1,
                            read_utc=READ_UTC, method=METHOD))
    text = json.dumps(dict(
        dataset="round6_reads",
        title="Retained official reads behind the 2026-11-18 pack",
        generated_by="tools/build_2026_11_18_manifest.py",
        rule=("A read file in this pack is immutable history. This manifest is the fingerprint; "
              "tools/verify_2026_11_18.py re-hashes every file against it on every build."),
        files=entries), indent=1) + "\n"
    out = os.path.join(PACK, "MANIFEST.json")
    if "--check" in sys.argv:
        if not os.path.exists(out) or open(out, encoding="utf-8").read() != text:
            print("STALE: data/verification/2026_11_18/MANIFEST.json - rerun "
                  "tools/build_2026_11_18_manifest.py")
            return 1
        print(f"[manifest] current: {len(entries)} retained reads")
        return 0
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"[manifest] wrote {len(entries)} read fingerprints to data/verification/2026_11_18/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
