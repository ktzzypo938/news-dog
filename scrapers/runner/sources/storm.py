"""風傳媒爬蟲"""
import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import base

SOURCE_CODE = 'STORM'
BASE_URL = 'https://www.storm.mg'

CATEGORY_PAGES = {
    'politics': 'https://www.storm.mg/channel/all/7',
    'society': 'https://www.storm.mg/channel/all/22',  # 地方新聞，對應本專案社會/地方事件範圍
    'lifestyle': 'https://www.storm.mg/channel/all/5',
    'cross_strait': 'https://www.storm.mg/channel/all/11',
}

MAX_URLS_PER_CATEGORY = 40
ARTICLE_RE = re.compile(r'/article/\d+$')
URL_CATEGORY_MAP = {}
CATEGORY_LABELS = {
    'politics': '政治',
    'society': '社會',
    'lifestyle': '生活',
    'cross_strait': '兩岸',
}


def get_list_urls(session):
    all_urls = []
    URL_CATEGORY_MAP.clear()

    for category, list_url in CATEGORY_PAGES.items():
        try:
            resp = session.get(list_url, timeout=20)
            resp.encoding = 'utf-8'
            soup = BeautifulSoup(resp.text, 'lxml')
            category_urls = []
            for a in soup.select('a[href]'):
                full_url = _normalize_url(urljoin(BASE_URL, a.get('href', '')))
                if ARTICLE_RE.search(full_url) and not full_url.endswith('/110488'):
                    category_urls.append(full_url)
            for full_url in list(dict.fromkeys(category_urls))[:MAX_URLS_PER_CATEGORY]:
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
        article_ld = _extract_news_article_json_ld(soup)

        canonical = _extract_canonical_url(soup) or _normalize_url(url)
        image_url = base.extract_image_url(soup)

        title_node = soup.select_one('h1')
        title = title_node.get_text(strip=True) if title_node else ""
        if not title and article_ld:
            title = article_ld.get('headline', '')
        if not title:
            og_title = soup.select_one('meta[property="og:title"]')
            title = og_title.get('content', '') if og_title else ""
        title = title.split(' | ', 1)[0].strip()

        published_at = base.extract_published_at(soup, [
            ('meta[name="datePublished"]', 'content'),
            ('meta[property="article:published_time"]', 'content'),
        ])

        photographer = _extract_photographer(soup)
        clean_text = ""
        if article_ld and article_ld.get('articleBody'):
            clean_text = _clean_text(article_ld.get('articleBody', ''))
        if not clean_text:
            content_node = soup.select_one('article')
            clean_text = _extract_clean_text(content_node) if content_node else ""

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


def _extract_news_article_json_ld(soup):
    for ld_node in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(ld_node.string or '')
        except Exception:
            continue
        for item in _iter_json_ld_items(data):
            item_type = item.get('@type')
            if item.get('articleBody') and (
                item_type == 'NewsArticle'
                or (isinstance(item_type, list) and 'NewsArticle' in item_type)
            ):
                return item
    return None


def _iter_json_ld_items(data):
    if isinstance(data, dict):
        yield data
        graph = data.get('@graph')
        if graph:
            yield from _iter_json_ld_items(graph)
    elif isinstance(data, list):
        for item in data:
            yield from _iter_json_ld_items(item)


def _extract_clean_text(content_node):
    content = BeautifulSoup(str(content_node), 'lxml')
    for tag in content.select('script, style, iframe, figure, .ad, .recommend, .related, aside'):
        tag.decompose()
    base.remove_promo_blocks(content)

    paragraphs = []
    for p in content.select('p'):
        text = _clean_text(p.get_text(' ', strip=True))
        if text:
            paragraphs.append(text)

    if paragraphs:
        return "\n".join(paragraphs)
    return _clean_text(content.get_text(' ', strip=True))


def _clean_text(text):
    if not text:
        return ""

    text = re.sub(r'\s+', ' ', text).strip()
    for marker in [
        '更多風傳媒獨家內幕：',
        '更多風傳媒報導：',
        '更多文章推薦：',
        '更多相關報導：',
        '責任編輯：',
    ]:
        if marker in text:
            text = text.split(marker, 1)[0].strip()
    return text


def _extract_photographer(soup):
    for node in soup.select('figcaption, img[alt]'):
        text = node.get_text(strip=True) if node.name != 'img' else node.get('alt', '')
        photographer = base.extract_photographer(text)
        if photographer:
            return photographer
    return None
