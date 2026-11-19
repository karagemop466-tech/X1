#!/usr/bin/env python3
"""Validate the outcome corpus and render a public, aggregate-only audit page."""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from build_results_feed import parse_week, norm  # noqa: E402

PAGE = ROOT / 'pages/evaluation.html'
OPS = 'https://operations.nfl.com/calendar-events/nfl-schedule/making-the-schedule'
NFL = 'https://www.nfl.com'
GAME = NFL + '/games/'
ROLES = ('train', 'validation', 'development_only', 'final_holdout_candidate')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def json_file(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def transcription_path(week):
    return f'data/results/raw/official_results_2026_week{week:02d}.psv'


def official_schedule(week):
    return f'{NFL}/schedules/2026/by-week/week-{week}'


def transcribed_week(week, evidence_date):
    with (ROOT / transcription_path(week)).open(encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f, delimiter='|'):
            expected_status = 'FINAL_TIE' if row['away_score'] == row['home_score'] else 'FINAL'
            require(row['week'] == str(week) and row['status'] == expected_status
                    and row['schedule_url'] == official_schedule(week) and row['retrieved'] == evidence_date,
                    f"unverified transcribed row: {row['game_url']}")
            yield dict(row, date_iso=row['game_date'], away_team=row['away'], home_team=row['home'])


def season_roles(windows):
    require(set(windows) == set(ROLES), 'unexpected or missing season roles')
    ordered = []
    for role in ROLES:
        years = windows[role]
        require(isinstance(years, list) and years and all(type(year) is int for year in years),
                f'{role}: empty or invalid seasons')
        ordered.extend(years)
    require(ordered == list(range(ordered[0], ordered[-1] + 1)),
            'season ranges must be strictly chronological, contiguous and disjoint')
    return {year: role for role in ROLES for year in windows[role]}


def load_protocol():
    paths = {'evaluation/protocol.json', *(f'data/results/raw/week_{w:02d}.md' for w in range(1, 10)),
             *(transcription_path(w) for w in range(1, 10))}
    lock = json_file('evaluation/evidence-lock.json')
    require(set(lock) == paths, 'evidence lock must cover the full frozen capture window')
    for path, digest in lock.items():
        require(sha256((ROOT / path).read_bytes()).hexdigest() == digest, f'frozen bytes changed: {path}')
    rule = json_file('evaluation/protocol.json')
    roles = season_roles(rule['seasons'])
    window = rule['corpus']
    require(roles.get(window['season']) == 'development_only', 'outcome corpus must stay in development')
    require(window['first_week'] == 1 and window['last_week'] == len(window['expected_week_counts']) == 9,
            'unexpected corpus window')
    require(window['leaderboard_eligible'] is False and rule['holdout_state'] == 'unregistered',
            'this audit cannot activate a strategy or leaderboard')
    return rule


def canonical(rows, weeks):
    """Compare every game by slug (feed team abbreviations can differ by alias)."""
    games = {}
    for row in rows:
        week = int(row['week'])
        if week not in weeks:
            continue
        url = row['game_url']
        require(re.fullmatch(re.escape(GAME) + rf'[a-z0-9-]+-at-[a-z0-9-]+-2026-reg-{week}', url),
                f'week {week}: invalid game-specific official link: {url}')
        require(url not in games, f'duplicate game link: {url}')
        require(row['away_score'].isdigit() and row['home_score'].isdigit(), f'not a final: {url}')
        require(row['away_team'] != row['home_team'], f'home and away clubs identical: {url}')
        games[url] = (week, row['date_iso'], norm(row['away_team']), norm(row['home_team']),
                      row['away_score'], row['home_score'])
    return games


def compare(expected, actual, label):
    different = sorted(url for url in expected.keys() | actual.keys() if expected.get(url) != actual.get(url))
    require(not different, f'{label}: {len(different)} missing, extra or different game rows; first: {different[:1]}')


def load_corpus(rule):
    window = rule['corpus']
    week_counts = dict(enumerate(window['expected_week_counts'], start=window['first_week']))
    rows = []
    for week, count in week_counts.items():
        batch = parse_week(week)  # parse the pinned official NFL schedule anchors
        require(len(batch) == count, f'week {week}: expected {count} final anchors, got {len(batch)}')
        require(all(row['retrieved_at'] == window['evidence_date'] for row in batch), 'capture date differs')
        rows.extend(batch)
    games = canonical(rows, week_counts)
    transcribed = [row for week in week_counts for row in transcribed_week(week, window['evidence_date'])]
    compare(games, canonical(transcribed, week_counts), 'official schedule transcription')
    return sorted(rows, key=lambda row: (int(row['week']), row['date_iso'], row['game_url']))


def link(url, label='NFL source'):
    return f'<a href="{escape(url, quote=True)}">{escape(label)}</a>'


def table(headers, lines):
    head = ''.join(f'<th scope="col">{escape(h)}</th>' for h in headers)
    body = '\n'.join('<tr>' + ''.join(f'<td>{v}</td>' for v in cells) + '</tr>' for cells in lines)
    return f'<div class="tablewrap" tabindex="0"><table class="wide" data-table><thead><tr>{head}</tr></thead><tbody>\n{body}\n</tbody></table></div>'


def render(rule, corpus):
    src = NFL + '/standings/league/{}/REG'
    weekly = [(str(w), str(sum(int(g['week']) == w for g in corpus)),
               link(official_schedule(w), f'Official Week {w} schedule'))
              for w in range(1, 10)]
    split_details = (
        ('Train', 'Historical development only. Official game-result coverage has not been verified for this window.', src.format(2019)),
        ('Validation', 'Retrospective model selection only. Never a clean prospective test: these seasons already appear in repo backtests.', src.format(2025)),
        ('Development only', 'The locked outcome corpus belongs here. Do not relabel games already played as prospective.', src.format(2026)),
        ('Final holdout candidate', 'Not registered. No evaluation until the strategy is frozen before the first eligible kickoff.', OPS),
    )
    splits = []
    for role, (label, state, url) in zip(ROLES, split_details):
        years = rule['seasons'][role]
        window = f'{years[0]}–{years[-1]}' if len(years) > 1 else str(years[0])
        splits.append((label, window, state, link(url, 'Official NFL reference')))
    questions = (
        ('Is the 136-game log a clean holdout?', 'No. It consists of finals already known at lock time.', 'Use as a retrospective outcomes-only corpus. Freeze a future strategy before it can see any holdout outcomes.', src.format(2026)),
        ('Can older mirror scores be promoted?', 'No. An official standings link is a cross-check, not verification of each game.', 'Require 100% per-game official finals for the frozen historical game set. Keep all unverified values out of model scoring.', src.format(2025)),
        ('Can outcomes establish an edge against the market?', 'No. Outcomes contain no qualifying price or timestamped market quote.', 'Keep market, residual and CLV blank here. Require two permitted, timestamped snapshots (open and close) for each priced market, plus settlement rules, before running a market evaluation.', OPS),
        ('Can this corpus measure the injury effect?', 'No. Final scores do not establish who was expected, active or starting before kickoff.', 'Join permitted availability snapshots by game and cutoff; run paired with/without models on identical eligible games and report game-cluster uncertainty.', NFL + '/injuries/league/2026/reg9'),
    )
    return f'''<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Evaluation readiness | NFL research</title><link rel="stylesheet" href="../assets/site.css">
<style>.tablewrap{{overflow:auto}} main{{max-width:1050px;margin:auto}}</style></head>
<body><main>
<header class="pagetitle"><nav aria-label="Related pages"><a href="../index.html">Dashboard</a> · <a href="readiness.html">Decision readiness</a> · <a href="flagged.html">Flagged for review</a></nav>
<p class="eyebrow">{rule['id']} · protocol defined {rule['defined_on']}</p>
<h1>Evaluation readiness</h1><p>What the outcome log can support, and what must be in place before a strategy can be ranked.</p></header>
<section class="content" aria-labelledby="summary"><h2 id="summary">Executive summary</h2>
<div class="note"><b>{len(corpus)} official finals, zero leaderboard-eligible results from this audit.</b> The 136-game reference is reproducible as the first nine weeks of 2026, not a new feed or a prospective sample. This page publishes coverage only: no picks, model scores, prices or ROI.</div>
<h2>Locked outcome corpus</h2>
<p>For every game, week, date, teams, score and official game URL agree between the retained NFL schedule anchors and the structured official schedule transcription. Source snapshot: {rule['corpus']['evidence_date']}. The later Week 10 finals are outside the lock; the shadow baseline uses a different window.</p>
{table(('2026 week', 'Finals in corpus', 'Official evidence'), weekly)}
<h2>Chronological split</h2>
<p>These are protocol assignments, not NFL claims. Historical verification gaps are not filled by mirror rows. The holdout has no registered strategy and no reported result.</p>
{table(('Use', 'NFL seasons', 'Status', 'Official reference'), splits)}
<h2 id="review">Flagged for review: questions and suggested next steps</h2>
{table(('Question', 'What we know', 'What clears the gap', 'Official reference'), [(escape(q), escape(a), escape(s), link(u, 'NFL reference')) for q, a, s, u in questions])}
<p><b>Registration gate:</b> {escape(rule['holdout_gate'])}</p>
</section></main></body></html>
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-page', action='store_true', help='update derived HTML, never the protocol or lock')
    args = parser.parse_args()
    try:
        rule = load_protocol()
        corpus = load_corpus(rule)
        page = render(rule, corpus)
        if args.write_page:
            PAGE.write_text(page, encoding='utf-8')
        require(PAGE.read_text(encoding='utf-8') == page, 'evaluation page stale; run with --write-page')
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f'evaluation check failed: {exc}\n')
    print(f'{rule["id"]}: {len(corpus)} games match the official schedule transcriptions; split and public page validated')


if __name__ == '__main__':
    main()
