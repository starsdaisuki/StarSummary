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
from star_summary.transcriber import ENGINES, DEFAULT_ENGINE
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
        asr_context=args.context or "",
        summarize=args.summarize,
        deepseek_api_key=args.api_key or "",
        cookies=args.cookies,
        cookies_from_browser=args.cookies_from_browser,
        output_dir=args.output or "./star_summary_output",
        keep_audio=args.keep_audio,
        copy=args.copy,
    )


def _prompt_line(text: str) -> str:
    """单行输入，处理 EOF / Ctrl-C。"""
    try:
        return input(text).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)


# ──────────────────── 交互模式：媒体文件夹批量转录 ────────────────────

AUDIO_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".oga", ".aac", ".opus", ".wma"}
VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".flv", ".ts"}
MEDIA_EXTS = AUDIO_EXTS | VIDEO_EXTS


def _media_kind(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in VIDEO_EXTS:
        return "video"
    return "unknown"


def _media_icon(path: str) -> str:
    return "🎬" if _media_kind(path) == "video" else "🎵"


def _find_media(directory: str) -> list[str]:
    """目录下所有支持的音频/视频文件（按名排序）。"""
    try:
        names = os.listdir(directory)
    except OSError:
        return []
    out = [
        os.path.join(directory, n)
        for n in names
        if os.path.isfile(os.path.join(directory, n))
        and os.path.splitext(n)[1].lower() in MEDIA_EXTS
    ]
    return sorted(out)


def _parse_selection(choice: str, items: list) -> list:
    """解析 '1 3 5' / '1-3' / 逗号混合；去重保序。"""
    picked = []
    for part in choice.replace(",", " ").split():
        if "-" in part:
            try:
                a, b = part.split("-", 1)
                picked += [items[i - 1] for i in range(int(a), int(b) + 1) if 1 <= i <= len(items)]
            except ValueError:
                continue
        else:
            try:
                i = int(part)
                if 1 <= i <= len(items):
                    picked.append(items[i - 1])
            except ValueError:
                continue
    seen, uniq = set(), []
    for x in picked:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def _transcribe_and_save(transcriber, summarizer, path: str, out_dir: str | None, language: str | None) -> None:
    """转录单个媒体文件并写出 <stem>.txt / .timed.txt [/ .summary.txt]。"""
    size_mb = os.path.getsize(path) / (1024 * 1024)
    name = os.path.basename(path)
    print(f"\n{_media_icon(path)} {name}（{size_mb:.1f} MB）")

    transcript = transcriber.transcribe(path, language=language)

    stem = os.path.splitext(name)[0]
    base = os.path.join(out_dir or os.path.dirname(path), stem)

    with open(base + ".txt", "w", encoding="utf-8") as f:
        f.write(transcript.text + "\n")
    with open(base + ".timed.txt", "w", encoding="utf-8") as f:
        for seg in transcript.segments:
            f.write(f"[{format_time(seg.start)} → {format_time(seg.end)}]  {seg.text}\n")

    print(f"  {_C.GREEN}✅ 完成! {len(transcript.segments)} 段, {len(transcript.text)} 字 → {base}.txt{_C.RESET}")

    if summarizer is not None:
        summary = summarizer.summarize(transcript.text)
        if summary and summary.text:
            with open(base + ".summary.txt", "w", encoding="utf-8") as f:
                f.write(summary.text + "\n")
            print(f"  {_C.GREEN}📋 总结 → {base}.summary.txt{_C.RESET}")


def _interactive_batch() -> None:
    """无参数时的引导模式：扫描文件夹 → 选引擎 → 批量转录（默认 qwen3-asr-flash）。"""
    from star_summary.transcriber import get_transcriber

    print(f"\n{_C.MAGENTA}{_C.BOLD}⭐ StarSummary 交互模式{_C.RESET}")
    print(f"{_C.DIM}{'─' * 40}{_C.RESET}")

    # 1. 文件夹（或直接一个文件）
    print("\n📁 音频/视频在哪个文件夹？")
    print(f"   {_C.DIM}直接回车 = 当前目录（{os.getcwd()}）{_C.RESET}")
    target = _prompt_line("   路径: ")
    target = os.path.expanduser(target) if target else os.getcwd()

    single = False
    if os.path.isfile(target) and os.path.splitext(target)[1].lower() in MEDIA_EXTS:
        files, single = [target], True
    elif os.path.isdir(target):
        files = _find_media(target)
        if not files:
            log_error(f"{target} 下没有音频/视频文件")
            log_info(f"支持: {', '.join(sorted(MEDIA_EXTS))}")
            sys.exit(1)
    else:
        log_error(f"路径不存在或格式不支持: {target}")
        sys.exit(1)

    # 2. 列出 + 选择
    if single:
        selected = files
        print(f"\n{_media_icon(files[0])} 选中: {os.path.basename(files[0])}")
    else:
        na = sum(1 for f in files if _media_kind(f) == "audio")
        nv = sum(1 for f in files if _media_kind(f) == "video")
        parts = [p for p in (f"{na} 音频" if na else "", f"{nv} 视频" if nv else "") if p]
        print(f"\n📋 找到 {len(files)} 个文件（{' · '.join(parts)}）:")
        for i, p in enumerate(files, 1):
            sz = os.path.getsize(p) / (1024 * 1024)
            print(f"   {i}. {_media_icon(p)} {os.path.basename(p)}（{sz:.1f} MB）")

        print("\n🔢 要转哪些？（直接回车 = 全部）")
        print(f"   {_C.DIM}支持: 1 3 5  /  1-3  /  all  /  按类型: audio  video{_C.RESET}")
        choice = _prompt_line("   选择: ").lower()
        if not choice or choice == "all":
            selected = files
        elif choice in ("audio", "音频", "video", "视频"):
            tk = {"音频": "audio", "视频": "video"}.get(choice, choice)
            selected = [f for f in files if _media_kind(f) == tk]
            if not selected:
                log_error(f"没有 {choice} 类型的文件")
                sys.exit(1)
        else:
            selected = _parse_selection(choice, files)
            if not selected:
                log_error("无效选择")
                sys.exit(1)

    # 3. 引擎
    engine_keys = list(ENGINES)
    print("\n🧠 用哪个识别引擎？（直接回车 = 1）")
    for i, k in enumerate(engine_keys, 1):
        star = " ←默认" if k == DEFAULT_ENGINE else ""
        print(f"   {i}. {ENGINES[k]['label']}{star}")
        print(f"      {_C.DIM}{ENGINES[k]['desc']}{_C.RESET}")
    pick = _prompt_line("   选择: ")
    engine = DEFAULT_ENGINE
    if pick:
        if pick in ENGINES:
            engine = pick
        elif pick.isdigit() and 1 <= int(pick) <= len(engine_keys):
            engine = engine_keys[int(pick) - 1]
        else:
            log_warn(f"看不懂「{pick}」，用默认 {DEFAULT_ENGINE}")

    # 4. 专有名词提示（仅 qwen）
    asr_context = ""
    if engine == "qwen":
        print("\n🏷️  音频里有特殊人名/术语吗？（直接回车 = 跳过，推荐跳过）")
        print(f"   {_C.DIM}⚠️ 词写不全反而会把本来对的词带偏，只在你确定时才填{_C.RESET}")
        print(f"   {_C.DIM}例: 卷积 感受野 池化 反向传播{_C.RESET}")
        asr_context = _prompt_line("   提示词: ")

    # 5. 语言
    print("\n🌐 语言？（直接回车 = zh 中文，中英混说也 OK）")
    print(f"   {_C.DIM}也可填: en  ja  auto{_C.RESET}")
    lang = _prompt_line("   语言: ").lower() or "zh"
    if lang == "auto":
        lang = None

    # 6. 输出目录
    print("\n📝 转录文本输出到哪？")
    print(f"   {_C.DIM}直接回车 = 和源文件同目录{_C.RESET}")
    out_dir = _prompt_line("   路径: ")
    if out_dir:
        out_dir = os.path.expanduser(out_dir)
        os.makedirs(out_dir, exist_ok=True)
    else:
        out_dir = None

    # 7. 可选 AI 总结
    do_summary = _prompt_line("\n🤖 顺便给每篇做 AI 总结? [y/N]: ").lower() in ("y", "yes")

    # 准备引擎 + 总结器
    config = Config(engine=engine, asr_context=asr_context)
    transcriber = get_transcriber(
        engine=config.engine,
        model=config.whisper_model,
        api_key=config.dashscope_api_key,
        groq_api_key=config.groq_api_key,
        context=config.asr_context,
    )
    summarizer = None
    if do_summary:
        if not config.deepseek_api_key:
            log_warn("没有 DEEPSEEK_API_KEY，跳过总结")
        else:
            from star_summary.summarizer import get_summarizer
            summarizer = get_summarizer(api_key=config.deepseek_api_key)

    # 开跑
    print(f"\n{_C.CYAN}{_C.BOLD}🚀 开始处理 {len(selected)} 个文件...{_C.RESET}")
    failures = []
    for path in selected:
        try:
            _transcribe_and_save(transcriber, summarizer, path, out_dir, lang)
        except Exception as exc:
            failures.append((os.path.basename(path), str(exc)))
            log_error(f"失败: {os.path.basename(path)}: {exc}")
            log_info("继续下一个...")

    if failures:
        print(f"\n{_C.YELLOW}⚠️ 完成，但有 {len(failures)} 个失败:{_C.RESET}")
        for n, e in failures:
            print(f"   - {n}: {e}")
        sys.exit(1)
    print(f"\n{_C.GREEN}{_C.BOLD}🎉 全部完成！共 {len(selected)} 个文件{_C.RESET}")


def _parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="StarSummary (星语) - Video/Audio → Transcript → Summary",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "https://www.bilibili.com/video/BV1xx..."
  %(prog)s "https://www.youtube.com/watch?v=xxx" --engine whisper --model large-v3
  %(prog)s recording.m4a --lang zh             # 默认 qwen 引擎（阿里 qwen3-asr-flash，中文最准）
  %(prog)s video.mp4 --engine groq             # 英文素材可用 Groq whisper-large-v3
  %(prog)s lecture.mp3 --context "卷积 感受野 池化 反向传播"   # 专有名词提示（谨慎用，见 --context 说明）
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
        default=DEFAULT_ENGINE,
        choices=list(ENGINES),
        help=f"ASR engine (default: {DEFAULT_ENGINE} — 阿里 qwen3-asr-flash，中文准确率远高于 whisper)",
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
        "--context",
        default=None,
        help=("专有名词提示，空格分隔，仅 qwen 引擎生效。⚠️ 实测是双刃剑："
              "提示词不全会把本来识别对的词带偏，只在你确定音频里有哪些人名/术语时才用"),
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

    # 无参数 → 交互引导模式（文件夹批量转录），有参数 → CLI 模式
    if len(sys.argv) == 1:
        _interactive_batch()
        return
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
        context=config.asr_context,
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
