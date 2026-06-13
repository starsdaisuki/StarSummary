"""yt-dlp 下载器实现"""

import functools
import os
import subprocess
import tempfile
from urllib.parse import urlparse

from star_summary.downloader.base import AbstractDownloader
from star_summary.models import DownloadResult
from star_summary.utils import log_step, log_info, log_success, log_warn, log_error


# B 站反爬风控（HTTP 412）绕过：B 站 WAF 用 TLS 指纹识别非浏览器客户端，
# 普通 yt-dlp 抓网页就被 412 拒绝；playurl API 还额外要求 Origin 头。
# 官方修复 PR #16889 截至 2026-06 仍未合并到任何发布版，故在调用层 workaround：
#   --impersonate chrome  → 模拟真浏览器 TLS+HTTP2 指纹（需 yt-dlp 装 curl_cffi）
#   --add-header Origin   → 过 api.bilibili.com 的 412
# 仅对 B 站链接生效，YouTube/抖音等不受影响。
_BILIBILI_HOSTS = ("bilibili.com", "b23.tv", "bilibili.tv")


def _is_bilibili(source: str) -> bool:
    host = urlparse(source).netloc.lower()
    return any(h in host for h in _BILIBILI_HOSTS)


@functools.lru_cache(maxsize=1)
def _impersonate_available() -> bool:
    """检测系统 yt-dlp 是否带 curl_cffi（--impersonate 依赖它）。
    可用时输出形如 'Chrome-136 ... curl_cffi'，不可用时为 'Chrome ... (unavailable)'。"""
    try:
        result = subprocess.run(
            ["yt-dlp", "--list-impersonate-targets"],
            capture_output=True, text=True, timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    return any(
        "chrome" in line.lower() and "unavailable" not in line.lower()
        for line in result.stdout.splitlines()
    )


def _bilibili_args(source: str) -> list[str]:
    """B 站链接需要的额外参数；非 B 站返回空（保持原行为不变）。"""
    if not _is_bilibili(source):
        return []
    args = ["--add-header", "Origin:https://www.bilibili.com"]
    if _impersonate_available():
        args = ["--impersonate", "chrome", *args]
    else:
        log_warn(
            "B站需要 curl_cffi 才能绕过 412 风控，否则会下载失败。"
            "请运行: uv tool install --upgrade yt-dlp --with curl_cffi"
        )
    return args


class YtdlpDownloader(AbstractDownloader):
    def __init__(
        self,
        cookies: str | None = None,
        cookies_from_browser: str | None = None,
    ) -> None:
        self.cookies = cookies
        self.cookies_from_browser = cookies_from_browser
        self._tmp_dir = tempfile.mkdtemp(prefix="starsummary_")

    @property
    def tmp_dir(self) -> str:
        return self._tmp_dir

    def download(self, source: str) -> DownloadResult:
        log_step("📥", "Downloading audio...")
        log_info(f"URL: {source}")
        if self.cookies_from_browser:
            log_info(f"Reading cookies from: {self.cookies_from_browser}")
        elif self.cookies:
            log_info(f"Using cookies file: {self.cookies}")

        # 先尝试获取标题
        title = self._get_title(source)

        # 下载音频
        output_template = os.path.join(self._tmp_dir, "audio.%(ext)s")
        cmd = [
            "yt-dlp",
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", "3",
            "-o", output_template,
            "--no-playlist",
            "--no-warnings",
        ]

        if self.cookies_from_browser:
            cmd.extend(["--cookies-from-browser", self.cookies_from_browser])
        elif self.cookies:
            cmd.extend(["--cookies", self.cookies])

        cmd.extend(_bilibili_args(source))
        cmd.append(source)

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                log_error(f"yt-dlp failed:\n{result.stderr}")
                log_info("Try downloading the file manually and use the local file path instead.")
                raise RuntimeError("yt-dlp download failed")
        except subprocess.TimeoutExpired:
            log_error("Download timed out (5 min limit)")
            raise RuntimeError("Download timed out")
        except FileNotFoundError:
            log_error("yt-dlp not found. Install it: brew install yt-dlp")
            raise RuntimeError("yt-dlp not installed")

        # 查找下载的文件
        audio_path = self._find_audio()
        size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        log_success(f"Audio downloaded: {size_mb:.1f} MB")

        return DownloadResult(audio_path=audio_path, title=title)

    def _get_title(self, source: str) -> str:
        """尝试获取视频标题"""
        cmd = ["yt-dlp", "--print", "title", "--no-warnings", "--no-playlist"]
        if self.cookies_from_browser:
            cmd.extend(["--cookies-from-browser", self.cookies_from_browser])
        elif self.cookies:
            cmd.extend(["--cookies", self.cookies])
        cmd.extend(_bilibili_args(source))
        cmd.append(source)

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                title = result.stdout.strip()
                log_info(f"Title: {title}")
                return title
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return ""

    def _find_audio(self) -> str:
        """查找下载目录中的音频文件"""
        audio_file = os.path.join(self._tmp_dir, "audio.mp3")
        if os.path.exists(audio_file):
            return audio_file

        for f in os.listdir(self._tmp_dir):
            if f.startswith("audio."):
                return os.path.join(self._tmp_dir, f)

        log_error("Failed to find downloaded audio file")
        raise RuntimeError("Downloaded audio file not found")
