"""ETtoday 新聞雲爬蟲"""
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import base

SOURCE_CODE = 'ETTODAY'
BASE_URL = 'https://www.ettoday.net'

CATEGORY_IDS = {
    'politics': '1',
    'cross_strait': '3',  # ETtoday 使用「大陸」
    'lifestyle': '5',
    'society': '6',
}

MAX_URLS_PER_CATEGORY = 40
ARTICLE_RE = re.compile(r'/news/\d{8}/\d+\.htm')
URL_CATEGORY_MAP = {}
CATEGORY_LABELS = {
    'politics': '政治',
    'cross_strait': '兩岸',
    'lifestyle': '生活',
    'society': '社會',
}


def get_list_urls(session):
    all_urls = []
    URL_CATEGORY_MAP.clear()

    for list_date in _target_dates():
        for category, category_id in CATEGORY_IDS.items():
            list_url = f'{BASE_URL}/news/news-list-{list_date}-{category_id}.htm'
            try:
                resp = session.get(list_url, timeout=15)
                resp.encoding = 'utf-8'
                soup = BeautifulSoup(resp.text, 'lxml')
                category_urls = []
                for a in soup.select('div.part_list_2 a[href]'):
                    full_url = _normalize_url(urljoin(BASE_URL, a.get('href', '')))
                    if ARTICLE_RE.search(full_url):
                        category_urls.append(full_url)
                for full_url in list(dict.fromkeys(category_urls))[:MAX_URLS_PER_CATEGORY]:
                    all_urls.append(full_url)
                    URL_CATEGORY_MAP.setdefault(full_url, category)
            except Exception as e:
                print(f"[{SOURCE_CODE}] Failed to fetch {category} list {list_date}: {e}")

    return list(dict.fromkeys(all_urls))


def scrape_article(session, url):
    try:
        resp = session.get(url, timeout=20)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'lxml')

        canonical = _extract_canonical_url(soup) or _normalize_url(url)
        image_url = base.extract_image_url(soup)

        title_node = soup.select_one('h1.title') or soup.select_one('h1')
        title = title_node.get_text(strip=True) if title_node else ""
        if not title:
            og_title = soup.select_one('meta[property="og:title"]')
            title = og_title.get('content', '') if og_title else ""
        title = title.split(' | ETtoday', 1)[0].strip()

        published_at = base.extract_published_at(soup, [
            ('time.date', 'datetime'),
            ('time', 'datetime'),
            ('.date', None),
        ])

        content_node = soup.select_one('div.story')
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


def _target_dates():
    today = datetime.now(timezone(timedelta(hours=8))).date()
    return [today.strftime('%Y-%m-%d')]


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
        'script, style, iframe, .ad, .fb-page, .recommended, .related-news, '
        '.social-share, .et_social_2, aside'
    ):
        tag.decompose()
    base.remove_promo_blocks(content)

    paragraphs = []
    for p in content.select('p'):
        text = p.get_text(strip=True)
        if not text:
            continue
        if text.startswith('▲') and '圖／' in text:
            continue
        if text.startswith('►') or text.startswith('★'):
            continue
        paragraphs.append(text)

    if paragraphs:
        return "\n".join(paragraphs)

    return content.get_text("\n", strip=True)


def _extract_photographer(content_node):
    for node in content_node.select('p, img[alt]'):
        text = node.get_text(strip=True) if node.name != 'img' else node.get('alt', '')
        photographer = base.extract_photographer(text)
        if photographer:
            return photographer
    return None
