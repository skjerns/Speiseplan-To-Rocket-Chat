#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
daily_menu_post.py

This script posts today’s cafeteria dishes to Rocket.Chat.
It performs the following tasks:

  1. Locates the weekly speiseplan image using get_this_week_speiseplan().
  2. Crops today’s two dish images from the weekly image with extract_dishes_today().
  3. Uploads the dish images to GitHub via upload_to_github().
  4. Posts the dish images to Rocket.Chat and adds emoji reactions using post_to_rocket_chat().

This script is to be run every weekday (Monday–Friday), for example via a cronjob
at 1pm.

Ensure that your environment variables or an env.py file provide:
  ROCKETCHAT_URL, ROCKETCHAT_ID, ROCKETCHAT_TOKEN, and optionally ROCKETCHAT_CHANNEL.
"""

import os
import glob
import subprocess
from datetime import datetime
from PIL import Image
from rocketchat_API.rocketchat import RocketChat

# Load configuration either from env.py or environment variables
try:
    from env import ROCKETCHAT_URL, ROCKETCHAT_ID, ROCKETCHAT_TOKEN, ROCKETCHAT_CHANNEL
except ImportError:
    ROCKETCHAT_URL = os.environ.get("ROCKETCHAT_URL")
    ROCKETCHAT_ID = os.environ.get("ROCKETCHAT_ID")
    ROCKETCHAT_TOKEN = os.environ.get("ROCKETCHAT_TOKEN")
    ROCKETCHAT_CHANNEL = os.environ.get("ROCKETCHAT_CHANNEL", "Speiseplan_TEST")

# Global variable to store the weekly menu file
GLOBAL_SPEISEPLAN = None

def get_this_week_speiseplan():
    """
    Locate the most recent weekly speiseplan PNG in the './speiseplaene' directory.
    This PNG is assumed to be the menu for the entire week.

    Returns:
        The file path of the weekly speiseplan.
    """
    global GLOBAL_SPEISEPLAN
    files = glob.glob(os.path.join("speiseplaene", "*.png"))
    if not files:
        raise FileNotFoundError("No weekly menu PNG found in './speiseplaene'.")
    # Choose the most recently created file
    latest_file = max(files, key=os.path.getctime)
    GLOBAL_SPEISEPLAN = latest_file
    print(f"Found weekly speiseplan: {latest_file}")
    return latest_file

def extract_dishes_today():
    """
    Crop out today's two dish images from the weekly speiseplan.

    Assumptions:
      - The speiseplan image is organized into five horizontal rows (Monday-Friday).
      - Each row is split into two halves for the two dish options.

    Returns:
       A tuple (dish1_path, dish2_path) with the filenames of the two cropped images.
       If today is Saturday or Sunday, returns (None, None).
    """
    today = datetime.now()
    weekday = today.weekday()  # Monday=0, Tuesday=1, ... Sunday=6
    if weekday >= 5:
        print("Today is weekend. No dishes to extract.")
        return None, None

    if not GLOBAL_SPEISEPLAN:
        raise Exception("Weekly speiseplan not loaded. Call get_this_week_speiseplan() first.")

    image = Image.open(GLOBAL_SPEISEPLAN)
    width, height = image.size

    # Assume five equal horizontal rows in the image
    row_height = height // 5
    top = weekday * row_height
    bottom = (weekday + 1) * row_height

    # Crop dish1 (left half) and dish2 (right half)
    dish1 = image.crop((0, top, width // 2, bottom))
    dish2 = image.crop((width // 2, top, width, bottom))

    today_str = today.strftime("%Y-%m-%d")
    dish1_path = f"./dishes/dish1_{today_str}.png"
    dish2_path = f"./dishes/dish2_{today_str}.png"

    dish1.save(dish1_path)
    dish2.save(dish2_path)

    print(f"Extracted dishes: {dish1_path}, {dish2_path}")
    return dish1_path, dish2_path

def upload_to_github(dish1_path, dish2_path):
    """
    Upload the dish images to GitHub by adding, committing, and pushing the new files.

    This function sets up the git user (if necessary), stages the two dish images,
    commits them with an appropriate message, and pushes the changes.
    """
    try:
        print("Configuring git user...")
        subprocess.check_output(['git', 'config', '--global', 'user.name', 'github-actions[bot]'])
        subprocess.check_output(['git', 'config', '--global', 'user.email', 'github-actions[bot]@users.noreply.github.com'])

        print("Adding dish images to git...")
        subprocess.check_output(['git', 'add', dish1_path, dish2_path])

        print("Committing changes...")
        # If there is nothing to commit, ignore the error.
        try:
            subprocess.check_output(['git', 'commit', '-m', "Add today's dishes"])
        except subprocess.CalledProcessError as e:
            msg = e.output.decode() if e.output else str(e)
            if "nothing to commit" in msg:
                print("No changes to commit.")
            else:
                print("Commit error:", msg)

        print("Pushing changes to GitHub...")
        subprocess.run(['git', 'push'], check=True)
        print("Uploaded dishes to GitHub successfully.")
    except Exception as e:
        print("Error uploading to GitHub:", e)

def post_to_rocket_chat(dish1_path, dish2_path):
    """
    Post the dish images to Rocket.Chat and add emoji reactions to each post.

    Each dish is uploaded as a file to the configured Rocket.Chat channel.
    After posting, several reactions (e.g., :thumbsup:, :thumbsdown:, :yum:) are added.
    """
    if not dish1_path or not dish2_path:
        print("No dishes to post to Rocket.Chat.")
        return

    rocket = RocketChat(
        user_id=ROCKETCHAT_ID,
        auth_token=ROCKETCHAT_TOKEN,
        server_url=f"https://{ROCKETCHAT_URL}"
    )

    for dish_path in [dish1_path, dish2_path]:
        with open(dish_path, 'rb') as f:
            print(f"Uploading {dish_path} to Rocket.Chat...")
            response = rocket.files_upload(
                file=f,
                filename=os.path.basename(dish_path),
                description="Today's dish",
                channel=ROCKETCHAT_CHANNEL
            )
        resp_json = response.json()
        if not resp_json.get("success"):
            print(f"Failed to upload {dish_path}: {resp_json}")
            continue
        message_id = resp_json.get("message", {}).get("_id")
        print(f"Successfully posted {dish_path} with message id: {message_id}")

        # Add reactions to help users rate the dish
        emojis = [":thumbsup:", ":thumbsdown:", ":yum:"]
        for emoji in emojis:
            payload = {"emoji": emoji, "messageId": message_id, "shouldReact": True}
            react_response = rocket._post("chat.react", data=payload)
            print(f"Added reaction {emoji} to message {message_id}: {react_response.json()}")

if __name__ == "__main__":
    asd
    speiseplan = get_this_week_speiseplan()
    dish1_path, dish2_path = extract_dishes_today()
    upload_to_github(dish1_path, dish2_path)
    post_to_rocket_chat(dish1_path, dish2_path)
