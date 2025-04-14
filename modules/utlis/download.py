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
    """Download a file with progress updates using aria2c in Google Colab"""
    start_time = time.time()

    # Optimized aria2c command with parallel connections and chunking
    download_cmd = f'aria2c -x 16 -s 16 -k 1M --max-connection-per-server=16 --retry-wait=5 --max-tries=5 --split=16 --out={filename} {url}'

    try:
        # Start the aria2c download process
        process = subprocess.Popen(
            download_cmd, 
            shell=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE
        )

        logger.info(f"Started download with command: {download_cmd}")

        while True:
            output = process.stdout.readline().decode('utf-8')
            error_output = process.stderr.readline().decode('utf-8')

            if output == '' and error_output == '' and process.poll() is not None:
                logger.info("Download completed")
                break

            if output:
                # Log download progress
                logger.debug(f"aria2c output: {output}")

            if error_output:
                # Capture and log errors from aria2c
                logger.error(f"aria2c error: {error_output}")

        # Check if the download was successful and rename the file
        if os.path.exists(filename):
            logger.info(f"Download successful: {filename}")
            return filename
        else:
            logger.error("Download failed: File not found after download")
            await message.edit("❌ Download failed.")
            return None

    except Exception as e:
        logger.error(f"Error during download: {e}")
        await message.edit(f"❌ Download failed: {str(e)}")
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