# 相容舊入口：實際部署請使用統一 runner 架構。

$INGEST_API_BASE = if ($env:INGEST_API_BASE) { $env:INGEST_API_BASE } else { "https://square-news-632027619686.asia-east1.run.app/ingest" }
$API_KEY = if ($env:API_KEY) { $env:API_KEY } else { "temporary-api-key-123" }
$REGION = if ($env:REGION) { $env:REGION } else { "asia-east1" }

$sources = @("TVBS", "PTS", "EBC", "ETTODAY", "CHINATIMES", "TTV", "UDN", "CTS", "LTN", "FTV", "STORM", "SET", "CNA", "CTI")
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "deploy_all.ps1 使用統一 runner 部署。" -ForegroundColor Yellow
Push-Location "$scriptDir/runner"

try {
    foreach ($source in $sources) {
        $sourceLower = $source.ToLower()
        $memory = if ($source -eq "STORM") { "1Gi" } else { "256Mi" }
        Write-Host "------------------------------------" -ForegroundColor Cyan
        Write-Host "正在部署爬蟲: $source" -ForegroundColor Cyan
        Write-Host "------------------------------------"

        gcloud functions deploy "scraper-$sourceLower" `
            --gen2 `
            --runtime python311 `
            --trigger-http `
            --entry-point run_scraper `
            --no-allow-unauthenticated `
            --region $REGION `
            --set-env-vars "INGEST_API_BASE=$INGEST_API_BASE,API_KEY=$API_KEY,SOURCE_CODE=$source,SCRAPER_ONLY_TODAY=true,SCRAPER_TIMEZONE=Asia/Taipei" `
            --memory $memory `
            --timeout 300s `
            --max-instances 1
    }
}
finally {
    Pop-Location
}

Write-Host "`n所有爬蟲部署完成！" -ForegroundColor Green
