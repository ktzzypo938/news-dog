# 新聞爬蟲部署指南

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

### 執行結果判讀

Cloud Function 的回應碼會反映來源健康狀態，方便 Cloud Scheduler / 監控發現壞掉的來源：

- `200`：正常，或本輪沒有新文章（訊息開頭若是 `WARNING:` 代表部分文章解析失敗）
- `500`：列表頁抓不到任何 URL，或有新 URL 但一篇都沒成功送入（selector 失效、被擋、ingest API 壞掉）

每輪結束會印一行 `[CODE] SUMMARY listed=.. new=.. ingested=.. skipped_date=.. skipped_cached=.. failed=..`，可直接做 log-based metric。
- `REGION`: Cloud Functions 區域

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
