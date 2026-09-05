"""Offline regressions for source filtering, upstream errors and URL selection."""
import contextlib
import io
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import base
import main
from sources import cti, cts, storm


def response(status=200, text='', headers=None):
    return SimpleNamespace(status_code=status, text=text, headers=headers or {}, encoding=None,
                           json=lambda: json.loads(text))


class RunnerRegressions(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        for name, value in [('SKIP_URL_CACHE', {}), ('SCRAPER_TARGET_DATE', '2026-09-05'),
                            ('SCRAPER_LOOKBACK_DAYS', 1), ('SCRAPER_ONLY_TODAY', True)]:
            self.stack.enter_context(patch.object(base, name, value))
        self.stack.enter_context(patch('time.sleep'))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))

    def run_urls(self, source, session, urls):
        with patch.object(source, 'get_list_urls', return_value=urls), \
                patch.object(base, 'get_new_urls', side_effect=lambda _, __, u: u), \
                patch.object(base, 'ingest_article', return_value=True):
            return base.run_source(session, source.SOURCE_CODE, source)

    def test_all_vip_and_commentary_are_successful_exclusions(self):
        session = Mock(spec=requests.Session)
        session.get.side_effect = [response(text='<meta property="article:section" content="VIP">'),
                                   response(text='<meta property="article:section" content="評論">')]
        urls = ['https://www.storm.mg/article/1', 'https://www.storm.mg/article/2']
        stats = self.run_urls(storm, session, urls)
        self.assertEqual(main.evaluate_run(stats)[0], 200)
        self.assertEqual(stats['failed'], 0)
        self.assertEqual(stats['skipped_filtered'], 2)
        session.get.reset_mock()
        again = self.run_urls(storm, session, urls)
        self.assertEqual(again['skipped_cached'], 2)
        session.get.assert_not_called()

    def test_gone_articles_are_cached_exclusions(self):
        session = Mock(spec=requests.Session)
        session.get.side_effect = [response(410), response(404)]
        urls = ['https://ctinews.com/news/items/Gone1', 'https://ctinews.com/news/items/Gone2']
        stats = self.run_urls(cti, session, urls)
        self.assertEqual(main.evaluate_run(stats)[0], 200)
        self.assertEqual(stats['failed'], 0)
        self.assertEqual(stats['skipped_unavailable'], 2)

    def test_rate_limit_stops_batch_and_defers_remaining_urls(self):
        session = Mock(spec=requests.Session)
        session.get.return_value = response(429, headers={'Retry-After': '120'})
        urls = ['https://ctinews.com/news/items/Limited1', 'https://ctinews.com/news/items/Limited2']
        stats = self.run_urls(cti, session, urls)
        self.assertEqual(session.get.call_count, 1)
        self.assertEqual(stats['deferred'], 2)
        self.assertEqual(stats['failed'], 0)
        self.assertEqual(stats['retry_after_seconds'], 120)
        self.assertNotIn(urls[0], base.SKIP_URL_CACHE)

    def test_real_parse_errors_still_fail_even_with_date_exclusions(self):
        session = Mock(spec=requests.Session)
        source = SimpleNamespace(SOURCE_CODE='TEST', get_list_urls=Mock(), scrape_article=Mock())
        source.scrape_article.side_effect = [
            {'title': 'Old news', 'cleanText': 'Body.', 'publishedAt': '2026-09-01 10:00:00'},
            None, None,
        ]
        stats = self.run_urls(source, session, ['old', 'broken1', 'broken2'])
        self.assertEqual(stats['failed'], 2)
        self.assertEqual(main.evaluate_run(stats)[0], 500)

    def test_backend_auth_failure_is_not_an_empty_new_url_list(self):
        session = Mock(spec=requests.Session)
        session.post.return_value = response(401)
        with patch.object(base, 'API_KEY', 'test-only'), self.assertRaises(RuntimeError):
            base.get_new_urls(session, 'CTI', ['https://example.invalid/article'])

    def test_cti_uses_article_id_and_recent_dates_not_json_ld_slot_id(self):
        payload = [
            {'id': 1, 'news_id': 2, 'release_at': 3}, 'SlotWrong', 'ActualNews', '2026-09-05 10:00:00',
            {'id': 5, 'news_id': 6, 'release_at': 7}, 'OldSlot', 'OldNews', '2026-08-01 10:00:00',
        ]
        html = '<script type="application/ld+json">{"url":"https://ctinews.com/news/items/SlotWrong"}</script>'
        html += '<script id="__NUXT_DATA__" type="application/json">' + json.dumps(payload) + '</script>'
        html += '<a class="news-link" href="/news/items/ActualNews">News</a>'
        html += '<a class="news-link" href="/news/items/OldNews">Old recommendation</a>'
        session = Mock(spec=requests.Session)
        session.get.return_value = response(text=html)
        with patch.object(cti, 'TOPIC_PAGES', ['/topic-test']):
            urls = cti.get_list_urls(session)
        self.assertEqual(urls, ['https://ctinews.com/news/items/ActualNews'])
        self.assertEqual(session.get.call_count, 1)

    def test_cti_all_old_items_do_not_trigger_homepage_fallback(self):
        payload = [{'news_id': 1, 'release_at': 2}, 'OldNews', '2026-08-01 10:00:00']
        html = '<script id="__NUXT_DATA__" type="application/json">' + json.dumps(payload) + '</script>'
        session = Mock(spec=requests.Session)
        session.get.return_value = response(text=html)
        with patch.object(cti, 'TOPIC_PAGES', ['/topic-test']):
            self.assertEqual(cti.get_list_urls(session), [])
        self.assertEqual(session.get.call_count, 1)

    def test_http_adapter_does_not_repeat_a_rate_limited_request(self):
        calls = []

        class Limited(BaseHTTPRequestHandler):
            def do_GET(self):
                calls.append(self.path)
                self.send_response(429)
                self.send_header('Retry-After', '0')
                self.end_headers()

            def log_message(self, *_):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Limited)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with base.create_session() as session:
                result = session.get(f'http://127.0.0.1:{server.server_port}/limited', timeout=3)
            self.assertEqual(result.status_code, 429)
            self.assertEqual(len(calls), 1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_cts_parses_official_api_article_without_changing_canonical_url(self):
        article = {'id': '202609053075329', 'title': '測試新聞', 'category': '政治',
                   'publishTime': '2026-09-05 10:55:00',
                   'link': '/cts/politics/202609/202609053075329.html',
                   'content': '<p>第一段。</p><p>第二段。</p><script>advert()</script>',
                   'coverImage': {'imageUrl': 'https://www.cts.com.tw/photo.jpg'}}
        session = Mock(spec=requests.Session)
        session.get.return_value = response(text=json.dumps({'status': True, 'data': {'article': article}}))
        url = 'https://news.cts.com.tw' + article['link']
        result = cts.scrape_article(session, url)
        self.assertEqual(result['title'], '測試新聞')
        self.assertEqual(result['url'], url)
        self.assertEqual(result['publishedAt'], '2026-09-05 10:55:00')
        self.assertEqual(result['cleanText'], '第一段。\n第二段。')
        self.assertEqual(result['imageUrl'], 'https://www.cts.com.tw/photo.jpg')

    def test_cts_list_filters_category_and_old_items_before_fetching_articles(self):
        articles = [
            {'link': '/cts/politics/202609/202609053075329.html', 'category': '政治',
             'title': '今日政治', 'publishTime': '2026-09-05 10:55:00'},
            {'link': '/cts/sports/202609/202609053075328.html', 'category': '運動',
             'title': '其他分類', 'publishTime': '2026-09-05 10:55:00'},
            {'link': '/cts/politics/202608/202608013000001.html', 'category': '政治',
             'title': '舊聞', 'publishTime': '2026-08-01 10:55:00'},
        ]
        session = Mock(spec=requests.Session)
        session.get.return_value = response(text=json.dumps({'status': True, 'data': {
            'articles': articles, 'pagination': {'page': 1, 'totalPages': 1}}}))
        urls = cts._fetch_category_urls(session, 'politics', 'politics/list', '政治')
        self.assertEqual(urls, ['https://news.cts.com.tw/cts/politics/202609/202609053075329.html'])

    def test_cts_blocked_api_does_not_look_like_an_empty_list(self):
        session = Mock(spec=requests.Session)
        session.get.return_value = response(403, '<h1>Request blocked</h1>')
        with self.assertRaises(base.SourceFetchError):
            cts._fetch_category_urls(session, 'politics', 'politics/list', '政治')


if __name__ == '__main__':
    unittest.main()
