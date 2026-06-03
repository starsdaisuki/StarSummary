"""CLI 入口 - argparse 参数解析与流程编排"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

from star_summary import __version__
from star_summary.config import Config
from star_summary.models import TranscriptResult, SummaryResult
from star_summary.utils import (
    _Colors as _C,
    log_step, log_info, log_success, log_warn, log_error, format_time,
)


def _check_system_deps() -> None:
    """检查系统依赖（yt-dlp, ffmpeg）"""
    missing = []
    if shutil.which("yt-dlp") is None:
        missing.append("yt-dlp")
    if shutil.which("ffmpeg") is None:
        missing.append("ffmpeg")
    if missing:
        log_warn(f"System tools not found: {', '.join(missing)}")
        log_info("Install them: brew install yt-dlp ffmpeg")
        log_info("(Only needed for downloading from URLs)")


def _sanitize_title(title: str) -> str:
    """简化标题：取前30字符，去掉特殊符号，空格换下划线"""
    title = title[:30]
    title = re.sub(r'[\\/:*?"<>|.\n\r\t]', '', title)
    title = title.strip()
    title = re.sub(r'\s+', '_', title)
    return title or "untitled"


def _build_output_dir(base_dir: str, title: str) -> tuple[str, str]:
    """构建按日期分组的输出目录，返回 (output_dir, file_prefix)"""
    today = datetime.now().strftime("%Y-%m-%d")
    time_stamp = datetime.now().strftime("%H%M%S")
    safe_title = _sanitize_title(title)
    file_prefix = f"{safe_title}_{time_stamp}"
    output_dir = os.path.join(base_dir, today)
    os.makedirs(output_dir, exist_ok=True)
    return output_dir, file_prefix


def _save_results(
    transcript: TranscriptResult,
    summary: SummaryResult | None,
    output_dir: str,
    file_prefix: str,
    source: str,
) -> str:
    """保存转录和总结结果到文件，返回 transcript 文件的绝对路径"""
    log_step("💾", "Saving results...")

    # 1. transcript.txt - 纯文本（带元信息头部注释）
    transcript_path = os.path.join(output_dir, f"{file_prefix}_transcript.txt")
    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write(f"# Source: {source}\n")
        f.write(f"# Engine: {transcript.engine}\n")
        f.write(f"# Language: {transcript.language}")
        if transcript.language_confidence > 0:
            f.write(f" ({transcript.language_confidence:.0%})")
        f.write("\n")
        f.write(f"# Duration: {transcript.duration:.0f}s\n")
        f.write(f"# Segments: {len(transcript.segments)}\n")
        f.write(f"# Transcribe time: {transcript.transcribe_time:.1f}s\n")
        f.write("# " + "─" * 50 + "\n\n")
        f.write(transcript.text)
    log_success(f"Transcript → {os.path.abspath(transcript_path)}")

    # 2. timed.txt - 带时间戳
    timed_path = os.path.join(output_dir, f"{file_prefix}_timed.txt")
    with open(timed_path, "w", encoding="utf-8") as f:
        for seg in transcript.segments:
            start = format_time(seg.start)
            end = format_time(seg.end)
            f.write(f"[{start} → {end}]  {seg.text}\n")
    log_success(f"Timed transcript → {os.path.abspath(timed_path)}")

    # 3. summary.txt - AI 总结（仅 --summarize 时）
    if summary and summary.text:
        summary_path = os.path.join(output_dir, f"{file_prefix}_summary.txt")
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(f"# Source: {source}\n")
            f.write(f"# Model: {summary.model}\n")
            f.write(f"# Summarize time: {summary.summarize_time:.1f}s\n")
            f.write("# " + "─" * 50 + "\n\n")
            f.write(summary.text)
        log_success(f"Summary → {os.path.abspath(summary_path)}")

    return os.path.abspath(transcript_path)


def _copy_to_clipboard(text: str) -> None:
    """复制文本到系统剪贴板（macOS pbcopy）"""
    try:
        proc = subprocess.run(
            ["pbcopy"], input=text.encode("utf-8"), check=True,
        )
        log_success("Transcript copied to clipboard")
    except (FileNotFoundError, subprocess.CalledProcessError):
        log_warn("Failed to copy to clipboard (pbcopy not available)")


def _print_preview(transcript: TranscriptResult, summary: SummaryResult | None) -> None:
    """打印结果预览"""
    log_step("📝", "Transcript preview:")
    preview = transcript.text[:500]
    if len(transcript.text) > 500:
        preview += f"\n... ({len(transcript.text) - 500} more characters)"
    print(f"\n{_C.DIM}{preview}{_C.RESET}")

    if summary and summary.text:
        log_step("📋", "Summary:")
        print(f"\n{summary.text}")


def _build_config_from_args(args: argparse.Namespace) -> Config:
    """从 argparse 结果构建 Config"""
    return Config(
        input=args.input,
        engine=args.engine,
        whisper_model=args.model,
        language=args.lang,
        summarize=args.summarize,
        deepseek_api_key=args.api_key or "",
        cookies=args.cookies,
        cookies_from_browser=args.cookies_from_browser,
        output_dir=args.output or "./star_summary_output",
        keep_audio=args.keep_audio,
        copy=args.copy,
    )


def _prompt(icon: str, msg: str, default: str = "") -> str:
    """带图标的交互提示，支持默认值"""
    hint = f" ({default})" if default else ""
    try:
        return input(f"  {icon} {msg}{hint}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)


def _interactive_mode() -> Config:
    """交互模式：逐步提示用户输入参数，返回 Config"""
    # 输入源（必填）
    while True:
        source = _prompt("📎", "视频链接或文件路径")
        if source:
            break
        log_warn("Please enter a URL or file path")

    # ASR 引擎
    engine_input = _prompt("🎙️", "ASR 引擎 [groq/paraformer/whisper]", "groq")
    engine = engine_input if engine_input in ("groq", "paraformer", "whisper") else "groq"

    # AI 总结
    summarize_input = _prompt("🤖", "AI 总结? [y/N]", "N")
    summarize = summarize_input.lower() in ("y", "yes")

    # 复制到剪贴板
    copy_input = _prompt("📋", "复制到剪贴板? [Y/n]", "Y")
    copy = copy_input.lower() not in ("n", "no")

    print()
    return Config(
        input=source,
        engine=engine,
        summarize=summarize,
        copy=copy,
    )


def _parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="StarSummary (星语) - Video/Audio → Transcript → Summary",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "https://www.bilibili.com/video/BV1xx..."
  %(prog)s "https://www.youtube.com/watch?v=xxx" --engine whisper --model large-v3
  %(prog)s recording.m4a --lang zh             # 默认 groq 引擎（云端 whisper-large-v3）
  %(prog)s video.mp4 --engine paraformer       # 超长音频用阿里云实时兜底
  %(prog)s audio.mp3 --summarize
  %(prog)s "https://..." -s -o ~/summaries/
  %(prog)s "https://v.douyin.com/xxx" -cb chrome
  %(prog)s audio.mp3 --copy
        """,
    )

    parser.add_argument(
        "input",
        help="Video/audio URL (YouTube, Bilibili, etc.) or local file path",
    )
    parser.add_argument(
        "-e", "--engine",
        default="groq",
        choices=["groq", "paraformer", "whisper"],
        help="ASR engine (default: groq — cloud whisper-large-v3, free tier)",
    )
    parser.add_argument(
        "-m", "--model",
        default="small",
        choices=["tiny", "base", "small", "medium", "large-v2", "large-v3"],
        help="Whisper model size, only for --engine whisper (default: small)",
    )
    parser.add_argument(
        "-l", "--lang",
        default=None,
        help="Language code, e.g. zh, en, ja (default: auto-detect)",
    )
    parser.add_argument(
        "-s", "--summarize",
        action="store_true",
        help="Enable LLM summarization with DeepSeek",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="DeepSeek API key (or set DEEPSEEK_API_KEY env var)",
    )
    parser.add_argument(
        "-c", "--cookies",
        default=None,
        help="Path to cookies.txt file",
    )
    parser.add_argument(
        "-cb", "--cookies-from-browser",
        default=None,
        metavar="BROWSER",
        help="Read cookies from browser: chrome, edge, safari, firefox",
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Output directory (default: ./star_summary_output/)",
    )
    parser.add_argument(
        "--keep-audio",
        action="store_true",
        help="Keep downloaded audio file after transcription",
    )
    parser.add_argument(
        "-C", "--copy",
        action="store_true",
        help="Copy transcript to clipboard (macOS pbcopy)",
    )

    return parser.parse_args()


