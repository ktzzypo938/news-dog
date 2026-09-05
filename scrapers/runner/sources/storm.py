"""風傳媒爬蟲"""
import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import base

SOURCE_CODE = 'STORM'
BASE_URL = 'https://www.storm.mg'

CATEGORY_PAGES = {
    'politics': 'https://www.storm.mg/channel/all/7',
    'society': 'https://www.storm.mg/channel/all/22',  # 地方新聞，對應本專案社會/地方事件範圍
    'lifestyle': 'https://www.storm.mg/channel/all/5',
    'cross_strait': 'https://www.storm.mg/channel/all/11',
}

MAX_URLS_PER_CATEGORY = 40
ARTICLE_RE = re.compile(r'/article/\d+$')
URL_CATEGORY_MAP = {}

# 投書／專欄／書摘不是新聞報導，標題格式固定，列表階段就排除（省下抓取）
NON_NEWS_TITLE_RES = [
    re.compile(r'^觀點投書\s*[：:]'),           # 觀點投書：近千億養不出「無人機國家隊」…
    re.compile(r'^[\w·]{2,6}觀點\s*[：:]'),     # 吳斯懷觀點：美軍彈藥告急…
    re.compile(r'^[\w·]{2,6}專欄\s*[：:]'),     # 夏珍專欄：時不我予「綠白合」…
    # 風書房書摘，編號在標題結尾且可能省略：…：《台灣核彈》選摘（7）
    re.compile(r'選摘\s*(?:[（(]\s*\d+\s*[）)])?\s*$'),
]

# 不收錄的 article:section。列表頁看不出這些，只能在文章頁判斷：
#   VIP  付費牆內容，內文常被截成 200–350 字導讀，拿來做分析／聚合只會污染結果，
#        而且標題偽裝成一般新聞（專訪》、調查》、歷史新新聞》），標題正則擋不到
#   評論  涵蓋觀點投書、專欄、專文、評書、風書房書摘等所有意見文章
EXCLUDED_SECTIONS = {'VIP', '評論'}
CATEGORY_LABELS = {
    'politics': '政治',
    'society': '社會',
    'lifestyle': '生活',
    'cross_strait': '兩岸',
}


def is_non_news_title(title):
    """判斷是否為風傳媒的投書／專欄／書摘等非新聞內容。"""
    if not title:
        return False
    title = title.strip()
    return any(p.search(title) for p in NON_NEWS_TITLE_RES)


def _extract_section(soup):
    """取 article:section（風傳媒用它區分 新聞／評論／VIP）。"""
    node = (soup.select_one('meta[property="article:section"]')
            or soup.select_one('meta[name="section"]'))
    return (node.get('content') or '').strip() if node else ''


def get_list_urls(session):
    all_urls = []
    URL_CATEGORY_MAP.clear()

    for category, list_url in CATEGORY_PAGES.items():
        try:
            resp = session.get(list_url, timeout=20)
            resp.encoding = 'utf-8'
            soup = BeautifulSoup(resp.text, 'lxml')
            titles = {}
            category_urls = []
            for a in soup.select('a[href]'):
                full_url = _normalize_url(urljoin(BASE_URL, a.get('href', '')))
                if not ARTICLE_RE.search(full_url) or full_url.endswith('/110488'):
                    continue
                category_urls.append(full_url)
                # 同一篇會有圖片連結與標題連結，取最長的文字當標題
                text = a.get_text(' ', strip=True)
                if len(text) > len(titles.get(full_url, '')):
                    titles[full_url] = text

            news_urls = [u for u in dict.fromkeys(category_urls) if not is_non_news_title(titles.get(u))]
            skipped = len(set(category_urls)) - len(news_urls)
            if skipped:
                print(f"[{SOURCE_CODE}] {category}: skipped {skipped} non-news articles")
            for full_url in news_urls[:MAX_URLS_PER_CATEGORY]:
                all_urls.append(full_url)
                URL_CATEGORY_MAP.setdefault(full_url, category)
        except Exception as e:
            print(f"[{SOURCE_CODE}] Failed to fetch {category} list: {e}")

    return list(dict.fromkeys(all_urls))


