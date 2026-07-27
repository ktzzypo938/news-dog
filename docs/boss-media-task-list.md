# 老闆版台灣媒體爬蟲任務清單

更新日期：2026-05-22

## 任務原則

這份清單是新的主要執行範圍，後續新增 crawler 以本文件為準。原本已完成但不在清單內的 `TAISOUNDS` 太報保留在 runner，不移除、不回退。

每個來源仍維持同一份資料 contract：

| 欄位 | 必填 | 說明 |
|---|---|---|
| `source` | yes | 來源代碼 |
| `url` | yes | canonical URL，去除追蹤參數 |
| `title` | yes | 文章標題 |
| `publishedAt` | yes | `YYYY-MM-DD HH:mm:ss` |
| `cleanText` | yes | 清理後純文字內文 |
| `rawHtml` | yes | 目前固定空字串 |
| `imageUrl` | no | 主圖 URL |
| `imagePhotographer` | no | 攝影或圖片來源署名 |

標準分類先維持：

| 分類 | 中文 | 說明 |
|---|---|---|
| `politics` | 政治 | 政治、要聞中明確政治類 |
| `society` | 社會 | 社會、地方事件、司法、警政 |
| `cross_strait` | 兩岸 | 兩岸、陸港澳、台海關係 |

## 狀態定義

| 狀態 | 說明 |
|---|---|
| DONE | 舊有來源已納入 runner |
| READY | 新增來源已完成本地驗證，待部署 |
| TODO | 尚未開始 |
| TODO-LATER | 列入任務，但主題較偏商業/財經，排在綜合新聞後 |
| VERIFY | 開做前需先確認官方網站或是否與既有來源重疊 |
| EXTRA | 已完成但不在老闆清單，先保留 |

## 老闆清單總覽

