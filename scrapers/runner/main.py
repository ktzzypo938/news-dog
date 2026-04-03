"""
統一爬蟲入口點（Cloud Function）

部署時透過 SOURCE_CODE 環境變數指定來源（如 CNA、CTI、LTN、SET、UDN）。
也支援 HTTP query param ?source=CNA 供本地測試。

新增來源步驟：
  1. 在 sources.yml 加一筆設定
  2. 在 sources/ 目錄建立 {module}.py（實作 get_list_urls / scrape_article）
  3. 在 deploy_runner.sh 加一行部署指令
"""
import os
import importlib
import urllib3

import yaml
import functions_framework

import base


def load_config():
    config_path = os.path.join(os.path.dirname(__file__), 'sources.yml')
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


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
    count = base.run_source(session, source_code, source_module)

    return f"Successfully processed {count} articles from {source_code}", 200
