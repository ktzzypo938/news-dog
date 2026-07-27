"""太報 TaiSounds 爬蟲"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import base

SOURCE_CODE = 'TAISOUNDS'
BASE_URL = 'https://www.taisounds.com'

CATEGORY_SECTIONS = {
    'politics': 70,
    'society': 95,
    'cross_strait': 85,  # 太報分類名稱為「美中台」
}
CATEGORY_LABELS = {
    'politics': '政治',
    'society': '社會',
    'cross_strait': '兩岸',
}
MAX_URLS_PER_CATEGORY = 30
MAX_SECTION_PAGES = 6
ARTICLE_RE = re.compile(r'/news/content/\d+/\d+$')
URL_CATEGORY_MAP = {}
CROSS_STRAIT_KEYWORDS = (
    '兩岸', '台海', '台灣問題', '台獨', '中共', '國台辦', '陸委會',
    '共軍', '解放軍', '對台', '對岸', '統一', '赴陸', '軍售',
    '侵台', '武統', '台灣', '台美', '美台', '中美', '美中',
    '川習', '習近平', '中國', '北京', '香港', '黎智英', '中方',
)


def get_list_urls(session):
    _ensure_headers(session)
    URL_CATEGORY_MAP.clear()

    cross_urls = _fetch_category_urls(session, 'cross_strait')
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

        canonical = _extract_canonical_url(soup) or normalized_url
        title = _extract_title(soup)
        published_at = base.extract_published_at(soup, [
            ('div.publish', None),
        ])
        image_url = base.extract_image_url(soup)

        content_node = soup.select_one('div.news-box-text')
        if content_node:
            photographer = _extract_photographer(content_node)
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


def _fetch_category_urls(session, category, exclude=None):
    exclude = exclude or set()
    section_id = CATEGORY_SECTIONS[category]
    urls = []
    for page in range(1, MAX_SECTION_PAGES + 1):
        for full_url, title in _fetch_section_page_items(session, section_id, page):
            if full_url in exclude:
                continue
            if category == 'cross_strait' and not _is_cross_strait_title(title):
                continue
            urls.append(full_url)
            if len(dict.fromkeys(urls)) >= MAX_URLS_PER_CATEGORY:
                return list(dict.fromkeys(urls))[:MAX_URLS_PER_CATEGORY]
    return list(dict.fromkeys(urls))[:MAX_URLS_PER_CATEGORY]


def _fetch_section_page_items(session, section_id, page):
    try:
        if page == 1:
            list_url = f'{BASE_URL}/news/section/{section_id}'
            resp = session.get(list_url, timeout=20)
            resp.encoding = 'utf-8'
            soup = BeautifulSoup(resp.text, 'lxml')
        else:
            list_url = f'{BASE_URL}/news/infinatesection/{section_id}?page={page}'
            resp = session.post(
                list_url,
                headers={
                    'Accept': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                    'Referer': f'{BASE_URL}/news/section/{section_id}',
                },
                timeout=20,
            )
            html = (resp.json() or {}).get('HtmlString', '')
            soup = BeautifulSoup(html, 'lxml')

        items = []
        for a in soup.select('#ulnewslist a[href], li .media a[href]'):
            full_url = _normalize_url(urljoin(BASE_URL, a.get('href', '')))
            if ARTICLE_RE.search(full_url):
                title_node = a.select_one('h4')
                title = title_node.get_text(' ', strip=True) if title_node else a.get_text(' ', strip=True)
                items.append((full_url, title))
        return list(dict.fromkeys(items))
    except Exception as e:
        print(f"[{SOURCE_CODE}] Failed to fetch section {section_id} page {page}: {e}")
        return []


def _is_cross_strait_title(title):
    if not title:
        return False
    return any(keyword in title for keyword in CROSS_STRAIT_KEYWORDS)


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
    return title.split(' | ', 1)[0].split(' - 太報', 1)[0].strip()


def _extract_clean_text(content_node):
    content = BeautifulSoup(str(content_node), 'lxml')
    for tag in content.select('script, style, iframe, img, .mbt-text, .article-ad, .ad, .news-label'):
        tag.decompose()

    text = content.get_text('\n', strip=True)
    paragraphs = []
    for line in text.splitlines():
        clean = _clean_text(line)
        if clean:
            paragraphs.append(clean)
    return "\n".join(paragraphs)


def _clean_text(text):
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text).strip()
    if text in {'收藏文章', '更多太報報導'}:
        return ""
    return text


def _extract_photographer(content_node):
    for node in content_node.select('.mbt-text, img[alt]'):
        text = node.get_text(' ', strip=True) if node.name != 'img' else node.get('alt', '')
        credit = _extract_caption_credit(text) or base.extract_photographer(text)
        if credit:
            return credit
    return None


def _extract_caption_credit(text):
    if not text:
        return None
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return None

    credit = None
    if '。' in text:
        credit = text.rsplit('。', 1)[-1].strip()
    elif '，' in text:
        credit = text.rsplit('，', 1)[-1].strip()
    else:
        credit = text

    if not credit:
        return None
    if len(credit) > 60:
        return None

    credit = re.sub(r'^(圖片|照片|圖|資料照片|資料照)[：:／/，,、\s]*', '', credit).strip()
    credit = re.sub(r'^翻攝(?:自)?', '', credit).strip()
    credit = re.sub(r'^取自', '', credit).strip()
    credit = re.sub(r'(提供|攝影|攝)$', '', credit).strip()
    if credit in {'圖片', '照片', '圖', '翻攝', '作者'}:
        return None
    return credit or None
