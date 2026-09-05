"""聯合新聞網爬蟲"""
import re
from bs4 import BeautifulSoup
import base

SOURCE_CODE = 'UDN'
CAT_IDS = ['1', '2', '9', '5']  # 要聞/政治、社會、生活、國際


def get_list_urls(session):
    all_urls = []
    for cat_id in CAT_IDS:
        list_url = f'https://udn.com/news/breaknews/1/{cat_id}'
        try:
            resp = session.get(list_url, timeout=15)
            soup = BeautifulSoup(resp.text, 'lxml')
            for a in soup.select('div.story-list__text h2 a'):
                href = a.get('href')
                if not href:
                    continue
                full_url = "https://udn.com" + href.split('?')[0].split('#')[0].rstrip('/')
                all_urls.append(full_url)
        except Exception as e:
            print(f"[{SOURCE_CODE}] Failed to fetch cat {cat_id}: {e}")
    return all_urls


def scrape_article(session, url):
    try:
        resp = base.get_page(session, url, timeout=20, source_code=SOURCE_CODE)
        if resp is None:
            return None
        soup = BeautifulSoup(resp.text, 'lxml')

        image_url = base.extract_image_url(soup)

        # 攝影師：UDN 從主圖 alt 或 figcaption 提取
        photographer = None
        cover_img = (soup.select_one('.article-content__cover img')
                     or soup.select_one('section.article-content__editor img'))
        if cover_img:
            photographer = base.extract_photographer(cover_img.get('alt', ''))
        if not photographer:
            figcaption = (soup.select_one('.article-content__cover figcaption')
                          or soup.select_one('section.article-content__editor figcaption'))
            if figcaption:
                photographer = base.extract_photographer(figcaption.get_text())
        # UDN 特有：從圖說末尾取出通訊社名稱（如「路透」「美聯社」）
        if not photographer and cover_img:
            alt_text = cover_img.get('alt', '').strip()
            m = re.search(r'。([^\s。（）]{1,10})$', alt_text)
            if m:
                source = m.group(1).strip()
                if source and len(source) <= 8:
                    photographer = source

        title_node = soup.select_one('h1.article-content__title')
        title = title_node.get_text(strip=True) if title_node else ""

        content_node = soup.select_one('section.article-content__editor')
        if content_node:
            for tag in content_node.select('script, style, .inline-ad, .article-content__info'):
                tag.decompose()
            base.remove_promo_blocks(content_node)
            clean_text = content_node.get_text("\n", strip=True)
        else:
            clean_text = ""

        published_at = base.extract_published_at(soup, [
            ('time.article-content__time', None),
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
