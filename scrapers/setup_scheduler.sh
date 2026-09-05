#!/bin/bash

# Cloud Scheduler 自動設定腳本：各來源每 30 分鐘執行一次，依序錯開 1 分鐘。
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-square-news-483901}"
REGION="${REGION:-asia-east1}"
# 順序對應既有正式排程的分鐘偏移，請勿任意重排。
SCRAPERS=("chinatimes" "cna" "cti" "cts" "ebc" "ettoday" "ftv" "ltn" "pts" "set" "storm" "ttv" "tvbs" "udn")
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-632027619686-compute@developer.gserviceaccount.com}"

echo "------------------------------------"
echo "開始設定 Cloud Scheduler 排程..."
echo "------------------------------------"

for OFFSET in "${!SCRAPERS[@]}"; do
    SCRAPER="${SCRAPERS[$OFFSET]}"
    NAME="scraper-$SCRAPER"
    JOB_NAME="job-$NAME"
    SCHEDULE="${OFFSET},$((OFFSET + 30)) * * * *"
    DESCRIPTION="每 30 分鐘執行一次 $NAME 爬蟲（每小時第 ${OFFSET}、$((OFFSET + 30)) 分鐘）"

    echo "正在設定 $NAME 的排程：$SCHEDULE"
    if gcloud scheduler jobs describe "$JOB_NAME" \
        --project="$PROJECT_ID" --location="$REGION" >/dev/null 2>&1; then
        # 原地更新，保留既有 OIDC、URL、時區、逾時、重試與啟用／暫停狀態。
        gcloud scheduler jobs update http "$JOB_NAME" \
            --project="$PROJECT_ID" --location="$REGION" \
            --schedule="$SCHEDULE" --description="$DESCRIPTION" --quiet
    else
        URL=$(gcloud functions describe "$NAME" --project="$PROJECT_ID" \
            --region="$REGION" --gen2 --format='value(serviceConfig.uri)')
        if [ -z "$URL" ]; then
            echo "錯誤：找不到 $NAME 的 URL，請先完成部署。" >&2
            exit 1
        fi
        gcloud scheduler jobs create http "$JOB_NAME" \
            --project="$PROJECT_ID" --location="$REGION" \
            --schedule="$SCHEDULE" --time-zone="Etc/UTC" \
            --attempt-deadline="330s" \
            --uri="$URL" --http-method=GET \
            --oidc-service-account-email="$SERVICE_ACCOUNT" \
            --oidc-token-audience="$URL" \
            --description="$DESCRIPTION" --quiet
    fi

    echo "✅ $NAME 排程設定完成！"
    echo "------------------------------------"
done

echo -e "\n🎉 所有爬蟲排程設定完成！你可以到 Cloud Console 檢視結果。"
