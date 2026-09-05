# 華視專用取頁服務

GCP 的爬蟲直接存取華視新聞網會收到 CloudFront 403。本 Worker 只轉送華視官網公開使用的新聞 JSON API；後端 API 金鑰、文章入庫、排程與分類仍由 GCP runner 管理。

- 分類列表：`GET /api/news/{politics|society|life|international}/list?page=1&limit=30`，最多 15 頁。
- 單篇文章：`GET /api/news/{15 位數文章 ID}`。
- 請求須帶 `Authorization: Bearer <CTS_FETCH_TOKEN>`，金鑰只存於 Worker secret 與 GCP 環境設定。
- 不轉送呼叫者金鑰到華視，不跟隨重新導向，不接受任意目標網址。
- 上游 429 與 `Retry-After` 會交還 runner；不在 Worker 內重試。

部署：

```bash
npx wrangler@4.129.0 deploy --config edge/cts-fetch/wrangler.jsonc
npx wrangler@4.129.0 secret put CTS_FETCH_TOKEN --config edge/cts-fetch/wrangler.jsonc
```

接著以相同金鑰設定 GCP 的 `scraper-cts`：`CTS_FETCH_BASE_URL=https://news-dog-cts-fetch.q27913588.workers.dev`、`CTS_FETCH_TOKEN`。這兩個環境變數只提供給華視來源。

本地直接存取華視可省略這兩個變數；正式 GCP 環境需使用 Worker。金鑰更新後請驗證帶金鑰的列表與文章請求均為 HTTP 200，未登入為 HTTP 401，再更新 crawler。

測試：`node --test edge/cts-fetch/test.mjs`。
