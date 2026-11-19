"""Render the dated integration review. Only aggregate report movement is published."""
import csv
import gzip
import hashlib
import json
import sys
from pathlib import Path
from html import escape
from build_console import table, page, src_link
from verify_injuries_from_raw import parse

ROOT = Path(__file__).resolve().parents[1]
CUTOFF = '2026-11-19T01:53:42Z'


def grid(headers, rows, key):
    return table([(h, False) for h in headers.split('|')], rows, key, filter_col=0)


def report():
    ledger = ROOT / 'data/ledger/injuries'
    previous = {}
    output = []
    for line in (ledger / 'ledger.jsonl').read_text().splitlines():
        entry = json.loads(line)
        stamp = entry['captured_at_utc']
        if stamp > CUTOFF:
            continue
        blob = (ledger / entry['file']).read_bytes()
        raw = gzip.decompress(blob)
        assert hashlib.sha256(raw).hexdigest() == entry['sha256']
        assert hashlib.sha256(blob).hexdigest() == entry['gzip_sha256']
        rows, week, _, selected, _ = parse(raw.decode())
        assert week == selected == entry['week'] and rows
        values = {(r['club_name'], r['slug']): (r['practice_status'], r['game_status']) for r in rows}
        assert len(values) == len(rows) and all(all(k) for k in values)
        key = (entry['season'], week)
        old = previous.get(key)
        counts = [''] * 3 if old is None else list(map(str, (len(values.keys()-old.keys()), len(old.keys()-values.keys()), sum(values[k]!=old[k] for k in values.keys() & old.keys()))))
        output.append([stamp, str(week), 'Anchor' if old is None else 'Comparable read', *counts, src_link(f'https://www.nfl.com/injuries/league/{key[0]}/reg{week}', 'NFL report')])
        previous[key] = values
    return output


def render():
    venues = list(csv.DictReader((ROOT/'data/decision_review/venues.tsv').open(), delimiter='\t'))
    assert len({v['game_url'] for v in venues}) == len(venues) == 27
    strategies = list(csv.DictReader((ROOT/'data/mind_change/register.csv').open()))
    body = '<h2>Executive decision: remain in shadow</h2><p>Venue and injury-report movement are observable inputs, not evidence that a strategy beats the market. No entry is promoted or rewarded by this review.</p>'
    body += '<h2>Availability movement</h2><p>Compared with the preceding retained read of the same season and week. A blank is an anchor, not zero. A row entering or leaving a report does not establish participation. Changed counts only common players whose practice or game designation changed.</p>' + grid('Captured (UTC)|Week|Comparison|Added|Removed|Changed|Official source',report(),'deltas')
    body += '<h2>Fixture venues</h2><p>Game Centre reads from 18 November. Roof status and playing surface are unverified; no weather or personnel adjustment is applied.</p>' + grid('Fixture|Week|Venue as printed|Location|Official source',[[escape(v[k]) for k in ('slug','week','stadium','location')] + [src_link(v['game_url'],'Game Centre')] for v in venues],'venue')
    body += '<h2>What would change our mind?</h2><p>Project-defined diagnostic tests, not a leaderboard. The NFL supplies results, not these thresholds. A retrospective test cannot qualify an entry for a reward.</p>' + grid('Strategy|Consider adopting if|Consider abandoning if|Diagnostic state|Result source',[[escape(s[k]) for k in ('entry_id','adopt_if','abandon_if','state')]+[src_link('https://www.nfl.com/schedules/','NFL outcomes')] for s in strategies],'mind')
    # A historical page must not acquire a new verification clock at each render.
    import build_console
    build_console.AS_OF = CUTOFF
    return page('Evidence review', 'Governance', body, 'Dated evidence through 19 November 2026 · Weeks 10–11')


if __name__ == '__main__':
    path = ROOT / 'console/evidence-review.html'
    html = render()
    if '--check' in sys.argv:
        # Navigation tags count later captures; compare the dated analysis, not the live shell.
        assert html.split('<main>')[1] == path.read_text().split('<main>')[1], 'stale evidence review'
    else:
        path.write_text(html)
