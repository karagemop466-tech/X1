#!/usr/bin/env python3
"""Vendor the pinned upstream archive into `data/lab/upstream/` and record its hash.

Run:  python3 tools/lab/fetch_upstream.py [--archive /path/to/nfldata-master.tar.gz]

Why the archive and not the raw files: `raw.githubusercontent.com` is not reachable from
this session's sandbox, and `release-assets.githubusercontent.com` (where every nflverse
release asset lives) is blocked too.  `codeload.github.com` **is** reachable, so the
repository archive is the one upstream this session can actually read.  That is a
limitation of the sandbox, not of the data, and it is published on the sources page.

The extracted files are vendored so that `build_prices.py` / `build_results.py` never
touch the network: a rebuild is byte-for-byte reproducible from the repository alone.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UP = os.path.join(ROOT, "data", "lab", "upstream")
ARCHIVE_URL = "https://codeload.github.com/nflverse/nfldata/tar.gz/refs/heads/master"
# Only the files the lab publishes from. Everything else in the archive is ignored, so the
# vendored footprint is 3.4 MB rather than the archive's 9.5 MB.
WANTED = ["games.csv", "initial_lines.csv", "closing_lines.csv", "sc_lines.csv"]


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv: list[str]) -> int:
    os.makedirs(UP, exist_ok=True)
    tmpdir = tempfile.mkdtemp(prefix="x1-lab-")
    archive = None
    if "--archive" in argv:
        archive = os.path.abspath(argv[argv.index("--archive") + 1])
    else:
        archive = os.path.join(tmpdir, "nfldata-master.tar.gz")
        print(f"fetching {ARCHIVE_URL}")
        r = subprocess.run(
            ["curl", "-sSL", "--max-time", "180", ARCHIVE_URL, "-o", archive],
            capture_output=True, text=True,
        )
        if r.returncode != 0 or not os.path.exists(archive) or os.path.getsize(archive) == 0:
            print(f"FETCH FAILED rc={r.returncode} stderr={r.stderr[:400]}", file=sys.stderr)
            return 1
    size = os.path.getsize(archive)
    digest = sha256(archive)
    print(f"archive {size:,} bytes sha256={digest}")

    with tarfile.open(archive, "r:gz") as tf:
        members = {os.path.basename(m.name): m for m in tf.getmembers()
                   if m.isfile() and os.path.dirname(m.name).endswith("/data")}
        missing = [w for w in WANTED if w not in members]
        if missing:
            print(f"archive is missing {missing}", file=sys.stderr)
            return 1
        for name in WANTED:
            src = tf.extractfile(members[name])
            assert src is not None
            with open(os.path.join(UP, name), "wb") as out:
                shutil.copyfileobj(src, out)

    files = {}
    for name in WANTED:
        path = os.path.join(UP, name)
        files[name] = {"sha256": sha256(path), "bytes": os.path.getsize(path)}
        print(f"  {name:22s} {files[name]['bytes']:>9,} bytes  {files[name]['sha256']}")

    pin = {
        "archive_url": ARCHIVE_URL,
        "archive_sha256": digest,
        "archive_bytes": size,
        "repo": "https://github.com/nflverse/nfldata",
        "branch": "master",
        "publisher": "nflverse (Lee Sharpe) - repository `nfldata`",
        "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": files,
        "why_this_upstream": (
            "raw.githubusercontent.com and release-assets.githubusercontent.com are not "
            "reachable from the sandbox that built this artefact; codeload.github.com is. "
            "The repository archive is therefore the only nflverse source that could be "
            "read directly."
        ),
        "limitations": [
            "nflverse release assets (player_stats, injuries, depth_charts, pbp, snap_counts) "
            "are hosted on release-assets.githubusercontent.com, which this sandbox cannot reach.",
            "www.nfl.com is not reachable from this sandbox, so no league page could be "
            "re-fetched while building this artefact.",
            "The archive is a branch snapshot: `master` moves. The SHA-256 above pins the "
            "exact bytes, and every artefact records the per-file hashes.",
        ],
    }
    out = os.path.join(UP, "_pin.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(pin, fh, indent=1)
        fh.write("\n")
    print(f"wrote {os.path.relpath(out, ROOT)}")
    shutil.rmtree(tmpdir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
