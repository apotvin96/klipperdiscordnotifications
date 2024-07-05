import aiohttp
import asyncio
from io import BytesIO
from PIL import Image
from datetime import datetime, timezone
import os
import logging

##################################################################################
# Replace these with your own values
##################################################################################

DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')  # Example usage with environment variables
KLIPPER_STATUS_URL = "http://127.0.0.1/printer/objects/query?webhooks&print_stats"
CAMERA_SNAPSHOT_URL = "http://127.0.0.1/webcam/?action=snapshot"
INTERVAL_SECONDS = 30  # Check status every 30 seconds - you shouldn't need to adjust this value
NOTIFICATION_INTERVAL = 10  # Progress updates every 10%, Change as needed
THUMBNAIL_URL = "https://direct.path.to.thumbnail.png"  # URL to your thumbnail image
ICON_URL = "https://direct.path.to.icon.png"  # URL to your icon image
EMBED_COLOR = 12582656  # Custom yellow-green color (in Discord's decimal format)
FOOTER_TEXT = "3D Printer Notifications"  # Text shown on the footer of the embed
ROTATE_ANGLE = 180  # Angle to rotate the image, adjust as needed
ENABLE_SNAPSHOTS = True  # Enable or disable snapshots in notifications

##################################################################################
# Configure logging
##################################################################################

logging.basicConfig(level=logging.INFO)  # Adjust level as needed

##################################################################################
# No need to modify anything below this section
##################################################################################

last_reported_progress = -1
estimated_total_duration = None
current_print_filename = None
total_layers = None
current_layer = None

notification_flags = {
    "started": False,
    "completed": False,
    "cancelled": False,
    "idle": False
}

async def get_klipper_status(session):
    try:
        async with session.get(KLIPPER_STATUS_URL) as response:
            response.raise_for_status()
            return await response.json()
    except aiohttp.ClientError as e:
        print(f"Error fetching Klipper status: {e}")
        return None

async def get_camera_snapshot(session):
    try:
        async with session.get(CAMERA_SNAPSHOT_URL) as response:
            response.raise_for_status()
            return await response.read()
    except aiohttp.ClientError as e:
        print(f"Error fetching camera snapshot: {e}")
        return None

def rotate_image(image_data):
    try:
        image = Image.open(BytesIO(image_data))
        rotated_image = image.rotate(ROTATE_ANGLE)  # Rotate by specified degrees
        output = BytesIO()
        rotated_image.save(output, format='JPEG')
        return output.getvalue()
    except Exception as e:
        print(f"Error rotating image: {e}")
        return None

async def send_discord_notification(session, title, content, image_data=None):
    data = {
        "embeds": [
            {
                "title": title,
                "description": content,
                "color": EMBED_COLOR,
                "thumbnail": {
                    "url": THUMBNAIL_URL
                },
                "footer": {
                    "text": FOOTER_TEXT,
                    "icon_url": ICON_URL
                },
                "timestamp": datetime.now(timezone.utc).isoformat()  # Current timestamp in ISO 8601 format
            }
        ]
    }
    headers = {
        "Content-Type": "application/json"
    }

    try:
        if ENABLE_SNAPSHOTS and image_data:
            rotated_image_data = rotate_image(image_data)
            if rotated_image_data:
                # Send the snapshot image first and get the URL
                with aiohttp.MultipartWriter('form-data') as mpwriter:
                    file_part = mpwriter.append(rotated_image_data)
                    file_part.set_content_disposition('form-data', name='file', filename='snapshot.jpg')

                    async with session.post(DISCORD_WEBHOOK_URL, data=mpwriter) as response:
                        response.raise_for_status()
                        result = await response.json()
                        if 'attachments' in result:
                            data['embeds'][0]['image'] = {'url': result['attachments'][0]['url']}
                        return  # Stop here to prevent double posting

        async with session.post(DISCORD_WEBHOOK_URL, headers=headers, json=data) as response:
            response.raise_for_status()
    except aiohttp.ClientError as e:
        print(f"Error sending Discord notification: {e}")

