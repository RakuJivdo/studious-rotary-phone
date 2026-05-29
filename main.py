import os
import re
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ALLOWED_CHAT_ID = int(os.environ.get("ALLOWED_CHAT_ID", "0"))

─── Telegram Limits ────────────────────────────────────────────────────────
MAX_QUESTION_LEN = 300
MAX_OPTION_LEN = 100
MAX_EXPLANATION_LEN = 200
FIXED_OPTIONS = 4

─── Error Codes & Messages ──────────────────────────────────────────────────
Emojis written as unicode escapes for maximum platform compatibility
\u274c = ❌ \u26a0 = ⚠️ \u2705 = ✅ \U0001f4cb = 📋
ERROR_MESSAGES = {
"MISSING_QUESTION": "\u274c ERROR [MISSING_QUESTION]: Pehli line empty hai -- question likho.",
"TOO_FEW_OPTIONS": "\u274c ERROR [TOO_FEW_OPTIONS]: Exactly 4 options hone chahiye (lines 2-5).",
"TOO_MANY_OPTIONS": "\u274c ERROR [TOO_MANY_OPTIONS]: Exactly 4 options hone chahiye (lines 2-5).",
"NO_CORRECT_OPTION": "\u274c ERROR [NO_CORRECT_OPTION]: Kisi bhi option mein * nahi lagaya. Sahi answer ke option ke end mein * lagao. Jaise: Delhi*",
"MULTIPLE_CORRECT_OPTIONS":"\u274c ERROR [MULTIPLE_CORRECT_OPTIONS]: Ek se zyada options mein * laga hai. Sirf ek sahi answer hona chahiye.",
"MISSING_EXPLANATION": "\u274c ERROR [MISSING_EXPLANATION]: Explanation compulsory hai. 4 options ke baad explanation likhna zaroori hai.",
"QUESTION_TOO_LONG": f"\u274c ERROR [QUESTION_TOO_LONG]: Question {MAX_QUESTION_LEN} characters se zyada lamba hai (Telegram limit).",
"OPTION_TOO_LONG": f"\u274c ERROR [OPTION_TOO_LONG]: Koi option {MAX_OPTION_LEN} characters se zyada lamba hai (Telegram limit).",
"EXPLANATION_TOO_LONG": f"\u274c ERROR [EXPLANATION_TOO_LONG]: Explanation {MAX_EXPLANATION_LEN} characters se zyada lambi hai (Telegram limit).",
}


def split_into_blocks(full_text: str) -> list[str]:
"""
Split the incoming message into question blocks.
Blocks are separated by one or more blank lines.
"""
# Normalize line endings
full_text = full_text.replace("\r\n", "\n").replace("\r", "\n")

# Split on blank lines (one or more)
raw_blocks = re.split(r'\n\s*\n', full_text.strip())

# Filter empty blocks
blocks = [b.strip() for b in raw_blocks if b.strip()]
return blocks


def parse_block(block: str) -> dict:
"""
Strict format:
Line 1 -> Question
Lines 2-5 -> Exactly 4 options (any prefix or no prefix, position-based)
Line 6 onward -> Explanation (compulsory, can be multiline within the block)

Correct answer marked with * at the END of the option text.

Returns a dict with either:
{"ok": True, "question": ..., "options": [...], "correct_index": int, "explanation": ...}
{"ok": False, "error_code": ..., "raw": original block text}
"""
lines = block.splitlines()
non_empty_lines = [l.strip() for l in lines if l.strip()]

if not non_empty_lines:
return {"ok": False, "error_code": "MISSING_QUESTION", "raw": block}

# ── Line 1: Question ──────────────────────────────────────────────────
question = non_empty_lines[0]
if not question:
return {"ok": False, "error_code": "MISSING_QUESTION", "raw": block}

if len(question) > MAX_QUESTION_LEN:
return {"ok": False, "error_code": "QUESTION_TOO_LONG", "raw": block}

