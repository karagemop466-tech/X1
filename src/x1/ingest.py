"""Data acquisition.

The sandbox egress allow-list permits GitHub hosts only, so every bulk file is
pulled through the GitHub REST contents API (raw media type). Each download is
cached under ``data/raw`` and fingerprinted so the site can publish exactly
which bytes produced which table.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List

from . import config

# (local filename, owner/repo, path in repo, source registry key)
MANIFEST: List[tuple[str, str, str, str]] = [
    ("games.csv", "nflverse/nfldata", "data/games.csv", "nfldata_games"),
    ("closing_lines.csv", "nflverse/nfldata", "data/closing_lines.csv", "nfldata_closing_lines"),
    ("rosters.csv", "nflverse/nfldata", "data/rosters.csv", "nfldata_rosters"),
    ("standings.csv", "nflverse/nfldata", "data/standings.csv", "nfldata_standings"),
    ("teams.csv", "nflverse/nfldata", "data/teams.csv", "nfldata_games"),
    ("sc_lines.csv", "nflverse/nfldata", "data/sc_lines.csv", "nfldata_games"),
    ("initial_lines.csv", "nflverse/nfldata", "data/initial_lines.csv", "nfldata_games"),
    ("datasets_readme.md", "nflverse/nfldata", "DATASETS.md", "nfldata_games"),
    ("injuries_2026.csv", "Beexly/Sports", "data/nflverse/injuries_2026.csv", "nflverse_injuries"),
    ("rosters_2026.csv", "Beexly/Sports", "data/nflverse/rosters_2026.csv", "nflverse_weekly_rosters"),
    ("player_stats_weekly_archive.parquet", "Beexly/Sports", "data/nflverse/player_stats_weekly_archive.parquet", "player_week_stats"),
    ("player_week_stats_2026.csv", "Beexly/Sports", "data/nflverse/pennydata_2026_player_week_stats.csv", "player_week_stats"),
    ("depth_charts.parquet", "Beexly/Sports", "data/nflverse/hf_mikeysports_2025_depth_charts_zone1.parquet", "depth_charts_2025"),
    ("weather_history.parquet", "Beexly/Sports", "data/nflverse/kaggle_tobycrabtree_scores_weather_zone1.parquet", "weather_history"),
    ("ngs_receiving.csv.gz", "Beexly/Sports", "data/nflverse/ngs_receiving.csv.gz", "ngs_receiving"),
    ("contracts.parquet", "Beexly/Sports", "data/nflverse/hf_ypolatog_contracts_500_zone1.parquet", "player_week_stats"),
    ("pbp_2026_slim.csv.gz", "Beexly/Sports", "data/nflverse/pbp_2026_slim_clean_checkout.csv.gz", "nflverse_injuries"),
]


@dataclass
class FileRecord:
    name: str
    repo: str
    path: str
    source_key: str
    url: str
    bytes: int
    sha256: str
    status: str


def _raw_url(repo: str, path: str) -> str:
    return f"{config.GITHUB_API}/repos/{repo}/contents/{path}"


def _download(repo: str, path: str, dest: Path) -> None:
    req = urllib.request.Request(
        _raw_url(repo, path),
        headers={
            "Accept": config.GITHUB_RAW_ACCEPT,
            "User-Agent": "x1-nfl-lines",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        payload = resp.read()
    dest.write_bytes(payload)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sync(force: bool = False) -> List[FileRecord]:
    """Download every manifest entry into ``data/raw`` and return provenance."""
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    records: List[FileRecord] = []
    for name, repo, path, source_key in MANIFEST:
        dest = config.RAW_DIR / name
        if force or not dest.exists():
            try:
                _download(repo, path, dest)
                status = "downloaded"
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
                status = f"failed: {exc}"
                if not dest.exists():
                    records.append(
                        FileRecord(name, repo, path, source_key, _raw_url(repo, path), 0, "", status)
                    )
                    continue
        else:
            status = "cached"
        records.append(
            FileRecord(
                name=name,
                repo=repo,
                path=path,
                source_key=source_key,
                url=_raw_url(repo, path),
                bytes=dest.stat().st_size,
                sha256=_sha256(dest),
                status=status,
            )
        )
    manifest_path = config.DATA_DIR / "raw_manifest.json"
    manifest_path.write_text(json.dumps([asdict(r) for r in records], indent=2))
    return records


def raw_path(name: str) -> Path:
    return config.RAW_DIR / name


def copy_to_processed(name: str, target: str) -> Path:
    """Copy a raw artefact into the processed folder (kept in git for review)."""
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    src = raw_path(name)
    dst = config.PROCESSED_DIR / target
    shutil.copyfile(src, dst)
    return dst