def calculate_progress(print_stats):
    global estimated_total_duration, total_layers, current_layer

    print_duration = print_stats.get('print_duration', 0)
    total_layers = print_stats.get('info', {}).get('total_layer', None)
    current_layer = print_stats.get('info', {}).get('current_layer', None)

    if estimated_total_duration is None:
        estimated_total_duration = print_stats.get('total_duration', 1)
    
    if total_layers and current_layer:
        progress_percentage = (current_layer / total_layers) * 100
        estimated_total_duration = (print_duration / progress_percentage) * 100 if progress_percentage > 0 else estimated_total_duration
        remaining_time = max(0, estimated_total_duration - print_duration)
        return progress_percentage, print_duration, remaining_time
    
    if estimated_total_duration > 0:
        progress_percentage = (print_duration / estimated_total_duration) * 100
        remaining_time = max(0, estimated_total_duration - print_duration)
        return progress_percentage, print_duration, remaining_time
    
    return 0, print_duration, 0

def format_time(seconds):
    minutes, secs = divmod(seconds, 60)
    hours, mins = divmod(minutes, 60)
    return f"{int(hours)}h {int(mins)}m {int(secs)}s"

async def check_printer_status(session):
    global last_reported_progress, estimated_total_duration, current_print_filename, total_layers, current_layer, notification_flags
    status = await get_klipper_status(session)
    if status:
        print_stats = status['result']['status'].get('print_stats', {})
        printer_state = print_stats.get('state', 'unknown')
        progress_percentage, print_duration, remaining_time = calculate_progress(print_stats)  # Retrieve progress_percentage and print_duration

        if printer_state == "printing":
            if last_reported_progress == -1:
                # New print started
                current_print_filename = print_stats.get('filename', 'Unknown')
                content = f"**Filename:** {current_print_filename}"
                snapshot = await get_camera_snapshot(session) if ENABLE_SNAPSHOTS else None
                if not notification_flags["started"]:
                    await send_discord_notification(session, f"{current_print_filename} has started printing", content, snapshot)
                    notification_flags["started"] = True
                last_reported_progress = 0
                notification_flags["completed"] = False
                notification_flags["cancelled"] = False
                notification_flags["idle"] = False

            elif progress_percentage >= last_reported_progress + NOTIFICATION_INTERVAL and progress_percentage < 100:
                # Progress update
                elapsed_time = print_duration
                content = (f"**Filename:** {current_print_filename}\n"
                           f"**Progress:** {progress_percentage:.2f}%\n"
                           f"**Elapsed:** {format_time(elapsed_time)}\n"
                           f"**Remaining:** {format_time(remaining_time)}\n"
                           f"**Current Layer:** {current_layer}/{total_layers}")
                snapshot = await get_camera_snapshot(session) if ENABLE_SNAPSHOTS else None
                await send_discord_notification(session, "Print Progress Update", content, snapshot)
                last_reported_progress = progress_percentage

        elif printer_state == "complete" and not notification_flags["completed"]:
            # Print completed
            elapsed_time = print_duration
            content = (f"{current_print_filename} **completed!**\n"
                       f"**Total Duration:** {print_stats.get('total_duration', 'Unknown')} seconds\n"
                       f"**Filament Used:** {print_stats.get('filament_used', 'Unknown')} mm\n"
                       f"**Elapsed Time:** {format_time(elapsed_time)}")
            snapshot = await get_camera_snapshot(session) if ENABLE_SNAPSHOTS else None
            await send_discord_notification(session, "Print Completed", content, snapshot)
            last_reported_progress = 100
            estimated_total_duration = None
            total_layers = None
            current_layer = None
            notification_flags["completed"] = True
            notification_flags["started"] = False

        elif printer_state == "cancelled" and not notification_flags["cancelled"]:
            # Print cancelled
            content = f"{current_print_filename} cancelled."
            snapshot = await get_camera_snapshot(session) if ENABLE_SNAPSHOTS else None
            await send_discord_notification(session, "Print Cancelled", content, snapshot)
            last_reported_progress = -1
            estimated_total_duration = None
            total_layers = None
            current_layer = None
            notification_flags["cancelled"] = True
            notification_flags["started"] = False

        elif printer_state == "idle" and not notification_flags["idle"]:
            # Printer idle
            await send_discord_notification(session, "Printer Idle", "Printer is now idle.")
            last_reported_progress = -1
            estimated_total_duration = None
            total_layers = None
            current_layer = None
            notification_flags["idle"] = True
            notification_flags["started"] = False

    await asyncio.sleep(INTERVAL_SECONDS)
    asyncio.create_task(check_printer_status(session))

async def main():
    async with aiohttp.ClientSession() as session:
        task = asyncio.create_task(check_printer_status(session))
        await task

if __name__ == "__main__":
    asyncio.run(main())
