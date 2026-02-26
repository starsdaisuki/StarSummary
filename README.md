# StarSummary (星语)

Video/Audio → Transcript → Summary

将视频/音频转录为文字，并可选地进行 AI 总结。支持 CLI、Web UI、Telegram Bot 三种使用方式。

## 功能

- 支持 YouTube、Bilibili、抖音等平台视频链接
- 支持本地音频/视频文件
- 双 ASR 引擎：阿里云 Paraformer（默认，云端）/ faster-whisper（本地）
- 可选 DeepSeek LLM 总结
- 输出带时间戳的转录文本
- 三种使用方式：CLI 命令行 / Gradio Web UI / Telegram Bot

## 安装

### 前置依赖

macOS:

```bash
brew install yt-dlp ffmpeg
```

Ubuntu/Debian:

```bash
sudo apt install ffmpeg
pip install yt-dlp
```

### 安装项目

基本安装：

```bash
uv sync
```

安装全部可选功能（whisper + 总结）：

```bash
uv sync --extra all
```

### 配置 API Key

在项目根目录创建 `.env` 文件：

```
DASHSCOPE_API_KEY=your-key        # Paraformer（默认引擎）
DEEPSEEK_API_KEY=your-key         # DeepSeek（总结功能）
TELEGRAM_BOT_TOKEN=your-token     # Telegram Bot
```

## 使用方式

### 1. CLI 命令行

无参数进入交互模式：

```bash
starsummary
```

转录视频链接：

```bash
starsummary "https://www.bilibili.com/video/BV1xx..."
```

使用本地 whisper 引擎（无需 API Key）：

```bash
starsummary video.mp4 --engine whisper
```

指定 whisper 模型大小：

```bash
starsummary audio.mp3 -e whisper -m large-v3
```

启用 AI 总结：

```bash
starsummary "https://www.youtube.com/watch?v=xxx" --summarize
```

使用 cookies 下载（抖音等需要登录的平台）：

```bash
starsummary "https://v.douyin.com/xxx" -cb chrome
```

转录后复制到剪贴板：

```bash
starsummary audio.mp3 --copy
```

### 2. Web UI

```bash
starsummary-web
```

自动打开浏览器，提供图形化操作界面。

### 3. Telegram Bot

需要先在 `.env` 中配置 `TELEGRAM_BOT_TOKEN`：

```bash
starsummary-bot
```

直接给 Bot 发视频链接或音频文件即可获得转录文本。

## CLI 参数

| 参数 | 说明 |
|------|------|
| `input` | 视频/音频 URL 或本地文件路径 |
| `-e, --engine` | ASR 引擎：`paraformer`（默认）或 `whisper` |
| `-m, --model` | Whisper 模型大小（仅 whisper 引擎），默认 `small` |
| `-l, --lang` | 语言代码（zh/en/ja），默认自动检测 |
| `-s, --summarize` | 启用 LLM 总结 |
| `--api-key` | DeepSeek API Key（或用环境变量） |
| `-c, --cookies` | cookies 文件路径 |
| `-cb, --cookies-from-browser` | 从浏览器读取 cookies |
| `-o, --output` | 输出目录，默认 `./star_summary_output/` |
| `--keep-audio` | 保留下载的音频文件 |
| `-C, --copy` | 转录后复制纯文本到剪贴板（macOS pbcopy） |

## 输出文件

输出按日期分组，文件名包含标题和时间戳，避免覆盖：

```
star_summary_output/
└── 2026-02-26/
    ├── 崩坏星穹铁道_火花_143052_transcript.txt
    ├── 崩坏星穹铁道_火花_143052_timed.txt
    └── 崩坏星穹铁道_火花_143052_summary.txt
```

| 文件 | 说明 |
|------|------|
| `*_transcript.txt` | 纯文本转录（带元信息头部） |
| `*_timed.txt` | 带时间戳的转录 `[MM:SS.ss → MM:SS.ss]` |
| `*_summary.txt` | AI 总结（仅 `--summarize` 时生成） |

## VPS 部署（Telegram Bot）

### 一行命令部署

SSH 到 VPS 后直接运行：

```bash
bash <(curl -sL https://raw.githubusercontent.com/starsdaisuki/StarSummary/main/deploy/setup.sh)
```

脚本会自动 clone 仓库 → 安装 uv/ffmpeg/yt-dlp → 用 `uv python install 3.12` 安装 Python → 交互式配置 API Key → 创建 systemd 服务 → 配置 crontab 定时任务。兼容 Debian 12 和 Ubuntu 22/24。

### 手动 clone 后部署

```bash
git clone https://github.com/starsdaisuki/StarSummary.git ~/StarSummary
cd ~/StarSummary
bash deploy/setup.sh
```

### 后续更新

```bash
bash deploy/update.sh
```

### 管理服务

查看状态：

```bash
sudo systemctl status starsummary-bot
```

重启：

```bash
sudo systemctl restart starsummary-bot
```

停止：

```bash
sudo systemctl stop starsummary-bot
```

查看日志：

```bash
journalctl -u starsummary-bot -f
```

## Whisper 模型选择

仅在使用 `--engine whisper` 时有效：

| 模型 | 大小 | 速度 | 准确率 | 推荐场景 |
|------|------|------|--------|----------|
| `tiny` | ~75MB | ★★★★★ | ★★ | 快速预览 |
| `base` | ~150MB | ★★★★ | ★★★ | 日常够用 |
| `small` | ~500MB | ★★★★ | ★★★★ | **默认推荐** |
| `medium` | ~1.5GB | ★★★ | ★★★★ | 更高准确率 |
| `large-v3` | ~3GB | ★★ | ★★★★★ | 最高准确率 |

## 项目结构

```
StarSummary/
├── src/star_summary/
│   ├── __init__.py              # 版本号
│   ├── cli.py                   # CLI 入口（含交互模式）
│   ├── web.py                   # Gradio Web UI
│   ├── bot.py                   # Telegram Bot
│   ├── config.py                # 配置管理
│   ├── utils.py                 # 工具函数
│   ├── models.py                # 数据模型
│   ├── downloader/              # 下载模块
│   │   ├── base.py
│   │   ├── ytdlp.py
│   │   └── local.py
│   ├── transcriber/             # 转录模块
│   │   ├── base.py
│   │   ├── paraformer.py
│   │   └── whisper_local.py
│   └── summarizer/              # 总结模块
│       ├── base.py
│       └── deepseek.py
├── deploy/                      # VPS 部署
│   ├── setup.sh                 # 一键部署
│   ├── update.sh                # 快速更新
│   └── starsummary-bot.service  # systemd 服务
└── pyproject.toml
```
