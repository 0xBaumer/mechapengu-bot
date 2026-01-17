import json
import os
import random
import time
import requests
import tweepy
import fal_client  # pip install fal-client, xai-sdk not needed, using requests for xAI
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import Literal
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

MECHA_PENGU_IMAGE = (
    "https://v3.fal.media/files/lion/wGJuMrE8a1NcZ4aQ_sFaX_drift-ice.jpg"
)


def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    return []


def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f)


class TweetResponse(BaseModel):
    tweet: str = Field(description="The tweet text, must be under 280 characters")
    image_prompt: str = Field(
        description="The image generation prompt for a related image"
    )
    meme_top_text: str = Field(default="", description="Top text for meme format (if meme)")
    meme_bottom_text: str = Field(default="", description="Bottom text for meme format (if meme)")


def generate_tweet_and_prompt(history):
    # 50% chance to make a classic meme format
    is_meme_format = random.random() < 0.5
    
    if is_meme_format:
        lore = """You are Mechapengu, a degen meme lord. Generate a CLASSIC MEME FORMAT post.
        
        MEME RULES:
        - Create stupid, provocative, trending crypto memes
        - Use classic meme templates mentally (Drake, Distracted Boyfriend, Expanding Brain, etc.)
        - Generate TOP TEXT and BOTTOM TEXT for the meme image (short, punchy, ALL CAPS style)
        - The tweet text is the caption/context (can be short or just emojis)
        - Make it about crypto trends, $MECH, market moves, or degen culture
        - Be unhinged, stupid, and provocative - what actually works on Twitter
        - NO hashtags or dashes
        
        Your response must include:
        - tweet: Short caption for the meme (can be emojis or brief text)
        - image_prompt: Description of meme image (the visual, not the text)
        - meme_top_text: Text for TOP of image (short, punchy)
        - meme_bottom_text: Text for BOTTOM of image (short, punchy)"""
    else:
        lore = """You are Mechapengu, a degen penguin robot in the crypto space. You're here to farm engagement and make MECH/Mecha Pengu token moon. 
        
        Your style:
        - Post spicy crypto memes and trending topics from crypto Twitter
        - React to market moves, pumps, dumps, and crypto drama
        - Roast rugs, scams, and paper hands
        - Hype bullish narratives (AI agents, L2s, DeFi, memecoins)
        - Use crypto slang: gm, wagmi, ngmi, ser, anon, rekt, giga brain, cope, fud, ape, degen, etc.
        - Be funny, edgy, sometimes unhinged
        - No hashtags or dashes in tweets
        - Keep it memeable and viral-worthy
        
        Focus on Abstract chain L2 and the broader crypto ecosystem trends.
        
        Set meme_top_text and meme_bottom_text to empty strings."""

    # 2/3 chance to add MECH content
    if random.random() < 2 / 3:
        lore += """ This tweet should mention $MECH in a hype, memey way. 
        Talk about it mooning, being undervalued, or being the next 100x. 
        Make it funny and engaging. Get people to ape in."""

    # 1/5 chance to mention @AbstractChain
    if random.random() < 1 / 5:
        lore += """ Mention @AbstractChain in this tweet. 
        Hype the tech, the ecosystem, or just give them a based shoutout. 
        Make Abstract look like the future of L2s."""

    prev_tweets = "\n".join(history[-3:]) if history else "No previous tweets."
    prompt = f"{lore}\nPrevious tweets:\n{prev_tweets}\n\nGenerate a new tweet (under 280 characters) and an image prompt. The image should be creative and diverse - NOT just moons and rockets every time. Use varied scenarios: Mechapengu doing different activities, in different settings, with different moods and themes. Be creative and avoid repetitive imagery."

    response = requests.post(
        "https://api.x.ai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {XAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "grok-2-1212",  # Using grok-2-1212 which supports structured outputs
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 300,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "tweet_response",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "tweet": {
                                "type": "string",
                                "description": "The tweet text, must be under 280 characters",
                            },
                            "image_prompt": {
                                "type": "string",
                                "description": "The image generation prompt for a related image",
                            },
                            "meme_top_text": {
                                "type": "string",
                                "description": "Top text for meme format (empty if not a meme)",
                            },
                            "meme_bottom_text": {
                                "type": "string",
                                "description": "Bottom text for meme format (empty if not a meme)",
                            },
                        },
                        "required": ["tweet", "image_prompt", "meme_top_text", "meme_bottom_text"],
                        "additionalProperties": False,
                    },
                },
            },
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

    # Parse the JSON response
    try:
        tweet_data = json.loads(content)
        # Validate with Pydantic
        validated_response = TweetResponse(**tweet_data)

        # Modify image prompt if this is a pengu-bot tweet
        image_prompt = validated_response.image_prompt

        # Add water color specification if water-related keywords are present
        water_keywords = [
            "water",
            "ocean",
            "sea",
            "lake",
            "river",
            "swimming",
            "diving",
            "underwater",
            "waves",
            "beach",
            "shore",
            "splash",
            "aquatic",
            "marine",
        ]
        if any(keyword in image_prompt.lower() for keyword in water_keywords):
            image_prompt += " Any water in the scene should be rendered in a vibrant medium spring green color (#00fa9a), giving it a unique, stylized appearance."

        return (
            validated_response.tweet,
            image_prompt,
            validated_response.meme_top_text,
            validated_response.meme_bottom_text,
            is_meme_format
        )
    except (json.JSONDecodeError, Exception) as e:
        print(f"Error parsing structured response: {e}")
        print(f"Raw content: {content}")
        raise Exception(f"Failed to parse structured response: {e}")


