import os
import re
import logging
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = "7903545339:AAFzleTOLJOJPiEhCtf79L3fQJtkL9b46XQ"
ALLOWED_CHAT_ID = 0

# ─── Telegram Limits ────────────────────────────────────────────────────────
MAX_QUESTION_LEN = 300
MAX_OPTION_LEN = 100
FIXED_OPTIONS = 4

# ─── Error Codes & Messages ──────────────────────────────────────────────────
ERROR_MESSAGES = {
    "MISSING_QUESTION": "\u274c ERROR [MISSING_QUESTION]: Pehli line empty hai -- question likho.",
    "TOO_FEW_OPTIONS": "\u274c ERROR [TOO_FEW_OPTIONS]: Exactly 4 options hone chahiye (lines 2-5).",
    "NO_CORRECT_OPTION": "\u274c ERROR [NO_CORRECT_OPTION]: Kisi bhi option mein * nahi lagaya. Sahi answer ke option ke end mein * lagao. Jaise: Delhi*",
    "MULTIPLE_CORRECT_OPTIONS": "\u274c ERROR [MULTIPLE_CORRECT_OPTIONS]: Ek se zyada options mein * laga hai. Sirf ek sahi answer hona chahiye.",
    "MISSING_EXPLANATION": "\u274c ERROR [MISSING_EXPLANATION]: Explanation compulsory hai. 4 options ke baad explanation likhna zaroori hai.",
    "QUESTION_TOO_LONG": f"\u274c ERROR [QUESTION_TOO_LONG]: Question {MAX_QUESTION_LEN} characters se zyada lamba hai (Telegram limit).",
    "OPTION_TOO_LONG": f"\u274c ERROR [OPTION_TOO_LONG]: Koi option {MAX_OPTION_LEN} characters se zyada lamba hai (Telegram limit).",
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

    if len(non_empty_lines) < 6:
        if len(non_empty_lines) < 5:
            return {"ok": False, "error_code": "TOO_FEW_OPTIONS", "raw": block}
        else:
            return {"ok": False, "error_code": "MISSING_EXPLANATION", "raw": block}

    raw_options = non_empty_lines[1:5]

    explanation_lines = non_empty_lines[5:]
    explanation = "\n".join(explanation_lines).strip()
    
    if not explanation:
        return {"ok": False, "error_code": "MISSING_EXPLANATION", "raw": block}

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
    chat_id = update.effective_chat.id

    text = update.message.text or ""
    if not text.strip():
        return

    blocks = split_into_blocks(text)
    if not blocks:
        await update.message.reply_text("\u26a0 Koi content nahi mila.")
        return

    success_count = 0
    error_count = 0

    for block in blocks:
        result = parse_block(block)

        if result["ok"]:
            try:
                # 1. Poll send karenge
                await context.bot.send_poll(
                    chat_id=chat_id,
                    question=result["question"],
                    options=result["options"],
                    type="quiz",
                    correct_option_id=result["correct_index"],
                    is_anonymous=False,
                )
                
                # 2. Explanation as a true MarkdownV2 Spoiler send karenge
                # MarkdownV2 me characters escape karne padte hain, isliye seedhe text ke sath || use karenge
                spoiler_text = f"\U0001f4a1 *Explanation:*\n||{result['explanation']}||"
                
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=spoiler_text,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                
                success_count += 1
            except Exception as e:
                error_text = (
                    f"\u274c ERROR [TELEGRAM_API_ERROR]: Poll/Explanation send karte waqt error aaya.\n"
                    f"Detail: {e}"
                )
                await update.message.reply_text(error_text)
                await update.message.reply_text(block)
                error_count += 1
        else:
            error_msg = ERROR_MESSAGES.get(
                result["error_code"],
                f"\u274c ERROR [{result['error_code']}]: Unknown error.",
            )
            error_headline = f"{error_msg}\n\n\U0001f4cb Niche diye gaye galat block ko copy karke fix karein:"
            await update.message.reply_text(error_headline)
            await update.message.reply_text(result["raw"])
            error_count += 1

    # ── Summary ───────────────────────────────────────────────────────────
    total = len(blocks)
    if total > 1:
        summary = (
            f"\u2705 {success_count}/{total} polls successfully bane.\n"
            f"\u274c {error_count}/{total} mein errors hain -- upar dekho."
            if error_count
            else f"\u2705 Saare {total} polls successfully bane!"
        )
        await update.message.reply_text(summary)

    if error_count == 0:
        try:
            await update.message.delete()
        except Exception:
            pass


def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN set nahi hai!")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("\u2705 Bot chal raha hai...")
    app.run_polling()


if __name__ == "__main__":
    main()
              
