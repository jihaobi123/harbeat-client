"""Corpus independence and frozen V3 assets are part of the experiment contract."""
import copy
import unittest

from scripts.build_vocal_overlap_corpus import ordinary_windows, select_new, assert_original_preserved, preview_duration


def row(tid, bpm=100, coverage=.5, sha=None, eligible=True, title=None):
    return {'track_id': tid, 'sha': sha or tid, 'bpm': bpm, 'vocalCoverage': coverage,
            'style': [{'style': 'Trap'}], 'eligible': eligible, 'title': title or tid}


class CorpusTests(unittest.TestCase):
    def test_selection_excludes_old_sources_and_is_order_independent(self):
        old = [row('old')]
        rows = [row('duplicate', sha='old'), row('new1', bpm=80),
                row('new2', bpm=140), row('bad', eligible=False)]
        self.assertEqual([x['track_id'] for x in select_new(rows, old, 12)], ['new2', 'new1'])
        self.assertEqual(select_new(rows, old, 12), select_new(list(reversed(rows)), old, 12))

    def test_selection_does_not_depend_on_experiment_results(self):
        rows = [row('a', bpm=85), row('b', bpm=135)]
        result = select_new(rows, [row('old')], 1)
        mutated = copy.deepcopy(rows)
        for item in mutated:
            item['experimentWins'] = 1000 if item['track_id'] != result[0]['track_id'] else 0
        self.assertEqual(select_new(mutated, [row('old')], 1)[0]['track_id'], result[0]['track_id'])

    def test_original_windows_remain_ordinary_two_and_four_bars(self):
        track = {'bars': list(range(0, 120, 2)), 'duration': 110,
                 'sections': [{'start': 0, 'end': 20, 'label': 'intro'},
                              {'start': 20, 'end': 100, 'label': 'verse'}]}
        wins = ordinary_windows(track)
        self.assertEqual([(w['start'], w['end'], w['bars']) for w in wins],
                         [(0, 4, 2), (0, 8, 4), (20, 24, 2), (20, 28, 4)])

    def test_duration_rounding_does_not_disguise_missing_evidence(self):
        self.assertEqual(preview_duration(141370, 141.36986394557823), 141.36986394557823)
        self.assertEqual(preview_duration(141370, 140), 141.370)
        self.assertEqual(preview_duration(200000, 200), 150)

    def test_original_projection_allows_only_new_a_variants(self):
        old = {'id': 'old', 'native': {'sha256': 'native'},
               'windows': [{'id': 'w', 'start': 0, 'variants': {'old2': {'sha256': 'old'}}}]}
        expanded = copy.deepcopy(old)
        expanded['windows'][0]['variants']['new'] = {'sha256': 'new'}
        assert_original_preserved([old], [expanded], {'new'})
        expanded['windows'][0]['variants']['old2']['sha256'] = 'changed'
        with self.assertRaises(AssertionError):
            assert_original_preserved([old], [expanded], {'new'})


if __name__ == '__main__':
    unittest.main()
