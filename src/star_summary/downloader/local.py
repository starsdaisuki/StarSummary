"""本地文件处理"""

import os
from pathlib import Path

from star_summary.downloader.base import AbstractDownloader
from star_summary.models import DownloadResult
from star_summary.utils import log_step, log_info, log_error

SUPPORTED_FORMATS = {
    ".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma",  # audio
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".ts",   # video
}


class LocalDownloader(AbstractDownloader):
    def download(self, source: str) -> DownloadResult:
        path = os.path.abspath(source)

        if not os.path.isfile(path):
            log_error(f"File not found: {path}")
            raise FileNotFoundError(f"File not found: {path}")

        ext = Path(path).suffix.lower()
        if ext not in SUPPORTED_FORMATS:
            log_error(f"Unsupported file format: {ext}")
            log_info(f"Supported formats: {', '.join(sorted(SUPPORTED_FORMATS))}")
            raise ValueError(f"Unsupported format: {ext}")

        log_step("📂", "Using local file")
        log_info(f"File: {path}")

        title = Path(path).stem
        return DownloadResult(audio_path=path, title=title)
