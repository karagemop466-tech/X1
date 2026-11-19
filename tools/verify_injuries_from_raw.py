"""NFL report table parser adapted from PR #92; preserve empty official cells."""
import html as html_mod
import re
CLUB_HEAD = re.compile(r'd3-o-section-sub-title"><span>([^<]{2,40})</span>')
TABLE_RE = re.compile(r"<table[^>]*d3-o-reports--detailed[^>]*>(.*?)</table>", re.S)
TR_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
A_HREF = re.compile(r'href="(/players/[^"]+?)/?"')
ROW_COUNT_RE = re.compile(r"<h2[^>]*>Injuries\s*-\s*WEEK\s*(\d+)</h2>", re.I)
# the week picker is a <select> of <option value="/injuries/league/2026/regN">WEEK N</option>;
# an option is a route, not a publication, so the selected one is the only evidence of what printed
TAB_RE = re.compile(r'<option[^>]*value="[^"]*/injuries/league/(\d{4})/reg(\d+)"([^>]*)>', re.I)
SEL_RE = re.compile(r'reg(\d+)"[^>]*\s+selected', re.I)


def _text(cell: str) -> str:
    t = re.sub(r"<[^>]+>", "", cell)
    return html_mod.unescape(t).strip()


def parse(doc: str):
    """-> (rows, week_printed, tabs, selected_week).

    rows: list of dicts with club_name, slug, player, position, injury, practice_status, game_status.
    """
    rows = []
    pos = 0
    while True:
        head = CLUB_HEAD.search(doc, pos)
        tbl = TABLE_RE.search(doc, pos)
        if not tbl:
            break
        club = ""
        if head and head.start() < tbl.start():
            club = _text(head.group(1))
            pos = tbl.end()
        else:
            pos = tbl.end()
        for tr in TR_RE.findall(tbl.group(1)):
            tds = TD_RE.findall(tr)
            if len(tds) < 5:
                continue
            slug = ""
            m = A_HREF.search(tds[0])
            if m:
                # last path segment: the published table stores the full player-page URL
                slug = m.group(1).strip("/").split("/")[-1]
            player = _text(tds[0])
            if not player or player.lower() == "player":
                continue
            rows.append(dict(club_name=club, slug=slug, player=player,
                             position=_text(tds[1]), injury=_text(tds[2]),
                             practice_status=_text(tds[3]), game_status=_text(tds[4])))
    wk = ROW_COUNT_RE.search(doc)
    tabs = {int(m.group(2)) for m in TAB_RE.finditer(doc)}
    opts = {int(m.group(2)): bool(re.search(r"\bselected\b", m.group(3))) for m in TAB_RE.finditer(doc)}
    sel = SEL_RE.search(doc)
    return (rows, (int(wk.group(1)) if wk else None), tabs,
            (int(sel.group(1)) if sel else None), opts)


