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
  ROCKETCHAT_URL, ROCKETCHAT_ID, ROCKETCHAT_TOKEN
"""
import os
import re
import time
import glob
import locale
import subprocess
from datetime import datetime
from PIL import Image
from rocketchat_API.rocketchat import RocketChat

# Load configuration either from env.py or environment variables
try:
    from env import ROCKETCHAT_URL, ROCKETCHAT_ID, ROCKETCHAT_TOKEN
except ImportError:
    ROCKETCHAT_URL = os.environ.get("ROCKETCHAT_URL")
    ROCKETCHAT_ID = os.environ.get("ROCKETCHAT_ID")
    ROCKETCHAT_TOKEN = os.environ.get("ROCKETCHAT_TOKEN")


tage = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'FEHLER', 'FEHLER']


def get_this_week_speiseplan():
    """
    Locate the most recent weekly speiseplan PNG in the './speiseplaene' directory.
    This PNG is assumed to be the menu for the entire week.

    Returns:
        The file path of the weekly speiseplan.
    """
    files = glob.glob(os.path.join("speiseplaene", "*.png"))
    if not files:
        raise FileNotFoundError("No weekly menu PNG found in './speiseplaene'.")
    # Choose the most recently created file
    latest_file = max(files, key=os.path.getctime)
    print(f"Found weekly speiseplan: {latest_file}")
    return latest_file


from datetime import datetime, timedelta

def date_from_weekday(target_weekday):
    """
    Get the date of a specific weekday in the current week.

    Parameters:
        target_weekday (int): The target weekday (0=Monday, 1=Tuesday, ..., 6=Sunday).

    Returns:
        datetime.date: The date of the target weekday.
    """
    today = datetime.now()
    current_weekday = today.weekday()  # Monday=0, ..., Sunday=6
    delta_days = target_weekday - current_weekday
    target_date = today + timedelta(days=delta_days)
    return target_date.date()

# Example: Get the date of this week's Friday (5)

def extract_dishes_today(speiseplan_png, weekday=None):
    """
    Crop out today's two dish images from the weekly speiseplan.

    Assumptions:
      - The speiseplan image is organized into five horizontal rows (Monday-Friday).
      - Each row is split into two halves for the two dish options.

    Returns:
       A tuple (dish1_path, dish2_path) with the filenames of the two cropped images.
       If today is Saturday or Sunday, returns (None, None).
    """
    if weekday is None:
        day = datetime.now()
        weekday = day.weekday()  # Monday=0, Tuesday=1, ... Sunday=6

    else:
        day = date_from_weekday(weekday)

    if weekday >= 5:
        print("Today is weekend. No dishes to extract.")
        exit()

    image = Image.open(speiseplan_png)
    width, height = image.size

    padding_top = 265
    padding_left = 118
    padding = 9

    box_height = 90
    box_width = 210


    # Assume five equal horizontal rows in the image
    row_height = height // 5
    top = weekday * row_height
    bottom = (weekday + 1) * row_height

    # Crop dish1 (left half) and dish2 (right half)
    top = padding_top + weekday*(box_height+padding)
    bottom = top+box_height

    left1 = padding_left
    right1 = left1+box_width
    dish1 = image.crop((left1, top, right1, bottom))

    left2 = right1+padding
    right2 = left2+box_width
    dish2 = image.crop((left2, top, right2, bottom))

    today_str = day.strftime("%Y-%m-%d")
    dish1_path = f"./dishes/{today_str}_dish1.png"
    dish2_path = f"./dishes/{today_str}_dish2.png"

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


    base_url = 'https://raw.githubusercontent.com/skjerns/Speiseplan-To-Rocket-Chat/main/dishes'
    urls = [f'{base_url}/{os.path.basename(file)}' for file in [dish1_path, dish2_path]]
    return  urls

def post_to_rocket_chat(urls):
    """
    Post the dish images to Rocket.Chat and add emoji reactions to each post.

    Each dish is uploaded as a file to the configured Rocket.Chat channel.
    After posting, several reactions (e.g., :thumbsup:, :thumbsdown:, :yum:) are added.
    """
    assert isinstance(urls, list)

    rocket = RocketChat(user_id=ROCKETCHAT_ID,
                        auth_token=ROCKETCHAT_TOKEN,
                        server_url=f'https://{ROCKETCHAT_URL}')


    for i, url in enumerate(urls):
        date_str = os.path.basename(url).split('_')[0]
        parsed_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        german_weekday = tage[parsed_date.weekday()]

        names = ['Fleisch/Fisch', 'Veggy']
        msg = (f'**{german_weekday} {i+1}**\t- {names[i]} - {parsed_date.strftime("%d. %b")}. '
              f'\nBenutze die Emojis um zu bewerten.\n\n{url}')

        time.sleep(1)
        res = rocket.chat_post_message(msg,
                                       emoji=[':cut_of_meat:', ':leafy_green:'][i],
                                       channel='Speiseplan-feedback',
                                       # alias='SpeiseplanBot',
                                       # previewUrls=[url]
                                       )

        resp_json = res.json()
        if not resp_json.get("success"):
            print(f"Failed to upload {url}: {resp_json}")
            continue

        message_id = resp_json.get("message", {}).get("_id")
        print(f"Successfully posted {url} with message id: {message_id}")

        # Add reactions to help users rate the dish
        emojis = ['frowning2', 'neutral_face', 'slightly_smiling_face', 'smile', 'star_struck']
        i = 0
        while i<len(emojis):
            time.sleep(0.5)
            emoji = emojis[i]
            res = rocket.chat_react(message_id, emoji=emoji)
            res_json = res.json()
            if 'error' in (err:=res_json) and 'error-too-many-requests' in err:
                wait = int(re.search(r'\b\d+\b(?=\s+seconds)', err).group())
                time.sleep(wait)
                print(f'too many reqeusts, wait {wait}')
                continue
            elif  'error'  in err:
                raise Exception(f'could not react: {err}')
            i += 1
            print(f"Added reaction {emoji} to message {message_id}: {res.json()}")

if __name__ == "__main__":

    speiseplan_png = get_this_week_speiseplan()
    dish1_path, dish2_path = extract_dishes_today(speiseplan_png)
    urls = upload_to_github(dish1_path, dish2_path)
    post_to_rocket_chat(urls)
