"""Aggregate reviewed private NFL evidence. Never equate active with played.

This is a descriptive label-reliability evaluator, not a feature or a betting model.
The caller is responsible for complete, manually reviewed official evidence.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

LABELS = ("Questionable", "Doubtful", "Out")
CLEARANCE = "Cleared"
OUTCOMES = ("played", "active_dnp", "inactive")


def official(url: str) -> None:
    """Require an HTTPS URL on an NFL domain; this does not authenticate its contents."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("expected a specific official NFL evidence URL")
    try:
        parsed = urlsplit(url.strip())
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid evidence URL") from exc

    if (
        parsed.scheme.lower() != "https"
        or not (host == "nfl.com" or host.endswith(".nfl.com"))
        or parsed.path in ("", "/")
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
    ):
        raise ValueError("expected a specific HTTPS URL on an official NFL host")


def clock(text: str) -> datetime:
    """Parse an offset-aware ISO-8601 timestamp and normalize it to UTC."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("timestamp is required")
    try:
        value = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp must be valid ISO-8601") from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp needs a UTC offset")
    return value.astimezone(timezone.utc)


def interval(k: int, n: int) -> list[float] | None:
    """Two-sided 95% Wilson interval for a descriptive binomial proportion."""
    if n <= 0:
        return None
    if k < 0 or k > n:
        raise ValueError("success count must be between zero and n")
    p, z = k / n, 1.959963984540054
    center = p + z * z / (2 * n)
    radius = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    scale = 1 + z * z / n
    return [max(0.0, (center - radius) / scale), min(1.0, (center + radius) / scale)]


def identity(row: dict[str, str]) -> tuple[str, str, str, str]:
    """Return the stable season/game/team/player key, rejecting missing identifiers."""
    try:
        values = tuple(str(row[field] if row[field] is not None else "").strip()
                       for field in ("season", "game_id", "team_id", "player_id"))
    except (KeyError, TypeError) as exc:
        raise ValueError("evidence row is missing an identity field") from exc
    if not all(values):
        raise ValueError("incomplete evidence key")
    return values  # type: ignore[return-value]


def _field(row: dict[str, str], name: str) -> str:
    try:
        value = row[name]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"evidence row is missing {name}") from exc
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    return value.strip()


def _sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_manifest(manifest: dict, reports_path: str | Path, outcomes_path: str | Path,
                    reports: list[dict[str, str]], outcomes: list[dict[str, str]]) -> None:
    """Fail closed unless a reviewer attests to complete, source-checked input files.

    The manifest binds the attestation to exact input hashes and row counts. It cannot
    authenticate NFL pages or prove that the reviewer's completeness claim is true.
    """
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be a JSON object")
    if manifest.get("complete_official_evidence") is not True:
        raise ValueError("manifest must attest complete official evidence")
    if manifest.get("official_sources_reviewed") is not True:
        raise ValueError("manifest must attest manual review of official sources")
    if not str(manifest.get("reviewed_by", "")).strip():
        raise ValueError("manifest reviewer is required")
    clock(manifest.get("reviewed_at", ""))

    seasons = manifest.get("seasons")
    if not isinstance(seasons, list) or not seasons or not all(str(s).strip() for s in seasons):
        raise ValueError("manifest must list the covered seasons")
    season_ids = set(map(str, seasons))
    if len(season_ids) != len(seasons):
        raise ValueError("manifest seasons must be unique")
    coverage = manifest.get("team_ids_by_season")
    if not isinstance(coverage, dict) or set(map(str, coverage)) != season_ids:
        raise ValueError("manifest must give 32-team coverage for every listed season")
    teams_by_season = {}
    for season, teams in coverage.items():
        if not isinstance(teams, list) or len(teams) != 32 or not all(str(t).strip() for t in teams):
            raise ValueError(f"manifest season {season} must attest 32 distinct team IDs")
        team_ids = set(map(str, teams))
        if len(team_ids) != 32:
            raise ValueError(f"manifest season {season} must attest 32 distinct team IDs")
        teams_by_season[str(season)] = team_ids

    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("manifest files section is required")
    for name, path, rows in (("reports", reports_path, reports), ("outcomes", outcomes_path, outcomes)):
        item = files.get(name)
        if not isinstance(item, dict):
            raise ValueError(f"manifest {name} file record is required")
        expected_hash = item.get("sha256", "")
        if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash):
            raise ValueError(f"manifest {name} SHA-256 must be 64 hexadecimal characters")
        if _sha256(path).lower() != expected_hash.lower():
            raise ValueError(f"manifest {name} hash does not match the input file")
        if isinstance(item.get("rows"), bool) or item.get("rows") != len(rows):
            raise ValueError(f"manifest {name} row count does not match the input file")
        for row in rows:
            key = identity(row)
            if key[0] not in season_ids or key[2] not in teams_by_season[key[0]]:
                raise ValueError(f"{name} row falls outside the manifest season/team coverage")
            official(_field(row, "source"))


def evaluate(reports, outcomes) -> list[dict[str, object]]:
    """Summarize latest pre-kickoff designations against reviewed game-book status.

    This pure function is suitable for synthetic tests. The command-line interface also
    requires a hash-bound reviewer manifest attesting complete 32-team, official-source
    coverage before it will emit empirical rates. Missing outcomes are unmatched, not non-plays.
    """
    latest: dict[tuple[str, str, str, str], tuple[datetime, str]] = {}
    observed: dict[tuple[str, str, str, str], str] = {}
    seen_captures: set[tuple[tuple[str, str, str, str], datetime]] = set()
    kickoffs: dict[tuple[str, str, str, str], datetime] = {}

    for row in reports:
        key = identity(row)
        official(_field(row, "source"))
        captured_at = clock(_field(row, "captured_at"))
        kickoff = clock(_field(row, "kickoff"))
        if key in kickoffs and kickoffs[key] != kickoff:
            raise ValueError("conflicting kickoff timestamps for player-game")
        kickoffs[key] = kickoff
        if captured_at >= kickoff:
            continue  # post-kickoff evidence is never used to set a pregame designation

        designation = _field(row, "designation")
        if designation not in (*LABELS, CLEARANCE):
            raise ValueError("invalid designation; use an explicit 'Cleared' label, not a blank")
        capture_key = (key, captured_at)
        if capture_key in seen_captures:
            raise ValueError("duplicate player-game capture timestamp")
        seen_captures.add(capture_key)
        if key not in latest or captured_at > latest[key][0]:
            latest[key] = captured_at, designation

    for row in outcomes:
        key = identity(row)
        official(_field(row, "source"))
        status = _field(row, "game_book_status")
        if status not in OUTCOMES:
            raise ValueError("ambiguous game-book evidence")
        if key in observed:
            raise ValueError("duplicate player-game outcome")
        observed[key] = status

    # [reported, matched, played, active_dnp, inactive]
    counts: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0, 0, 0])
    for key, (_, designation) in latest.items():
        if designation == CLEARANCE:  # explicit verified clearance; never infer from a blank
            continue
        count = counts[key[0], designation]
        count[0] += 1
        status = observed.get(key)
        if status is None:
            continue
        count[1] += 1
        count[2 + OUTCOMES.index(status)] += 1

    result = []
    for (season, designation), (reported, n, played, active_dnp, inactive) in sorted(counts.items()):
        result.append({
            "season": season,
            "designation": designation,
            "reported": reported,
            "n": n,
            "unmatched": reported - n,
            "played": played,
            "active_dnp": active_dnp,
            "inactive": inactive,
            "play_rate": played / n if n else None,
            "wilson95": interval(played, n),
        })
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", type=Path, help="reviewed reports.csv")
    parser.add_argument("outcomes", type=Path, help="reviewed outcomes.csv")
    parser.add_argument("--manifest", type=Path, required=True,
                        help="hash-bound completeness/source-review attestation JSON")
    args = parser.parse_args()
    try:
        with args.reports.open(encoding="utf-8", newline="") as stream:
            reports = list(csv.DictReader(stream))
        with args.outcomes.open(encoding="utf-8", newline="") as stream:
            outcomes = list(csv.DictReader(stream))
        with args.manifest.open(encoding="utf-8") as stream:
            manifest = json.load(stream)
        verify_manifest(manifest, args.reports, args.outcomes, reports, outcomes)
        result = evaluate(reports, outcomes)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
