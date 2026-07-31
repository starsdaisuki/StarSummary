# StarSummary（星语）项目文档

> 本文档面向项目维护者，用于快速理解公开架构、接口与部署约束。
>
> 最后更新：2026-02-26

## 一、项目简介

StarSummary（星语）是一个视频/音频转文字工具，支持 B站、YouTube 等平台的视频链接或本地文件，通过 ASR（语音识别）转录为文字，可选 LLM 总结。

**核心流程**：`输入(URL/本地文件) → 下载音频(yt-dlp) → 语音转文字(ASR) → [可选] LLM 总结 → 输出文件`

**三合一入口**：

```
CLI 交互模式 ─┐
Gradio Web  ──┤──→ downloader → transcriber → summarizer
Telegram Bot ─┘
```

**仓库地址**：https://github.com/starsdaisuki/starsummary

## 二、技术栈

- **语言**：Python 3.12+，使用 type hints
- **包管理**：uv（非 pip），pyproject.toml 管理依赖
- **系统依赖**：yt-dlp、ffmpeg
- **ASR 方案**：
  - 云端（默认）：阿里云百炼 Paraformer，通过 `dashscope` SDK，模型 `fun-asr-realtime`
  - 本地（备选）：`faster-whisper`，CTranslate2 后端，通过 `--engine whisper` 切换
- **LLM 总结**（可选）：DeepSeek API，通过 `openai` SDK（兼容接口）
- **下载**：yt-dlp，通过 subprocess 调用
- **Web UI**：Gradio
- **Telegram Bot**：python-telegram-bot

## 三、项目结构

```
StarSummary/
├── pyproject.toml
├── README.md
├── STAR_SUMMARY_SPEC.md          ← 本文件
├── .env                           # API Keys（不入库）
├── deploy/
│   ├── setup.sh                   # VPS 一键部署脚本
│   └── update.sh                  # 快速更新脚本
├── src/
│   └── star_summary/
│       ├── __init__.py
│       ├── cli.py                 # CLI 入口，argparse + 交互模式 + 流程编排
│       ├── web.py                 # Gradio Web UI 入口
│       ├── bot.py                 # Telegram Bot 入口
│       ├── config.py              # 配置管理（环境变量、默认值）
│       ├── utils.py               # 工具函数（日志美化、时间格式化）
│       ├── models.py              # 数据模型（dataclass）
│       │
│       ├── downloader/            # 下载模块
│       │   ├── __init__.py        # 导出 get_downloader() 工厂函数
│       │   ├── base.py            # AbstractDownloader 基类
│       │   ├── ytdlp.py           # yt-dlp 实现（YouTube/B站等）
│       │   └── local.py           # 本地文件处理
│       │
│       ├── transcriber/           # 语音转文字模块（核心）
│       │   ├── __init__.py        # 导出 get_transcriber() 工厂函数
│       │   ├── base.py            # AbstractTranscriber 基类
│       │   ├── paraformer.py      # 阿里云 Paraformer（默认）
│       │   └── whisper_local.py   # 本地 faster-whisper（备选）
│       │
│       └── summarizer/            # LLM 总结模块
│           ├── __init__.py        # 导出 get_summarizer() 工厂函数
│           ├── base.py            # AbstractSummarizer 基类
│           └── deepseek.py        # DeepSeek API 实现
```

## 四、数据模型（models.py）

所有模块通过统一的 dataclass 传递数据：

```python
@dataclass
class Segment:
    start: float          # 开始时间（秒）
    end: float            # 结束时间（秒）
    text: str             # 文本内容

@dataclass
class TranscriptResult:
    text: str                          # 完整文本
    segments: list[Segment]            # 带时间戳的片段列表
    language: str = "unknown"
    language_confidence: float = 0.0
    duration: float = 0.0             # 音频总时长（秒）
    transcribe_time: float = 0.0      # 转录耗时（秒）
    engine: str = ""                   # 使用的引擎名称

@dataclass
class DownloadResult:
    audio_path: str       # 音频文件路径
    title: str = ""       # 视频标题
    duration: float = 0.0

@dataclass
class SummaryResult:
    text: str
    model: str = ""
    summarize_time: float = 0.0
```

## 五、模块化架构与工厂模式

每个模块遵循相同的设计模式：

1. `base.py` 定义抽象基类（AbstractXxx），规定统一接口
2. 具体实现各写一个文件，实现抽象接口
3. `__init__.py` 提供工厂函数（get_xxx），根据参数选择实现
4. CLI/Web/Bot 调用工厂函数获取实例，不关心底层实现

**示例：transcriber 模块**

```python
# transcriber/__init__.py
def get_transcriber(engine: str = "paraformer", **kwargs) -> AbstractTranscriber:
    if engine == "paraformer":
        from .paraformer import ParaformerTranscriber
        return ParaformerTranscriber(**kwargs)
    elif engine == "whisper":
        from .whisper_local import WhisperLocalTranscriber
        return WhisperLocalTranscriber(**kwargs)
    else:
        raise ValueError(f"Unknown engine: {engine}")
```

