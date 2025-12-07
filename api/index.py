import os
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# 1. Bot Token ከ Vercel Environment እናመጣለን (ለደህንነት)
TOKEN = os.environ.get("TOKEN")

# --- 1secmail API Functions ---

def generate_email():
    """አዲስ ኢሜይል ከ 1secmail ይፈጥራል"""
    url = "https://www.1secmail.com/api/v1/?action=genRandomMailbox&count=1"
    response = requests.get(url).json()
    return response[0] # ምሳሌ: "user@1secmail.com"

def check_email(login, domain):
    """ኢሜይል ውስጥ የገቡ መልእክቶችን ያያል"""
    url = f"https://www.1secmail.com/api/v1/?action=getMessages&login={login}&domain={domain}"
    messages = requests.get(url).json()
    return messages

def read_message(login, domain, msg_id):
    """የአንድን መልእክት ዝርዝር (Body) ያነባል"""
    url = f"https://www.1secmail.com/api/v1/?action=readMessage&login={login}&domain={domain}&id={msg_id}"
    msg = requests.get(url).json()
    return msg

# --- Telegram Bot Logic ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start ሲባል የሚመጣ"""
    keyboard = [
        [InlineKeyboardButton("📧 አዲስ ኢሜይል ፍጠር (Generate)", callback_data='gen_email')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("ሰላም! እኔ Temp Mail Bot ነኝ።\nለፌስቡክ ወይም ለቲክቶክ መመዝገቢያ ጊዜያዊ ኢሜይል እሰራለሁ። 👇", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Button ሲነካ የሚሰራ"""
    query = update.callback_query
    await query.answer() # Loading እንዳይል

    data = query.data
    
    if data == 'gen_email':
        # አዲስ ኢሜይል ፍጠር
        new_email = generate_email()
        login, domain = new_email.split('@')
        
        # ኢሜይሉን ለተጠቃሚው አሳይ + Inbox ማያ ቁልፍ ጨምርበት
        # ቁልፉ ላይ ኢሜይሉን አብረን እንልካለን (ለማስታወስ)
        keyboard = [
            [InlineKeyboardButton("📩 Inbox ፈትሽ (Check)", callback_data=f"check|{login}|{domain}")],
            [InlineKeyboardButton("🔄 ሌላ አዲስ (New)", callback_data='gen_email')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"✅ አዲሱ ኢሜይልህ ይኸው:\n\n`{new_email}`\n\n(Copy አድርገህ ተጠቀም፣ መልእክት ሲላክለት 'Inbox ፈትሽ' የሚለውን ንካ)",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    elif data.startswith('check|'):
        # Inbox መፈተሽ
        _, login, domain = data.split('|')
        messages = check_email(login, domain)
        
        if not messages:
            await query.answer("📭 ምንም መልእክት አልገባም! ትንሽ ቆይተህ ሞክር።", show_alert=True)
        else:
            # መልእክት ካለ የመጨረሻውን እናንብብ
            last_msg = messages[0]
            full_msg = read_message(login, domain, last_msg['id'])
            
            sender = full_msg.get('from')
            subject = full_msg.get('subject')
            body = full_msg.get('textBody') # ኮዱ ያለበት ቦታ
            
            await query.edit_message_text(
                f"📬 **አዲስ መልእክት ገብቷል!**\n\n**ከ:** {sender}\n**ርዕስ:** {subject}\n\n**መልእክት:**\n{body}\n",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ተመለስ", callback_data=f"back|{login}|{domain}")]])
            )
            
    elif data.startswith('back|'):
         _, login, domain = data.split('|')
         email = f"{login}@{domain}"
         keyboard = [
            [InlineKeyboardButton("📩 Inbox ፈትሽ (Check)", callback_data=f"check|{login}|{domain}")],
            [InlineKeyboardButton("🔄 ሌላ አዲስ (New)", callback_data='gen_email')]
        ]
         await query.edit_message_text(
            f"✅ ኢሜይልህ:\n`{email}`",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

# --- Vercel Entry Point ---
# Vercel ይህንን function ነው የሚጠራው
async def handler(request):
    """Vercel Serverless Function"""
    # ቦቱን መገንባት
    application = ApplicationBuilder().token(TOKEN).build()
    
    # ትዛዞችን መጨመር
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))

    # ከ Telegram የመጣውን መረጃ (Update) መቀበል
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
    except Exception as e:
        print(f"Error: {e}")

    return "OK"

# Vercel የ Python web server (Flask/FastAPI) ስለማይጠቀም
# ቀጥታ ለ Request ምላሽ እንዲሰጥ ነው የምናደርገው።
# (ማሳሰቢያ: ይህ ኮድ ለ Vercel Serverless እንዲሆን ተቀናብሮ የተጻፈ ነው)
