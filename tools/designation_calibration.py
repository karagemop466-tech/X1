"""Aggregate reviewed private NFL evidence. Never equate active with played."""
import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import datetime
from urllib.parse import urlsplit


LABELS = ('Questionable', 'Doubtful', 'Out')


def official(url):
    p = urlsplit(url)
    host = p.hostname or ''
    if p.scheme != 'https' or not (host == 'nfl.com' or host.endswith('.nfl.com')) or p.path in ('', '/'):
        raise ValueError('expected specific official NFL evidence URL')


def clock(text):
    t = datetime.fromisoformat(text.replace('Z', '+00:00'))
    if t.tzinfo is None:
        raise ValueError('timestamp needs UTC offset')
    return t


def interval(k, n):
    if not n:
        return None
    p, z = k / n, 1.959963984540054
    center = p + z*z/(2*n)
    radius = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n))
    return [max(0, (center-radius)/(1+z*z/n)), min(1, (center+radius)/(1+z*z/n))]


def evaluate(reports, outcomes):
    latest, observed, seen = {}, {}, set()
    for r in reports:
        key = identity(r)
        official(r['source'])
        t, kick = clock(r['captured_at']), clock(r['kickoff'])
        if t >= kick:
            continue
        label = r['designation']
        if label not in (*LABELS, '') or (key, t) in seen:
            raise ValueError('invalid designation or duplicate capture')
        seen.add((key, t))
        if key not in latest or t > latest[key][0]:
            latest[key] = t, label
    for r in outcomes:
        key = identity(r)
        official(r['source'])
        status = r['game_book_status']
        if key in observed or status not in ('played', 'active_dnp', 'inactive'):
            raise ValueError('ambiguous game book evidence')
        observed[key] = status
    counts = defaultdict(lambda: [0, 0, 0])
    for key, (_, label) in latest.items():
        if not label:
            continue
        c = counts[key[0], label]
        c[0] += 1
        c[1] += key in observed
        c[2] += observed.get(key) == 'played'
    return [dict(season=s, designation=l, reported=total, n=n, unmatched=total-n,
                 played=k, play_rate=k/n if n else None, wilson95=interval(k, n))
            for (s, l), (total, n, k) in sorted(counts.items())]


def identity(row):
    key = tuple(row[f].strip() for f in ('season', 'game_id', 'team_id', 'player_id'))
    if not all(key):
        raise ValueError('incomplete evidence key')
    return key


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reports', type=argparse.FileType('r'))
    parser.add_argument('outcomes', type=argparse.FileType('r'))
    args = parser.parse_args()
    print(json.dumps(evaluate(csv.DictReader(args.reports), csv.DictReader(args.outcomes)), indent=2))
