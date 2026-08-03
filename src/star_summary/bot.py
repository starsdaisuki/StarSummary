"""Telegram Bot for StarSummary"""

import io
import os
import re
import shutil
import tempfile

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
from star_summary.config import Config
from star_summary.transcriber import ENGINES, DEFAULT_ENGINE
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
/help - 使用帮助
/engine - 切换识别引擎（中文推荐阿里 qwen）"""

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

4. 切换识别引擎
发送 /engine 弹出引擎选择菜单，点一下就切，之后的转录都用新引擎。
• 阿里 qwen3-asr-flash（默认）— 中文/歌曲/术语最准，不会在静音段编字幕
• Groq whisper-large-v3 — 英文够用，免费额度大
• 本地 faster-whisper — 离线可用，慢

注意：
• 较长的视频可能需要几分钟处理
• 引擎选择按聊天记住，重启 Bot 后回到默认"""

# URL 正则
_URL_PATTERN = re.compile(r'https?://\S+')

# Telegram 单条消息最大长度
_MAX_MSG_LEN = 4000


def _get_allowed_users() -> set[int]:
    """读取 ALLOWED_TELEGRAM_USERS 环境变量，返回允许的用户 ID 集合。空集合表示不限制。"""
    raw = os.environ.get("ALLOWED_TELEGRAM_USERS", "").strip()
    if not raw:
        return set()
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


async def _check_user(update: Update) -> bool:
    """检查用户是否有权限。白名单为空时允许所有人。"""
    allowed = _get_allowed_users()
    if not allowed:
        return True
    user_id = update.effective_user.id if update.effective_user else 0
    if user_id in allowed:
        return True
    await update.message.reply_text("⛔ 你没有权限使用此 Bot。")
    return False


def _is_url(text: str) -> bool:
    return bool(_URL_PATTERN.match(text.strip()))


