#!/usr/bin/env python3
"""Gate for the decision-center section.

Fails if a row is unsourced, an owner decision has been filled in by a session,
a source board disappears, a flag blocks release, or a generated page is stale.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "suggestions"
OUT = ROOT / "suggestions"
ALLOWED = {"nfl.com", "www.nfl.com", "media.nfl.com", "static.www.nfl.com", "github.com"}
STATUSES = {"BLOCKED", "PARTIAL", "ANSWERED", "DEFINED", "OWNER DECISION", "NEEDS REVIEW"}
errors, checks = [], []


def check(cond, msg):
    (checks if cond else errors).append(msg)


def valid_url(url: str) -> bool:
    p = urlparse(url)
    return p.scheme == "https" and (p.hostname in ALLOWED or (p.hostname or "").endswith(".nfl.com"))


def main() -> int:
    reg = json.loads((DATA / "decision_center.json").read_text(encoding="utf-8"))
    reads = json.loads((DATA / "official_reads.json").read_text(encoding="utf-8"))
    check(reg["meta"]["generated_at"] == "2026-11-19", "register carries the 2026-11-19 build date")
    check("does not implement" in reg["meta"]["rule"], "register states the no-implementation rule")

    for row in reg["questions"]:
        rid = row["id"]
        for field in ("area", "question", "information_held", "information_missing", "answer",
                      "status", "how_to_discover", "blocks", "source_url", "source_note"):
            check(bool(row.get(field)), f"{rid}: {field} is populated")
        check(row["status"] in STATUSES, f"{rid}: status is one of the published states")
        check(valid_url(row["source_url"]), f"{rid}: official or repository source link is https")

    for row in reg["suggestions"]:
        rid = row["id"]
        for field in ("area", "title", "problem", "path_a", "path_b", "path_c", "recommended",
                      "why", "impact", "effort", "risk", "unlocks", "source_url"):
            check(bool(row.get(field)), f"{rid}: {field} is populated")
        check(row["status"] == "proposed — awaiting owner decision", f"{rid}: remains proposed")
        check(row["decision"] == "" and row["owner"] == "", f"{rid}: decision and owner cells are blank")
        check(valid_url(row["source_url"]), f"{rid}: source link is https")

    for row in reg["missing_information"]:
        rid = row["id"]
        for field in ("missing_information", "why_it_is_missing", "official_source_candidate",
                      "how_to_collect", "clears", "current_state", "source_url"):
            check(bool(row.get(field)), f"{rid}: {field} is populated")
        check(valid_url(row["source_url"]), f"{rid}: source link is https")

    ids = [r["id"] for r in reg["questions"] + reg["suggestions"] + reg["missing_information"]]
    check(len(ids) == len(set(ids)), "row IDs are unique across all three registers")

    for b in reg["source_boards"]:
        path = ROOT / b["path"]
        check(path.exists(), f"{b['id']}: source board {b['path']} exists")
        check(valid_url(b["url"]), f"{b['id']}: source board link is https")

    for f in reg["flags"]:
        check(not f["blocks_release"], f"{f['id']}: flag does not block release")
        check(all(f.get(k) for k in ("item", "verified", "unknown", "settles_it", "source_url")),
              f"{f['id']}: flag states what is verified, unknown and settling")
        check(valid_url(f["source_url"]), f"{f['id']}: flag source link is https")

    check(len(reads["reads"]) == 5, "five official pages were re-read")
    check(len({r["url"] for r in reads["reads"]}) == 5, "official read URLs are unique")
    check(reads["meta"]["read_at"] == "2026-11-19", "official reads carry the 2026-11-19 date")
    for r in reads["reads"]:
        check(valid_url(r["url"]), f"{r['id']}: official read URL is https")
        check(bool(r["observed"]) and bool(r["irregularity"]),
              f"{r['id']}: observation and limitation are both recorded")

    names = {p.name for p in OUT.glob("*.html")}
    check({"index.html", "questions.html", "paths.html", "missing.html", "review.html"} <= names,
          "all five section pages exist")
    for name in ("index.html", "questions.html", "paths.html", "missing.html", "review.html"):
        text = (OUT / name).read_text(encoding="utf-8")
        check('href="../assets/site.css"' in text, f"{name}: links the audited stylesheet")
        check("2026-11-14" in text, f"{name}: carries the snapshot date")
        check('href="../pages/flagged.html"' in text, f"{name}: links Flagged for review")
        check('href="../index.html"' in text, f"{name}: links the landing page")
        check('data-table' in text, f"{name}: carries at least one data table")
        # source cells never contain an empty or local-only link
        for cell in re.findall(r'<td>(<a class="src-link"[^>]+>.*?</a>)</td>', text):
            check("https://" in cell, f"{name}: source cell carries an https link")

    if errors:
        print(f"Decision center verification FAILED ({len(errors)}):")
        for e in errors[:40]:
            print(" -", e)
        if len(errors) > 40:
            print(f" ... and {len(errors)-40} more")
        return 1
    print(f"Decision center verification passed: {len(checks)} assertions, "
          f"{len(reg['questions'])} questions, {len(reg['suggestions'])} paths, "
          f"{len(reg['missing_information'])} missing-input rows, {len(reg['flags'])} non-blocking flags.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
