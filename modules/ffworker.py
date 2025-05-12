import os
import re
import json
import time
import shlex
import logging
import asyncio
import psutil
from typing import Tuple, Dict, Any, Optional

# Ensure these helper functions are available or import them from a utils module
from utils import format_size, format_time, get_progress_bar

# Directory for processed files
DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "./downloads")

async def process_with_ffmpeg(bot, m, input_path, status_msg):
    """
    Process a video file with FFmpeg using user-provided parameters.
    
    Args:
        bot: Telegram bot instance
        m: Original message object
        input_path: Path to the input video file (must be a string path)
        status_msg: Message object to update with progress
        
    Returns:
        str: Path to the output file on success, None on failure
    """
    try:
        # Ensure input_path is a string and file exists
        if not isinstance(input_path, str):
            return await status_msg.edit_text("❌ Invalid input path: Must be a string")
            
        if not os.path.isfile(input_path):
            return await status_msg.edit_text(f"❌ Input file does not exist: {input_path}")
            
        # Verify file is readable and is binary
        try:
            with open(input_path, 'rb') as f:
                # Just check if readable, don't read whole file
                f.read(1024)
        except Exception as e:
            return await status_msg.edit_text(f"❌ Cannot read input file: {str(e)}")
        
        # Probe input file
        probe_cmd = [
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,r_frame_rate,avg_frame_rate,duration,bit_rate,nb_frames,codec_name:format=duration,bit_rate,size',
            '-of', 'json', input_path
        ]
        proc_probe = await asyncio.create_subprocess_exec(*probe_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await proc_probe.communicate()
        if proc_probe.returncode != 0:
            return await status_msg.edit_text(f"❌ Error getting video info:\n{err.decode().strip()}")

        data = json.loads(out.decode())
        stream = data.get("streams", [{}])[0]
        fmt = data.get("format", {})

        # Handle potential missing values with defaults
        total_duration = float(stream.get("duration") or fmt.get("duration") or 0)
        fr = stream.get("r_frame_rate", "25/1")
        frame_rate = eval(fr) if '/' in fr else float(fr)
        total_size = os.path.getsize(input_path)
        input_codec = stream.get("codec_name", "unknown")

        await status_msg.edit_text(
            "📂 Input File Info:\n"
            f"▫️ Size: {format_size(total_size)}\n"
            f"▫️ Duration: {format_time(total_duration)}\n"
            f"▫️ Resolution: {stream.get('width', 'N/A')}x{stream.get('height', 'N/A')}\n"
            f"▫️ Codec: {input_codec}\n\n"
            "⚙️ Send your FFmpeg command:"
        )

        cmd_msg = await bot.listen(m.chat.id)
        ffmpeg_cmd = cmd_msg.text.strip()

        base_name = os.path.splitext(os.path.basename(input_path))[0]
        output_path = os.path.join(DOWNLOAD_DIR, f"{base_name}_processed.mkv")
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Log the full command for debugging
        full_cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'info', '-stats', '-y', '-i', input_path] + shlex.split(ffmpeg_cmd) + [output_path]
        logging.info(f"Running FFmpeg command: {' '.join(full_cmd)}")
        
        # Execute the command
        try:
            proc = await asyncio.create_subprocess_exec(
                *full_cmd, 
                stdout=asyncio.subprocess.PIPE, 
                stderr=asyncio.subprocess.PIPE
            )
        except Exception as e:
            return await status_msg.edit_text(f"❌ Failed to start FFmpeg: {str(e)}")

        # Initialize progress data with safe defaults
        progress_data = {
            'frame': 0, 'fps': 0, 'time': 0, 'bitrate': 0, 'speed': 0,
            'size_kb': 0, 'q': 0, 'dup': 0, 'drop': 0
        }
        start_time = time.time()
        
        # Flag to track if the FFmpeg process is running
        ffmpeg_running = asyncio.Event()
        ffmpeg_running.set()  # Set to True initially

        # --- Task 1: Reading FFmpeg stderr ---
        async def read_ffmpeg_log():
            while True:
                line = await proc.stderr.readline()
                if not line:  # EOF
                    ffmpeg_running.clear()  # Signal that FFmpeg has stopped
                    break

                text_line = line.decode(errors="ignore").strip()
                
                # Debug log every 100 lines to help diagnose early termination
                if progress_data.get('debug_count', 0) % 100 == 0:
                    logging.debug(f"FFmpeg output: {text_line}")
                progress_data['debug_count'] = progress_data.get('debug_count', 0) + 1
                
                for key, pattern in {
                    'frame':   r"frame=\s*(\d+)",
                    'fps':     r"fps=\s*([\d\.]+)",
                    'time':    r"time=\s*(\d+):(\d+):(\d+\.\d+)",
                    'bitrate': r"bitrate=\s*([\d\.]+)\s*kbits/s",
                    'speed':   r"speed=\s*([\d\.]+)x",
                    'size_kb': r"size=\s*(\d+)kB",
                    'q':       r"q=\s*([\d\.]+)",
                    'dup':     r"dup=\s*(\d+)",
                    'drop':    r"drop=\s*(\d+)"
                }.items():
                    match = re.search(pattern, text_line)
                    if match:
                        if key == "time":
                            h, m, s = map(float, match.groups())
                            progress_data["time"] = int(h * 3600 + m * 60 + s)
                        else:
                            val = float(match.group(1)) if "." in match.group(1) else int(match.group(1))
                            progress_data[key] = val

        # --- Task 2: Periodic updater ---
        async def update_message_loop():
            last_update_time = 0
            while ffmpeg_running.is_set() or not proc.returncode:
                now = time.time()
                
                # Only update message every 2 seconds to avoid API rate limits
                if now - last_update_time < 2:
                    await asyncio.sleep(0.5)
                    continue
                    
                last_update_time = now
                
                # Calculate stats, handling division by zero and missing values
                percent = min(100, (progress_data['time'] / max(total_duration, 0.1)) * 100) if total_duration else 0
                
                # Handle speed=0 to avoid division by zero in ETA calculation
                speed = max(progress_data['speed'], 0.01)
                eta = (total_duration - progress_data['time']) / speed if progress_data['time'] < total_duration else 0
                
                # Handle zero size to avoid division by zero
                output_size = max(progress_data['size_kb'] * 1024, 1)
                compression_ratio = total_size / output_size if output_size else 1
                
                cpu = psutil.cpu_percent()
                ram = psutil.virtual_memory()
                elapsed = now - start_time

                def fmt(val, fallback="0.0"):
                    return f"{val:.1f}" if isinstance(val, (int, float)) else fallback

                # Ensure we're showing something even if values are zero
                estimated_final_size = "Calculating..."
                if progress_data['time'] > 0 and total_duration > 0:
                    ratio = total_duration / progress_data['time']
                    estimated_final_size = format_size(output_size * ratio)

                stats_text = (
                    "🔄 Encoding Progress:\n\n"
                    f"{get_progress_bar(percent)} {percent:.1f}%\n"
                    f" Duration: {format_time(progress_data['time'])} / {format_time(total_duration)}\n"
                    f" Frames: {progress_data['frame'] or '0'} @ {fmt(progress_data['fps'])} FPS\n"
                    f" Quality: q={fmt(progress_data['q'])}\n"
                    f" Size: {format_size(output_size)} (Est. Final: {estimated_final_size})\n"
                    f" Compression: {compression_ratio:.2f}x\n"
                    f" Bitrate: {fmt(progress_data['bitrate'])} kbps | Speed: {fmt(progress_data['speed'])}x\n"
                    f" ETA: {format_time(eta)} |  Elapsed: {format_time(elapsed)}\n"
                    f"\n CPU: {cpu}% | RAM: {format_size(ram.used)}/{format_size(ram.total)}\n"
                    f"\n<code>{ffmpeg_cmd}</code>"
                )
                try:
                    await status_msg.edit_text(stats_text)
                except Exception as e:
                    logging.error(f"Failed to update status message: {e}")
                
                # Check if process is still running
                if proc.returncode is not None and not ffmpeg_running.is_set():
                    break
                    
                await asyncio.sleep(0.5)

        # Perform periodic heartbeat checks on ffmpeg
        async def monitor_ffmpeg():
            while proc.returncode is None:
                # Just check if the process is still running
                if proc.returncode is not None:
                    ffmpeg_running.clear()
                    break
                await asyncio.sleep(1)

        # Launch all tasks
        await asyncio.gather(
            read_ffmpeg_log(),
            update_message_loop(),
            monitor_ffmpeg()
        )

        # Wait for process to complete
        return_code = await proc.wait()
        
        # Check if operation was successful
        if return_code != 0 or not os.path.exists(output_path):
            return await status_msg.edit_text(
                f"❌ FFmpeg process failed with return code {return_code}\n\n"
                f"Last command: <code>{ffmpeg_cmd}</code>"
            )
            
        final_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
        processing_time = time.time() - start_time
        compression_ratio = total_size / max(final_size, 1)  # Avoid division by zero

        await status_msg.edit_text(
            f"✅ Done!\n\n"
            f"▫️ Original: {format_size(total_size)}\n"
            f"▫️ Final:    {format_size(final_size)}\n"
            f"▫️ Ratio:    {compression_ratio:.2f}x\n"
            f"▫️ Time:     {format_time(processing_time)}"
        )
        return output_path

    except Exception as e:
        logging.error(f"FFmpeg processing failed: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Error occurred:\n{e}")
        return None