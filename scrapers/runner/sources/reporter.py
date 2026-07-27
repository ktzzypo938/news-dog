"""報導者 The Reporter 爬蟲"""
import json
import re
from datetime import timezone, timedelta
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from dateutil import parser

import base

SOURCE_CODE = 'REPORTER'
BASE_URL = 'https://www.twreporter.org'
TAIPEI_TZ = timezone(timedelta(hours=8))

CATEGORIES = {
    'politics': {
        'label': '政治',
        'paths': ('politics-and-society',),
        'pages': 4,
    },
    'society': {
        'label': '社會',
        'paths': ('humanrights', 'education', 'health', 'politics-and-society'),
        'pages': 3,
    },
    'cross_strait': {
        'label': '兩岸',
        'paths': ('world', 'politics-and-society'),
        'pages': 8,
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
MAX_URLS_PER_CATEGORY = 30
MAX_CANDIDATES_PER_CATEGORY = MAX_URLS_PER_CATEGORY * 3
ARTICLE_RE = re.compile(r'^https://www\.twreporter\.org/a/[A-Za-z0-9_-]+$')
URL_CATEGORY_MAP = {}

TEXT_BLOCK_TYPES = {
    'unstyled',
    'annotation',
    'blockquote',
    'header-one',
    'header-two',
    'header-three',
    'ordered-list-item',
    'unordered-list-item',
}


def get_list_urls(session):
    _ensure_headers(session)
    URL_CATEGORY_MAP.clear()

    all_urls = []
    seen = set()
    for category, cfg in CATEGORIES.items():
        posts = _fetch_category_posts(session, cfg)
        added = 0
        for post in posts:
            url = _post_url(post)
            if not url or url in seen:
                continue
            if cfg.get('keywords') and not _contains_keyword(_post_search_text(post), cfg['keywords']):
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
        state = _extract_redux_state(soup)
        post = _find_post_by_slug(state, _slug_from_url(normalized_url)) or {}

        canonical = _post_url(post) or _extract_canonical_url(soup) or normalized_url
        title = (post.get('title') or _extract_meta_content(soup, 'meta[property="og:title"]') or '').strip()
        title = title.split(' - 報導者', 1)[0].strip()
        published_at = _parse_datetime_taipei(post.get('published_date')) or base.extract_published_at(soup)
        image_url = _extract_post_image(post) or base.extract_image_url(soup)
        clean_text = _extract_clean_text(post)

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
        photographer = _extract_photographer(post)
        if photographer:
            result["imagePhotographer"] = photographer
        return result
    except Exception as e:
        print(f"[{SOURCE_CODE}] Error scraping {url}: {e}")
        return None


def get_url_category(url):
    category = URL_CATEGORY_MAP.get(_normalize_url(url))
    return CATEGORIES.get(category, {}).get('label', '未知')


def _fetch_category_posts(session, cfg):
    posts = []
    for path in cfg['paths']:
        for page in range(1, cfg['pages'] + 1):
            try:
                resp = session.get(_category_url(path, page), timeout=20)
                resp.encoding = 'utf-8'
                if resp.status_code >= 400:
                    break
                state = _extract_redux_state(BeautifulSoup(resp.text, 'lxml'))
                page_posts = _posts_from_state(state)
                if not page_posts:
                    break
                posts.extend(page_posts)
                if len(_dedupe_posts(posts)) >= MAX_CANDIDATES_PER_CATEGORY:
                    break
            except Exception as e:
                print(f"[{SOURCE_CODE}] Failed to fetch category {path} page {page}: {e}")
                break
        if len(_dedupe_posts(posts)) >= MAX_CANDIDATES_PER_CATEGORY:
            break
    return _dedupe_posts(posts)


def _category_url(path, page):
    url = f'{BASE_URL}/categories/{path}'
    if page <= 1:
        return url
    return f'{url}?page={page}'


def _extract_redux_state(soup):
    for node in soup.select('script'):
        text = node.string or node.get_text() or ''
        if 'window.__REDUX_STATE__=' not in text:
            continue
        raw = text.split('window.__REDUX_STATE__=', 1)[1].strip()
        if raw.endswith(';'):
            raw = raw[:-1]
        try:
            return json.loads(raw)
        except Exception:
            return {}
    return {}


def _posts_from_state(state):
    posts = state.get('entities', {}).get('posts', {})
    by_id = posts.get('byId', {})
    return [by_id.get(post_id, {}) for post_id in posts.get('allIds', []) if by_id.get(post_id)]


def _find_post_by_slug(state, slug):
    for post in _posts_from_state(state):
        if post.get('slug') == slug:
            return post
    return None


def _dedupe_posts(posts):
    by_slug = {}
    for post in posts:
        slug = post.get('slug')
        if slug and slug not in by_slug:
            by_slug[slug] = post
    return list(by_slug.values())


def _post_url(post):
    slug = post.get('slug')
    if not slug:
        return None
    url = _normalize_url(urljoin(BASE_URL, f'/a/{slug}'))
    return url if ARTICLE_RE.match(url) else None


def _post_search_text(post):
    parts = [
        post.get('title'),
        post.get('subtitle'),
        post.get('og_description'),
        _extract_blocks_text(post.get('brief')),
    ]
    tags = post.get('tags') or []
    if isinstance(tags, list):
        parts.extend(tag.get('name') for tag in tags if isinstance(tag, dict))
    return ' '.join(part for part in parts if part)


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


def _slug_from_url(url):
    return urlparse(url).path.rstrip('/').split('/')[-1]


def _extract_canonical_url(soup):
    node = soup.select_one('link[rel="canonical"]')
    if node and node.get('href'):
        return _normalize_url(urljoin(BASE_URL, node['href']))
    og_url = soup.select_one('meta[property="og:url"]')
    if og_url and og_url.get('content'):
        return _normalize_url(urljoin(BASE_URL, og_url['content']))
    return None


def _extract_meta_content(soup, selector):
    node = soup.select_one(selector)
    return node.get('content') if node and node.get('content') else None


def _parse_datetime_taipei(value):
    if not value:
        return None
    try:
        dt = parser.parse(str(value).strip())
        if dt.tzinfo:
            dt = dt.astimezone(TAIPEI_TZ)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return None


def _extract_post_image(post):
    for field in ('hero_image', 'og_image'):
        image = post.get(field)
        url = _extract_resized_image_url(image)
        if url:
            return url
    return None


def _extract_resized_image_url(image):
    if not isinstance(image, dict):
        return None
    targets = image.get('resized_targets') or {}
    for key in ('desktop', 'mobile', 'tablet', 'w400', 'tiny'):
        target = targets.get(key)
        if isinstance(target, dict) and target.get('url'):
            return target['url']
    if image.get('url'):
        return image['url']
    return None


def _extract_clean_text(post):
    text = _extract_blocks_text(post.get('content'))
    if text:
        return text
    return _extract_blocks_text(post.get('brief'))


def _extract_blocks_text(blocks_root):
    if not isinstance(blocks_root, dict):
        return ""
    lines = []
    for block in blocks_root.get('api_data') or []:
        if block.get('type') not in TEXT_BLOCK_TYPES:
            continue
        text = _extract_content_text(block.get('content'))
        if text:
            lines.append(text)
    return "\n".join(lines)


def _extract_content_text(value):
    if isinstance(value, str):
        return _clean_html_text(value)
    if isinstance(value, list):
        parts = [_extract_content_text(item) for item in value]
        return _normalize_text(' '.join(part for part in parts if part))
    if isinstance(value, dict):
        if value.get('text'):
            return _clean_html_text(value['text'])
        if value.get('content'):
            return _extract_content_text(value['content'])
    return ""


def _clean_html_text(text):
    if not text:
        return ""
    soup = BeautifulSoup(str(text), 'lxml')
    return _normalize_text(soup.get_text(' ', strip=True))


def _normalize_text(text):
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', str(text)).strip()
    return text


def _extract_photographer(post):
    image = post.get('hero_image') or {}
    description = image.get('description') if isinstance(image, dict) else None
    if description:
        return base.extract_photographer(description)
    return None
