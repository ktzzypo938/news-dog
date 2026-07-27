"""菱傳媒 RWNEWS 爬蟲"""
import re
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

import base

SOURCE_CODE = 'RWNEWS'
BASE_URL = 'https://rwnews.tw'
INDEX_JSON_URL = f'{BASE_URL}/js/viewindexnews300.json'

CATEGORIES = {
    'politics': {'label': '政治'},
    'society': {'label': '社會'},
    'cross_strait': {'label': '兩岸'},
}
MAX_URLS_PER_CATEGORY = 30
ARTICLE_RE = re.compile(r'^https://rwnews\.tw/article\.php\?news=\d+$')
URL_CATEGORY_MAP = {}

POLITICS_KEYWORDS = (
    '總統',
    '總統府',
    '行政院',
    '立法院',
    '立委',
    '市長',
    '議員',
    '政府',
    '部長',
    '國會',
    '國民黨',
    '民進黨',
    '民眾黨',
    '賴清德',
    '柯文哲',
    '盧秀燕',
    '高雄市長',
    '軍售',
    '外交',
    '選舉',
    '黨主席',
)
SOCIETY_KEYWORDS = (
    '車禍',
    '死亡',
    '警方',
    '警',
    '檢',
    '法院',
    '火災',
    '地震',
    '花蓮',
    '災',
    '詐欺',
    '司法',
    '交保',
    '輕生',
    '墜',
    '案',
    '民眾',
)
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

    entries = _fetch_index_entries(session)
    buckets = {
        'politics': _filter_entries(entries, POLITICS_KEYWORDS),
        'society': _filter_entries(entries, SOCIETY_KEYWORDS),
        'cross_strait': _filter_entries(entries, CROSS_STRAIT_KEYWORDS),
    }

    all_urls = []
    seen = set()
    for category in ('politics', 'society', 'cross_strait'):
        added = 0
        for entry in buckets[category]:
            url = entry['url']
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

        canonical = _extract_canonical_url(soup) or normalized_url
        title = _extract_title(soup)
        published_at = base.extract_published_at(soup, [
            ('.article_time', None),
        ])
        image_url = base.extract_image_url(soup)
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


def _fetch_index_entries(session):
    try:
        resp = session.get(
            INDEX_JSON_URL,
            headers={
                'Accept': 'application/json,text/javascript,*/*;q=0.01',
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': f'{BASE_URL}/',
            },
            timeout=20,
        )
        resp.encoding = 'utf-8'
        data = resp.json()
    except Exception as e:
        print(f"[{SOURCE_CODE}] Failed to fetch index JSON: {e}")
        return []

    entries = []
    for item in data or []:
        article_id = item.get('id')
        if not article_id:
            continue
        text = ' '.join(
            part for part in (
                item.get('title'),
                item.get('maintype'),
                item.get('subtype'),
                item.get('description'),
            )
            if part
        )
        entries.append({
            'url': _normalize_url(f'{BASE_URL}/article.php?news={article_id}'),
            'text': text,
        })
    return entries


def _filter_entries(entries, keywords):
    return [entry for entry in entries if any(keyword in entry.get('text', '') for keyword in keywords)]


def _ensure_headers(session):
    session.headers.update({
        'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate',
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    })


def _normalize_url(url):
    parsed = urlparse(url)
    if parsed.query:
        news = parse_qs(parsed.query).get('news', [''])[0]
        if news:
            return f'{parsed.scheme}://{parsed.netloc}{parsed.path}?news={news}'
    return url.split('#')[0].rstrip('/')


def _extract_canonical_url(soup):
    og_url = soup.select_one('meta[property="og:url"]')
    if og_url and og_url.get('content'):
        return _normalize_url(urljoin(BASE_URL, og_url['content']))
    node = soup.select_one('link[rel="canonical"]')
    if node and node.get('href'):
        return _normalize_url(urljoin(BASE_URL, node['href']))
    return None


def _extract_title(soup):
    title_node = soup.select_one('h1')
    if title_node:
        return title_node.get_text(' ', strip=True)
    og_title = soup.select_one('meta[property="og:title"]')
    if og_title and og_title.get('content'):
        return og_title['content'].strip()
    return ""


def _extract_clean_text(soup):
    article_node = soup.select_one('#article_text') or soup.select_one('article')
    if not article_node:
        return ""
    content = BeautifulSoup(str(article_node), 'lxml')
    for tag in content.select('script, style, iframe, img, figure'):
        tag.decompose()
    parts = []
    for line in content.get_text('\n', strip=True).splitlines():
        clean = re.sub(r'\s+', ' ', line).strip()
        if clean:
            parts.append(clean)
    return "\n".join(parts)
