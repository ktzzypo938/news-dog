"""上報 UpMedia 爬蟲"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import base

SOURCE_CODE = 'UPMEDIA'
BASE_URL = 'https://www.upmedia.mg'

CATEGORY_PAGES = {
    'politics': {
        'url': 'https://www.upmedia.mg/tw/focus/politics',
        'selector': 'div.sub-three.lift-news a[href]',
        'pages': 2,
    },
    'society': {
        'url': 'https://www.upmedia.mg/tw/focus/society',
        'selector': 'div.sub-three.lift-news a[href]',
        'pages': 2,
    },
    'cross_strait': {
        'url': 'https://www.upmedia.mg/tw/international/cross-strait-affairs',
        'selector': 'div.inter-list a[href]',
        'pages': 3,
    },
}

MAX_URLS_PER_CATEGORY = 30
ARTICLE_RE = re.compile(r'/tw/.+/\d+$')
URL_CATEGORY_MAP = {}
CATEGORY_LABELS = {
    'politics': '政治',
    'society': '社會',
    'cross_strait': '兩岸',
}


def get_list_urls(session):
    _ensure_headers(session)
    all_urls = []
    URL_CATEGORY_MAP.clear()

    for category, config in CATEGORY_PAGES.items():
        category_urls = []
        for page in range(1, config['pages'] + 1):
            list_url = _with_page(config['url'], page)
            try:
                resp = session.get(list_url, timeout=20)
                resp.encoding = 'utf-8'
                soup = BeautifulSoup(resp.text, 'lxml')
                for a in soup.select(config['selector']):
                    full_url = _normalize_url(urljoin(BASE_URL, a.get('href', '')))
                    if ARTICLE_RE.search(full_url):
                        category_urls.append(full_url)
            except Exception as e:
                print(f"[{SOURCE_CODE}] Failed to fetch {category} list page {page}: {e}")

        for full_url in list(dict.fromkeys(category_urls))[:MAX_URLS_PER_CATEGORY]:
            all_urls.append(full_url)
            URL_CATEGORY_MAP.setdefault(full_url, category)

    return list(dict.fromkeys(all_urls))


def scrape_article(session, url):
    try:
        _ensure_headers(session)
        resp = session.get(
            url,
            headers={'Referer': 'https://www.upmedia.mg/tw/latest-news'},
            timeout=20,
        )
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'lxml')

        canonical = _extract_canonical_url(soup) or _normalize_url(url)
        image_url = base.extract_image_url(soup)

        title_node = soup.select_one('h1') or soup.select_one('meta[property="og:title"]')
        if getattr(title_node, 'name', '') == 'meta':
            title = title_node.get('content', '')
        else:
            title = title_node.get_text(strip=True) if title_node else ""
        title = title.split(' -- 上報', 1)[0].strip()

        published_at = base.extract_published_at(soup)

        content_node = soup.select_one('div.news-box-text')
        if content_node:
            photographer = _extract_photographer(soup)
            clean_text = _extract_clean_text(content_node)
        else:
            photographer = None
            clean_text = ""

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
    return CATEGORY_LABELS.get(category, 'article（分類由列表控制）')


def _ensure_headers(session):
    session.headers.update({
        'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
    })


def _with_page(url, page):
    if page <= 1:
        return url
    return f"{url}?p={page}"


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


def _extract_clean_text(content_node):
    content = BeautifulSoup(str(content_node), 'lxml')
    for tag in content.select(
        'script, style, iframe, .ad-detail, .ad-news, .news-foot, '
        '.news-label, .mbt-text, .img-box, .publish-news'
    ):
        tag.decompose()

    paragraphs = []
    for p in content.select('p'):
        text = _clean_text(p.get_text(' ', strip=True))
        if text:
            paragraphs.append(text)

    if paragraphs:
        return "\n".join(paragraphs)
    return _clean_text(content.get_text('\n', strip=True))


def _clean_text(text):
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return ""
    if text.startswith('（熱門點閱：'):
        return ""
    return text


def _extract_photographer(soup):
    for node in soup.select('div.news-box img[alt], div.news-box-text img[alt], .mbt-text'):
        text = node.get_text(strip=True) if node.name != 'img' else node.get('alt', '')
        photographer = _extract_upmedia_credit(text) or base.extract_photographer(text)
        if photographer:
            return photographer
    return None


def _extract_upmedia_credit(text):
    if not text:
        return None
    match = re.search(r'（([^（）]{1,80})）', text)
    if not match:
        return None
    credit = match.group(1).strip()
    if not any(token in credit for token in ('攝', '擷取', '翻攝', '提供', '資料照')):
        return None
    credit = re.sub(r'攝.*$', '', credit).strip()
    credit = re.sub(r'^(圖|圖片|照片|影音|資料照|資料照片)[／/:：]', '', credit).strip()
    credit = re.sub(r'^資料照[，,、]?', '', credit).strip()
    return credit or None
