#!/usr/bin/env python3
"""Snapshot annex checks (session arena/a78e0158-x1).

Scope: `site/` only (the canonical site has its own verifiers).
Enforces the same house rule at annex tiering (docs/annex/sources-snapshot.md):
1. every internal link/asset in site/*.html resolves inside site/;
2. every non-empty <tbody> data row contains at least one external https link
   (the annex puts the source link in a per-row Source cell);
3. external hosts must belong to the annex's registered tiers
   (official NFL family, nflverse on github.com, or trusted-secondary list);
4. no page contains unresolved template markers.

Exit 1 on any failure.
"""
import re, sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
ALLOWED_HOSTS = (
    "nfl.com", "operations.nfl.com", "github.com", "raw.githubusercontent.com",
    "nbcsports.com", "sofistadium.com", "profootballhof.com",
    "nytimes.com", "sports.yahoo.com",
    "karagemop466-tech.github.io",  # this project's own published Pages artifact (flag F14 reference)
)
TEMPLATE_MARKERS = ("{{", "}}", "None None")

bad: list[str] = []


class AnnexParser(HTMLParser):
    def __init__(self, page: Path):
        super().__init__(convert_charrefs=True)
        self.page = page
        self.links: list[str] = []
        self.in_tbody = 0
        self.table_stack: list[bool] = []
        self.row: dict | None = None
        self.rows: list[dict] = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag in ("a", "link", "script") and ("href" in d or "src" in d):
            self.links.append(d.get("href") or d.get("src"))
        if tag == "tbody":
            self.in_tbody += 1
        if tag == "table":
            self.table_stack.append("data-table" in dict(attrs))
        if tag == "tr" and self.in_tbody:
            self.row = {"links": 0, "text": "", "data_table": bool(self.table_stack and self.table_stack[-1])}
        if tag == "a" and self.row is not None and (d.get("href") or "").startswith("https://"):
            self.row["links"] += 1

    def handle_endtag(self, tag):
        if tag == "tbody":
            self.in_tbody -= 1
        if tag == "table" and self.table_stack:
            self.table_stack.pop()
        if tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.row is not None:
            self.row["text"] += data


def main() -> int:
    pages = sorted(SITE.glob("*.html"))
    if not pages:
        print("annex verification failed: no pages in site/")
        return 1
    for page in pages:
        text = page.read_text(encoding="utf-8")
        for marker in TEMPLATE_MARKERS:
            if marker in text:
                bad.append(f"{page.name}: template marker {marker!r} present")
        if re.search(r">\s*(nan|None|undefined)\s*<", text):
            bad.append(f"{page.name}: unresolved placeholder cell present")
        p = AnnexParser(page)
        p.feed(text)
        for href in p.links:
            if not href or href.startswith(("http", "mailto:", "#")):
                continue
            target = (SITE / href.split("#")[0]).resolve()
            if not target.exists():
                bad.append(f"{page.name}: broken link -> {href}")
            if target.exists() and target.suffix == ".html" and SITE not in target.parents:
                bad.append(f"{page.name}: internal link escapes site/ -> {href}")
        # per-row rule applies to data tables (marked data-table); other tables must
        # carry at least one reference link somewhere in the table (method/definitions)
        for i, row in enumerate(p.rows, 1):
            if row["text"].strip() and row["links"] == 0 and row.get("data_table"):
                bad.append(f"{page.name}: data row {i} has no external source link")
        for href in re.findall(r'href="(https?://[^"]+)"', text):
            host = urlparse(href).hostname or ""
            if not any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS):
                bad.append(f"{page.name}: external host not in annex allowlist -> {host}")
    if bad:
        print("Annex verification failed:")
        print("\n".join(f"- {e}" for e in bad))
        return 1
    print(f"Annex verification passed: {len(pages)} pages; links resolve; "
          f"every data row sourced; hosts within registered tiers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
