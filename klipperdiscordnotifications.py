import requests
import json
from io import BytesIO
from PIL import Image
from datetime import datetime, timezone
import sched
import time

##################################################################################
# Replace these with your own values
##################################################################################

DISCORD_WEBHOOK_URL = "YOUR_WEBHOOK_URL_HERE"
KLIPPER_STATUS_URL = "http://127.0.0.1/printer/objects/query?webhooks&print_stats"
CAMERA_SNAPSHOT_URL = "http://127.0.0.1/webcam/?action=snapshot"
INTERVAL_SECONDS = 10  # Check status every 10 seconds - you shouldn't need to adjust this value
NOTIFICATION_INTERVAL = 10  # Progress updates every 10%, Change as needed
THUMBNAIL_URL = "https://direct.path.to.thumbnail.png"  # URL to your thumbnail image
ICON_URL = "https://direct.path.to.icon.png"  # URL to your icon image
EMBED_COLOR = 12582656  # Custom yellow-green color (in Discord's decimal format)
FOOTER_TEXT = "3D Printer Notifications"  # Text shown on the footer of the embed
ROTATE_ANGLE = 180  # Angle to rotate the image, adjust as needed
ENABLE_SNAPSHOTS = True  # Enable or disable snapshots in notifications

##################################################################################
# No need to modify anything below this section
##################################################################################

last_reported_progress = -1
estimated_total_duration = None
current_print_filename = None
total_layers = None
current_layer = None

scheduler = sched.scheduler(time.time, time.sleep)

def get_klipper_status():
    try:
        response = requests.get(KLIPPER_STATUS_URL)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching Klipper status: {e}")
        return None

def get_camera_snapshot():
    try:
        response = requests.get(CAMERA_SNAPSHOT_URL)
        response.raise_for_status()
        return response.content
    except requests.RequestException as e:
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

def send_discord_notification(title, content, image_data=None):
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
                files = {
                    "file": ("snapshot.jpg", rotated_image_data, "image/jpeg")
                }
                data["embeds"][0]["image"] = {
                    "url": "attachment://snapshot.jpg"
                }
                response = requests.post(DISCORD_WEBHOOK_URL, data={"payload_json": json.dumps(data)}, files=files)
            else:
                response = requests.post(DISCORD_WEBHOOK_URL, headers=headers, data=json.dumps(data))
        else:
            response = requests.post(DISCORD_WEBHOOK_URL, headers=headers, data=json.dumps(data))
        
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error sending Discord notification: {e}")
        return response.status_code

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

def check_printer_status():
    global last_reported_progress, estimated_total_duration, current_print_filename, total_layers, current_layer
    status = get_klipper_status()
    if status:
        print_stats = status['result']['status'].get('print_stats', {})
        printer_state = print_stats.get('state', 'unknown')
        progress_percentage, print_duration, remaining_time = calculate_progress(print_stats)  # Retrieve progress_percentage and print_duration
        
        if printer_state == "printing":
            if last_reported_progress == -1:
                # New print started
                current_print_filename = print_stats.get('filename', 'Unknown')
                content = f"**Filename:** {current_print_filename}"
                snapshot = get_camera_snapshot() if ENABLE_SNAPSHOTS else None
                send_discord_notification(f"{current_print_filename} has started printing", content, snapshot)
                last_reported_progress = 0
            else:
                # Progress update
                elapsed_time = print_duration
                content = f"**Filename:** {current_print_filename}\n**Progress:** {progress_percentage:.2f}%\n**Elapsed:** {format_time(elapsed_time)}\n**Remaining:** {format_time(remaining_time)}\n**Current Layer:** {current_layer}/{total_layers}"
                
                # Send notification for every 10% increment passed since last report
                if int(progress_percentage) >= last_reported_progress + NOTIFICATION_INTERVAL:
                    snapshot = get_camera_snapshot() if ENABLE_SNAPSHOTS else None
                    send_discord_notification("Print Progress Update", content, snapshot)
                    last_reported_progress = int(progress_percentage // NOTIFICATION_INTERVAL) * NOTIFICATION_INTERVAL

        elif printer_state == "complete" and last_reported_progress != 100:
            # Print completed
            elapsed_time = print_duration
            content = f"{current_print_filename} **completed!**\n**Total Duration:** {print_stats.get('total_duration', 'Unknown')} seconds\n**Filament Used:** {print_stats.get('filament_used', 'Unknown')} mm\n**Elapsed Time:** {format_time(elapsed_time)}"
            snapshot = get_camera_snapshot() if ENABLE_SNAPSHOTS else None
            send_discord_notification("Print Completed", content, snapshot)
            last_reported_progress = 100
            estimated_total_duration = None
            total_layers = None
            current_layer = None

        elif printer_state == "cancelled" and last_reported_progress != -1:
            # Print cancelled
            content = f"{current_print_filename} cancelled."
            snapshot = get_camera_snapshot() if ENABLE_SNAPSHOTS else None
            send_discord_notification("Print Cancelled", content, snapshot)
            last_reported_progress = -1
            estimated_total_duration = None
            total_layers = None
            current_layer = None

        elif printer_state == "idle" and last_reported_progress != -1:
            # Printer idle
            send_discord_notification("Printer Idle", "Printer is now idle.")
            last_reported_progress = -1
            estimated_total_duration = None
            total_layers = None
            current_layer = None

    scheduler.enter(INTERVAL_SECONDS, 1, check_printer_status)

def main():
    scheduler.enter(0, 1, check_printer_status)
    scheduler.run()

if __name__ == "__main__":
    main()
