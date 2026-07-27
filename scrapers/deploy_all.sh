#!/bin/bash

# 相容舊入口：實際部署請使用統一 runner 架構。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "deploy_all.sh 已改為轉呼叫 deploy_runner.sh（統一 runner 部署）。"
exec "$SCRIPT_DIR/deploy_runner.sh"