**所有 transcriber 返回统一的 `TranscriptResult`**，CLI 不需要关心是谁干的活。

## 六、各模块技术细节

### 6.1 阿里云 Paraformer（默认 ASR）

- SDK：`dashscope`
- 模型：`fun-asr-realtime`（最新最强），备选 `paraformer-realtime-v2`
- API Key：环境变量 `DASHSCOPE_API_KEY`，dashscope SDK 自动读取
- **关键约束**：只接受单声道音频，需用 ffmpeg 预处理：`ffmpeg -i input.mp3 -ac 1 -ar 16000 output.mp3`
- 区域：默认北京 endpoint，国际 VPS 可用新加坡（需额外配置）
- 计费：约 ¥0.04/分钟，只对有语音内容的时长计费，新用户 90 天免费额度

```python
from dashscope.audio.asr import Recognition
recognition = Recognition(
    model='fun-asr-realtime',
    format='mp3',
    sample_rate=16000,
    language_hints=['zh', 'en'],
    callback=None,
)
result = recognition.call('audio.mp3')
# result.get_sentence() → list of dict with text, begin_time, end_time
```

### 6.2 本地 faster-whisper（备选 ASR）

- 设备：CPU，`compute_type=int8`
- 默认将线程数限制为可用核心数的一半，降低持续负载并保留系统响应性
- 默认模型为 `small`，需要更高精度时再显式选择更大模型
- 开启 VAD 过滤（vad_filter=True）跳过静音

### 6.3 下载模块

- **ytdlp.py**：通过 subprocess 调用 yt-dlp，只提取音频（`-x --audio-format mp3`），超时 5 分钟
- **local.py**：验证文件存在且格式支持，直接返回路径
- 支持 cookies 参数（`--cookies` / `--cookies-from-browser`）

### 6.4 总结模块

- DeepSeek API，通过 openai SDK，base_url 设为 `https://api.deepseek.com`
- 模型：`deepseek-chat`，temperature=0.3
- 文本过长时截断（max_chars=60000）
- `summarize()` 方法支持自定义 `system_prompt` 参数，不同场景可传入不同风格的 prompt
- 内置四种总结风格：简洁摘要、详细总结、提取要点、自定义（用户输入 prompt）

### 6.5 Telegram Bot

- **白名单机制**：环境变量 `ALLOWED_TELEGRAM_USERS`，逗号分隔用户 ID
  - 有值时：只允许白名单用户使用
  - 为空或未设置时：不做过滤，所有人可用
- 支持接收 URL 消息和音频/视频文件
- 文本过长时分段发送或以文件形式发送（>4000 字符）
- 需 24 小时运行，部署在 VPS 上
- **Inline Keyboard 总结功能**（需配置 DEEPSEEK_API_KEY）：
  - 转录完成后显示四个按钮：📋 简洁摘要 / 📝 详细总结 / 🎯 提取要点 / ✨ 自定义
  - 每个按钮对应不同的 system prompt 风格
  - "✨ 自定义"：用户发送风格描述（如"用猫娘语气总结"），作为 system prompt 调用 DeepSeek
  - 通过 `context.user_data` 记住上次自定义风格，下次可复用
  - 总结完成后自动移除按钮，避免重复点击
  - 未配置 DEEPSEEK_API_KEY 时不显示总结按钮

## 七、配置说明

### .env 文件

```
DASHSCOPE_API_KEY=sk-xxx        # 阿里云百炼（必需，Paraformer ASR 用）
TELEGRAM_BOT_TOKEN=7123:AAFxxx  # TG Bot Token（Bot 功能需要）
ALLOWED_TELEGRAM_USERS=123,456  # TG 白名单，可选（空=不限制）
DEEPSEEK_API_KEY=sk-xxx         # DeepSeek（可选，--summarize 用）
```

### 环境变量加载

- 本地：cli.py / web.py / bot.py 开头通过 `python-dotenv` 的 `load_dotenv()` 加载
- VPS：systemd 的 `EnvironmentFile` 指令加载

## 八、CLI 参数

```
positional:
  input                 视频/音频 URL 或本地文件路径（无参数时进入交互模式）

options:
  -e, --engine          ASR 引擎：paraformer（默认）或 whisper
  -m, --model           Whisper 模型大小（仅 whisper 引擎有效），默认 small
  -l, --lang            语言代码（zh/en/ja），默认自动检测
  -s, --summarize       启用 LLM 总结
  -C, --copy            转录完成后复制到剪贴板（macOS pbcopy）
  -c, --cookies         cookies 文件路径
  -o, --output          输出目录，默认 ./star_summary_output/
  --keep-audio          保留下载的音频文件
```

**交互模式**：不带任何参数运行 `starsummary` 时进入引导式配置，默认值支持一路回车。

## 九、输出文件

输出到 `star_summary_output/` 下，按日期分组：

```
star_summary_output/
├── 2026-02-26/
│   ├── 视频标题_143052_transcript.txt      # 纯文本转录
│   ├── 视频标题_143052_timed.txt           # 带时间戳
│   └── 视频标题_143052_summary.txt         # AI 总结（可选）
```

