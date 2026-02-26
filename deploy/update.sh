#!/usr/bin/env bash
# StarSummary 快速更新脚本
# 用法: bash deploy/update.sh

set -e

GREEN='\033[92m'
CYAN='\033[96m'
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

ok()   { echo -e "   ${GREEN}✓ $1${RESET}"; }
step() { echo -e "\n${CYAN}${BOLD}$1  $2${RESET}"; }

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_NAME="starsummary-bot"

echo -e "\n${BOLD}  ✦ StarSummary 更新 ✦${RESET}\n"

cd "${PROJECT_DIR}"

# 拉取代码
step "📥" "拉取最新代码..."
git pull
ok "代码更新完成"

# 同步依赖
step "📚" "同步依赖..."
uv sync
ok "依赖同步完成"

# 重启服务
step "🔄" "重启服务..."
sudo systemctl restart "${SERVICE_NAME}"
sleep 2

if sudo systemctl is-active --quiet "${SERVICE_NAME}"; then
    ok "Bot 已重启"
else
    echo -e "   \033[91m✗ 重启失败，查看日志: journalctl -u ${SERVICE_NAME} -n 20\033[0m"
    exit 1
fi

# 显示状态
step "📊" "当前状态"
sudo systemctl status "${SERVICE_NAME}" --no-pager -l

echo ""
