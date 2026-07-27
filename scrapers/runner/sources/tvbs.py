"""TVBS 新聞爬蟲"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import base

SOURCE_CODE = 'TVBS'
BASE_URL = 'https://news.tvbs.com.tw'

CATEGORIES = {
    'politics': {
        'slug': 'politics',
        'label': '政治',
    },
    'society': {
        'slug': 'local',
        'label': '社會',
    },
    'lifestyle': {
        'slug': 'life',
        'label': '生活',
    },
    'cross_strait': {
        'slug': 'china',
        'label': '兩岸',
    },
}
MAX_URLS_PER_CATEGORY = 30
URL_CATEGORY_MAP = {}


def get_list_urls(session):
    _ensure_headers(session)
    URL_CATEGORY_MAP.clear()

    all_urls = []
    for category, cfg in CATEGORIES.items():
        urls = _fetch_category_urls(session, category, cfg['slug'])
        for url in urls:
            all_urls.append(url)
            URL_CATEGORY_MAP[url] = category

    return list(dict.fromkeys(all_urls))


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
            ('div.author', None),
        ])
        image_url = base.extract_image_url(soup)

        content_node = (
            soup.select_one('#news_detail_div')
            or soup.select_one('div[itemprop="articleBody"]')
            or soup.select_one('.article_content')
        )
        clean_text = _extract_clean_text(content_node) if content_node else ""
        photographer = _extract_photographer(soup, content_node)

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
    normalized_url = _normalize_url(url)
    category = URL_CATEGORY_MAP.get(normalized_url)
    if not category:
        for key, cfg in CATEGORIES.items():
            if f"/{cfg['slug']}/" in normalized_url:
                category = key
                break
    return CATEGORIES.get(category, {}).get('label', '未知')


def _fetch_category_urls(session, category, slug):
    list_url = f'{BASE_URL}/{slug}'
    article_re = re.compile(rf'^{re.escape(BASE_URL)}/{re.escape(slug)}/\d+$')
    urls = []
    try:
        resp = session.get(list_url, timeout=20)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'lxml')
        for a in soup.select(f'a[href*="/{slug}/"]'):
            full_url = _normalize_url(urljoin(BASE_URL, a.get('href', '')))
            if not article_re.match(full_url):
                continue
            urls.append(full_url)
            if len(dict.fromkeys(urls)) >= MAX_URLS_PER_CATEGORY:
                break
    except Exception as e:
        print(f"[{SOURCE_CODE}] Failed to fetch {category}: {e}")

    return list(dict.fromkeys(urls))[:MAX_URLS_PER_CATEGORY]


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
    title_node = soup.select_one('h1.title') or soup.select_one('h1')
    if title_node:
        return title_node.get_text(' ', strip=True)

    og_title = soup.select_one('meta[property="og:title"]')
    if og_title and og_title.get('content'):
        return og_title['content'].split('│TVBS新聞網', 1)[0].strip()
    return ""


def _extract_clean_text(content_node):
    content = BeautifulSoup(str(content_node), 'lxml')

    marker = content.select_one('#article-end-marker')
    if marker:
        for sibling in list(marker.next_siblings):
            sibling.extract()
        marker.decompose()

    for tag in content.select(
        'script, style, iframe, img, '
        '.ad_pc, .ad_mo, .adsbox, .guangxuan, .widely_declared, '
        '.article_ad, .article_community, div[align="center"]'
    ):
        tag.decompose()
    base.remove_promo_blocks(content)

    paragraphs = []
    for line in content.get_text('\n', strip=True).splitlines():
        clean = _clean_text(line)
        if clean:
            paragraphs.append(clean)
    return "\n".join(paragraphs)


def _clean_text(text):
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text).strip()
    if not text or text in {'&nbsp', '&nbsp;', 'nbsp'}:
        return ""
    if text.startswith(('延伸閱讀：', '更多 TVBS 報導', '在 Google 新聞上關注 TVBS')):
        return ""
    return text


def _extract_photographer(soup, content_node):
    for node in soup.select('article img[alt], article img[title]'):
        credit = _extract_image_credit(node.get('alt') or node.get('title') or '')
        if credit:
            return credit

    if content_node:
        for node in content_node.select('img[alt], img[title]'):
            credit = _extract_image_credit(node.get('alt') or node.get('title') or '')
            if credit:
                return credit
    return None


def _extract_image_credit(text):
    if not text:
        return None
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return None

    credit = base.extract_photographer(text)
    if credit:
        return _normalize_credit(credit)

    m = re.search(r'[（(]圖[／/](.+?)[）)]', text)
    if m:
        return _normalize_credit(m.group(1))
    return None


def _normalize_credit(credit):
    if not credit:
        return None
    credit = re.sub(r'\s+', ' ', credit).strip()
    credit = re.sub(r'^(圖片|照片|圖|資料照片|資料照)[：:／/，,、\s]*', '', credit).strip()
    credit = re.sub(r'^翻攝(?:自)?', '', credit).strip()
    credit = re.sub(r'(提供|攝影|攝|資料照)$', '', credit).strip()
    if credit in {'圖片', '照片', '圖', '翻攝', '資料照'}:
        return None
    return credit or None
