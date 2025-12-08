import os
import requests
import random
import string
import asyncio
import json
from datetime import datetime
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

app = Flask(__name__)
TOKEN = os.environ.get("TOKEN")

# Admin ID
try:
    ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
except ValueError:
    ADMIN_ID = 0

# --- JSONBin Configuration ---
JSONBIN_ID = os.environ.get("JSONBIN_ID")
JSONBIN_KEY = os.environ.get("JSONBIN_KEY")
JSONBIN_URL = f"https://api.jsonbin.io/v3/b/{JSONBIN_ID}"
HEADERS = {
    "X-Master-Key": JSONBIN_KEY,
    "Content-Type": "application/json"
}

# --- Database Functions ---
def get_db():
    """ዳታቤዙን ያመጣል (Default structure ካልኖረ ይፈጥራል)"""
    default_db = {"users": [], "channel": None, "daily": {"date": "", "active": []}}
    
    if not JSONBIN_ID or not JSONBIN_KEY: return default_db
    
    try:
        resp = requests.get(JSONBIN_URL, headers=HEADERS)
        if resp.status_code == 200:
            data = resp.json().get("record", {})
            # የጎደለ ነገር ካለ እንሙላ (Migration)
            if "users" not in data: data["users"] = []
            if "channel" not in data: data["channel"] = None
            if "daily" not in data: data["daily"] = {"date": "", "active": []}
            return data
    except: pass
    return default_db

def update_db(data):
    """ዳታቤዙን ይዘግባል"""
    if not JSONBIN_ID or not JSONBIN_KEY: return
    try:
        requests.put(JSONBIN_URL, json=data, headers=HEADERS)
    except: pass

def track_user_activity(user_id):
    """ተጠቃሚ ሲገባ መመዝገብ (ለ Total እና Daily Stats)"""
    if not JSONBIN_ID or not JSONBIN_KEY: return
    
    # ይህ ሂደት ጊዜ ሊወስድ ስለሚችል Vercel እንዳይጨናነቅ በ try block እንያዘው
    try:
        db = get_db()
        changed = False
        
        # 1. Total Users (ጠቅላላ)
        if user_id not in db["users"]:
            db["users"].append(user_id)
            changed = True
            
        # 2. Daily Stats (የዛሬ)
        today = datetime.now().strftime("%Y-%m-%d")
        daily = db.get("daily", {"date": today, "active": []})
        
        # ቀን ከተቀየረ Reset አድርግ
        if daily.get("date") != today:
            daily = {"date": today, "active": []}
            changed = True
            
        # ዛሬ ካልተመዘገበ መዝግበው
        if user_id not in daily["active"]:
            daily["active"].append(user_id)
            changed = True
            
        db["daily"] = daily
        
        if changed:
            update_db(db)
    except:
        pass

def set_force_channel(channel):
    db = get_db()
    db["channel"] = channel
    update_db(db)

def get_force_channel():
    db = get_db()
    return db.get("channel")

def get_all_users():
    db = get_db()
    return db.get("users", [])

# --- Engines ---
TM_PROVIDERS = ["https://api.mail.gw", "https://api.mail.tm"]
GUERRILLA_API = "https://api.guerrillamail.com/ajax.php"

# ===========================
# 🛠️ Helper Functions
# ===========================
def create_tm_account():
    for base_url in TM_PROVIDERS:
        try:
            domains_resp = requests.get(f"{base_url}/domains", timeout=4)
            if domains_resp.status_code != 200: continue
            
            domain_list = domains_resp.json()['hydra:member']
            if not domain_list: continue
            
            premium = [d for d in domain_list if any(x in d['domain'] for x in ['.com', '.net', '.org'])]
            domain_obj = random.choice(premium) if premium else random.choice(domain_list)
            
            username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
            password = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
            address = f"{username}@{domain_obj['domain']}"
            
            reg = requests.post(f"{base_url}/accounts", json={"address": address, "password": password}, headers={"Content-Type": "application/json"}, timeout=4)
            if reg.status_code == 201:
                return {"type": "tm", "email": address, "password": password, "url": base_url}
        except: continue
    return None

def check_tm_mail(account):
    try:
        token_resp = requests.post(f"{account['url']}/token", json={"address": account['email'], "password": account['password']}, headers={"Content-Type": "application/json"}, timeout=5)
        if token_resp.status_code != 200: return []
        token = token_resp.json()['token']
        
        msg_resp = requests.get(f"{account['url']}/messages?page=1", headers={"Authorization": f"Bearer {token}"}, timeout=5)
        if msg_resp.status_code != 200: return []
        messages = msg_resp.json()['hydra:member']
        
        results = []
        for msg in messages:
            content_resp = requests.get(f"{account['url']}/messages/{msg['id']}", headers={"Authorization": f"Bearer {token}"}, timeout=5)
            if content_resp.status_code == 200:
                full = content_resp.json()
                results.append({
                    "from": full.get('from', {}).get('address', 'Unknown'),
                    "subject": full.get('subject', 'No Subject'),
                    "body": full.get('text', '') or full.get('intro', 'No Content')
                })
        return results
    except: return []

