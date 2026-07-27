"""寰宇新聞 GLOBALNEWS 爬蟲"""
import re
from datetime import timezone, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from dateutil import parser

import base

SOURCE_CODE = 'GLOBALNEWS'
BASE_URL = 'https://globalnewstv.com.tw'
IMPORTANT_CATEGORY = '%e4%bb%8a%e6%97%a5%e9%87%8d%e8%a6%81%e6%96%b0%e8%81%9e'
ARTICLE_RE = re.compile(r'^https://globalnewstv\.com\.tw/\d{6}/\d+/?$')
MAX_URLS_PER_CATEGORY = 30
MAX_CATEGORY_PAGES = 8
URL_CATEGORY_MAP = {}

CATEGORIES = {
    'politics': {'label': '政治'},
    'society': {'label': '社會'},
    'cross_strait': {'label': '兩岸'},
}

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
    '蔣萬安',
    '軍售',
    '外交部',
    '國防部',
    '政策',
    '選舉',
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
    '住戶',
    '交通',
    '長照',
    '醫',
    '孕婦',
    '高溫',
    '失蹤',
    '救',
    '違規',
    '大樓',
    '民眾',
    '疫情',
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
    '北韓',
    '中朝',
)


def get_list_urls(session):
    _ensure_headers(session)
    URL_CATEGORY_MAP.clear()

    entries = _fetch_important_entries(session)
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
        published_at = _extract_published_at(soup)
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


def _fetch_important_entries(session):
    merged = {}
    for page in range(1, MAX_CATEGORY_PAGES + 1):
        list_url = _category_url(page)
        try:
            resp = session.get(list_url, timeout=20)
            resp.encoding = 'utf-8'
            soup = BeautifulSoup(resp.text, 'lxml')
            page_entries = _extract_entries(soup)
            if not page_entries:
                break
            for entry in page_entries:
                existing = merged.setdefault(entry['url'], {'url': entry['url'], 'text': ''})
                if entry['text'] and entry['text'] not in existing['text']:
                    existing['text'] = f"{existing['text']} {entry['text']}".strip()
        except Exception as e:
            print(f"[{SOURCE_CODE}] Failed to fetch important page {page}: {e}")
            break

    return list(merged.values())


def _category_url(page):
    if page <= 1:
        return f'{BASE_URL}/category/{IMPORTANT_CATEGORY}/'
    return f'{BASE_URL}/category/{IMPORTANT_CATEGORY}/page/{page}/'


def _extract_entries(soup):
    entries = []
    for a in soup.select('a[href]'):
        full_url = _normalize_url(urljoin(BASE_URL, a.get('href', '')))
        if not ARTICLE_RE.match(full_url):
            continue
        item = a.find_parent('article') or a.find_parent('div') or a
        text = item.get_text(' ', strip=True) or a.get_text(' ', strip=True)
        entries.append({'url': full_url, 'text': text})
    return entries


def _filter_entries(entries, keywords):
    result = []
    for entry in entries:
        if any(keyword in entry.get('text', '') for keyword in keywords):
            result.append(entry)
    return result


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


def _extract_title(soup):
    title_node = soup.select_one('h1.jeg_post_title') or soup.select_one('h1')
    if title_node:
        return title_node.get_text(' ', strip=True)

    og_title = soup.select_one('meta[property="og:title"]')
    if og_title and og_title.get('content'):
        return og_title['content'].split(' - 寰宇新聞網', 1)[0].strip()
    return ""


def _extract_published_at(soup):
    node = soup.select_one('meta[property="article:published_time"]')
    if node and node.get('content'):
        try:
            dt = parser.parse(node['content'])
            if dt.tzinfo:
                dt = dt.astimezone(timezone(timedelta(hours=8)))
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass
    return base.extract_published_at(soup, [
        ('.jeg_meta_date', None),
    ])


def _extract_clean_text(soup):
    article_node = soup.select_one('.entry-content .content-inner') or soup.select_one('.entry-content')
    if not article_node:
        return ""

    parts = []
    for item in article_node.select('p'):
        clean = _clean_text(item.get_text(' ', strip=True))
        if clean:
            parts.append(clean)
    return "\n".join(parts)


def _clean_text(text):
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text).strip()
    if not text or text.startswith(('Tags:', '標籤', '延伸閱讀')):
        return ""
    return text
