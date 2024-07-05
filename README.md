# 3D Printer Discord Notification Bot for Klipper Firmware

This script monitors your 3D printer's status and sends notifications to a Discord channel via a webhook. Notifications include print start, print progress updates, print completion, cancellation, and idle states. Optionally, snapshots of the print can be included in the notifications.

![Screenshot from 2024-07-04 12-46-03](https://github.com/ejahdev/klipperdiscordnotifications/assets/116228748/94080052-eb0d-49a7-88b2-2b9c808524f4)

## Features

- Sends notifications to Discord using webhooks.
- Monitors print progress and provides updates at specified intervals.
- Includes snapshots of the print in the notifications.
- Ensures notifications for each state are sent only once.

## Requirements

- Python 3.7+
- aiohttp
- pillow

## Installation

1. Clone the repository:

    ```sh
    git clone https://github.com/yourusername/3d-printer-discord-notify.git
    cd 3d-printer-discord-notify
    ```

2. Install the required dependencies:

    ```sh
    pip install -r requirements.txt
    ```

## Configuration

Edit the `discordnotify.py` script to replace the placeholder values with your actual configurations:

```python
DISCORD_WEBHOOK_URL = "YOUR_WEBHOOK_URL_HERE"
KLIPPER_STATUS_URL = "http://127.0.0.1/printer/objects/query?webhooks&print_stats"
CAMERA_SNAPSHOT_URL = "http://127.0.0.1/webcam/?action=snapshot"
THUMBNAIL_URL = "https://direct.path.to.thumbnail.png"
ICON_URL = "https://direct.path.to.icon.png"
```
## Usage

Run the script using Python:
```python
python discordnotify.py
```
The script will start monitoring the printer status and sending notifications to the configured Discord webhook.

## Setting up Klipper for Layer Information

To enable accurate progress updates and layer information in your notifications, follow the steps below to configure Klipper:

1. Modify Klipper Configuration File:
   Edit your Klipper printer configuration file (typically `printer.cfg`).

2. Enable Progress and Layer Information:
   Add the following lines to your Klipper configuration file to enable layer progress reporting:

   ```sh
   [printer]
   progress_log: true
   ```
3. Integrate with Slicer (Mainsail Documentation):
   Follow the instructions in the [Mainsail Documentation for your slicer](https://docs.mainsail.xyz/overview/slicer) to configure it to send layer         information to klipper.

4. Restart Klipper:
   After editing the Klipper configuration file and setting up youur slicer integration, restart Klipper for the changes to take effect.
