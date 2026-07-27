"""民視新聞 FTV 爬蟲"""
import json
import re
from datetime import datetime
from urllib.parse import quote, urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

import base

SOURCE_CODE = 'FTV'
BASE_URL = 'https://www.ftvnews.com.tw'
API_BASE_URL = 'https://ftvapiv2.ftvnews.com.tw/API'

CATEGORIES = {
    'politics': {
        'tag': '政治',
        'label': '政治',
    },
    'society': {
        'tag': '社會',
        'label': '社會',
    },
    'lifestyle': {
        'tag': '生活',
        'label': '生活',
    },
    'cross_strait': {
        'tag': '兩岸',
        'label': '兩岸',
    },
}
MAX_URLS_PER_CATEGORY = 30
MAX_CANDIDATES_PER_CATEGORY = 45
MAX_TAG_PAGES = 3
MAX_FALLBACK_WEB_IDS = 320
MAX_FALLBACK_VIDEO_IDS = 40
ARTICLE_RE = re.compile(r'^https://www\.ftvnews\.com\.tw/news/detail/[A-Za-z0-9]+$')
ARTICLE_ID_RE = re.compile(r'/news/detail/([A-Za-z0-9]+)$')
URL_CATEGORY_MAP = {}
FALLBACK_ARTICLE_CACHE = {}
BLOCKED_MARKERS = (
    'Just a moment...',
    'challenge.cloudflare.com',
    'cf-chl',
    'cf_clearance',
)


def get_list_urls(session):
    _ensure_headers(session)
    URL_CATEGORY_MAP.clear()
    FALLBACK_ARTICLE_CACHE.clear()

    all_urls = []
    seen = set()
    for category, cfg in CATEGORIES.items():
        urls = _fetch_tag_urls(session, category, cfg['tag'])
        for url in urls:
            if url in seen:
                continue
            all_urls.append(url)
            seen.add(url)
            URL_CATEGORY_MAP[url] = category
            if sum(1 for u in all_urls if URL_CATEGORY_MAP.get(u) == category) >= MAX_URLS_PER_CATEGORY:
                break

    if not all_urls:
        all_urls = _fetch_fallback_urls_from_api(session)

    return list(dict.fromkeys(all_urls))


def scrape_article(session, url):
    try:
        _ensure_headers(session)
        normalized_url = _normalize_url(url)
        if normalized_url in FALLBACK_ARTICLE_CACHE:
            return FALLBACK_ARTICLE_CACHE[normalized_url]

        html = _get_html(session, normalized_url)
        soup = BeautifulSoup(html, 'lxml')

        if _looks_blocked(200, html):
            api_article = _scrape_article_from_api(session, normalized_url)
            if api_article:
                return api_article

        canonical = _extract_canonical_url(soup) or normalized_url
        title = _extract_title(soup)
        published_at = base.extract_published_at(soup, [
            ('span.date', None),
        ])
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


def _fetch_tag_urls(session, category, tag):
    urls = []
    encoded_tag = quote(tag)
    for page in range(1, MAX_TAG_PAGES + 1):
        suffix = '/' if page == 1 else f'/{page}'
        list_url = f'{BASE_URL}/tag/{encoded_tag}{suffix}'
        try:
            html = _get_html(session, list_url)
            soup = BeautifulSoup(html, 'lxml')
            page_urls = _extract_urls_from_list_soup(soup)
            if not page_urls:
                title = soup.select_one('title')
                title_text = title.get_text(' ', strip=True) if title else ''
                print(f"[{SOURCE_CODE}] No links on {list_url}; title='{title_text[:80]}', html_len={len(html)}")
                break
            urls.extend(page_urls)
            if len(dict.fromkeys(urls)) >= MAX_CANDIDATES_PER_CATEGORY:
                break
        except Exception as e:
            print(f"[{SOURCE_CODE}] Failed to fetch {category} page {page}: {e}")
            break

    return list(dict.fromkeys(urls))[:MAX_CANDIDATES_PER_CATEGORY]