def generate_image(image_prompt):
    response = fal_client.run(
        "fal-ai/flux-pro/kontext",
        {"prompt": image_prompt, "image_url": MECHA_PENGU_IMAGE},
    )
    image_url = response["images"][0]["url"]
    img_data = requests.get(image_url).content
    with open("temp_image.png", "wb") as f:
        f.write(img_data)
    return "temp_image.png"


def create_meme_image(top_text, bottom_text, base_image_path):
    """Create a classic meme with white text on top and bottom"""
    img = Image.open(base_image_path)
    draw = ImageDraw.Draw(img)
    
    # Try to use Impact font, fallback to default
    try:
        # Try common Impact font locations
        font_size = int(img.height * 0.1)  # 10% of image height
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Impact.ttf", font_size)
    except:
        try:
            font = ImageFont.truetype("Impact.ttf", font_size)
        except:
            # Fallback to default if Impact not found
            font = ImageFont.load_default()
    
    # Function to draw text with black outline
    def draw_text_with_outline(text, position, anchor="mm"):
        x, y = position
        # Draw outline (black)
        outline_range = 3
        for adj_x in range(-outline_range, outline_range + 1):
            for adj_y in range(-outline_range, outline_range + 1):
                draw.text((x + adj_x, y + adj_y), text, font=font, fill="black", anchor=anchor)
        # Draw text (white)
        draw.text(position, text, font=font, fill="white", anchor=anchor)
    
    # Draw top text
    if top_text:
        top_position = (img.width // 2, int(img.height * 0.1))
        draw_text_with_outline(top_text.upper(), top_position)
    
    # Draw bottom text
    if bottom_text:
        bottom_position = (img.width // 2, int(img.height * 0.9))
        draw_text_with_outline(bottom_text.upper(), bottom_position)
    
    # Save the meme
    img.save("temp_image.png")
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
                tweet_text, image_prompt, meme_top, meme_bottom, is_meme = generate_tweet_and_prompt(history)
                print(f"\nGenerated tweet: {tweet_text}")
                print(f"Image prompt: {image_prompt}")
                if is_meme:
                    print(f"MEME FORMAT - Top: {meme_top}, Bottom: {meme_bottom}")

                image_path = generate_image(image_prompt)
                print(f"Image generated: {image_path}")
                
                # If it's a meme format, add text overlay
                if is_meme and (meme_top or meme_bottom):
                    image_path = create_meme_image(meme_top, meme_bottom, image_path)
                    print(f"Meme text added to image")

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
                                # Use the tweet text from result (in case it was edited)
                                final_tweet_text = result["tweet_data"]["text"]
                                post_tweet(final_tweet_text, image_path)
                                history.append(final_tweet_text)
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
                                # Use the tweet text from result (in case it was edited)
                                final_tweet_text = result["tweet_data"]["text"]
                                post_tweet(final_tweet_text, image_path)
                                history.append(final_tweet_text)
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

                    sleep_time = random.uniform(
                        1800, 3600
                    )  # 30 to 60 minutes in seconds
                    print(f"Waiting {sleep_time/60:.1f} minutes until next tweet...")
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
