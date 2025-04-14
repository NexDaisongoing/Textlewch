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

from bar import download_progress_bar

logger = logging.getLogger(__name__)

def get_file_extension(url):
    """Extract file extension from URL or default to mp4"""
    parsed = urlparse(url)
    path = parsed.path
    ext = os.path.splitext(path)[1]
    if ext and ext.startswith('.'):
        return ext[1:].lower()
    return "mp4"  # Default extension


def get_filename_from_url(url):
    """Extract filename from URL or generate a timestamped one"""
    parsed = urlparse(url)
    path = parsed.path
    filename = os.path.basename(path)
    if filename:
        # Clean the filename
        filename = re.sub(r'[\\/:*?"<>|]', '', filename)
        if not os.path.splitext(filename)[1]:
            filename += f".{get_file_extension(url)}"
        return filename
    return time_name()


def time_name():
    """Generate a timestamp-based filename"""
    date = datetime.date.today()
    now = datetime.datetime.now()
    current_time = now.strftime("%H%M%S")
    return f"{date} {current_time}.mp4"


def is_direct_media_url(url):
    """Check if URL is likely a direct media file"""
    media_extensions = ['mp4', 'mkv', 'avi', 'mov', 'webm', 'flv', '3gp', 'wmv', 'm4v']
    parsed = urlparse(url)
    path = parsed.path.lower()
    
    # Check if URL ends with a media extension
    if any(path.endswith(f'.{ext}') for ext in media_extensions):
        return True
    
    # Check if URL has media content type (would require a HEAD request in practice)
    # This is a simplified check that looks for extension in the path
    return any(f'.{ext}' in path for ext in media_extensions)


async def download_with_progress(url, filename, message):
    """Download a file with progress updates"""
    start_time = time.time()
    temp_filename = f"{filename}.download"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    
    try:
        with requests.get(url, headers=headers, stream=True, allow_redirects=True) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            
            if total_size == 0:
                await message.edit("Unknown file size. Downloading...")
            
            downloaded = 0
            last_update_time = time.time()
            progress_message = await message.edit("⬇️ Starting download...")
            
            with open(temp_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # Update progress message every 3 seconds to avoid hitting API limits
                        if time.time() - last_update_time > 3:
                            await download_progress_bar(downloaded, total_size, progress_message, start_time)
                            last_update_time = time.time()
                            
        # Rename the completed download to the final filename
        os.rename(temp_filename, filename)
        return filename
                                
    except Exception as e:
        logger.error(f"Download error: {e}")
        await message.edit(f"❌ Download failed: {str(e)}")
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
        return None


async def aio_download(url, name, extension=".pdf"):
    """Download a file asynchronously using aiohttp"""
    filename = f'{name}{extension}'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                f = await aiofiles.open(filename, mode='wb')
                await f.write(await resp.read())
                await f.close()
    return filename


async def download_video(url, cmd, name):
    """Download video using yt-dlp or similar tool with retry mechanism"""
    download_cmd = f'{cmd} -R 25 --fragment-retries 25 --external-downloader aria2c --downloader-args "aria2c: -x 16 -j 32"'
    failed_counter = 0
    max_retries = 10
    
    print(download_cmd)
    logging.info(download_cmd)
    
    # First attempt
    k = subprocess.run(download_cmd, shell=True)
    
    # Retry logic for vision ias and similar sites
    while "visionias" in cmd and k.returncode != 0 and failed_counter < max_retries:
        failed_counter += 1
        await asyncio.sleep(5)
        k = subprocess.run(download_cmd, shell=True)
    
    try:
        # Check for various possible output filenames
        if os.path.isfile(name):
            return name
        elif os.path.isfile(f"{name}.webm"):
            return f"{name}.webm"
        
        name_base = name.split(".")[0]
        if os.path.isfile(f"{name_base}.mkv"):
            return f"{name_base}.mkv"
        elif os.path.isfile(f"{name_base}.mp4"):
            return f"{name_base}.mp4"
        elif os.path.isfile(f"{name_base}.mp4.webm"):
            return f"{name_base}.mp4.webm"
        
        # Fallback to the base name
        return name
    except Exception as e:
        logger.error(f"Error finding downloaded file: {e}")
        # Return a best guess filename
        return os.path.splitext(name)[0] + ".mp4"