# ── Need at least 6 non-empty lines: 1 question + 4 options + 1 explanation
if len(non_empty_lines) < 6:
# Figure out a more specific error
if len(non_empty_lines) < 2:
return {"ok": False, "error_code": "TOO_FEW_OPTIONS", "raw": block}
if len(non_empty_lines) <= 5:
# Could be missing options or missing explanation
options_present = len(non_empty_lines) - 1 # subtract question line
if options_present < FIXED_OPTIONS:
return {"ok": False, "error_code": "TOO_FEW_OPTIONS", "raw": block}
else:
return {"ok": False, "error_code": "MISSING_EXPLANATION", "raw": block}

# ── Lines 2-5: Exactly 4 options (position-based) ─────────────────────
raw_options = non_empty_lines[1:5]

if len(raw_options) < FIXED_OPTIONS:
return {"ok": False, "error_code": "TOO_FEW_OPTIONS", "raw": block}

# ── Lines 6+: Explanation ─────────────────────────────────────────────
explanation_lines = non_empty_lines[5:]
if not explanation_lines:
return {"ok": False, "error_code": "MISSING_EXPLANATION", "raw": block}

explanation = " ".join(explanation_lines).strip()
if not explanation:
return {"ok": False, "error_code": "MISSING_EXPLANATION", "raw": block}

if len(explanation) > MAX_EXPLANATION_LEN:
return {"ok": False, "error_code": "EXPLANATION_TOO_LONG", "raw": block}

# ── Parse each option — strip any leading prefix like A) a) 1) etc. ───
# A prefix is: optional letter/number followed by ) or . and a space
prefix_pattern = re.compile(r'^[A-Za-z0-9]{1,2}[).]\s*')

options = []
correct_indices = []

for i, opt_raw in enumerate(raw_options):
# Strip prefix if present
opt_text = prefix_pattern.sub("", opt_raw).strip()

# If stripping ate the whole string, keep original (no prefix was there)
if not opt_text:
opt_text = opt_raw.strip()

is_correct = opt_text.endswith("*")
if is_correct:
opt_text = opt_text[:-1].strip()
correct_indices.append(i)

if len(opt_text) > MAX_OPTION_LEN:
return {"ok": False, "error_code": "OPTION_TOO_LONG", "raw": block}

options.append(opt_text)

# ── Validate correct answer ───────────────────────────────────────────
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

if ALLOWED_CHAT_ID and chat_id != ALLOWED_CHAT_ID:
return

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
# ── Send as quiz poll ─────────────────────────────────────────
try:
await context.bot.send_poll(
chat_id=chat_id,
question=result["question"],
options=result["options"],
type="quiz",
correct_option_id=result["correct_index"],
explanation=result["explanation"],
is_anonymous=False,
)
success_count += 1
except Exception as e:
# Telegram API se koi unexpected error aaya
error_text = (
f"\u274c ERROR [TELEGRAM_API_ERROR]: Poll send karte waqt error aaya.\n"
f"Detail: {e}\n\n"
f"\U0001f4cb Original block:\n{block}"
)
await update.message.reply_text(error_text)
error_count += 1
else:
# ── Send error report + original block ────────────────────────
error_msg = ERROR_MESSAGES.get(
result["error_code"],
f"\u274c ERROR [{result['error_code']}]: Unknown error."
)
error_report = f"{error_msg}\n\n\U0001f4cb Galat block (copy karke fix karo):\n\n{result['raw']}\n"
await update.message.reply_text(error_report, parse_mode="Markdown")
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

# Delete original message only if ALL were successful
if error_count == 0:
try:
await update.message.delete()
except Exception:
pass


def main():
if not BOT_TOKEN:
raise ValueError("BOT_TOKEN environment variable set nahi hai!")

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
print("\u2705 Bot chal raha hai...")
app.run_polling()


if name == "main":
main()
