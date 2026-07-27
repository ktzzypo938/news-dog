# 台灣主流媒體爬蟲擴充計畫

更新日期：2026-05-22

## 2026-05-22 新方向

老闆版最終清單已整理到 `docs/boss-media-task-list.md`，後續新增來源以該文件為主要 task backlog。本文件保留原本規劃脈絡、共同資料標準與實作流程；原先的 15 家優先清單改為歷史參考。

`TAISOUNDS` 太報已完成並保留在 runner，但不列入老闆版 33 家清單。

## 判斷依據

本計畫用三個角度挑選新增媒體：

- 來源型態：優先選有紙本新聞/雜誌背景的媒體，或專門做網路新聞的原生網媒。
- 原始內容：優先爬媒體自己的網站，暫不優先做 Yahoo 新聞、LINE TODAY 等聚合入口，避免重複與授權邊界不清。
- 內容型態：優先選文字新聞站；電視新聞台、影音導向來源先降為候補。
- 主題範圍：優先支援兩岸、社會、政治；工業、商業、純財經媒體不列入第一階段。
- 可維護性：優先選靜態 HTML、RSS、清楚分類頁；需要瀏覽器或強反爬的來源排後面。

參考資料：

- Reuters Institute Digital News Report 2025 Taiwan: https://reutersinstitute.politics.ox.ac.uk/digital-news-report/2025/taiwan
- RSF Taiwan media landscape: https://rsf.org/en/analyse_regionale/958
- NCC 頻道清冊： https://www.ncc.gov.tw/chinese/show_file.aspx?file_sn=64850&table_name=news
- 信傳媒對 ETtoday 與主要網路媒體競爭者整理： https://www.cmmedia.com.tw/home/articles/47651

## 現況

目前已完成並納入 `scrapers/runner`：

| 狀態 | source | 媒體 | module | 備註 |
|---|---|---|---|---|
| DONE | CNA | 中央通訊社 | `cna.py` | 既有為政治、社會、國際；後續補兩岸 |
| DONE | CTI | 中天新聞 | `cti.py` | 需 `ssl_verify=false` |
| DONE | LTN | 自由時報 | `ltn.py` | 已修正 publishedAt |
| DONE | SET | 三立新聞 | `set.py` | 既有為政治、社會、國際；後續補兩岸 |
| DONE | UDN | 聯合新聞網 | `udn.py` | 既有為要聞/政治、社會、國際；後續補兩岸 |
| READY | TVBS | TVBS | `tvbs.py` | 已完成政治、社會、兩岸，本地驗證通過，待部署 |
| READY | EBC | 東森新聞 | `ebc.py` | 已完成政治、社會、兩岸，本地驗證通過，待部署 |
| READY | FTV | 民視新聞 | `ftv.py` | 已完成政治、社會、兩岸，本地驗證通過，待部署 |
| READY | PTS | 公視新聞 | `pts.py` | 已完成政治、社會、兩岸，本地驗證通過，待部署 |
| READY | CTS | 華視新聞 | `cts.py` | 已完成政治、社會、兩岸關鍵字篩選，本地驗證通過，待部署 |
| READY | TTV | 台視新聞 | `ttv.py` | 已完成政治、社會、兩岸關鍵字篩選，本地驗證通過，待部署 |
| READY | NEXTTV | 壹電視 | `nexttv.py` | 已完成政治、社會、兩岸，本地驗證通過，待部署 |
| READY | MNEWS | 鏡新聞 | `mnews.py` | 已完成政治、社會、兩岸關鍵字篩選，本地驗證通過，待部署 |
| READY | GLOBALNEWS | 寰宇新聞 | `globalnews.py` | 已完成今日重要新聞關鍵字分類，本地驗證通過，待部署 |
| READY | CTWANT | CTWANT | `ctwant.py` | 已完成政治、社會、兩岸關鍵字篩選，本地驗證通過，待部署 |
| READY | RWNEWS | 菱傳媒 | `rwnews.py` | 已完成 JSON 資料源與關鍵字分類，本地驗證通過，待部署；資料源最新時間需上線前再確認 |
| READY | CNEWS | 匯流新聞網 | `cnews.py` | 已完成政治、社會、兩岸關鍵字篩選，本地驗證通過，待部署；兩岸近期候選量略低 |
| READY | TNL | 關鍵評論網 | `tnl.py` | 已完成政治、社會、中國/兩岸分類，本地驗證通過，待部署；使用 NewsArticle JSON-LD |
| READY | REPORTER | 報導者 | `reporter.py` | 已完成政治、社會、兩岸關鍵字篩選，本地驗證通過，待部署；使用 REDUX state，UTC 時間轉台灣時間 |
| READY | PEOPLENEWS | 民報 | `peoplenews.py` | 已確認目前官方站為 `www.peoplenews.tw`，使用 WordPress REST API；政治、社會完成，兩岸候選量較低 |
| READY | ERA | 年代新聞 | `era.py` | 已確認官方文字新聞站為 `eracom.com.tw/EraNews`，完成政治、社會、兩岸，本地驗證通過 |
| READY | NEW7 | 新新聞 | `new7.py` | 已確認獨立 `new7.storm.mg/article` URL 與 JSON-LD；低量深度來源，政治 30、社會 24、兩岸 14 |
| READY | CW | 天下雜誌 | `cw.py` | 已完成政治、社會、兩岸分類頁，本地驗證通過；社會候選量較低 |
| READY | BUSINESSWEEKLY | 商業周刊 | `businessweekly.py` | 已完成焦點/時事與趨勢中國入口，本地驗證通過；政治/社會候選量較低 |
| READY | COMMERCIALTIMES | 工商時報 | `commercialtimes.py` | 已完成要聞、兩岸與民生政策關鍵字入口，本地驗證通過；避開會回 403 的即時分類 |
| READY | ECONOMIC | 經濟日報 | `economic.py` | 已完成要聞、兩岸與民生/生活議題入口，本地驗證通過；與 UDN 為不同 source code |
| READY | CHINATIMES | 中時新聞網 | `chinatimes.py` | 已完成政治、社會、兩岸，本地驗證通過，待部署 |
| READY | ETTODAY | ETtoday 新聞雲 | `ettoday.py` | 已完成政治、社會、兩岸，本地驗證通過，待部署 |
| READY | NOWNEWS | NOWnews 今日新聞 | `nownews.py` | 已完成政治、社會、兩岸，本地驗證通過，待部署 |
| READY | STORM | 風傳媒 | `storm.py` | 已完成政治、社會/地方新聞、兩岸，本地驗證通過，待部署 |
| READY | NEWTALK | Newtalk 新頭殼 | `newtalk.py` | 已完成政治、社會、中國/兩岸，本地驗證通過，待部署 |
| READY | UPMEDIA | 上報 | `upmedia.py` | 已完成政治、社會、兩岸局勢，本地驗證通過，待部署 |
| READY | MIRROR | 鏡週刊 | `mirror.py` | 已完成政治、社會、兩岸關鍵字篩選，本地驗證通過，待部署 |
| READY | TAISOUNDS | 太報 | `taisounds.py` | 已完成政治、社會、美中台/兩岸，本地驗證通過，待部署 |

