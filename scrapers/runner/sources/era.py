"""年代新聞 ERA 爬蟲"""
import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

import base

SOURCE_CODE = 'ERA'
BASE_URL = 'https://www.eracom.com.tw'

CATEGORIES = {
    'politics': {
        'label': '政治',
        'path': 'political',
    },
    'society': {
        'label': '社會',
        'path': 'Society',
    },
    'cross_strait': {
        'label': '兩岸',
        'path': 'China',
    },
}
MAX_URLS_PER_CATEGORY = 30
PAGE_OFFSETS = (0, 10, 20)
ARTICLE_RE = re.compile(r'^https://www\.eracom\.com\.tw/EraNews/Home/[^/]+/\d{4}-\d{2}-\d{2}/\d+\.html$')
URL_CATEGORY_MAP = {}


def get_list_urls(session):
    _ensure_headers(session)
    URL_CATEGORY_MAP.clear()

    all_urls = []
    seen = set()
    for category, cfg in CATEGORIES.items():
        urls = _fetch_category_urls(session, cfg['path'])
        added = 0
        for url in urls:
            if url in seen:
                continue
            all_urls.append(url)
            seen.add(url)
            URL_CATEGORY_MAP[url] = category
            added += 1
            if added >= MAX_URLS_PER_CATEGORY:
                break
    return all_urls


def scrape_article(session, url):
    try:
        _ensure_headers(session)
        normalized_url = _normalize_url(url)
        resp = session.get(normalized_url, timeout=20)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'lxml')
        article_ld = _extract_article_ld(soup) or {}

        canonical = _extract_canonical_url(soup, article_ld) or normalized_url
        title = _extract_title(soup, article_ld)
        published_at = base.extract_published_at(soup)
        image_url = _extract_image_url(soup, article_ld)
        clean_text = _extract_clean_text(soup)

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
        return result
    except Exception as e:
        print(f"[{SOURCE_CODE}] Error scraping {url}: {e}")
        return None


def get_url_category(url):
    category = URL_CATEGORY_MAP.get(_normalize_url(url))
    return CATEGORIES.get(category, {}).get('label', '未知')


def _fetch_category_urls(session, path):
    urls = []
    for offset in PAGE_OFFSETS:
        try:
            resp = session.get(_category_url(path, offset), timeout=20)
            resp.encoding = 'utf-8'
            if resp.status_code >= 400:
                break
            soup = BeautifulSoup(resp.text, 'lxml')
            page_urls = _extract_list_urls(soup)
            if not page_urls:
                break
            urls.extend(page_urls)
        except Exception as e:
            print(f"[{SOURCE_CODE}] Failed to fetch category {path} offset {offset}: {e}")
            break
    return list(dict.fromkeys(urls))


def _category_url(path, offset):
    url = f'{BASE_URL}/EraNews/Home/{path}/'
    if offset <= 0:
        return url
    return f'{url}?pp={offset}'


def _extract_list_urls(soup):
    urls = []
    for a in soup.select('a[href]'):
        full_url = _normalize_url(urljoin(BASE_URL, a.get('href', '')))
        if ARTICLE_RE.match(full_url):
            urls.append(full_url)
    return list(dict.fromkeys(urls))


def _ensure_headers(session):
    session.headers.update({
        'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    })


def _normalize_url(url):
    parsed = urlparse(url)
    normalized = f'{parsed.scheme}://{parsed.netloc}{parsed.path}'
    return normalized.rstrip('/')


def _extract_canonical_url(soup, article_ld):
    if article_ld.get('url'):
        return _normalize_url(urljoin(BASE_URL, article_ld['url']))
    node = soup.select_one('link[rel="canonical"]')
    if node and node.get('href'):
        return _normalize_url(urljoin(BASE_URL, node['href']))
    og_url = soup.select_one('meta[property="og:url"]')
    if og_url and og_url.get('content'):
        return _normalize_url(urljoin(BASE_URL, og_url['content']))
    return None


def _extract_article_ld(soup):
    for ld_node in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(ld_node.string or '')
        except Exception:
            continue
        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if isinstance(item, dict) and item.get('@type') == 'NewsArticle':
                return item
    return None


def _extract_title(soup, article_ld):
    if article_ld.get('headline'):
        return article_ld['headline'].strip()
    node = soup.select_one('h1.articletitle') or soup.select_one('h1')
    if node:
        return node.get_text(' ', strip=True)
    og_title = soup.select_one('meta[property="og:title"]')
    if og_title and og_title.get('content'):
        return og_title['content'].strip()
    return ""


def _extract_image_url(soup, article_ld):
    image = article_ld.get('image')
    if isinstance(image, dict):
        return image.get('url') or image.get('contentUrl')
    if isinstance(image, str):
        return image
    return base.extract_image_url(soup)


def _extract_clean_text(soup):
    content_node = soup.select_one('.article-main')
    if not content_node:
        return ""
    content = BeautifulSoup(str(content_node), 'lxml')
    for tag in content.select('script, style, iframe, img, figure, aside, .article-page'):
        tag.decompose()
    paragraphs = []
    for p in content.select('p'):
        text = _normalize_text(p.get_text(' ', strip=True))
        if text:
            paragraphs.append(text)
    if paragraphs:
        return "\n".join(paragraphs)
    return _normalize_text(content.get_text('\n', strip=True))


def _normalize_text(text):
    if not text:
        return ""
    return re.sub(r'\s+', ' ', str(text)).strip()
