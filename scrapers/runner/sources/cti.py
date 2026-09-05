"""中天新聞爬蟲（需要 ssl_verify=false）"""
import re
import json
from bs4 import BeautifulSoup
import base

SOURCE_CODE = 'CTI'
ALLOWED_CATS = ['政治', '社會', '生活', '國際', '要聞', '全球']
REQUEST_INTERVAL_SECONDS = 1.0

# CTI 分類 topic 頁（要聞、社會、國際）
TOPIC_PAGES = [
    '/news/topics/LaDQVMegmZ',  # 要聞
    '/news/topics/dnbepPejZB',  # 社會
    '/news/topics/A65QZ5exYy',  # 生活
    '/news/topics/Wqk9W8eD3M',  # 國際
]


def get_list_urls(session):
    session._scraper_request_interval = REQUEST_INTERVAL_SECONDS
    all_urls = []
    valid_pages = 0
    for path in TOPIC_PAGES:
        url = f'https://ctinews.com{path}'
        try:
            resp = base.get_page(session, url, timeout=15, source_code=SOURCE_CODE)
            if resp is None:
                if vars(session).get('_scraper_rate_limited'):
                    break
                continue
            urls = _extract_list_urls(BeautifulSoup(resp.text, 'lxml'))
            if urls is not None:
                valid_pages += 1
                all_urls.extend(urls)
        except Exception as e:
            print(f"[{SOURCE_CODE}] Failed to fetch {path}: {e}")

    # 只有頁面結構失效才用首頁；近期文章少或全是舊文，不代表列表壞掉。
    if not valid_pages and not vars(session).get('_scraper_rate_limited'):
        print(f"[{SOURCE_CODE}] Topic page data unavailable, trying homepage...")
        try:
            resp = base.get_page(session, 'https://ctinews.com/', timeout=15, source_code=SOURCE_CODE)
            if resp is not None:
                urls = _extract_list_urls(BeautifulSoup(resp.text, 'lxml'))
                if urls is not None:
                    valid_pages += 1
                    all_urls.extend(urls)
        except Exception as e:
            print(f"[{SOURCE_CODE}] Fallback failed: {e}")

    session._scraper_list_valid = bool(valid_pages)
    return list(dict.fromkeys(all_urls))


def _extract_list_urls(soup):
    """Nuxt 的 news_id 才是文章 ID；JSON-LD 的版位 id 會組出大量 410 網址。"""
    node = soup.find('script', id='__NUXT_DATA__')
    try:
        data = json.loads(node.string or node.get_text()) if node else None
    except (ValueError, TypeError):
        return None
    if not isinstance(data, list):
        return None

    def scalar(ref):
        if isinstance(ref, int) and not isinstance(ref, bool) and 0 <= ref < len(data):
            value = data[ref]
            return value if isinstance(value, str) else None
        return None

    articles = {}
    recognized = False
    target_dates = base.get_target_dates()
    for item in data:
        if not isinstance(item, dict) or 'news_id' not in item or 'release_at' not in item:
            continue
        recognized = True
        article_id = scalar(item['news_id'])
        published_at = base.parse_datetime(scalar(item['release_at']))
        if not article_id or not re.fullmatch(r'[A-Za-z0-9]+', article_id) or not published_at:
            continue
        if not base.should_ingest_published_at(published_at, target_dates):
            continue
        articles[article_id] = max(articles.get(article_id, ''), published_at)
    if not recognized:
        return None
    return [f'https://ctinews.com/news/items/{article_id}'
            for article_id in sorted(articles, key=lambda key: articles[key], reverse=True)]


def scrape_article(session, url):
    try:
        session._scraper_request_interval = REQUEST_INTERVAL_SECONDS
        resp = base.get_page(session, url, timeout=20, source_code=SOURCE_CODE)
        if resp is None:
            return None
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
            return base.SkippedArticle('category:' + cat_name)

        title_node = soup.select_one('h1.article-title') or soup.select_one('h1')
        title = title_node.get_text(strip=True) if title_node else ""

        content_node = (soup.select_one('[itemprop="articleBody"]')
                        or soup.select_one('div.article-content')
                        or soup.select_one('div.article-body')
                        or soup.select_one('div.text'))
        if content_node:
            for tag in content_node.select('script, style, .ad-container, .related-news'):
                tag.decompose()
            base.remove_promo_blocks(content_node)
            clean_text = content_node.get_text("\n", strip=True)
        else:
            clean_text = ""

        published_at = base.extract_published_at(soup, [
            ('time.pub-date', 'datetime'),
            ('time.pub-date', None),
            ('time', None),
        ])

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
