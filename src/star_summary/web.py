"""Gradio Web UI for StarSummary"""

import os
import time
import traceback

import gradio as gr

from star_summary.config import Config
from star_summary.utils import format_time


def _run_pipeline(
    source: str,
    engine: str,
    language: str,
    summarize: bool,
) -> tuple[str, str, str]:
    """
    执行完整流水线，返回 (转录文本, 总结文本, 状态信息)。
    复用现有的 downloader / transcriber / summarizer 模块。
    """
    if not source.strip():
        return "", "", "请输入视频链接或文件路径"

    config = Config(
        input=source.strip(),
        engine=engine,
        language=language if language != "auto" else None,
        summarize=summarize,
    )

    status_parts: list[str] = []

    # ── Step 1: 下载/获取音频 ──
    from star_summary.downloader import get_downloader

    downloader = get_downloader(config.input)
    try:
        download_result = downloader.download(config.input)
    except Exception as e:
        return "", "", f"下载失败: {e}"

    title = download_result.title or config.input
    status_parts.append(f"标题: {title}")

    # ── Step 2: 转录 ──
    from star_summary.transcriber import get_transcriber

    transcriber = get_transcriber(
        engine=config.engine,
        model=config.whisper_model,
        api_key=config.dashscope_api_key,
    )

    try:
        transcript = transcriber.transcribe(
            download_result.audio_path,
            language=config.language,
        )
    except Exception as e:
        return "", "", f"转录失败: {e}"
    finally:
        # 清理 yt-dlp 临时文件
        import shutil
        from star_summary.downloader.ytdlp import YtdlpDownloader
        if isinstance(downloader, YtdlpDownloader):
            shutil.rmtree(downloader.tmp_dir, ignore_errors=True)

    status_parts.append(f"引擎: {transcript.engine}")
    status_parts.append(f"语言: {transcript.language}")
    if transcript.duration > 0:
        status_parts.append(f"音频时长: {format_time(transcript.duration)}")
    status_parts.append(f"转录耗时: {transcript.transcribe_time:.1f}s")
    status_parts.append(f"片段数: {len(transcript.segments)}")
    status_parts.append(f"字符数: {len(transcript.text)}")

    # ── Step 3: 可选总结 ──
    summary_text = "未启用"
    if config.summarize:
        if not config.deepseek_api_key:
            summary_text = "未配置 DEEPSEEK_API_KEY，跳过总结"
        else:
            from star_summary.summarizer import get_summarizer

            summarizer = get_summarizer(api_key=config.deepseek_api_key)
            try:
                summary_result = summarizer.summarize(transcript.text)
                summary_text = summary_result.text or "总结为空"
                status_parts.append(f"总结耗时: {summary_result.summarize_time:.1f}s")
            except Exception as e:
                summary_text = f"总结失败: {e}"

    # ── 保存文件 ──
    from star_summary.cli import _build_output_dir, _save_results
    from star_summary.models import SummaryResult

    output_dir, file_prefix = _build_output_dir("./star_summary_output", title)
    summary_obj = SummaryResult(text=summary_text) if config.summarize and summary_text not in ("未启用", "") else None
    _save_results(transcript, summary_obj, output_dir, file_prefix, title)
    status_parts.append(f"文件保存: {os.path.abspath(output_dir)}/")

    status = "\n".join(status_parts)
    return transcript.text, summary_text, status


def _build_ui() -> gr.Blocks:
    """构建 Gradio 界面"""
    with gr.Blocks(title="StarSummary (星语)") as demo:
        gr.Markdown("# ✦ StarSummary (星语) ✦\n视频/音频 → 文字，一键搞定")

        with gr.Row():
            with gr.Column(scale=1):
                source_input = gr.Textbox(
                    label="视频链接或文件路径",
                    placeholder="https://www.bilibili.com/video/BVxxx 或 /path/to/audio.mp3",
                    lines=1,
                )
                engine_radio = gr.Radio(
                    choices=["paraformer", "whisper"],
                    value="paraformer",
                    label="ASR 引擎",
                )
                lang_dropdown = gr.Dropdown(
                    choices=["auto", "zh", "en", "ja"],
                    value="auto",
                    label="语言",
                )
                summarize_check = gr.Checkbox(
                    label="AI 总结 (需要 DEEPSEEK_API_KEY)",
                    value=False,
                )
                run_btn = gr.Button("开始转录", variant="primary", size="lg")

            with gr.Column(scale=2):
                transcript_output = gr.Textbox(
                    label="转录文本",
                    lines=20,
                    max_lines=50,
                )
                summary_output = gr.Textbox(
                    label="AI 总结",
                    lines=8,
                    max_lines=20,
                )
                status_output = gr.Textbox(
                    label="状态信息",
                    lines=4,
                    interactive=False,
                )

        run_btn.click(
            fn=_run_pipeline,
            inputs=[source_input, engine_radio, lang_dropdown, summarize_check],
            outputs=[transcript_output, summary_output, status_output],
        )

    return demo


def main() -> None:
    from dotenv import load_dotenv
    load_dotenv()

    demo = _build_ui()
    demo.launch(inbrowser=True, theme=gr.themes.Soft())


if __name__ == "__main__":
    main()
