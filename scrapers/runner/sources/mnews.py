"""鏡新聞 MNEWS 爬蟲"""
import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import base

SOURCE_CODE = 'MNEWS'
BASE_URL = 'https://www.mnews.tw'
LOAD_MORE_ACTION_ID = '2cacc308e0a3da59e8e691a5b807e6e5fdbb7817'

CATEGORIES = {
    'politics': {
        'label': '政治',
        'slug': 'pol',
    },
    'society': {
        'label': '社會',
        'slug': 'soc',
    },
    'cross_strait': {
        'label': '兩岸',
        'slugs': ('chengxi', 'arms', 'int', 'pol'),
    },
}
MAX_URLS_PER_CATEGORY = 30
PAGE_SIZE = 12
MAX_ACTION_PAGES = 4
ARTICLE_RE = re.compile(r'^https://www\.mnews\.tw/story/[A-Za-z0-9_-]+$')
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
    '軍售',
)


def get_list_urls(session):
    _ensure_headers(session)
    URL_CATEGORY_MAP.clear()

    all_urls = []
    seen = set()
    for category, cfg in CATEGORIES.items():
        if category == 'cross_strait':
            urls = _fetch_cross_strait_urls(session, cfg['slugs'])
        else:
            urls = _fetch_category_urls(session, category, cfg['slug'])

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

        canonical = _extract_canonical_url(soup) or normalized_url
        title = _extract_title(soup)
        published_at = base.extract_published_at(soup)
        image_url = base.extract_image_url(soup)
        clean_text = _extract_clean_text(soup)
        photographer = _extract_photographer(soup)

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


def _fetch_category_urls(session, category, slug):
    entries = _fetch_category_entries(session, slug)
    urls = []
    for entry in entries:
        if _is_marketing_entry(entry):
            continue
        url = entry['url']
        if url not in urls:
            urls.append(url)
        if len(urls) >= MAX_URLS_PER_CATEGORY:
            break
    return urls


def _fetch_cross_strait_urls(session, slugs):
    urls = []
    for slug in slugs:
        entries = _fetch_category_entries(session, slug)
        for entry in entries:
            if _is_marketing_entry(entry):
                continue
            if not _looks_cross_strait(entry.get('text', '')):
                continue
            url = entry['url']
            if url not in urls:
                urls.append(url)
            if len(urls) >= MAX_URLS_PER_CATEGORY:
                return urls
    return urls


def _fetch_category_entries(session, slug):
    list_url = f'{BASE_URL}/category/{slug}'
    entries = []
    try:
        resp = session.get(list_url, timeout=20)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'lxml')
        entries.extend(_extract_entries_from_html(soup))
    except Exception as e:
        print(f"[{SOURCE_CODE}] Failed to fetch category {slug}: {e}")
        return entries

    skip = PAGE_SIZE
    for _ in range(MAX_ACTION_PAGES):
        more_entries = _fetch_action_entries(session, slug, skip)
        if not more_entries:
            break
        entries.extend(more_entries)
        skip += PAGE_SIZE
        if len(entries) >= MAX_URLS_PER_CATEGORY + 8:
            break

    unique = []
    seen = set()
    for entry in entries:
        url = entry.get('url')
        if not url or url in seen:
            continue
        seen.add(url)
        unique.append(entry)
    return unique


def _extract_entries_from_html(soup):
    entries = []
    scope = soup.select_one('[class*="category_listWrapper"]') or soup
    for a in scope.select('a[href^="/story/"]'):
        href = a.get('href', '')
        url = _normalize_url(urljoin(BASE_URL, href))
        if not ARTICLE_RE.match(url):
            continue
        text = a.get_text(' ', strip=True)
        entries.append({'url': url, 'slug': href.rsplit('/', 1)[-1], 'text': text})
    return entries


def _fetch_action_entries(session, slug, skip):
    list_url = f'{BASE_URL}/category/{slug}'
    payload = [{
        'skip': skip,
        'categorySlug': slug,
        'pageSize': PAGE_SIZE,
        'isWithCount': False,
        'filteredSlug': [],
    }]
    headers = {
        'Accept': 'text/x-component',
        'Content-Type': 'text/plain;charset=UTF-8',
        'Next-Action': LOAD_MORE_ACTION_ID,
        'Origin': BASE_URL,
        'Referer': list_url,
    }
    try:
        resp = session.post(
            list_url,
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers=headers,
            timeout=20,
        )
        resp.encoding = 'utf-8'
        data = _parse_action_response(resp.text)
    except Exception as e:
        print(f"[{SOURCE_CODE}] Failed to fetch more {slug} skip {skip}: {e}")
        return []

    entries = []
    for item in data.get('allPosts', []):
        slug_value = item.get('slug')
        if not slug_value:
            continue
        url = _normalize_url(urljoin(BASE_URL, f'/story/{slug_value}'))
        if not ARTICLE_RE.match(url):
            continue
        entries.append({
            'url': url,
            'slug': slug_value,
            'text': item.get('name') or '',
        })
    return entries


def _parse_action_response(text):
    for line in text.splitlines():
        if not line.startswith('1:'):
            continue
        try:
            return json.loads(line[2:])
        except Exception:
            return {}
    return {}


def _is_marketing_entry(entry):
    slug = entry.get('slug') or ''
    text = entry.get('text') or ''
    if slug in {'aboutus', 'privacy', 'press-self-regulation', 'webauthorization'}:
        return True
    if re.search(r'(?:^|[0-9])(mkt|pr)[0-9]', slug):
        return True
    return text.startswith(('特企', '【生活特輯】', '【財經特輯】', '《鏡好買》'))


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


def _extract_title(soup):
    title_node = soup.select_one('h1')
    if title_node:
        return title_node.get_text(' ', strip=True)

    og_title = soup.select_one('meta[property="og:title"]')
    if og_title and og_title.get('content'):
        return og_title['content'].strip()
    return ""


def _extract_clean_text(soup):
    parts = []
    lead = soup.select_one('article')
    if lead:
        clean = _clean_text(lead.get_text(' ', strip=True))
        if clean:
            parts.append(clean)

    content_node = soup.select_one('[class*="story_contentWrapper"]')
    if content_node:
        content = BeautifulSoup(str(content_node), 'lxml')
        for tag in content.select('script, style, iframe, img, figure, aside'):
            tag.decompose()
        for item in content.select('p'):
            clean = _clean_text(item.get_text(' ', strip=True))
            if clean and clean not in parts:
                parts.append(clean)

    return "\n".join(parts)


def _clean_text(text):
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return ""
    if text.startswith(('延伸閱讀', '熱門新聞', '推薦文章', '更新時間')):
        return ""
    return text


def _extract_photographer(soup):
    node = soup.select_one('[class*="photo_credit"], [class*="imageCredit"], figcaption')
    if not node:
        return None
    credit = base.extract_photographer(node.get_text(' ', strip=True))
    if credit:
        return credit
    return None
