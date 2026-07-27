"""工商時報 Commercial Times 爬蟲"""
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

import base

SOURCE_CODE = 'COMMERCIALTIMES'
BASE_URL = 'https://www.ctee.com.tw'

SOCIETY_KEYWORDS = (
    '社會',
    '民生',
    '生活',
    '勞工',
    '就業',
    '醫療',
    '健保',
    '教育',
    '交通',
    '消費',
    '食安',
    '詐騙',
    '法院',
    '檢調',
    '警方',
    '地震',
    '災',
    '房市',
)

CATEGORIES = {
    'politics': {
        'label': '政治',
        'urls': (
            'https://www.ctee.com.tw/policy/p-highlights',
            'https://www.ctee.com.tw/policy/p-prime',
            'https://www.ctee.com.tw/policy/macro',
        ),
    },
    'society': {
        'label': '社會',
        'urls': (
            'https://www.ctee.com.tw/policy/p-prime',
            'https://www.ctee.com.tw/policy/p-tax',
            'https://www.ctee.com.tw/livenews/policy',
        ),
        'keywords': SOCIETY_KEYWORDS,
        'fallback_unfiltered': True,
    },
    'cross_strait': {
        'label': '兩岸',
        'urls': (
            'https://www.ctee.com.tw/china',
            'https://www.ctee.com.tw/china/cross-strait',
            'https://www.ctee.com.tw/china/c-highlights',
        ),
    },
}

MAX_URLS_PER_CATEGORY = 30
MAX_CANDIDATES_PER_CATEGORY = MAX_URLS_PER_CATEGORY * 3
ARTICLE_RE = re.compile(r'^https://www\.ctee\.com\.tw/news/\d{14}-\d{6}$')
URL_CATEGORY_MAP = {}


def get_list_urls(session):
    _ensure_headers(session)
    URL_CATEGORY_MAP.clear()

    all_urls = []
    seen = set()
    for category, cfg in CATEGORIES.items():
        urls = _fetch_category_urls(session, cfg)
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
            ('time', None),
        ])
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


def _fetch_category_urls(session, cfg):
    filtered_entries = []
    unfiltered_entries = []
    keywords = cfg.get('keywords') or ()

    for list_url in cfg['urls']:
        try:
            resp = session.get(list_url, timeout=20)
            resp.encoding = 'utf-8'
            if resp.status_code >= 400:
                continue
            soup = BeautifulSoup(resp.text, 'lxml')
            entries = _extract_entries(soup)
            unfiltered_entries.extend(entries)
            for entry in entries:
                if not keywords or _contains_keyword(entry['text'], keywords):
                    filtered_entries.append(entry)
            if len(_dedupe_entries(filtered_entries)) >= MAX_CANDIDATES_PER_CATEGORY:
                break
        except Exception as e:
            print(f"[{SOURCE_CODE}] Failed to fetch list {list_url}: {e}")

    entries = _dedupe_entries(filtered_entries)
    if cfg.get('fallback_unfiltered') and len(entries) < MAX_URLS_PER_CATEGORY:
        by_url = {entry['url']: entry for entry in entries}
        for entry in _dedupe_entries(unfiltered_entries):
            by_url.setdefault(entry['url'], entry)
            if len(by_url) >= MAX_CANDIDATES_PER_CATEGORY:
                break
        entries = list(by_url.values())
    return [entry['url'] for entry in entries]


def _extract_entries(soup):
    entries = []
    for anchor in soup.select('a[href*="/news/"]'):
        url = _normalize_url(urljoin(BASE_URL, anchor.get('href', '')))
        if not ARTICLE_RE.match(url):
            continue
        parent = anchor.find_parent('article') or anchor.find_parent('li') or anchor.find_parent('div') or anchor
        text = parent.get_text(' ', strip=True)
        if not text:
            img = anchor.select_one('img[alt]') or parent.select_one('img[alt]')
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
        return node.get_text(' ', strip=True)
    og_title = soup.select_one('meta[property="og:title"]')
    if og_title and og_title.get('content'):
        return og_title['content'].strip()
    return ""


def _extract_clean_text(soup):
    content_node = soup.select_one('article') or soup.select_one('.article-wrap')
    if not content_node:
        return ""

    content = BeautifulSoup(str(content_node), 'lxml')
    for tag in content.select('script, style, iframe, img, figure, aside, .ad, .social, .article__tag'):
        tag.decompose()

    lines = []
    skip_prefixes = (
        '切換文字大小',
        '複製文章連結',
        '分享至臉書',
        '以Line分享',
        '參與討論',
        '友善列印',
        '已將目前網頁',
        '延伸閱讀',
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
    for node in soup.select('figcaption, .content__body, img[alt]'):
        text = node.get('alt', '') if node.name == 'img' else node.get_text(' ', strip=True)
        photographer = base.extract_photographer(text)
        if photographer:
            return _clean_photographer(photographer)
    return None


def _clean_photographer(text):
    text = _normalize_text(text)
    for marker in (
        '切換文字大小',
        '複製文章連結',
        '分享至臉書',
        '以Line分享',
        '參與討論',
        '友善列印',
        '已將目前網頁',
    ):
        text = text.split(marker, 1)[0].strip()
    return text[:500] if text else None


def _normalize_text(text):
    return re.sub(r'\s+', ' ', str(text)).strip() if text else ""
