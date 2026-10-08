"""內文的行內連結與粗體不能把一段切成好幾行（UDN 人名標籤、CNA 電頭記者名）。"""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import base
from sources import udn

UDN_ARTICLE = """
<html><body>
<h1 class="article-content__title">影／白委爆徐佳青讓兒子藉攝影官名義出訪</h1>
<section class="article-content__editor ">
<p><div class="video-container"><iframe src="https://video.udn.com/embed/news/1330021"></iframe></div></p>
<p>
台灣民眾黨團日前揭露僑委會委員長<a href='/search/tagging/2/徐佳青' class='tag'><strong>徐佳青</strong></a>違法攜子登上軍事管制區的東沙島，民眾黨立委洪毓祥、<a href='/search/tagging/2/陳昭姿' class='tag'><strong>陳昭姿</strong></a>與黨團主任陳智菡今天舉行記者會，再批徐佳青任職僑委會期間，多次讓兒子隨行<a href='/search/tagging/2/出訪' class='tag'><strong>出訪</strong></a>活動，以及領公帑假借出國名義探親與看球賽，要求徐佳青應該辭職，政風單位也要儘速調查。</p>
<p>
</p><p>
洪毓祥表示，徐佳青假借國家機密考察之名，實則出國探親與家庭旅遊。</p>
</section>
</body></html>
"""


class InlineTextRegression(unittest.TestCase):
    def test_block_text_keeps_inline_links_in_the_same_line(self):
        node = BeautifulSoup('<div><p>駐<a>日本</a>代表處今晚在<a><b>東京</b></a>舉辦酒會。</p>'
                             '<p>Bo <a>Tedards</a> said hello.</p><p>第二行<br>換行保留</p></div>', 'lxml').div

        self.assertEqual(base.block_text(node).splitlines(),
                         ['駐日本代表處今晚在東京舉辦酒會。', 'Bo Tedards said hello.', '第二行', '換行保留'])

    def test_udn_paragraph_keeps_tagged_names(self):
        with patch.object(base, 'get_page', return_value=SimpleNamespace(text=UDN_ARTICLE)):
            result = udn.scrape_article(None, 'https://udn.com/news/story/6656/9795943')

        self.assertEqual(result['cleanText'].splitlines(), [
            '台灣民眾黨團日前揭露僑委會委員長徐佳青違法攜子登上軍事管制區的東沙島，民眾黨立委洪毓祥、陳昭姿'
            '與黨團主任陳智菡今天舉行記者會，再批徐佳青任職僑委會期間，多次讓兒子隨行出訪活動，'
            '以及領公帑假借出國名義探親與看球賽，要求徐佳青應該辭職，政風單位也要儘速調查。',
            '洪毓祥表示，徐佳青假借國家機密考察之名，實則出國探親與家庭旅遊。',
        ])


if __name__ == '__main__':
    unittest.main()
