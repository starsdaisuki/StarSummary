"""Telegram Bot for StarSummary"""

import io
import os
import re
import shutil
import tempfile

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)
from star_summary.config import Config
from star_summary.utils import format_time

WELCOME_TEXT = """✦ StarSummary (星语) ✦

视频/音频 → 文字转录，发链接即用。

使用方式：
• 直接发送视频链接（YouTube、B站、抖音等）
• 或者发送音频/视频文件

支持平台：
YouTube, Bilibili, 抖音, 西瓜视频, 微博, Twitter/X, 及更多 yt-dlp 支持的站点

命令：
/start - 欢迎信息
/help - 使用帮助"""

HELP_TEXT = """使用帮助

1. 发送链接
直接粘贴视频链接，Bot 会自动下载并转录：
https://www.bilibili.com/video/BVxxx
https://www.youtube.com/watch?v=xxx

2. 发送文件
直接发送音频或视频文件，Bot 会自动转录。
支持格式：mp3, wav, flac, m4a, ogg, mp4, mkv, avi, mov, webm

3. 输出
转录完成后，Bot 会直接回复文字。
如果文本较长，会以 txt 文件形式发送。

注意：
• 较长的视频可能需要几分钟处理
• 默认使用阿里云 Paraformer 引擎"""

# URL 正则
_URL_PATTERN = re.compile(r'https?://\S+')

# Telegram 单条消息最大长度
_MAX_MSG_LEN = 4000


def _is_url(text: str) -> bool:
    return bool(_URL_PATTERN.match(text.strip()))


def _run_transcribe(audio_path: str) -> tuple[str, str]:
    """
    执行转录流水线，返回 (转录文本, 状态信息)。
    """
    config = Config()
    from star_summary.transcriber import get_transcriber

    transcriber = get_transcriber(
        engine=config.engine,
        model=config.whisper_model,
        api_key=config.dashscope_api_key,
    )

    transcript = transcriber.transcribe(audio_path, language=config.language)

    info_parts = [
        f"引擎: {transcript.engine}",
        f"语言: {transcript.language}",
    ]
    if transcript.duration > 0:
        info_parts.append(f"时长: {format_time(transcript.duration)}")
    info_parts.append(f"耗时: {transcript.transcribe_time:.1f}s")
    info_parts.append(f"字符: {len(transcript.text)}")

    return transcript.text, " | ".join(info_parts)


async def _send_transcript(update: Update, text: str, info: str) -> None:
    """发送转录结果，过长则以文件形式发送"""
    if len(text) <= _MAX_MSG_LEN:
        await update.message.reply_text(f"{text}\n\n📊 {info}")
    else:
        # 以 txt 文件发送
        buf = io.BytesIO(text.encode("utf-8"))
        buf.name = "transcript.txt"
        await update.message.reply_document(
            document=buf,
            caption=f"📝 转录完成（{len(text)} 字符）\n📊 {info}",
        )


async def cmd_start(update: Update, context) -> None:
    await update.message.reply_text(WELCOME_TEXT)


async def cmd_help(update: Update, context) -> None:
    await update.message.reply_text(HELP_TEXT)


async def handle_url(update: Update, context) -> None:
    """处理用户发送的 URL"""
    url = update.message.text.strip()

    if not _is_url(url):
        return

    status_msg = await update.message.reply_text("⏳ 正在下载音频...")

    # 下载
    from star_summary.downloader import get_downloader
    from star_summary.downloader.ytdlp import YtdlpDownloader

    downloader = get_downloader(url)
    try:
        download_result = downloader.download(url)
    except Exception as e:
        await status_msg.edit_text(
            f"❌ 下载失败: {e}\n\n"
            "请检查链接是否正确，或尝试其他平台的链接。\n"
            "支持：YouTube, Bilibili, 抖音, 西瓜视频, Twitter/X 等"
        )
        return

    title = download_result.title or "未知标题"
    await status_msg.edit_text(f"🎙️ 正在转录: {title}")

    # 转录
    try:
        text, info = _run_transcribe(download_result.audio_path)
    except Exception as e:
        await status_msg.edit_text(f"❌ 转录失败: {e}\n\n请稍后重试。")
        return
    finally:
        if isinstance(downloader, YtdlpDownloader):
            shutil.rmtree(downloader.tmp_dir, ignore_errors=True)

    await status_msg.delete()
    await _send_transcript(update, text, info)


async def handle_file(update: Update, context) -> None:
    """处理用户发送的音频/视频文件"""
    message = update.message
    file_obj = message.audio or message.video or message.document or message.voice

    if file_obj is None:
        return

    # 检查文件大小（Telegram Bot API 限制 20MB 下载）
    if file_obj.file_size and file_obj.file_size > 20 * 1024 * 1024:
        await message.reply_text("⚠️ 文件超过 20MB，Telegram 限制无法下载。\n请上传较小的文件或发送视频链接。")
        return

    status_msg = await message.reply_text("⏳ 正在下载文件...")

    # 下载文件到本地
    tmp_dir = tempfile.mkdtemp(prefix="starsummary_tg_")
    file_name = getattr(file_obj, "file_name", None) or "audio.mp3"
    local_path = os.path.join(tmp_dir, file_name)

    try:
        tg_file = await file_obj.get_file()
        await tg_file.download_to_drive(local_path)
    except Exception as e:
        await status_msg.edit_text(f"❌ 文件下载失败: {e}")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return

    await status_msg.edit_text("🎙️ 正在转录...")

    # 转录
    try:
        text, info = _run_transcribe(local_path)
    except Exception as e:
        await status_msg.edit_text(f"❌ 转录失败: {e}\n\n请稍后重试。")
        return
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    await status_msg.delete()
    await _send_transcript(update, text, info)


async def handle_unknown(update: Update, context) -> None:
    """处理无法识别的文本消息"""
    text = update.message.text or ""
    if text.startswith("/"):
        await update.message.reply_text("❓ 未知命令，输入 /help 查看帮助。")
    # 非 URL 非命令的普通文本，忽略


def main() -> None:
    from dotenv import load_dotenv
    load_dotenv()

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN not set")
        print("   Set it in .env or environment: export TELEGRAM_BOT_TOKEN='your-token'")
        return

    print("✦ StarSummary Bot starting...")

    app = Application.builder().token(token).build()

    # 命令处理
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))

    # 文件处理（音频、视频、文档、语音）
    app.add_handler(MessageHandler(
        filters.AUDIO | filters.VIDEO | filters.Document.ALL | filters.VOICE,
        handle_file,
    ))

    # URL 处理
    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(_URL_PATTERN),
        handle_url,
    ))

    # 未知消息
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unknown))

    print("✦ Bot is running. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
