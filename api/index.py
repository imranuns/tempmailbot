import os
import json
import asyncio
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# ⚠️ TOKEN ከ Vercel Environment Variable ይመጣል
TOKEN = os.environ.get("TOKEN")

# --- 1secmail API Functions ---

def generate_email():
    """አዲስ ኢሜይል ይፈጥራል"""
    url = "https://www.1secmail.com/api/v1/?action=genRandomMailbox&count=1"
    try:
        response = requests.get(url).json()
        return response[0]
    except:
        return None

def check_email(login, domain):
    """ኢሜይል ይፈትሻል"""
    url = f"https://www.1secmail.com/api/v1/?action=getMessages&login={login}&domain={domain}"
    try:
        response = requests.get(url).json()
        return response
    except:
        return []

def read_message(login, domain, msg_id):
    """መልእክት ያነባል"""
    url = f"https://www.1secmail.com/api/v1/?action=readMessage&login={login}&domain={domain}&id={msg_id}"
    try:
        response = requests.get(url).json()
        return response
    except:
        return None

# --- Telegram Bot Logic ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start ትዛዝ"""
    keyboard = [
        [InlineKeyboardButton("📧 አዲስ ኢሜይል ፍጠር", callback_data='gen_email')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 **ሰላም! እኔ Temp Mail Bot ነኝ።**\n\n"
        "ለ Facebook, TikTok ወይም ለሌላ ድረገጽ መመዝገቢያ "
        "ጊዜያዊ ኢሜይል እሰራለሁ። 👇", 
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Buttons ሲነኩ የሚሰራ"""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == 'gen_email':
        email = generate_email()
        if email:
            login, domain = email.split('@')
            keyboard = [
                [InlineKeyboardButton("📩 Inbox ፈትሽ (Refresh)", callback_data=f"check|{login}|{domain}")],
                [InlineKeyboardButton("🔄 ሌላ አዲስ ኢሜይል", callback_data='gen_email')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"✅ **አዲሱ ኢሜይልህ:**\n\n`{email}`\n\n"
                "👆 ይህንን Copy አድርገህ ተጠቀም። ኮድ ሲላክ 'Inbox ፈትሽ' የሚለውን ንካ።",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text("❌ ችግር ተፈጥሯል! እባክህ ድጋሚ ሞክር።")

    elif data.startswith('check|'):
        try:
            _, login, domain = data.split('|')
            messages = check_email(login, domain)
            
            if not messages:
                await query.answer("📭 ባዶ ነው! ምንም መልእክት አልገባም።", show_alert=True)
            else:
                last_msg_id = messages[0]['id']
                full_msg = read_message(login, domain, last_msg_id)
                
                if full_msg:
                    sender = full_msg.get('from')
                    subject = full_msg.get('subject')
                    body = full_msg.get('textBody', 'No text content')
                    
                    keyboard = [[InlineKeyboardButton("🔙 ተመለስ", callback_data=f"back|{login}|{domain}")]]
                    
                    await query.edit_message_text(
                        f"📬 **አዲስ መልእክት!**\n\n"
                        f"**ከ:** `{sender}`\n"
                        f"**ርዕስ:** `{subject}`\n\n"
                        f"**መልእክት:**\n{body}\n",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='Markdown'
                    )
        except:
             await query.answer("Error checking mail", show_alert=True)

    elif data.startswith('back|'):
        _, login, domain = data.split('|')
        email = f"{login}@{domain}"
        keyboard = [
            [InlineKeyboardButton("📩 Inbox ፈትሽ (Refresh)", callback_data=f"check|{login}|{domain}")],
            [InlineKeyboardButton("🔄 ሌላ አዲስ ኢሜይል", callback_data='gen_email')]
        ]
        await query.edit_message_text(
            f"✅ **ኢሜይልህ:**\n`{email}`",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

# --- Vercel Webhook Handler ---

async def main(request):
    """Vercel ይጠራዋል"""
    if not TOKEN:
        print("❌ Error: No TOKEN found in environment variables!")
        return "No Token"
        
    application = ApplicationBuilder().token(TOKEN).build()
    
    # 🔥 ወሳኝ ለውጥ: ቦቱ ስራ ከመጀመሩ በፊት Initialize መደረግ አለበት!
    await application.initialize()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))

    try:
        if request.method == "POST":
            data = await request.json()
            update = Update.de_json(data, application.bot)
            await application.process_update(update)
            return "Success"
        return "Bot is running!"
    except Exception as e:
        print(f"❌ Error in main: {e}")
        return f"Error: {e}"

# Vercel entry point
from http.server import BaseHTTPRequestHandler

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Temp Mail Bot is Active!")

    def do_POST(self):
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            class MockRequest:
                def __init__(self, data):
                    self.data = data
                    self.method = "POST"
                async def json(self):
                    return json.loads(self.data)
            
            mock_req = MockRequest(post_data)
            loop.run_until_complete(main(mock_req))
            loop.close()
            
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        except Exception as e:
            print(f"❌ Server Error: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode())
