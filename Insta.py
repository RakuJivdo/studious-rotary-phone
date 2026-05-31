"""
Instagram Reels Downloader Telegram Bot
Requirements: pip install python-telegram-bot yt-dlp
Usage: python insta_bot.py
"""

import os
import logging
import asyncio
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
import yt_dlp

# ── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"   # ← paste your bot token here
DOWNLOAD_DIR = "./downloads"
COOKIES_FILE = "instagram_cookies.txt"  # optional but recommended (see below)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

os.makedirs(DOWNLOAD_DIR, exist_ok=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def is_instagram_url(url: str) -> bool:
    return "instagram.com" in url and (
        "/reel/" in url or "/reels/" in url or "/p/" in url or "/tv/" in url
    )


def download_reel(url: str) -> str | None:
    """Download Instagram reel and return file path, or None on failure."""
    out_template = os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s")

    opts = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": out_template,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": False,
        "postprocessors": [
            {
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            }
        ],
        # Use cookies if file exists (helps with private/login-required reels)
        **({"cookiefile": COOKIES_FILE} if os.path.exists(COOKIES_FILE) else {}),
        # Spoof a browser to avoid Instagram bot detection
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        },
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = ydl.prepare_filename(info)
            # Normalize extension
            for ext in (".webm", ".mkv"):
                path = path.replace(ext, ".mp4")
            return path
    except Exception as e:
        logger.error("Download failed: %s", e)
        return None


# ── Handlers ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Instagram Reels Downloader*\n\n"
        "Just send me an Instagram Reel link and I'll download it in the highest quality!\n\n"
        "Supported links:\n"
        "• instagram.com/reel/...\n"
        "• instagram.com/p/...\n"
        "• instagram.com/tv/...\n\n"
        "⚠️ Only *public* reels work without login cookies.",
        parse_mode="Markdown",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()

    if not is_instagram_url(url):
        await update.message.reply_text(
            "❌ That doesn't look like an Instagram Reel link.\n"
            "Please send a link like:\n`https://www.instagram.com/reel/ABC123/`",
            parse_mode="Markdown",
        )
        return

    # Clean URL — remove tracking params
    url = url.split("?")[0].rstrip("/") + "/"

    status_msg = await update.message.reply_text("⏳ Downloading reel in highest quality…")

    file_path = await asyncio.get_event_loop().run_in_executor(
        None, download_reel, url
    )

    if not file_path or not os.path.exists(file_path):
        await status_msg.edit_text(
            "❌ Download failed!\n\n"
            "Possible reasons:\n"
            "• Reel is from a *private account*\n"
            "• Instagram blocked the request\n"
            "• Invalid or expired link\n\n"
            "Try again in a minute or send a different reel.",
            parse_mode="Markdown",
        )
        return

    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    logger.info("Downloaded: %s (%.1f MB)", file_path, file_size_mb)

    if file_size_mb > 50:
        os.remove(file_path)
        await status_msg.edit_text(
            f"⚠️ File is *{file_size_mb:.1f} MB* — too large for Telegram (50 MB limit).\n"
            "This is a very long reel. Unfortunately it can't be sent directly.",
            parse_mode="Markdown",
        )
        return

    await status_msg.edit_text("📤 Uploading to Telegram…")

    try:
        with open(file_path, "rb") as video_file:
            await context.bot.send_video(
                chat_id=update.message.chat_id,
                video=video_file,
                caption="✅ Here's your Instagram Reel!",
                supports_streaming=True,
            )
        await status_msg.delete()
    except Exception as e:
        logger.error("Upload failed: %s", e)
        await status_msg.edit_text(f"❌ Upload failed: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Instagram Reel Bot is running… Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
