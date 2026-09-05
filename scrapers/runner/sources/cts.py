"""華視官方新聞 API；GCP 透過專用取頁服務存取，文章網址維持原站。"""
import re
import os
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import base

SOURCE_CODE = 'CTS'
BASE_URL = 'https://news.cts.com.tw'
FETCH_BASE_URL = os.getenv('CTS_FETCH_BASE_URL', BASE_URL).rstrip('/')
FETCH_TOKEN = os.getenv('CTS_FETCH_TOKEN', '')
PAGE_SIZE = 30

CATEGORIES = {
    'cross_strait': {
        'label': '兩岸',
        'paths': ('international/list', 'politics/list'),
    },
    'politics': {
        'label': '政治',
        'path': 'politics/list',
        'tag': '政治',
    },
    'society': {
        'label': '社會',
        'path': 'society/list',
        'tag': '社會',
    },
    'lifestyle': {
        'label': '生活',
        'path': 'life/list',
        'tag': '生活',
    },
}
MAX_URLS_PER_CATEGORY = 30
MAX_CATEGORY_PAGES = 8
MAX_CROSS_STRAIT_PAGES = 15
ARTICLE_RE = re.compile(r'^https://news\.cts\.com\.tw/[a-z]+/[a-z_]+/\d{6}/\d+\.html$')
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
    '小三通',
    '金門',
    '馬祖',
    '海警',
)


def get_list_urls(session):
    URL_CATEGORY_MAP.clear()
    session._cts_list_pages = {}
    session._scraper_list_valid = False
    all_urls = []
    seen = set()
    for category, cfg in CATEGORIES.items():
        if category == 'cross_strait':
            urls = _fetch_cross_strait_urls(session, cfg['paths'])
        else:
            urls = _fetch_category_urls(session, category, cfg['path'], cfg['tag'])
        for url in urls:
            if url not in seen:
                seen.add(url)
                all_urls.append(url)
                URL_CATEGORY_MAP[url] = category
    return all_urls


def _get_api(session, path, allow_missing=False):
    session._scraper_request_interval = 0.5
    headers = {'Accept': 'application/json'}
    if FETCH_BASE_URL != BASE_URL:
        if not FETCH_TOKEN:
            raise base.SourceFetchError('CTS_FETCH_TOKEN is required for the configured fetch service')
        headers['Authorization'] = 'Bearer ' + FETCH_TOKEN
    url = FETCH_BASE_URL + path
    resp = base.get_page(session, url, timeout=25, source_code=SOURCE_CODE, headers=headers)
    if resp is None:
        if allow_missing and (base.SKIP_URL_CACHE.get(url) in ('http404', 'http410')
                              or vars(session).get('_scraper_rate_limited')):
            return None
        raise base.SourceFetchError(f'CTS API request failed: {path}')
    try:
        payload = resp.json()
    except ValueError as e:
        raise base.SourceFetchError(f'CTS API returned non-JSON data: {path}') from e
    if not isinstance(payload, dict) or payload.get('status') is not True or not isinstance(payload.get('data'), dict):
        raise base.SourceFetchError(f'CTS API returned an invalid response: {path}')
    return payload['data']


def _iter_list_items(session, path, max_pages):
    category = path.split('/')[0]
    cache = vars(session).setdefault('_cts_list_pages', {})
    for page in range(1, max_pages + 1):
        key = (category, page)
        if key not in cache:
            cache[key] = _get_api(session, f'/api/news/{category}/list?page={page}&limit={PAGE_SIZE}')
        data = cache[key]
        items = data.get('articles')
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise base.SourceFetchError('CTS API list has no valid articles array')
        session._scraper_list_valid = True
        if not items:
            return
        dates = [base.parse_datetime(item.get('publishTime')) for item in items]
        # 列表依時間排序；整頁都比日期範圍舊時即可停止翻頁。
        if (base.SCRAPER_ONLY_TODAY and all(dates)
                and max(value[:10] for value in dates) < min(base.get_target_dates())):
            return
        for item, published_at in zip(items, dates):
            if not published_at or base.should_ingest_published_at(published_at):
                yield item
        total_pages = data.get('pagination', {}).get('totalPages')
        if (isinstance(total_pages, int) and page >= total_pages) or len(items) < PAGE_SIZE:
            return


def _article_url(item):
    url = _normalize_url(urljoin(BASE_URL, item.get('link') or ''))
    return url if ARTICLE_RE.fullmatch(url) else None


def _fetch_category_urls(session, category, path, expected_tag):
    urls = []
    for item in _iter_list_items(session, path, MAX_CATEGORY_PAGES):
        url = _article_url(item)
        if url and item.get('category') == expected_tag and url not in urls:
            urls.append(url)
            if len(urls) >= MAX_URLS_PER_CATEGORY:
                break
    return urls


def _fetch_cross_strait_urls(session, paths):
    urls = []
    for path in paths:
        for item in _iter_list_items(session, path, MAX_CROSS_STRAIT_PAGES):
            url = _article_url(item)
            text = str(item.get('title', '')) + ' ' + str(item.get('content', ''))
            if url and _looks_cross_strait(text) and url not in urls:
                urls.append(url)
                if len(urls) >= MAX_URLS_PER_CATEGORY:
                    return urls
    return urls


def scrape_article(session, url):
    canonical = _normalize_url(url)
    if not ARTICLE_RE.fullmatch(canonical):
        return None
    article_id = canonical.rsplit('/', 1)[-1].removesuffix('.html')
    path = '/api/news/' + article_id
    data = _get_api(session, path, allow_missing=True)
    if data is None:
        reason = base.SKIP_URL_CACHE.get(FETCH_BASE_URL + path)
        if reason in ('http404', 'http410'):
            base.remember_skip(canonical, reason)
        return None
    article = data.get('article')
    if not isinstance(article, dict):
        raise base.SourceFetchError(f'CTS API has no article: {article_id}')
    content = BeautifulSoup(article.get('content') or '', 'lxml')
    for tag in content.select('img, video, figure'):
        if tag.parent:
            tag.decompose()
    base.remove_promo_blocks(content)
    result = {
        'source': SOURCE_CODE,
        'url': _article_url(article) or canonical,
        'title': article.get('title', '').strip(),
        'publishedAt': base.parse_datetime(article.get('publishTime')),
        'rawHtml': '',
        'cleanText': content.get_text('\n', strip=True),
    }
    image = article.get('coverImage') or {}
    if isinstance(image, dict) and image.get('imageUrl'):
        result['imageUrl'] = image['imageUrl']
    return result


def get_url_category(url):
    category = URL_CATEGORY_MAP.get(_normalize_url(url))
    return CATEGORIES.get(category, {}).get('label', '未知')


def _looks_cross_strait(text):
    return any(keyword in text for keyword in CROSS_STRAIT_KEYWORDS)


def _normalize_url(url):
    return url.split('?')[0].split('#')[0].rstrip('/')