def _run_transcribe(audio_path: str, engine: str | None = None) -> tuple[str, str]:
    """
    执行转录流水线，返回 (转录文本, 状态信息)。
    engine 为 None 时用默认引擎；由 /engine 命令按聊天覆盖。
    """
    config = Config(engine=engine or DEFAULT_ENGINE)
    from star_summary.transcriber import get_transcriber

    transcriber = get_transcriber(
        engine=config.engine,
        model=config.whisper_model,
        api_key=config.dashscope_api_key,
        groq_api_key=config.groq_api_key,
        context=config.asr_context,
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


def _has_deepseek_key() -> bool:
    """检查是否配置了 DeepSeek API Key"""
    return bool(os.environ.get("DEEPSEEK_API_KEY", "").strip())


# 总结风格预设
_SUMMARY_STYLES: dict[str, str] = {
    "brief": "请用2-3句话概括这段内容的核心信息，简明扼要。",
    "detailed": "请对以下内容进行详细总结：先概括主题，再分点列出关键内容，标注重要数据和结论。",
    "keypoints": "请从以下内容中提取所有关键要点、数据、结论，用编号列表呈现。",
}


async def _send_transcript(update: Update, context, text: str, info: str) -> None:
    """发送转录结果，过长则以文件形式发送。配置了 DeepSeek 时显示总结按钮。"""
    # 构建 inline keyboard
    if _has_deepseek_key():
        keyboard = [
            [
                InlineKeyboardButton("📋 简洁摘要", callback_data="sum:brief"),
                InlineKeyboardButton("📝 详细总结", callback_data="sum:detailed"),
            ],
            [
                InlineKeyboardButton("🎯 提取要点", callback_data="sum:keypoints"),
                InlineKeyboardButton("✨ 自定义", callback_data="sum:custom"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
    else:
        reply_markup = None

    if len(text) <= _MAX_MSG_LEN:
        await update.message.reply_text(
            f"{text}\n\n📊 {info}",
            reply_markup=reply_markup,
        )
    else:
        # 以 txt 文件发送
        buf = io.BytesIO(text.encode("utf-8"))
        buf.name = "transcript.txt"
        await update.message.reply_document(
            document=buf,
            caption=f"📝 转录完成（{len(text)} 字符）\n📊 {info}",
            reply_markup=reply_markup,
        )

    # 存储转录文本供后续总结/导出使用
    context.user_data["last_transcript"] = text
    context.user_data["last_info"] = info


async def cmd_start(update: Update, context) -> None:
    await update.message.reply_text(WELCOME_TEXT)


async def cmd_help(update: Update, context) -> None:
    await update.message.reply_text(HELP_TEXT)


def _current_engine(context) -> str:
    return context.user_data.get("engine", DEFAULT_ENGINE)


async def cmd_engine(update: Update, context) -> None:
    """/engine —— 弹出引擎选择菜单"""
    if not await _check_user(update):
        return

    current = _current_engine(context)
    rows = []
    for key, meta in ENGINES.items():
        mark = "✅ " if key == current else ""
        rows.append([InlineKeyboardButton(f"{mark}{meta['label']}", callback_data=f"eng:{key}")])

    lines = ["🧠 选择识别引擎\n", f"当前：{ENGINES[current]['label']}\n"]
    for key, meta in ENGINES.items():
        lines.append(f"• {meta['label']}\n  {meta['desc']}")
    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def handle_url(update: Update, context) -> None:
    """处理用户发送的 URL"""
    if not await _check_user(update):
        return

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
        text, info = _run_transcribe(download_result.audio_path, engine=_current_engine(context))
    except Exception as e:
        await status_msg.edit_text(f"❌ 转录失败: {e}\n\n请稍后重试。")
        return
    finally:
        if isinstance(downloader, YtdlpDownloader):
            shutil.rmtree(downloader.tmp_dir, ignore_errors=True)

    await status_msg.delete()
    await _send_transcript(update, context, text, info)


async def handle_file(update: Update, context) -> None:
    """处理用户发送的音频/视频文件"""
    if not await _check_user(update):
        return

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
        text, info = _run_transcribe(local_path, engine=_current_engine(context))
    except Exception as e:
        await status_msg.edit_text(f"❌ 转录失败: {e}\n\n请稍后重试。")
        return
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    await status_msg.delete()
    await _send_transcript(update, context, text, info)


async def _run_summary(query, context, system_prompt: str) -> None:
    """执行总结并回复结果"""
    transcript = context.user_data.get("last_transcript", "")
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()

    status_msg = await query.message.reply_text("⏳ 正在生成总结...")

    try:
        from star_summary.summarizer import get_summarizer

        summarizer = get_summarizer(api_key=deepseek_key)
        result = summarizer.summarize(transcript, system_prompt=system_prompt)

        if result.text:
            summary_info = f"模型: {result.model} | 耗时: {result.summarize_time:.1f}s"
            if len(result.text) <= _MAX_MSG_LEN:
                await status_msg.edit_text(f"🤖 AI 总结\n\n{result.text}\n\n📊 {summary_info}")
            else:
                await status_msg.delete()
                buf = io.BytesIO(result.text.encode("utf-8"))
                buf.name = "summary.txt"
                await query.message.reply_document(
                    document=buf,
                    caption=f"🤖 AI 总结（{len(result.text)} 字符）\n📊 {summary_info}",
                )
        else:
            await status_msg.edit_text("❌ 总结生成失败，请稍后重试。")
    except Exception as e:
        await status_msg.edit_text(f"❌ 总结失败: {e}")


async def handle_callback(update: Update, context) -> None:
    """处理 Inline Keyboard 按钮点击"""
    query = update.callback_query
    await query.answer()

    # 引擎切换：不依赖已有转录，必须在 last_transcript 检查之前处理
    if query.data and query.data.startswith("eng:"):
        key = query.data.split(":", 1)[1]
        if key not in ENGINES:
            return
        context.user_data["engine"] = key
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            f"✅ 已切换到 {ENGINES[key]['label']}\n{ENGINES[key]['desc']}"
        )
        return

    transcript = context.user_data.get("last_transcript", "")
    if not transcript:
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("⚠️ 没有可用的转录文本，请重新发送链接或文件。")
        return

    if not query.data or not query.data.startswith("sum:"):
        return

    style = query.data.split(":", 1)[1]

    # 移除按钮，防止重复点击
    await query.edit_message_reply_markup(reply_markup=None)

    if style == "custom":
        # 自定义风格：提示用户输入
        prev_style = context.user_data.get("custom_style", "")
        if prev_style:
            hint = f"🎨 上次的风格：{prev_style}\n\n直接发送「用上次的」复用，或发送新的总结风格描述："
        else:
            hint = "🎨 请发送你想要的总结风格描述："
        await query.message.reply_text(hint)
        context.user_data["waiting_custom_style"] = True
        return

    system_prompt = _SUMMARY_STYLES.get(style)
    if not system_prompt:
        return

    await _run_summary(query, context, system_prompt)


async def handle_custom_style(update: Update, context) -> None:
    """处理用户发送的自定义总结风格"""
    if not context.user_data.get("waiting_custom_style"):
        return  # 不在等待状态，跳过让后续 handler 处理

    context.user_data["waiting_custom_style"] = False
    text = (update.message.text or "").strip()

    if not text:
        await update.message.reply_text("⚠️ 风格描述不能为空，请重新点击自定义按钮。")
        return

    # 如果用户说复用上次的
    prev_style = context.user_data.get("custom_style", "")
    if prev_style and text in ("用上次的", "复用", "上次的"):
        text = prev_style

    # 保存自定义风格
    context.user_data["custom_style"] = text

    transcript = context.user_data.get("last_transcript", "")
    if not transcript:
        await update.message.reply_text("⚠️ 没有可用的转录文本，请重新发送链接或文件。")
        return

    deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not deepseek_key:
        await update.message.reply_text("⚠️ 未配置 DEEPSEEK_API_KEY，无法生成总结。")
        return

    status_msg = await update.message.reply_text("⏳ 正在生成总结...")

    try:
        from star_summary.summarizer import get_summarizer

        summarizer = get_summarizer(api_key=deepseek_key)
        result = summarizer.summarize(transcript, system_prompt=text)

        if result.text:
            summary_info = f"模型: {result.model} | 耗时: {result.summarize_time:.1f}s"
            if len(result.text) <= _MAX_MSG_LEN:
                await status_msg.edit_text(f"🤖 AI 总结\n\n{result.text}\n\n📊 {summary_info}")
            else:
                await status_msg.delete()
                buf = io.BytesIO(result.text.encode("utf-8"))
                buf.name = "summary.txt"
                await update.message.reply_document(
                    document=buf,
                    caption=f"🤖 AI 总结（{len(result.text)} 字符）\n📊 {summary_info}",
                )
        else:
            await status_msg.edit_text("❌ 总结生成失败，请稍后重试。")
    except Exception as e:
        await status_msg.edit_text(f"❌ 总结失败: {e}")


async def handle_unknown(update: Update, context) -> None:
    """处理无法识别的文本消息"""
    # 如果正在等待自定义风格输入，交给 handle_custom_style
    if context.user_data.get("waiting_custom_style"):
        await handle_custom_style(update, context)
        return
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
    app.add_handler(CommandHandler("engine", cmd_engine))

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

    # Inline Keyboard 回调
    app.add_handler(CallbackQueryHandler(handle_callback))

    # 未知消息
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unknown))

    print("✦ Bot is running. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
