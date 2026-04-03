"""
共用基礎模組：HTTP Session、API 呼叫、共通工具函數
"""
import os
import json
import re
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

INGEST_API_BASE = os.getenv('INGEST_API_BASE', 'https://square-news-632027619686.asia-east1.run.app/ingest')
API_KEY = os.getenv('API_KEY', 'temporary-api-key-123')


def create_session(ssl_verify=True):
    """建立帶有 retry 策略的 HTTP Session"""
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })
    session.verify = ssl_verify
    return session


def get_new_urls(session, source_code, urls):
    """呼叫後端 API 檢查哪些 URL 尚未爬取（API 呼叫固定啟用 SSL 驗證）"""
    try:
        resp = session.post(
            f"{INGEST_API_BASE}/check-urls",
            json={"sourceCode": source_code, "urls": urls},
            headers={"X-API-KEY": API_KEY},
            timeout=15,
            verify=True,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"Error checking URLs: {e}")
    return []


def ingest_article(session, data):
    """將爬取的文章送入後端（API 呼叫固定啟用 SSL 驗證）"""
    try:
        resp = session.post(
            f"{INGEST_API_BASE}/articles",
            json=data,
            headers={"X-API-KEY": API_KEY},
            timeout=15,
            verify=True,
        )
        return resp.status_code == 202
    except Exception as e:
        print(f"Error ingesting article: {e}")
        return False


def extract_photographer(text):
    """從圖片說明文字中提取攝影師署名（整合所有來源的正則模式）"""
    if not text:
        return None
    patterns = [
        r'中央社記者(.+?)攝',          # CNA 特有
        r'記者(.+?)攝',
        r'圖／(.+?)提供',              # CTI, SET
        r'攝影[：:]\s*(.+?)(?:\s|$|）|】)',
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(1).strip()
    return None


def extract_image_url(soup):
    """從 og:image 或 JSON-LD 提取主圖 URL（各來源通用）"""
    # 1. og:image meta tag
    og_img = soup.select_one('meta[property="og:image"]')
    if og_img and og_img.get('content'):
        return og_img['content']

    # 2. JSON-LD 備用
    try:
        for ld_node in soup.select('script[type="application/ld+json"]'):
            ld_data = json.loads(ld_node.string)
            if not isinstance(ld_data, dict):
                continue
            # CNA 用 thumbnailUrl
            if ld_data.get('thumbnailUrl'):
                return ld_data['thumbnailUrl']
            img = ld_data.get('image')
            if img:
                if isinstance(img, str):
                    return img
                if isinstance(img, dict):
                    return img.get('contentUrl') or img.get('url')
                if isinstance(img, list) and img:
                    first = img[0]
                    if isinstance(first, dict):
                        return first.get('contentUrl') or first.get('url')
                    return first
    except Exception:
        pass

    return None


def run_source(session, source_code, source_module):
    """
    執行單一來源的完整爬取流程：
    1. 取得文章 URL 列表
    2. 過濾已爬取的 URL
    3. 爬取並送入後端
    返回成功數量
    """
    all_urls = source_module.get_list_urls(session)

    if not all_urls:
        print(f"[{source_code}] No URLs found")
        return 0

    unique_urls = list(set(all_urls))
    new_urls = get_new_urls(session, source_code, unique_urls)
    print(f"[{source_code}] Found {len(new_urls)} new URLs out of {len(unique_urls)}")

    success_count = 0
    for url in new_urls:
        article_data = source_module.scrape_article(session, url)
        if not article_data:
            continue
        if not article_data.get('title'):
            print(f"[{source_code}] Skipping {url}: Missing title")
            continue
        if not article_data.get('cleanText'):
            print(f"[{source_code}] Skipping {url}: Missing cleanText")
            continue
        if ingest_article(session, article_data):
            success_count += 1
        else:
            print(f"[{source_code}] Failed to ingest: {url}")

    return success_count