def create_guerrilla_account():
    try:
        resp = requests.get(f"{GUERRILLA_API}?f=get_email_address", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return {"type": "gr", "email": data['email_addr'], "sid": data['sid_token']}
    except: pass
    return None

def check_guerrilla_mail(account):
    try:
        cookies = {"PHPSESSID": account['sid']}
        resp = requests.get(f"{GUERRILLA_API}?f=get_email_list&offset=0&seq=0", cookies=cookies, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            results = []
            for msg in data.get('list', []):
                if msg['mail_subject'].startswith("Welcome"): continue
                results.append({"from": msg['mail_from'], "subject": msg['mail_subject'], "body": msg['mail_excerpt']})
            return results
    except: pass
    return []

# ===========================
# 🔐 Force Join Logic
# ===========================
async def check_subscription(user_id, bot):
    force_channel = get_force_channel()
    if not force_channel: return True
    try:
        member = await bot.get_chat_member(chat_id=force_channel, user_id=user_id)
        if member.status in ['left', 'kicked']: return False
        return True
    except: return True

async def send_force_join_message(update, context):
    force_channel = get_force_channel()
    if not force_channel: return
    keyboard = [[InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{force_channel.replace('@', '')}")], [InlineKeyboardButton("✅ Verify", callback_data='verify_join')]]
    text = "⛔ **ቦቱን ለመጠቀም መጀመሪያ ቻናላችንን ይቀላቀሉ።**"
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# ===========================
# 🤖 Telegram Logic
# ===========================

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 ID: `{update.effective_user.id}`", parse_mode='Markdown')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    track_user_activity(user_id) # 🔥 Record Stats
    
    if not await check_subscription(user_id, context.bot):
        await send_force_join_message(update, context)
        return
    await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    keyboard = [
        [InlineKeyboardButton("📩 ኢሜይል ፍጠር (Standard)", callback_data='gen_tm')],
        [InlineKeyboardButton("🔥 አማራጭ (Alternative)", callback_data='gen_gr')],
        [InlineKeyboardButton("🆘 እርዳታ (Support)", callback_data='ask_support')]
    ]
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Admin Dashboard", callback_data='admin_panel')])

    text = "👋 **Temp Mail Bot**\n\nለማንኛውም ድረገጽ እና ሶሻል ሚዲያ ምዝገባ የሚሆን ጊዜያዊ ኢሜይል ያግኙ። 👇"
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = update.effective_user.id

    if data == 'verify_join':
        track_user_activity(user_id)
        if await check_subscription(user_id, context.bot):
            await query.answer("✅ Welcome!")
            await show_main_menu(update, context)
        else:
            await query.answer("❌ Not Joined Yet!", show_alert=True)
        return

    # --- ADMIN PANEL & STATS ---
    if data == 'admin_panel':
        if user_id != ADMIN_ID: 
            await query.answer("⛔ Access Denied!", show_alert=True)
            return
        
        # 🔥 ስታቲስቲክስ ማምጣት
        db = get_db()
        total_users = len(db.get("users", []))
        
        today = datetime.now().strftime("%Y-%m-%d")
        daily_stats = db.get("daily", {})
        
        # ቀን ከተቀየረ 0 ነው፣ ካልሆነ የዛሬውን አሳይ
        if daily_stats.get("date") == today:
            daily_users = len(daily_stats.get("active", []))
        else:
            daily_users = 0
            
        channel_status = db.get("channel") if db.get("channel") else "Not Set"
        
        keyboard = [
            [InlineKeyboardButton("📢 Set Channel", callback_data='set_channel'), InlineKeyboardButton("❌ Remove Channel", callback_data='remove_channel')],
            [InlineKeyboardButton("📡 Broadcast", callback_data='start_broadcast')],
            [InlineKeyboardButton("🔙 Back", callback_data='start_menu')]
        ]
        
        stats_text = (
            f"👨‍✈️ **Admin Dashboard**\n\n"
            f"📊 **Statistics:**\n"
            f"👥 ጠቅላላ ተጠቃሚ: `{total_users}`\n"
            f"📅 የዛሬ ተጠቃሚ: `{daily_users}`\n\n"
            f"📢 Channel: `{channel_status}`"
        )
        await query.edit_message_text(stats_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return

    elif data == 'set_channel':
        if user_id != ADMIN_ID: return
        await context.bot.send_message(chat_id=user_id, text="📢 **Set Channel**\n\nቻናሉን ለዚህ Reply አድርገህ ላክ (Example: `@my_channel`)", reply_markup=ForceReply(selective=True), parse_mode='Markdown')
        return

    elif data == 'remove_channel':
        if user_id != ADMIN_ID: return
        set_force_channel(None)
        await query.answer("✅ Channel Removed!", show_alert=True)
        await show_main_menu(update, context)
        return

    elif data == 'start_broadcast':
        if user_id != ADMIN_ID: return
        await context.bot.send_message(chat_id=user_id, text="📢 **Broadcast**\n\nማስታወቂያውን ለዚህ Reply አድርገህ ላክ።", reply_markup=ForceReply(selective=True), parse_mode='Markdown')
        return

    elif data == 'ask_support':
        await context.bot.send_message(chat_id=user_id, text="🆘 **Support**\n\nችግርህን ለዚህ Reply አድርገህ ጻፍ።", reply_markup=ForceReply(selective=True), parse_mode='Markdown')
        return
        
    elif data == 'start_menu':
        await start(update, context)
        return

    # --- TEMP MAIL ---
    if not await check_subscription(user_id, context.bot):
        await send_force_join_message(update, context)
        return

    if data in ['gen_tm', 'gen_gr']:
        await query.answer("⚙️ Processing...")
        track_user_activity(user_id) # Update stats
        account = create_tm_account() if data == 'gen_tm' else create_guerrilla_account()
        
        if account:
            if account['type'] == 'tm': safe_data = f"chk|tm|{account['password']}|{account['email']}"
            else: safe_data = f"chk|gr|{account['sid']}"

            if len(safe_data.encode('utf-8')) > 64:
                 await query.edit_message_text("❌ Error. Retry.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Retry", callback_data=data)]]))
                 return

            keyboard = [[InlineKeyboardButton("📩 Inbox ፈትሽ", callback_data=safe_data)], [InlineKeyboardButton("🔙 ዋና ሜኑ", callback_data='start_menu')]]
            provider = "Standard" if account['type'] == 'tm' else "Alternative"
            await query.edit_message_text(f"✅ **ኢሜይል ተፈጥሯል!** ({provider})\n\n`{account['email']}`\n\nCopy አድርገው ይጠቀሙ።", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else: await query.answer("Server Error", show_alert=True)

    elif data.startswith('chk|'):
        parts = data.split('|')
        engine = parts[1]
        await query.answer("🔄 Inbox...")
        messages = []
        email_disp = "Unknown"
        
        if engine == 'tm':
            if len(parts) < 4: return
            for url in TM_PROVIDERS:
                res = check_tm_mail({"url": url, "email": parts[3], "password": parts[2]})
                if res: 
                    messages = res
                    email_disp = parts[3]
                    break
        elif engine == 'gr':
            messages = check_guerrilla_mail({"sid": parts[2]})
            email_disp = "Alternative"

        keyboard = [[InlineKeyboardButton("📩 Inbox ፈትሽ (Refresh)", callback_data=data)], [InlineKeyboardButton("🔙 ተመለስ", callback_data='start_menu')]]
        
        if not messages:
            try: await query.edit_message_text(f"📭 **Inbox ባዶ ነው!**\n\n`{email_disp}`\n\nእስካሁን ምንም መልእክት የለም።", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            except: pass
        else:
            msg = messages[0]
            text = f"📬 **መልእክት ገብቷል!**\n\n👤 **From:** {msg['from']}\n📌 **Subject:** {msg['subject']}\n\n{msg['body'][:3000]}"
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = update.message
    track_user_activity(user_id) # Message ሲልክም እንቁጠረው
    
    if msg.reply_to_message and msg.reply_to_message.from_user.is_bot:
        original = msg.reply_to_message.text
        
        if "Set Channel" in original and user_id == ADMIN_ID:
            ch = msg.text.strip()
            if not ch.startswith("@"): ch = "@" + ch
            set_force_channel(ch)
            await msg.reply_text(f"✅ Channel Set: `{ch}`")

        elif "Broadcast" in original and user_id == ADMIN_ID:
            users_list = get_all_users()
            success = 0
            if not users_list:
                await msg.reply_text("⚠️ No users found.")
                return
            status = await msg.reply_text(f"⏳ Sending to {len(users_list)} users...")
            for uid in users_list:
                if uid == ADMIN_ID: continue
                try:
                    await context.bot.copy_message(chat_id=uid, from_chat_id=user_id, message_id=msg.message_id)
                    success += 1
                except: pass
            await status.edit_text(f"✅ Broadcast Sent: {success}")
        
        elif "Support" in original:
            if ADMIN_ID:
                try:
                    await context.bot.send_message(chat_id=ADMIN_ID, text=f"🆘 **Support**\nFrom: {update.effective_user.first_name} (`{user_id}`)", parse_mode='Markdown')
                    await context.bot.forward_message(chat_id=ADMIN_ID, from_chat_id=user_id, message_id=msg.message_id)
                    await msg.reply_text("✅ መልእክትዎ ተልኳል!")
                except: await msg.reply_text("❌ Error sending.")

async def setup_application():
    application = ApplicationBuilder().token(TOKEN).build()
    await application.initialize()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("id", get_id))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_messages))
    return application

@app.route('/', methods=['GET', 'POST'])
@app.route('/api/index', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET': return "Bot Running! 🚀"
    if request.method == 'POST':
        if not TOKEN: return jsonify({"error": "No Token"}), 500
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            bot_app = loop.run_until_complete(setup_application())
            update = Update.de_json(request.get_json(force=True), bot_app.bot)
            loop.run_until_complete(bot_app.process_update(update))
            loop.close()
            return "OK"
        except Exception as e:
            print(f"Error: {e}")
            return jsonify({"error": str(e)}), 500
