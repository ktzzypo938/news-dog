"""
共用基礎模組：HTTP Session、API 呼叫、共通工具函數
"""
import os
import json
import re
import importlib
import requests
import yaml
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dateutil import parser
from zoneinfo import ZoneInfo

INGEST_API_BASE = os.getenv('INGEST_API_BASE', 'https://square-news-632027619686.asia-east1.run.app/ingest')
API_KEY = os.getenv('API_KEY', 'temporary-api-key-123')
SCRAPER_ONLY_TODAY = os.getenv('SCRAPER_ONLY_TODAY', 'true').strip().lower() not in ('0', 'false', 'no')
SCRAPER_TARGET_DATE = os.getenv('SCRAPER_TARGET_DATE')
SCRAPER_TIMEZONE = os.getenv('SCRAPER_TIMEZONE', 'Asia/Taipei')

COMMON_TIME_SELECTORS = [
    ('meta[property="article:published_time"]', 'content'),
    ('meta[name="pubdate"]', 'content'),
    ('meta[itemprop="datePublished"]', 'content'),
    ('time[datetime]', 'datetime'),
]


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


def load_sources_config():
    config_path = os.path.join(os.path.dirname(__file__), 'sources.yml')
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def iter_enabled_sources():
    config = load_sources_config()
    for source_code, source_cfg in config.get('sources', {}).items():
        if not source_cfg.get('enabled', True):
            continue
        module = importlib.import_module(f"sources.{source_cfg['module']}")
        options = source_cfg.get('options', {})
        yield (
            source_code,
            source_cfg.get('name', source_code),
            module,
            options.get('ssl_verify', True),
        )


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


def parse_datetime(value):
    """將各來源時間格式統一成後端使用的 yyyy-MM-dd HH:mm:ss。"""
    if not value:
        return None
    try:
        return parser.parse(str(value).strip()).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return None


def get_target_date():
    """取得本次允許送入的日期（yyyy-MM-dd）。"""
    if SCRAPER_TARGET_DATE:
        return SCRAPER_TARGET_DATE
    try:
        return datetime.now(ZoneInfo(SCRAPER_TIMEZONE)).date().isoformat()
    except Exception:
        return datetime.now().date().isoformat()


def should_ingest_published_at(published_at, target_date=None):
    """Cloud Function 預設只送入今天的文章，避免來源列表頁把舊文補進 DB。"""
    if not SCRAPER_ONLY_TODAY:
        return True
    if not published_at:
        return False
    return str(published_at).startswith(target_date or get_target_date())


def extract_published_at(soup, selectors=None):
    """依通用 meta tag、JSON-LD、來源指定 selector 順序解析發布時間。"""
    for selector, attr in COMMON_TIME_SELECTORS:
        node = soup.select_one(selector)
        if not node:
            continue
        value = node.get(attr) if attr else node.get_text(strip=True)
        parsed = parse_datetime(value)
        if parsed:
            return parsed

    for ld_node in soup.select('script[type="application/ld+json"]'):
        for value in _walk_json_ld_dates(_load_json_ld(ld_node)):
            parsed = parse_datetime(value)
            if parsed:
                return parsed

    for selector, attr in selectors or []:
        node = soup.select_one(selector)
        if not node:
            continue
        value = node.get(attr) if attr else node.get_text(strip=True)
        parsed = parse_datetime(value)
        if parsed:
            return parsed

    return None


def _load_json_ld(ld_node):
    try:
        if not ld_node.string:
            return None
        return json.loads(ld_node.string)
    except Exception:
        return None


def _walk_json_ld_dates(value):
    if isinstance(value, dict):
        for key in ('datePublished', 'dateCreated'):
            if value.get(key):
                yield value[key]
        graph = value.get('@graph')
        if graph:
            yield from _walk_json_ld_dates(graph)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_json_ld_dates(item)


# ── 內文雜訊清理（推薦閱讀、廣告、社群推廣等非本文內容）──

# 行首推廣符號：台灣新聞站的「推薦文章連結」幾乎都以這些符號開頭
_PROMO_BULLET_RE = re.compile(r'^\s*[▪▶►▸★☆✦‣👉]')

# 推薦區標頭：出現在文末時，該行以下全部視為推薦區
_PROMO_HEADER_RE = re.compile(
    r'^【?('
    r'全球熱話題|延伸閱讀|相關新聞|相關報導|推薦閱讀|推薦新聞|更多新聞|更多相關新聞|'
    r'更多報導|熱門新聞|熱門文章|熱門話題|看更多|你可能想看|你可能還想看|大家都在看|'
    r'網友都在看|精選閱讀|焦點新聞|今日推薦|編輯精選'
    r')】?[:：]?$'
)

