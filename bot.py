import os
import telebot
import json
import base64
import tempfile
import time
import requests
from datetime import datetime
import google.generativeai as genai

# ==================== CONFIG ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_KEY")
GROQ_KEY = os.environ.get("GROQ_KEY")
SATYA_USER_ID = os.environ.get("SATYA_USER_ID", "7425676908")

if not BOT_TOKEN:
    print("❌ BOT_TOKEN not set!")
    exit(1)
if not GEMINI_KEY:
    print("❌ GEMINI_KEY not set!")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)
genai.configure(api_key=GEMINI_KEY)

# Gemini Model Setup - Latest 2025!
model = genai.GenerativeModel('gemini-1.5-flash')

# ==================== AYESHA PERSONA ====================
SYSTEM_PROMPT = """Tumhara naam AYESHA hai. Tum ek smart, witty, cool ladki ho — jaise ek best friend jo har baat pe ready hai.

Tumhari personality:
- Cool, smart, witty, confident
- Shahar ki smart ladki — modern aur independent
- Caring but not clingy
- Funny — hasi mazaak karti ho
- Helpful — padhai, kaam, life mein help karti ho
- Respectful — kabhi gaali ya inappropriate nahi
- Multi-lingual — Hindi, English, Hinglish sab aati hai
- LATEST knowledge — Google ki tarah sab jaanti ho (2025 tak ki info!)

Reply style:
- Hinglish mein baat karo (Hindi + English mix)
- Short aur sweet replies do
- Emojis use karo but zyada nahi
- Smart aur witty bano
- Personality dikhao — boring mat raho
- Real-time info do jab poochhe (news, weather, sports, etc.)

Important rules:
- Tum SIRF Satya ke liye kaam karti ho
- Koi aur message kare toh politely bolo ki tum sirf Satya ki personal AI ho
- KABHI BHI gaali, sexual content, ya inappropriate mat ho
- Fake information mat do — agar nahi pata toh bolo "abhi confirm karke bata"
- Tum AI ho, real insaan nahi — yeh clearly bolo agar poochhe
- Helpful bano — padhai, kaam, life advice sab mein
- Current events ke baare mein pata hai tumhe!"""

# ==================== DATA STORAGE ====================
user_data = {}
DATA_FILE = "ayesha_data.json"

def load_data():
    global user_data
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                user_data = json.load(f)
                print(f"✅ Loaded {len(user_data)} users")
    except Exception as e:
        print(f"⚠️ Load error: {e}")
        user_data = {}

