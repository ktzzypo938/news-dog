"""鏡週刊 Mirror Media 爬蟲"""
import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import base

SOURCE_CODE = 'MIRROR'
BASE_URL = 'https://www.mirrormedia.mg'
GRAPHQL_ENDPOINT = 'https://go-story-prod-983956931553.asia-east1.run.app/api/graphql'

LISTING_QUERY = """
query ($take: Int, $skip: Int, $orderBy: [PostOrderByInput!]!, $filter: PostWhereInput!) {
  posts(take: $take, skip: $skip, orderBy: $orderBy, where: $filter) {
    id
    slug
    title
    publishedDate
    state
    categories { name slug }
    sections { name slug }
    heroImage { resized { original w1600 w800 } }
  }
}
"""

CATEGORY_LIMIT = 30
GRAPHQL_PAGE_SIZE = 60
ARTICLE_RE = re.compile(r'/story/([^/?#]+)$')
URL_CATEGORY_MAP = {}
CATEGORY_LABELS = {
    'politics': '政治',
    'society': '社會',
    'cross_strait': '兩岸',
}
CATEGORY_SLUGS = {
    'politics': 'political',
    'society': 'city-news',
}
CROSS_STRAIT_SCAN_SLUGS = ('political', 'news')
CROSS_STRAIT_STRONG_KEYWORDS = (
    '兩岸', '台海', '台灣問題', '台獨', '中共', '國台辦', '陸委會',
    '共軍', '解放軍', '對台', '對岸', '統一', '赴陸', '軍售台',
    '北京盼台灣', '台灣自願統一',
)
CROSS_STRAIT_PAIR_LEFT = ('中國', '北京', '習近平', '川習', '盧比歐', '美中', '中美', '大陸')
CROSS_STRAIT_PAIR_RIGHT = ('台灣', '對台', '台海', '軍售', '統一', '民進黨', '國民黨', '外交部', '陸委會', '台獨')


def get_list_urls(session):
    _ensure_headers(session)
    URL_CATEGORY_MAP.clear()

    cross_urls = _fetch_cross_strait_urls(session)
    cross_set = set(cross_urls)
    politics_urls = _fetch_category_urls(session, 'politics', exclude=cross_set)
    society_urls = _fetch_category_urls(session, 'society', exclude=cross_set)

    all_urls = []
    for category, urls in (
        ('politics', politics_urls),
        ('society', society_urls),
        ('cross_strait', cross_urls),
    ):
        for url in urls:
            normalized = _normalize_url(url)
            all_urls.append(normalized)
            URL_CATEGORY_MAP[normalized] = category

    return list(dict.fromkeys(all_urls))


def scrape_article(session, url):
    try:
        _ensure_headers(session)
        normalized_url = _normalize_url(url)
        resp = session.get(normalized_url, timeout=20)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'lxml')

        post = _extract_next_post(soup)
        canonical = _extract_canonical_url(soup) or normalized_url

        title = (post.get('title') if post else None) or _extract_title(soup)
        published_at = base.extract_published_at(soup)
        if not published_at and post:
            published_at = base.parse_datetime(post.get('publishedDate'))

        clean_text = _extract_post_text(post) if post else ""
        if not clean_text:
            clean_text = _extract_html_text(soup)

        image_url = _extract_post_image(post) if post else None
        if not image_url:
            image_url = base.extract_image_url(soup)

        photographer = _extract_image_credit(post, soup) if post else None

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


def _fetch_category_urls(session, category, exclude=None):
    exclude = exclude or set()
    urls = []
    for post in _iter_category_posts(session, CATEGORY_SLUGS[category], max_pages=6):
        full_url = _post_url(post)
        if not full_url or full_url in exclude:
            continue
        urls.append(full_url)
        if len(urls) >= CATEGORY_LIMIT:
            break
    return urls


def _fetch_cross_strait_urls(session):
    urls = []
    seen = set()
    for slug in CROSS_STRAIT_SCAN_SLUGS:
        for post in _iter_category_posts(session, slug, max_pages=12):
            title = post.get('title') or ''
            if not _is_cross_strait_title(title):
                continue
            full_url = _post_url(post)
            if full_url and full_url not in seen:
                seen.add(full_url)
                urls.append(full_url)
            if len(urls) >= CATEGORY_LIMIT:
                return urls
    return urls