## 共同資料標準

每個新來源都要輸出同一份 contract：

| 欄位 | 必填 | 說明 |
|---|---|---|
| `source` | yes | 來源代碼，例如 `ETTODAY` |
| `url` | yes | canonical URL，去除追蹤參數 |
| `title` | yes | 文章標題 |
| `publishedAt` | yes | `YYYY-MM-DD HH:mm:ss` |
| `cleanText` | yes | 清理後純文字內文 |
| `rawHtml` | yes | 目前固定空字串 |
| `imageUrl` | no | 主圖 URL |
| `imagePhotographer` | no | 攝影或圖片來源署名 |

分類先維持目前產品範圍：

| 標準分類 | 中文 | 說明 |
|---|---|---|
| `politics` | 政治 | 政治、要聞中明確政治類 |
| `society` | 社會 | 社會、地方事件、司法、警政 |
| `cross_strait` | 兩岸 | 兩岸、陸港澳、台海關係 |

## 舊版新增 15 家優先清單（歷史參考）

如果只看「紙本新聞／報系轉型」，目前最直接的缺口是 `CHINATIMES`；`UDN`、`LTN` 已在現有來源中。其餘紙本/雜誌系多半偏財經、商業或深度專題，與本輪兩岸、社會、政治追蹤的貼合度較低。

