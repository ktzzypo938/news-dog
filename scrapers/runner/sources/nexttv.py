"""壹電視 NEXTTV 爬蟲"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import base

SOURCE_CODE = 'NEXTTV'
BASE_URL = 'https://www.nexttv.com.tw'

CATEGORIES = {
    'politics': {
        'label': '政治',
        'path': 'Politics',
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
MAX_CATEGORY_PAGES = 8
ARTICLE_RE = re.compile(
    r'^https://www\.nexttv\.com\.tw/NextTV/News/Home/[A-Za-z]+/\d{4}-\d{2}-\d{2}/\d+\.html$'
)
URL_CATEGORY_MAP = {}


def get_list_urls(session):
    _ensure_headers(session)
    URL_CATEGORY_MAP.clear()

    all_urls = []
    seen = set()
    for category, cfg in CATEGORIES.items():
        urls = _fetch_category_urls(session, category, cfg['path'])
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
        published_at = base.extract_published_at(soup, [
            ('.article-assist .time', None),
            ('span.time', None),
        ])
        image_url = base.extract_image_url(soup)
        clean_text = _extract_clean_text(soup)
        photographer = _extract_origin(soup)

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


def _fetch_category_urls(session, category, path):
    urls = []
    for page in range(1, MAX_CATEGORY_PAGES + 1):
        list_url = _category_url(path, page)
        try:
            resp = session.get(list_url, timeout=20)
            resp.encoding = 'utf-8'
            soup = BeautifulSoup(resp.text, 'lxml')
            page_urls = _extract_category_urls(soup, path)
            if not page_urls:
                break
            urls.extend(page_urls)
            if len(dict.fromkeys(urls)) >= MAX_URLS_PER_CATEGORY:
                break
        except Exception as e:
            print(f"[{SOURCE_CODE}] Failed to fetch {category} page {page}: {e}")
            break

    return list(dict.fromkeys(urls))


def _category_url(path, page):
    base_url = f'{BASE_URL}/NextTV/News/Home/{path}/'
    if page <= 1:
        return base_url
    return f'{base_url}?pp={(page - 1) * 5}'


def _extract_category_urls(soup, path):
    urls = []
    marker = f'/NextTV/News/Home/{path}/'
    for a in soup.select(f'a[href*="{marker}"][href$=".html"]'):
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


def _extract_title(soup):
    title_node = soup.select_one('h1.article-title') or soup.select_one('h1')
    if title_node:
        return title_node.get_text(' ', strip=True)

    og_title = soup.select_one('meta[property="og:title"]')
    if og_title and og_title.get('content'):
        return og_title['content'].split('_', 1)[0].strip()
    return ""


def _extract_clean_text(soup):
    article_node = soup.select_one('.article-main')
    if not article_node:
        return ""

    content = BeautifulSoup(str(article_node), 'lxml')
    for tag in content.select('script, style, iframe, img, video, figure'):
        tag.decompose()

    parts = []
    for item in content.select('p'):
        clean = _clean_text(item.get_text(' ', strip=True))
        if clean:
            parts.append(clean)

    if parts:
        return "\n".join(parts)

    return "\n".join(
        clean for clean in (_clean_text(line) for line in content.get_text('\n', strip=True).splitlines()) if clean
    )


def _clean_text(text):
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return ""
    if text.startswith(('延伸閱讀', '熱門新聞', '推薦文章', '點閱：')):
        return ""
    return text


def _extract_origin(soup):
    node = soup.select_one('.article-assist .origin')
    if not node:
        return None
    value = re.sub(r'\s+', ' ', node.get_text(' ', strip=True)).strip()
    return value or None
