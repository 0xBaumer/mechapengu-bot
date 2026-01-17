import os
import asyncio
import json
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Telegram configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# File to store pending tweets
PENDING_TWEETS_FILE = "pending_tweets.json"

# Global variable to store approval results
approval_results = {}
edit_states = {}  # Track which tweets are being edited


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    await update.message.reply_text(
        "🐧 Mechapengu Approval Bot is ready!\n"
        "I'll send you tweets for approval before posting them."
    )


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages for editing tweets"""
    global approval_results, edit_states
    
    chat_id = update.message.chat_id
    
    # Check if this chat is editing a tweet
    if chat_id in edit_states:
        tweet_id = edit_states[chat_id]
        new_text = update.message.text
        
        # Load pending tweets
        if os.path.exists(PENDING_TWEETS_FILE):
            with open(PENDING_TWEETS_FILE, "r") as f:
                pending_tweets = json.load(f)
        else:
            pending_tweets = {}
        
        if tweet_id in pending_tweets:
            # Update the tweet text
            pending_tweets[tweet_id]['text'] = new_text
            with open(PENDING_TWEETS_FILE, "w") as f:
                json.dump(pending_tweets, f)
            
            # Store result with edited text
            approval_results[tweet_id] = {
                "action": "approve",
                "tweet_data": pending_tweets[tweet_id]
            }
            
            # Remove from pending
            del pending_tweets[tweet_id]
            with open(PENDING_TWEETS_FILE, "w") as f:
                json.dump(pending_tweets, f)
            
            # Clear editing state
            del edit_states[chat_id]
            
            await update.message.reply_text(
                f"✅ Tweet updated and approved!\n\nNew text: {new_text}\n\nPosting to Twitter..."
            )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button presses"""
    global approval_results
    
    query = update.callback_query
    await query.answer()
    
    # Parse callback data
    action, tweet_id = query.data.split("_", 1)
    
    # Load pending tweets
    if os.path.exists(PENDING_TWEETS_FILE):
        with open(PENDING_TWEETS_FILE, "r") as f:
            pending_tweets = json.load(f)
    else:
        pending_tweets = {}
    
    # Get pending tweet data
    if tweet_id not in pending_tweets:
        await query.edit_message_caption(
            caption="❌ Tweet data not found. It may have already been processed."
        )
        return
    
    tweet_data = pending_tweets[tweet_id]
    
    if action == "approve":
        # Update message to show approval
        await query.edit_message_caption(
            caption=f"✅ APPROVED\n\n{tweet_data['text']}\n\nPosting to Twitter..."
        )
        
        # Store result
        approval_results[tweet_id] = {"action": "approve", "tweet_data": tweet_data}
        
        # Remove from pending
        del pending_tweets[tweet_id]
        with open(PENDING_TWEETS_FILE, "w") as f:
            json.dump(pending_tweets, f)
    
    elif action == "edit":
        # Prompt user to send new text
        await query.edit_message_caption(
            caption=f"✏️ EDITING\n\nCurrent text:\n{tweet_data['text']}\n\nSend me the new tweet text (under 280 characters):"
        )
        
        # Set editing state
        edit_states[query.message.chat_id] = tweet_id
        
    elif action == "deny":
        # Update message to show denial
        await query.edit_message_caption(
            caption=f"❌ DENIED\n\n{tweet_data['text']}\n\nGenerating new tweet..."
        )
        
        # Store result
        approval_results[tweet_id] = {"action": "deny", "tweet_data": tweet_data}
        
        # Remove from pending
        del pending_tweets[tweet_id]
        with open(PENDING_TWEETS_FILE, "w") as f:
            json.dump(pending_tweets, f)


async def send_approval_request_async(application, tweet_text, preview_image_path):
    """Send a tweet for approval to Telegram (async version)"""
    # Generate unique ID for this tweet
    tweet_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Store pending tweet data
    if os.path.exists(PENDING_TWEETS_FILE):
        with open(PENDING_TWEETS_FILE, "r") as f:
            pending_tweets = json.load(f)
    else:
        pending_tweets = {}
    
    pending_tweets[tweet_id] = {
        "text": tweet_text,
        "preview_path": preview_image_path,
        "timestamp": datetime.now().isoformat()
    }
    
    with open(PENDING_TWEETS_FILE, "w") as f:
        json.dump(pending_tweets, f)
    
    # Create inline keyboard with approve/edit/deny buttons
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{tweet_id}"),
            InlineKeyboardButton("✏️ Edit", callback_data=f"edit_{tweet_id}"),
            InlineKeyboardButton("❌ Deny", callback_data=f"deny_{tweet_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send message with image and buttons
    message_text = f"🐧 New tweet for approval:\n\n{tweet_text}\n\nApprove to post as-is, Edit to change text, or Deny to skip."
    
    # Send photo with caption and buttons
    with open(preview_image_path, 'rb') as photo:
        await application.bot.send_photo(
            chat_id=TELEGRAM_CHAT_ID,
            photo=photo,
            caption=message_text,
            reply_markup=reply_markup
        )
    
    return tweet_id


async def send_notification_async(application, message):
    """Send a notification message to Telegram (async version)"""
    await application.bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=message
    )


def send_tweet_for_approval(tweet_text, preview_image_path):
    """Send tweet for approval and wait for response (blocking)"""
    global approval_results
    
    async def run_approval_bot():
        # Create application
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
        
        # Initialize the application
        await application.initialize()
        await application.start()
        
        # Send approval request
        tweet_id = await send_approval_request_async(application, tweet_text, preview_image_path)
        
        # Start polling for updates
        await application.updater.start_polling()
        
        # Wait for approval/denial (max 24 hours)
        timeout = 86400  # 24 hours in seconds
        start_time = datetime.now()
        
        while (datetime.now() - start_time).seconds < timeout:
            # Check if we have a result
            if tweet_id in approval_results:
                result = approval_results[tweet_id]
                del approval_results[tweet_id]  # Clean up
                
                # Stop the application
                await application.updater.stop()
                await application.stop()
                await application.shutdown()
                
                return result
            
            await asyncio.sleep(1)
        
        # Timeout - clean up
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        
        # Send timeout notification
        await send_notification_async(application, "⏰ Tweet approval timed out after 24 hours. Skipping...")
        
        return {"action": "timeout", "tweet_data": {"text": tweet_text}}
    
    # Run the async function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(run_approval_bot())
        return result
    finally:
        loop.close()


def send_notification(message):
    """Send a simple notification to Telegram (blocking)"""
    async def _send():
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        await application.initialize()
        await application.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message
        )
        await application.shutdown()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_send())
    finally:
        loop.close()


def check_telegram_config():
    """Check if Telegram configuration is set"""
    if not TELEGRAM_BOT_TOKEN:
        print("Warning: TELEGRAM_BOT_TOKEN not set in .env file")
        print("Please add TELEGRAM_BOT_TOKEN to your .env file")
        print("You can create a bot using @BotFather on Telegram")
        return False
    if not TELEGRAM_CHAT_ID:
        print("Warning: TELEGRAM_CHAT_ID not set in .env file")
        print("Please add TELEGRAM_CHAT_ID to your .env file")
        print("You can get your chat ID by messaging your bot and checking the updates")
        return False
    return True