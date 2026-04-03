"""中天新聞爬蟲（需要 ssl_verify=false）"""
import json
import re
from datetime import datetime
from bs4 import BeautifulSoup
from dateutil import parser
import base

SOURCE_CODE = 'CTI'
ALLOWED_CATS = ['政治', '社會', '國際', '要聞', '全球']

# CTI 分類 topic 頁（要聞、社會、國際）
TOPIC_PAGES = [
    '/news/topics/LaDQVMegmZ',  # 要聞
    '/news/topics/dnbepPejZB',  # 社會
    '/news/topics/Wqk9W8eD3M',  # 國際
]


def get_list_urls(session):
    all_paths = set()
    for path in TOPIC_PAGES:
        url = f'https://ctinews.com{path}'
        try:
            resp = session.get(url, timeout=15)
            paths = re.findall(r'/news/items/[a-zA-Z0-9]+', resp.text)
            all_paths.update(paths)
        except Exception as e:
            print(f"[{SOURCE_CODE}] Failed to fetch {path}: {e}")

    # 備用：若 topic 頁失效，從首頁補充
    if len(all_paths) < 10:
        print(f"[{SOURCE_CODE}] Topic pages returned {len(all_paths)} URLs, falling back to homepage...")
        try:
            resp = session.get('https://ctinews.com/', timeout=15)
            all_paths.update(re.findall(r'/news/items/[a-zA-Z0-9]+', resp.text))
        except Exception as e:
            print(f"[{SOURCE_CODE}] Fallback failed: {e}")

    return [
        ("https://ctinews.com" + p).split('?')[0].split('#')[0].rstrip('/')
        for p in all_paths
    ]


def scrape_article(session, url):
    try:
        resp = session.get(url, timeout=20)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'lxml')

        image_url = base.extract_image_url(soup)

        # 攝影師：figcaption 優先，再找第一張圖 alt
        photographer = None
        figcaption = (soup.select_one('figure.image figcaption')
                      or soup.select_one('[itemprop="articleBody"] figcaption'))
        if figcaption:
            photographer = base.extract_photographer(figcaption.get_text())
        if not photographer:
            content_area = (soup.select_one('[itemprop="articleBody"]')
                            or soup.select_one('div.article-content'))
            if content_area:
                first_img = content_area.select_one('img')
                if first_img:
                    photographer = base.extract_photographer(first_img.get('alt', ''))

        # 分類過濾（政治、社會、國際、要聞、全球）
        cat_node = soup.select_one('a.category-name') or soup.select_one('.category')
        cat_name = cat_node.get_text(strip=True) if cat_node else ""
        if cat_name and not any(c in cat_name for c in ALLOWED_CATS):
            print(f"[{SOURCE_CODE}] Skipping {url} due to category: {cat_name}")
            return None

        title_node = soup.select_one('h1.article-title') or soup.select_one('h1')
        title = title_node.get_text(strip=True) if title_node else ""

        content_node = (soup.select_one('[itemprop="articleBody"]')
                        or soup.select_one('div.article-content')
                        or soup.select_one('div.article-body')
                        or soup.select_one('div.text'))
        if content_node:
            for tag in content_node.select('script, style, .ad-container, .related-news'):
                tag.decompose()
            clean_text = content_node.get_text("\n", strip=True)
        else:
            clean_text = ""

        published_at = _parse_time(soup)

        result = {
            "source": SOURCE_CODE, "url": url,
            "title": title, "publishedAt": published_at,
            "rawHtml": "", "cleanText": clean_text,
        }
        if image_url:
            result["imageUrl"] = image_url
        if photographer:
            result["imagePhotographer"] = photographer
        return result
    except Exception as e:
        print(f"[{SOURCE_CODE}] Error scraping {url}: {e}")
        return None


def _parse_time(soup):
    # 1. article:published_time meta
    node = soup.select_one('meta[property="article:published_time"]')
    if node and node.get('content'):
        try:
            return parser.parse(node['content']).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass

    # 2. JSON-LD datePublished
    try:
        ld_node = soup.select_one('script[type="application/ld+json"]')
        if ld_node:
            ld_data = json.loads(ld_node.string)
            if isinstance(ld_data, dict) and ld_data.get('datePublished'):
                return parser.parse(ld_data['datePublished']).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        pass

    # 3. time element
    time_node = soup.select_one('time.pub-date') or soup.select_one('time')
    if time_node:
        time_str = time_node.get('datetime') or time_node.get_text(strip=True)
        try:
            return parser.parse(time_str).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass

    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
