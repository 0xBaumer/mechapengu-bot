import json
import os
import random
import time
import requests
import tweepy
import fal_client  # pip install fal-client, xai-sdk not needed, using requests for xAI
from PIL import Image
from datetime import datetime
from dotenv import load_dotenv
import telegram_handler

# Load environment variables from .env file
load_dotenv()

# API keys - set these as environment variables for security
XAI_API_KEY = os.getenv("XAI_API_KEY")
FAL_KEY = os.getenv("FAL_KEY")  # fal.ai uses auth via env or config
TWITTER_CONSUMER_KEY = os.getenv("TWITTER_CONSUMER_KEY")
TWITTER_CONSUMER_SECRET = os.getenv("TWITTER_CONSUMER_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")

# Test mode configuration
TEST_MODE = False  # Set to False to actually post tweets
TELEGRAM_APPROVAL = True

HISTORY_FILE = "tweet_history.json"


def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    return []


def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f)


def generate_tweet_and_prompt(history):
    lore = "You are Mechapengu, a nice penguin robot who loves adventures, helping others, and sharing fun facts about technology and nature. Keep tweets positive and engaging."
    prev_tweets = "\n".join(history[-3:]) if history else "No previous tweets."
    prompt = f"{lore}\nPrevious tweets:\n{prev_tweets}\nGenerate a new tweet (under 280 characters) and an image prompt for a cute related image. Format: Tweet: [text]\nImage prompt: [prompt]"

    response = requests.post(
        "https://api.x.ai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {XAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "grok-4",  # Changed from grok-4 to grok-beta
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 300,
        },
    )

    # Check if request was successful
    if response.status_code != 200:
        print(f"Error: API request failed with status {response.status_code}")
        print(f"Response: {response.text}")
        raise Exception(f"API request failed: {response.text}")

    response_json = response.json()

    # Debug print to see the actual response structure
    if "choices" not in response_json:
        print(f"Unexpected response structure: {response_json}")
        raise Exception("API response missing 'choices' field")

    content = response_json["choices"][0]["message"]["content"]

    tweet_start = content.find("Tweet: ") + 7
    prompt_start = content.find("Image prompt: ") + 14
    tweet_text = content[tweet_start : content.find("\n", tweet_start)].strip()
    image_prompt = content[prompt_start:].strip()

    return tweet_text, image_prompt


def generate_image(image_prompt):
    response = fal_client.run("fal-ai/flux-pro", {"prompt": image_prompt})
    image_url = response["images"][0]["url"]
    img_data = requests.get(image_url).content
    with open("temp_image.png", "wb") as f:
        f.write(img_data)
    return "temp_image.png"


def post_tweet(tweet_text, image_path):
    auth = tweepy.OAuth1UserHandler(
        TWITTER_CONSUMER_KEY,
        TWITTER_CONSUMER_SECRET,
        TWITTER_ACCESS_TOKEN,
        TWITTER_ACCESS_TOKEN_SECRET,
    )
    api = tweepy.API(auth)
    media = api.media_upload(image_path)

    client = tweepy.Client(
        consumer_key=TWITTER_CONSUMER_KEY,
        consumer_secret=TWITTER_CONSUMER_SECRET,
        access_token=TWITTER_ACCESS_TOKEN,
        access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
    )
    client.create_tweet(text=tweet_text, media_ids=[media.media_id_string])


def check_api_keys():
    """Check if all required API keys are set"""
    missing_keys = []

    if not XAI_API_KEY:
        missing_keys.append("XAI_API_KEY")
    if not FAL_KEY:
        missing_keys.append("FAL_KEY")

    # Only check Twitter keys if not in test mode
    if not TEST_MODE:
        if not TWITTER_CONSUMER_KEY:
            missing_keys.append("TWITTER_CONSUMER_KEY")
        if not TWITTER_CONSUMER_SECRET:
            missing_keys.append("TWITTER_CONSUMER_SECRET")
        if not TWITTER_ACCESS_TOKEN:
            missing_keys.append("TWITTER_ACCESS_TOKEN")
        if not TWITTER_ACCESS_TOKEN_SECRET:
            missing_keys.append("TWITTER_ACCESS_TOKEN_SECRET")

        # Check Telegram configuration when TELEGRAM_APPROVAL is True
        if TELEGRAM_APPROVAL:
            if not telegram_handler.check_telegram_config():
                print(
                    "\nError: TELEGRAM_APPROVAL is enabled but Telegram is not configured."
                )
                print("Please either:")
                print(
                    "  1. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in your .env file"
                )
                print("  2. Set TELEGRAM_APPROVAL=False in your .env file")
                return False
        elif not telegram_handler.check_telegram_config():
            print("\nTelegram approval bot is not configured.")
            print("The bot will continue without Telegram approval.")

    if missing_keys:
        print("Error: The following API keys are missing:")
        for key in missing_keys:
            print(f"  - {key}")
        print("\nPlease add these keys to your .env file")
        return False
    return True


