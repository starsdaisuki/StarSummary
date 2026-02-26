# StarSummary (星语)

Video/Audio → Transcript → Summary

将视频/音频转录为文字，并可选地进行 AI 总结。

## 功能

- 支持 YouTube、Bilibili、抖音等平台视频链接
- 支持本地音频/视频文件
- 双 ASR 引擎：阿里云 Paraformer（默认，云端）/ faster-whisper（本地）
- 可选 DeepSeek LLM 总结
- 输出带时间戳的转录文本

## 安装

### 前置依赖

```bash
brew install yt-dlp ffmpeg
```

### 安装项目

```bash
# 基本安装（仅 Paraformer 引擎）
uv pip install .

# 安装全部功能
uv pip install ".[all]"

# 仅安装 whisper 引擎
uv pip install ".[whisper]"

# 仅安装总结功能
uv pip install ".[summarize]"
```

### 配置 API Key

```bash
# Paraformer（默认引擎）
export DASHSCOPE_API_KEY="your-key"

# DeepSeek（总结功能）
export DEEPSEEK_API_KEY="your-key"
```

## 使用

```bash
# 基本用法 - 转录视频
starsummary "https://www.bilibili.com/video/BV1xx..."

# 使用本地 whisper 引擎（无需 API Key）
starsummary video.mp4 --engine whisper

# 指定 whisper 模型大小
starsummary audio.mp3 -e whisper -m large-v3

# 指定语言
starsummary video.mp4 --lang zh

# 启用 AI 总结
starsummary "https://www.youtube.com/watch?v=xxx" --summarize

# 使用 cookies 下载（抖音等需要登录的平台）
starsummary "https://v.douyin.com/xxx" -cb chrome

# 指定输出目录并保留音频
starsummary "https://..." -o ~/summaries/ --keep-audio
```

## 参数

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

## 输出文件

| 文件 | 说明 |
|------|------|
| `transcript.txt` | 纯文本转录（带元信息头部） |
| `transcript_timed.txt` | 带时间戳的转录 `[MM:SS.ss → MM:SS.ss]` |
| `summary.txt` | AI 总结（仅 `--summarize` 时生成） |

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
src/star_summary/
├── __init__.py              # 版本号
├── cli.py                   # CLI 入口
├── config.py                # 配置管理
├── utils.py                 # 工具函数
├── models.py                # 数据模型
├── downloader/              # 下载模块
│   ├── base.py              # 抽象基类
│   ├── ytdlp.py             # yt-dlp 实现
│   └── local.py             # 本地文件处理
├── transcriber/             # 转录模块
│   ├── base.py              # 抽象基类
│   ├── paraformer.py        # 阿里云 Paraformer
│   └── whisper_local.py     # 本地 faster-whisper
└── summarizer/              # 总结模块
    ├── base.py              # 抽象基类
    └── deepseek.py          # DeepSeek API
```
