# StarSummary (星语)

**Video/Audio → Transcript → Summary**

一条链接，自动转录为文字。粘贴 YouTube、B站、抖音等视频链接，或发送音频文件，即可获得完整的转录文本和 AI 总结。

支持三种使用方式：**命令行 CLI** / **Gradio Web UI** / **Telegram Bot**

## 功能亮点

- **多平台支持** — YouTube、Bilibili、抖音、西瓜视频、微博、Twitter/X 等所有 yt-dlp 支持的站点
- **本地文件** — 支持 mp3、wav、flac、m4a、ogg、mp4、mkv、avi、mov、webm
- **四 ASR 引擎** — 阿里 qwen3-asr-flash（**默认**，中文准确率最高）/ Groq whisper-large-v3（英文够用，免费额度大）/ faster-whisper（本地，无需联网）/ fun-asr-realtime（旧引擎，兼容保留）
- **AI 总结** — DeepSeek 一键总结，支持简洁摘要、详细总结、提取要点、自定义风格
- **带时间戳** — 输出 `[MM:SS.ss → MM:SS.ss]` 格式的时间轴文本
- **VPS 一键部署** — 一条命令部署 Telegram Bot 到服务器，支持 Debian / Ubuntu
- **交互模式** — 无参数运行自动进入引导式操作

## 本地安装

### 前置依赖

ffmpeg —— macOS:

```bash
brew install ffmpeg
```

Ubuntu/Debian:

```bash
sudo apt install ffmpeg
```

yt-dlp（两系统通用）。`--with curl_cffi` 是**下载 B 站必需**：B 站用 TLS 指纹反爬，需要 `--impersonate` 模拟真浏览器才能绕过 HTTP 412：

```bash
uv tool install yt-dlp --with curl_cffi
```

### 安装项目

```bash
git clone https://github.com/starsdaisuki/starsummary.git
```

```bash
cd StarSummary
```

```bash
uv sync
```

如果需要本地 whisper 引擎（可选）：

```bash
uv sync --extra whisper
```

### 配置 API Key

在项目根目录创建 `.env` 文件：

```bash
cp .env.example .env
```

然后编辑填入你的 Key：

```
DASHSCOPE_API_KEY=your-key        # 阿里云百炼（默认引擎 qwen3-asr-flash：https://bailian.console.aliyun.com）
GROQ_API_KEY=your-key             # Groq（whisper-large-v3，免费额度大：https://console.groq.com，可选）
DEEPSEEK_API_KEY=your-key         # DeepSeek（AI 总结功能，可选）
TELEGRAM_BOT_TOKEN=your-token     # Telegram Bot（仅 Bot 模式必填）
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

默认就是 qwen 引擎（阿里 qwen3-asr-flash），直接转录音频/链接：

```bash
starsummary recording.m4a -l zh
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

直接给 Bot 发视频链接或音频文件即可获得转录文本。转录完成后会显示 AI 总结按钮（需配置 `DEEPSEEK_API_KEY`），支持选择不同的总结风格。

## CLI 参数

| 参数 | 说明 |
|------|------|
| `input` | 视频/音频 URL 或本地文件路径 |
| `-e, --engine` | ASR 引擎：`qwen`（默认）/ `groq` / `whisper` / `paraformer` |
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

支持 Debian 12、Ubuntu 22/24，可用 root 或普通用户运行。

### 一键部署

SSH 到 VPS 后直接运行：

```bash
bash <(curl -sL https://raw.githubusercontent.com/starsdaisuki/starsummary/main/deploy/setup.sh)
```

脚本会自动完成：clone 仓库 → 安装 uv/Python 3.12/ffmpeg/yt-dlp → 安装依赖 → 交互式配置 API Key → 创建 systemd 服务 → 配置定时任务 → 启动 Bot。

### 手动 clone 后部署

```bash
git clone https://github.com/starsdaisuki/starsummary.git ~/StarSummary
```

```bash
cd ~/StarSummary
```

```bash
bash deploy/setup.sh
```

### 修改配置

```bash
nano ~/StarSummary/.env
```

| 配置项 | 说明 | 必填 |
|--------|------|------|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token（从 @BotFather 获取） | 是 |
| `DASHSCOPE_API_KEY` | 阿里云百炼 API Key（默认引擎 qwen3-asr-flash） | 推荐 |
| `GROQ_API_KEY` | Groq API Key（whisper-large-v3 引擎，免费额度大） | 可选 |
| `ALLOWED_TELEGRAM_USERS` | 允许使用的用户 ID，逗号分隔（留空则所有人可用） | 否 |
| `DEEPSEEK_API_KEY` | DeepSeek API Key（AI 总结功能） | 否 |

