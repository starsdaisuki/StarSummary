#!/usr/bin/env bash
# StarSummary VPS 一键部署脚本
# 用法:
#   bash deploy/setup.sh                     # 在项目目录中运行
#   bash <(curl -sL https://raw.githubusercontent.com/starsdaisuki/StarSummary/main/deploy/setup.sh)

set -e

REPO_URL="https://github.com/starsdaisuki/StarSummary.git"
DEFAULT_DIR="$HOME/StarSummary"

# ─────────────────────────────────────────────
# 颜色
# ─────────────────────────────────────────────
CYAN='\033[96m'
GREEN='\033[92m'
YELLOW='\033[93m'
RED='\033[91m'
MAGENTA='\033[95m'
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

ok()   { echo -e "   ${GREEN}✓ $1${RESET}"; }
warn() { echo -e "   ${YELLOW}⚠ $1${RESET}"; }
err()  { echo -e "   ${RED}✗ $1${RESET}"; }
step() { echo -e "\n${CYAN}${BOLD}$1  $2${RESET}"; }

# ─────────────────────────────────────────────
# root 检测：root 用户不需要 sudo
# ─────────────────────────────────────────────
if [ "$(id -u)" -eq 0 ]; then
    SUDO=""
else
    SUDO="sudo"
fi

# ─────────────────────────────────────────────
# 自动 clone：如果不在项目目录中
# ─────────────────────────────────────────────
_find_project_dir() {
    # 1. 如果当前目录有 pyproject.toml，说明已在项目中
    if [[ -f "./pyproject.toml" ]]; then
        echo "$(pwd)"
        return
    fi

    # 2. 如果是通过 bash deploy/setup.sh 运行，检查上级目录
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || true
    if [[ -n "${script_dir}" && -f "${script_dir}/../pyproject.toml" ]]; then
        echo "$(cd "${script_dir}/.." && pwd)"
        return
    fi

    # 3. 不在项目中，需要 clone
    echo ""
}

PROJECT_DIR="$(_find_project_dir)"

if [[ -z "${PROJECT_DIR}" ]]; then
    step "📦" "Clone StarSummary..."

    if ! command -v git &>/dev/null; then
        $SUDO apt-get update -qq && $SUDO apt-get install -y git
    fi

    if [[ -d "${DEFAULT_DIR}" && -f "${DEFAULT_DIR}/pyproject.toml" ]]; then
        ok "已存在 ${DEFAULT_DIR}，执行 git pull"
        cd "${DEFAULT_DIR}" && git pull
    else
        git clone "${REPO_URL}" "${DEFAULT_DIR}"
        ok "Clone 完成: ${DEFAULT_DIR}"
    fi

    PROJECT_DIR="${DEFAULT_DIR}"
    cd "${PROJECT_DIR}"
fi
DEPLOY_USER="$(whoami)"
VENV_DIR="${PROJECT_DIR}/.venv"
ENV_FILE="${PROJECT_DIR}/.env"
SERVICE_NAME="starsummary-bot"

echo -e "\n${MAGENTA}${BOLD}  ✦ StarSummary VPS 部署 ✦${RESET}"
echo -e "${DIM}  一键部署 Telegram Bot${RESET}\n"

# ─────────────────────────────────────────────
# 1. 检测系统
# ─────────────────────────────────────────────
step "📋" "检测系统环境..."

if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    ok "系统: ${PRETTY_NAME}"
else
    err "无法检测系统版本"
    exit 1
fi

if [[ "${ID}" != "ubuntu" && "${ID}" != "debian" && "${ID_LIKE}" != *"debian"* ]]; then
    warn "当前系统非 Ubuntu/Debian，部分命令可能需要手动调整"
fi

# ─────────────────────────────────────────────
# 2. 安装系统依赖（仅 ffmpeg, git, curl）
# ─────────────────────────────────────────────
step "📦" "安装系统依赖..."

$SUDO apt-get update -qq
$SUDO apt-get install -y ffmpeg git curl
ok "ffmpeg, git, curl 已就绪"

# ─────────────────────────────────────────────
# 3. 安装 uv
# ─────────────────────────────────────────────
step "🔧" "安装 uv..."

if command -v uv &>/dev/null; then
    ok "uv 已安装: $(uv --version)"
else
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    ok "uv 安装完成: $(uv --version)"
fi

# ─────────────────────────────────────────────
# 4. 用 uv 安装 Python 3.12
# ─────────────────────────────────────────────
step "🐍" "安装 Python 3.12..."

uv python install 3.12
ok "Python 3.12 已就绪 ($(uv python find 3.12))"

# ─────────────────────────────────────────────
# 5. 安装 yt-dlp
# ─────────────────────────────────────────────
step "📥" "安装 yt-dlp..."

if command -v yt-dlp &>/dev/null; then
    ok "yt-dlp 已安装"
else
    uv tool install yt-dlp
    ok "yt-dlp 安装完成"
fi

# ─────────────────────────────────────────────
# 6. 安装 Python 依赖
# ─────────────────────────────────────────────
step "📚" "安装 Python 依赖..."

cd "${PROJECT_DIR}"
uv sync
ok "依赖安装完成"

