# 新聞爬蟲部署指南

## 後台執行監控

共用 runner 會輸出 `telemetry=crawler_run` 的單行 JSON：開始、超過約 60 秒的進度與結束事件。
每次 HTTP 嘗試有獨立 `run_id`；Scheduler 的 job name／scheduled time 用來辨認排程時段與重試。
事件保留 revision、即時計數、錯誤階段與最多 5 個已移除 query／認證資訊的 URL 範例，不額外呼叫監控 API。
`accepted` 表示後端 HTTP 202，與文章資料庫實際新增篇數分開統計。

`newprism` 的監控收集器從 Cloud Logging 增量保存紀錄；後台入口 `/admin/crawlers`。
程式硬逾時或被終止可能無法輸出結束事件，此時由平台請求日誌／逾時未完成狀態補足。

離線驗證：`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scrapers/runner/tests -v`。

本專案目前啟用同事版 14 個新聞來源：

- `TVBS`: TVBS
- `PTS`: 公視新聞
- `EBC`: 東森新聞
- `ETTODAY`: ETtoday 新聞雲
- `CHINATIMES`: 中時新聞網
- `TTV`: 台視新聞
- `UDN`: 聯合新聞網
- `CTS`: 華視新聞
- `LTN`: 自由時報
- `FTV`: 民視新聞
- `STORM`: 風傳媒
- `SET`: 三立新聞
- `CNA`: 中央通訊社
- `CTI`: 中天新聞

各來源目前以「兩岸、政治、社會、生活」為主要抓取範圍；部分來源沒有獨立兩岸分類時，會從國際或要聞分類搭配關鍵字補抓。

其他舊來源檔案保留在 `sources/` 目錄，但 `sources.yml` 已設為 disabled，部署腳本不再納入；排程腳本會先刪除舊來源 scheduler。

## 主要架構

目前建議使用 `scrapers/runner/` 的統一爬蟲入口。所有來源共用同一份 Cloud Function 程式碼，透過 `SOURCE_CODE` 環境變數指定要執行哪一個來源。

```text
scrapers/
├── runner/
│   ├── main.py              # Cloud Function 入口
│   ├── base.py              # 共用 session、API、解析工具
│   ├── sources.yml          # 來源設定
│   └── sources/
│       ├── businessweekly.py
│       ├── cna.py
│       ├── cnews.py
│       ├── commercialtimes.py
│       ├── cti.py
│       ├── ctwant.py
│       ├── cw.py
│       ├── chinatimes.py
│       ├── ebc.py
│       ├── economic.py
│       ├── ettoday.py
│       ├── era.py
│       ├── ftv.py
│       ├── globalnews.py
│       ├── cts.py
│       ├── ltn.py
│       ├── mirror.py
│       ├── mnews.py
│       ├── newtalk.py
│       ├── new7.py
│       ├── nexttv.py
│       ├── nownews.py
│       ├── peoplenews.py
│       ├── pts.py
│       ├── reporter.py
│       ├── rwnews.py
│       ├── set.py
│       ├── storm.py
│       ├── taisounds.py
│       ├── tnl.py
│       ├── ttv.py
│       ├── tvbs.py
│       ├── upmedia.py
│       └── udn.py
├── deploy_runner.sh         # 建議部署入口
├── deploy_all.sh            # 相容入口，會轉呼叫 deploy_runner.sh
└── setup_scheduler.sh       # Cloud Scheduler 設定
```

`scrapers/cna`、`scrapers/cti`、`scrapers/ltn`、`scrapers/set`、`scrapers/udn` 是舊版獨立 Cloud Function 程式，暫時保留作為歷史參考；新維護與部署請以 `runner/` 為準。

## 資料輸出標準

每篇文章送到 ingest API 前會維持相同欄位：

```json
{
  "source": "CNA",
  "url": "https://example.com/news/1",
  "title": "文章標題",
  "publishedAt": "2026-05-17 10:04:28",
  "rawHtml": "",
  "cleanText": "清理後內文",
  "imageUrl": "https://example.com/image.jpg",
  "imagePhotographer": "攝影署名"
}
```

必填欄位是 `source`、`url`、`title`、`publishedAt`、`cleanText`。`imageUrl` 和 `imagePhotographer` 是選填欄位。

