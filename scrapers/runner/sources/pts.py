"""公視新聞 PTS 爬蟲"""
import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import base

SOURCE_CODE = 'PTS'
BASE_URL = 'https://news.pts.org.tw'

CATEGORIES = {
    'politics': {
        'id': 1,
        'label': '政治',
    },
    'society': {
        'id': 7,
        'label': '社會',
    },
    'lifestyle': {
        'id': 5,
        'label': '生活',
    },
    'cross_strait': {
        'id': 9,
        'label': '兩岸',
    },
}
MAX_URLS_PER_CATEGORY = 30
MAX_CATEGORY_PAGES = 5
ARTICLE_RE = re.compile(r'^https://news\.pts\.org\.tw/article/\d+$')
URL_CATEGORY_MAP = {}


def get_list_urls(session):
    _ensure_headers(session)
    URL_CATEGORY_MAP.clear()

    all_urls = []
    seen = set()
    for category, cfg in CATEGORIES.items():
        urls = _fetch_category_urls(session, category, cfg['id'])
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
        resp = base.get_page(session, normalized_url, timeout=20, source_code=SOURCE_CODE)
        if resp is None:
            return None
        soup = BeautifulSoup(resp.text, 'lxml')
        article_ld = _extract_article_ld(soup) or {}

        canonical = _extract_canonical_url(soup) or normalized_url
        title = _extract_title(soup, article_ld)
        published_at = base.extract_published_at(soup, [
            ('.article-time', None),
        ])
        image_url = base.extract_image_url(soup)
        clean_text = _extract_clean_text(article_ld, soup)

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


def _fetch_category_urls(session, category, category_id):
    urls = []
    for page in range(1, MAX_CATEGORY_PAGES + 1):
        list_url = f'{BASE_URL}/category/{category_id}?page={page}'
        try:
            resp = session.get(list_url, timeout=20)
            resp.encoding = 'utf-8'
            soup = BeautifulSoup(resp.text, 'lxml')
            page_urls = _extract_article_urls(soup)
            if not page_urls:
                break
            urls.extend(page_urls)
            if len(dict.fromkeys(urls)) >= MAX_URLS_PER_CATEGORY:
                break
        except Exception as e:
            print(f"[{SOURCE_CODE}] Failed to fetch {category} page {page}: {e}")
            break

    return list(dict.fromkeys(urls))


def _extract_article_urls(soup):
    scope = soup.select_one('.break-news-container') or soup
    urls = []
    for a in scope.select('a[href*="/article/"]'):
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
    return url.split('?')[0].split('#')[0].rstrip('/')


def _extract_canonical_url(soup):
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
            if not isinstance(item, dict):
                continue
            if item.get('@type') in {'NewsArticle', 'Article'} and item.get('articleBody'):
                return item
    return None


def _extract_title(soup, article_ld):
    title_node = soup.select_one('h1.article-title') or soup.select_one('h1')
    if title_node:
        return title_node.get_text(' ', strip=True)

    headline = article_ld.get('headline')
    if headline:
        return headline.split(' ｜ 公視新聞網', 1)[0].strip()
    return ""


def _extract_clean_text(article_ld, soup):
    text = article_ld.get('articleBody')
    if text:
        return _normalize_body_text(text)

    article_node = soup.select_one('article[itemprop="articleBody"]') or soup.select_one('article')
    if not article_node:
        return ""
    content = BeautifulSoup(str(article_node), 'lxml')
    for tag in content.select('script, style, iframe, img, .article-relative, .news-tag, .alert-content'):
        tag.decompose()
    base.remove_promo_blocks(content)
    return _normalize_body_text(content.get_text('\n', strip=True))


def _normalize_body_text(text):
    if not text:
        return ""
    paragraphs = []
    for line in str(text).splitlines():
        clean = re.sub(r'\s+', ' ', line).strip()
        if clean:
            paragraphs.append(clean)
    return "\n".join(paragraphs)
