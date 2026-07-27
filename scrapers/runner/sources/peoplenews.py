"""民報 PeopleNews 爬蟲"""
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

import base

SOURCE_CODE = 'PEOPLENEWS'
BASE_URL = 'https://www.peoplenews.tw'
API_BASE = f'{BASE_URL}/wp-json/wp/v2'

SOURCE_CATEGORY_IDS = (
    2,    # 焦點新聞
    5,    # 消費生活
    6,    # 醫藥健康
    139,  # 防詐快訊
    467,  # 教育文化
    468,  # 專欄論壇
)

CATEGORIES = {
    'cross_strait': {
        'label': '兩岸',
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
    'politics': {
        'label': '政治',
        'keywords': (
            '總統',
            '行政院',
            '立法院',
            '立委',
            '國會',
            '國民黨',
            '民進黨',
            '民眾黨',
            '賴清德',
            '柯文哲',
            '選舉',
            '黨主席',
            '罷免',
            '憲法',
            '大法官',
            '就職',
            '國防',
            '外交',
            '彈劾',
            '政府',
        ),
    },
    'society': {
        'label': '社會',
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
            '偷拍',
            '醫美',
            '食安',
            '育兒',
            '托盟',
            '校園',
            '教育',
            '醫療',
            '衛福部',
            '新北',
            '台北',
            '高雄',
            '台中',
            '安全',
            '密室',
            '診所',
            '交通',
        ),
    },
}

MAX_URLS_PER_CATEGORY = 30
MAX_API_PAGES = 6
URL_CATEGORY_MAP = {}
ARTICLE_RE = re.compile(r'^https://www\.peoplenews\.tw/articles/[^/]+/\d+$')


def get_list_urls(session):
    _ensure_headers(session)
    URL_CATEGORY_MAP.clear()

    posts = _fetch_candidate_posts(session)
    all_urls = []
    seen = set()

    for category, cfg in CATEGORIES.items():
        added = 0
        for post in posts:
            url = _normalize_url(post.get('link', ''))
            if not ARTICLE_RE.match(url) or url in seen:
                continue
            if not _contains_keyword(_post_search_text(post), cfg['keywords']):
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
        post_id = _extract_post_id(normalized_url)
        post = _fetch_post(session, post_id) if post_id else None
        if post:
            return _article_from_post(post, normalized_url)
        return _scrape_article_page(session, normalized_url)
    except Exception as e:
        print(f"[{SOURCE_CODE}] Error scraping {url}: {e}")
        return None


def get_url_category(url):
    category = URL_CATEGORY_MAP.get(_normalize_url(url))
    return CATEGORIES.get(category, {}).get('label', '未知')


def _fetch_candidate_posts(session):
    posts = []
    for page in range(1, MAX_API_PAGES + 1):
        try:
            resp = session.get(
                f'{API_BASE}/posts',
                params={
                    'per_page': 100,
                    'page': page,
                    'categories': ','.join(str(cat_id) for cat_id in SOURCE_CATEGORY_IDS),
                    '_fields': 'id,link,title,excerpt,date',
                },
                timeout=20,
            )
            if resp.status_code >= 400:
                break
            page_posts = resp.json()
            if not page_posts:
                break
            posts.extend(page_posts)
        except Exception as e:
            print(f"[{SOURCE_CODE}] Failed to fetch API page {page}: {e}")
            break
    return posts


def _fetch_post(session, post_id):
    resp = session.get(
        f'{API_BASE}/posts/{post_id}',
        params={'_embed': '1'},
        timeout=20,
    )
    if resp.status_code != 200:
        return None
    return resp.json()


def _article_from_post(post, fallback_url):
    canonical = _normalize_url(post.get('link') or fallback_url)
    title = _clean_html_text(post.get('title', {}).get('rendered', ''))
    published_at = base.parse_datetime(post.get('date'))
    clean_text = _extract_clean_text(post.get('content', {}).get('rendered', ''))
    image_url = _extract_image_url(post)

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


def _scrape_article_page(session, url):
    resp = session.get(url, timeout=20)
    resp.encoding = 'utf-8'
    soup = BeautifulSoup(resp.text, 'lxml')
    canonical = _extract_canonical_url(soup) or url
    title_node = soup.select_one('h1')
    title = title_node.get_text(' ', strip=True) if title_node else ""
    published_at = base.extract_published_at(soup)
    image_url = base.extract_image_url(soup)
    content_node = soup.select_one('.inner-post-entry.entry-content')
    clean_text = _extract_clean_text(str(content_node)) if content_node else ""

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


def _post_search_text(post):
    title = _clean_html_text(post.get('title', {}).get('rendered', ''))
    excerpt = _clean_html_text(post.get('excerpt', {}).get('rendered', ''))
    return f'{title} {excerpt}'.strip()


def _contains_keyword(text, keywords):
    return any(keyword in text for keyword in keywords)


def _ensure_headers(session):
    session.headers.update({
        'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
        ),
        'Accept': 'application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    })


def _normalize_url(url):
    parsed = urlparse(url)
    normalized = f'{parsed.scheme}://{parsed.netloc}{parsed.path}'
    return normalized.rstrip('/')


def _extract_post_id(url):
    match = re.search(r'/(\d+)$', url)
    return match.group(1) if match else None


def _extract_clean_text(html):
    soup = BeautifulSoup(html or '', 'lxml')
    for tag in soup.select(
        'script, style, iframe, figure, img, .rp4wp-related-posts, '
        '.penci-post-countview-number-check'
    ):
        tag.decompose()

    paragraphs = []
    for node in soup.select('p, h2, h3, li'):
        text = _clean_html_text(str(node))
        if text:
            paragraphs.append(text)
    if paragraphs:
        return "\n".join(paragraphs)
    return _clean_html_text(str(soup))


def _clean_html_text(html):
    if not html:
        return ""
    text = BeautifulSoup(str(html), 'lxml').get_text(' ', strip=True)
    return re.sub(r'\s+', ' ', text).strip()


def _extract_image_url(post):
    embedded = post.get('_embedded', {})
    media = embedded.get('wp:featuredmedia') or []
    if media and isinstance(media[0], dict):
        return media[0].get('source_url')
    return None


def _extract_canonical_url(soup):
    node = soup.select_one('link[rel="canonical"]')
    if node and node.get('href'):
        return _normalize_url(urljoin(BASE_URL, node['href']))
    og_url = soup.select_one('meta[property="og:url"]')
    if og_url and og_url.get('content'):
        return _normalize_url(urljoin(BASE_URL, og_url['content']))
    return None