時間解析統一在 `runner/base.py`，會優先讀通用 meta tag、JSON-LD，再 fallback 到來源指定 selector。若解析不到 `publishedAt`，runner 會略過該篇，避免把解析失敗誤標成執行當下時間。

## 本地測試

進入專案根目錄後執行：

```bash
python3 scrapers/runner/test_all.py
```

做較完整的抽樣分析：

```bash
python3 scrapers/runner/analyze_all.py
```

## 部署方式

先確認 `scrapers/deploy_runner.sh` 裡的環境變數：

- `INGEST_API_BASE`: 後端 ingest API 基礎路徑
- `API_KEY`: ingest API key。**不再有預設值**，部署前必須 `export API_KEY=...`（與後端 `APP_API_KEY` 相同）
- `SCRAPER_LOOKBACK_DAYS`: 允許送入「今天往前幾天」的文章，預設 1（今天＋昨天），用來補回跨日前沒抓到的稿
- `REGION`: Cloud Functions 區域
- `PROJECT_ID`: 預設為 `square-news-483901`，部署不依賴本機目前選取的 GCP 專案。
- `CTS_FETCH_BASE_URL`、`CTS_FETCH_TOKEN`: 華視專用取頁服務的網址與金鑰；首次設定或更換時同時提供。未提供時部署腳本保留線上既有設定。

### 執行結果判讀

Cloud Function 的回應碼會反映來源健康狀態，方便 Cloud Scheduler / 監控發現壞掉的來源：

- `200`：正常、沒有近期新文章，或全部文章按規則排除。`WARNING:` 表示部分文章失敗或因限流延後。
- `500`：列表結構失效，或至少 2 篇真正解析／匯入失敗且沒有成功文章。
- `503`：來源 API 或後端 API 無法使用，或尚未取得列表即被限流；不會把 API 驗證失敗誤報為「沒有新文章」。

每輪日誌包含 `listed`、`new`、`ingested`、`skipped_date`、`skipped_cached`、`skipped_filtered`、`skipped_unavailable`、`deferred`、`retry_after_seconds`、`failed`。VIP／評論是 `skipped_filtered`；404／410 是 `skipped_unavailable`；429 會停止本輪後續請求，尚未處理的文章列為 `deferred`，由後續排程重新檢查。

中天使用頁面 Nuxt 資料中的 `news_id` 與 `release_at` 選取近期文章，不使用含錯誤版位網址的 JSON-LD。請求間隔至少 1 秒，HTTP adapter 不會在收到 429 後逐篇自動重試。

華視在 GCP 直接請求會收到來源 CloudFront 403。正式環境改由 `../edge/cts-fetch/` 的專用 Cloudflare Worker 存取華視官方 JSON API，再由原有 runner 分類、檢查重複及匯入。資料中的文章網址維持 `news.cts.com.tw`。Worker 僅接受已授權的華視分類列表與文章 API，不提供任意網址轉送。

離線回歸測試：

```bash
python3 -m unittest discover -s scrapers/runner/tests -v
node --test edge/cts-fetch/test.mjs
```

部署所有來源：

```bash
cd scrapers
./deploy_runner.sh
```

部署後會建立各來源 Cloud Functions：

- `scraper-cna`
- `scraper-cti`
- `scraper-ltn`
- `scraper-set`
- `scraper-udn`
- `scraper-tvbs`
- `scraper-ebc`
- `scraper-ftv`
- `scraper-pts`
- `scraper-cts`
- `scraper-ttv`
- `scraper-chinatimes`
- `scraper-nexttv`
- `scraper-mnews`
- `scraper-globalnews`
- `scraper-ctwant`
- `scraper-rwnews`
- `scraper-cnews`
- `scraper-tnl`
- `scraper-reporter`
- `scraper-peoplenews`
- `scraper-era`
- `scraper-new7`
- `scraper-cw`
- `scraper-businessweekly`
- `scraper-commercialtimes`
- `scraper-economic`
- `scraper-ettoday`
- `scraper-nownews`
- `scraper-storm`
- `scraper-newtalk`
- `scraper-upmedia`
- `scraper-mirror`
- `scraper-taisounds`

## Cloud Scheduler

部署完成後可設定排程：

```bash
cd scrapers
./setup_scheduler.sh
```

目前排程腳本預設每 15 分鐘觸發一次各來源 Cloud Function，並使用 OIDC 呼叫未公開的 Gen2 Cloud Function。
