import os
import time
import datetime
import aiohttp
import aiofiles
import asyncio
import logging
import requests
import subprocess
import re
from urllib.parse import urlparse

from utlis.bar import download_progress_bar

# Setting up logging

logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def get_file_extension(url):
    """Extract file extension from URL or default to mp4"""
    parsed = urlparse(url)
    path = parsed.path
    ext = os.path.splitext(path)[1]
    if ext and ext.startswith('.'):
        logger.debug(f"File extension extracted: {ext[1:].lower()}")
        return ext[1:].lower()
    logger.debug("No file extension found. Defaulting to 'mp4'.")
    return "mp4"  # Default extension


def get_filename_from_url(url):
    """Extract filename from URL or generate a timestamped one"""
    parsed = urlparse(url)
    path = parsed.path
    filename = os.path.basename(path)
    if filename:
        filename = re.sub(r'[\\/:*?"<>|]', '', filename)  # Remove invalid characters
        if not os.path.splitext(filename)[1]:
            filename += f".{get_file_extension(url)}"
        logger.debug(f"Filename extracted: {filename}")
        return filename
    logger.debug("Filename extraction failed. Using timestamp.")
    return time_name()


def time_name():
    """Generate a timestamp-based filename"""
    date = datetime.date.today()
    now = datetime.datetime.now()
    current_time = now.strftime("%H%M%S")
    filename = f"{date} {current_time}.mp4"
    logger.debug(f"Generated timestamp filename: {filename}")
    return filename


def is_direct_media_url(url):
    """Check if URL is likely a direct media file"""
    media_extensions = ['mp4', 'mkv', 'avi', 'mov', 'webm', 'flv', '3gp', 'wmv', 'm4v']
    parsed = urlparse(url)
    path = parsed.path.lower()

    if any(path.endswith(f'.{ext}') for ext in media_extensions):
        logger.debug(f"URL is a direct media file: {url}")
        return True
    logger.debug(f"URL is not a direct media file: {url}")
    return False



