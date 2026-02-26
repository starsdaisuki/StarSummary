"""下载器抽象基类"""

from abc import ABC, abstractmethod

from star_summary.models import DownloadResult


class AbstractDownloader(ABC):
    @abstractmethod
    def download(self, source: str) -> DownloadResult:
        """下载音频，返回 DownloadResult"""
        ...
