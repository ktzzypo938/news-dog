"""中時新聞網爬蟲"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import base

SOURCE_CODE = 'CHINATIMES'
BASE_URL = 'https://www.chinatimes.com'

CATEGORY_PAGES = {
    'politics': 'https://www.chinatimes.com/realtimenews/260407/',
    'lifestyle': 'https://www.chinatimes.com/realtimenews/260405/',
    'society': 'https://www.chinatimes.com/realtimenews/260402/',
    'cross_strait': 'https://www.chinatimes.com/realtimenews/260409/',
}
CATEGORY_LABELS = {
    '260407': '政治',
    '260405': '生活',
    '260402': '社會',
    '260409': '兩岸',
}

ARTICLE_RE = re.compile(r'/realtimenews/\d{14}-\d+')


def get_list_urls(session):
    all_urls = []
    for category, list_url in CATEGORY_PAGES.items():
        try:
            resp = session.get(list_url, timeout=15)
            resp.encoding = 'utf-8'
            soup = BeautifulSoup(resp.text, 'lxml')
            for a in soup.select('a[href]'):
                href = a.get('href', '')
                full_url = _normalize_url(urljoin(BASE_URL, href))
                if ARTICLE_RE.search(full_url):
                    all_urls.append(full_url)
        except Exception as e:
            print(f"[{SOURCE_CODE}] Failed to fetch {category} list: {e}")
    return list(dict.fromkeys(all_urls))


def scrape_article(session, url):
    try:
        resp = session.get(url, timeout=20)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'lxml')

        canonical = _extract_canonical_url(soup) or _normalize_url(url)
        image_url = base.extract_image_url(soup)

        title_node = soup.select_one('h1') or soup.select_one('meta[property="og:title"]')
        title = (
            title_node.get_text(strip=True)
            if getattr(title_node, 'name', '') != 'meta'
            else title_node.get('content', '')
        )
        title = title.replace(' - 中時新聞網', '').strip()

        published_at = base.extract_published_at(soup, [
            ('div.meta-info time', 'datetime'),
            ('div.meta-info time', None),
            ('span.date', None),
        ])

        content_node = soup.select_one('div.article-body')
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
    match = re.search(r'-(260407|260405|260402|260409)', url)
    return CATEGORY_LABELS.get(match.group(1), '未知') if match else '未知'


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


def _extract_clean_text(content_node):
    content = BeautifulSoup(str(content_node), 'lxml')
    for tag in content.select(
        'script, style, figure, .ad, .promote-word, .article-hash-tag, '
        '.social-share, .more-news, .recommend, iframe'
    ):
        tag.decompose()
    base.remove_promo_blocks(content)

    paragraphs = []
    for p in content.select('p'):
        text = p.get_text(strip=True)
        if text:
            paragraphs.append(text)
    if paragraphs:
        return "\n".join(paragraphs)

    return content.get_text("\n", strip=True)


def _extract_photographer(content_node):
    for node in content_node.select('figcaption, img[alt]'):
        text = node.get_text(strip=True) if node.name != 'img' else node.get('alt', '')
        photographer = base.extract_photographer(text)
        if photographer:
            return photographer
    return None
