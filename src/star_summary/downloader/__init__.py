"""下载模块 - 根据输入自动选择下载器"""

from star_summary.downloader.base import AbstractDownloader
from star_summary.downloader.ytdlp import YtdlpDownloader
from star_summary.downloader.local import LocalDownloader


def get_downloader(
    source: str,
    cookies: str | None = None,
    cookies_from_browser: str | None = None,
) -> AbstractDownloader:
    """根据输入自动判断：URL 用 YtdlpDownloader，本地文件用 LocalDownloader"""
    if source.startswith(("http://", "https://", "www.")):
        return YtdlpDownloader(
            cookies=cookies,
            cookies_from_browser=cookies_from_browser,
        )
    return LocalDownloader()
