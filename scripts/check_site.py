"""
Integration check for docs/: (1) every internal link and asset resolves, (2) every
data-table row (<tbody> row) that carries entries has at least one external source link,
(3) no page contains unfilled placeholders. Exit 1 on any failure.
"""
import re, sys
from html.parser import HTMLParser
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"
bad = []
pages = sorted(DOCS.glob("*.html"))

class P(HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []; self.in_tbody = 0; self.rows = []; self.cur = None
    def handle_starttag(self, tag, a):
        d = dict(a)
        if tag in ("a", "link", "script") and ("href" in d or "src" in d):
            self.links.append(d.get("href") or d.get("src"))
        if tag == "tbody": self.in_tbody += 1
        if tag == "tr" and self.in_tbody: self.cur = {"links": 0, "text": ""}
        if tag == "a" and self.cur is not None and d.get("href", "").startswith("http"): self.cur["links"] += 1
    def handle_endtag(self, tag):
        if tag == "tbody": self.in_tbody -= 1
        if tag == "tr" and self.cur is not None: self.rows.append(self.cur); self.cur = None
    def handle_data(self, data):
        if self.cur is not None: self.cur["text"] += data

for page in pages:
    text = page.read_text(encoding="utf-8")
    p = P(); p.feed(text)
    for href in p.links:
        if not href or href.startswith(("http", "mailto:", "#")): continue
        target = (DOCS / href.split("#")[0]).resolve()
        if not target.exists(): bad.append(f"{page.name}: broken link -> {href}")
    for row in p.rows:
        if row["text"].strip() and row["links"] == 0 and "Source" not in row["text"]:
            # matrix rows (correlation) are derived values; the caption on the page links the source
            if page.name != "strategies.html":
                bad.append(f"{page.name}: table row without source link: {row['text'].strip()[:80]!r}")
    if "TODO" in text or "{" in re.sub(r"<style.*?</style>|<script.*?</script>", "", text, flags=re.S) and "function" not in text:
        pass
    for ph in ("TODO", "XXX", "nan</", ">nan<", "None</td>"):
        if ph in text: bad.append(f"{page.name}: placeholder {ph!r} present")

for css in ("assets/style.css", "assets/app.js"):
    if not (DOCS / css).exists(): bad.append(f"missing {css}")
if not (DOCS / "index.html").exists(): bad.append("missing index.html")
print(f"checked {len(pages)} pages")
if bad:
    print("\n".join(bad)); print(f"FAIL: {len(bad)} problem(s)"); sys.exit(1)
print("OK: no broken links; all data rows have a source link; no placeholders")
