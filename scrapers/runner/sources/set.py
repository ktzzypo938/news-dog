"""三立新聞爬蟲"""
import re
from datetime import datetime
from bs4 import BeautifulSoup
from dateutil import parser
import base

SOURCE_CODE = 'SET'
GROUP_IDS = ['6', '41', '5']  # 政治、社會、國際


def get_list_urls(session):
    all_urls = []
    for group_id in GROUP_IDS:
        list_url = f'https://www.setn.com/ViewAll.aspx?PageGroupID={group_id}'
        try:
            resp = session.get(list_url, timeout=15)
            soup = BeautifulSoup(resp.text, 'lxml')

            links = (soup.select('h3.view-li-title a')
                     or soup.select('div.view-li-title a')
                     or soup.select('div.newsItems h3 a')
                     or soup.select('a[href*="/News.aspx"]'))

            print(f"[{SOURCE_CODE}] Found {len(links)} links in group {group_id}")

            for a in links:
                href = a.get('href', '')
                if not href or '/News.aspx' not in href:
                    continue
                full_url = href if href.startswith('http') else "https://www.setn.com" + href
                # 保留 NewsID 參數
                m = re.search(r'NewsID=(\d+)', full_url)
                if m:
                    full_url = f"https://www.setn.com/News.aspx?NewsID={m.group(1)}"
                else:
                    full_url = full_url.split('?')[0].split('#')[0].rstrip('/')
                all_urls.append(full_url)
        except Exception as e:
            print(f"[{SOURCE_CODE}] Failed to fetch group {group_id}: {e}")

    # 備用：若分類頁抓取量不足，從首頁補充
    if len(all_urls) < 5:
        print(f"[{SOURCE_CODE}] Warning: Only {len(all_urls)} URLs from categories, trying homepage...")
        try:
            resp = session.get('https://www.setn.com/', timeout=15)
            for news_id in set(re.findall(r'NewsID=(\d+)', resp.text)):
                all_urls.append(f"https://www.setn.com/News.aspx?NewsID={news_id}")
        except Exception as e:
            print(f"[{SOURCE_CODE}] Failed to fetch homepage: {e}")

    return all_urls


def scrape_article(session, url):
    try:
        resp = session.get(url, timeout=20)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'lxml')

        image_url = base.extract_image_url(soup)

        # 攝影師：figcaption 優先，再找第一張圖 alt
        photographer = None
        figcaption = (soup.select_one('#ckuse figcaption')
                      or soup.select_one('[itemprop="articleBody"] figcaption'))
        if figcaption:
            photographer = base.extract_photographer(figcaption.get_text())
        if not photographer:
            content_area = soup.select_one('#ckuse') or soup.select_one('[itemprop="articleBody"]')
            if content_area:
                first_img = content_area.select_one('img')
                if first_img:
                    photographer = base.extract_photographer(first_img.get('alt', ''))

        title_node = soup.select_one('h1.news-title') or soup.select_one('h1')
        title = title_node.get_text(strip=True) if title_node else ""

        content_node = (soup.select_one('[itemprop="articleBody"]')
                        or soup.select_one('div#Content1')
                        or soup.select_one('article'))
        if content_node:
            for tag in content_node.select('script, style, .article-ads, .fb-quote'):
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

    # 2. time element (多個備用選擇器)
    time_node = (soup.select_one('time.page_date')
                 or soup.select_one('time.page-date')
                 or soup.select_one('span.date'))
    if time_node:
        try:
            return parser.parse(time_node.get_text(strip=True)).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass

    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
