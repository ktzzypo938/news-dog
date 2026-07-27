"""天下雜誌 CW 爬蟲"""
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

import base

SOURCE_CODE = 'CW'
BASE_URL = 'https://www.cw.com.tw'

CATEGORIES = {
    'politics': {
        'label': '政治',
        'urls': (
            'https://www.cw.com.tw/subchannel.action?idSubChannel=375',
            'https://www.cw.com.tw/masterChannel.action?idMasterChannel=77',
        ),
    },
    'society': {
        'label': '社會',
        'urls': (
            'https://www.cw.com.tw/subchannel.action?idSubChannel=377',
            'https://www.cw.com.tw/masterChannel.action?idMasterChannel=77',
        ),
    },
    'cross_strait': {
        'label': '兩岸',
        'urls': (
            'https://www.cw.com.tw/subchannel.action?idSubChannel=16',
            'https://www.cw.com.tw/masterChannel.action?idMasterChannel=9',
        ),
    },
}

MAX_URLS_PER_CATEGORY = 30
ARTICLE_RE = re.compile(r'^https://www\.cw\.com\.tw/article/\d+$')
URL_CATEGORY_MAP = {}


def get_list_urls(session):
    _ensure_headers(session)
    URL_CATEGORY_MAP.clear()

    all_urls = []
    seen = set()
    for category, cfg in CATEGORIES.items():
        urls = _fetch_category_urls(session, cfg['urls'])
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
        photographer = _extract_photographer(soup)
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
        if photographer:
            result["imagePhotographer"] = photographer
        return result
    except Exception as e:
        print(f"[{SOURCE_CODE}] Error scraping {url}: {e}")
        return None


def get_url_category(url):
    category = URL_CATEGORY_MAP.get(_normalize_url(url))
    return CATEGORIES.get(category, {}).get('label', '未知')


def _fetch_category_urls(session, urls):
    entries = []
    for list_url in urls:
        try:
            resp = session.get(list_url, timeout=20)
            resp.encoding = 'utf-8'
            if resp.status_code >= 400:
                continue
            soup = BeautifulSoup(resp.text, 'lxml')
            entries.extend(_extract_entries(soup))
        except Exception as e:
            print(f"[{SOURCE_CODE}] Failed to fetch list {list_url}: {e}")
    return [entry['url'] for entry in _dedupe_entries(entries)]


def _extract_entries(soup):
    entries = []
    for item in soup.select('.articleGroup section.article'):
        anchor = item.select_one('a[href*="/article/"]')
        if not anchor:
            continue
        url = _normalize_url(urljoin(BASE_URL, anchor.get('href', '')))
        if not ARTICLE_RE.match(url):
            continue
        text = item.get_text(' ', strip=True)
        if not text:
            img = item.select_one('img[alt]')
            text = img.get('alt', '') if img else ''
        entries.append({'url': url, 'text': _normalize_text(text)})
    return entries


def _dedupe_entries(entries):
    by_url = {}
    for entry in entries:
        current = by_url.get(entry['url'])
        if not current or len(entry.get('text', '')) > len(current.get('text', '')):
            by_url[entry['url']] = entry
    return list(by_url.values())


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


def _extract_canonical_url(soup):
    node = soup.select_one('link[rel="canonical"]')
    if node and node.get('href'):
        return _normalize_url(urljoin(BASE_URL, node['href']))
    og_url = soup.select_one('meta[property="og:url"]')
    if og_url and og_url.get('content'):
        return _normalize_url(urljoin(BASE_URL, og_url['content']))
    return None


def _extract_title(soup):
    node = soup.select_one('h1')
    if node:
        return _clean_title(node.get_text(' ', strip=True))
    og_title = soup.select_one('meta[property="og:title"]')
    if og_title and og_title.get('content'):
        return _clean_title(og_title['content'])
    return ""


def _clean_title(title):
    return str(title).split('｜天下雜誌', 1)[0].strip()


def _extract_clean_text(soup):
    content_node = (
        soup.select_one('.article__content')
        or soup.select_one('#article-full-content')
        or soup.select_one('article')
    )
    if not content_node:
        return ""

    content = BeautifulSoup(str(content_node), 'lxml')
    for tag in content.select(
        'script, style, iframe, img, figure, aside, .leaflet, .extended-reading, '
        '.article__keyword, .article__recommend, .native-ad, .paywall, .subscription'
    ):
        tag.decompose()

    lines = []
    skip_prefixes = (
        '訂戶獨享',
        '登入/註冊',
        '瞭解更多',
        '延伸閱讀',
        '相關文章',
        '責任編輯',
        '核稿編輯',
        'App內開啟',
        '訂閱天下',
    )
    for line in content.get_text('\n', strip=True).splitlines():
        text = _normalize_text(line)
        if not text:
            continue
        if any(text.startswith(prefix) for prefix in skip_prefixes):
            continue
        lines.append(text)

    return "\n".join(lines)


def _extract_photographer(soup):
    for node in soup.select('figcaption, .caption, .pic-info, img[alt]'):
        text = node.get('alt', '') if node.name == 'img' else node.get_text(' ', strip=True)
        photographer = base.extract_photographer(text)
        if photographer:
            return photographer
        m = re.search(r'圖片來源[：:]\s*([^，。／（）()\s]{1,30})', text)
        if m:
            return m.group(1).strip()
    return None


def _normalize_text(text):
    return re.sub(r'\s+', ' ', str(text)).strip() if text else ""
