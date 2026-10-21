"""TVBS 的 meta 發布時間是真正的 UTC，送進後端前要換成台灣時間。"""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import base
from sources import tvbs

PAGE = '''<html><head>
<meta property="article:published_time" content="2026-10-18T02:14:25.000Z">
<script type="application/ld+json">{"datePublished":"2026-10-18T02:14:25.000Z"}</script>
</head><body>
<h1 class="title">台中12歲男童墜樓</h1>
<div class="author">記者 發佈時間：2026.10.18 10:14</div>
<div class="article-editor-content"><p>晚間突然傳出巨響。</p></div>
</body></html>'''


class TvbsPublishedAt(unittest.TestCase):
    def test_utc_meta_time_becomes_taipei_time(self):
        session = Mock(spec=requests.Session)
        session.headers = {}
        with patch.object(base, 'get_page', return_value=SimpleNamespace(text=PAGE)):
            article = tvbs.scrape_article(session, 'https://news.tvbs.com.tw/local/4037554')
        # 頁面「發佈時間 10:14」＝meta 02:14Z；舊版取牆上時間會變成 02:14
        self.assertEqual(article['publishedAt'], '2026-10-18 10:14:25')

    def test_utc_time_after_midnight_moves_to_next_taipei_day(self):
        self.assertEqual(base.parse_datetime('2026-10-18T17:30:00Z', respect_timezone=True),
                         '2026-10-19 01:30:00')

    def test_wall_time_without_timezone_is_kept(self):
        self.assertEqual(base.parse_datetime('2026.10.18 10:14', respect_timezone=True),
                         '2026-10-18 10:14:00')

    def test_other_sources_still_ignore_timezone_labels(self):
        # 三立的 meta 標 +00:00 但實際是台灣時間，預設行為不能變
        self.assertEqual(base.parse_datetime('2026-10-18T10:14:25+00:00'), '2026-10-18 10:14:25')


if __name__ == '__main__':
    unittest.main()
