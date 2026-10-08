import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import base
from sources import ftv


class FakeApiSession:
    """只認得 existing 裡的 ID，其餘回「無資料」，並記下查過哪些 ID。"""

    def __init__(self, existing):
        self.existing = set(existing)
        self.requested = []

    def get(self, url, params=None, headers=None, timeout=None):
        article_id = params['id']
        self.requested.append(article_id)
        if article_id in self.existing:
            body = {'Status': 'Success', 'ITEM': [{'Title': f'立法院審查 {article_id}', 'Description': '立委質詢行政院長。'}]}
        else:
            body = {'Status': 'Fail', 'Desc': '無資料'}
        return type('Resp', (), {'encoding': None, 'json': lambda self: body})()


class FtvFallbackTests(unittest.TestCase):
    def setUp(self):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(base, 'SCRAPER_TARGET_DATE', '2026-10-08'))
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        ftv.URL_CATEGORY_MAP.clear()
        ftv.FALLBACK_ARTICLE_CACHE.clear()

    def test_months_ten_to_twelve_use_a_letter_in_the_article_id(self):
        from datetime import date
        self.assertEqual(ftv._article_id_prefix(date(2026, 9, 4)), '2026904')
        self.assertEqual(ftv._article_id_prefix(date(2026, 10, 8)), '2026A08')
        self.assertEqual(ftv._article_id_prefix(date(2026, 12, 31)), '2026C31')

    def test_published_date_is_read_from_letter_month_ids(self):
        self.assertTrue(ftv._published_at_from_article_id('2026A07W0400').startswith('2026-10-07 '))
        self.assertTrue(ftv._published_at_from_article_id('2025B15W0001').startswith('2025-11-15 '))
        self.assertTrue(ftv._published_at_from_article_id('2026904W0748').startswith('2026-09-04 '))
        self.assertIsNone(ftv._published_at_from_article_id('20261008W0001'))

    def test_scan_reaches_late_day_ids_across_gaps_and_stops_after_missing_run(self):
        existing = [f'2026A08W{n:04d}' for n in (1, 2, 14, 400, 410, 730)]
        existing += [f'2026A08W{n:04d}' for n in range(15, 400)]
        existing += [f'2026A08W{n:04d}' for n in range(411, 730)]
        session = FakeApiSession(existing)

        urls = ftv._fetch_fallback_urls_from_api(session)

        self.assertIn(f'{ftv.BASE_URL}/news/detail/2026A08W0730', urls)
        self.assertEqual(len(urls), len(set(existing)))
        web_requests = [i for i in session.requested if 'W' in i]
        self.assertEqual(web_requests[-1], f'2026A08W{730 + ftv.MAX_CONSECUTIVE_MISSING_IDS:04d}')

    def test_scan_gives_up_quickly_when_the_day_has_no_articles_yet(self):
        session = FakeApiSession([])

        self.assertEqual(ftv._fetch_fallback_urls_from_api(session), [])
        self.assertEqual(len(session.requested), 3 * ftv.MAX_CONSECUTIVE_MISSING_IDS)


if __name__ == '__main__':
    unittest.main()