| 優先 | source | 媒體 | 類型 | 本輪建議 |
|---:|---|---|---|---|
| READY | CHINATIMES | 中時新聞網 | 紙本報紙轉型 | 已完成本地驗證，待部署 |
| 已有 | UDN | 聯合新聞網 | 報系轉型 | 已完成，後續補兩岸分類 |
| 已有 | LTN | 自由時報 | 報紙轉型 | 已完成，後續補兩岸分類 |
| READY | MIRROR | 鏡週刊 | 紙本雜誌 + 網路新聞 | 已完成本地驗證，待部署 |
| 候補 | REPORTER | 報導者 | 原生深度新聞 | 非紙本，但適合政治社會深度補充 |
| READY | ECONOMIC | 經濟日報 | 報系/財經報紙 | 已依老闆新方向納入，使用要聞、兩岸與民生/生活議題入口 |
| READY | COMMERCIALTIMES | 工商時報 | 工商報紙 | 已依老闆新方向納入，使用要聞、兩岸與民生政策入口 |

難度：

- A：預期 `requests + BeautifulSoup` 可完成。
- B：可能需要 embedded JSON、API 或 selector 細修。
- C：可能需要 Scrapling / Playwright / Cloud Run。

狀態：

- TODO：尚未開始
- PROBE：可爬性調查中
- IMPLEMENTING：開發中
- VALIDATING：抽樣驗證中
- READY：可部署
- DEPLOYED：已部署
- BLOCKED：需決策或技術突破

| 順序 | 狀態 | source | 媒體 | 類型 | 起始 URL | 難度 | 備註 |
|---:|---|---|---|---|---|---|---|
| 1 | READY | CHINATIMES | 中時新聞網 | 紙本報紙轉型 | https://www.chinatimes.com/realtimenews/ | A | 已完成政治/社會/兩岸爬蟲與本地驗證，待部署 |
| 2 | READY | ETTODAY | ETtoday 新聞雲 | 原生網路新聞 | https://www.ettoday.net/news/news-list.htm | A | 已完成政治/社會/兩岸爬蟲與本地驗證，待部署 |
| 3 | READY | NOWNEWS | NOWnews 今日新聞 | 原生網路新聞 | https://www.nownews.com/ | A | 已完成政治/社會/兩岸爬蟲與本地驗證，待部署 |
| 4 | READY | STORM | 風傳媒 | 原生網路新聞 | https://www.storm.mg/ | B | 已完成政治/社會/兩岸爬蟲與本地驗證，待部署；社會以地方新聞頻道對應 |
| 5 | READY | NEWTALK | 新頭殼 | 原生網路新聞 | https://newtalk.tw/ | A | 已完成政治/社會/兩岸爬蟲與本地驗證，待部署；兩岸以中國分類對應 |
| 6 | READY | UPMEDIA | 上報 | 原生網路新聞 | https://www.upmedia.mg/ | B | 已完成政治/社會/兩岸爬蟲與本地驗證，待部署；需補瀏覽器 headers |
| 7 | READY | MIRROR | 鏡週刊 | 紙本雜誌 + 網路新聞 | https://www.mirrormedia.mg/ | B | 已完成政治/社會/兩岸爬蟲與本地驗證，待部署；使用 Next embedded data 與 GraphQL 列表 |
| 8 | READY | TAISOUNDS | 太報 | 原生網路新聞 | https://www.taisounds.com/ | B | 已完成政治/社會/美中台爬蟲與本地驗證，待部署；列表第二頁後使用 infinatesection JSON |
| 9 | TODO | CMEDIA | 信傳媒 | 原生網路新聞 | https://www.cmmedia.com.tw/ | A | 文字新聞站，政治內容多 |
| 10 | READY | TNL | 關鍵評論網 | 原生網路新聞/評論 | https://www.thenewslens.com/ | B | 已完成政治/社會/中國分類與本地驗證，待部署；正文取 NewsArticle JSON-LD |
| 11 | READY | REPORTER | 報導者 | 原生網路深度新聞 | https://www.twreporter.org/ | B | 已完成政治/社會/兩岸關鍵字分類與本地驗證，待部署 |
| 12 | TODO | READR | READr | 原生網路資料新聞 | https://www.readr.tw/ | B | 更新節奏較慢，偏資料新聞 |
| 13 | TODO | RFA | 自由亞洲電台繁中 | 專門網路新聞 | https://www.rfa.org/cantonese?encoding=traditional | B | 兩岸/中國議題多，需確認繁中路徑 |
| 14 | TODO | VOACHINESE | 美國之音中文網 | 專門網路新聞 | https://www.voachinese.com/ | B | 兩岸/中國/國際政治多，需確認繁中與授權邊界 |
| 15 | READY | PEOPLENEWS | 民報 | 原生網路新聞 | https://www.peoplenews.tw/ | B | 已確認新站並完成本地驗證，待部署；舊 `peoplemedia.tw` 不作為新 ingest 來源 |

## 暫不列入第一批

