"""關鍵評論網 TNL 爬蟲"""
import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

import base

SOURCE_CODE = 'TNL'
BASE_URL = 'https://www.thenewslens.com'

CATEGORIES = {
    'politics': {
        'label': '政治',
        'path': 'politics',
        'pages': 3,
    },
    'society': {
        'label': '社會',
        'path': 'society',
        'pages': 3,
    },
    'cross_strait': {
        'label': '兩岸',
        'path': 'china',
        'pages': 3,
    },
}
MAX_URLS_PER_CATEGORY = 30
MAX_CANDIDATES_PER_CATEGORY = MAX_URLS_PER_CATEGORY * 3
ARTICLE_RE = re.compile(r'^https://www\.thenewslens\.com/article/\d+$')
URL_CATEGORY_MAP = {}


def get_list_urls(session):
    _ensure_headers(session)
    URL_CATEGORY_MAP.clear()

    all_urls = []
    seen = set()
    for category, cfg in CATEGORIES.items():
        urls = _fetch_category_urls(session, cfg)
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
        clean_text = _extract_clean_text(soup, article_ld)

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


def _fetch_category_urls(session, cfg):
    urls = []
    for page in range(1, cfg['pages'] + 1):
        try:
            resp = session.get(_category_url(cfg['path'], page), timeout=20)
            resp.encoding = 'utf-8'
            if resp.status_code >= 400:
                break
            soup = BeautifulSoup(resp.text, 'lxml')
            urls.extend(_extract_list_urls(soup))
            if len(dict.fromkeys(urls)) >= MAX_CANDIDATES_PER_CATEGORY:
                break
        except Exception as e:
            print(f"[{SOURCE_CODE}] Failed to fetch category {cfg['path']} page {page}: {e}")
            break
    return list(dict.fromkeys(urls))


def _category_url(path, page):
    if page <= 1:
        return f'{BASE_URL}/category/{path}'
    return f'{BASE_URL}/category/{path}/page{page}'


def _extract_list_urls(soup):
    urls = []
    for item in soup.select('.shadow-sm.p-3.bg-white.item'):
        anchor = item.select_one('h3.item-title a[href*="/article/"]')
        if not anchor:
            anchor = item.select_one('a[href*="/article/"]')
        if not anchor:
            continue
        url = _normalize_url(urljoin(BASE_URL, anchor.get('href', '')))
        if ARTICLE_RE.match(url):
            urls.append(url)
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
            if isinstance(item, dict) and item.get('@type') in {'NewsArticle', 'Article'}:
                return item
    return None


def _extract_title(soup, article_ld):
    if article_ld.get('headline'):
        return _clean_title(article_ld['headline'])
    node = soup.select_one('h1')
    if node:
        return node.get_text(' ', strip=True)
    og_title = soup.select_one('meta[property="og:title"]')
    if og_title and og_title.get('content'):
        return _clean_title(og_title['content'])
    return ""


def _clean_title(title):
    return str(title).split(' - TNL The News Lens', 1)[0].strip()


def _extract_image_url(soup, article_ld):
    image = article_ld.get('image')
    if isinstance(image, list) and image:
        first = image[0]
        if isinstance(first, dict):
            return first.get('url') or first.get('contentUrl')
        return first
    if isinstance(image, dict):
        return image.get('url') or image.get('contentUrl')
    if isinstance(image, str):
        return image
    return base.extract_image_url(soup)


def _extract_clean_text(soup, article_ld):
    body = article_ld.get('articleBody')
    if body:
        return _normalize_body_text(body)

    article_body = soup.select_one('section.article-body')
    if not article_body:
        return ""

    content = BeautifulSoup(str(article_body), 'lxml')
    for tag in content.select('script, style, iframe, img, figure, aside, .ad-content'):
        tag.decompose()

    paragraphs = []
    for p in content.select('p'):
        text = _normalize_text(p.get_text(' ', strip=True))
        if text:
            paragraphs.append(text)
    if paragraphs:
        return "\n".join(paragraphs)
    return _normalize_body_text(content.get_text('\n', strip=True))


def _normalize_body_text(text):
    if not text:
        return ""
    parts = []
    for line in str(text).splitlines():
        clean = _normalize_text(line)
        if clean:
            parts.append(clean)
    if len(parts) <= 1:
        return _normalize_text(text)
    return "\n".join(parts)


def _normalize_text(text):
    return re.sub(r'\s+', ' ', str(text)).strip() if text else ""
