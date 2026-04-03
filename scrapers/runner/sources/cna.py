"""中央通訊社爬蟲"""
from datetime import datetime
from bs4 import BeautifulSoup
from dateutil import parser
import base

SOURCE_CODE = 'CNA'
CAT_CODES = ['aipl', 'asoc', 'aopl']  # 政治、社會、國際


def get_list_urls(session):
    all_urls = []
    for code in CAT_CODES:
        list_url = f'https://www.cna.com.tw/list/{code}.aspx'
        try:
            resp = session.get(list_url, timeout=15)
            soup = BeautifulSoup(resp.text, 'lxml')
            for a in soup.select('ul.mainList li a'):
                href = a.get('href', '')
                if '/news/' in href:
                    full_url = href if href.startswith('http') else "https://www.cna.com.tw" + href
                    all_urls.append(full_url.split('?')[0].split('#')[0].rstrip('/'))
        except Exception as e:
            print(f"[{SOURCE_CODE}] Failed to fetch {code} list: {e}")
    return all_urls


def scrape_article(session, url):
    try:
        resp = session.get(url, timeout=20)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'lxml')

        image_url = base.extract_image_url(soup)

        # 從 div.paragraph 提取攝影師
        photographer = None
        content_node = soup.select_one('div.paragraph')
        if content_node:
            first_img = content_node.select_one('img')
            if first_img:
                photographer = base.extract_photographer(first_img.get('alt', ''))
        if not photographer:
            figcaption = soup.select_one('div.paragraph figcaption')
            if figcaption:
                photographer = base.extract_photographer(figcaption.get_text())

        title_node = soup.select_one('h1 span') or soup.select_one('h1')
        title = title_node.get_text(strip=True) if title_node else ""

        if content_node:
            for tag in content_node.select('script, style, .article-ads, .more-news'):
                tag.decompose()
            clean_text = content_node.get_text("\n", strip=True)
        else:
            clean_text = ""

        time_node = soup.select_one('div.updatetime span') or soup.select_one('time')
        published_at = _parse_time(time_node.get_text(strip=True) if time_node else "")

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


def _parse_time(time_str):
    try:
        return parser.parse(time_str).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
