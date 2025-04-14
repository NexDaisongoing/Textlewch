import os
import time
import datetime
import aiohttp
import aiofiles
import asyncio
import logging
import requests
import tgcrypto
import subprocess
import concurrent.futures
import re
import sys
import threading
from urllib.parse import urlparse
from pathlib import Path

from utils import progress_bar

from pyrogram import Client, filters
from pyrogram.types import Message

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global variables for tracking download/processing progress
download_progress = {}
processing_progress = {}
failed_counter = 0


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


def duration(filename):
    """Get the duration of a media file using ffprobe"""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", filename],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        return float(result.stdout)
    except Exception as e:
        logger.error(f"Error getting duration: {e}")
        return 0


def exec(cmd):
    """Execute a command and return its output"""
    process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output = process.stdout.decode()
    error = process.stderr.decode()
    if error:
        logger.error(f"Command error: {error}")
    return output


def pull_run(work, cmds):
    """Run multiple commands in parallel using ThreadPoolExecutor"""
    with concurrent.futures.ThreadPoolExecutor(max_workers=work) as executor:
        logger.info("Waiting for tasks to complete")
        fut = executor.map(exec, cmds)


async def monitor_ffmpeg_progress(process, message, filename, total_duration):
    """Monitor FFmpeg progress and update the message"""
    pattern = re.compile(r"time=(\d+):(\d+):(\d+)\.(\d+)")
    last_update_time = time.time()
    start_time = time.time()
    
    while process.poll() is None:
        if process.stderr:
            line = process.stderr.readline().decode('utf-8', errors='ignore')
            if line:
                matches = pattern.search(line)
                if matches:
                    h, m, s, ms = map(int, matches.groups())
                    current_seconds = h * 3600 + m * 60 + s + ms/100
                    percentage = min(100, int(current_seconds / total_duration * 100)) if total_duration else 0
                    
                    # Update progress not too frequently to avoid Telegram API limits
                    if time.time() - last_update_time > 3:  # Update every 3 seconds
                        elapsed = time.time() - start_time
                        speed = current_seconds / elapsed if elapsed > 0 else 0
                        eta = (total_duration - current_seconds) / speed if speed > 0 else 0
                        
                        progress_text = f"**⚙️ Processing with FFmpeg**\n"
                        progress_text += f"• Progress: {percentage}% [{current_seconds:.1f}s / {total_duration:.1f}s]\n"
                        progress_text += f"• Speed: {speed:.2f}x\n"
                        progress_text += f"• ETA: {format_time(eta)}\n"
                        progress_text += f"• Elapsed: {format_time(elapsed)}"
                        
                        try:
                            await message.edit(progress_text)
                            last_update_time = time.time()
                        except Exception as e:
                            logger.error(f"Failed to update progress message: {e}")
        
        await asyncio.sleep(1)


