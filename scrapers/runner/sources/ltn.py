"""自由時報爬蟲"""
from bs4 import BeautifulSoup
import base

SOURCE_CODE = 'LTN'
CATEGORIES = ['politics', 'society', 'life', 'world']  # 政治、社會、生活、國際


def get_list_urls(session):
    all_urls = []
    for cat in CATEGORIES:
        list_url = f'https://news.ltn.com.tw/list/breakingnews/{cat}'
        try:
            resp = session.get(list_url, timeout=15)
            soup = BeautifulSoup(resp.text, 'lxml')
            for a in soup.select('ul.list li a'):
                href = a.get('href', '')
                if '/news/' in href and 'breakingnews' in href:
                    all_urls.append(href.split('?')[0].split('#')[0].rstrip('/'))
        except Exception as e:
            print(f"[{SOURCE_CODE}] Failed to fetch {cat} list: {e}")
    return all_urls


def scrape_article(session, url):
    try:
        resp = session.get(url, timeout=20)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'lxml')

        image_url = base.extract_image_url(soup)

        # 攝影師：先從第一張圖的 title/alt，再從 figcaption
        photographer = None
        first_img = (soup.select_one('[itemprop="articleBody"] img')
                     or soup.select_one('article img'))
        if first_img:
            caption_text = first_img.get('title', '') or first_img.get('alt', '')
            photographer = base.extract_photographer(caption_text)
        if not photographer:
            figcaption = (soup.select_one('[itemprop="articleBody"] figcaption')
                          or soup.select_one('.photo_desc'))
            if figcaption:
                photographer = base.extract_photographer(figcaption.get_text())

        title_node = soup.select_one('div.whitecon h1') or soup.select_one('h1')
        title = title_node.get_text(strip=True) if title_node else ""

        # LTN 正文在 [itemprop="articleBody"] 下的 div.text 裡
        # 注意：不能用 .boxTitle 當 remove selector，因為 div.text.boxTitle.boxText 就是正文 div
        body = soup.select_one('[itemprop="articleBody"]')
        content_node = (body.select_one('div.text') if body else None) or soup.select_one('div.text')
        if content_node:
            for tag in content_node.select('script, style, .article_popular, .apps, .author, .disclaim, .further_reading, .adHeight250, .adHeight280'):
                tag.decompose()
            base.remove_promo_blocks(content_node)
            paragraphs = content_node.find_all('p')
            if paragraphs:
                texts = [
                    p.get_text(strip=True) for p in paragraphs
                    if p.get_text(strip=True)
                    and "請繼續往下閱讀" not in p.get_text(strip=True)
                    and "點我下載APP" not in p.get_text(strip=True)
                ]
                clean_text = "\n".join(texts)
            else:
                clean_text = content_node.get_text("\n", strip=True)
        else:
            clean_text = ""

        published_at = base.extract_published_at(soup, [
            ('span.time', None),
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
