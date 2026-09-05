"""
統一爬蟲入口點（Cloud Function）

部署時透過 SOURCE_CODE 環境變數指定來源（如 CNA、CTI、LTN、SET、UDN）。
也支援 HTTP query param ?source=CNA 供本地測試。

新增來源步驟：
  1. 在 sources.yml 加一筆設定
  2. 在 sources/ 目錄建立 {module}.py（實作 get_list_urls / scrape_article）
  3. 在 deploy_runner.sh 加一行部署指令

回應碼約定（讓 Cloud Scheduler / 監控看得出來源壞掉）：
  200  正常，或本輪沒有新文章
  500  列表結構失效、或至少 2 篇真正解析／匯入失敗且沒有成功文章
  503  來源 API、後端 API 或列表限流，須稍後再試
"""
import os
import importlib
import urllib3

import functions_framework

import base


def load_config():
    return base.load_sources_config()


def evaluate_run(stats):
    """依統計決定回應碼與訊息。"""
    if stats.get('retry_after_seconds') and stats['listed'] == 0:
        return 503, f"WARNING: source rate limited; retry after {stats['retry_after_seconds']} seconds"
    if stats['listed'] == 0 and not stats.get('list_ok'):
        return 500, "ERROR: list page returned no URLs (selector or site change?)"
    # 正常排除、失效網址、日期過濾與限流延後都不計入解析失敗。
    if stats['failed'] >= 2 and stats['ingested'] == 0:
        return 500, (f"ERROR: {stats['new']} new URLs but none ingested "
                     f"(failed={stats['failed']}; article parser or ingest API broken?)")
    msg = (f"Successfully processed {stats['ingested']} articles "
           f"(listed={stats['listed']}, new={stats['new']}, skipped_date={stats['skipped_date']}, "
           f"skipped_cached={stats['skipped_cached']}, failed={stats['failed']}, "
           f"skipped_filtered={stats.get('skipped_filtered', 0)}, "
           f"skipped_unavailable={stats.get('skipped_unavailable', 0)}, "
           f"deferred={stats.get('deferred', 0)}, retry_after_seconds={stats.get('retry_after_seconds', 0)})")
    if stats['failed'] > 0 or stats.get('deferred'):
        msg = "WARNING: " + msg
    return 200, msg


@functions_framework.http
def run_scraper(request):
    source_code = (request.args.get('source') or os.getenv('SOURCE_CODE', '')).upper()

    if not source_code:
        return "Missing SOURCE_CODE env var or ?source= query param", 400

    config = load_config()
    sources = config.get('sources', {})

    if source_code not in sources:
        return f"Unknown source: {source_code}. Available: {list(sources.keys())}", 400

    source_cfg = sources[source_code]

    if not source_cfg.get('enabled', True):
        return f"Source {source_code} is disabled", 200

    options = source_cfg.get('options', {})
    ssl_verify = options.get('ssl_verify', True)

    # CTI 需要停用 SSL 警告
    if not ssl_verify:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    session = base.create_session(ssl_verify=ssl_verify)

    module_name = source_cfg['module']
    try:
        source_module = importlib.import_module(f'sources.{module_name}')
    except ImportError as e:
        return f"Cannot load module 'sources.{module_name}': {e}", 500

    print(f"Starting {source_code} ({source_cfg['name']}) scraper...")
    try:
        stats = base.run_source(session, source_code, source_module)
    except (base.IngestAPIError, base.SourceFetchError) as e:
        print(f"[{source_code}] ERROR: {e}")
        return f"ERROR: {e} from {source_code}", 503

    status, message = evaluate_run(stats)
    print(f"[{source_code}] {message}")
    if status == 503 and stats.get('retry_after_seconds'):
        return f"{message} from {source_code}", status, {'Retry-After': str(stats['retry_after_seconds'])}
    return f"{message} from {source_code}", status
