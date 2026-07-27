"""Newtalk 新頭殼爬蟲"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import base

SOURCE_CODE = 'NEWTALK'
BASE_URL = 'https://newtalk.tw'

CATEGORY_PAGES = {
    'politics': 'https://newtalk.tw/news/subcategory/2',
    'society': 'https://newtalk.tw/news/subcategory/14',
    'cross_strait': 'https://newtalk.tw/news/subcategory/7',  # Newtalk 使用「中國」
}

ARTICLE_RE = re.compile(r'/news/view/\d{4}-\d{2}-\d{2}/\d+$')
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
            for a in soup.select('ul.category-list a[href]'):
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

        title_node = soup.select_one('h1') or soup.select_one('meta[property="og:title"]')
        if getattr(title_node, 'name', '') == 'meta':
            title = title_node.get('content', '')
        else:
            title = title_node.get_text(strip=True) if title_node else ""
        title = title.replace('[Newtalk新聞]', '').split(' | ', 1)[0].strip()

        published_at = base.extract_published_at(soup, [
            ('meta[name="datePublished"]', 'content'),
            ('meta[itemprop="datePublished"]', 'content'),
        ])

        content_node = soup.select_one('div.articleBody[itemprop="articleBody"]') or soup.select_one('div.news_content')
        if content_node:
            photographer = _extract_photographer(soup)
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
        'script, style, iframe, .loading-block, .ad-container, .ad-half, '
        '.recommend, .gliaplayer-container, .news_img, figure, aside'
    ):
        tag.decompose()

    paragraphs = []
    for p in content.select('p'):
        text = _clean_text(p.get_text(' ', strip=True))
        if text:
            paragraphs.append(text)

    if paragraphs:
        return "\n".join(paragraphs)
    return _clean_text(content.get_text('\n', strip=True))


def _clean_text(text):
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text).strip()
    if text.startswith(('全站首選：', '現正最夯：')):
        return ""
    return text


def _extract_photographer(soup):
    for node in soup.select('div.news_img p.text, div.news_img img[alt], figcaption, img[alt]'):
        text = node.get_text(strip=True) if node.name != 'img' else node.get('alt', '')
        photographer = _extract_newtalk_credit(text) or base.extract_photographer(text)
        if photographer:
            return photographer
    return None


def _extract_newtalk_credit(text):
    if not text:
        return None
    match = re.search(r'圖[：:]\s*(.+)$', text)
    if not match:
        return None
    credit = match.group(1).strip()
    credit = re.sub(r'[／/]\s*攝.*$', '', credit).strip()
    credit = re.sub(r'（.*?）', '', credit).strip()
    return credit or None
