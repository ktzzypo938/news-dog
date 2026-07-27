#!/bin/bash
# 統一爬蟲部署腳本
# 所有爬蟲共用 runner/ 目錄的程式碼，透過 SOURCE_CODE 環境變數區分
set -euo pipefail

INGEST_API_BASE="${INGEST_API_BASE:-https://square-news-632027619686.asia-east1.run.app/ingest}"
API_KEY="${API_KEY:-temporary-api-key-123}"
REGION="${REGION:-asia-east1}"

# 要部署的來源清單（與 sources.yml 一致）
# 新增來源時在此加一行，並在 sources/ 目錄建立對應的 .py 檔
SOURCES=("TVBS" "PTS" "EBC" "ETTODAY" "CHINATIMES" "TTV" "UDN" "CTS" "LTN" "FTV" "STORM" "SET" "CNA" "CTI")

cd "$(dirname "$0")/runner"

for SOURCE in "${SOURCES[@]}"; do
    echo "------------------------------------"
    echo "正在部署爬蟲: $SOURCE"
    echo "------------------------------------"

    SOURCE_LOWER=$(echo "$SOURCE" | tr '[:upper:]' '[:lower:]')
    MEMORY="256Mi"
    if [ "$SOURCE" = "STORM" ]; then
        MEMORY="1Gi"
    fi

    gcloud functions deploy "scraper-${SOURCE_LOWER}" \
        --gen2 \
        --runtime python311 \
        --trigger-http \
        --entry-point run_scraper \
        --no-allow-unauthenticated \
        --region "$REGION" \
        --set-env-vars "INGEST_API_BASE=${INGEST_API_BASE},API_KEY=${API_KEY},SOURCE_CODE=${SOURCE},SCRAPER_ONLY_TODAY=true,SCRAPER_TIMEZONE=Asia/Taipei" \
        --memory "$MEMORY" \
        --timeout 300s \
        --max-instances 1

    echo ""
done

echo "所有爬蟲部署完成！"