def _fetch_fallback_urls_from_api(session):
    target_date = base.get_target_date()
    print(f"[{SOURCE_CODE}] Tag pages unavailable; scanning API fallback for {target_date}")

    urls = []
    seen = set()
    for article_id in _candidate_article_ids(target_date):
        article = _fetch_api_article(session, article_id, target_date)
        if not article:
            continue
        category = _infer_category(article)
        if not category:
            continue

        url = article['url']
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)
        URL_CATEGORY_MAP[url] = category
        FALLBACK_ARTICLE_CACHE[url] = article

    print(f"[{SOURCE_CODE}] API fallback found {len(urls)} candidate URLs")
    return urls


def _candidate_article_ids(target_date):
    try:
        date = datetime.fromisoformat(target_date).date()
    except Exception:
        date = datetime.now(ZoneInfo(base.SCRAPER_TIMEZONE)).date()

    prefix = f'{date.year}{date.month}{date.day:02d}'
    for i in range(1, MAX_FALLBACK_WEB_IDS + 1):
        yield f'{prefix}W{i:04d}'
    for marker in ('P', 'U'):
        for i in range(1, MAX_FALLBACK_VIDEO_IDS + 1):
            yield f'{prefix}{marker}{i:02d}M1'


def _fetch_api_article(session, article_id, target_date):
    try:
        resp = session.get(
            f'{API_BASE_URL}/getNewsVideoUrl.aspx',
            params={'id': article_id},
            headers={'Referer': f'https://embed.ftvnews.com.tw/{article_id}'},
            timeout=12,
        )
        resp.encoding = 'utf-8'
        data = resp.json()
    except Exception:
        return None

    if data.get('Status') != 'Success' or not data.get('ITEM'):
        return None

    item = data['ITEM'][0]
    title = _clean_text(item.get('Title', ''))
    description = _clean_text(item.get('Description', ''))
    if not title or not description:
        return None

    url = f'{BASE_URL}/news/detail/{article_id}'
    article = {
        "source": SOURCE_CODE,
        "url": url,
        "title": title,
        "publishedAt": _fallback_published_at(target_date),
        "rawHtml": "",
        "cleanText": description,
    }
    image_url = item.get('Image')
    if image_url:
        article["imageUrl"] = image_url
    return article


def _scrape_article_from_api(session, url):
    article_id = _extract_article_id(url)
    if not article_id:
        return None
    return _fetch_api_article(session, article_id, base.get_target_date())


def _extract_article_id(url):
    match = ARTICLE_ID_RE.search(_normalize_url(url))
    return match.group(1) if match else None


def _fallback_published_at(target_date):
    try:
        now = datetime.now(ZoneInfo(base.SCRAPER_TIMEZONE)).strftime('%H:%M:%S')
    except Exception:
        now = '00:00:00'
    return f'{target_date} {now}'


def _infer_category(article):
    text = f"{article.get('title', '')} {article.get('cleanText', '')}"
    if _has_any(text, ('兩岸', '中共', '中國代理人', '國台辦', '解放軍', '共軍', '台海', '北京')):
        return 'cross_strait'
    if _has_any(text, (
        '政治', '總統', '副總統', '行政院', '立法院', '立委', '藍委', '綠委',
        '國民黨', '民進黨', '民眾黨', '柯文哲', '黃國昌', '賴清德', '蕭美琴',
        '蔣萬安', '選舉', '罷免', '外交部', '總統府', '黨團', '縣市長'
    )):
        return 'politics'
    if _has_any(text, (
        '社會', '警方', '警消', '檢方', '法院', '地院', '起訴', '判決', '羈押',
        '詐騙', '毒品', '車禍', '火警', '意外', '失蹤', '命案', '竊盜', '攻擊'
    )):
        return 'society'
    if _has_any(text, (
        '生活', '颱風', '梅雨', '氣象', '天氣', '高溫', '健康', '醫師', '醫生',
        '疫苗', '旅遊', '美食', '星座', '運勢', '穿搭', '減重', '大眾運輸'
    )):
        return 'lifestyle'
    if _has_any(text, ('娛樂', '藝人', '歌手', '演唱會', '球員', '賽事', '財經', '股價')):
        return None
    return None


