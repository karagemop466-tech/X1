"""HTML utilities: turn a page into an ordered event stream + table objects.

The official NFL pages are server-rendered, so plain `urllib` + `html.parser` is
enough (verified on GitHub-hosted runners: nfl.com/standings returns one 33-row
table, nfl.com/injuries returns 28 five-column tables).

The parser deliberately keeps *document order*: injury tables carry no team
column, so the team has to be recovered from the element that precedes the
table. Callers therefore get both `tables` (structured) and `events`
(('heading', ...), ('link', ...), ('text', ...), ('table', index)).
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple

HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
SKIP_TAGS = {"script", "style", "noscript", "svg", "template"}
BREAK_TAGS = {"br", "p", "div", "li", "tr", "section"}


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


class DocParser(HTMLParser):
    """Collect headings, links, loose text and tables in document order."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.events: List[Tuple[Any, ...]] = []
        self.tables: List[Dict[str, Any]] = []

        self._tdepth = 0
        self._skip = 0
        self._table: Optional[Dict[str, Any]] = None
        self._row: Optional[List[Dict[str, Any]]] = None
        self._cell: Optional[Dict[str, Any]] = None
        self._link: Optional[Tuple[str, List[str], List[str]]] = None
        self._head: Optional[Tuple[int, List[str]]] = None
        self._text_buf: List[str] = []

    # ------------------------------------------------------------------ utils
    def _flush_text(self) -> None:
        if self._tdepth == 0 and self._cell is None:
            text = _squash(" ".join(self._text_buf))
            self._text_buf = []
            if text:
                self.events.append(("text", text))
        else:
            self._text_buf = []

    # ------------------------------------------------------------ start tags
    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag in SKIP_TAGS:
            self._skip += 1
            return
        attr = {k.lower(): (v or "") for k, v in attrs}

        if tag == "table":
            self._flush_text()
            self._tdepth += 1
            if self._tdepth == 1:
                self._table = {"index": len(self.tables), "header": None, "rows": []}
            return

        if self._tdepth >= 1:
            if tag in ("tr",) and self._tdepth == 1:
                self._row = []
            elif tag in ("td", "th") and self._tdepth == 1:
                self._cell = {"tag": tag, "text": "", "hrefs": [], "imgs": []}
            elif tag == "img" and self._cell is not None:
                for key in ("src", "data-src"):
                    if attr.get(key):
                        self._cell["imgs"].append(attr[key])
                        break
            elif tag == "a" and self._cell is not None:
                self._link = (attr.get("href", ""), [], [])
            return

        if tag in HEADING_TAGS:
            self._flush_text()
            self._head = (int(tag[1]), [])
        elif tag == "a":
            self._flush_text()
            self._link = (attr.get("href", ""), [], [])
        elif tag == "img":
            if self._link is not None:
                src = attr.get("src") or attr.get("data-src")
                if src:
                    self._link[2].append(src)
        elif tag in BREAK_TAGS:
            if self._text_buf and tag in ("p", "div", "li", "section"):
                self._flush_text()

    def handle_startendtag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag == "br":
            if self._cell is not None:
                self._cell["text"] += " "
            elif self._link is not None:
                self._link[1].append(" ")
        else:
            self.handle_starttag(tag, attrs)

    # -------------------------------------------------------------- end tags
    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
            return

        if tag == "table" and self._tdepth >= 1:
            self._tdepth -= 1
            if self._tdepth == 0 and self._table is not None:
                self.tables.append(self._table)
                self.events.append(("table", self._table["index"]))
                self._table = None
            return

        if self._tdepth >= 1:
            if tag == "a" and self._link is not None:
                # Links inside a table stay attached to the cell that contains
                # them; they must not leak into the document-level event stream.
                href, _parts, imgs = self._link
                self._link = None
                if self._cell is not None:
                    if href:
                        self._cell["hrefs"].append(href)
                    self._cell["imgs"].extend(imgs)
            elif tag in ("td", "th") and self._cell is not None:
                self._cell["text"] = _squash(self._cell["text"])
                if self._row is not None:
                    self._row.append(self._cell)
                self._cell = None
            elif tag == "tr" and self._tdepth == 1 and self._row is not None:
                cells = self._row
                self._row = None
                if not cells:
                    return
                if all(c["tag"] == "th" for c in cells):
                    if self._table is not None and self._table["header"] is None:
                        self._table["header"] = [c["text"] for c in cells]
                elif self._table is not None:
                    self._table["rows"].append(cells)
            return

        if tag in HEADING_TAGS and self._head is not None:
            level, parts = self._head
            self._head = None
            text = _squash(" ".join(parts))
            if text:
                self.events.append(("heading", level, text))
        elif tag == "a" and self._link is not None:
            href, parts, imgs = self._link
            self._link = None
            text = _squash(" ".join(parts))
            self.events.append(("link", href, text, imgs))
        elif tag in BREAK_TAGS and tag in ("p", "div", "li", "section"):
            self._flush_text()

    # ------------------------------------------------------------------ data
    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self._cell is not None:
            self._cell["text"] += data
        if self._link is not None:
            self._link[1].append(data)
        if self._head is not None:
            self._head[1].append(data)
        if self._tdepth == 0 and self._cell is None and self._link is None and self._head is None:
            self._text_buf.append(data)

    def close(self) -> None:  # noqa: D102 - stdlib override
        super().close()
        self._flush_text()


def parse(html: str) -> DocParser:
    parser = DocParser()
    parser.feed(html)
    parser.close()
    return parser


def cell_text(cell: Dict[str, Any]) -> str:
    return cell.get("text", "").strip()


def cell_href(cell: Dict[str, Any]) -> str:
    return cell["hrefs"][0] if cell.get("hrefs") else ""


def row_texts(row: List[Dict[str, Any]]) -> List[str]:
    return [cell_text(c) for c in row]


# --------------------------------------------------------------------- helpers
TEAM_HREF_RE = re.compile(r"nfl\.com/teams/([a-z0-9\-]+)", re.I)
TEAM_PATH_RE = re.compile(r"^/teams/([a-z0-9\-]+)", re.I)
LOGO_RE = re.compile(r"/(?:clubs/logos|league/api/clubs/logos)/([A-Z]{2,3})(?:[\./]|$)")


def abbrev_from_imgs(imgs: List[str]) -> Optional[str]:
    for src in imgs or []:
        match = LOGO_RE.search(src)
        if match:
            return match.group(1)
    return None


def slug_from_href(href: str) -> Optional[str]:
    """Extract the official team slug from an NFL.com team link.

    Handles absolute ('https://www.nfl.com/teams/buffalo-bills/') and
    relative ('/teams/buffalo-bills/') hrefs, with or without a trailing slash.
    """
    href = (href or "").strip()
    match = TEAM_HREF_RE.search(href)
    if match:
        return match.group(1).lower()
    match = TEAM_PATH_RE.match(href)
    return match.group(1).lower() if match else None


def titleize_slug(slug: str) -> str:
    """'los-angeles-chargers' -> 'Los Angeles Chargers'. Pure formatting, no lookup."""
    small = {"and", "of", "the"}
    parts = slug.split("-")
    out = []
    for i, part in enumerate(parts):
        out.append(part.capitalize() if i == 0 or part not in small else part)
    return " ".join(out)
