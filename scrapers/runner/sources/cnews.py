"""匯流新聞網 CNEWS 爬蟲"""
import re
from urllib.parse import quote, urljoin, urlparse

from bs4 import BeautifulSoup

import base

SOURCE_CODE = 'CNEWS'
BASE_URL = 'https://cnews.com.tw'

CATEGORIES = {
    'politics': {
        'label': '政治',
        'slugs': ('政治匯流',),
    },
    'society': {
        'label': '社會',
        'slugs': ('新聞匯流', '生活匯流', '調查匯流'),
        'keywords': (
            '車禍',
            '死亡',
            '警方',
            '警',
            '檢',
            '法院',
            '火災',
            '地震',
            '災',
            '詐騙',
            '詐欺',
            '司法',
            '交保',
            '弊案',
            '案',
            '地方',
            '校園',
            '醫院',
            '花蓮',
            '高雄',
            '台中',
            '新北',
            '台北',
            '民眾',
        ),
        'fallback_unfiltered': True,
    },
    'cross_strait': {
        'label': '兩岸',
        'slugs': ('國際匯流', '政治匯流'),
        'keywords': (
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
        ),
    },
}

MAX_CATEGORY_PAGES = 6
MAX_URLS_PER_CATEGORY = 30
MAX_CANDIDATES_PER_CATEGORY = MAX_URLS_PER_CATEGORY * 3
URL_CATEGORY_MAP = {}

EXCLUDED_PATH_PREFIXES = (
    '/category/',
    '/tag/',
    '/author/',
    '/post_video/',
    '/feed/',
    '/news/',
    '/todaynews',
    '/contact',
    '/privacy',
)
EXCLUDED_PATHS = {
    '/news',
    '/版權聲明',
}


def get_list_urls(session):
    _ensure_headers(session)
    URL_CATEGORY_MAP.clear()

    all_urls = []
    seen = set()
    for category, cfg in CATEGORIES.items():
        urls = _fetch_category_urls(session, category, cfg)
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


def _fetch_category_urls(session, category, cfg):
    filtered_urls = []
    unfiltered_urls = []
    keywords = cfg.get('keywords')

    for slug in cfg['slugs']:
        for page in range(1, MAX_CATEGORY_PAGES + 1):
            try:
                resp = session.get(_category_url(slug, page), timeout=20)
                resp.encoding = 'utf-8'
                if resp.status_code >= 400:
                    break
                soup = BeautifulSoup(resp.text, 'lxml')
                entries = _extract_entries(soup)
                if not entries:
                    break
                for entry in entries:
                    unfiltered_urls.append(entry['url'])
                    if not keywords or _contains_keyword(entry['text'], keywords):
                        filtered_urls.append(entry['url'])
                if len(dict.fromkeys(filtered_urls)) >= MAX_CANDIDATES_PER_CATEGORY:
                    break
            except Exception as e:
                print(f"[{SOURCE_CODE}] Failed to fetch {category} {slug} page {page}: {e}")
                break
        if len(dict.fromkeys(filtered_urls)) >= MAX_CANDIDATES_PER_CATEGORY:
            break

    urls = list(dict.fromkeys(filtered_urls))
    if cfg.get('fallback_unfiltered') and len(urls) < MAX_URLS_PER_CATEGORY:
        for url in list(dict.fromkeys(unfiltered_urls)):
            if url not in urls:
                urls.append(url)
            if len(urls) >= MAX_CANDIDATES_PER_CATEGORY:
                break
    return urls


def _category_url(slug, page):
    encoded_slug = quote(slug, safe='')
    if page <= 1:
        return f'{BASE_URL}/category/{encoded_slug}/'
    return f'{BASE_URL}/category/{encoded_slug}/page/{page}/'


def _extract_entries(soup):
    entries = []
    for a in soup.select('a[href]'):
        full_url = _normalize_url(urljoin(BASE_URL, a.get('href', '')))
        if not _is_article_url(full_url):
            continue
        text = _extract_link_context_text(a)
        if _looks_like_read_more_only(text):
            continue
        entries.append({
            'url': full_url,
            'text': text,
        })
    return _dedupe_entries(entries)


def _is_article_url(url):
    parsed = urlparse(url)
    if parsed.netloc not in {'cnews.com.tw', 'www.cnews.com.tw'}:
        return False
    path = parsed.path.rstrip('/')
    if not path or path == '/':
        return False
    if path in EXCLUDED_PATHS:
        return False
    if any(path.startswith(prefix) for prefix in EXCLUDED_PATH_PREFIXES):
        return False
    if path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg')):
        return False
    return True


def _extract_link_context_text(anchor):
    title_node = anchor.select_one('h1, h2, h3, h4, .title-wrapper')
    intro_node = anchor.select_one('.intro-wrapper, .intro')
    parts = []
    if title_node:
        parts.append(title_node.get_text(' ', strip=True))
    if intro_node:
        parts.append(intro_node.get_text(' ', strip=True))
    if not parts:
        parent = anchor.find_parent(class_='content') or anchor.find_parent('article') or anchor.parent
        if parent:
            parts.append(parent.get_text(' ', strip=True))
    if not parts:
        parts.append(anchor.get_text(' ', strip=True))
    return _normalize_text(' '.join(parts))


def _looks_like_read_more_only(text):
    return not text or text.upper().replace(' ', '') == 'READMORE'


def _dedupe_entries(entries):
    by_url = {}
    for entry in entries:
        current = by_url.get(entry['url'])
        if not current or len(entry['text']) > len(current['text']):
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
    for selector in (
        'meta[property="og:title"]',
        'meta[name="twitter:title"]',
    ):
        node = soup.select_one(selector)
        if node and node.get('content'):
            title = node['content']
            return title.split(' - 匯流新聞網', 1)[0].strip()
    article_node = soup.select_one('article')
    if article_node:
        h_node = article_node.select_one('h1, h2')
        if h_node:
            return h_node.get_text(' ', strip=True)
    return ""


def _extract_clean_text(soup):
    article_node = soup.select_one('article')
    if not article_node:
        return ""

    content = BeautifulSoup(str(article_node), 'lxml')
    for tag in content.select(
        'script, style, iframe, img, figure, aside, nav, form, '
        '.sharedaddy, .jp-relatedposts, .post-navigation, .td-a-rec'
    ):
        tag.decompose()

    paragraphs = []
    for p in content.select('p'):
        text = _clean_paragraph(p.get_text(' ', strip=True))
        if text:
            paragraphs.append(text)

    if paragraphs:
        return "\n".join(paragraphs)
    return _normalize_text(content.get_text('\n', strip=True))


def _clean_paragraph(text):
    text = _normalize_text(text)
    if not text:
        return ""
    skip_prefixes = (
        '更多新聞：',
        '延伸閱讀：',
        '照片來源：',
    )
    if text.startswith(skip_prefixes):
        return ""
    return text


def _normalize_text(text):
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip()
