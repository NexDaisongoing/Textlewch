import os
import re
import time
import subprocess
import asyncio
import logging
from pathlib import Path

from utlis.bar import ffmpeg_progress_bar


logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def get_duration(filename):
    """Get the duration of a media file using ffprobe"""
    try:
        logger.info(f"Getting duration for {filename}")
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", filename],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        duration = float(result.stdout)
        logger.info(f"Duration of {filename} is {duration} seconds")
        return duration
    except Exception as e:
        logger.error(f"Error getting duration for {filename}: {e}")
        return 0

def get_file_size(filename):
    """Get the size of a file in bytes"""
    try:
        logger.info(f"Getting file size for {filename}")
        size = os.path.getsize(filename)
        logger.info(f"Size of {filename} is {size} bytes")
        return size
    except Exception as e:
        logger.error(f"Error getting file size for {filename}: {e}")
        return 0

def estimate_output_size(input_file, ffmpeg_cmd):
    """Estimate the output file size based on the input file and FFmpeg command"""
    logger.info(f"Estimating output size for {input_file} using command: {ffmpeg_cmd}")
    input_size = get_file_size(input_file)

    # Check if the command contains compression parameters
    if "-crf" in ffmpeg_cmd:
        crf_match = re.search(r'-crf\s+(\d+)', ffmpeg_cmd)
        if crf_match:
            crf = int(crf_match.group(1))
            if crf > 23:
                estimated_size = input_size * 0.7
                logger.info(f"CRF value is {crf}, estimated size: {estimated_size} bytes")
                return estimated_size
            else:
                estimated_size = input_size * 0.9
                logger.info(f"CRF value is {crf}, estimated size: {estimated_size} bytes")
                return estimated_size

    if "-c:v libx264" in ffmpeg_cmd or "-c:v h264" in ffmpeg_cmd:
        estimated_size = input_size * 0.8
        logger.info(f"Video codec h264, estimated size: {estimated_size} bytes")
        return estimated_size
    elif "-c:v libx265" in ffmpeg_cmd or "-c:v hevc" in ffmpeg_cmd:
        estimated_size = input_size * 0.6
        logger.info(f"Video codec hevc, estimated size: {estimated_size} bytes")
        return estimated_size

    # Default: assume the output will be about the same size
    logger.info(f"No specific codec or CRF found, assuming output size will be the same as input: {input_size} bytes")
    return input_size

async def monitor_ffmpeg_progress(process, message, filename, total_duration, estimated_size=None):
    """Monitor FFmpeg progress and update the message with the progress bar"""
    logger.info(f"Monitoring FFmpeg progress for {filename}")
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
                time_matches = pattern.search(line)
                if time_matches:
                    h, m, s, ms = map(int, time_matches.groups())
                    current_seconds = h * 3600 + m * 60 + s + ms/100
                    size_match = size_pattern.search(line)
                    if size_match:
                        processed_size = int(size_match.group(1)) * 1024  # Convert kB to bytes

                    # Update progress every 3 seconds
                    if time.time() - last_update_time > 3:
                        logger.info(f"Progress: {current_seconds}/{total_duration} seconds, {processed_size} bytes processed")
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

    logger.info(f"FFmpeg process completed with return code {process.returncode}")
    return process.returncode

async def process_with_ffmpeg(input_file, message, progress_msg, custom_ffmpeg):
    """Process a video file with FFmpeg and show progress"""
    logger.info(f"Starting FFmpeg processing for {input_file}")
    output_file = f"{os.path.splitext(input_file)[0]}_processed{os.path.splitext(input_file)[1]}"

    try:
        # Get video duration for progress calculation
        input_duration = get_duration(input_file)

        # Create FFmpeg command with custom parameters
        ffmpeg_cmd = custom_ffmpeg.replace("{input}", input_file).replace("{output}", output_file) if "{input}" in custom_ffmpeg and "{output}" in custom_ffmpeg else f'ffmpeg -i "{input_file}" {custom_ffmpeg} "{output_file}"'
        
        logger.info(f"FFmpeg command: {ffmpeg_cmd}")

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
            logger.info(f"FFmpeg processing completed successfully for {input_file}. Removing original file.")
            os.remove(input_file)
            return output_file
        else:
            error_output = process.stderr.read().decode() if process.stderr else "Unknown error"
            await progress_msg.edit(f"❌ FFmpeg processing failed:\n```\n{error_output[:1000]}\n```")
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
        logger.info(f"Generating thumbnail for {filename}")
        subprocess.run(f'ffmpeg -i "{filename}" -ss 00:01:00 -vframes 1 "{thumbnail_file}"', shell=True)
        logger.info(f"Thumbnail generated for {filename}")
        return thumbnail_file
    except Exception as e:
        logger.error(f"Error generating thumbnail for {filename}: {e}")
        return None