修改后重启服务生效：

```bash
sudo systemctl restart starsummary-bot
```

### 后续更新

```bash
cd ~/StarSummary && bash deploy/update.sh
```

会自动 `git pull` → `uv sync` → 重启服务。

### 管理服务

```bash
# 查看状态
sudo systemctl status starsummary-bot
```

```bash
# 重启
sudo systemctl restart starsummary-bot
```

```bash
# 停止
sudo systemctl stop starsummary-bot
```

```bash
# 查看实时日志
journalctl -u starsummary-bot -f
```

```bash
# 查看最近 50 行日志
journalctl -u starsummary-bot -n 50 --no-pager
```

### 完全卸载

如需从 VPS 上彻底移除 StarSummary：

```bash
# 停止并删除 systemd 服务
sudo systemctl stop starsummary-bot
sudo systemctl disable starsummary-bot
sudo rm /etc/systemd/system/starsummary-bot.service
sudo systemctl daemon-reload
```

```bash
# 删除 crontab 定时任务
crontab -l | grep -v 'starsummary-managed' | crontab -
```

```bash
# 删除项目目录
rm -rf ~/StarSummary
```

```bash
# 可选：删除 uv 和 yt-dlp 的软链接
sudo rm -f /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/yt-dlp
```

## 转录引擎选择

| 引擎 | 位置 | 质量 | 说明 |
|------|------|------|------|
| `qwen` | 云端 | ★★★★★ | **默认**。阿里 `qwen3-asr-flash`，中文/歌曲/专业术语准确率显著高于 whisper，且不会在静音段编字幕水印。需 `DASHSCOPE_API_KEY`。API 单次上限 5 分钟，超长音频自动在静音点切片并发转录 |
| `groq` | 云端 | ★★★ | whisper-large-v3，免费额度大、注册不要信用卡；英文够用，**中文同音词错误多且有幻觉**。>25MB 自动分片 |
| `whisper` | 本地 | ★★★ | faster-whisper，无需联网；需 `uv sync --extra whisper`，吃 CPU 且发热 |
| `paraformer` | 云端 | ★★ | 阿里旧实时引擎 `fun-asr-realtime`，兼容保留，新用途请选 `qwen` |

> Groq 免费额度：7200 音频秒/小时、单文件 25MB（本工具自动分片绕过 25MB 限制）。需要更高额度可在 Groq 控制台免费升级 Dev tier（加张卡，额度 ×10）。

### 为什么中文默认换成 qwen

同一段带伴奏的中文歌，两个引擎的同素材对比：

| 正确内容 | `qwen3-asr-flash` | `whisper-large-v3` |
|---|---|---|
| 你站在**讲台**上，把难题说得**亮堂** | ✅ | 你站在**墙台**上，把难题说的**两趟** |
| 像冬天防雨的**装甲** | ✅ | 冬天风雨的**庄稼** |
| **粉笔灰**落在肩上 | ✅ | **粉笔回**落在肩上 |
| **慢条斯理**的推理 | ✅ | **满条死里**的推理 |
| （前奏无人声，应为空） | 不输出 | 凭空补出「**作词 ×××**」 |
| （片尾静音，应为空） | 不输出 | 凭空补出「**优优独播剧场**」 |

最后两行是 Whisper 的经典幻觉：它的训练集里有海量视频字幕，遇到没有人声的段落不会输出「空」，
而是吐出训练集里最高频的字幕文本（音乐视频的作者署名卡、盗版剧集的片尾水印）。

速度上 qwen 也不吃亏：4.5 分钟音频 3.7s vs Groq 5.1s。

### 专有名词提示（`--context`）

`qwen` 引擎支持传入专有名词偏置识别结果：

```bash
starsummary lecture.mp3 --context "卷积 感受野 池化 反向传播"
```

> ⚠️ **这是双刃剑，默认关闭。** 实测中给出不完整的提示词，会把模型**本来识别正确的词带偏**
> （同一段音频裸跑得到「装甲」，加了一组不含「装甲」的提示词后反而退化成「庄稼」）。
> 只在你确切知道音频里会出现哪些人名/术语、并且能写全时才用。
>
> 顺带一提，Whisper 的 `prompt` 参数在中文上更糟：实测它会把提示词**原样吐进转录结果**里，
> 并在结尾进入复读循环。所以 `--context` 对 `groq` 引擎不生效。

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
│   │   ├── qwen.py              # 阿里 qwen3-asr-flash（默认，含静音点切片+并发）
│   │   ├── groq.py              # Groq whisper-large-v3（含 >25MB 分片）
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