def format_time(seconds):
    """Format seconds into HH:MM:SS format"""
    hours, remainder = divmod(int(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


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
            progress_message = await message.edit(f"**⬇️ Downloading**\n• Progress: 0%\n• Size: Unknown\n• Speed: 0 KB/s\n• ETA: Unknown")
            
            with open(temp_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # Update progress message every 3 seconds to avoid hitting API limits
                        if time.time() - last_update_time > 3:
                            elapsed = time.time() - start_time
                            speed = downloaded / elapsed if elapsed > 0 else 0
                            eta = (total_size - downloaded) / speed if speed > 0 and total_size > 0 else 0
                            percentage = min(100, int(downloaded / total_size * 100)) if total_size > 0 else 0
                            
                            progress_text = f"**⬇️ Downloading**\n"
                            progress_text += f"• Progress: {percentage}%\n"
                            progress_text += f"• Size: {human_readable_size(downloaded)}/{human_readable_size(total_size)}\n"
                            progress_text += f"• Speed: {human_readable_size(speed)}/s\n"
                            progress_text += f"• ETA: {format_time(eta)}"
                            
                            try:
                                await progress_message.edit(progress_text)
                                last_update_time = time.time()
                            except Exception as e:
                                logger.error(f"Failed to update progress message: {e}")
                                
        # Rename the completed download to the final filename
        os.rename(temp_filename, filename)
        return filename
                                
    except Exception as e:
        logger.error(f"Download error: {e}")
        await message.edit(f"❌ Download failed: {str(e)}")
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
        return None


async def aio(url, name):
    """Download a PDF file asynchronously"""
    k = f'{name}.pdf'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                f = await aiofiles.open(k, mode='wb')
                await f.write(await resp.read())
                await f.close()
    return k


async def download(url, name):
    """Download a PDF file asynchronously (alias for aio)"""
    ka = f'{name}.pdf'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                f = await aiofiles.open(ka, mode='wb')
                await f.write(await resp.read())
                await f.close()
    return ka


def parse_vid_info(info):
    """Parse video stream information from ffmpeg output"""
    info = info.strip()
    info = info.split("\n")
    new_info = []
    temp = []
    for i in info:
        i = str(i)
        if "[" not in i and '---' not in i:
            while "  " in i:
                i = i.replace("  ", " ")
            i.strip()
            i = i.split("|")[0].split(" ", 2)
            try:
                if "RESOLUTION" not in i[2] and i[2] not in temp and "audio" not in i[2]:
                    temp.append(i[2])
                    new_info.append((i[0], i[2]))
            except:
                pass
    return new_info


def vid_info(info):
    """Parse video stream information into a dictionary"""
    info = info.strip()
    info = info.split("\n")
    new_info = dict()
    temp = []
    for i in info:
        i = str(i)
        if "[" not in i and '---' not in i:
            while "  " in i:
                i = i.replace("  ", " ")
            i.strip()
            i = i.split("|")[0].split(" ", 3)
            try:
                if "RESOLUTION" not in i[2] and i[2] not in temp and "audio" not in i[2]:
                    temp.append(i[2])
                    new_info.update({f'{i[2]}': f'{i[0]}'})
            except:
                pass
    return new_info


async def run(cmd):
    """Run a command asynchronously and return its output"""
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await proc.communicate()

    print(f'[{cmd!r} exited with {proc.returncode}]')
    if proc.returncode == 1:
        return False
    if stdout:
        return f'[stdout]\n{stdout.decode()}'
    if stderr:
        return f'[stderr]\n{stderr.decode()}'


def human_readable_size(size, decimal_places=2):
    """Convert size in bytes to human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if size < 1024.0 or unit == 'PB':
            break
        size /= 1024.0
    return f"{size:.{decimal_places}f} {unit}"


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


async def process_direct_url(url, m, caption=None, custom_ffmpeg=None):
    """Handle direct media URLs by downloading and processing them"""
    # Extract filename from URL or generate a timestamp-based name
    filename = get_filename_from_url(url)
    
    download_msg = await m.reply_text(f"**⬇️ Starting download:** `{filename}`")
    
    # Download the file with progress updates
    downloaded_file = await download_with_progress(url, filename, download_msg)
    
    if not downloaded_file:
        await download_msg.edit("❌ Download failed")
        return
    
    # If custom FFmpeg processing is needed, process the downloaded file
    if custom_ffmpeg and custom_ffmpeg.lower() != "skip":
        await process_with_ffmpeg(downloaded_file, m, download_msg, custom_ffmpeg)
    else:
        await download_msg.edit(f"✅ Download completed: `{filename}`")
    
    # Upload the final file
    thumb = "no"  # Default thumbnail setting
    await send_vid(None, m, caption or f"**File:** `{filename}`", downloaded_file, thumb, filename, download_msg)


async def process_with_ffmpeg(input_file, m, progress_msg, custom_ffmpeg):
    """Process a video file with FFmpeg and show progress"""
    output_file = f"{os.path.splitext(input_file)[0]}_processed{os.path.splitext(input_file)[1]}"
    
    try:
        # Get video duration for progress calculation
        input_duration = duration(input_file)
        
        # Create FFmpeg command with custom parameters
        if "{input}" in custom_ffmpeg and "{output}" in custom_ffmpeg:
            ffmpeg_cmd = custom_ffmpeg.replace("{input}", input_file).replace("{output}", output_file)
        else:
            ffmpeg_cmd = f'ffmpeg -i "{input_file}" {custom_ffmpeg} "{output_file}"'
        
        # Update message that processing is starting
        await progress_msg.edit(f"**⚙️ Starting FFmpeg processing...**\n`{ffmpeg_cmd}`")
        
        # Start FFmpeg process
        process = subprocess.Popen(
            ffmpeg_cmd,
            shell=True,
            stderr=subprocess.PIPE,
            universal_newlines=False
        )
        
        # Monitor and update progress
        await monitor_ffmpeg_progress(process, progress_msg, input_file, input_duration)
        
        # Check if process completed successfully
        if process.returncode == 0 and os.path.exists(output_file):
            await progress_msg.edit("✅ FFmpeg processing completed successfully!")
            # Remove input file to save space
            os.remove(input_file)
            return output_file
        else:
            error_output = process.stderr.read().decode() if process.stderr else "Unknown error"
            await progress_msg.edit(f"❌ FFmpeg processing failed:\n```\n{error_output[:1000]}\n```")
            # Log the full error
            logger.error(f"FFmpeg error: {error_output}")
            return input_file
    
    except Exception as e:
        await progress_msg.edit(f"⚠️ Error during FFmpeg processing: {str(e)}")
        logger.exception("FFmpeg processing error")
        return input_file


async def download_video(url, cmd, name):
    """Download video using yt-dlp or similar tool with retry mechanism"""
    download_cmd = f'{cmd} -R 25 --fragment-retries 25 --external-downloader aria2c --downloader-args "aria2c: -x 16 -j 32"'
    global failed_counter
    print(download_cmd)
    logging.info(download_cmd)
    k = subprocess.run(download_cmd, shell=True)
    if "visionias" in cmd and k.returncode != 0 and failed_counter <= 10:
        failed_counter += 1
        await asyncio.sleep(5)
        await download_video(url, cmd, name)
    failed_counter = 0
    try:
        if os.path.isfile(name):
            return name
        elif os.path.isfile(f"{name}.webm"):
            return f"{name}.webm"
        name = name.split(".")[0]
        if os.path.isfile(f"{name}.mkv"):
            return f"{name}.mkv"
        elif os.path.isfile(f"{name}.mp4"):
            return f"{name}.mp4"
        elif os.path.isfile(f"{name}.mp4.webm"):
            return f"{name}.mp4.webm"
        return name
    except FileNotFoundError as exc:
        return os.path.splitext[0] + "." + "mp4"


async def send_doc(bot: Client, m: Message, cc, ka, cc1, prog, count, name):
    """Send a document (file) to Telegram chat"""
    reply = await m.reply_text(f"Uploading » `{name}`")
    time.sleep(1)
    start_time = time.time()
    await m.reply_document(ka, caption=cc1)
    count += 1
    await reply.delete(True)
    time.sleep(1)
    os.remove(ka)
    time.sleep(3)


async def send_vid(bot: Client, m: Message, cc, filename, thumb, name, prog, custom_ffmpeg=None):
    """Send a video to Telegram chat with proper formatting and thumbnails"""
    # First generate thumbnail
    subprocess.run(f'ffmpeg -i "{filename}" -ss 00:01:00 -vframes 1 "{filename}.jpg"', shell=True)
    
    # If a custom FFmpeg command is provided, run it
    if custom_ffmpeg and custom_ffmpeg.lower() != "skip":
        ffmpeg_output_filename = f"{filename}_processed.mp4"
        try:
            # Notify that processing is starting
            process_msg = await m.reply_text(f"**⚙️ Processing with FFmpeg...**\n`{custom_ffmpeg}`")
            
            # Get video duration for progress calculation
            input_duration = duration(filename)
            
            # Prepare FFmpeg command
            if "{input}" in custom_ffmpeg and "{output}" in custom_ffmpeg:
                ffmpeg_cmd = custom_ffmpeg.replace("{input}", filename).replace("{output}", ffmpeg_output_filename)
            else:
                ffmpeg_cmd = f'ffmpeg -i "{filename}" {custom_ffmpeg} "{ffmpeg_output_filename}"'
            
            # Start FFmpeg process
            process = subprocess.Popen(
                ffmpeg_cmd,
                shell=True,
                stderr=subprocess.PIPE,
                universal_newlines=False
            )
            
            # Monitor and update progress
            await monitor_ffmpeg_progress(process, process_msg, filename, input_duration)
            
            # Check if process completed successfully
            if process.returncode == 0 and os.path.exists(ffmpeg_output_filename):
                await process_msg.edit("✅ FFmpeg processing completed successfully!")
                # Remove the original file to save space and update filename
                os.remove(filename)
                filename = ffmpeg_output_filename
            else:
                error_output = process.stderr.read().decode() if process.stderr else "Unknown error"
                await process_msg.edit(f"❌ FFmpeg processing failed:\n```\n{error_output[:1000]}\n```")
                # Log the full error
                logger.error(f"FFmpeg error: {error_output}")
                # Continue with the original file if processing failed
            
            time.sleep(2)
            await process_msg.delete()
            
        except Exception as e:
            await m.reply_text(f"⚠️ Error during FFmpeg processing: {str(e)}")
            logger.exception("FFmpeg processing error")
            # Continue with the original file in case of exceptions
    
    if prog:
        await prog.delete(True)
    reply = await m.reply_text(f"**⥣ Uploading ...** » `{name}`")
    
    try:
        if thumb == "no":
            thumbnail = f"{filename}.jpg"
        else:
            thumbnail = thumb
    except Exception as e:
        await m.reply_text(str(e))
    
    dur = int(duration(filename))
    start_time = time.time()
    
    try:
        await m.reply_video(
            filename,
            caption=cc,
            supports_streaming=True,
            height=720,
            width=1280,
            thumb=thumbnail,
            duration=dur,
            progress=progress_bar,
            progress_args=(reply, start_time)
        )
    except Exception as e:
        logger.error(f"Failed to send video: {e}")
        await m.reply_text(f"❌ Failed to send as video: {str(e)}")
        await m.reply_document(
            filename,
            caption=cc,
            progress=progress_bar,
            progress_args=(reply, start_time)
        )
    
    os.remove(filename)
    if os.path.exists(f"{filename}.jpg"):
        os.remove(f"{filename}.jpg")
    await reply.delete(True)


# Add a new handler function for direct media URLs
async def handle_direct_link(m: Message, url, custom_filename=None, custom_ffmpeg=None):
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
    await send_vid(None, m, f"**File:** `{filename}`", downloaded_file, thumb, filename, download_msg)