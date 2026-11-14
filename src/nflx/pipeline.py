"""End-to-end collection pipeline over official NFL endpoints.

Run with::

    python -m nflx.pipeline collect --out data/nfl

The pipeline writes one JSON document per dataset plus a ``provenance.json``
manifest recording, for every dataset, the URL it came from and the UTC
timestamp of the retrieval.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .collect import (
    collect_injuries as parse_injuries,
    collect_player_stats as parse_player_stats,
    collect_schedule as parse_schedule,
    collect_standings as parse_standings,
)
from .gamebook import parse_gamebook
from .http import Fetcher
from .sources import SOURCES

SEASON = 2026
REGULAR_SEASON_WEEKS = 18


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
    print(f"  wrote {path} ({path.stat().st_size} bytes)")


def _extract_pdf_text(pdf_bytes: bytes) -> Optional[str]:
    """Extract the text layer of a PDF using pypdf when it is available.

    ``layout`` mode is used because the game book is a two-column document:
    layout mode preserves the horizontal column boundaries, which is what makes
    the visitor/home split recoverable.
    """
    try:
        import io

        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        chunks = []
        for page in reader.pages:
            try:
                chunks.append(page.extract_text(extraction_mode="layout") or "")
            except Exception:
                chunks.append(page.extract_text() or "")
        return "\n".join(chunks)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"    PDF text extraction failed: {exc}")
        return None


def _gamebook_url(game_id: str) -> str:
    """Official game-book PDF URL for a game id.

    The Game Center page links the PDF at
    ``https://static.www.nfl.com/image/upload/v<version>/gamecenter/<id>.pdf``.
    The version segment changes whenever the league republishes the document,
    so the URL is discovered from the Game Center page rather than guessed.
    """
    return game_id


GAMEBOOK_LINK_RE = re.compile(
    r"https://static\.www\.nfl\.com/[^\"'\s]*?/gamecenter/(?P<gid>[0-9a-f\-]+)\.pdf"
)


# ---------------------------------------------------------------------------
# collection steps
# ---------------------------------------------------------------------------
def collect_injury_report(fetcher: Fetcher, out_dir: Path) -> Dict[str, Any]:
    source = SOURCES["injuries_current"]
    result = fetcher.get(source.url, max_age=3600)
    records, provenance = parse_injuries(
        result.text(), result.fetched_at, source.url, "injuries_current"
    )
    _write(out_dir / "injuries.json", {"provenance": provenance.to_dict(), "records": records})
    return provenance.to_dict()


def collect_standings(fetcher: Fetcher, out_dir: Path) -> Dict[str, Any]:
    source = SOURCES["standings"]
    result = fetcher.get(source.url, max_age=3600)
    records, provenance = parse_standings(
        result.text(), result.fetched_at, source.url, "standings"
    )
    _write(out_dir / "standings.json", {"provenance": provenance.to_dict(), "records": records})
    return provenance.to_dict()


def collect_schedule(fetcher: Fetcher, out_dir: Path, weeks: Optional[List[int]] = None) -> Dict[str, Any]:
    """Collect the official schedule for the season.

    The weekly pages render the scoreboard client-side, so the schedule data is
    taken from the league's own embedded game array, which the pages carry for
    the current season.
    """
    weeks = weeks or list(range(1, REGULAR_SEASON_WEEKS + 1))
    all_records: List[Dict[str, Any]] = []
    notes: List[str] = []
    retrieved_at = _now()

    for week in weeks:
        url = f"https://www.nfl.com/schedules/{SEASON}/by-week/week-{week}"
        try:
            result = fetcher.get(url, max_age=86400)
        except Exception as exc:
            notes.append(f"week {week}: {exc}")
            continue
        records, _ = parse_schedule(result.text(), result.fetched_at, url, "schedule_week")
        if not records:
            # The embedded array is present on the standings page too; fall back
            # to the league-wide schedule payload for the week.
            records = _schedule_from_standings_payload(fetcher, week, url, result.fetched_at)
        for record in records:
            record["week"] = str(week)
        all_records.extend(records)

    provenance = {
        "source_key": "schedule_week",
        "source_url": f"https://www.nfl.com/schedules/{SEASON}/by-week/week-1",
        "retrieved_at": retrieved_at,
        "record_count": len(all_records),
        "notes": notes,
    }
    _write(out_dir / "schedule.json", {"provenance": provenance, "records": all_records})
    return provenance


def _schedule_from_standings_payload(
    fetcher: Fetcher, week: int, url: str, retrieved_at: str
) -> List[Dict[str, Any]]:
    """Read the league's embedded ``nationalGames`` payload.

    The NFL embeds a JSON array of game objects (title, kickoff, game id,
    week, season) in several pages. It is the same payload the schedule page
    itself consumes, so it is a primary league source.
    """
    import json as _json

    source = SOURCES["standings"]
    try:
        result = fetcher.get(source.url, max_age=3600)
    except Exception:
        return []
    html = result.text()
    marker = "nationalGames=["
    start = html.find(marker)
    if start < 0:
        return []
    start = html.find("[", start)
    depth = 0
    end = -1
    for index in range(start, len(html)):
        char = html[index]
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    if end < 0:
        return []
    try:
        games = _json.loads(html[start:end])
    except ValueError:
        return []
    records = []
    for game in games:
        if str(game.get("Week")) != str(week):
            continue
        title = game.get("Title", "")
        away, _, home = title.partition(" at ")
        records.append(
            {
                "game_id": game.get("GameId"),
                "title": title,
                "away_team": away.strip() or None,
                "home_team": home.strip() or None,
                "start_time_utc": game.get("StartTime"),
                "game_territory": game.get("GameTerritory"),
                "week": str(week),
                "season": str(game.get("NflSeason")),
                "source_url": source.url,
                "source_label": source.title,
                "retrieved_at": retrieved_at,
            }
        )
    return records


def collect_player_stats(fetcher: Fetcher, out_dir: Path) -> Dict[str, Any]:
    """Collect the three headline player-stat categories with full pagination."""
    categories = [
        ("passing", "player_stats_passing", "passingyards"),
        ("rushing", "player_stats_rushing", "rushingyards"),
        ("receiving", "player_stats_receiving", "receivingreceptions"),
    ]
    all_provenance = []
    for category, source_key, sort_key in categories:
        source = SOURCES[source_key]
        url = source.url
        records: List[Dict[str, Any]] = []
        seen = set()
        retrieved_at = _now()
        pages = 0
        while url and pages < 40:
            try:
                result = fetcher.get(url, max_age=3600)
            except Exception as exc:
                print(f"  ! {category} page {pages}: {exc}")
                break
            page_records, _ = parse_player_stats(
                result.text(), result.fetched_at, url, source_key, category
            )
            new = [r for r in page_records if r["player"] not in seen]
            for record in new:
                seen.add(record["player"])
            records.extend(new)
            pages += 1
            url = _next_page_url(result.text())
            if not new:
                break
        provenance = {
            "source_key": source_key,
            "source_url": source.url,
            "retrieved_at": retrieved_at,
            "record_count": len(records),
            "notes": [f"paginated over {pages} page(s)"],
        }
        _write(
            out_dir / f"player_stats_{category}.json",
            {"provenance": provenance, "records": records},
        )
        all_provenance.append(provenance)
    return {"categories": all_provenance}


NEXT_PAGE_RE = re.compile(
    r'<a href="(?P<href>/stats/player-stats/category/[^"]+aftercursor=[^"]+)"[^>]*'
    r'class="nfl-o-table-pagination__next"'
)


def _next_page_url(html: str) -> Optional[str]:
    match = NEXT_PAGE_RE.search(html)
    if not match:
        return None
    return "https://www.nfl.com" + match.group("href")


def collect_gamebooks(
    fetcher: Fetcher,
    out_dir: Path,
    game_ids: List[str],
    source_url: str,
    max_games: int = 60,
) -> Dict[str, Any]:
    """Download and parse official Game Book PDFs for the given game ids.

    The Game Book is the league's own record of the game: lineups, inactives,
    officials, weather and the full box score.
    """
    records: List[Dict[str, Any]] = []
    notes: List[str] = []
    fetched = 0

    for game_id in game_ids[:max_games]:
        page_url = _game_center_url_for(fetcher, game_id)
        if not page_url:
            notes.append(f"{game_id}: no Game Center page located")
            continue
        try:
            page = fetcher.get(page_url, max_age=86400)
        except Exception as exc:
            notes.append(f"{game_id}: Game Center fetch failed ({exc})")
            continue
        links = GAMEBOOK_LINK_RE.findall(page.text())
        if not links:
            notes.append(f"{game_id}: no Game Book PDF link on the Game Center page")
            continue
        pdf_url = page_url.rsplit("/", 1)[0]
        pdf_url = f"https://static.www.nfl.com/image/upload/v0/gamecenter/{links[0]}.pdf"
        # The version segment is discovered from the page markup itself.
        version_match = re.search(
            r"https://static\.www\.nfl\.com/image/upload/(v[0-9]+)/gamecenter/", page.text()
        )
        if version_match:
            pdf_url = f"https://static.www.nfl.com/image/upload/{version_match.group(1)}/gamecenter/{links[0]}.pdf"
        try:
            pdf = fetcher.get(pdf_url, max_age=86400)
        except Exception as exc:
            notes.append(f"{game_id}: Game Book PDF fetch failed ({exc})")
            continue
        text = _extract_pdf_text(pdf.body)
        if not text:
            notes.append(f"{game_id}: Game Book text layer unavailable")
            continue
        book = parse_gamebook(text)
        record = book.to_dict()
        record.update(
            {
                "game_id": game_id,
                "game_book_url": pdf_url,
                "game_center_url": page_url,
                "source_url": source_url,
                "source_label": SOURCES["game_book"].title,
                "retrieved_at": pdf.fetched_at,
            }
        )
        records.append(record)
        fetched += 1
        print(f"  game book {fetched}: {record.get('matchup')} ({record.get('visitor_points')}-"
              f"{record.get('home_points')})")

    provenance = {
        "source_key": "game_book",
        "source_url": source_url,
        "retrieved_at": _now(),
        "record_count": len(records),
        "notes": notes[:50],
    }
    _write(out_dir / "gamebooks.json", {"provenance": provenance, "records": records})
    return provenance


GAME_CENTER_RE = re.compile(
    r'"GameId":"(?P<gid>[0-9a-f\-]+)".*?"Title":"(?P<title>[^"]+)"', re.IGNORECASE
)


def _game_center_url_for(fetcher: Fetcher, game_id: str) -> Optional[str]:
    """Build a Game Center URL for a game id.

    NFL game-center URLs are ``/games/<away>-at-<home>-<season>-<season-type>-<week>``.
    The slug cannot be derived from the id alone, so the weekly schedule page is
    used to map id -> slug. The mapping is cached for the life of the process.
    """
    slug = _slug_cache.get(game_id)
    if slug:
        return slug
    for week in range(1, REGULAR_SEASON_WEEKS + 1):
        url = f"https://www.nfl.com/schedules/{SEASON}/by-week/week-{week}"
        try:
            page = fetcher.get(url, max_age=86400)
        except Exception:
            continue
        text = page.text()
        index = text.find(game_id)
        if index < 0:
            continue
        # The anchor immediately preceding the game id in the markup is the
        # Game Center link for that game.
        window = text[max(0, index - 6000) : index + 6000]
        anchors = re.findall(r'href="(/games/[^"]+)"', window)
        if anchors:
            slug = "https://www.nfl.com" + anchors[-1]
            _slug_cache[game_id] = slug
            return slug
    return None


_slug_cache: Dict[str, str] = {}


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Collect official NFL data.")
    parser.add_argument("--out", default="data/nfl", help="output directory")
    parser.add_argument("--cache", default=".cache/nflx", help="HTTP cache directory")
    parser.add_argument("--skip-gamebooks", action="store_true")
    parser.add_argument("--max-gamebooks", type=int, default=40)
    parser.add_argument("--weeks", default="", help="comma separated week numbers")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    fetcher = Fetcher(Path(args.cache))

    manifest: Dict[str, Any] = {"generated_at": _now(), "season": SEASON, "datasets": []}

    print("[1/5] injury report")
    manifest["datasets"].append(collect_injury_report(fetcher, out_dir))

    print("[2/5] standings")
    manifest["datasets"].append(collect_standings(fetcher, out_dir))

    print("[3/5] schedule")
    weeks = [int(w) for w in args.weeks.split(",") if w.strip()] or None
    manifest["datasets"].append(collect_schedule(fetcher, out_dir, weeks))

    print("[4/5] player statistics")
    manifest["datasets"].append(collect_player_stats(fetcher, out_dir))

    if not args.skip_gamebooks:
        print("[5/5] official game books")
        schedule_path = out_dir / "schedule.json"
        game_ids: List[str] = []
        if schedule_path.exists():
            payload = json.loads(schedule_path.read_text(encoding="utf-8"))
            seen = set()
            for record in payload.get("records", []):
                gid = record.get("game_id")
                if gid and gid not in seen:
                    seen.add(gid)
                    game_ids.append(gid)
        manifest["datasets"].append(
            collect_gamebooks(
                fetcher,
                out_dir,
                game_ids,
                SOURCES["game_book"].url,
                max_games=args.max_gamebooks,
            )
        )

    _write(out_dir / "provenance.json", manifest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
