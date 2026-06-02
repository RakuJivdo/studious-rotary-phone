import os
import re
import asyncio  # Delay dene ke liye use hoga
import logging
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = "7903545339:AAFzleTOLJOJPiEhCtf79L3fQJtkL9b46XQ"
TARGET_GROUP_ID = -1003956011577

# ─── Telegram Limits ────────────────────────────────────────────────────────
MAX_QUESTION_LEN = 300
MAX_OPTION_LEN = 100
FIXED_OPTIONS = 4

# ─── Error Codes & Messages ──────────────────────────────────────────────────
ERROR_MESSAGES = {
    "MISSING_QUESTION": "❌ ERROR [MISSING_QUESTION]: Pehli line empty hai -- question likho.",
    "TOO_FEW_OPTIONS": "❌ ERROR [TOO_FEW_OPTIONS]: Exactly 4 options hone chahiye (lines 2-5).",
    "NO_CORRECT_OPTION": "❌ ERROR [NO_CORRECT_OPTION]: Kisi bhi option mein * nahi lagaya. Sahi answer ke option ke end mein * lagao. Jaise: Delhi*",
    "MULTIPLE_CORRECT_OPTIONS": "❌ ERROR [MULTIPLE_CORRECT_OPTIONS]: Ek se zyada options mein * laga hai. Sirf ek sahi answer hona chahiye.",
    "QUESTION_TOO_LONG": f"❌ ERROR [QUESTION_TOO_LONG]: Question {MAX_QUESTION_LEN} characters se zyada lamba hai (Telegram limit).",
    "OPTION_TOO_LONG": f"❌ ERROR [OPTION_TOO_LONG]: Koi option {MAX_OPTION_LEN} characters se zyada lamba hai (Telegram limit).",
}


def split_into_blocks(full_text: str) -> list[str]:
    full_text = full_text.replace("\r\n", "\n").replace("\r", "\n")
    raw_blocks = re.split(r"\n\s*\n", full_text.strip())
    return [b.strip() for b in raw_blocks if b.strip()]


def parse_block(block: str) -> dict:
    lines = block.splitlines()
    non_empty_lines = [l.strip() for l in lines if l.strip()]

    if not non_empty_lines:
        return {"ok": False, "error_code": "MISSING_QUESTION", "raw": block}

    question = non_empty_lines[0]
    if not question:
        return {"ok": False, "error_code": "MISSING_QUESTION", "raw": block}

    if len(question) > MAX_QUESTION_LEN:
        return {"ok": False, "error_code": "QUESTION_TOO_LONG", "raw": block}

    if len(non_empty_lines) < 5:
        return {"ok": False, "error_code": "TOO_FEW_OPTIONS", "raw": block}

    raw_options = non_empty_lines[1:5]

    explanation = ""
    if len(non_empty_lines) > 5:
        explanation_lines = non_empty_lines[5:]
        explanation = "\n".join(explanation_lines).strip()

    prefix_pattern = re.compile(r"^[A-Za-z0-9]{1,2}[).]\s*")
    options = []
    correct_indices = []

    for i, opt_raw in enumerate(raw_options):
        opt_text = prefix_pattern.sub("", opt_raw).strip()
        if not opt_text:
            opt_text = opt_raw.strip()

        is_correct = opt_text.endswith("*")
        if is_correct:
            opt_text = opt_text[:-1].strip()
            correct_indices.append(i)

        if len(opt_text) > MAX_OPTION_LEN:
            return {"ok": False, "error_code": "OPTION_TOO_LONG", "raw": block}
        options.append(opt_text)

    if len(correct_indices) == 0:
        return {"ok": False, "error_code": "NO_CORRECT_OPTION", "raw": block}
    if len(correct_indices) > 1:
        return {"ok": False, "error_code": "MULTIPLE_CORRECT_OPTIONS", "raw": block}

    return {
        "ok": True,
        "question": question,
        "options": options,
        "correct_index": correct_indices[0],
        "explanation": explanation,
    }


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    private_chat_id = update.effective_chat.id

    text = update.message.text or ""
    if not text.strip():
        return

    blocks = split_into_blocks(text)
    if not blocks:
        await update.message.reply_text("⚠️ Koi content nahi mila.")
        return

    success_count = 0
    error_count = 0
    total = len(blocks)

    for idx, block in enumerate(blocks):
        result = parse_block(block)

        if result["ok"]:
            try:
                # 1. Poll bhejna (Timeout limits badha di hain)
                await context.bot.send_poll(
                    chat_id=TARGET_GROUP_ID,
                    question=result["question"],
                    options=result["options"],
                    type="quiz",
                    correct_option_id=result["correct_index"],
                    is_anonymous=False,
                    connect_timeout=20.0,  # Connection ke liye 20s wait karega
                    read_timeout=20.0       # Response read karne ke liye 20s wait karega
                )
                
                # 2. Explanation message bhejna (Agar ho)
                if result["explanation"]:
                    spoiler_text = f"💡 <b>Explanation:</b>\n<span class=\"tg-spoiler\">{result['explanation']}</span>"
                    
                    await context.bot.send_message(
                        chat_id=TARGET_GROUP_ID,
                        text=spoiler_text,
                        parse_mode=ParseMode.HTML,
                        connect_timeout=20.0,
                        read_timeout=20.0
                    )
                
                success_count += 1

                # Agar bulk message hai (1 se zyada poll), toh har poll ke baad thoda delay do
                if total > 1 and idx < (total - 1):
                    await asyncio.sleep(2.0)  # 2 seconds ka break taaki timeout/flood error na aaye

            except Exception as e:
                error_text = (
                    f"❌ ERROR [TELEGRAM_API_ERROR]: Group mein content send karte waqt error aaya.\n"
                    f"Detail: {e}"
                )
                await context.bot.send_message(chat_id=private_chat_id, text=error_text)
                await context.bot.send_message(chat_id=private_chat_id, text=block)
                error_count += 1
        else:
            error_msg = ERROR_MESSAGES.get(
                result["error_code"],
                f"❌ ERROR [{result['error_code']}]: Unknown error.",
            )
            error_headline = f"{error_msg}\n\n📋 Niche diye gaye galat block ko copy karke fix karein:"
            
            await context.bot.send_message(chat_id=private_chat_id, text=error_headline)
            await context.bot.send_message(chat_id=private_chat_id, text=result["raw"])
            error_count += 1

    # ── Summary ───────────────────────────────────────────────────────────
    if total > 1:
        summary = (
            f"✅ {success_count}/{total} polls successfully group mein post ho gaye.\n"
            f"❌ {error_count}/{total} mein errors hain -- upar private chat mein dekho."
            if error_count
            else f"✅ Saare {total} polls successfully group mein post ho gaye!"
        )
        await context.bot.send_message(chat_id=private_chat_id, text=summary)

    if error_count == 0:
        try:
            await update.message.delete()
        except Exception:
            pass


def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN set nahi hai!")

    # Application builder mein bhi defaults timeout set kar sakte hain backup ke liye
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ Bot chal raha hai (Timeout fixes apply kar diye hain)...")
    app.run_polling()


if __name__ == "__main__":
    main()