def scrape_article(session, url):
    try:
        resp = base.get_page(session, url, timeout=20, source_code=SOURCE_CODE)
        if resp is None:
            return None
        soup = BeautifulSoup(resp.text, 'lxml')

        # 頻道判斷擺最前面：VIP／評論不收，省下後面所有解析
        section = _extract_section(soup)
        if section in EXCLUDED_SECTIONS:
            print(f"[{SOURCE_CODE}] Skipping {section} article: {url}")
            return base.SkippedArticle(section)

        article_ld = _extract_news_article_json_ld(soup)

        canonical = _extract_canonical_url(soup) or _normalize_url(url)
        image_url = base.extract_image_url(soup)

        title_node = soup.select_one('h1')
        title = title_node.get_text(strip=True) if title_node else ""
        if not title and article_ld:
            title = article_ld.get('headline', '')
        if not title:
            og_title = soup.select_one('meta[property="og:title"]')
            title = og_title.get('content', '') if og_title else ""
        title = title.split(' | ', 1)[0].strip()

        # 列表頁沒抓到標題文字（純圖片連結）時的最後一道防線
        if is_non_news_title(title):
            print(f"[{SOURCE_CODE}] Skipping non-news article: {url}")
            return base.SkippedArticle('non-news-title')

        published_at = base.extract_published_at(soup, [
            ('meta[name="datePublished"]', 'content'),
            ('meta[property="article:published_time"]', 'content'),
        ])

        photographer = _extract_photographer(soup)
        clean_text = ""
        if article_ld and article_ld.get('articleBody'):
            clean_text = _clean_text(article_ld.get('articleBody', ''))
        if not clean_text:
            content_node = soup.select_one('article')
            clean_text = _extract_clean_text(content_node) if content_node else ""

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


def _extract_news_article_json_ld(soup):
    for ld_node in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(ld_node.string or '')
        except Exception:
            continue
        for item in _iter_json_ld_items(data):
            item_type = item.get('@type')
            if item.get('articleBody') and (
                item_type == 'NewsArticle'
                or (isinstance(item_type, list) and 'NewsArticle' in item_type)
            ):
                return item
    return None


def _iter_json_ld_items(data):
    if isinstance(data, dict):
        yield data
        graph = data.get('@graph')
        if graph:
            yield from _iter_json_ld_items(graph)
    elif isinstance(data, list):
        for item in data:
            yield from _iter_json_ld_items(item)


def _extract_clean_text(content_node):
    content = BeautifulSoup(str(content_node), 'lxml')
    for tag in content.select('script, style, iframe, figure, .ad, .recommend, .related, aside'):
        tag.decompose()
    base.remove_promo_blocks(content)

    paragraphs = []
    for p in content.select('p'):
        text = _clean_text(p.get_text(' ', strip=True))
        if text:
            paragraphs.append(text)

    if paragraphs:
        return "\n".join(paragraphs)
    return _clean_text(content.get_text(' ', strip=True))


def _clean_text(text):
    """逐行整理空白並保留換行；整篇壓成一行會讓 base.sanitize_clean_text 的逐行規則失去意義。"""
    if not text:
        return ""

    for marker in [
        '更多風傳媒獨家內幕：',
        '更多風傳媒報導：',
        '更多文章推薦：',
        '更多相關報導：',
        '責任編輯：',
    ]:
        if marker in text:
            text = text.split(marker, 1)[0]

    lines = []
    for line in str(text).splitlines():
        clean = re.sub(r'[ \t\u3000\xa0]+', ' ', line).strip()
        if clean:
            lines.append(clean)
    return "\n".join(lines)


def _extract_photographer(soup):
    for node in soup.select('figcaption, img[alt]'):
        text = node.get_text(strip=True) if node.name != 'img' else node.get('alt', '')
        photographer = base.extract_photographer(text)
        if photographer:
            return photographer
    return None
