"""Groq (whisper-large-v3) 云端转录实现。

复用项目现成的 openai SDK，指向 Groq 的 OpenAI 兼容 endpoint。
免费额度即可用（注册不要信用卡）。

Groq 免费版单文件上限 25MB：本实现先把音频转成 16kHz 单声道 mp3
大幅压缩；若仍超限，用 ffmpeg 按时长分片转录、再把时间戳偏移合并，
因此可通吃长短音频，真正替代云端 Paraformer/Qwen。
"""

import math
import os
import shutil
import subprocess
import tempfile
import time

from star_summary.models import Segment, TranscriptResult
from star_summary.transcriber.base import AbstractTranscriber
from star_summary.utils import log_step, log_info, log_success, log_error, log_warn

# Groq 免费版单文件 25MB，留余量
_MAX_BYTES = int(os.environ.get("GROQ_MAX_BYTES", 24 * 1024 * 1024))
# 超限时分片时长（秒）。16kHz 单声道 64kbps mp3 约 0.48MB/分钟，
# 20 分钟约 9.6MB，安全落在 25MB 内。
_CHUNK_SECONDS = int(os.environ.get("GROQ_CHUNK_SECONDS", 1200))
_GROQ_BASE_URL = "https://api.groq.com/openai/v1"


def _require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        log_error("ffmpeg not found, cannot preprocess audio")
        log_info("Install it: brew install ffmpeg")
        raise RuntimeError("ffmpeg not installed")


def _to_mono16k_mp3(src: str, start: float | None = None, dur: float | None = None) -> str:
    """转 16kHz 单声道 mp3（可选 [start, start+dur] 区间），返回临时文件路径。"""
    tmp = os.path.join(tempfile.mkdtemp(prefix="groq_asr_"), "audio.mp3")
    cmd = ["ffmpeg"]
    if start is not None:
        cmd += ["-ss", str(start)]
    if dur is not None:
        cmd += ["-t", str(dur)]
    cmd += ["-i", src, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", "-y", tmp]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return tmp


def _probe_duration(path: str) -> float:
    """用 ffprobe 取音频时长（秒）；不可用时返回 0。"""
    if shutil.which("ffprobe") is None:
        return 0.0
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, check=True,
        )
        return float(out.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        return 0.0


def _seg_get(s, key):
    """兼容 dict 或 pydantic 对象两种 segment 形态。"""
    return s.get(key) if isinstance(s, dict) else getattr(s, key, None)


class GroqTranscriber(AbstractTranscriber):
    def __init__(self, api_key: str = "", model: str = "whisper-large-v3") -> None:
        self.api_key = api_key or os.environ.get("GROQ_API_KEY", "")
        self.model = model

    def _client(self):
        try:
            from openai import OpenAI
        except ImportError:
            log_error("openai package not installed")
            log_info("Install it: uv add openai")
            raise RuntimeError("openai not installed")
        return OpenAI(base_url=_GROQ_BASE_URL, api_key=self.api_key)

    def _transcribe_one(self, client, path: str, language: str | None) -> list[Segment]:
        """转录单个（已 <25MB）文件，返回相对该文件时间轴的 Segment 列表。"""
        with open(path, "rb") as fh:
            kwargs = dict(
                model=self.model,
                file=fh,
                response_format="verbose_json",
                temperature=0,
            )
            if language:
                kwargs["language"] = language
            resp = client.audio.transcriptions.create(**kwargs)

        segments: list[Segment] = []
        for s in (getattr(resp, "segments", None) or []):
            txt = (_seg_get(s, "text") or "").strip()
            if not txt:
                continue
            segments.append(Segment(
                start=float(_seg_get(s, "start") or 0.0),
                end=float(_seg_get(s, "end") or 0.0),
                text=txt,
            ))
        if not segments:
            txt = (getattr(resp, "text", "") or "").strip()
            if txt:
                segments.append(Segment(start=0.0, end=0.0, text=txt))
        return segments

    def transcribe(self, audio_path: str, language: str | None = None) -> TranscriptResult:
        if not self.api_key:
            log_error("GROQ_API_KEY not set")
            log_info("Get a free key (no credit card) at https://console.groq.com → API Keys")
            log_info("Then set it: export GROQ_API_KEY='gsk_...'  (or put it in .env)")
            raise RuntimeError("GROQ_API_KEY not configured")

        _require_ffmpeg()
        client = self._client()

        log_step("🎙️", f"Transcribing with Groq ({self.model})...")
        log_info(f"Audio: {audio_path}")
        log_info("Converting to 16kHz mono mp3...")
        converted = _to_mono16k_mp3(audio_path)

        t0 = time.time()
        try:
            size = os.path.getsize(converted)
            if size <= _MAX_BYTES:
                segments = self._transcribe_one(client, converted, language)
            else:
                # 超 25MB：按时长分片，逐块转录后偏移时间戳合并
                duration = _probe_duration(audio_path) or _probe_duration(converted)
                if duration <= 0:
                    log_warn("无法探测时长，整文件直送（可能超 25MB 限制）")
                    segments = self._transcribe_one(client, converted, language)
                else:
                    n = math.ceil(duration / _CHUNK_SECONDS)
                    log_info(f"文件 {size / 1024 / 1024:.1f}MB 超限，分 {n} 片（每片 {_CHUNK_SECONDS}s）")
                    segments = []
                    for i in range(n):
                        start = i * _CHUNK_SECONDS
                        dur = min(_CHUNK_SECONDS, duration - start)
                        log_info(f"  片 {i + 1}/{n}: {start:.0f}s–{start + dur:.0f}s")
                        chunk = _to_mono16k_mp3(audio_path, start=start, dur=dur)
                        try:
                            chunk_segs = self._transcribe_one(client, chunk, language)
                        finally:
                            shutil.rmtree(os.path.dirname(chunk), ignore_errors=True)
                        for seg in chunk_segs:
                            seg.start += start
                            seg.end += start
                        segments.extend(chunk_segs)
        except Exception as e:
            log_error(f"Groq API error: {e}")
            log_info("检查网络/key，或换引擎：--engine paraformer / whisper")
            raise RuntimeError(f"Groq transcription failed: {e}")
        finally:
            shutil.rmtree(os.path.dirname(converted), ignore_errors=True)

        elapsed = time.time() - t0
        full_text = "\n".join(s.text for s in segments)
        total_dur = segments[-1].end if segments else 0.0

        log_success(f"Transcribed in {elapsed:.1f}s")
        log_success(f"Segments: {len(segments)}, Characters: {len(full_text)}")

        return TranscriptResult(
            text=full_text,
            segments=segments,
            language=language or "auto",
            language_confidence=1.0 if language else 0.0,
            duration=total_dur,
            transcribe_time=elapsed,
            engine=f"groq/{self.model}",
        )
