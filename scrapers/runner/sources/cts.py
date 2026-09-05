"""華視新聞 CTS 爬蟲"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import base

SOURCE_CODE = 'CTS'
BASE_URL = 'https://news.cts.com.tw'

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
    _ensure_headers(session)
    URL_CATEGORY_MAP.clear()

    all_urls = []
    seen = set()
    for category, cfg in CATEGORIES.items():
        if category == 'cross_strait':
            urls = _fetch_cross_strait_urls(session, cfg['paths'])
        else:
            urls = _fetch_category_urls(session, category, cfg['path'], cfg['tag'])

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

        canonical = _extract_canonical_url(soup) or normalized_url
        title = _extract_title(soup)
        published_at = base.extract_published_at(soup, [
            ('.news-detail-time', None),
            ('.article-time', None),
            ('.date', None),
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


def _fetch_category_urls(session, category, path, expected_tag):
    urls = []
    for page in range(1, MAX_CATEGORY_PAGES + 1):
        list_url = f'{BASE_URL}/{path}?page={page}'
        try:
            resp = session.get(list_url, timeout=20)
            resp.encoding = 'utf-8'
            soup = BeautifulSoup(resp.text, 'lxml')
            page_urls = _extract_card_urls(soup, expected_tag=expected_tag)
            if not page_urls:
                break
            urls.extend(page_urls)
            if len(dict.fromkeys(urls)) >= MAX_URLS_PER_CATEGORY:
                break
        except Exception as e:
            print(f"[{SOURCE_CODE}] Failed to fetch {category} page {page}: {e}")
            break

    return list(dict.fromkeys(urls))


def _fetch_cross_strait_urls(session, paths):
    urls = []
    for path in paths:
        for page in range(1, MAX_CROSS_STRAIT_PAGES + 1):
            list_url = f'{BASE_URL}/{path}?page={page}'
            try:
                resp = session.get(list_url, timeout=20)
                resp.encoding = 'utf-8'
                soup = BeautifulSoup(resp.text, 'lxml')
                page_urls = _extract_card_urls(soup, keyword_filter=True)
                if not page_urls:
                    break
                urls.extend(page_urls)
                if len(dict.fromkeys(urls)) >= MAX_URLS_PER_CATEGORY:
                    return list(dict.fromkeys(urls))
            except Exception as e:
                print(f"[{SOURCE_CODE}] Failed to fetch cross_strait {path} page {page}: {e}")
                break

    return list(dict.fromkeys(urls))


def _extract_card_urls(soup, expected_tag=None, keyword_filter=False):
    urls = []
    for card in soup.select('a.news-list-card[href]'):
        full_url = _normalize_url(urljoin(BASE_URL, card.get('href', '')))
        if not ARTICLE_RE.match(full_url):
            continue

        if expected_tag:
            tag_node = card.select_one('.news-tag')
            tag_text = tag_node.get_text(' ', strip=True) if tag_node else ''
            if expected_tag not in tag_text:
                continue

        if keyword_filter and not _looks_cross_strait(card.get_text(' ', strip=True)):
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


def _extract_title(soup):
    title_node = soup.select_one('h1.news-detail-title') or soup.select_one('h1')
    if title_node:
        return title_node.get_text(' ', strip=True)

    og_title = soup.select_one('meta[property="og:title"]')
    if og_title and og_title.get('content'):
        return og_title['content'].split(' - 華視新聞網', 1)[0].strip()
    return ""


def _extract_clean_text(soup):
    article_node = soup.select_one('.article-content')
    if not article_node:
        article_node = soup.select_one('article')
    if not article_node:
        return ""

    content = BeautifulSoup(str(article_node), 'lxml')
    for tag in content.select(
        'script, style, iframe, img, video, figure, aside, .article-source, '
        '.social-share, .news-tag, .related-news, .recommend, .advertise'
    ):
        tag.decompose()
    base.remove_promo_blocks(content)

    lines = []
    for line in content.get_text('\n', strip=True).splitlines():
        clean = _clean_text(line)
        if clean:
            lines.append(clean)

    return "\n".join(lines)


def _clean_text(text):
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return ""
    if text.startswith(('點我下載華視新聞APP', '按讚加入華視新聞粉絲團', '【更多新聞】', '責任編輯：')):
        return ""
    return text
