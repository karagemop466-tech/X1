"""Player identity resolution across two official naming conventions.

The league publishes the same player under two different names:

* the **injury report** and **player pages** use the full name and a profile
  slug - ``Jayden Daniels``, ``/players/jayden-daniels/``;
* the **game book** uses the abbreviated form - ``J.Daniels``.

Joining the two is what makes the depth model possible, so the mapping has to
be derived rather than guessed. This module derives it from the data itself:

1. The profile slug gives the surname and the player's initials.
2. The game-book name is split into an initial part and a surname part.
3. A match is accepted only when it is unique on both sides.

Anything that cannot be resolved uniquely is left unresolved, and the caller
records it for review rather than picking a candidate.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")


def slug_parts(slug: str) -> Tuple[str, str]:
    """Split a player profile slug into ``(initials, surname)``.

    ``jayden-daniels`` -> ``("jd", "daniels")``
    ``chris-johnson-jr`` -> ``("cjj", "johnsonjr")``
    """
    text = (slug or "").strip().lower().rstrip("/")
    text = text.rsplit("/", 1)[-1]
    parts = [p for p in _SLUG_STRIP_RE.split(text) if p]
    if not parts:
        return ("", "")
    surname = parts[-1]
    # A trailing suffix (jr, sr, ii, iii) is not part of the surname.
    if len(parts) >= 2 and parts[-1] in ("jr", "sr", "ii", "iii", "iv"):
        surname = parts[-2]
        given = parts[:-2]
    else:
        given = parts[:-1]
    initials = "".join(p[0] for p in given if p)
    return (initials, surname)


def gamebook_parts(name: str) -> Tuple[str, str]:
    """Split a game-book name into ``(initials, surname)``.

    ``J.Daniels`` -> ``("j", "daniels")``
    ``A.Vera-Tucker`` -> ``("a", "veratucker")``
    ``G.Van Roten`` -> ``("g", "vanroten")``
    """
    text = (name or "").strip()
    if not text:
        return ("", "")
    text = text.replace(".", " ")
    parts = [p for p in re.split(r"\s+", text) if p]
    if not parts:
        return ("", "")
    if len(parts) == 1:
        token = parts[0]
        return (token[:1].lower(), _normalise(token))
    if len(parts[0]) == 1:
        # ``G.Van Roten`` - a single initial followed by a multi-word surname.
        initials = parts[0].lower()
        surname = _normalise(" ".join(parts[1:]))
        return (initials, surname)
    initials = "".join(p[0] for p in parts[:-1]).lower()
    surname = _normalise(parts[-1])
    return (initials, surname)


def _normalise(value: str) -> str:
    return re.sub(r"[^a-z]", "", (value or "").lower())


def full_name_parts(name: str) -> Tuple[str, str]:
    """Split a full name into ``(initials, surname)``.

    ``Jayden Daniels`` -> ``("j", "daniels")``
    """
    text = (name or "").strip()
    parts = [p for p in re.split(r"\s+", text) if p]
    if not parts:
        return ("", "")
    if len(parts) == 1:
        return (parts[0][:1].lower(), _normalise(parts[0]))
    return (parts[0][:1].lower(), _normalise(parts[-1]))


class AliasIndex:
    """Maps injury-report players onto the names used in the game books."""

    def __init__(self) -> None:
        #: ``(initials, surname)`` -> game-book name.
        self._gamebook: Dict[Tuple[str, str], str] = {}
        #: game-book name -> ``(initials, surname)``.
        self._reverse: Dict[str, Tuple[str, str]] = {}
        #: Resolutions that were ambiguous.
        self.ambiguous: List[str] = []
        #: Resolutions that had no candidate.
        self.unresolved: List[str] = []

    def add_gamebook_names(self, names: Iterable[str]) -> None:
        for name in names:
            key = gamebook_parts(name)
            if not key[1]:
                continue
            if key in self._gamebook and self._gamebook[key] != name:
                self.ambiguous.append(name)
                continue
            self._gamebook[key] = name
            self._reverse[name] = key

    def resolve(self, full_name: str, slug: Optional[str] = None) -> Optional[str]:
        """Return the game-book name for a player, or ``None``.

        The profile slug is preferred because it is unambiguous. When it is not
        available the full name is used. A match is only returned when it is
        unique.
        """
        candidates: List[str] = []
        if slug:
            initials, surname = slug_parts(slug)
            if surname:
                candidates.append(f"{initials}{surname}")
        full_initials, full_surname = full_name_parts(full_name)
        if full_surname:
            candidates.append(f"{full_initials}{full_surname}")

        matches = set()
        for candidate in candidates:
            for key, name in self._gamebook.items():
                joined = f"{key[0]}{key[1]}"
                if joined == candidate:
                    matches.add(name)
        if len(matches) == 1:
            return matches.pop()
        if len(matches) > 1:
            self.ambiguous.append(full_name)
        else:
            self.unresolved.append(full_name)
        return None

    def names(self) -> Sequence[str]:
        return list(self._reverse.keys())
