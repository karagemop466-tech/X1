"""Official club-site registry.

NFL.com's own teams page (https://www.nfl.com/teams/) prints, for every club, a
"View Profile" link (nfl.com/teams/<slug>/) followed by a "View Full Site" link
to that club's official website. That makes the league the authority for which
domain is official, so the pipeline reads the mapping from the league instead of
trusting a hand-written list.

The hand-written list in `sources.py` is only a fallback for the case where the
teams page cannot be reached; when both are available the league page wins.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Tuple
from urllib.parse import urlparse

from . import htmlutil as H

TEAMS_URL = "https://www.nfl.com/teams/"
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data"
DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "pipeline", "club_registry.json"
)


def discover(html: str) -> Dict[str, str]:
    """Return {team_slug: official club domain} from the NFL.com teams page."""
    doc = H.parse(html)
    mapping: Dict[str, str] = {}
    events = doc.events
    for index, event in enumerate(events):
        if event[0] != "link":
            continue
        slug = H.slug_from_href(event[1])
        if not slug:
            continue
        # The club site link is the next link after the profile link.
        for follow in events[index + 1: index + 4]:
            if follow[0] != "link":
                continue
            host = (urlparse(follow[1]).hostname or "").lower()
            if not host or host.endswith("nfl.com"):
                continue
            # The league prints "https://www.club.com/"; store the bare domain so
            # the fetcher decides the host prefix itself.
            if host.startswith("www."):
                host = host[4:]
            mapping[slug] = host
            break
    return mapping


def load_previous() -> Dict[str, str]:
    if not os.path.exists(DATA_PATH):
        return {}
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload.get("by_slug", {})
    except Exception:  # noqa: BLE001
        return {}


def save(mapping: Dict[str, str], source_url: str) -> None:
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    rows = [
        {
            "team_slug": slug,
            "club_domain": domain,
            "official_site": f"https://www.{domain}",
            "_source_url": source_url,
            "_source_label": "NFL.com — Official Sites of all 32 NFL Teams",
            "_source_org": "NFL",
            "_retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "_flags": [],
            "_unverified": [],
            "_verified": True,
        }
        for slug, domain in sorted(mapping.items())
    ]
    with open(DATA_PATH, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "dataset": "club_registry",
                "title": "Official club sites, as listed by the league",
                "source": {
                    "url": source_url,
                    "label": "NFL.com — Official Sites of all 32 NFL Teams",
                    "org": "NFL",
                },
                "columns": ["team_slug", "club_domain", "official_site"],
                "source_url": source_url,
                "source_label": "NFL.com — Official Sites of all 32 NFL Teams",
                "source_org": "NFL",
                "count": len(mapping),
                "by_slug": mapping,
                "rows": rows,
                "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                "verification": {
                    "rows": len(rows),
                    "rows_verified": len(rows),
                    "rows_flagged": 0,
                    "unverified_cells": 0,
                    "flagged_reasons": {},
                },
            },
            handle,
            indent=1,
            ensure_ascii=False,
        )
        handle.write("\n")


def resolve(html: Optional[str], log: List[Dict[str, object]]) -> Dict[str, str]:
    """Discovery first, committed cache second, hand-written fallback last."""
    mapping: Dict[str, str] = {}
    if html:
        discovered = discover(html)
        if len(discovered) >= 28:
            mapping = discovered
            save(discovered, TEAMS_URL)
            log.append({"source": "discovered from nfl.com/teams/", "count": len(discovered)})
        else:
            log.append(
                {"source": "nfl.com/teams/ parse short", "count": len(discovered), "action": "ignored"}
            )
    if not mapping:
        cached = load_previous()
        if len(cached) >= 28:
            mapping = cached
            log.append({"source": "cached club_registry.json", "count": len(cached)})
    return mapping
