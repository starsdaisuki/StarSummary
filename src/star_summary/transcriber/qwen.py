"""阿里云百炼 Qwen3-ASR 转录实现（中文首选引擎）。

相比 Groq 上的 whisper-large-v3，qwen3-asr-flash 在中文上的优势是同素材实测出来的：
带伴奏的中文歌里，whisper 把「讲台」听成「墙台」、「粉笔灰」听成「粉笔回」、
「装甲」听成「庄稼」，还会在纯音乐/静音段凭空补出「作词 ×××」「优优独播剧场」
这类训练集里的字幕水印（Whisper 的经典幻觉）；qwen3-asr-flash 上述全部正确，
且非语音段直接不输出。

两个 API 限制和对应处理：
  1. 单次调用最长 5 分钟 / 10MB  → 按静音点切片后并发调用，再按片偏移拼时间戳。
  2. 同步接口不返回句级时间戳    → 片内按标点切句、按字数比例插值出近似时间戳
                                    （片边界是真实时间，片内是估算）。
"""

import concurrent.futures as _futures
import os
import re
import shutil
import subprocess
import tempfile
import time

from star_summary.models import Segment, TranscriptResult
from star_summary.transcriber.base import AbstractTranscriber
from star_summary.utils import log_step, log_info, log_success, log_error, log_warn

# 单次调用硬上限 5 分钟，留余量
_MAX_CHUNK_SECONDS = 280.0
# 切片目标时长。官方工具包默认 120s，但实测切点附近会丢词
# （Anthropic→暗拓扑、神仙代码→深陷），切得越少越好，所以尽量贴近上限。
# 代价是时间戳粒度变粗——片内是按字数插值估算的。
_TARGET_CHUNK_SECONDS = float(os.environ.get("QWEN_CHUNK_SECONDS", 240))
# 并发上传数（纯网络 IO，不吃本地算力）
_CONCURRENCY = int(os.environ.get("QWEN_CONCURRENCY", 4))
# 句子切分标点
_SENT_SPLIT = re.compile(r"(?<=[。！？；!?;])")


def _require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        log_error("ffmpeg not found, cannot preprocess audio")
        log_info("Install it: brew install ffmpeg")
        raise RuntimeError("ffmpeg not installed")