def _has_any(text, keywords):
    return any(keyword in text for keyword in keywords)


def _extract_urls_from_list_soup(soup):
    urls = []
    for a in soup.select('a[href*="/news/detail/"]'):
        full_url = _normalize_url(urljoin(BASE_URL, a.get('href', '')))
        if ARTICLE_RE.match(full_url):
            urls.append(full_url)

    for ld_node in soup.select('script[type="application/ld+json"]'):
        text = ld_node.get_text('\n', strip=True)
        for item in _walk_json(_load_json(text)):
            if not isinstance(item, dict):
                continue
            url = item.get('url')
            if not url:
                continue
            full_url = _normalize_url(urljoin(BASE_URL, str(url)))
            if ARTICLE_RE.match(full_url):
                urls.append(full_url)

    return list(dict.fromkeys(urls))


def _load_json(text):
    try:
        return json.loads(text)
    except Exception:
        return None


def _walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_json(item)


def _get_html(session, url, timeout=20):
    resp = session.get(url, timeout=timeout)
    resp.encoding = 'utf-8'
    html = resp.text or ''
    if _looks_blocked(resp.status_code, html):
        print(f"[{SOURCE_CODE}] Requests fetch looked blocked ({resp.status_code}) for {url}")
    return html


def _looks_blocked(status_code, html):
    if status_code >= 400:
        return True
    return any(marker in html for marker in BLOCKED_MARKERS)


def _browser_headers():
    return {
        'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    }


def _ensure_headers(session):
    session.headers.update(_browser_headers())


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
        return og_title['content'].split(' - 民視新聞網', 1)[0].strip()
    return ""


def _extract_clean_text(soup):
    parts = []
    figcaption = soup.select_one('.article-cover figcaption')
    if figcaption:
        caption = _clean_text(figcaption.get_text(' ', strip=True))
        if caption:
            parts.append(caption)

    for selector in ('#preface', '#newscontent'):
        node = soup.select_one(selector)
        if not node:
            continue
        content = BeautifulSoup(str(node), 'lxml')
        for tag in content.select('script, style, iframe, img, .othernews'):
            parent = tag.parent
            tag.decompose()
            if parent and parent.name in ('strong', 'p') and not parent.get_text(' ', strip=True):
                parent.decompose()
        base.remove_promo_blocks(content)

        for item in content.select('p, h2, h3'):
            clean = _clean_text(item.get_text(' ', strip=True))
            if clean:
                parts.append(clean)

    return "\n".join(parts)


def _clean_text(text):
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text).strip()
    if not text or text in {'&nbsp', '&nbsp;', 'nbsp'}:
        return ""
    if text.startswith(('更多新聞：', '延伸閱讀', '《民視新聞網》提醒您')):
        return ""
    return text


def _extract_photographer(soup):
    figcaption = soup.select_one('.article-cover figcaption')
    if figcaption:
        credit = _extract_image_credit(figcaption.get_text(' ', strip=True))
        if credit:
            return credit
    return None


def _extract_image_credit(text):
    if not text:
        return None
    credit = base.extract_photographer(text)
    if credit:
        return _normalize_credit(credit)

    m = re.search(r'[（(](?:示意)?圖[／/](.+?)[）)]', text)
    if m:
        return _normalize_credit(m.group(1))
    return None


def _normalize_credit(credit):
    if not credit:
        return None
    credit = re.sub(r'\s+', ' ', credit).strip()
    credit = re.sub(r'^(圖片|照片|示意圖|圖|資料照片|資料照)[：:／/，,、\s]*', '', credit).strip()
    credit = re.sub(r'^翻攝(?:自)?', '', credit).strip()
    credit = re.sub(r'(提供|攝影|攝|資料照)$', '', credit).strip()
    if credit in {'圖片', '照片', '圖', '示意圖', '翻攝', '資料照'}:
        return None
    return credit or None
