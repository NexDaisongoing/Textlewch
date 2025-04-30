import os
import asyncio
import logging
import time
import psutil
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
        # Ask for FFmpeg commands
        await status_msg.edit_text(
            "Starting FFmpeg Process!\n\n"
        )

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

        # Prepare output file
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        output_path = os.path.join(DOWNLOAD_DIR, f"{base_name}_processed.mkv")

        # Start processing
        start_time = time.time()
        total_size = os.path.getsize(input_path)
        ff_args = ffmpeg_cmd  # Store the command for display

        # Build FFmpeg command more safely
        cmd = [
            'ffmpeg',
            '-hide_banner',  # Hide version info to get cleaner errors
            '-y',  # Overwrite output file if exists
            '-i', input_path,
            ffmpeg_cmd,  # Split the user's command into parts
            output_path
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # Progress tracking
        while True:
            await asyncio.sleep(1)  # Update every second
            
            # Check process status
            if proc.returncode is not None:
                break
                
            # Get current file size
            try:
                current_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
            except:
                current_size = 0
                
            # Calculate progress
            elapsed = time.time() - start_time
            percentage = (current_size / total_size) * 100 if total_size > 0 else 0
            
            # Calculate speed (using input size as reference)
            speed = current_size / (elapsed + 0.001)
            speed_display = f"{speed/1024:.1f} kB/s" if speed < 1024*1024 else f"{speed/(1024*1024):.1f} MB/s"
            
            # Calculate ETA
            remaining = total_size - current_size
            eta = remaining / (speed + 0.001)
            
            # Get system stats
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory()
            
            # Prepare progress message
            progress_text = (
                "Encoding:\n\n"
                f"{get_progress_bar(percentage)} {percentage:.1f}%\n"
                f"Encoded: {format_size(current_size)} / {format_size(total_size)}\n"
                f"Speed: {speed_display}\n"
                f"ETA: {format_time(eta)} | Elapsed: {format_time(elapsed)}\n"
                f"Total Time Taken: {format_time(eta + elapsed)}\n\n"
                f"CPU: {cpu}% | RAM: {format_size(ram.used)}/{format_size(ram.total)}\n\n"
                f"<code>{ff_args}</code>"
            )
            
            try:
                await status_msg.edit_text(progress_text)
            except MessageNotModified:
                pass
            except Exception as e:
                logging.error(f"Progress update error: {e}")

        # Check result
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            error_msg = stderr.decode().strip()
            # Try to extract the actual error message (last few lines)
            error_lines = error_msg.split('\n')
            relevant_error = '\n'.join(error_lines[-10:])  # Get last 10 lines
            
            await status_msg.edit_text(
                f"❌ FFmpeg Processing Failed\n\n"
                f"Command: {' '.join(cmd)}\n\n"
                f"Error: {relevant_error}"
            )
            return None

        return output_path

    except Exception as e:
        await status_msg.edit_text(f"❌ Processing Error: {str(e)}")
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