| 媒體/平台 | 原因 | 後續 |
|---|---|---|
| Yahoo 奇摩新聞 | 聚合入口，來源重複高 | 若要做，應只做索引與來源映射，不 ingest 全文 |
| LINE TODAY | 聚合入口，來源重複高 | 同 Yahoo |
| 經濟日報 | 已依老闆新方向納入 Batch 4 | 持續觀察財經內容比例，必要時收斂關鍵字 |
| 工商時報 | 已依老闆新方向納入 Batch 4 | 持續觀察財經內容比例，必要時收斂關鍵字 |
| 商業周刊 | 已依老闆新方向納入 Batch 4 | 社會分類以民生生活關鍵字補齊 |
| 天下雜誌 | 已依老闆新方向納入 Batch 4 | 深度來源更新量可能較低 |
| 東森新聞 | 新聞台/影音來源，不符合本輪優先原則 | 之後若要補新聞台再做 |
| 民視新聞網 | 新聞台/影音來源，不符合本輪優先原則 | 之後若要補新聞台再做 |
| 公視新聞網 | 公共媒體且重要，但本輪先以紙本/原生網媒為主 | 可作為新聞台/公共媒體批次第一順位 |
| 台視/華視/中視 | 無線電視新聞，不符合本輪優先原則 | 之後若要補新聞台再做 |
| 壹電視 | 新聞台/影音來源，不符合本輪優先原則 | 之後若要補新聞台再做 |
| 鏡新聞 | 新聞台來源；同集團的鏡週刊已完成 | 後續若要補新聞台再評估 |
| 年代新聞 | 主流新聞台，但官方網站路徑需再確認 | 若確認穩定列表，替換第 15 名或加入第二批 |

## 每家實作流程

每新增一家，都照同一流程走：

1. PROBE：確認分類頁、文章 URL、canonical URL、是否需要 JS。
2. IMPLEMENTING：建立 `scrapers/runner/sources/{module}.py`。
3. CONFIG：在 `scrapers/runner/sources.yml` 加上 source。
4. VALIDATING：跑 `PYTHONDONTWRITEBYTECODE=1 python3 scrapers/runner/test_all.py`。
5. ANALYZE：跑 `PYTHONDONTWRITEBYTECODE=1 python3 scrapers/runner/analyze_all.py`，確認欄位完整率。
6. REVIEW：抽看至少 5 篇文章的 title / publishedAt / cleanText / imageUrl。
7. DEPLOY：確認通過後再部署單一來源或整批。

## 驗收標準

每個來源必須達到：

- 列表頁至少抓到 20 筆候選 URL；若該來源本身更新量較低，需註明。
- 抽樣 5 篇文章中，`title`、`publishedAt`、`cleanText` 必須 5/5。
- `publishedAt` 不可以用執行當下時間 fallback。
- `cleanText` 最短建議大於 100 字；若是快訊型文章需註明例外。
- URL 去重後不可含 `utm_*`、`fbclid` 等追蹤參數。
- 不新增 browser / Scrapling 依賴，除非 PROBE 確認必要。

## 建議批次

### Batch 1：綜合新聞優先，且符合紙本/網路原生

- CHINATIMES
- ETTODAY
- NOWNEWS
- STORM
- NEWTALK

### Batch 2：原生網媒與紙本雜誌系

- UPMEDIA
- MIRROR
- TAISOUNDS
- CMEDIA
- TNL

### Batch 3：兩岸/政治深度與補充來源

- REPORTER
- READR
- RFA
- VOACHINESE
- PEOPLENEWS

## 下一步

老闆版清單已成為新的主要 task backlog：`docs/boss-media-task-list.md`。

`CHINATIMES`、`TVBS`、`EBC`、`FTV`、`PTS`、`CTS`、`TTV`、`NEXTTV`、`MNEWS`、`GLOBALNEWS`、`CTWANT`、`RWNEWS`、`CNEWS`、`TNL`、`REPORTER`、`PEOPLENEWS`、`ERA`、`NEW7`、`CW`、`BUSINESSWEEKLY`、`COMMERCIALTIMES`、`ECONOMIC`、`ETTODAY`、`NOWNEWS`、`STORM`、`NEWTALK`、`UPMEDIA`、`MIRROR` 已完成本地驗證；`TAISOUNDS` 已完成但作為額外保留來源。下一步若要上線：

- 部署 runner 新增來源。
- 設定或更新 Cloud Scheduler。
- 上線後觀察 Batch 4 來源的商業/財經內容比例，必要時再把關鍵字收斂到政治、社會、兩岸。
