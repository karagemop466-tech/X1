"""Record KR-T1 once before kickoff; replay against pinned inputs without rewriting it."""
import argparse
import csv
import hashlib
import io
import json
import random
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean

from regimes import prior_finals

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / 'research/kickoff-regimes'
LEDGER = PUBLIC / 'week11.json'
BASE = '6f7df25375139f9f253a33f46191cb3007d8349f'
REGISTRATION = '5d1e59d66e1b450306934b94feff596dfcda9770'
PINS = {
    'data/results/verified_results_2026_r3.csv': 'd807853fff21a687f7bb270defc62a2fd3fe9d9b99a69b30c0b197ac92311161',
    'data/lab/escrow/week11_forecasts_2026-11-17.csv': '9050d41f36de779ef26cf3633235537b19b6bde7f594de70c377a9cf86ec453f',
}
RESULTS, ESCROW = PINS
CUTOFF = date(2026, 11, 19)


def pinned_rows(path):
    raw = (ROOT / path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != PINS[path]:
        raw = subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=ROOT)
        if hashlib.sha256(raw).hexdigest() != PINS[path]:
            raise ValueError(f'Input fingerprint mismatch: {path}')
    return list(csv.DictReader(io.StringIO(raw.decode())))


def history():
    games = prior_finals(pinned_rows(RESULTS), 2026, CUTOFF)
    if len(games) != 150 or any(int(g['week']) >= 11 for g in games):
        raise ValueError('Not the registered training window')
    return games


def club(s):
    return {'ARI': 'AZ', 'ARZ': 'AZ', 'LAR': 'LA'}.get(s, s)


def outcome(total, threshold):
    return 0 if total < threshold else 2 if total > threshold else 1


def distribution(counts, line):
    smooth = [counts[0] + .5, counts[1] + .5 if line.is_integer() else 0, counts[2] + .5]
    return [x / sum(smooth) for x in smooth]


def forecast(games, fixture):
    line = float(fixture['our_fair_line'])
    teams = {club(fixture['away']), club(fixture['home'])}
    counts, weighted = [0, 0, 0], [0, 0, 0]
    for g in games:
        k = outcome(int(g['home_score']) + int(g['away_score']), line)
        counts[k] += 1
        weighted[k] += 1 + bool(teams & {club(g['away_team']), club(g['home_team'])})
    return dict(game_id=fixture['game_id'], away=fixture['away'], home=fixture['home'],
                kickoff_utc=fixture['kickoff_utc'], official_game=fixture['official_fixture_url'],
                threshold=line, market_line=None, residual=None, n=len(games), counts=counts,
                weighted_counts=weighted, candidate=distribution(weighted, line),
                benchmark=distribution(counts, line))


def replay(stamp):
    if hashlib.sha256((PUBLIC / 'KR-T1.md').read_bytes()).hexdigest() != '402862dc2fce9c6ed73dfb19751ba5f75936c98911741d82f5ce22fc3d8ae950':
        raise ValueError('Registration changed')
    games = history()
    rows = [forecast(games, f) for f in pinned_rows(ESCROW) if f['market'] == 'total_A']
    rows.sort(key=lambda r: (r['kickoff_utc'], r['game_id']))
    dt = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
    if dt.date() != CUTOFF or dt >= datetime.fromisoformat(rows[0]['kickoff_utc'].replace('Z', '+00:00')):
        raise ValueError('Outside registered forecast window')
    if len(rows) != 13 or len({r['official_game'] for r in rows}) != 13:
        raise ValueError('Expected the complete Week 11 slate')
    return dict(trial='KR-T1', registered_commit=REGISTRATION, recorded_at_utc=stamp,
                input_sha256=PINS, input_commit=BASE, class_order=['under', 'push', 'over'],
                leaderboard_eligible=False, forecasts=rows)


def checked_record():
    saved = json.loads(LEDGER.read_text())
    if replay(saved['recorded_at_utc']) != saved:
        raise ValueError('Escrow does not reproduce')
    return saved


def evaluate(rows, finals):
    """Consume only the verified result-store schema, matching by official fixture URL."""
    pending = {r['official_game']: r for r in rows}
    losses = []
    seen = set()
    for f in finals:
        url = f['game_url']
        if url not in pending:
            continue
        r = pending[url]
        if (url in seen or f['source_url'] != 'https://www.nfl.com/schedules/2026/by-week/week-11'
                or (club(f['away_team']), club(f['home_team'])) != (club(r['away']), club(r['home']))
                or not all(f[k].isdigit() for k in ('away_score', 'home_score'))):
            raise ValueError(f'Invalid or duplicated final: {url}')
        seen.add(url)
        k = outcome(int(f['away_score']) + int(f['home_score']), r['threshold'])
        losses.append([sum((p - (j == k))**2 for j, p in enumerate(r[model]))
                       for model in ('benchmark', 'candidate')])
    if len(losses) != len(rows):
        return {'status': 'pending', 'official_finals': len(losses), 'required': len(rows)}
    differences = [a - b for a, b in losses]
    rng = random.Random(20261119)
    draws = sorted(mean(rng.choices(differences, k=len(rows))) for _ in range(10000))
    return dict(status='paper only', n=len(rows), benchmark_brier=mean(a for a,b in losses),
                candidate_brier=mean(b for a,b in losses), improvement=mean(differences),
                interval_95=[draws[249], draws[9749]])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['record', 'check', 'score'])
    action = parser.parse_args().action
    if action == 'record':
        stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        record = replay(stamp)
        with LEDGER.open('x') as out:
            out.write(json.dumps(record, indent=2) + '\n')
    else:
        record = checked_record()
        if action == 'score':
            with (ROOT / RESULTS).open() as f:
                print(json.dumps(evaluate(record['forecasts'], csv.DictReader(f)), indent=2))
        else:
            print('All 13 frozen vectors and their inputs reproduce.')