def _iter_category_posts(session, category_slug, max_pages):
    for page in range(max_pages):
        payload = {
            'query': LISTING_QUERY,
            'variables': {
                'take': GRAPHQL_PAGE_SIZE,
                'skip': page * GRAPHQL_PAGE_SIZE,
                'orderBy': [{'publishedDate': 'desc'}],
                'filter': {
                    'state': {'equals': 'published'},
                    'categories': {'some': {'slug': {'equals': category_slug}}},
                },
            },
        }
        try:
            resp = session.post(
                GRAPHQL_ENDPOINT,
                json=payload,
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'Origin': BASE_URL,
                    'Referer': f'{BASE_URL}/category/{category_slug}',
                },
                timeout=20,
            )
            data = resp.json()
            posts = (data.get('data') or {}).get('posts') or []
        except Exception as e:
            print(f"[{SOURCE_CODE}] Failed to fetch category {category_slug} page {page + 1}: {e}")
            break
        if not posts:
            break
        for post in posts:
            yield post


def _post_url(post):
    slug = post.get('slug') if post else None
    if not slug:
        return None
    return f"{BASE_URL}/story/{slug}"


def _is_cross_strait_title(title):
    if not title:
        return False
    if any(keyword in title for keyword in CROSS_STRAIT_STRONG_KEYWORDS):
        return True
    return (
        any(keyword in title for keyword in CROSS_STRAIT_PAIR_LEFT)
        and any(keyword in title for keyword in CROSS_STRAIT_PAIR_RIGHT)
    )


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
    title_node = soup.select_one('h1') or soup.select_one('meta[property="og:title"]')
    if getattr(title_node, 'name', '') == 'meta':
        title = title_node.get('content', '')
    else:
        title = title_node.get_text(strip=True) if title_node else ""
    return title.split(' - 鏡週刊', 1)[0].strip()


def _extract_next_post(soup):
    node = soup.select_one('#__NEXT_DATA__')
    if not node or not node.string:
        return {}
    try:
        data = json.loads(node.string)
        return ((data.get('props') or {}).get('pageProps') or {}).get('postData') or {}
    except Exception:
        return {}


def _extract_post_text(post):
    content = post.get('content') or post.get('trimmedContent') or post.get('brief') or {}
    paragraphs = []
    for block in content.get('blocks') or []:
        text = _clean_text(block.get('text'))
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)


def _extract_html_text(soup):
    article = BeautifulSoup(str(soup.select_one('article') or soup.select_one('main') or soup), 'lxml')
    for tag in article.select('script, style, iframe, aside, nav, footer, button, form'):
        tag.decompose()
    paragraphs = []
    for p in article.select('p'):
        text = _clean_text(p.get_text(' ', strip=True))
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)


def _clean_text(text):
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text).strip()
    if text in ('贊助本文', '加入訂閱會員', '已複製連結'):
        return ""
    return text


def _extract_post_image(post):
    image = (post.get('heroImage') or {}).get('resized') or {}
    return image.get('w1600') or image.get('w800') or image.get('original')


def _extract_image_credit(post, soup):
    caption = post.get('heroCaption') or ''
    credit = _extract_caption_credit(caption)
    if credit:
        return credit

    for field in ('photographers', 'camera_man'):
        names = _extract_contact_names(post.get(field))
        if names:
            return '、'.join(names)

    for node in soup.select('figcaption, article img[alt], meta[property="og:image:alt"]'):
        text = node.get('content', '') if node.name == 'meta' else node.get_text(strip=True)
        credit = _extract_caption_credit(text) or base.extract_photographer(text)
        if credit:
            return credit
    return None


def _extract_contact_names(value):
    if not value:
        return []
    if isinstance(value, dict):
        name = value.get('name')
        return [name] if name else []
    if isinstance(value, list):
        return [item.get('name') for item in value if isinstance(item, dict) and item.get('name')]
    if isinstance(value, str):
        return [value]
    return []


def _extract_caption_credit(text):
    if not text:
        return None
    matches = re.findall(r'[（(]([^（）()]{1,80})[）)]', text)
    if not matches:
        return base.extract_photographer(text)
    for raw_credit in reversed(matches):
        credit = raw_credit.strip()
        if credit in {'左', '右', '中', '上', '下', '左起', '右起'}:
            continue
        credit = re.sub(r'^(示意圖|資料照|資料圖片|圖|圖片|照片)[，,、:：\s]*', '', credit).strip()
        credit = re.sub(r'^翻攝自', '', credit).strip()
        credit = re.sub(r'^取自', '', credit).strip()
        credit = re.sub(r'(提供|攝影|攝)$', '', credit).strip()
        credit = re.sub(r'^鏡報(?=[\u4e00-\u9fff]{2,4}$)', '', credit).strip()
        if credit:
            return credit
    return None