# 單行即刪的雜訊（APP 推廣、社群導流、免責聲明等）
_PROMO_LINE_RES = [
    re.compile(r'^更多\s*[^，。]{0,12}(報導|新聞|內容)$'),
    re.compile(r'(點我)?下載[^，。]{0,10}(APP|App|app)'),
    re.compile(r'(按讚)?加入[^，。]{0,12}(粉絲團|粉絲專頁|好友|LINE)'),
    re.compile(r'(訂閱|追蹤)[^，。]{0,12}(頻道|粉絲團|粉絲專頁|IG|Instagram|YouTube|Youtube|LINE|臉書)'),
    re.compile(r'請繼續往下閱讀'),
    re.compile(r'往下滑.{0,6}看更多'),
    re.compile(r'^(廣告|AD|贊助|贊助內容|Sponsored)$', re.IGNORECASE),
    re.compile(r'^◤.*◢$'),                       # UDN 促購/推廣塊標題
    re.compile(r'本文(由|經)[^，。]{0,20}(授權|同意)(轉載|刊登)'),
    re.compile(r'在\s*Google\s*(新聞|News)\s*上關注'),
    re.compile(r'^\d+\s*小時前$'),                 # 推薦卡片殘留的相對時間
]


def sanitize_clean_text(text):
    """移除 cleanText 中的推薦閱讀、廣告、社群推廣等非本文行（所有來源統一套用）。"""
    if not text:
        return text
    lines = text.splitlines()
    total = len(lines)
    out = []
    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        if _PROMO_HEADER_RE.match(line):
            # 標頭出現在文章尾段 → 之後全是推薦區，整段截斷
            if i >= total * 0.6:
                break
            continue  # 出現在前中段時僅刪標頭行
        if _PROMO_BULLET_RE.match(line):
            continue
        if any(p.search(line) for p in _PROMO_LINE_RES):
            continue
        out.append(line)
    return "\n".join(out)


# DOM 層通用雜訊 selector（各來源共用，在 get_text 前呼叫）
_JUNK_SELECTOR = (
    'script, style, iframe, noscript, aside, '
    '[class*="ad-"], [class*="-ad"], [id*="google_ads"], '
    '[class*="related"], [class*="recommend"], [class*="promo"], '
    '[class*="social"], [class*="share"], [class*="fb-"]'
)


def remove_promo_blocks(content_node):
    """DOM 層清理：移除廣告/推薦 class 區塊，以及「幾乎整塊都是連結」的推薦文章區。

    UDN 等站的編輯推廣區塊沒有 class（純 inline style），無法用 selector 鎖定，
    改以連結密度判斷：一個區塊有 2 個以上連結、且 75% 以上文字都在連結內，
    就視為推薦區而非本文。
    """
    if content_node is None:
        return
    for tag in content_node.select(_JUNK_SELECTOR):
        tag.decompose()

    for el in content_node.find_all(['div', 'section', 'ul', 'ol', 'p']):
        if not el.parent:      # 已隨外層一起被移除
            continue
        text = el.get_text(strip=True)
        if len(text) < 20:
            continue
        links = el.find_all('a')
        if len(links) < 2:
            continue
        link_text_len = sum(len(a.get_text(strip=True)) for a in links)
        if link_text_len / len(text) > 0.75:
            el.decompose()


def extract_photographer(text):
    """從圖片說明文字中提取攝影師署名（整合所有來源的正則模式）"""
    if not text:
        return None
    patterns = [
        r'中央社記者([^，。／（）()\s]{1,20})攝',          # CNA 特有
        r'（([^）]{1,20})攝）',
        r'(?:圖／)?記者([^，。／（）()\s]{1,20})攝',
        r'圖／(.+?)提供',              # CTI, SET
        r'圖／([^，。／（）()\s]{1,40})',
        r'攝影[：:]\s*(.+?)(?:\s|$|）|】)',
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            credit = m.group(1).strip()
            credit = re.sub(r'^(圖／)?記者', '', credit).strip()
            credit = re.sub(r'^資料照[，,、]?', '', credit).strip()
            return credit
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

    unique_urls = list(dict.fromkeys(all_urls))
    new_urls = get_new_urls(session, source_code, unique_urls)
    print(f"[{source_code}] Found {len(new_urls)} new URLs out of {len(unique_urls)}")

    target_date = get_target_date() if SCRAPER_ONLY_TODAY else None
    success_count = 0
    skipped_outside_date = 0
    for url in new_urls:
        article_data = source_module.scrape_article(session, url)
        if not article_data:
            continue
        # 中央雜訊過濾：不論來源自身清理邏輯，統一再過濾一次推薦/廣告內容
        article_data['cleanText'] = sanitize_clean_text(article_data.get('cleanText'))
        if not article_data.get('title'):
            print(f"[{source_code}] Skipping {url}: Missing title")
            continue
        if not article_data.get('cleanText'):
            print(f"[{source_code}] Skipping {url}: Missing cleanText")
            continue
        if not article_data.get('publishedAt'):
            print(f"[{source_code}] Skipping {url}: Missing publishedAt")
            continue
        if not should_ingest_published_at(article_data.get('publishedAt'), target_date):
            skipped_outside_date += 1
            continue
        if ingest_article(session, article_data):
            success_count += 1
        else:
            print(f"[{source_code}] Failed to ingest: {url}")

    if skipped_outside_date:
        print(f"[{source_code}] Skipped {skipped_outside_date} URLs outside target date {target_date}")

    return success_count
