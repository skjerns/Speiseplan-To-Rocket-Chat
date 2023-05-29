# Speiseplan-To-Rocket-Chat

Publish weekly Cafeteria Speiseplan to our Rocket.Chat

This repository fetches the current cafeteria menu from our intranet, parses the PDF, extracts the menu items and formats it nicely into something readable.
It then connects to our internal Rocket.Chat instance and posts the resulting menu to the respective channel. 

Update 2023: From now on it will just post the image to the channel.

The script runs every week on Monday at 10:00 using GitHub Actions.

<img src="https://user-images.githubusercontent.com/14980558/215501967-505db5ee-9316-479a-b125-9a9049b1cb7f.png" data-canonical-src="https://user-images.githubusercontent.com/14980558/215501967-505db5ee-9316-479a-b125-9a9049b1cb7f.png" width="400" />
