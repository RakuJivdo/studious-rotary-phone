import time
import requests

# ─── CONFIGURATION ──────────────────────────────────────────────────────────
# Aapka naya Token yahan daal diya hai
BOT_TOKEN = "7903545339:AAFzleTOLJOJPiEhCtf79L3fQJtkL9b46XQ"
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ─── LIMITS & ERROR MESSAGES ──────────────────────────────────────────────────
MAX_QUESTION_LEN = 300
MAX_OPTION_LEN = 100
MAX_EXPLANATION_LEN = 200

ERROR_MESSAGES = {
    "MISSING_QUESTION": "❌ ERROR: Pehli line khali hai -- sawaal likho.",
    "TOO_FEW_OPTIONS": "❌ ERROR: Exactly 4 options hone chahiye.",
    "TOO_MANY_OPTIONS": "❌ ERROR: Exactly 4 options hone chahiye.",
    "NO_CORRECT_OPTION": "❌ ERROR: Kisi bhi option ke aage * nahi lagaya. Sahi answer ke end mein * lagao (e.g., Delhi*).",
    "MULTIPLE_CORRECT_OPTIONS": "❌ ERROR: Ek se zyada options mein * laga hai. Sirf ek hi sahi answer hona chahiye.",
    "MISSING_EXPLANATION": "❌ ERROR: Explanation compulsory hai. 4 options ke baad explanation zaroori hai.",
    "QUESTION_TOO_LONG": f"❌ ERROR: Question {MAX_QUESTION_LEN} characters se bada hai.",
    "OPTION_TOO_LONG": f"❌ ERROR: Koi option {MAX_OPTION_LEN} characters se bada hai.",
    "EXPLANATION_TOO_LONG": f"❌ ERROR: Explanation {MAX_EXPLANATION_LEN} characters se badi hai."
}

# ─── HELPER FUNCTIONS ────────────────────────────────────────────────────────
def delete_webhook():
    """Google Script ka purana webhook hatane ke liye taaki Python sahi se chale"""
    try:
        requests.get(f"{TELEGRAM_API}/deleteWebhook")
    except Exception:
        pass

def send_message(chat_id, text, reply_to_id=None, parse_mode=None):
    url = f"{TELEGRAM_API}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if reply_to_id:
        payload["reply_to_message_id"] = reply_to_id
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Message bhejne mein error: {e}")

def delete_message(chat_id, message_id):
    url = f"{TELEGRAM_API}/deleteMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "message_id": message_id})
    except Exception:
        pass

def send_poll(chat_id, data, original_msg_id, raw_block):
    url = f"{TELEGRAM_API}/sendPoll"
    payload = {
        "chat_id": chat_id,
        "question": data["question"],
        "options": data["options"],
        "type": "quiz",
        "correct_option_id": data["correct_index"],
        "explanation": data["explanation"],
        "is_anonymous": False
    }
    try:
        res = requests.post(url, json=payload).json()
        if res.get("ok"):
            return True
        else:
            err_desc = res.get("description", "Unknown Telegram Error")
            err_text = f"❌ ERROR [TELEGRAM_API_ERROR]: Poll send nahi hua.\nDetail: {err_desc}\n\n📋 Original text:\n{raw_block}"
            send_message(chat_id, err_text, original_msg_id)
            return False
    except Exception as e:
        print(f"Poll request failed: {e}")
        return False

def parse_block(block):
    lines = [l.strip() for l in block.split("\n") if l.strip()]
    if not lines:
        return {"ok": False, "error_code": "MISSING_QUESTION", "raw": block}

    question = lines[0]
    if len(question) > MAX_QUESTION_LEN:
        return {"ok": False, "error_code": "QUESTION_TOO_LONG", "raw": block}

    if len(lines) < 6:
        if len(lines) < 2:
            return {"ok": False, "error_code": "TOO_FEW_OPTIONS", "raw": block}
        if len(lines) <= 5:
            return {"ok": False, "error_code": "MISSING_EXPLANATION", "raw": block}

    raw_options = lines[1:5]
    explanation_lines = lines[5:]
    explanation = " ".join(explanation_lines).strip()

    if not explanation:
        return {"ok": False, "error_code": "MISSING_EXPLANATION", "raw": block}
    if len(explanation) > MAX_EXPLANATION_LEN:
        return {"ok": False, "error_code": "EXPLANATION_TOO_LONG", "raw": block}

    options = []
    correct_indices = []

    for i, opt_raw in enumerate(raw_options):
        # Prefix hatane ke liye (A. ya 1))
        import re
        opt_text = re.sub(r'^[A-Za-z0-9]{1,2}[).]\s*', '', opt_raw).strip()
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
        "explanation": explanation
    }

def handle_message(message):
    text = message.get("text", "").strip()
    if not text:
        return

    chat_id = message["chat"]["id"]
    msg_id = message["message_id"]

    # Blocks mein todna (Double enter check)
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    raw_blocks = [b.strip() for b in normalized.split("\n\s*\n") if b.strip()]
    
    # Agar regex split issue kare toh simple fallback split
    if len(raw_blocks) <= 1:
        raw_blocks = [b.strip() for b in normalized.split("\n\n") if b.strip()]

    if not raw_blocks:
        return

    success_count = 0
    error_count = 0

    for block in raw_blocks:
        result = parse_block(block)
        if result["ok"]:
            if send_poll(chat_id, result, msg_id, block):
                success_count += 1
            else:
                error_count += 1
        else:
            err_msg = ERROR_MESSAGES.get(result["error_code"], "Unknown Error")
            error_report = f"{err_msg}\n\n📋 Galat block:\n\n{result['raw']}"
            send_message(chat_id, error_report, msg_id)
            error_count += 1

    total = len(raw_blocks)
    if total > 1:
        summary = f"✅ {success_count}/{total} polls bane.\n❌ {error_count}/{total} errors hain." if error_count > 0 else f"✅ Saare {total} polls kamyabi se ban gaye!"
        send_message(chat_id, summary, msg_id)

    if error_count == 0:
        delete_message(chat_id, msg_id)

# ─── MAIN POLLING LOOP ────────────────────────────────────────────────────────
def main():
    print("Bot starting... Purana Webhook delete ho raha hai...")
    delete_webhook()
    print("Bot live hai! Telegram par message bhej kar check karein.")
    
    offset = 0
    while True:
        try:
            url = f"{TELEGRAM_API}/getUpdates?offset={offset}&timeout=30"
            response = requests.get(url).json()
            
            if response.get("ok") and response.get("result"):
                for update in response["result"]:
                    offset = update["update_id"] + 1
                    if "message" in update:
                        handle_message(update["message"])
        except Exception as e:
            print(f"Loop error: {e}")
        time.sleep(1)

if __name__ == "__main__":
    main()