def main():
    """Main bot loop"""
    if not check_api_keys():
        return

    print(f"Starting Mechapengu bot (TEST_MODE={TEST_MODE})")

    try:
        while True:
            history = load_history()

            try:
                tweet_text, image_prompt = generate_tweet_and_prompt(history)
                print(f"\nGenerated tweet: {tweet_text}")
                print(f"Image prompt: {image_prompt}")

                image_path = generate_image(image_prompt)
                print(f"Image generated: {image_path}")

                if TEST_MODE:
                    # Test mode: show what would be posted
                    print(f"Test mode: Would post tweet with text: {tweet_text}")
                    print(f"Test mode: Would post with image: {image_path}")
                    print("Tweet would be posted with this content and image.")

                    # Clean up the temp image
                    os.remove(image_path)

                    # In test mode, break after one iteration or use shorter sleep
                    print(
                        "\nTest mode: Waiting 30 seconds before next tweet (or press Ctrl+C to stop)"
                    )
                    time.sleep(30)
                else:
                    # Production mode: send to Telegram for approval first

                    # Check if Telegram approval is required
                    if TELEGRAM_APPROVAL:
                        # Telegram approval is mandatory - config already validated in check_api_keys()
                        print("Sending tweet to Telegram for approval...")

                        try:
                            # Send for approval and wait for response
                            result = telegram_handler.send_tweet_for_approval(
                                tweet_text, image_path
                            )

                            if result["action"] == "approve":
                                print("Tweet approved! Posting to Twitter...")
                                post_tweet(tweet_text, image_path)
                                history.append(tweet_text)
                                save_history(history)
                                print(f"Tweet posted successfully!")

                                # Send confirmation to Telegram
                                telegram_handler.send_notification(
                                    "✅ Tweet posted successfully to Twitter!"
                                )

                            elif result["action"] == "deny":
                                print(
                                    "Tweet denied. Will generate a new one in the next cycle."
                                )
                                # Don't add to history, will generate new one

                            elif result["action"] == "timeout":
                                print("Approval timed out. Skipping this tweet.")

                        except Exception as e:
                            print(f"Error with Telegram approval: {e}")
                            print(
                                "Cannot continue without approval when TELEGRAM_APPROVAL is enabled."
                            )
                            # Skip this tweet and continue to next cycle
                    elif telegram_handler.check_telegram_config():
                        # Telegram is configured but not required - use it if available
                        print("Sending tweet to Telegram for optional approval...")

                        try:
                            # Send for approval and wait for response
                            result = telegram_handler.send_tweet_for_approval(
                                tweet_text, image_path
                            )

                            if result["action"] == "approve":
                                print("Tweet approved! Posting to Twitter...")
                                post_tweet(tweet_text, image_path)
                                history.append(tweet_text)
                                save_history(history)
                                print(f"Tweet posted successfully!")

                                # Send confirmation to Telegram
                                telegram_handler.send_notification(
                                    "✅ Tweet posted successfully to Twitter!"
                                )

                            elif result["action"] == "deny":
                                print(
                                    "Tweet denied. Will generate a new one in the next cycle."
                                )
                                # Don't add to history, will generate new one

                            elif result["action"] == "timeout":
                                print("Approval timed out. Skipping this tweet.")

                        except Exception as e:
                            print(f"Error with Telegram approval: {e}")
                            print("Continuing without approval...")
                            # Post anyway since approval is optional
                            post_tweet(tweet_text, image_path)
                            history.append(tweet_text)
                            save_history(history)
                            print(f"Tweet posted successfully!")
                    else:
                        # No Telegram config and not required, post directly
                        print("Posting directly to Twitter...")
                        post_tweet(tweet_text, image_path)
                        history.append(tweet_text)
                        save_history(history)
                        print(f"Tweet posted successfully!")

                    # Clean up files
                    if os.path.exists(image_path):
                        os.remove(image_path)

                    sleep_time = random.uniform(3600, 10800)  # 1 to 3 hours in seconds
                    print(f"Waiting {sleep_time/3600:.1f} hours until next tweet...")
                    time.sleep(sleep_time)

            except Exception as e:
                print(f"\nError occurred: {e}")
                if TEST_MODE:
                    print("Test mode: Waiting 30 seconds before retry...")
                    time.sleep(30)
                else:
                    print("Waiting 5 minutes before retry...")
                    time.sleep(300)  # Wait 5 minutes before retry in production

    except KeyboardInterrupt:
        print("\nBot stopped by user")


if __name__ == "__main__":
    main()
