"""新新聞 NEW7 爬蟲"""
import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

import base

SOURCE_CODE = 'NEW7'
BASE_URL = 'https://new7.storm.mg'

LIST_PATHS = (
    '',
    'category/k248039',  # 政策盤點
    'category/k320014',  # 透明政府
    'category/k364837',  # 社會轉角
    'category/k205747',  # 歷史新新聞
    'topic',
    'specialtopic',
)

CATEGORIES = {
    'cross_strait': {
        'label': '兩岸',
        'keywords': (
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
            '台獨',
            '統一',
            '李登輝',
            '江澤民',
        ),
    },
    'politics': {
        'label': '政治',
        'keywords': (
            '政府',
            '司法',
            '監察',
            '國民黨',
            '民進黨',
            '民眾黨',
            '縣長',
            '總統',
            '立委',
            '國會',
            '政策',
            '國發',
            '台電',
            '中油',
            '預算',
            '選舉',
            '基金會',
        ),
    },
    'society': {
        'label': '社會',
        'keywords': (
            '醫療',
            '中醫',
            '護理',
            '健保',
            '民眾',
            '社會',
            '司法',
            '詐騙',
            '交通',
            '減重',
            '患者',
            '藥',
            '醫師',
            '政府',
            '醫院',
            '照護',
        ),
    },
}

MAX_URLS_PER_CATEGORY = 30
ARTICLE_RE = re.compile(r'^https://new7\.storm\.mg/article/\d+$')
URL_CATEGORY_MAP = {}


def get_list_urls(session):
    _ensure_headers(session)
    URL_CATEGORY_MAP.clear()

    entries = _fetch_entries(session)
    all_urls = []
    seen = set()
    for category, cfg in CATEGORIES.items():
        added = 0
        for entry in entries:
            url = entry['url']
            if url in seen:
                continue
            if not _contains_keyword(entry.get('text', ''), cfg['keywords']):
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


def _fetch_entries(session):
    entries = []
    for path in LIST_PATHS:
        try:
            resp = session.get(_list_url(path), timeout=20)
            resp.encoding = 'utf-8'
            if resp.status_code >= 400:
                continue
            soup = BeautifulSoup(resp.text, 'lxml')
            entries.extend(_extract_entries(soup))
        except Exception as e:
            print(f"[{SOURCE_CODE}] Failed to fetch list {path or '/'}: {e}")
    return _dedupe_entries(entries)


def _list_url(path):
    if not path:
        return f'{BASE_URL}/'
    return f'{BASE_URL}/{path}'


def _extract_entries(soup):
    entries = []
    for a in soup.select('a[href]'):
        url = _normalize_url(urljoin(BASE_URL, a.get('href', '')))
        if not ARTICLE_RE.match(url):
            continue
        parent = a.find_parent('div') or a
        text = _normalize_text(parent.get_text(' ', strip=True) or a.get_text(' ', strip=True))
        entries.append({'url': url, 'text': text})
    return entries


def _dedupe_entries(entries):
    by_url = {}
    for entry in entries:
        current = by_url.get(entry['url'])
        if not current or len(entry.get('text', '')) > len(current.get('text', '')):
            by_url[entry['url']] = entry
    return list(by_url.values())


def _contains_keyword(text, keywords):
    return any(keyword in text for keyword in keywords)


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
    node = soup.select_one('h1.article_title') or soup.select_one('h1')
    if node:
        return node.get_text(' ', strip=True)
    og_title = soup.select_one('meta[property="og:title"]')
    if og_title and og_title.get('content'):
        return og_title['content'].split('-新新聞', 1)[0].strip()
    return ""


def _extract_image_url(soup, article_ld):
    for key in ('thumbnailUrl', 'image'):
        image = article_ld.get(key)
        if isinstance(image, dict):
            return image.get('url') or image.get('contentUrl')
        if isinstance(image, str):
            return image
    return base.extract_image_url(soup)


def _extract_clean_text(soup, article_ld):
    body = article_ld.get('articleBody')
    if body:
        return _normalize_body_text(body)

    content_node = soup.select_one('.article_content, .article_content_wrapper')
    if not content_node:
        return ""
    content = BeautifulSoup(str(content_node), 'lxml')
    for tag in content.select('script, style, iframe, img, figure, aside'):
        tag.decompose()
    return _normalize_body_text(content.get_text('\n', strip=True))


def _normalize_body_text(text):
    if not text:
        return ""
    parts = []
    for line in str(text).splitlines():
        clean = _normalize_text(line)
        if clean:
            parts.append(clean)
    return "\n".join(parts) if len(parts) > 1 else _normalize_text(text)


def _normalize_text(text):
    if not text:
        return ""
    return re.sub(r'\s+', ' ', str(text)).strip()
