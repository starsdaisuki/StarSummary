"""阿里云百炼 ASR 转录实现（dashscope SDK 同步调用）"""

import os
import shutil
import subprocess
import tempfile
import time

from star_summary.models import Segment, TranscriptResult
from star_summary.transcriber.base import AbstractTranscriber
from star_summary.utils import log_step, log_info, log_success, log_error, log_warn

def _ensure_mono_16k_mp3(audio_path: str) -> str:
    """用 ffmpeg 将音频转换为单声道 16kHz mp3，返回临时文件路径"""
    if shutil.which("ffmpeg") is None:
        log_error("ffmpeg not found, cannot convert audio format")
        log_info("Install it: brew install ffmpeg")
        raise RuntimeError("ffmpeg not installed")

    tmp_path = os.path.join(tempfile.mkdtemp(prefix="starsummary_conv_"), "audio.mp3")
    cmd = ["ffmpeg", "-i", audio_path, "-vn", "-ar", "16000", "-ac", "1", "-y", tmp_path]

    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=True)
    except subprocess.CalledProcessError as e:
        log_error(f"ffmpeg conversion failed: {e.stderr}")
        raise RuntimeError("Audio format conversion failed")

    log_info(f"Converted to mp3: {tmp_path}")
    return tmp_path


class ParaformerTranscriber(AbstractTranscriber):
    def __init__(self, api_key: str = "", model: str = "fun-asr-realtime") -> None:
        self.api_key = api_key or os.environ.get("DASHSCOPE_API_KEY", "")
        self.model = model

    def transcribe(self, audio_path: str, language: str | None = None) -> TranscriptResult:
        if not self.api_key:
            log_error("DASHSCOPE_API_KEY not set")
            log_info("Set the environment variable: export DASHSCOPE_API_KEY='your-key'")
            log_info("Or switch to local engine: starsummary <input> --engine whisper")
            raise RuntimeError("DASHSCOPE_API_KEY not configured")

        try:
            from dashscope.audio.asr import Recognition
            from http import HTTPStatus
        except ImportError:
            log_error("dashscope package not installed")
            log_info("Install it: uv add dashscope")
            raise RuntimeError("dashscope not installed")

        # dashscope SDK 自动读取 DASHSCOPE_API_KEY 环境变量
        os.environ["DASHSCOPE_API_KEY"] = self.api_key

        log_step("🎙️", f"Transcribing with {self.model}...")
        log_info(f"Audio: {audio_path}")

        # 统一转换为单声道 16kHz mp3（dashscope ASR 只支持单声道）
        log_info("Converting to mono 16kHz mp3...")
        converted_path = _ensure_mono_16k_mp3(audio_path)
        audio_path = converted_path

        # 构建语言提示
        language_hints = ["zh", "en"]
        if language:
            language_hints = [language]

        recognition = Recognition(
            model=self.model,
            format="mp3",
            sample_rate=16000,
            language_hints=language_hints,
            callback=None,
        )

        t0 = time.time()

        try:
            result = recognition.call(audio_path)
        except Exception as e:
            log_error(f"ASR API error: {e}")
            log_info("Check your network connection or try: starsummary <input> --engine whisper")
            raise RuntimeError(f"ASR API call failed: {e}")
        finally:
            # 清理转换的临时文件
            try:
                os.remove(converted_path)
                os.rmdir(os.path.dirname(converted_path))
            except OSError:
                pass

        elapsed = time.time() - t0

        if result.status_code != HTTPStatus.OK:
            msg = getattr(result, "message", "unknown error")
            log_error(f"ASR API returned error: {result.status_code}")
            log_info(f"Message: {msg}")
            raise RuntimeError(f"ASR API error: {result.status_code} - {msg}")

        # 解析 sentences → 统一的 TranscriptResult
        sentences = result.get_sentence() or []
        segments: list[Segment] = []
        text_parts: list[str] = []

        for s in sentences:
            text = s.get("text", "").strip()
            if not text:
                continue
            begin = s.get("begin_time", 0) / 1000.0  # ms → s
            end = s.get("end_time", 0) / 1000.0
            segments.append(Segment(start=begin, end=end, text=text))
            text_parts.append(text)

        full_text = "\n".join(text_parts)
        detected_lang = language or "zh"

        log_success(f"Transcribed in {elapsed:.1f}s")
        log_success(f"Segments: {len(segments)}, Characters: {len(full_text)}")

        return TranscriptResult(
            text=full_text,
            segments=segments,
            language=detected_lang,
            language_confidence=1.0,
            duration=segments[-1].end if segments else 0.0,
            transcribe_time=elapsed,
            engine=self.model,
        )
