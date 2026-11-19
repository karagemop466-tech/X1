from copy import deepcopy
import unittest
from unittest.mock import patch

import build


class EvaluationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rule = build.load_protocol()
        cls.corpus = build.load_corpus(cls.rule)

    def test_locked_window_matches_both_feeds(self):
        self.assertEqual(len(self.corpus), 136)
        self.assertEqual({int(row['week']) for row in self.corpus}, set(range(1, 10)))
        self.assertEqual(len({row['game_url'] for row in self.corpus}), 136)
        self.assertFalse(self.rule['corpus']['leaderboard_eligible'])

    def test_splits_reject_overlap_and_gaps(self):
        for bad_years in ([2023, 2025], [2025], [2025, 2024]):
            windows = deepcopy(self.rule['seasons'])
            windows['validation'] = bad_years
            with self.subTest(years=bad_years), self.assertRaisesRegex(ValueError, 'chronological'):
                build.season_roles(windows)

    def test_reject_changed_hash(self):
        lock = build.json_file('evaluation/evidence-lock.json')
        lock['data/results/raw/week_01.md'] = '0' * 64
        with patch.object(build, 'json_file', return_value=lock), self.assertRaisesRegex(ValueError, 'frozen bytes'):
            build.load_protocol()

    def test_reject_duplicate_and_unofficial_source(self):
        row = self.corpus[0]
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            build.canonical([row, row], {1})
        invalid = dict(row, game_url=row['game_url'].replace('nfl.com', 'nfl.com.example'))
        with self.assertRaisesRegex(ValueError, 'official link'):
            build.canonical([invalid], {1})

    def test_reject_result_drift(self):
        row = self.corpus[0]
        original = build.canonical([row], {1})
        wrong_score = build.canonical([dict(row, home_score=str(int(row['home_score']) + 1))], {1})
        for replacement in ({}, wrong_score):
            with self.assertRaisesRegex(ValueError, 'different game rows'):
                build.compare(original, replacement, 'test feed')

    def test_no_individual_game_rows_in_public_html(self):
        page = build.render(self.rule, self.corpus)
        self.assertNotIn(build.GAME, page)
        self.assertNotIn('data/results/', page)
        self.assertEqual(page.count('Official Week '), 9)


if __name__ == '__main__':
    unittest.main()