# ─────────────────────────────────────────────
# 7. 交互式配置引导
# ─────────────────────────────────────────────
if [[ ! -f "${ENV_FILE}" ]]; then
    step "⚙️" "配置引导"
    echo ""

    # DASHSCOPE_API_KEY
    echo -e "  ${BOLD}1/3${RESET} 🔑 请输入阿里云百炼 API Key (DASHSCOPE_API_KEY):"
    read -r -p "      " DASHSCOPE_KEY
    if [[ -n "${DASHSCOPE_KEY}" ]]; then
        ok "已保存"
    else
        warn "已跳过（Paraformer 引擎将不可用）"
    fi
    echo ""

    # TELEGRAM_BOT_TOKEN
    echo -e "  ${BOLD}2/3${RESET} 🤖 请输入 Telegram Bot Token:"
    read -r -p "      " TG_TOKEN
    if [[ -n "${TG_TOKEN}" ]]; then
        ok "已保存"
    else
        err "Telegram Bot Token 是必填项！"
        exit 1
    fi
    echo ""

    # ALLOWED_USERS
    echo -e "  ${BOLD}3/3${RESET} 👤 请输入允许使用 Bot 的 Telegram 用户 ID（多个用逗号分隔）:"
    read -r -p "      " ALLOWED_USERS
    if [[ -n "${ALLOWED_USERS}" ]]; then
        ok "已保存"
    else
        warn "未设置，所有人均可使用 Bot"
    fi
    echo ""

    # DEEPSEEK_API_KEY (可选)
    echo -e "  ${DIM}（可选）${RESET}💬 请输入 DeepSeek API Key（直接回车跳过）:"
    read -r -p "      " DEEPSEEK_KEY
    if [[ -n "${DEEPSEEK_KEY}" ]]; then
        ok "已保存"
    else
        echo -e "   ${DIM}⏭ 已跳过${RESET}"
    fi
    echo ""

    # 写入 .env
    cat > "${ENV_FILE}" <<ENVEOF
# StarSummary 配置
DASHSCOPE_API_KEY=${DASHSCOPE_KEY}
TELEGRAM_BOT_TOKEN=${TG_TOKEN}
ALLOWED_TELEGRAM_USERS=${ALLOWED_USERS}
DEEPSEEK_API_KEY=${DEEPSEEK_KEY}
ENVEOF

    chmod 600 "${ENV_FILE}"
    ok "配置已写入 ${ENV_FILE}"
else
    step "⚙️" "检测到已有 .env，跳过配置引导"
    ok "使用现有配置: ${ENV_FILE}"
fi

# ─────────────────────────────────────────────
# 8. 安装 systemd 服务
# ─────────────────────────────────────────────
step "🚀" "配置 systemd 服务..."

SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

$SUDO tee "${SERVICE_FILE}" > /dev/null <<SVCEOF
[Unit]
Description=StarSummary Telegram Bot
After=network.target

[Service]
Type=simple
User=${DEPLOY_USER}
WorkingDirectory=${PROJECT_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${VENV_DIR}/bin/starsummary-bot
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SVCEOF

$SUDO systemctl daemon-reload
$SUDO systemctl enable "${SERVICE_NAME}"
ok "systemd 服务已安装并设为开机自启"

# ─────────────────────────────────────────────
# 9. 配置 crontab 定时任务
# ─────────────────────────────────────────────
step "⏰" "配置定时任务..."

CRON_MARKER="# starsummary-managed"

# 移除旧的 starsummary cron 条目
(crontab -l 2>/dev/null || true) | grep -v "${CRON_MARKER}" | crontab -

# 添加新的定时任务
(crontab -l 2>/dev/null || true; cat <<CRONEOF
0 3 * * 1 $(command -v yt-dlp || echo /usr/local/bin/yt-dlp) -U >/dev/null 2>&1 ${CRON_MARKER}
0 4 * * * $SUDO systemctl restart ${SERVICE_NAME} >/dev/null 2>&1 ${CRON_MARKER}
CRONEOF
) | crontab -

ok "每周一 03:00 自动更新 yt-dlp"
ok "每天 04:00 自动重启 Bot"

# ─────────────────────────────────────────────
# 10. 启动服务
# ─────────────────────────────────────────────
step "▶️" "启动服务..."

$SUDO systemctl restart "${SERVICE_NAME}"
sleep 2

if $SUDO systemctl is-active --quiet "${SERVICE_NAME}"; then
    ok "Bot 已启动并运行中"
else
    err "启动失败，查看日志: journalctl -u ${SERVICE_NAME} -n 20"
    exit 1
fi

# ─────────────────────────────────────────────
# 完成
# ─────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}  ✦ 部署完成！✦${RESET}"
echo ""
echo -e "  ${DIM}管理命令：${RESET}"
echo -e "  sudo systemctl status ${SERVICE_NAME}     ${DIM}# 查看状态${RESET}"
echo -e "  sudo systemctl restart ${SERVICE_NAME}    ${DIM}# 重启${RESET}"
echo -e "  sudo systemctl stop ${SERVICE_NAME}       ${DIM}# 停止${RESET}"
echo -e "  journalctl -u ${SERVICE_NAME} -f          ${DIM}# 看日志${RESET}"
echo -e "  bash deploy/update.sh                     ${DIM}# 更新代码${RESET}"
echo ""
