#!/usr/bin/env python3
"""Drift alarms for retained captures (C-3 of session arena-543cdcb0-x1).

The brief's words: *"Add a drift alarm to every scraper. Pin each parser to expected row counts and
required fields; fail the build loudly when a field goes missing rather than publishing a blank."*

This is the pin side of that. ``pipeline.capture_store`` decides **what** to keep; this module decides
**whether the shape of a read is still the shape we agreed to publish**. It does not repair, pad or
default anything: a violation is a string that travels with the capture into the index, into
``data/captures/status.json`` and onto the site, where a human can read it next to the number that
caused it.

Violations, and why each one is here
------------------------------------
``missing-field``        the parser stopped producing a column. Every downstream table would otherwise
                         print a blank that reads like "no injury listed" when it means "we broke".
``row-count-out-of-range`` a page read that lost half its clubs, or gained a duplicate block, is a
                         parsing accident, not a news event.
``duplicate-key``        two rows claim to be the same entity; a join would silently pick one.
``blank-over-allowance``  a field allowed to be blank (an unprinted game status) is blank 100% of the
                         time — usually the field was scraped empty, not that everyone is healthy.
``unknown-value``        a designation outside the vocabulary the league prints; a new label has to be
                         read and pinned deliberately, never mapped to the nearest old one.
``club-code-outside-register`` a read whose club codes are not the 32 the standings page prints. The
                         Week 10 series fired this on the Rams: one extraction path writes ``LA``, the
                         other ``LAR``, so a row-level join reported 14 players gone and 14 arrived when
                         no player moved at all. Alarm-only, because the fix is a published alias table,
                         not a quiet rewrite of what a source printed.
``standings-closure``     league-wide arithmetic: wins must equal losses and points for must equal
                         points against, or a row was misread.
``slate-closure``         a game week must cover all 32 clubs exactly once, as a fixture or as a bye.
                         A partial page read fails here — this check is what caught a 2-of-3-chunk
                         read during the session that wrote this file, which is why it is a pin.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The vocabularies the official pages print. Kept as printed, including the exact capitalisation,
# because the point of the check is to notice when the printed set changes.
PRACTICE_STATUS = {
    "Full Participation in Practice", "Limited Participation in Practice",
    "Did Not Participate In Practice", "Did Not Participate in Practice", "",
}
GAME_STATUS = {"Out", "Doubtful", "Questionable", "", "Probable"}


def _v(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return cfg.get("pins", {})


def evaluate(dataset: str, rows: List[Dict[str, str]], schema: List[str],
             cfg: Dict[str, Any],
             extra: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, str]]:
    """Return the list of violations for one captured read (empty list = the read is well-shaped)."""
    out: List[Dict[str, str]] = []
    pin = _v(cfg).get(dataset, {})

    for w in list(extra or []):
        out.append(w)

    for field in pin.get("required_fields", []):
        if field not in schema:
            out.append({"kind": "missing-field", "field": field,
                        "detail": f"the read produced no `{field}` column at all"})
    n = len(rows)
    lo, hi = pin.get("min_rows"), pin.get("max_rows")
    if lo is not None and n < int(lo):
        out.append({"kind": "row-count-out-of-range", "field": "*",
                    "detail": f"{n} rows, minimum pinned {lo}"})
    if hi is not None and n > int(hi):
        out.append({"kind": "row-count-out-of-range", "field": "*",
                    "detail": f"{n} rows, maximum pinned {hi}"})
    if "exact_rows" in pin and n != int(pin["exact_rows"]):
        out.append({"kind": "row-count-out-of-range", "field": "*",
                    "detail": f"{n} rows, exactly {pin['exact_rows']} pinned"})

    key = pin.get("unique_key") or []
    if key:
        seen: Dict[tuple, int] = {}
        for r in rows:
            k = tuple(r.get(f, "") for f in key)
            seen[k] = seen.get(k, 0) + 1
        dupes = sorted(k for k, c in seen.items() if c > 1)
        for k in dupes[:10]:
            out.append({"kind": "duplicate-key", "field": "+".join(key),
                        "detail": f"{'|'.join(k)} appears {seen[k]} times"})
        if dupes:
            out.append({"kind": "duplicate-key", "field": "+".join(key),
                        "detail": f"{len(dupes)} duplicate keys in total"})

    for field, allowance in (pin.get("max_blank_fraction") or {}).items():
        if field not in schema or not rows:
            continue
        blanks = sum(1 for r in rows if not r.get(field, ""))
        frac = blanks / len(rows)
        if frac > float(allowance):
            out.append({"kind": "blank-over-allowance", "field": field,
                        "detail": f"{blanks}/{len(rows)} blank = {frac:.3f}, allowance {allowance}"})

    for field in pin.get("vocabulary", []):
        if field not in schema:
            continue
        allowed = {"practice_status": PRACTICE_STATUS, "game_status": GAME_STATUS}.get(field, set())
        unknown = sorted({r.get(field, "") for r in rows} - allowed)
        for v in unknown:
            out.append({"kind": "unknown-value", "field": field,
                        "detail": f"printed value {v!r} is outside the vocabulary the league prints"})

    checks = pin.get("invariants", [])
    if "club-vocabulary" in checks:
        allowed = set(pin.get("clubs", []))
        field = pin.get("club_field", "team")
        odd = sorted({r.get(field, "") for r in rows if r.get(field, "")} - allowed)
        for v in odd:
            out.append({"kind": "club-code-outside-register", "field": field,
                        "detail": f"{v!r} is not one of the 32 club codes the standings page prints; "
                                  f"it is a spelling of another club or a page change, and a join on it "
                                  f"would silently drop {sum(1 for r in rows if r.get(field) == v)} rows"})
    if "standings-closure" in checks:
        w = sum(int(r.get("w") or 0) for r in rows)
        l = sum(int(r.get("l") or 0) for r in rows)
        t = sum(int(r.get("t") or 0) for r in rows)
        pf = sum(int(r.get("pf") or 0) for r in rows)
        pa = sum(int(r.get("pa") or 0) for r in rows)
        if w != l:
            out.append({"kind": "standings-closure", "field": "w/l", "detail": f"{w} wins vs {l} losses"})
        if t % 2:
            out.append({"kind": "standings-closure", "field": "t", "detail": f"{t} ties is not even"})
        if pf != pa:
            out.append({"kind": "standings-closure", "field": "pf/pa", "detail": f"{pf} vs {pa}"})
    if "slate-closure" in checks:
        appearances: Dict[str, int] = {}
        for r in rows:
            if r.get("row_type", "game") == "bye":
                club = r.get("away", "")
                if club:
                    appearances[club] = appearances.get(club, 0) + 1
                continue
            for f in ("away", "home"):
                club = r.get(f, "")
                if club:
                    appearances[club] = appearances.get(club, 0) + 1
        expected = int(pin.get("clubs", 32))
        missing = expected - len(appearances)
        if missing:
            out.append({"kind": "slate-closure", "field": "clubs",
                        "detail": f"{len(appearances)} of {expected} clubs appear in this read"})
        for club, c in sorted(appearances.items()):
            if c != 1:
                out.append({"kind": "slate-closure", "field": "clubs",
                            "detail": f"{club} appears {c} times in one game week"})
    return out


def describe(cfg: Dict[str, Any]) -> str:
    lines = []
    for dataset, pin in sorted(_v(cfg).items()):
        bits = []
        if "min_rows" in pin:
            bits.append(f"rows >= {pin['min_rows']}")
        if "max_rows" in pin:
            bits.append(f"rows <= {pin['max_rows']}")
        if "exact_rows" in pin:
            bits.append(f"rows == {pin['exact_rows']}")
        if pin.get("required_fields"):
            bits.append(f"{len(pin['required_fields'])} required fields")
        if pin.get("unique_key"):
            bits.append(f"unique on {'+'.join(pin['unique_key'])}")
        if pin.get("invariants"):
            bits.append("+".join(pin["invariants"]))
        lines.append(f"  {dataset:14s} " + "; ".join(bits))
    return "pins:\n" + "\n".join(lines)


if __name__ == "__main__":  # cheap self-documenting entry point for CI logs
    with open(os.path.join(ROOT, "data", "captures", "config.json"), encoding="utf-8") as fh:
        print(describe(json.load(fh)))
