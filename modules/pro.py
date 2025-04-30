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
        await status_msg.edit_text("Starting FFmpeg Process!\n\nSend your FFmpeg command:")
        cmd_msg = await bot.listen(m.chat.id)
        ffmpeg_cmd = cmd_msg.text.strip()
        await cmd_msg.delete()

        if ffmpeg_cmd.lower() == "help":
            examples = (
                "Example commands:\n"
                "`-vf scale=1280:720 -c:v libx264 -crf 23`\n"
                "`-c:v libx265 -preset fast -crf 28`\n"
                "`-c:v copy -c:a copy` (no re-encoding)"
            )
            await status_msg.edit_text(examples)
            cmd_msg = await bot.listen(m.chat.id)
            ffmpeg_cmd = cmd_msg.text.strip()
            await cmd_msg.delete()

        base_name = os.path.splitext(os.path.basename(input_path))[0]
        output_path = os.path.join(DOWNLOAD_DIR, f"{base_name}_processed.mkv")

        start_time = time.time()
        
        # Get input duration using ffprobe
        probe_cmd = [
            'ffprobe', 
            '-v', 'error', 
            '-show_entries', 'format=duration', 
            '-of', 'default=noprint_wrappers=1:nokey=1', 
            input_path
        ]
        
        probe_process = await asyncio.create_subprocess_exec(
            *probe_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await probe_process.communicate()
        total_duration = float(stdout.decode().strip())
        total_size = os.path.getsize(input_path)
        
        # Prepare FFmpeg command with more detailed progress
        ff_args = ffmpeg_cmd
        cmd = [
            'ffmpeg',
            '-hide_banner',
            '-y',
            '-progress', 'pipe:1',  # Send progress to stdout
            '-i', input_path,
            *shlex.split(ff_args),
            output_path
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # Initialize progress variables
        progress_data = {
            'frame': 0,
            'fps': 0,
            'time': 0,
            'bitrate': 0,
            'speed': 0,
            'progress': '',
            'out_time_ms': 0,
            'total_size': 0,
            'dup_frames': 0,
            'drop_frames': 0,
        }
        
        # Create update task
        last_update_time = 0
        UPDATE_INTERVAL = 3  # Update message every 3 seconds
        
        async def read_stderr():
            while True:
                line = await proc.stderr.readline()
                if not line:
                    break
                decoded_line = line.decode("utf-8", errors="ignore").strip()
                # Just for debug logging
                logging.debug(f"FFMPEG stderr: {decoded_line}")
                
        stderr_reader = asyncio.create_task(read_stderr())
        
        # Read progress output
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
                
            decoded_line = line.decode("utf-8", errors="ignore").strip()
            if not decoded_line:
                continue
                
            # Parse progress information
            if '=' in decoded_line:
                key, value = decoded_line.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                if key == 'frame':
                    progress_data['frame'] = int(value)
                elif key == 'fps':
                    progress_data['fps'] = float(value)
                elif key == 'bitrate':
                    # Remove 'kbits/s' and convert to float
                    if value != 'N/A':
                        progress_data['bitrate'] = float(value.replace('kbits/s', '').strip())
                elif key == 'total_size':
                    progress_data['total_size'] = int(value)
                elif key == 'out_time_ms':
                    progress_data['out_time_ms'] = int(value)
                elif key == 'out_time':
                    # Parse timestamp like "00:00:05.24"
                    time_parts = value.split(':')
                    hours = int(time_parts[0])
                    minutes = int(time_parts[1])
                    seconds = float(time_parts[2])
                    progress_data['time'] = hours * 3600 + minutes * 60 + seconds
                elif key == 'speed':
                    # Remove "x" and convert to float
                    if value != 'N/A':
                        progress_data['speed'] = float(value.replace('x', '').strip())
                elif key == 'progress':
                    progress_data['progress'] = value
                elif key == 'dup_frames':
                    progress_data['dup_frames'] = int(value)
                elif key == 'drop_frames':
                    progress_data['drop_frames'] = int(value)
            
            # Update status message at regular intervals
            current_time = time.time()
            if current_time - last_update_time >= UPDATE_INTERVAL:
                last_update_time = current_time
                
                # Calculate progress percentage based on time
                percentage = min(100, (progress_data['time'] / total_duration) * 100) if total_duration > 0 else 0
                
                # Calculate ETA
                elapsed = current_time - start_time
                if progress_data['speed'] > 0:
                    eta = (total_duration - progress_data['time']) / progress_data['speed']
                else:
                    eta = (total_duration - progress_data['time']) * (elapsed / max(1, progress_data['time']))
                
                # Get system resources
                cpu = psutil.cpu_percent()
                ram = psutil.virtual_memory()
                
                # Format output size
                output_size = progress_data['total_size']
                speed_display = f"{progress_data['speed']:.2f}x"
                bitrate_display = f"{progress_data['bitrate']:.1f} kbits/s" if progress_data['bitrate'] > 0 else "N/A"
                
                progress_text = (
                    "Encoding:\n\n"
                    f"{get_progress_bar(percentage)} {percentage:.1f}%\n"
                    f"Time: {format_time(progress_data['time'])} / {format_time(total_duration)}\n"
                    f"Frames: {progress_data['frame']} @ {progress_data['fps']:.1f} FPS\n"
                    f"Output Size: {format_size(output_size)}\n"
                    f"Bitrate: {bitrate_display} | Speed: {speed_display}\n"
                    f"ETA: {format_time(eta)} | Elapsed: {format_time(elapsed)}\n"
                    f"Duplicated Frames: {progress_data['dup_frames']} | Dropped Frames: {progress_data['drop_frames']}\n\n"
                    f"CPU: {cpu}% | RAM: {format_size(ram.used)}/{format_size(ram.total)}\n\n"
                    f"<code>{ff_args}</code>"
                )
                
                try:
                    await status_msg.edit_text(progress_text)
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        logging.warning(f"Progress update error: {e}")
                
                # Check if encoding is complete
                if progress_data['progress'] == 'end':
                    break
        
        # Cancel stderr reader task
        stderr_reader.cancel()
        
        # Wait for process to complete
        await proc.wait()
        
        if proc.returncode != 0:
            stderr_data = await proc.stderr.read()
            error_msg = stderr_data.decode().strip()
            error_lines = error_msg.split('\n')
            relevant_error = '\n'.join(error_lines[-10:])
            await status_msg.edit_text(
                f"❌ FFmpeg Processing Failed\n\n"
                f"Command: {' '.join(cmd)}\n\n"
                f"Error: {relevant_error}"
            )
            return None
        
        # Final success message
        final_size = os.path.getsize(output_path)
        compression_ratio = (total_size / final_size) if final_size > 0 else 0
        
        await status_msg.edit_text(
            f"✅ FFmpeg Processing Complete!\n\n"
            f"Original Size: {format_size(total_size)}\n"
            f"Final Size: {format_size(final_size)}\n"
            f"Compression Ratio: {compression_ratio:.2f}x\n"
            f"Total Time: {format_time(time.time() - start_time)}"
        )
        
        return output_path
    except Exception as e:
        logging.error(f"FFmpeg processing error: {str(e)}")
        await status_msg.edit_text(f"❌ Error: {str(e)}")
        return None

async def send_large_message(bot, chat_id, text):
    max_length = 4096
    for i in range(0, len(text), max_length):
        await bot.send_message(chat_id, text[i:i+max_length])

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
                output_path,
                caption="✅ Processing complete!"
            )

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