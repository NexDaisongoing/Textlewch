import os
import re
import asyncio
import logging
import time
import psutil
import shlex
import json
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from pyrogram.errors import MessageNotModified

# Setup logging
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('bot_errors.log')]
)

# Configuration
DOWNLOAD_DIR = "./downloads/pro"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
test_feature = {}

# Utility Functions
def format_size(bytes):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024:
            return f"{bytes:.2f} {unit}"
        bytes /= 1024
    return f"{bytes:.2f} TB"

def format_time(seconds):
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes}m {seconds}s"

def get_progress_bar(percentage, length=20):
    filled = int(percentage/100 * length)
    return f"[{'█' * filled}{'░' * (length - filled)}]"

async def download_with_progress(bot, chat_id, file_msg, file_path, status_msg):
    start_time = time.time()
    last_update = 0
    completed = False

    def progress(current, total):
        nonlocal last_update, completed
        now = time.time()
        if now - last_update < 1 and not completed:
            return

        percentage = (current / total) * 100
        elapsed = now - start_time
        speed = current / (elapsed + 0.001)  # Avoid division by zero
        eta = (total - current) / (speed + 0.001)
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory()

        progress_text = (
            "Downloading:\n\n"
            f"{get_progress_bar(percentage)} {percentage:.1f}%\n"
            f"Downloaded: {format_size(current)} / {format_size(total)}\n"
            f"Speed: {format_size(speed)}/s\n"
            f"ETA: {format_time(eta)} | Elapsed: {format_time(elapsed)}\n"
            f"Total Time Taken: {format_time(eta + elapsed)}\n\n"
            f"CPU: {cpu}% | RAM: {format_size(ram.used)}/{format_size(ram.total)}"
        )

        try:
            asyncio.create_task(bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg.id,
                text=progress_text
            ))
        except MessageNotModified:
            pass
        except Exception as e:
            logging.error(f"Progress update error: {e}")

        last_update = now
        if current == total:
            completed = True

    file = await bot.download_media(
        message=file_msg,
        file_name=file_path,
        progress=progress
    )
    return file

async def process_with_ffmpeg(bot, m: Message, input_path, status_msg):
    try:
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

        cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'info', '-stats', '-y', '-i', input_path, *shlex.split(ffmpeg_cmd), output_path]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

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
                except MessageNotModified:
                    pass
                
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

# Main Bot Handlers
def register_handlers(bot: Client):
    @bot.on_message(filters.command("test") & filters.private)
    async def toggle_test(_, m: Message):
        cmd = m.text.strip().lower()
        if len(cmd.split()) == 1:
            status = test_feature.get(m.chat.id, True)
            await m.reply_text(f"/test is currently {'ON' if status else 'OFF'}")
        else:
            arg = cmd.split(maxsplit=1)[1]
            if arg in ("on", "off"):
                test_feature[m.chat.id] = arg == "on"
                await m.reply_text(f"/test has been turned {'ON' if arg == 'on' else 'OFF'}")
            else:
                await m.reply_text("Usage: /test on or /test off")

    @bot.on_message(filters.command("pro") & filters.private)
    async def pro_handler(bot: Client, m: Message):
        try:
            # Initialize
            if m.chat.id not in test_feature:
                test_feature[m.chat.id] = True

            # Get video file
            prompt_msg = await m.reply_text("Please send a video file or .mkv document")
            file_msg = await bot.listen(m.chat.id)
            await prompt_msg.delete()

            # Validate file
            if file_msg.video:
                media = file_msg.video
                ext = os.path.splitext(media.file_name or str(file_msg.id))[1] or ".mp4"
            elif file_msg.document and file_msg.document.file_name.lower().endswith(".mkv"):
                media = file_msg.document
                ext = ".mkv"
            else:
                return await m.reply_text("❌ Invalid file type. Please send a video or .mkv file")

            # Prepare download
            file_name = media.file_name or f"file_{file_msg.id}{ext}"
            file_path = os.path.join(DOWNLOAD_DIR, file_name)

            # Start download with progress
            status_msg = await m.reply_text("Starting download...")
            local_file = await download_with_progress(bot, m.chat.id, file_msg, file_path, status_msg)

            # Process with FFmpeg
            output_path = await process_with_ffmpeg(bot, m, local_file, status_msg)
            if not output_path:
                return

            # Upload result
            await status_msg.edit_text("📤 Uploading processed file...")
            await m.reply_chat_action(enums.ChatAction.UPLOAD_DOCUMENT)
            await m.reply_document(
                output_path
            )
            await status_msg.delete()

            # Show command if test mode is on
            if test_feature.get(m.chat.id, True):
                await m.reply_text(f"FFmpeg command used:\n```\n{ffmpeg_cmd}\n```")

            # Cleanup
            await status_msg.delete()
            for f in [local_file, output_path]:
                try:
                    os.remove(f)
                except:
                    pass

        except Exception as e:
            logging.error(f"Error in pro_handler: {e}")
            await m.reply_text(f"❌ An error occurred: {str(e)}")
