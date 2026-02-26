"""总结器抽象基类"""

from abc import ABC, abstractmethod

from star_summary.models import SummaryResult


class AbstractSummarizer(ABC):
    @abstractmethod
    def summarize(self, text: str, system_prompt: str | None = None) -> SummaryResult:
        """总结文本，返回 SummaryResult。可选自定义 system_prompt。"""
        ...
