import os
import time
import datetime
import aiohttp
import aiofiles
import asyncio
import logging
import subprocess
import concurrent.futures
import re
import sys
from urllib.parse import urlparse
from pathlib import Path
from vars import API_ID, API_HASH, BOT_TOKEN, WEBHOOK, PORT

from pyromod import Client
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup

# Import utility and modular functions
from utlis.bar import progress_bar, format_time, human_readable_size
from utlis.download import (
    download_with_progress, 
    aio_download, 
    download_video, 
    is_direct_media_url, 
    get_filename_from_url
    download_with_aria2c
)
from utlis.process import process_with_ffmpeg, get_duration, generate_thumbnail
from utlis.upload import send_doc, send_vid
from utlis.direct_link import handle_direct_link, process_direct_url

from handlers import register_handlers

# Configure logging
logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global variables for tracking download/processing progress
download_progress = {}
processing_progress = {}

def exec(cmd):
    """Execute a shell command and return its output."""
    process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output = process.stdout.decode()
    error = process.stderr.decode()
    if error:
        logger.error(f"Command error: {error}")
    return output


def parse_vid_info(info):
    """Extract video stream information from ffmpeg output."""
    info = info.strip().split("\n")
    new_info = []
    temp = []
    for i in info:
        if "[" not in i and "---" not in i:
            i = re.sub(r"\s{2,}", " ", i).strip()
            parts = i.split("|")[0].split(" ", 2)
            try:
                if "RESOLUTION" not in parts[2] and parts[2] not in temp and "audio" not in parts[2]:
                    temp.append(parts[2])
                    new_info.append((parts[0], parts[2]))
            except IndexError:
                pass
    return new_info


async def run(cmd):
    """Run a shell command asynchronously and return its output."""
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error(f"Command failed: {stderr.decode()}")
        return None
    return stdout.decode()


# Initialize bot with Pyrogram
bot = Client(
    "bot_session",
    api_id=os.getenv("API_ID"),
    api_hash=os.getenv("API_HASH"),
    bot_token=os.getenv("BOT_TOKEN")
)

register_handlers(bot)

@bot.on_message(filters.command("start"))
async def start_command(client, message: Message):
    """Handle the /start command."""
    await message.reply_text(
        "Welcome! Use /help to see available commands.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Support", url="https://t.me/support")]]
        )
    )


@bot.on_message(filters.command("direct") & filters.regex(r'https?://'))
async def direct_command(client, message: Message):
    """Handle the /direct command to process URLs."""
    url = re.search(r'(https?://\S+)', message.text).group(1)
    if not is_direct_media_url(url):
        await message.reply_text("The provided URL is not a valid media URL.")
        return

    custom_ffmpeg = None
    ffmpeg_match = re.search(r'--ffmpeg\s+"([^"]+)"', message.text)
    if ffmpeg_match:
        custom_ffmpeg = ffmpeg_match.group(1)

    await handle_direct_link(message, url, custom_ffmpeg)


@bot.on_message(filters.command("upload"))
async def upload_command(client, message: Message):
    """Handle the /upload command to process user-uploaded files."""
    editable = await message.reply_text("Send me a TXT file with URLs.")
    input: Message = await client.listen(editable.chat.id)
    file_path = await input.download()

    try:
        async with aiofiles.open(file_path, "r") as file:
            content = await file.read()
        urls = content.strip().split("\n")
        await editable.edit(f"Found {len(urls)} URLs. Processing them now...")
    except Exception as e:
        logger.error(f"Error reading file: {str(e)}")
        await editable.edit("Invalid file or content.")
        return

    for idx, url in enumerate(urls, start=1):
        await editable.edit(f"Processing URL {idx}/{len(urls)}: {url}")
        try:
            filename = get_filename_from_url(url)
            await download_with_progress(url, filename, message)
            await send_doc(client, message.chat.id, filename)
        except Exception as e:
            logger.error(f"Failed to process URL {url}: {str(e)}")
            await message.reply_text(f"Failed to process URL: {url}")

        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

    await editable.edit("All URLs processed successfully!")

@bot.on_message(filters.command("leech") & filters.regex(r'https?://'))
async def leech_command(client, message: Message):
    """Handle the /leech command to download, process, and upload media."""

    # Extract the URL from the user's message.
    url = re.search(r'(https?://\S+)', message.text).group(1)
    
    # Default to None if no custom FFmpeg is provided
    custom_ffmpeg = None
    ffmpeg_match = re.search(r'--ffmpeg\s+"([^"]+)"', message.text)
    if ffmpeg_match:
        custom_ffmpeg = ffmpeg_match.group(1)

    # Send the initial reply message and store it as the Progress Message
    reply = await message.reply_text("Fetching file...")  # This is the Progress Message

    try:
        # Step 1: Get the filename from the URL
        filename = get_filename_from_url(url)
        await reply.edit(f"Downloading:\n`{filename}`")  # Update the progress message with filename.

        # Step 2: Download the file with progress
        await download_with_aria2c(url, filename, reply)  # The progress of download is reflected in the Progress Message.

        # Step 3: Process with FFmpeg (using custom_ffmpeg if provided)
        if custom_ffmpeg:
            await reply.edit(f"Processing with custom FFmpeg command: `{custom_ffmpeg}`")
        else:
            await reply.edit("Processing with default FFmpeg settings...")
        
        processed_path = await process_with_ffmpeg(filename, message, reply, custom_ffmpeg)  # Process file

        # Step 4: Upload the processed file
        await reply.edit("Uploading processed file...")  # Update message with uploading progress
        await send_doc(client, message.chat.id, processed_path)  # Upload the file

        # Final completion message
        await reply.edit("✅ Done! File uploaded.")  # Mark as completed.

    except Exception as e:
        # Handle any errors
        logger.error(f"Leech Error: {e}")
        await reply.edit(f"❌ Error:\n{e}")  # Update the progress message with the error message.

    finally:
        # Clean up by removing the downloaded and processed files after completion.
        for f in [filename, processed_path if 'processed_path' in locals() else None]:
            if f and os.path.exists(f):
                os.remove(f)

async def main():
    if WEBHOOK:
        # Start the web server
        app = await web_server()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", PORT)
        await site.start()
        print(f"Web server started on port {PORT}")

if __name__ == "__main__":
    print("""
    █░█░█ █▀█ █▀█ █▀▄ █▀▀ █▀█ ▄▀█ █▀▀ ▀█▀     ▄▀█ █▀ █░█ █░█ ▀█▀ █▀█ █▀ █░█   
    ▀▄▀▄▀ █▄█ █▄█ █▄▀ █▄▄ █▀▄ █▀█ █▀░ ░█░     █▀█ ▄█ █▀█ █▄█ ░█░ █▄█ ▄█ █▀█ """)

    # Start the bot and web server concurrently
    async def start_bot():
        await bot.start()

    async def start_web():
        await main()

    loop = asyncio.get_event_loop()
    try:
        # Create tasks to run bot and web server concurrently
        loop.create_task(start_bot())
        loop.create_task(start_web())

        # Keep the main thread running until all tasks are complete
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        # Cleanup
        loop.stop()