"""Static site generator.

Renders the whole dashboard from the collected JSON datasets. Every rendered
table row carries a link to the official source the row came from; the
verification step refuses to publish if any populated row lacks one.

Output is a directory of static HTML files that GitHub Pages can serve
directly - no build service, no runtime, no JavaScript framework.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .sources import SOURCES, Source

# ---------------------------------------------------------------------------
# small HTML helpers
# ---------------------------------------------------------------------------


def esc(value: Any) -> str:
    """Escape a value for HTML text content."""
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def esc_attr(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def fmt_number(value: Any, digits: int = 2) -> str:
    """Format a number, leaving blanks for missing values."""
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return esc(value)
    if isinstance(value, (int,)):
        return esc(f"{value:,}")
    if isinstance(value, float):
        if value != value:  # NaN
            return ""
        return esc(f"{value:,.{digits}f}")
    return esc(value)


def source_link(url: Optional[str], label: str = "source") -> str:
    """Render the official-source link that every populated row must carry."""
    if not url:
        return '<span class="src src--missing">no source</span>'
    return (
        f'<a class="src" href="{esc_attr(url)}" target="_blank" rel="noopener">'
        f"{esc(label)} &#8599;</a>"
    )


@dataclass
class Table:
    """A rendered table with a caption and column headers."""

    caption: str
    headers: List[str]
    rows: List[List[str]]
    #: Class applied to the table element.
    css_class: str = ""
    note: Optional[str] = None

    def to_html(self) -> str:
        head = "".join(f"<th>{esc(h)}</th>" for h in self.headers)
        body = []
        for row in self.rows:
            cells = "".join(f"<td>{cell}</td>" for cell in row)
            body.append(f"<tr>{cells}</tr>")
        caption = f'<caption class="tbl__cap">{esc(self.caption)}</caption>' if self.caption else ""
        klass = f" {self.css_class}" if self.css_class else ""
        note = f'<p class="tbl__note">{note}</p>' if self.note else ""
        return (
            f'<div class="table-wrap"><table class="tbl{klass}">{caption}'
            f"<thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>{note}"
        )


# ---------------------------------------------------------------------------
# page shell
# ---------------------------------------------------------------------------
NAV: List[Dict[str, str]] = [
    {"id": "index", "href": "index.html", "label": "Overview", "icon": "◈"},
    {"id": "requirements", "href": "pages/requirements.html", "label": "Requirements", "icon": "☰"},
    {"id": "questions", "href": "pages/questions.html", "label": "Questions & gaps", "icon": "?"},
    {"id": "strategies", "href": "pages/strategies.html", "label": "Strategies", "icon": "◬"},
    {"id": "validation", "href": "pages/validation.html", "label": "Validation gates", "icon": "✓"},
    {"id": "correlation", "href": "pages/correlation.html", "label": "Correlations", "icon": "∿"},
    {"id": "schedule", "href": "pages/schedule.html", "label": "Schedule", "icon": "▦"},
    {"id": "availability", "href": "pages/availability.html", "label": "Injuries & depth", "icon": "＋"},
    {"id": "suggestions", "href": "pages/suggestions.html", "label": "Suggestions", "icon": "✦"},
    {"id": "review", "href": "pages/review.html", "label": "Flagged for review", "icon": "⚑"},
    {"id": "sources", "href": "pages/sources.html", "label": "Sources", "icon": "⛁"},
]

BRAND = "FOURTH DOWN"
BRAND_SUB = "NFL DECISION SUPPORT"


def page(
    *,
    slug: str,
    eyebrow: str,
    title: str,
    intro: str,
    body: str,
    asof: str,
    extra_nav: str = "",
) -> str:
    """Render a complete page with the shared shell."""
    prefix = _asset_prefix(slug)
    nav_items = []
    for item in NAV:
        active = " class=\"active\"" if item["id"] == slug else ""
        nav_items.append(
            f'<a{active} href="{prefix}{item["href"]}">{item["icon"]} &nbsp;{esc(item["label"])}</a>'
        )

    # Body links are written site-absolute; rewrite them for the page depth.
    body = re.sub(r'href="(?!https?:|mailto:|#)([^"]*?\.html)"',
                  lambda m: f'href="{prefix}{m.group(1)}"', body)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} — {BRAND}</title>
<meta name="description" content="{esc_attr(intro)}">
<link rel="stylesheet" href="{prefix}assets/site.css">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<aside class="rail">
  <a class="brand" href="{prefix}index.html">
    <span class="brand-mark">4D</span>
    <span>{BRAND}<small>{BRAND_SUB}</small></span>
  </a>
  <nav>
    <label>WORKSPACE</label>
    {''.join(nav_items)}
    {extra_nav}
  </nav>
  <div class="rail-note">
    <span class="dot"></span>
    <p>Every published row links to the official source it came from. Unverified values are left blank and listed on the Flagged for review page.</p>
  </div>
  <footer>Evidence first. No invented inputs.</footer>
</aside>
<main id="main">
  <header class="top">
    <span>WORKSPACE <i>/ {esc(eyebrow)}</i></span>
    <span class="asof">DATA AS OF {esc(asof)}</span>
  </header>
  <section class="page-title">
    <div class="eyebrow">{esc(eyebrow)}</div>
    <h1>{esc(title)}</h1>
    <p>{esc(intro)}</p>
  </section>
  <section class="content">
{body}
  </section>
</main>
</body>
</html>
"""


def _asset_prefix(slug: str) -> str:
    """Paths inside a subpage are relative to ``pages/``."""
    return "" if slug == "index" else "../"


# ---------------------------------------------------------------------------
# building blocks
# ---------------------------------------------------------------------------
def section(heading: str, content: str, *, level: int = 2) -> str:
    tag = f"h{level}"
    return f'<section class="block"><{tag}>{esc(heading)}</{tag}>{content}</section>'


def note(text: str, kind: str = "info") -> str:
    return f'<div class="note note--{esc_attr(kind)}">{text}</div>'


def stat_grid(stats: Sequence[Dict[str, Any]]) -> str:
    cells = []
    for stat in stats:
        value = stat.get("value")
        display = "" if value in (None, "") else str(value)
        cells.append(
            '<div class="stat"><div class="stat__v">{0}</div>'
            '<div class="stat__k">{1}</div></div>'.format(
                esc(display), esc(stat.get("label", ""))
            )
        )
    return f'<div class="stats">{"".join(cells)}</div>'


def badge(text: str, kind: str = "") -> str:
    klass = f" status status--{kind}" if kind else " status"
    return f'<span class="{klass.strip()}">{esc(text)}</span>'
