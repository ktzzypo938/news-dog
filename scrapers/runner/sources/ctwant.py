"""CTWANT 爬蟲"""
import json
import re
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

import base

SOURCE_CODE = 'CTWANT'
BASE_URL = 'https://www.ctwant.com'

CATEGORIES = {
    'politics': {
        'label': '政治',
        'paths': ('政治',),
    },
    'society': {
        'label': '社會',
        'paths': ('社會',),
    },
    'cross_strait': {
        'label': '兩岸',
        'paths': ('國際/大陸', '國際'),
    },
}
MAX_URLS_PER_CATEGORY = 30
ARTICLE_RE = re.compile(r'^https://www\.ctwant\.com/article/\d+$')
URL_CATEGORY_MAP = {}

CROSS_STRAIT_KEYWORDS = (
    '中國',
    '大陸',
    '兩岸',
    '台海',
    '中共',
    '國台辦',
    '陸委會',
    '北京',
    '香港',
    '澳門',
    '解放軍',
    '共軍',
    '對台',
    '習近平',
    '川習',
    '訪中',
    '台獨',
    '九二共識',
    '軍售',
)


def get_list_urls(session):
    _ensure_headers(session)
    URL_CATEGORY_MAP.clear()

    all_urls = []
    seen = set()
    for category, cfg in CATEGORIES.items():
        urls = _fetch_category_urls(session, category, cfg['paths'])
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

        canonical = _extract_canonical_url(soup) or normalized_url
        title = _extract_title(soup, article_ld)
        published_at = base.extract_published_at(soup, [
            ('time.p-article-info__time', 'datetime'),
        ])
        image_url = base.extract_image_url(soup)
        clean_text = _extract_clean_text(soup, article_ld)
        photographer = _extract_photographer(article_ld)

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
    return CATEGORIES.get(category, {}).get('label', '未知')


def _fetch_category_urls(session, category, paths):
    urls = []
    for path in paths:
        list_url = _category_url(path)
        try:
            resp = session.get(list_url, timeout=20)
            resp.encoding = 'utf-8'
            soup = BeautifulSoup(resp.text, 'lxml')
            keyword_filter = category == 'cross_strait' and path != '國際/大陸'
            page_urls = _extract_article_urls(soup, keyword_filter=keyword_filter)
            urls.extend(page_urls)
            if len(dict.fromkeys(urls)) >= MAX_URLS_PER_CATEGORY:
                break
        except Exception as e:
            print(f"[{SOURCE_CODE}] Failed to fetch {category} {path}: {e}")
            break

    return list(dict.fromkeys(urls))


def _category_url(path):
    return f'{BASE_URL}/category/{quote(path, safe="/")}/'


def _extract_article_urls(soup, keyword_filter=False):
    urls = []
    for a in soup.select('a[href^="/article/"]'):
        full_url = _normalize_url(urljoin(BASE_URL, a.get('href', '')))
        if not ARTICLE_RE.match(full_url):
            continue
        item = a.find_parent('li') or a.find_parent('article') or a
        text = item.get_text(' ', strip=True)
        if keyword_filter and not _looks_cross_strait(text):
            continue
        urls.append(full_url)
    return list(dict.fromkeys(urls))


def _looks_cross_strait(text):
    return any(keyword in text for keyword in CROSS_STRAIT_KEYWORDS)


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
            if isinstance(item, dict) and item.get('@type') in {'NewsArticle', 'Article'}:
                return item
    return None


def _extract_title(soup, article_ld):
    title_node = soup.select_one('h1')
    if title_node:
        return title_node.get_text(' ', strip=True)
    if article_ld.get('headline'):
        return article_ld['headline'].strip()
    return ""


def _extract_clean_text(soup, article_ld):
    text = article_ld.get('articleBody')
    if text:
        return _normalize_body_text(text)

    article_node = soup.select_one('article')
    if not article_node:
        return ""
    content = BeautifulSoup(str(article_node), 'lxml')
    for tag in content.select('script, style, iframe, img, figure, aside'):
        tag.decompose()
    return _normalize_body_text(content.get_text('\n', strip=True))


def _normalize_body_text(text):
    if not text:
        return ""
    parts = []
    for line in str(text).splitlines():
        clean = re.sub(r'\s+', ' ', line).strip()
        if clean:
            parts.append(clean)
    if len(parts) <= 1:
        return re.sub(r'\s+', ' ', str(text)).strip()
    return "\n".join(parts)


def _extract_photographer(article_ld):
    image = article_ld.get('image')
    caption = None
    if isinstance(image, dict):
        caption = image.get('caption')
    if not caption:
        return None
    return base.extract_photographer(caption)
