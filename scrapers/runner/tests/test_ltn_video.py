import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import base
from sources import ltn


class LtnVideoTests(unittest.TestCase):
    def parse(self, content):
        html = '<div class="whitecon" itemprop="articleBody"><h1>新聞標題</h1><div class="text">' + content + '</div></div>'
        with patch.object(base, 'get_page', return_value=SimpleNamespace(text=html)):
            return ltn.scrape_article(SimpleNamespace(), 'https://news.ltn.com.tw/news/politics/breakingnews/1')

    def test_video_only_entry_is_an_intentional_exclusion(self):
        article = self.parse('<p><iframe src="https://www.youtube.com/embed/editorial-video"></iframe></p>')
        self.assertIsInstance(article, base.SkippedArticle)
        self.assertEqual(article.reason, 'video-only')

    def test_article_with_video_and_text_keeps_its_content(self):
        article = self.parse('<iframe src="https://www.youtube.com/embed/editorial-video"></iframe><p>這是新聞的文字內文。</p>')
        self.assertEqual(article['cleanText'], '這是新聞的文字內文。')

    def test_empty_ordinary_article_remains_an_error_for_runner_validation(self):
        article = self.parse('')
        self.assertNotIsInstance(article, base.SkippedArticle)
        self.assertEqual(article['cleanText'], '')

    def test_ad_frame_does_not_hide_a_missing_article_body(self):
        article = self.parse('<iframe src="https://ads.example/embed/advertisement"></iframe>')
        self.assertNotIsInstance(article, base.SkippedArticle)
        self.assertEqual(article['cleanText'], '')
