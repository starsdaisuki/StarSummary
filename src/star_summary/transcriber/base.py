"""转录器抽象基类"""

from abc import ABC, abstractmethod

from star_summary.models import TranscriptResult


class AbstractTranscriber(ABC):
    @abstractmethod
    def transcribe(self, audio_path: str, language: str | None = None) -> TranscriptResult:
        """转录音频，返回 TranscriptResult"""
        ...
