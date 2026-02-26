# StarSummary（星语）项目规范文档

> 本文档用于指导 Claude Code 构建完整项目。请严格按照以下规范实现。

## 一、项目概述

StarSummary（星语）是一个 CLI 工具，用于将视频/音频转录为文字并可选地进行 AI 总结。

**核心流程**：`输入(URL/本地文件) → 下载音频 → 语音转文字(ASR) → [可选] LLM 总结 → 输出文件`

**运行环境**：macOS (Apple Silicon M4 Pro)，使用 `uv` 管理 Python 项目。

## 二、技术栈

- **语言**：Python 3.12+，使用 type hints
- **包管理**：uv（非 pip），pyproject.toml 管理依赖
- **系统依赖**：yt-dlp、ffmpeg（通过 brew 安装）
- **ASR 方案**：
  - 云端（默认）：阿里云百炼 Paraformer，通过 `dashscope` SDK
  - 本地（备选）：`faster-whisper`，CTranslate2 后端
- **LLM 总结**（可选）：DeepSeek API，通过 `openai` SDK（兼容接口）
- **下载**：yt-dlp，通过 subprocess 调用

## 三、项目结构

```
StarSummary/
├── pyproject.toml
├── README.md
├── src/
│   └── star_summary/
│       ├── __init__.py              # 版本号等
│       ├── cli.py                   # CLI 入口，argparse，流程编排
│       ├── config.py                # 配置管理（环境变量、默认值）
│       ├── utils.py                 # 工具函数（日志美化、时间格式化）
│       ├── models.py                # 数据模型（dataclass）
│       │
│       ├── downloader/              # 下载模块
│       │   ├── __init__.py          # 导出 get_downloader()
│       │   ├── base.py              # AbstractDownloader 基类
│       │   ├── ytdlp.py            # yt-dlp 实现（YouTube/B站等）
│       │   └── local.py             # 本地文件处理（直接返回路径）
│       │
│       ├── transcriber/             # 语音转文字模块
│       │   ├── __init__.py          # 导出 get_transcriber()
│       │   ├── base.py              # AbstractTranscriber 基类
│       │   ├── paraformer.py        # 阿里云 Paraformer（默认）
│       │   └── whisper_local.py     # 本地 faster-whisper（备选）
│       │
│       └── summarizer/              # LLM 总结模块
│           ├── __init__.py          # 导出 get_summarizer()
│           ├── base.py              # AbstractSummarizer 基类
│           └── deepseek.py          # DeepSeek API 实现
```

## 四、数据模型（models.py）

使用 dataclass 定义统一的数据结构：

```python
from dataclasses import dataclass, field

@dataclass
class Segment:
    """单个语音片段"""
    start: float          # 开始时间（秒）
    end: float            # 结束时间（秒）
    text: str             # 文本内容

@dataclass
class TranscriptResult:
    """转录结果 —— 所有 transcriber 统一返回此类型"""
    text: str                          # 完整文本
    segments: list[Segment]            # 带时间戳的片段列表
    language: str = "unknown"          # 检测到的语言
    language_confidence: float = 0.0   # 语言检测置信度
    duration: float = 0.0             # 音频总时长（秒）
    transcribe_time: float = 0.0      # 转录耗时（秒）
    engine: str = ""                   # 使用的引擎名称

@dataclass
class DownloadResult:
    """下载结果"""
    audio_path: str       # 音频文件路径
    title: str = ""       # 视频标题（如果能获取到）
    duration: float = 0.0 # 时长（秒）

@dataclass 
class SummaryResult:
    """总结结果"""
    text: str                  # 总结文本
    model: str = ""            # 使用的模型
    summarize_time: float = 0.0  # 耗时
```

## 五、各模块实现细节

### 5.1 配置管理（config.py）

从环境变量读取配置，支持以下环境变量：

```
DASHSCOPE_API_KEY     - 阿里云百炼 API Key（Paraformer 用）
DEEPSEEK_API_KEY      - DeepSeek API Key（总结用）
STAR_SUMMARY_COOKIES  - cookies 文件路径
```

提供一个 Config dataclass，CLI 解析完参数后构造 Config 传给各模块。

### 5.2 日志工具（utils.py）

提供带 ANSI 颜色的美化日志函数：