文件名格式：`{标题简化}_{HHMMSS}_transcript.txt`

## 十、部署方式

### 本地 Mac 使用

```bash
starsummary                    # 交互模式
starsummary "URL"              # 直接转录
starsummary -e whisper "URL"   # 本地引擎
starsummary -s "URL"           # 带总结
starsummary -C "URL"           # 转录完复制到剪贴板
starsummary-web                # Web 界面
```

### VPS 一键部署（Debian 12）

```bash
bash <(curl -sL https://raw.githubusercontent.com/starsdaisuki/starsummary/main/deploy/setup.sh)
```

部署脚本功能：
- 检测系统环境，安装系统依赖（ffmpeg、git）
- 通过 uv 安装 Python 3.12 和项目依赖
- 交互式引导配置 .env（API Key、Bot Token、白名单）
  - TELEGRAM_BOT_TOKEN 排在第一位（必填）
  - DASHSCOPE_API_KEY、ALLOWED_TELEGRAM_USERS、DEEPSEEK_API_KEY 均为可选
  - 空值不写入 .env，保持文件干净
  - ALLOWED_TELEGRAM_USERS 留空时会二次确认（任何人可用）
- 创建 systemd 服务，Bot 开机自启 + 后台运行

### systemd 服务配置

```ini
[Unit]
Description=StarSummary Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/StarSummary
EnvironmentFile=/root/StarSummary/.env
ExecStart=/root/StarSummary/.venv/bin/starsummary-bot
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 服务管理命令

```bash
systemctl status starsummary-bot   # 查看状态
systemctl restart starsummary-bot  # 重启
systemctl stop starsummary-bot     # 停止
journalctl -u starsummary-bot -f   # 实时日志
```

### 自动化任务（crontab）

```bash
0 3 * * 1 ~/.local/bin/uv tool upgrade yt-dlp    # 每周一凌晨 3 点自动更新 yt-dlp
0 4 * * * systemctl restart starsummary-bot       # 每天凌晨 4 点重启 Bot
```

### 部署注意事项

- VPS 上 yt-dlp 和 uv 装在 `~/.local/bin/`，需创建软链接到 `/usr/local/bin/` 让 systemd 能找到
- Debian 12 不支持 Ubuntu PPA，Python 版本通过 `uv python install 3.12` 管理
- 部署前确认目标网络能够访问 Telegram 与所选 ASR/LLM API

## 十一、扩展指南

### 添加新 ASR 引擎（如讯飞）

1. 新建 `transcriber/xunfei.py`，实现 `AbstractTranscriber` 接口
2. 在 `transcriber/__init__.py` 工厂函数加一个分支
3. CLI 的 `--engine` 参数加一个选项
4. 如果需要新的 API Key，在 setup.sh 引导中加一步

**只需改 2-3 个文件，核心逻辑完全不动。**

### 添加新总结引擎

同理，新建独立 provider 模块，实现 `AbstractSummarizer`，再在工厂函数中注册。

### 添加新平台入口（如 Discord Bot）

新建 `discord_bot.py`，import 现有的 downloader/transcriber/summarizer 模块即可，核心逻辑复用。

## 十二、pyproject.toml 关键配置

```toml
[project]
name = "star-summary"
requires-python = ">=3.12"
dependencies = [
    "dashscope>=1.20.0",
    "python-dotenv",
    "openai>=1.0.0",
]

[project.optional-dependencies]
whisper = ["faster-whisper>=1.0.0"]
web = ["gradio"]
bot = ["python-telegram-bot"]
all = ["faster-whisper>=1.0.0", "gradio", "python-telegram-bot"]

[project.scripts]
starsummary = "star_summary.cli:main"
starsummary-web = "star_summary.web:main"
starsummary-bot = "star_summary.bot:main"
```

## 十三、已知问题与待办

### 已知问题
- 抖音链接 yt-dlp 支持不稳定，建议先在 app 保存到本地再用本地文件模式
- B站经常改接口导致 yt-dlp 失效，需定期更新 yt-dlp

### 已完成
- [x] Telegram Bot Inline Keyboard 总结功能（四种风格 + 自定义）
- [x] 白名单可选（留空时二次确认）
- [x] openai 从可选依赖改为必需依赖
- [x] setup.sh 空值不写入 .env、修复变量名重复 bug

### 待办
- [ ] 完善 setup.sh 脚本的区域检测和 PATH 修复逻辑
- [ ] 支持新加坡 endpoint 配置选项（海外 VPS 优化延迟）
- [ ] 错误重试机制（网络波动时自动重试）
- [ ] 结构化日志持久化
- [ ] 转录失败率和 API 额度监控
- [ ] 考虑支持更多 ASR 引擎（OpenAI Whisper API、讯飞）

## 十四、开发基线

- Python 3.12+，使用 `uv` 管理环境与依赖
- 部署脚本以 Debian 12 + systemd 为兼容基线
- 编辑器应忽略 `__pycache__`、`.venv` 与本地 `.env`
