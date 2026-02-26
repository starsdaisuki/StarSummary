"""阿里云百炼 Paraformer 转录实现"""

import os
import time

from star_summary.models import Segment, TranscriptResult
from star_summary.transcriber.base import AbstractTranscriber
from star_summary.utils import log_step, log_info, log_success, log_error, log_warn


class ParaformerTranscriber(AbstractTranscriber):
    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key or os.environ.get("DASHSCOPE_API_KEY", "")

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

        # 设置 API Key
        os.environ["DASHSCOPE_API_KEY"] = self.api_key

        log_step("🎙️", "Transcribing with Paraformer...")
        log_info(f"Audio: {audio_path}")

        # 根据文件后缀判断格式
        ext = os.path.splitext(audio_path)[1].lstrip(".").lower()
        audio_format = ext if ext in ("mp3", "wav", "flac", "aac", "ogg", "m4a") else "mp3"

        # 构建语言提示
        language_hints = ["zh", "en"]
        if language:
            language_hints = [language]

        recognition = Recognition(
            model="paraformer-realtime-v2",
            format=audio_format,
            sample_rate=16000,
            language_hints=language_hints,
        )

        t0 = time.time()

        try:
            result = recognition.call(audio_path)
        except Exception as e:
            log_error(f"Paraformer API error: {e}")
            log_info("Check your network connection or try: starsummary <input> --engine whisper")
            raise RuntimeError(f"Paraformer API call failed: {e}")

        elapsed = time.time() - t0

        if result.status_code != HTTPStatus.OK:
            log_error(f"Paraformer API returned error: {result.status_code}")
            log_info(f"Message: {getattr(result, 'message', 'unknown error')}")
            raise RuntimeError(f"Paraformer API error: {result.status_code}")

        # 解析结果
        sentences = result.get_sentence() or []
        segments: list[Segment] = []
        text_parts: list[str] = []

        for s in sentences:
            text = s.get("text", "").strip()
            if not text:
                continue
            begin = s.get("begin_time", 0) / 1000.0  # ms -> s
            end = s.get("end_time", 0) / 1000.0
            segments.append(Segment(start=begin, end=end, text=text))
            text_parts.append(text)

        full_text = "\n".join(text_parts)

        # 检测到的语言
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
            engine="paraformer",
        )
