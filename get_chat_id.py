import os
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def echo_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    chat_title = update.effective_chat.title or "Direct Message"
    
    response = f"Chat ID: {chat_id}\nChat Type: {chat_type}\nChat Name: {chat_title}"
    await update.message.reply_text(response)
    print(response)

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, echo_chat_id))
    
    print("Bot started! Send any message to get the chat ID.")
    print("Press Ctrl+C to stop.\n")
    
    app.run_polling()

if __name__ == "__main__":
    main()