def _to_mono16k_mp3(src: str, start: float | None = None, dur: float | None = None) -> str:
    """转 16kHz 单声道 mp3（可选 [start, start+dur] 区间），返回临时文件绝对路径。"""
    tmp = os.path.join(tempfile.mkdtemp(prefix="qwen_asr_"), "audio.mp3")
    cmd = ["ffmpeg"]
    if start is not None:
        cmd += ["-ss", str(start)]
    if dur is not None:
        cmd += ["-t", str(dur)]
    cmd += ["-i", src, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", "-y", tmp]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return os.path.abspath(tmp)


def _probe_duration(path: str) -> float:
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


def _silence_midpoints(path: str) -> list[float]:
    """用 ffmpeg silencedetect 找静音段，返回每段静音的中点（秒），作为候选切点。"""
    try:
        proc = subprocess.run(
            ["ffmpeg", "-i", path, "-af", "silencedetect=noise=-35dB:d=0.35",
             "-f", "null", "-"],
            capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError:
        return []

    starts = [float(m) for m in re.findall(r"silence_start:\s*([\d.]+)", proc.stderr)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*([\d.]+)", proc.stderr)]
    return [(s + e) / 2 for s, e in zip(starts, ends)]


def _plan_chunks(duration: float, cuts: list[float]) -> list[tuple[float, float]]:
    """贪心地在静音点处切片，返回 [(start, end), ...]。找不到静音点就按固定时长硬切。"""
    if duration <= _MAX_CHUNK_SECONDS:
        return [(0.0, duration)]

    spans: list[tuple[float, float]] = []
    pos = 0.0
    cuts = sorted(c for c in cuts if c > 0)

    while duration - pos > _MAX_CHUNK_SECONDS:
        lo, hi = pos + _TARGET_CHUNK_SECONDS * 0.5, pos + _MAX_CHUNK_SECONDS
        # 选落在 [lo, hi] 内、最接近目标时长的静音点
        candidates = [c for c in cuts if lo <= c <= hi]
        if candidates:
            target = pos + _TARGET_CHUNK_SECONDS
            cut = min(candidates, key=lambda c: abs(c - target))
        else:
            cut = min(pos + _TARGET_CHUNK_SECONDS, hi)  # 没静音点就硬切
        spans.append((pos, cut))
        pos = cut

    spans.append((pos, duration))
    return spans


def _split_into_segments(text: str, start: float, end: float) -> list[Segment]:
    """把一片的文本按标点切句，按字数比例插值时间戳。"""
    text = text.strip()
    if not text:
        return []

    parts = [p.strip() for p in _SENT_SPLIT.split(text) if p.strip()]
    if len(parts) <= 1:
        return [Segment(start=start, end=end, text=text)]

    total = sum(len(p) for p in parts) or 1
    span = max(end - start, 0.0)
    segments: list[Segment] = []
    cursor = start
    for p in parts:
        width = span * len(p) / total
        segments.append(Segment(start=cursor, end=min(cursor + width, end), text=p))
        cursor += width
    return segments


class QwenASRTranscriber(AbstractTranscriber):
    """qwen3-asr-flash / qwen3-asr-flash-realtime 等百炼 Qwen-ASR 系列。"""

    def __init__(
        self,
        api_key: str = "",
        model: str = "qwen3-asr-flash",
        context: str = "",
    ) -> None:
        self.api_key = api_key or os.environ.get("DASHSCOPE_API_KEY", "")
        self.model = model
        # context：专有名词/术语提示，直接偏置识别结果（whisper 的 prompt 做不到这件事）
        self.context = (context or os.environ.get("STAR_SUMMARY_ASR_CONTEXT", "")).strip()

    # ── 单片调用 ──
    def _call_once(self, mp3_path: str, language: str | None, attempt: int = 0):
        import dashscope

        messages = []
        if self.context:
            messages.append({"role": "system", "content": [{"text": self.context}]})
        messages.append({"role": "user", "content": [{"audio": "file://" + mp3_path}]})

        asr_options: dict = {"enable_itn": False}
        if language:
            asr_options["language"] = language

        resp = dashscope.MultiModalConversation.call(
            api_key=self.api_key,
            model=self.model,
            messages=messages,
            result_format="message",
            asr_options=asr_options,
        )

        if resp.status_code != 200:
            # 限流/瞬时错误退避重试
            if attempt < 2 and resp.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                return self._call_once(mp3_path, language, attempt + 1)
            raise RuntimeError(f"Qwen ASR API error {resp.status_code}: "
                               f"{getattr(resp, 'code', '')} {getattr(resp, 'message', '')}")

        try:
            content = resp.output.choices[0].message.content
        except (AttributeError, IndexError, KeyError):
            return "", None

        text = ""
        for item in content or []:
            if isinstance(item, dict) and item.get("text"):
                text = item["text"].strip()
                break

        detected = None
        for ann in (getattr(resp.output.choices[0].message, "annotations", None) or []):
            if isinstance(ann, dict) and ann.get("type") == "audio_info":
                detected = ann.get("language")
        return text, detected

    def _transcribe_span(self, src: str, span: tuple[float, float], language: str | None):
        start, end = span
        chunk = _to_mono16k_mp3(src, start=start, dur=end - start)
        try:
            text, detected = self._call_once(chunk, language)
        finally:
            shutil.rmtree(os.path.dirname(chunk), ignore_errors=True)
        return _split_into_segments(text, start, end), detected

    # ── 主入口 ──
    def transcribe(self, audio_path: str, language: str | None = None) -> TranscriptResult:
        if not self.api_key:
            log_error("DASHSCOPE_API_KEY not set")
            log_info("拿 key：https://bailian.console.aliyun.com → API-KEY（支付宝实名即可，不要外币卡）")
            log_info("然后写进 .env：DASHSCOPE_API_KEY=sk-...")
            log_info("或换引擎：starsummary <input> --engine groq / whisper")
            raise RuntimeError("DASHSCOPE_API_KEY not configured")

        try:
            import dashscope  # noqa: F401
        except ImportError:
            log_error("dashscope package not installed")
            log_info("Install it: uv add dashscope")
            raise RuntimeError("dashscope not installed")

        _require_ffmpeg()

        log_step("🎙️", f"Transcribing with Qwen ASR ({self.model})...")
        log_info(f"Audio: {audio_path}")
        if self.context:
            log_info(f"Context 提示: {self.context[:60]}{'…' if len(self.context) > 60 else ''}")

        duration = _probe_duration(audio_path)
        t0 = time.time()

        try:
            if duration <= 0:
                log_warn("无法探测时长，按单片直送（音频超 5 分钟会被 API 拒绝）")
                spans = [(0.0, 0.0)]
                converted = _to_mono16k_mp3(audio_path)
                try:
                    text, detected = self._call_once(converted, language)
                finally:
                    shutil.rmtree(os.path.dirname(converted), ignore_errors=True)
                segments = _split_into_segments(text, 0.0, 0.0)
            elif duration <= _MAX_CHUNK_SECONDS:
                log_info(f"时长 {duration:.0f}s，单次调用")
                segments, detected = self._transcribe_span(audio_path, (0.0, duration), language)
            else:
                cuts = _silence_midpoints(audio_path)
                spans = _plan_chunks(duration, cuts)
                log_info(f"时长 {duration:.0f}s 超单次上限，切 {len(spans)} 片"
                         f"（静音点 {len(cuts)} 个，并发 {_CONCURRENCY}）")

                results: list[list[Segment]] = [[] for _ in spans]
                detected = None
                with _futures.ThreadPoolExecutor(max_workers=_CONCURRENCY) as pool:
                    futs = {
                        pool.submit(self._transcribe_span, audio_path, sp, language): i
                        for i, sp in enumerate(spans)
                    }
                    done = 0
                    for fut in _futures.as_completed(futs):
                        i = futs[fut]
                        segs, lang_i = fut.result()
                        results[i] = segs
                        detected = detected or lang_i
                        done += 1
                        log_info(f"  片 {done}/{len(spans)} 完成"
                                 f"（{spans[i][0]:.0f}s–{spans[i][1]:.0f}s，{sum(len(s.text) for s in segs)} 字）")
                segments = [s for group in results for s in group]
        except RuntimeError:
            raise
        except Exception as e:
            log_error(f"Qwen ASR error: {e}")
            log_info("检查网络/key，或换引擎：--engine groq / whisper")
            raise RuntimeError(f"Qwen transcription failed: {e}")

        elapsed = time.time() - t0
        full_text = "\n".join(s.text for s in segments)

        log_success(f"Transcribed in {elapsed:.1f}s")
        log_success(f"Segments: {len(segments)}, Characters: {len(full_text)}")

        return TranscriptResult(
            text=full_text,
            segments=segments,
            language=language or detected or "auto",
            language_confidence=1.0 if language else 0.0,
            duration=duration or (segments[-1].end if segments else 0.0),
            transcribe_time=elapsed,
            engine=f"qwen/{self.model}",
        )
