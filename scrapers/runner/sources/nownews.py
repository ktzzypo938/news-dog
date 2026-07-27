"""NOWnews 今日新聞爬蟲"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import base

SOURCE_CODE = 'NOWNEWS'
BASE_URL = 'https://www.nownews.com'

CATEGORY_PAGES = {
    'politics': 'https://www.nownews.com/cat/news-summary/politics/',
    'society': 'https://www.nownews.com/cat/news-summary/society-vientiane/',
    'cross_strait': 'https://www.nownews.com/cat/news-global/chinaindex/',
}

ARTICLE_RE = re.compile(r'/news/\d+$')
URL_CATEGORY_MAP = {}
CATEGORY_LABELS = {
    'politics': '政治',
    'society': '社會',
    'cross_strait': '兩岸',
}


def get_list_urls(session):
    all_urls = []
    URL_CATEGORY_MAP.clear()

    for category, list_url in CATEGORY_PAGES.items():
        try:
            resp = session.get(list_url, timeout=15)
            resp.encoding = 'utf-8'
            soup = BeautifulSoup(resp.text, 'lxml')
            category_urls = []
            for a in soup.select('a[href]'):
                full_url = _normalize_url(urljoin(BASE_URL, a.get('href', '')))
                if ARTICLE_RE.search(full_url):
                    category_urls.append(full_url)
            for full_url in list(dict.fromkeys(category_urls)):
                all_urls.append(full_url)
                URL_CATEGORY_MAP.setdefault(full_url, category)
        except Exception as e:
            print(f"[{SOURCE_CODE}] Failed to fetch {category} list: {e}")

    return list(dict.fromkeys(all_urls))


def scrape_article(session, url):
    try:
        resp = session.get(url, timeout=20)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'lxml')

        canonical = _extract_canonical_url(soup) or _normalize_url(url)
        image_url = base.extract_image_url(soup)

        title_node = soup.select_one('h1.article-title') or soup.select_one('h1')
        title = title_node.get_text(strip=True) if title_node else ""
        if not title:
            og_title = soup.select_one('meta[property="og:title"]')
            title = og_title.get('content', '') if og_title else ""
        title = title.split(' | NOWnews', 1)[0].strip()

        published_at = base.extract_published_at(soup, [
            ('time.time', None),
            ('time', None),
        ])

        content_node = (
            soup.select_one('div.article-content-edtor')
            or soup.select_one('div.article-content')
            or soup.select_one('article.article-body')
        )
        if content_node:
            photographer = _extract_photographer(content_node)
            clean_text = _extract_clean_text(content_node)
        else:
            photographer = None
            clean_text = ""

        result = {
            "source": SOURCE_CODE,
            "url": canonical,
            "title": title,
            "publishedAt": published_at,
            "rawHtml": "",
            "cleanText": clean_text,
        }
        if image_url:
            result["imageUrl"] = image_url
        if photographer:
            result["imagePhotographer"] = photographer
        return result
    except Exception as e:
        print(f"[{SOURCE_CODE}] Error scraping {url}: {e}")
        return None


def get_url_category(url):
    category = URL_CATEGORY_MAP.get(_normalize_url(url))
    return CATEGORY_LABELS.get(category, 'article（分類由列表控制）')


def _normalize_url(url):
    return url.split('?')[0].split('#')[0].rstrip('/')


def _extract_canonical_url(soup):
    node = soup.select_one('link[rel="canonical"]')
    if node and node.get('href'):
        return _normalize_url(urljoin(BASE_URL, node['href']))
    og_url = soup.select_one('meta[property="og:url"]')
    if og_url and og_url.get('content'):
        return _normalize_url(urljoin(BASE_URL, og_url['content']))
    return None


def _extract_clean_text(content_node):
    content = BeautifulSoup(str(content_node), 'lxml')
    for tag in content.select(
        'script, style, iframe, figure, #mediaPost, #facebookPost, '
        '.ad-blk1, .ad-blk, .adcolumn, .aditem, .hr-separator, '
        '.hr-separator-noword, .custom-blk, .related-item, .author-card, '
        '.keywordBlk, .social-link, .flex-jc-center'
    ):
        tag.decompose()

    for br in content.select('br'):
        br.replace_with('\n')

    lines = []
    for line in content.get_text('\n', strip=True).splitlines():
        text = re.sub(r'\s+', ' ', line).strip()
        if not text:
            continue
        if text == '我是廣告 請繼續往下閱讀':
            continue
        if text.startswith('更多「') and text.endswith('相關新聞。'):
            continue
        lines.append(text)

    return "\n".join(lines)


def _extract_photographer(content_node):
    for node in content_node.select('figcaption, img[alt]'):
        text = node.get_text(strip=True) if node.name != 'img' else node.get('alt', '')
        photographer = base.extract_photographer(text)
        if photographer:
            return photographer
    return None