```python
def log_step(emoji: str, msg: str): ...   # 步骤标题，cyan + bold
def log_info(msg: str): ...                # 详细信息，dim
def log_success(msg: str): ...             # 成功，green ✓
def log_warn(msg: str): ...                # 警告，yellow ⚠
def log_error(msg: str): ...               # 错误，red ✗
```

以及时间格式化函数：

```python
def format_time(seconds: float) -> str:
    """格式化为 MM:SS.ss 或 HH:MM:SS.ss"""
```

### 5.3 下载模块（downloader/）

**base.py** - 抽象基类：

```python
from abc import ABC, abstractmethod

class AbstractDownloader(ABC):
    @abstractmethod
    def download(self, source: str) -> DownloadResult:
        """下载音频，返回 DownloadResult"""
        ...
```

**ytdlp.py** - yt-dlp 实现：

- 通过 `subprocess.run()` 调用 yt-dlp
- 支持 `--cookies` 和 `--cookies-from-browser` 参数
- 只提取音频（`-x --audio-format mp3`）
- 下载到临时目录（tempfile.mkdtemp）
- 超时 5 分钟
- 尝试获取视频标题（通过 yt-dlp 的 `--print title`）

**local.py** - 本地文件处理：

- 验证文件存在且是支持的格式
- 支持的格式：mp3, wav, flac, aac, ogg, m4a, wma, mp4, mkv, avi, mov, webm, flv, ts
- 直接返回文件路径，不做复制

**`__init__.py`** - 工厂函数：

```python
def get_downloader(source: str, **kwargs) -> AbstractDownloader:
    """根据输入自动判断：URL 用 YtdlpDownloader，本地文件用 LocalDownloader"""
```

### 5.4 转录模块（transcriber/）—— 最核心

**base.py** - 抽象基类：

```python
class AbstractTranscriber(ABC):
    @abstractmethod
    def transcribe(self, audio_path: str, language: str | None = None) -> TranscriptResult:
        ...
```

**paraformer.py** - 阿里云百炼 Paraformer（默认方案）：

- 使用 `dashscope` SDK（pip 包名：`dashscope`）
- 使用录音文件识别 API（适合我们的场景，非实时流式）
- 模型名：`paraformer-v2`（16k 采样率通用）或 `paraformer-8k-v2`
- 支持直接传入本地音频文件路径
- API Key 从环境变量 `DASHSCOPE_API_KEY` 读取

核心调用方式：

```python
from dashscope.audio.asr import Recognition
from http import HTTPStatus

recognition = Recognition(
    model='paraformer-realtime-v2',
    format='mp3',
    sample_rate=16000,
    language_hints=['zh', 'en'],  # 支持中英混合
)
result = recognition.call(audio_path)

if result.status_code == HTTPStatus.OK:
    sentences = result.get_sentence()
    # sentences 是 list，每个元素有 text、begin_time、end_time
```

注意事项：
- 需要先用 ffmpeg 确认/转换音频格式和采样率
- 如果音频文件较大（>几十MB），考虑先压缩
- 做好错误处理：API Key 未设置、网络错误、余额不足等
- 将 dashscope 的返回格式转换为统一的 TranscriptResult

**whisper_local.py** - 本地 faster-whisper（备选方案）：

- 使用 `faster-whisper` 库
- 设备：cpu，compute_type：int8（Apple Silicon 兼容性最好）
- **CPU 线程数限制为总核心数的一半**（避免过热！之前用全部核心导致 90°C+）
- 支持 model_size 参数：tiny/base/small/medium/large-v2/large-v3，默认 small（不再默认 medium，避免过热）
- 开启 VAD 过滤（vad_filter=True）跳过静音

**`__init__.py`** - 工厂函数：

```python
def get_transcriber(engine: str = "paraformer", **kwargs) -> AbstractTranscriber:
    """
    engine="paraformer" → ParaformerTranscriber（默认）
    engine="whisper"    → WhisperLocalTranscriber
    """
```

### 5.5 总结模块（summarizer/）

**deepseek.py** - DeepSeek API：

- 使用 `openai` SDK，base_url 设为 `https://api.deepseek.com`
- 模型：`deepseek-chat`
- 文本过长时截断（max_chars=60000）
- system prompt 设定为专业内容总结助手
- user prompt 要求：先概括核心主题，再分点列出要点
- temperature=0.3（偏确定性）

### 5.6 CLI 入口（cli.py）

**参数设计**：