def _print_banner() -> None:
    print(f"""
{_C.MAGENTA}{_C.BOLD}  ✦ StarSummary (星语) ✦{_C.RESET}
{_C.DIM}  Video/Audio → Transcript → Summary{_C.RESET}
    """)


def main() -> None:
    from dotenv import load_dotenv
    load_dotenv()

    _print_banner()

    # 无参数 → 交互模式，有参数 → CLI 模式
    if len(sys.argv) == 1:
        config = _interactive_mode()
    else:
        args = _parse_args()
        config = _build_config_from_args(args)

    # ── 检查系统依赖 ──
    _check_system_deps()

    # ── Step 1: 下载/获取音频 ──
    from star_summary.downloader import get_downloader

    downloader = get_downloader(
        config.input,
        cookies=config.cookies,
        cookies_from_browser=config.cookies_from_browser,
    )

    try:
        download_result = downloader.download(config.input)
    except (RuntimeError, FileNotFoundError, ValueError) as e:
        log_error(str(e))
        sys.exit(1)

    # ── Step 2: 转录 ──
    from star_summary.transcriber import get_transcriber

    transcriber = get_transcriber(
        engine=config.engine,
        model=config.whisper_model,
        api_key=config.dashscope_api_key,
        groq_api_key=config.groq_api_key,
    )

    try:
        transcript = transcriber.transcribe(
            download_result.audio_path,
            language=config.language,
        )
    except RuntimeError as e:
        log_error(str(e))
        sys.exit(1)
    finally:
        # 清理临时文件（yt-dlp 下载的音频）
        from star_summary.downloader.ytdlp import YtdlpDownloader
        if isinstance(downloader, YtdlpDownloader):
            if config.keep_audio:
                for f in os.listdir(downloader.tmp_dir):
                    shutil.move(
                        os.path.join(downloader.tmp_dir, f),
                        os.path.join(config.output_dir, f),
                    )
                log_info(f"Audio kept in {config.output_dir}/")
            shutil.rmtree(downloader.tmp_dir, ignore_errors=True)

    # ── Step 3: 可选总结 ──
    summary = None
    if config.summarize:
        if not config.deepseek_api_key:
            log_warn("No DeepSeek API key found.")
            log_info("Set DEEPSEEK_API_KEY env var or use --api-key")
            log_warn("Skipping summarization.")
        else:
            from star_summary.summarizer import get_summarizer

            summarizer = get_summarizer(api_key=config.deepseek_api_key)
            summary = summarizer.summarize(transcript.text)

    # ── Step 4: 保存结果 ──
    title = download_result.title or "untitled"
    source = download_result.title or config.input
    output_dir, file_prefix = _build_output_dir(config.output_dir, title)
    transcript_path = _save_results(transcript, summary, output_dir, file_prefix, source)

    # ── Step 5: 复制到剪贴板 ──
    if config.copy:
        _copy_to_clipboard(transcript.text)

    # ── Step 6: 打印预览 ──
    _print_preview(transcript, summary)

    # ── Done ──
    print(f"\n{_C.GREEN}{_C.BOLD}  ✦ All done! Files saved to: {os.path.abspath(output_dir)}/ ✦{_C.RESET}\n")


if __name__ == "__main__":
    main()
