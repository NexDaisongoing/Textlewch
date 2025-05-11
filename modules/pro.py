import os
import re
import asyncio
import logging
import time
import psutil
import shlex
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
        import json, re, shlex, os, time, logging, psutil
       
        # Start time for ETA and elapsed
        start_time = time.time()

        # FFprobe to get video info
        probe_cmd = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,r_frame_rate,avg_frame_rate,duration,bit_rate,nb_frames,codec_name:format=duration,bit_rate,size',
            '-of', 'json',
            input_path
        ]
        probe_process = await asyncio.create_subprocess_exec(*probe_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await probe_process.communicate()
        if probe_process.returncode != 0:
            await status_msg.edit_text(f"❌ Error getting video info:\n{stderr.decode().strip()}")
            return

        probe_data = json.loads(stdout.decode())
        stream_info = probe_data.get("streams", [{}])[0]
        format_info = probe_data.get("format", {})

        total_duration = float(stream_info.get("duration") or format_info.get("duration") or 0)
        frame_rate = stream_info.get("r_frame_rate", "25/1")
        if "/" in frame_rate:
            num, den = map(int, frame_rate.split("/"))
            frame_rate = num / den if den != 0 else 25
        else:
            frame_rate = float(frame_rate) if frame_rate else 25

        total_frames = int(stream_info.get("nb_frames", 0) or total_duration * frame_rate)
        width = stream_info.get("width", 0)
        height = stream_info.get("height", 0)
        input_bitrate = int(stream_info.get("bit_rate") or format_info.get("bit_rate") or 0)
        input_codec = stream_info.get("codec_name", "unknown")
        total_size = os.path.getsize(input_path)

        await status_msg.edit_text(
            f"📂 Input File Info:\n"
            f"▫️ Size: {format_size(total_size)}\n"
            f"▫️ Duration: {format_time(total_duration)}\n"
            f"▫️ Resolution: {width}x{height}\n"
            f"▫️ Codec: {input_codec}\n"
            f"▫️ Bitrate: {input_bitrate/1000:.0f} kbps\n"
            f"▫️ Framerate: {frame_rate:.3f} fps\n\n"
            "⚙️ Send your FFmpeg command:"
        )

        cmd_msg = await bot.listen(m.chat.id)
        ffmpeg_cmd = cmd_msg.text.strip()
        await cmd_msg.delete()

        parsed_args = shlex.split(ffmpeg_cmd)
        codec_match = re.search(r'-c:v\s+(\w+)', ffmpeg_cmd)
        target_codec = codec_match.group(1) if codec_match else "unknown"

        base_name = os.path.splitext(os.path.basename(input_path))[0]
        output_path = os.path.join(DOWNLOAD_DIR, f"{base_name}_processed.mkv")

        cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'info', '-stats', '-y', '-i', input_path, *parsed_args, output_path]

        await status_msg.edit_text(
            f"🎬 Starting FFmpeg Processing\n\n"
            f"Input: {os.path.basename(input_path)}\n"
            f"Target Codec: {target_codec}\n"
            f"Command: <code>{ffmpeg_cmd}</code>"
        )

        start_time = time.time()

        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

        progress_data = {'frame': 0, 'fps': 0, 'time': 0, 'bitrate': 0, 'speed': 0, 'size_kb': 0, 'q': 0, 'dup': 0, 'drop': 0}
        last_update_time = 0
        UPDATE_INTERVAL = 2

        while True:
            line = await proc.stderr.readline()
            if not line:
                break

            line = line.decode("utf-8", errors="ignore").strip()
            if not line or not line.startswith("frame="):
                continue

            for key, pattern in {
                'frame': r"frame=\s*(\d+)",
                'fps': r"fps=\s*([\d\.]+)",
                'time': r"time=\s*(\d+):(\d+):(\d+\.\d+)",
                'bitrate': r"bitrate=\s*([\d\.]+)\s*kbits/s",
                'speed': r"speed=\s*([\d\.]+)x",
                'size_kb': r"size=\s*(\d+)kB",
                'q': r"q=\s*([\d\.]+)",
                'dup': r"dup=\s*(\d+)",
                'drop': r"drop=\s*(\d+)"
            }.items():
                if key == "time":
                    match = re.search(pattern, line)
                    if match:
                        h, m, s = map(float, match.groups())
                        progress_data["time"] = int(h * 3600 + m * 60 + s)
                else:
                    match = re.search(pattern, line)
                    if match:
                        progress_data[key] = float(match.group(1)) if "." in match.group(1) else int(match.group(1))

            current_time = time.time()
            if current_time - last_update_time >= UPDATE_INTERVAL and progress_data['time'] > 0:
                last_update_time = current_time
                percent = (progress_data['time'] / total_duration) * 100 if total_duration else 0
                elapsed = current_time - start_time
                eta = ((total_duration - progress_data['time']) / progress_data['speed']) if progress_data['speed'] else 0
                output_size = progress_data['size_kb'] * 1024
                compression_ratio = total_size / output_size if output_size else 1
                est_final_size = output_size / (progress_data['time'] / total_duration) if progress_data['time'] else 0

                cpu = psutil.cpu_percent()
                ram = psutil.virtual_memory()

                text = (
                    f"🔄 Encoding Progress:\n\n"
                    f"{get_progress_bar(percent)} {percent:.1f}%\n"
                    f"⏱️ Time: {format_time(progress_data['time'])} / {format_time(total_duration)}\n"
                    f"🎞️ Frames: {progress_data['frame']} @ {progress_data['fps']:.1f} FPS\n"
                    f"📊 Quality: q={progress_data['q']}\n"
                    f"📦 Size: {format_size(output_size)} (Est. Final: {format_size(est_final_size)})\n"
                    f"🔄 Compression: {compression_ratio:.2f}x\n"
                    f"📈 Bitrate: {progress_data['bitrate']} kbps | ⚡ Speed: {progress_data['speed']}x\n"
                    f"⏳ ETA: {format_time(eta)} | ⌛ Elapsed: {format_time(elapsed)}\n"
                )

                if progress_data['dup'] > 0 or progress_data['drop'] > 0:
                    text += f"🔄 Dup: {progress_data['dup']} | 🗑️ Drop: {progress_data['drop']}\n"

                text += f"\n🖥️ CPU: {cpu}% | 🧠 RAM: {format_size(ram.used)}/{format_size(ram.total)}\n\n<code>{ffmpeg_cmd}</code>"

                try:
                    await status_msg.edit_text(text)
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        logging.warning(f"Edit error: {e}")

        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            error_lines = stderr.decode().splitlines()
            filtered_errors = [line for line in error_lines if any(x in line.lower() for x in ['error', 'invalid', 'unable'])]
            filtered_error_text = '\n'.join(filtered_errors[-10:])

            await status_msg.edit_text(f"❌ FFmpeg Failed\n\n{filtered_error_text}\n\n<code>{ffmpeg_cmd}</code>")

        final_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
        compression_ratio = total_size / final_size if final_size else 0
        processing_time = time.time() - start_time

        await status_msg.edit_text(
            f"✅ Done!\n\n"
            f"▫️ Original: {format_size(total_size)}\n"
            f"▫️ Final: {format_size(final_size)}\n"
            f"▫️ Ratio: {compression_ratio:.2f}x\n"
            f"▫️ Time: {format_time(processing_time)}\n\n"
            f"<code>{ffmpeg_cmd}</code>"
        )

        return output_path
    except Exception as e:
        logging.error(f"FFmpeg processing failed: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Error occurred:\n{str(e)}")
        return

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
                await m.reply_text(f"FFmpeg command used:\n```\n{ff_args}\n```")

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