import os
import logging
from pyrogram.types import Message

from utlis.download import download_with_progress, get_filename_from_url
from utlis.process import process_with_ffmpeg
from utlis.upload import send_vid

logger = logging.getLogger(__name__)

async def handle_direct_link(m: Message, url, custom_filename=None, custom_ffmpeg=None, caption=None):
    """Handle direct media URLs by downloading and processing them"""
    # Extract filename from URL or use custom filename if provided
    filename = custom_filename or get_filename_from_url(url)
    
    download_msg = await m.reply_text(f"**⬇️ Starting download:** `{filename}`")
    
    # Download the file with progress updates
    downloaded_file = await download_with_progress(url, filename, download_msg)
    
    if not downloaded_file:
        await download_msg.edit("❌ Download failed")
        return
    
    # If custom FFmpeg processing is needed, process the downloaded file
    if custom_ffmpeg and custom_ffmpeg.lower() != "skip":
        processed_file = await process_with_ffmpeg(downloaded_file, m, download_msg, custom_ffmpeg)
        if processed_file != downloaded_file:
            downloaded_file = processed_file
    else:
        await download_msg.edit(f"✅ Download completed: `{filename}`")
    
    # Upload the final file
    thumb = "no"  # Default thumbnail setting
    caption = caption or f"**File:** `{filename}`"
    await send_vid(None, m, caption, downloaded_file, thumb, filename, download_msg)


async def process_direct_url(url, m, caption=None, custom_ffmpeg=None):
    """Legacy function for backwards compatibility"""
    await handle_direct_link(m, url, None, custom_ffmpeg, caption)
