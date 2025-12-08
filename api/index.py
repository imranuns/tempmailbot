import os
import requests
import random
import string
import asyncio
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

app = Flask(__name__)
TOKEN = os.environ.get("TOKEN")

# 🔥 Admin ID from Environment Variable
try:
    ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
except ValueError:
    ADMIN_ID = 0

# Broadcast User List (In-Memory for Vercel)
users_db = set()

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
# 🤖 Telegram Logic
# ===========================

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 ID: `{update.effective_user.id}`", parse_mode='Markdown')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users_db.add(user_id) 
    await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    keyboard = [
        [InlineKeyboardButton("📩 ኢሜይል ፍጠር (Standard)", callback_data='gen_tm')],
        [InlineKeyboardButton("🔥 አማራጭ (Alternative)", callback_data='gen_gr')],
        [InlineKeyboardButton("🆘 እርዳታ (Support)", callback_data='ask_support')]
    ]
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("📢 Admin Dashboard", callback_data='admin_panel')])

    text = "👋 **Temp Mail Bot**\n\nለማንኛውም ድረገጽ እና ሶሻል ሚዲያ ምዝገባ የሚሆን ጊዜያዊ ኢሜይል ያግኙ። 👇"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = update.effective_user.id
    
    # --- ADMIN PANEL ---
    if data == 'admin_panel':
        if user_id != ADMIN_ID: 
            await query.answer("⛔ Access Denied!", show_alert=True)
            return
        keyboard = [[InlineKeyboardButton("📢 Broadcast", callback_data='start_broadcast')], [InlineKeyboardButton("🔙 Back", callback_data='start_menu')]]
        await query.edit_message_text("👨‍✈️ **Admin Dashboard**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return

    # --- BROADCAST (FORCE REPLY) ---
    elif data == 'start_broadcast':
        if user_id != ADMIN_ID: return
        # Vercel ላይ State ስለማይሰራ ForceReply እንጠቀማለን
        await context.bot.send_message(
            chat_id=user_id,
            text="📢 **Broadcast Mode**\n\nመላክ የሚፈልጉትን ማስታወቂያ (ጽሁፍ፣ ፎቶ፣ ቪዲዮ) ለዚህ መልእክት **Reply** አድርገው ይላኩ።",
            parse_mode='Markdown',
            reply_markup=ForceReply(selective=True)
        )
        return

    # --- SUPPORT (FORCE REPLY) ---
    elif data == 'ask_support':
        await context.bot.send_message(
            chat_id=user_id,
            text="🆘 **Support Center**\n\nችግርዎን ለዚህ መልእክት **Reply** አድርገው ይፃፉ። አድሚኑ ያገኘዋል።",
            parse_mode='Markdown',
            reply_markup=ForceReply(selective=True)
        )
        return
        
    elif data == 'start_menu':
        await show_main_menu(update, context)
        return

    # --- TEMP MAIL LOGIC ---
    elif data in ['gen_tm', 'gen_gr']:
        await query.answer("⚙️ በመፍጠር ላይ...")
        account = create_tm_account() if data == 'gen_tm' else create_guerrilla_account()
        
        if account:
            if account['type'] == 'tm':
                safe_data = f"chk|tm|{account['password']}|{account['email']}"
            else:
                safe_data = f"chk|gr|{account['sid']}"

            if len(safe_data.encode('utf-8')) > 64:
                 await query.edit_message_text("❌ Error. Retry.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Retry", callback_data=data)]]))
                 return

            keyboard = [[InlineKeyboardButton("📩 Inbox ፈትሽ", callback_data=safe_data)], [InlineKeyboardButton("🔙 ዋና ሜኑ", callback_data='start_menu')]]
            provider_name = "Standard Mail" if account['type'] == 'tm' else "Alternative Mail"
            
            await query.edit_message_text(f"✅ **ኢሜይል ተፈጥሯል!** ({provider_name})\n\n`{account['email']}`\n\nCopy አድርገው ይጠቀሙ።", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await query.answer("Server Error. Try again.", show_alert=True)

    elif data.startswith('chk|'):
        parts = data.split('|')
        engine = parts[1]
        await query.answer("🔄 Inbox በመፈተሽ ላይ...")
        
        messages = []
        email_display = "Unknown"
        
        if engine == 'tm':
            if len(parts) < 4: return
            password = parts[2]
            email = parts[3]
            email_display = email
            for url in TM_PROVIDERS:
                res = check_tm_mail({"url": url, "email": email, "password": password})
                if res: 
                    messages = res
                    break
        elif engine == 'gr':
            sid = parts[2]
            email_display = "Alternative Mail"
            messages = check_guerrilla_mail({"sid": sid})

        keyboard = [[InlineKeyboardButton("📩 Inbox ፈትሽ (Refresh)", callback_data=data)], [InlineKeyboardButton("🔙 ተመለስ", callback_data='start_menu')]]
        
        if not messages:
            try:
                await query.edit_message_text(f"📭 **Inbox ባዶ ነው!**\n\n`{email_display}`\n\nመልእክት እስኪገባ ይጠብቁ...", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            except: pass
        else:
            msg = messages[0]
            text = f"📬 **መልእክት ገብቷል!**\n\n👤 **From:** {msg['from']}\n📌 **Subject:** {msg['subject']}\n\n{msg['body'][:3000]}"
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = update.message
    
    # 🔥 Check if it's a REPLY to a ForceReply message
    if msg.reply_to_message and msg.reply_to_message.from_user.is_bot:
        original_text = msg.reply_to_message.text
        
        # 1. BROADCAST HANDLING
        if "Broadcast Mode" in original_text and user_id == ADMIN_ID:
            success = 0
            if not users_db:
                await msg.reply_text("⚠️ No users found in memory (Vercel limitation).")
                return

            for uid in users_db:
                if uid == ADMIN_ID: continue
                try:
                    await context.bot.copy_message(chat_id=uid, from_chat_id=user_id, message_id=msg.message_id)
                    success += 1
                except: pass
            
            await msg.reply_text(f"✅ Broadcast Sent: {success}")
        
        # 2. SUPPORT HANDLING
        elif "Support Center" in original_text:
            if ADMIN_ID:
                try:
                    await context.bot.send_message(chat_id=ADMIN_ID, text=f"🆘 **New Support!**\nUser: {update.effective_user.first_name} (`{user_id}`)", parse_mode='Markdown')
                    await context.bot.forward_message(chat_id=ADMIN_ID, from_chat_id=user_id, message_id=msg.message_id)
                    await msg.reply_text("✅ መልእክትዎ ተልኳል! አድሚኑ በቅርቡ ይመልሳል።")
                except Exception as e:
                    await msg.reply_text(f"❌ Error: {e}")
            else:
                await msg.reply_text("❌ Admin ID not configured.")

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
