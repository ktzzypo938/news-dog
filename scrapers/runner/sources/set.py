"""三立新聞爬蟲"""
import re
from bs4 import BeautifulSoup
import base

SOURCE_CODE = 'SET'
GROUP_IDS = ['6', '41', '4', '5']  # 政治、社會、生活、國際
# 舊網址 ViewAll.aspx?PageGroupID=N 已 301 到這裡；直接打新網址省一次轉址
LIST_URL = 'https://www.setn.com/viewallbypgid/{group_id}'
ARTICLE_RE = re.compile(r'^https://www\.setn\.com/news/\d+$')

# 分類頁的專屬列表容器。頁面其他區塊（熱門、焦點、側欄）是全站共用的，
# 會混進娛樂／體育，所以絕不能退回「整頁所有 /news/ 連結」的寬鬆抓法。
LIST_SELECTORS = (
    'div.about_news_list_content a[href]',
    'div.news_list_area a[href]',
    'h3.view-li-title a',      # 舊版
    'div.view-li-title a',     # 舊版
)


def get_list_urls(session):
    all_urls = []
    for group_id in GROUP_IDS:
        list_url = LIST_URL.format(group_id=group_id)
        try:
            resp = session.get(list_url, timeout=15)
            resp.encoding = 'utf-8'
            soup = BeautifulSoup(resp.text, 'lxml')

            links = []
            for selector in LIST_SELECTORS:
                links = soup.select(selector)
                if links:
                    break
            if not links:
                print(f"[{SOURCE_CODE}] WARNING: no list container matched on group {group_id} (site changed?)")
                continue

            found = 0
            for a in links:
                href = a.get('href', '')
                if not href:
                    continue
                full_url = href if href.startswith('http') else "https://www.setn.com" + href
                # 舊格式：/News.aspx?NewsID=123（保留 NewsID 參數，與後端 normalizeUrl 一致）
                m = re.search(r'NewsID=(\d+)', full_url)
                if m:
                    all_urls.append(f"https://www.setn.com/News.aspx?NewsID={m.group(1)}")
                    found += 1
                    continue
                # 新格式：/news/1879418
                full_url = full_url.split('?')[0].split('#')[0].rstrip('/')
                if ARTICLE_RE.match(full_url):
                    all_urls.append(full_url)
                    found += 1
            print(f"[{SOURCE_CODE}] Found {found} article links in group {group_id}")
        except Exception as e:
            print(f"[{SOURCE_CODE}] Failed to fetch group {group_id}: {e}")

    return list(dict.fromkeys(all_urls))


def scrape_article(session, url):
    try:
        resp = base.get_page(session, url, timeout=20, source_code=SOURCE_CODE)
        if resp is None:
            return None
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
                        or soup.select_one('#newsContent')          # 2026 新版文章頁
                        or soup.select_one('.article_content_area')
                        or soup.select_one('article'))
        if content_node:
            for tag in content_node.select('script, style, .article-ads, .fb-quote'):
                tag.decompose()
            base.remove_promo_blocks(content_node)
            clean_text = content_node.get_text("\n", strip=True)
        else:
            clean_text = ""

        published_at = base.extract_published_at(soup, [
            ('time.page_date', None),
            ('time.page-date', None),
            ('span.date', None),
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