```
positional:
  input                 视频/音频 URL 或本地文件路径

options:
  -e, --engine          ASR 引擎：paraformer（默认）或 whisper
  -m, --model           Whisper 模型大小（仅 whisper 引擎有效），默认 small
  -l, --lang            语言代码（zh/en/ja），默认自动检测
  -s, --summarize       启用 LLM 总结
  --api-key             DeepSeek API Key（或用环境变量）
  -c, --cookies         cookies 文件路径
  -cb, --cookies-from-browser  从浏览器读取 cookies（chrome/edge/safari/firefox）
  -o, --output          输出目录，默认 ./star_summary_output/
  --keep-audio          保留下载的音频文件
  -h, --help            帮助信息
```

**主流程伪代码**：

```python
def main():
    # 1. 打印 banner
    print("✦ StarSummary (星语) ✦")
    
    # 2. 解析参数，构造 Config
    args = parse_args()
    
    # 3. 获取 downloader 并下载
    downloader = get_downloader(args.input, cookies=..., cookies_from_browser=...)
    download_result = downloader.download(args.input)
    
    # 4. 获取 transcriber 并转录
    transcriber = get_transcriber(engine=args.engine, model=args.model)
    transcript = transcriber.transcribe(download_result.audio_path, language=args.lang)
    
    # 5. 可选：总结
    summary = None
    if args.summarize:
        summarizer = get_summarizer(api_key=...)
        summary = summarizer.summarize(transcript.text)
    
    # 6. 保存结果
    save_results(transcript, summary, output_dir=args.output)
    
    # 7. 打印预览
    print_preview(transcript, summary)
    
    # 8. 清理临时文件
    cleanup()
```

## 六、输出文件格式

保存到 `--output` 指定的目录（默认 `./star_summary_output/`）：

1. **transcript.txt** - 纯文本转录（带元信息头部注释）
2. **transcript_timed.txt** - 带时间戳的转录，格式：`[MM:SS.ss → MM:SS.ss]  文本内容`
3. **summary.txt** - AI 总结（仅 `--summarize` 时生成）

## 七、pyproject.toml 配置

```toml
[project]
name = "star-summary"
version = "0.2.0"
description = "StarSummary (星语) - Video/Audio → Transcript → Summary"
requires-python = ">=3.12"
dependencies = [
    "dashscope>=1.20.0",
]

[project.optional-dependencies]
whisper = ["faster-whisper>=1.0.0"]
summarize = ["openai>=1.0.0"]
all = ["faster-whisper>=1.0.0", "openai>=1.0.0"]

[project.scripts]
starsummary = "star_summary.cli:main"
```

注意：
- `dashscope` 是必需依赖（默认 ASR 引擎）
- `faster-whisper` 和 `openai` 是可选依赖
- 配置了 `[project.scripts]` 入口点，安装后可直接使用 `starsummary` 命令
- 用户安装时：`uv add star-summary` 或 `uv pip install ".[all]"`

## 八、错误处理要求

1. **依赖缺失时给清晰提示**：
   - 使用 whisper 引擎但没装 faster-whisper → 提示 `uv add faster-whisper`
   - 使用 summarize 但没装 openai → 提示 `uv add openai`
   - yt-dlp 或 ffmpeg 未安装 → 提示 `brew install yt-dlp ffmpeg`

2. **API Key 缺失时友好提示**：
   - Paraformer 无 DASHSCOPE_API_KEY → 提示设置环境变量，或建议切换到 `--engine whisper`
   - DeepSeek 无 API Key → 跳过总结并提示

3. **网络错误时**：提示检查网络，建议切换到 `--engine whisper` 本地模式

4. **下载失败时**：显示 yt-dlp 的错误信息，建议手动下载后用本地文件模式

## 九、开发步骤建议

请按以下顺序实现：

1. 先创建项目结构和 pyproject.toml
2. 实现 models.py 和 utils.py（基础设施）
3. 实现 downloader 模块（最简单）
4. 实现 transcriber/paraformer.py（默认方案）
5. 实现 transcriber/whisper_local.py（备选方案）
6. 实现 summarizer/deepseek.py
7. 实现 cli.py 串联所有模块
8. 实现 config.py
9. 编写 README.md
10. 测试运行

## 十、代码风格

- 使用 type hints
- docstring 用中文或英文均可
- 日志用 utils.py 里的函数，不要用 print 或 logging
- 异常处理要友好，面向终端用户（不要抛 traceback 给用户看）
- 变量命名用 snake_case，类名用 PascalCase
