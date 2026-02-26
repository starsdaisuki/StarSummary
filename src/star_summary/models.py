"""数据模型定义"""

from dataclasses import dataclass, field


@dataclass
class Segment:
    """单个语音片段"""
    start: float          # 开始时间（秒）
    end: float            # 结束时间（秒）
    text: str             # 文本内容


@dataclass
class TranscriptResult:
    """转录结果 - 所有 transcriber 统一返回此类型"""
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
