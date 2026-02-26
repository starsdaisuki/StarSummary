"""总结模块"""

from star_summary.summarizer.base import AbstractSummarizer
from star_summary.summarizer.deepseek import DeepSeekSummarizer


def get_summarizer(api_key: str) -> AbstractSummarizer:
    """创建 DeepSeek 总结器"""
    return DeepSeekSummarizer(api_key=api_key)