| 順序 | 狀態 | source | 媒體 | 類型 | 網域 | 備註 |
|---:|---|---|---|---|---|---|
| 1 | DONE | LTN | 自由時報 | 報紙 | `ltn.com.tw` | 已在 runner |
| 2 | DONE | UDN | 聯合報 | 報紙 | `udn.com` | 已在 runner |
| 3 | READY | CHINATIMES | 中國時報 | 報紙 | `chinatimes.com` | 已完成本地驗證，待部署 |
| 4 | DONE | CNA | 中央社 | 報紙/通訊社 | `cna.com.tw` | 已在 runner |
| 5 | READY | CW | 天下雜誌 | 報紙/雜誌 | `cw.com.tw` | 已完成政治、社會、兩岸分類頁，本地驗證通過，待部署；社會候選量較低 |
| 6 | READY | BUSINESSWEEKLY | 商業周刊 | 報紙/雜誌 | `businessweekly.com.tw` | 已完成焦點/時事與趨勢中國入口，本地驗證通過，待部署；政治/社會候選量較低 |
| 7 | READY | TVBS | TVBS | 電視文字新聞 | `news.tvbs.com.tw` | 已完成政治、社會、兩岸，本地驗證通過，待部署 |
| 8 | DONE | SET | 三立新聞 | 電視文字新聞 | `setn.com` | 已在 runner |
| 9 | READY | EBC | 東森新聞 | 電視文字新聞 | `news.ebc.net.tw` | 已完成政治、社會、兩岸，本地驗證通過，待部署 |
| 10 | READY | FTV | 民視新聞 | 電視文字新聞 | `ftvnews.com.tw` | 已完成政治、社會、兩岸，本地驗證通過，待部署 |
| 11 | READY | PTS | 公視新聞 | 電視文字新聞 | `news.pts.org.tw` | 已完成政治、社會、兩岸，本地驗證通過，待部署 |
| 12 | READY | CTS | 華視新聞 | 電視文字新聞 | `news.cts.com.tw` | 已完成政治、社會、兩岸關鍵字篩選，本地驗證通過，待部署 |
| 13 | READY | ERA | 年代新聞 | 電視文字新聞 | `eracom.com.tw/EraNews` | 已確認 `nextmedia.com.tw` 不可用；官方文字新聞站為年代電視 `eracom.com.tw/EraNews`，本地驗證通過 |
| 14 | READY | MNEWS | 鏡新聞 | 電視文字新聞 | `mnews.tw` | 已完成政治、社會、兩岸關鍵字篩選，本地驗證通過，待部署；與 MIRROR 不同來源 |
| 15 | READY | TTV | 台視新聞 | 電視文字新聞 | `news.ttv.com.tw` | 已完成政治、社會、兩岸關鍵字篩選，本地驗證通過，待部署 |
| 16 | READY | NEXTTV | 壹電視 | 電視文字新聞 | `nexttv.com.tw` | 已完成政治、社會、兩岸，本地驗證通過，待部署 |
| 17 | READY | GLOBALNEWS | 寰宇新聞 | 電視文字新聞 | `globalnewstv.com.tw` | 已完成今日重要新聞關鍵字分類，本地驗證通過，待部署 |
| 18 | READY | REPORTER | 報導者 | 網路原生媒體 | `twreporter.org` | 已完成政治、社會、兩岸關鍵字篩選，本地驗證通過，待部署；深度媒體更新節奏較慢 |
| 19 | READY | TNL | 關鍵評論網 | 網路原生媒體 | `thenewslens.com` | 已完成政治、社會、中國/兩岸分類，本地驗證通過，待部署；使用 NewsArticle JSON-LD |
| 20 | READY | STORM | 風傳媒 | 網路原生媒體 | `storm.mg` | 已完成本地驗證，待部署 |
| 21 | READY | UPMEDIA | 上報 | 網路原生媒體 | `upmedia.mg` | 已完成本地驗證，待部署 |
| 22 | READY | MIRROR | 鏡週刊 | 網路原生媒體 | `mirrormedia.mg` | 已完成本地驗證，待部署 |
| 23 | READY | NEWTALK | Newtalk 新頭殼 | 網路原生媒體 | `newtalk.tw` | 已完成本地驗證，待部署 |
| 24 | READY | RWNEWS | 菱傳媒 | 網路原生媒體 | `rwnews.tw` | 已完成 JSON 資料源與關鍵字分類，本地驗證通過，待部署；資料源最新時間需上線前再確認 |
| 25 | READY | ETTODAY | ETtoday 新聞雲 | 網路原生媒體 | `ettoday.net` | 已完成本地驗證，待部署 |
| 26 | READY | NOWNEWS | NOWnews 今日新聞 | 網路原生媒體 | `nownews.com` | 已完成本地驗證，待部署 |
| 27 | READY | PEOPLENEWS | 民報 | 網路原生媒體 | `peoplenews.tw` | 已確認目前官方站為 `www.peoplenews.tw`，使用 WordPress REST API；政治、社會完成，兩岸候選量較低 |
| 28 | READY | CNEWS | 匯流新聞網 | 網路原生媒體 | `cnews.com.tw` | 已完成政治、社會、兩岸關鍵字篩選，本地驗證通過，待部署；兩岸近期候選量略低 |
| 29 | READY | NEW7 | 新新聞 | 網路原生媒體 | `new7.storm.mg` | 已確認有獨立 `new7.storm.mg/article` URL 與 JSON-LD；低量深度來源，政治 30、社會 24、兩岸 14 |
| 30 | DONE | CTI | 中天新聞 | 電視 | `ctinews.com` | 已在 runner |
| 31 | READY | COMMERCIALTIMES | 工商時報 | 報紙 | `ctee.com.tw` | 已完成要聞、兩岸與民生政策關鍵字入口，本地驗證通過，待部署；避開會回 403 的即時分類 |
| 32 | READY | ECONOMIC | 經濟日報 | 報紙 | `money.udn.com` | 已完成要聞、兩岸與民生/生活議題入口，本地驗證通過，待部署；與 UDN 為不同 source code |
| 33 | READY | CTWANT | CTWANT | 網路原生媒體 | `ctwant.com` | 已完成政治、社會、兩岸關鍵字篩選，本地驗證通過，待部署 |

## 額外保留來源

| 狀態 | source | 媒體 | 網域 | 備註 |
|---|---|---|---|---|
| EXTRA | TAISOUNDS | 太報 | `taisounds.com` | 已完成本地驗證；不在老闆清單，但依使用者要求保留 |

## 執行批次

### Batch 0：已完成或已納入 runner

- CNA
- CTI
- LTN
- SET
- UDN
- TVBS
- EBC
- FTV
- PTS
- CTS
- TTV
- NEXTTV
- MNEWS
- GLOBALNEWS
- CTWANT
- RWNEWS
- CNEWS
- TNL
- REPORTER
- PEOPLENEWS
- ERA
- NEW7
- CW
- BUSINESSWEEKLY
- COMMERCIALTIMES
- ECONOMIC
- CHINATIMES
- ETTODAY
- NOWNEWS
- STORM
- NEWTALK
- UPMEDIA
- MIRROR
- TAISOUNDS（額外保留）

### Batch 1：電視文字新聞優先補齊

### Batch 2：網路原生與深度來源

### Batch 3：需確認或可能重疊

### Batch 4：商業/財經/雜誌系

- CW（READY）
- BUSINESSWEEKLY（READY）
- COMMERCIALTIMES（READY）
- ECONOMIC（READY）

## 下一步

老闆版 33 家清單已全數納入 runner 並完成本地 smoke test。下一步若要上線：

- 部署 runner 新增來源。
- 設定或更新 Cloud Scheduler。
- 上線後觀察 `COMMERCIALTIMES`、`ECONOMIC` 的商業/財經內容比例，必要時再把關鍵字收斂到政治、社會、兩岸。
