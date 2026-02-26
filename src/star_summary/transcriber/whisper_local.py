"""本地 faster-whisper 转录实现"""

import os
import time

from star_summary.models import Segment, TranscriptResult
from star_summary.transcriber.base import AbstractTranscriber
from star_summary.utils import log_step, log_info, log_success, log_warn


class WhisperLocalTranscriber(AbstractTranscriber):
    def __init__(self, model_size: str = "small") -> None:
        self.model_size = model_size

    def transcribe(self, audio_path: str, language: str | None = None) -> TranscriptResult:
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            from star_summary.utils import log_error
            log_error("faster-whisper package not installed")
            log_info("Install it: uv add faster-whisper")
            raise RuntimeError("faster-whisper not installed")

        log_step("🎙️", f"Transcribing with Whisper ({self.model_size})...")
        log_info("Loading model (first run will download the model)...")

        # CPU 线程数限制为总核心数的一半（避免过热）
        cpu_count = os.cpu_count() or 4
        cpu_threads = max(1, cpu_count // 2)
        log_info(f"Using {cpu_threads}/{cpu_count} CPU threads")

        model = WhisperModel(
            self.model_size,
            device="cpu",
            compute_type="int8",
            cpu_threads=cpu_threads,
        )

        log_info("Transcribing... (this may take a moment)")
        t0 = time.time()

        raw_segments, info = model.transcribe(
            audio_path,
            language=language,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )

        segments: list[Segment] = []
        text_parts: list[str] = []
        for seg in raw_segments:
            text = seg.text.strip()
            if text:
                segments.append(Segment(start=seg.start, end=seg.end, text=text))
                text_parts.append(text)

        elapsed = time.time() - t0
        full_text = "\n".join(text_parts)

        log_success(
            f"Language: {info.language} "
            f"({info.language_probability:.0%} confidence)"
        )
        if info.duration > 0:
            log_success(
                f"Duration: {info.duration:.0f}s → "
                f"Transcribed in {elapsed:.1f}s "
                f"({info.duration / elapsed:.1f}x realtime)"
            )
        log_success(f"Segments: {len(segments)}, Characters: {len(full_text)}")

        return TranscriptResult(
            text=full_text,
            segments=segments,
            language=info.language,
            language_confidence=info.language_probability,
            duration=info.duration,
            transcribe_time=elapsed,
            engine="whisper",
        )
