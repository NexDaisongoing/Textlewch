import os
import re
import time
import subprocess
import asyncio
import logging
from pathlib import Path

from utlis.bar import ffmpeg_progress_bar

logger = logging.getLogger(__name__)

def get_duration(filename):
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

def get_file_size(filename):
    """Get the size of a file in bytes"""
    try:
        return os.path.getsize(filename)
    except Exception as e:
        logger.error(f"Error getting file size: {e}")
        return 0

def estimate_output_size(input_file, ffmpeg_cmd):
    """Estimate the output file size based on the input file and FFmpeg command"""
    # This is a very rough estimation
    input_size = get_file_size(input_file)
    
    # Check if the command contains compression parameters
    if "-crf" in ffmpeg_cmd:
        # Try to extract CRF value
        crf_match = re.search(r'-crf\s+(\d+)', ffmpeg_cmd)
        if crf_match:
            crf = int(crf_match.group(1))
            # Higher CRF means lower quality and smaller file
            if crf > 23:  # Default CRF is often 23
                return input_size * 0.7  # Rough estimate for compressed output
            else:
                return input_size * 0.9
    
    # Check for video codec
    if "-c:v libx264" in ffmpeg_cmd or "-c:v h264" in ffmpeg_cmd:
        return input_size * 0.8
    elif "-c:v libx265" in ffmpeg_cmd or "-c:v hevc" in ffmpeg_cmd:
        return input_size * 0.6
    
    # Default: assume the output will be about the same size
    return input_size

async def monitor_ffmpeg_progress(process, message, filename, total_duration, estimated_size=None):
    """Monitor FFmpeg progress and update the message with the progress bar"""
    pattern = re.compile(r"time=(\d+):(\d+):(\d+)\.(\d+)")
    frame_pattern = re.compile(r"frame=\s*(\d+)")
    size_pattern = re.compile(r"size=\s*(\d+)kB")
    
    last_update_time = time.time()
    start_time = time.time()
    processed_size = 0
    
    while process.poll() is None:
        if process.stderr:
            line = process.stderr.readline().decode('utf-8', errors='ignore')
            if line:
                # Extract time
                time_matches = pattern.search(line)
                if time_matches:
                    h, m, s, ms = map(int, time_matches.groups())
                    current_seconds = h * 3600 + m * 60 + s + ms/100
                    
                    # Try to extract processed size
                    size_match = size_pattern.search(line)
                    if size_match:
                        processed_size = int(size_match.group(1)) * 1024  # Convert kB to bytes
                    
                    # Update progress not too frequently to avoid Telegram API limits
                    if time.time() - last_update_time > 3:  # Update every 3 seconds
                        await ffmpeg_progress_bar(
                            current_seconds, 
                            total_duration, 
                            processed_size, 
                            message, 
                            start_time, 
                            estimated_size
                        )
                        last_update_time = time.time()
        
        await asyncio.sleep(1)
    
    return process.returncode

async def process_with_ffmpeg(input_file, message, progress_msg, custom_ffmpeg):
    """Process a video file with FFmpeg and show progress"""
    output_file = f"{os.path.splitext(input_file)[0]}_processed{os.path.splitext(input_file)[1]}"
    
    try:
        # Get video duration for progress calculation
        input_duration = get_duration(input_file)
        
        # Create FFmpeg command with custom parameters
        if "{input}" in custom_ffmpeg and "{output}" in custom_ffmpeg:
            ffmpeg_cmd = custom_ffmpeg.replace("{input}", input_file).replace("{output}", output_file)
        else:
            ffmpeg_cmd = f'ffmpeg -i "{input_file}" {custom_ffmpeg} "{output_file}"'
        
        # Estimate output file size
        estimated_size = estimate_output_size(input_file, ffmpeg_cmd)
        
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
        return_code = await monitor_ffmpeg_progress(
            process, 
            progress_msg, 
            input_file, 
            input_duration, 
            estimated_size
        )
        
        # Check if process completed successfully
        if return_code == 0 and os.path.exists(output_file):
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

def generate_thumbnail(filename):
    """Generate thumbnail from video file"""
    thumbnail_file = f"{filename}.jpg"
    try:
        subprocess.run(f'ffmpeg -i "{filename}" -ss 00:01:00 -vframes 1 "{thumbnail_file}"', shell=True)
        return thumbnail_file
    except Exception as e:
        logger.error(f"Error generating thumbnail: {e}")
        return None
