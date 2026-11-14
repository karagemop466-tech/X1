"""HTML table extraction helpers built on the standard library.

NFL.com renders its statistical and report pages as server-side HTML tables with
a consistent class vocabulary (``d3-o-table``, ``d3-o-table--detailed``). This
module provides a small, dependency-free parser that turns those tables into
plain dictionaries so the rest of the pipeline never has to touch markup.
"""

from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser
from typing import Dict, List, Optional

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_tags(fragment: str) -> str:
    """Remove markup and collapse whitespace."""
    without_tags = _TAG_RE.sub(" ", fragment)
    return _WS_RE.sub(" ", unescape(without_tags)).strip()


class _TableParser(HTMLParser):
    """Collects every ``<table>`` on a page as a list of row cell-lists."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: List[List[List[str]]] = []
        self._table: Optional[List[List[str]]] = None
        self._row: Optional[List[str]] = None
        self._cell: Optional[List[str]] = None
        self._caption: Optional[str] = None
        self._in_caption = False
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._depth += 1
            if self._depth == 1:
                self._table = []
                self._caption = None
        elif self._depth == 1 and tag == "tr":
            self._row = []
        elif self._depth == 1 and tag in ("td", "th"):
            self._cell = []
        elif self._depth == 1 and tag == "caption":
            self._in_caption = True

    def handle_endtag(self, tag):
        if tag == "table":
            if self._depth == 1 and self._table is not None:
                self.tables.append(self._table)
                self._table = None
            self._depth = max(0, self._depth - 1)
        elif self._depth == 1 and tag in ("td", "th"):
            if self._cell is not None and self._row is not None:
                self._row.append(" ".join("".join(self._cell).split()))
                self._cell = None
        elif self._depth == 1 and tag == "tr":
            if self._row is not None and self._table is not None:
                self._table.append(self._row)
            self._row = None
        elif self._depth == 1 and tag == "caption":
            self._in_caption = False

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)
        elif self._in_caption and self._caption is None:
            self._caption = data.strip()


def find_tables(html: str) -> List[List[List[str]]]:
    """Return all tables on the page as lists of rows of cell strings."""
    parser = _TableParser()
    parser.feed(html)
    parser.close()
    return parser.tables


def table_to_dicts(table: List[List[str]], headers: Optional[List[str]] = None):
    """Convert a table into a list of dicts keyed by header text.

    If ``headers`` is supplied it is used verbatim (column order on these pages
    is stable and the ``<thead>`` labels are abbreviated, so an explicit list is
    clearer). Otherwise the first row is treated as the header.
    """
    rows = [r for r in table if any(cell.strip() for cell in r)]
    if not rows:
        return []
    if headers is None:
        headers = [h.strip() for h in rows[0]]
        rows = rows[1:]
    out = []
    for row in rows:
        record = {}
        for index, key in enumerate(headers):
            record[key] = row[index].strip() if index < len(row) else ""
        out.append(record)
    return out


class _TextIndexParser(HTMLParser):
    """Indexes visible text with the character offsets of the source HTML.

    Used to associate a heading (for example the club name above an injury
    table) with the table that follows it.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.segments: List[tuple] = []  # (start_offset, text)
        self._offset = 0
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._skip:
            return
        text = " ".join(data.split())
        if text:
            self.segments.append((self._offset, text))
        self._offset += len(data)


def text_index(html: str) -> List[tuple]:
    """Return ``(offset, text)`` pairs for visible text in document order."""
    parser = _TextIndexParser()
    parser.feed(html)
    parser.close()
    return parser.segments


def find_element_spans(html: str, class_name: str) -> List[tuple]:
    """Return ``(start, end)`` spans of elements carrying ``class_name``."""
    spans: List[tuple] = []
    pattern = re.compile(
        r"<(?:div|p|span|section|table)\b[^>]*class=\"[^\"]*\b"
        + re.escape(class_name)
        + r"\b[^\"]*\"[^>]*>",
        re.IGNORECASE,
    )
    for match in pattern.finditer(html):
        spans.append((match.start(), match.end()))
    return spans