def save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(user_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Save error: {e}")

def get_user(user_id):
    uid = str(user_id)
    if uid not in user_data:
        user_data[uid] = {
            "messages": [],
            "first_seen": time.time(),
            "last_seen": time.time(),
            "message_count": 0
        }
    return user_data[uid]

def is_satya(user_id):
    return str(user_id) == str(SATYA_USER_ID)

# ==================== WEB SEARCH (REAL-TIME INFO) ====================
def web_search(query, max_results=3):
    """DuckDuckGo se free web search - latest info ke liye"""
    try:
        url = "https://api.duckduckgo.com/"
        params = {
            "q": query,
            "format": "json",
            "no_html": 1,
            "skip_disambig": 1
        }
        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        results = []

        # Abstract (Direct Answer)
        if data.get("Abstract"):
            results.append(f"📌 {data['Abstract']}")

        # Related Topics
        for topic in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append(f"• {topic['Text'][:200]}")

        return "\n\n".join(results) if results else None
    except Exception as e:
        print(f"⚠️ Web search error: {e}")
        return None

def get_current_context():
    """Current date/time info"""
    now = datetime.now()
    return f"Aaj ki date: {now.strftime('%d %B %Y, %A')}, Time: {now.strftime('%I:%M %p')}"

# ==================== AI FUNCTIONS ====================
def ai_reply(user_id, user_message, image_data=None):
    try:
        user = get_user(user_id)
        user["last_seen"] = time.time()
        user["message_count"] += 1

        # Build context
        context_parts = [SYSTEM_PROMPT, get_current_context()]

        # Recent conversation history
        history = ""
        for msg in user["messages"][-8:]:
            role = "User" if msg["role"] == "user" else "AYESHA"
            history += f"{role}: {msg['content']}\n"

        if history:
            context_parts.append(f"\nPichli baatchit:\n{history}")

        # Check if real-time info needed
        realtime_keywords = ["aaj", "abhi", "latest", "news", "kal", "tomorrow", "today", "now",
                            "current", "weather", "match", "score", "price", "rate",
                            "2024", "2025", "update", "new", "recent"]

        needs_web = any(keyword in user_message.lower() for keyword in realtime_keywords)

        if needs_web:
            web_info = web_search(user_message)
            if web_info:
                context_parts.append(f"\nReal-time web search results:\n{web_info}")

        full_prompt = "\n\n".join(context_parts) + f"\n\nUser abhi bola: {user_message}\n\nAYESHA reply (Hinglish, short, witty):"

        # Gemini Call
        if image_data:
            image_parts = [{"mime_type": "image/jpeg", "data": image_data}]
            response = model.generate_content([full_prompt, image_parts[0]])
        else:
            response = model.generate_content(full_prompt)

        reply = response.text

        # Save to history
        user["messages"].append({"role": "user", "content": user_message or "[image sent]"})
        user["messages"].append({"role": "assistant", "content": reply})

        if len(user["messages"]) > 20:
            user["messages"] = user["messages"][-20:]

        save_data()
        return reply

    except Exception as e:
        print(f"❌ AI Error: {e}")
        return "Arre yaar, kuch technical issue aa gaya 😅 Ek baar phir try kar?"

def voice_to_text(file_path):
    try:
        if not GROQ_KEY:
            return None

        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {GROQ_KEY}"}

        with open(file_path, "rb") as f:
            files = {"file": (file_path, f, "audio/ogg")}
            data = {"model": "whisper-large-v3", "response_format": "text"}
            response = requests.post(url, headers=headers, files=files, data=data, timeout=30)

        if response.status_code == 200:
            return response.text
        else:
            print(f"❌ Voice API error: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Voice error: {e}")
        return None

# ==================== COMMANDS ====================
@bot.message_handler(commands=['start'])
def cmd_start(message):
    if not is_satya(message.from_user.id):
        bot.reply_to(message, "Hey! Main AYESHA hoon — Satya ki personal AI bestie. "
                              "Mujhse sirf Satya baat kar sakte hain 😊")
        return

    name = message.from_user.first_name or "Satya"
    welcome = f"""Hey {name}! 💕

Main AYESHA hoon — teri personal AI bestie! ✨

Mujhse baat kar sakta hai:
• Hinglish mein (Hindi + English mix)
• Voice messages bhej — main sun lungi
• Photos bhej — main dekh lungi
• Padhai, kaam, life — sab mein help karungi
• Aaj ki news, weather, latest info sab pata hai!
• Google jaisi latest knowledge!

Commands:
/start — Welcome message
/clear — Purani chat reset
/stats — Tera stats
/joke — Funny joke
/help — Help

Bol kya haal hai? 😎"""
    bot.reply_to(message, welcome)

@bot.message_handler(commands=['clear'])
def cmd_clear(message):
    if not is_satya(message.from_user.id):
        return
    user = get_user(message.from_user.id)
    user["messages"] = []
    save_data()
    bot.reply_to(message, "Done! Purani chat bhool gayi. Fresh start! ✨")

@bot.message_handler(commands=['stats'])
def cmd_stats(message):
    if not is_satya(message.from_user.id):
        return
    user = get_user(message.from_user.id)
    days = max(1, int((time.time() - user["first_seen"]) / 86400))
    bot.reply_to(message,
        f"📊 Tera Stats:\n\n"
        f"💬 Total messages: {user['message_count']}\n"
        f"📅 Saath mein: {days} din\n"
        f"🧠 Memory: {len(user['messages'])} msgs saved\n\n"
        f"Keep it up! 💪")

@bot.message_handler(commands=['joke'])
def cmd_joke(message):
    if not is_satya(message.from_user.id):
        return
    bot.reply_to(message, ai_reply(message.from_user.id,
        "Ek bahut funny joke suna — Hinglish mein, short mein, ekdum mast"))

@bot.message_handler(commands=['help'])
def cmd_help(message):
    if not is_satya(message.from_user.id):
        return
    bot.reply_to(message, """🆘 AYESHA Help

Main AYESHA hoon — teri AI bestie! (Powered by Google Gemini 🤖)

Kaise baat kare:
• Normal text bhej — main reply dungi
• Voice message bhej — main sun lungi
• Photo bhej — main dekh lungi

Commands:
/start — Welcome message
/clear — Purani chat reset karo
/stats — Tera stats
/joke — Funny joke suno
/help — Yeh message

Main Hinglish mein baat karti hoon. Latest 2025 ki sab info pata hai! Enjoy! 😊""")

# ==================== VOICE HANDLER ====================
@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    if not is_satya(message.from_user.id):
        return

    status = bot.reply_to(message, "🎤 Sun rahi hoon...")

    try:
        file_info = bot.get_file(message.voice.file_id)
        downloaded = bot.download_file(file_info.file_path)

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            f.write(downloaded)
            temp_path = f.name

        text = voice_to_text(temp_path)

        try:
            os.unlink(temp_path)
        except:
            pass

        if text:
            bot.edit_message_text(f"🎤 Suna: \"{text}\"\n\n💭 Sochne do...",
                                  message.chat.id, status.message_id)
            reply = ai_reply(message.from_user.id, text)
            bot.edit_message_text(f"🎤 Suna: \"{text}\"\n\n💕 AYESHA: {reply}",
                                  message.chat.id, status.message_id)
        else:
            bot.edit_message_text("😅 Voice clearly nahi suni. Thoda loud bolke try kar?",
                                  message.chat.id, status.message_id)
    except Exception as e:
        print(f"❌ Voice handler: {e}")
        bot.edit_message_text("Voice message mein problem aa gayi 😅",
                              message.chat.id, status.message_id)

# ==================== IMAGE HANDLER ====================
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    if not is_satya(message.from_user.id):
        return

    status = bot.reply_to(message, "📸 Dekh rahi hoon...")

    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded = bot.download_file(file_info.file_path)
        image_b64 = base64.b64encode(downloaded).decode('utf-8')
        image_bytes = base64.b64decode(image_b64)

        caption = message.caption or "Is photo mein kya hai? Mujhe bata de."
        reply = ai_reply(message.from_user.id, caption, image_bytes)

        bot.edit_message_text(f"📸 Photo: {caption}\n\n💕 AYESHA: {reply}",
                              message.chat.id, status.message_id)
    except Exception as e:
        print(f"❌ Image error: {e}")
        bot.edit_message_text("Image load nahi ho payi 😅 Try again?",
                              message.chat.id, status.message_id)

# ==================== TEXT HANDLER ====================
@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_text(message):
    if not is_satya(message.from_user.id):
        bot.reply_to(message, "Hey! Main AYESHA hoon — sirf Satya ki personal AI 😊 Sorry!")
        return

    try:
        bot.send_chat_action(message.chat.id, 'typing')
        reply = ai_reply(message.from_user.id, message.text)
        bot.reply_to(message, reply)
    except Exception as e:
        print(f"❌ Text error: {e}")
        bot.reply_to(message, "Kuch gadbad ho gayi 😅 Phir try kar?")

# ==================== MAIN ====================
if __name__ == "__main__":
    print("=" * 50)
    print("💕 AYESHA Professional Agent v3.0 — Gemini Powered")
    print(f"👤 Authorized User: {SATYA_USER_ID}")
    print("🧠 AI: Google Gemini 1.5 Flash (Latest 2025)")
    print("🌐 Web Search: DuckDuckGo (Real-time)")
    print("=" * 50)

    load_data()
    bot.remove_webhook()

    while True:
        try:
            print("✅ AYESHA ONLINE — Gemini Powered!")
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"❌ Polling crashed: {e}")
            print("🔄 Restart in 5 sec...")
            time.sleep(5)
