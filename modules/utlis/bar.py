import time
import datetime
import logging
from pyrogram.types import Message

logger = logging.getLogger(__name__)

def format_time(seconds):
    """Format seconds into HH:MM:SS format."""
    hours, remainder = divmod(int(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def human_readable_size(size, decimal_places=2):
    """Convert size in bytes to a human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if size < 1024.0 or unit == 'PB':
            break
        size /= 1024.0
    return f"{size:.{decimal_places}f} {unit}"

def create_progress_bar(current, total, length=20):
    """Create an ASCII progress bar."""
    if total == 0:
        filled_length = 0
    else:
        filled_length = int(length * current // total)
    bar = '█' * filled_length + '░' * (length - filled_length)
    return f"[{bar}]"

async def download_progress_bar(current, total, message: Message, start_time):
    """Universal download progress bar function."""
    if total == 0:
        return  # Avoid division by zero

    now = time.time()
    elapsed_time = now - start_time
    percentage = min(100, int(current / total * 100))
    speed = current / elapsed_time if elapsed_time > 0 else 0
    eta = (total - current) / speed if speed > 0 else 0

    progress_text = (
        f"Downloaded: {human_readable_size(current)}/{human_readable_size(total)} ({percentage}%)\n"
        f"Speed: {human_readable_size(speed)}/s\n"
        f"ETA: {format_time(eta)}\n"
        f"Elapsed: {format_time(elapsed_time)}\n"
        f"{create_progress_bar(current, total)}"
    )

    try:
        await message.edit(progress_text)
    except Exception as e:
        logger.error(f"Failed to update download progress message: {e}")

async def upload_progress_bar(current, total, message: Message, start_time):
    """Universal upload progress bar function."""
    if total == 0:
        return  # Avoid division by zero

    now = time.time()
    elapsed_time = now - start_time
    percentage = min(100, int(current / total * 100))
    speed = current / elapsed_time if elapsed_time > 0 else 0
    eta = (total - current) / speed if speed > 0 else 0

    progress_text = (
        f"Uploading: {human_readable_size(current)}/{human_readable_size(total)} ({percentage}%)\n"
        f"Speed: {human_readable_size(speed)}/s\n"
        f"ETA: {format_time(eta)}\n"
        f"Elapsed: {format_time(elapsed_time)}\n"
        f"{create_progress_bar(current, total)}"
    )

    try:
        await message.edit(progress_text)
    except Exception as e:
        logger.error(f"Failed to update upload progress message: {e}")

async def ffmpeg_progress_bar(current_seconds, total_duration, processed_size, message: Message, start_time, estimated_size=None):
    """Universal FFmpeg processing progress bar function."""
    if total_duration == 0:
        return  # Avoid division by zero

    now = time.time()
    elapsed_time = now - start_time
    percentage = min(100, int(current_seconds / total_duration * 100))
    speed = current_seconds / elapsed_time if elapsed_time > 0 else 0
    eta = (total_duration - current_seconds) / speed if speed > 0 else 0
    
    # Calculate estimated total time (ET)
    estimated_total_time = elapsed_time + eta

    progress_text = f"Encoded: {human_readable_size(processed_size)} ({percentage}%)\n"
    progress_text += f"Speed: {speed:.2f}x\n"
    if estimated_size:
        progress_text += f"Est. Size: {human_readable_size(estimated_size)}\n"
    progress_text += f"ET: {format_time(estimated_total_time)}\n"
    progress_text += f"ETA: {format_time(eta)}\n"
    progress_text += f"Elapsed: {format_time(elapsed_time)}\n"
    progress_text += create_progress_bar(current_seconds, total_duration)

    try:
        await message.edit(progress_text)
    except Exception as e:
        logger.error(f"Failed to update FFmpeg progress message: {e}")

# Legacy function for backward compatibility with existing code
async def progress_bar(current, total, message: Message, start):
    """Legacy progress bar function for compatibility with existing code."""
    await upload_progress_bar(current, total, message, start)
