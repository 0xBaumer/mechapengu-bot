import os
import asyncio
import json
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Telegram configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# File to store pending tweets
PENDING_TWEETS_FILE = "pending_tweets.json"

# Global state
approval_results = {}
edit_states = {}
generation_in_progress = False

# Event that /generate sets to wake up the main loop
_generate_event = None


def _get_generate_event():
    global _generate_event
    if _generate_event is None:
        _generate_event = asyncio.Event()
    return _generate_event


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    await update.message.reply_text(
        "🐧 Mechapengu Approval Bot is ready!\n"
        "I'll send you tweets for approval before posting them.\n\n"
        "Commands:\n"
        "/generate - Generate a new tweet immediately"
    )


async def generate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /generate command - triggers immediate tweet generation"""
    if generation_in_progress:
        await update.message.reply_text(
            "⏳ A tweet is already being generated or awaiting approval. Please wait."
        )
        return
    await update.message.reply_text("🐧 Generating a new tweet...")
    _get_generate_event().set()


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
        await query.edit_message_caption(
            caption=f"✅ APPROVED\n\n{tweet_data['text']}\n\nPosting to Twitter..."
        )
        approval_results[tweet_id] = {"action": "approve", "tweet_data": tweet_data}

        del pending_tweets[tweet_id]
        with open(PENDING_TWEETS_FILE, "w") as f:
            json.dump(pending_tweets, f)

    elif action == "edit":
        await query.edit_message_caption(
            caption=f"✏️ EDITING\n\nCurrent text:\n{tweet_data['text']}\n\nSend me the new tweet text (under 280 characters):"
        )
        edit_states[query.message.chat_id] = tweet_id

    elif action == "deny":
        await query.edit_message_caption(
            caption=f"❌ DENIED\n\n{tweet_data['text']}\n\nGenerating new tweet..."
        )
        approval_results[tweet_id] = {"action": "deny", "tweet_data": tweet_data}

        del pending_tweets[tweet_id]
        with open(PENDING_TWEETS_FILE, "w") as f:
            json.dump(pending_tweets, f)


def build_application():
    """Build a persistent Telegram Application with resilient HTTP settings and all handlers."""
    request = HTTPXRequest(
        connect_timeout=20.0,
        read_timeout=60.0,
        write_timeout=20.0,
        pool_timeout=10.0,
        connection_pool_size=8,
    )
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .request(request)
        .get_updates_request(HTTPXRequest(
            connect_timeout=20.0,
            read_timeout=60.0,
            write_timeout=20.0,
            pool_timeout=10.0,
            connection_pool_size=8,
        ))
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("generate", generate_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    return application


async def wait_for_trigger(timeout):
    """Wait for /generate command or timeout. Returns 'generate' or 'timer'."""
    event = _get_generate_event()
    event.clear()
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
        return "generate"
    except asyncio.TimeoutError:
        return "timer"


def set_generation_in_progress(in_progress):
    global generation_in_progress
    generation_in_progress = in_progress


async def send_and_wait_for_approval(application, tweet_text, preview_image_path, timeout=86400):
    """Send tweet for approval using the persistent bot and wait for response."""
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

    # Create inline keyboard
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{tweet_id}"),
            InlineKeyboardButton("✏️ Edit", callback_data=f"edit_{tweet_id}"),
            InlineKeyboardButton("❌ Deny", callback_data=f"deny_{tweet_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = f"🐧 New tweet for approval:\n\n{tweet_text}\n\nApprove to post as-is, Edit to change text, or Deny to skip."

    with open(preview_image_path, 'rb') as photo:
        await application.bot.send_photo(
            chat_id=TELEGRAM_CHAT_ID,
            photo=photo,
            caption=message_text,
            reply_markup=reply_markup
        )

    # Wait for approval/denial
    start_time = datetime.now()
    while (datetime.now() - start_time).total_seconds() < timeout:
        if tweet_id in approval_results:
            return approval_results.pop(tweet_id)
        await asyncio.sleep(1)

    return {"action": "timeout", "tweet_data": {"text": tweet_text}}


async def send_notification(application, message):
    """Send a notification message to Telegram."""
    await application.bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=message
    )


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