async def download_with_progress(url, filename, message):
    """Download a file using aria2c with progress updates"""
    start_time = time.time()
    temp_filename = f"{filename}.download"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

    # Define aria2c command for multi-connection download
    aria2c_cmd = [
        "aria2c",
        "--max-connection-per-server=16",   # 16 connections per server
        "--split=16",                        # Split the file into 16 parts
        "--continue=true",                   # Continue downloading if interrupted
        "--show-files=true",                 # Show file download progress
        "--dir", os.path.dirname(filename),  # Save to specified directory
        "--out", os.path.basename(filename), # Output filename
        url
    ]

    try:
        # Execute aria2c command for download
        process = subprocess.Popen(aria2c_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Capture output from aria2c for progress tracking
        progress_message = await message.edit("⬇️ Starting download with aria2c...")

        while True:
            output = process.stdout.readline()
            if output == b"" and process.poll() is not None:
                break
            if output:
                output = output.decode("utf-8").strip()
                # Log or display output to track progress
                if "progress" in output:
                    # Assuming output contains a percentage progress
                    match = re.search(r'(\d+)%', output)
                    if match:
                        percent = match.group(1)
                        await download_progress_bar(int(percent), 100, progress_message, start_time)

        # Check if file is downloaded successfully
        if os.path.exists(filename):
            return filename
        else:
            logger.error(f"Download failed: {filename} not found.")
            await message.edit(f"❌ Download failed: {filename} not found.")
            return None

    except Exception as e:
        logger.error(f"Download error: {e}")
        await message.edit(f"❌ Download failed: {str(e)}")
        return None

async def download_video(url, cmd, name):
    """Download video using yt-dlp or similar tool with retry mechanism"""
    download_cmd = f'{cmd} -R 25 --fragment-retries 25 --external-downloader aria2c --downloader-args "aria2c: -x 16 -j 32"'
    failed_counter = 0
    max_retries = 10

    logger.info(f"Starting video download with command: {download_cmd}")

    try:
        # First attempt
        k = subprocess.run(download_cmd, shell=True)

        # Retry logic for vision ias and similar sites
        while "visionias" in cmd and k.returncode != 0 and failed_counter < max_retries:
            failed_counter += 1
            await asyncio.sleep(5)
            k = subprocess.run(download_cmd, shell=True)

        # Check for various possible output filenames
        if os.path.isfile(name):
            logger.info(f"Download successful: {name}")
            return name
        elif os.path.isfile(f"{name}.webm"):
            logger.info(f"Download successful: {name}.webm")
            return f"{name}.webm"

        name_base = name.split(".")[0]
        if os.path.isfile(f"{name_base}.mkv"):
            logger.info(f"Download successful: {name_base}.mkv")
            return f"{name_base}.mkv"
        elif os.path.isfile(f"{name_base}.mp4"):
            logger.info(f"Download successful: {name_base}.mp4")
            return f"{name_base}.mp4"
        elif os.path.isfile(f"{name_base}.mp4.webm"):
            logger.info(f"Download successful: {name_base}.mp4.webm")
            return f"{name_base}.mp4.webm"

        # Fallback to the base name
        logger.warning(f"Unable to determine download file: falling back to {name}")
        return name

    except Exception as e:
        logger.error(f"Error during video download: {e}")
        return None

async def aio_download(url, name, extension=".pdf"):
    """Download a file asynchronously using aiohttp"""
    filename = f'{name}{extension}'
    logger.info(f"Starting asynchronous download: {filename}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    f = await aiofiles.open(filename, mode='wb')
                    await f.write(await resp.read())
                    await f.close()
                    logger.info(f"Download completed: {filename}")
                    return filename
                else:
                    logger.error(f"Download failed with status code {resp.status}")
                    return None
    except Exception as e:
        logger.error(f"Error during aio download: {e}")
        return None

# If convert_to_bytes isn’t defined in bar.py (or helpers.py), include it here:
def convert_to_bytes(value, unit):
    """Convert a value with a given unit (e.g., 'MiB', 'GiB') to bytes."""
    unit = unit.lower()
    if unit == 'kib':
        return value * 1024
    elif unit == 'mib':
        return value * 1024**2
    elif unit == 'gib':
        return value * 1024**3
    # Fallback for unknown units: assume bytes.
    return value

async def monitor_aria2c_progress(process, message: Message, start_time):
    """
    Monitor aria2c output, parse progress information, and update the progress bar.

    Adjust the regex below according to your aria2c output format.
    Expected format example: "12.34MiB/123.45MiB" 
    """
    size_pattern = re.compile(r"(\d+\.\d+)([KMG]iB)/(\d+\.\d+)([KMG]iB)")

    while True:
        line = await process.stdout.readline()
        if not line:
            break  # End-of-stream reached
        
        line = line.decode("utf-8").strip()
        logger.debug(f"aria2c output: {line}")

        match = size_pattern.search(line)
        if match:
            current_val, current_unit, total_val, total_unit = match.groups()
            try:
                current_bytes = convert_to_bytes(float(current_val), current_unit)
                total_bytes = convert_to_bytes(float(total_val), total_unit)
                await download_progress_bar(current_bytes, total_bytes, message, start_time)
            except Exception as e:
                logger.error(f"Error parsing aria2c output: {e}")

        await asyncio.sleep(0.5)  # Adjust sleep duration as needed

async def download_with_aria2c(url: str, filename: str, message: Message):
    """
    Download a file with aria2c while updating progress.

    `message` must implement an async edit() method (as with Pyrogram's Message).
    """
    start_time = time.time()
    download_cmd = (
        f"aria2c -x 16 -s 16 -k 1M --max-connection-per-server=16 "
        f"--retry-wait=5 --max-tries=5 --split=16 --out={filename} {url}"
    )
    logger.info(f"Starting download with command: {download_cmd}")

    process = await asyncio.create_subprocess_shell(
        download_cmd,
        stdout=PIPE,
        stderr=asyncio.subprocess.STDOUT  # Merge stderr into stdout for easier monitoring
    )

    # Run the progress monitor concurrently.
    monitor_task = asyncio.create_task(monitor_aria2c_progress(process, message, start_time))

    # Wait for aria2c to finish downloading.
    await process.wait()
    await monitor_task  # Ensure the monitor finishes.

    # Check if download was successful by verifying file existence.
    if os.path.exists(filename):
        logger.info(f"Download successful: {filename}")
        return filename
    else:
        logger.error("Download failed: File not found after download")
        try:
            await message.edit("❌ Download failed.")
        except Exception as e:
            logger.error(f"Failed to update message on error: {e}")
        return None
