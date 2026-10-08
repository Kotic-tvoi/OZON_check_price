"""Parallel workers: ordered output, two separate halves, isolated retries."""
from pathlib import Path
import sys
import threading
import unittest
from collections import Counter
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from core import PriceResult, validate_request
from scraper import scan_items, scan_pvz_group


def rows(items, status='ok'):
    return [PriceResult(index=x.index, article=x.article, pvz_url=x.pvz_url,
                        status=status, price=x.index + 100 if status == 'ok' else None)
            for x in items]


class TestTwoChromeSessions(unittest.TestCase):
    def test_two_halves_truly_overlap_and_merge_in_original_order(self):
        inputs = validate_request({'articles': [str(i) for i in range(1, 6)]})
        barrier = threading.Barrier(2)
        halves = []
        lock = threading.Lock()

        def fake_group(pvz_url, items, headed):
            with lock:
                halves.append([r.index for r in items])
            barrier.wait(timeout=2)  # Fails if the groups execute sequentially.
            return list(reversed(rows(items)))  # Merge must restore source order.

        with patch('scraper.scan_pvz_group', side_effect=fake_group):
            result = scan_items(inputs)
        self.assertCountEqual(halves, [[0, 1, 2], [3, 4]])
        self.assertEqual([r.index for r in result], [0, 1, 2, 3, 4])
        self.assertEqual([r.price for r in result], [100, 101, 102, 103, 104])

    def test_one_half_retries_without_restarting_the_other(self):
        inputs = validate_request({'articles': [str(i) for i in range(1, 7)]})
        calls = Counter()
        lock = threading.Lock()

        def one_attempt(pvz_url, items, headed=False):
            key = items[0].index
            with lock:
                calls[key] += 1
                count = calls[key]
            if key == 3 and count == 1:
                return rows(items, status='blocked')
            return rows(items)

        with patch('scraper._scan_pvz_group_once', side_effect=one_attempt):
            output = scan_items(inputs)
        self.assertEqual(dict(calls), {0: 1, 3: 2})
        self.assertEqual([r.price for r in output], [100, 101, 102, 103, 104, 105])
        self.assertTrue(all(r.status == 'ok' for r in output))

    def test_permanent_failure_keeps_other_half_and_returns_status(self):
        inputs = validate_request({'articles': ['1','2','3','4']})
        calls = Counter()

        def one_attempt(pvz_url, items, headed=False):
            key = items[0].index
            calls[key] += 1
            return rows(items, status='blocked') if key == 2 else rows(items)

        with patch('scraper._scan_pvz_group_once', side_effect=one_attempt):
            output = scan_items(inputs)
        self.assertEqual(dict(calls), {0: 1, 2: 5})
        self.assertEqual([r.status for r in output], ['ok', 'ok', 'blocked', 'blocked'])
        self.assertEqual([r.price for r in output], [100, 101, None, None])


if __name__ == '__main__':
    unittest.main()