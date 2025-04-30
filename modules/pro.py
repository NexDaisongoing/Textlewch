import os
import asyncio
import logging
import time
import psutil 
from pyrogram import filters, Client
from pyrogram.types import Message
from pyrogram.enums import ChatAction
from pyromod import listen  # For listening to user messages

# Set up logging configuration to capture only errors
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_errors.log'),
    ]
)

# Directory where files are stored and processed
download_dir = "./downloads/pro"

# In-memory toggle for /test feature per chat
test_feature = {}

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

async def send_message_in_parts(bot, chat_id, message):
    max_length = 4096
    for i in range(0, len(message), max_length):
        await bot.send_message(chat_id, message[i:i+max_length])

def register_test_toggle(bot: Client):
    @bot.on_message(filters.command("test") & filters.private)
    async def toggle_test(_, m: Message):
        cmd = m.text.strip().lower()
        if len(cmd.split()) == 1:
            status = test_feature.get(m.chat.id, True)
            text = f"/test is currently {'ON' if status else 'OFF'}."
        else:
            arg = cmd.split(maxsplit=1)[1]
            if arg in ("on", "off"):
                val = arg == "on"
                test_feature[m.chat.id] = val
                text = f"/test has been turned {'ON' if val else 'OFF'}."
            else:
                text = "Usage: /test on or /test off"
        await m.reply_text(text)

def pro_feature(bot: Client):
    register_test_toggle(bot)

    @bot.on_message(filters.command("pro") & filters.private)  
    async def pro_handler(_, m: Message):  
        try:
            if m.chat.id not in test_feature:
                test_feature[m.chat.id] = True

            # Send initial prompt message
            prompt_msg = await m.reply_text(
                "🔄 **FFmpeg Processing Status**\n\n"
                "📥 Please send me a video file or an .mkv document."
            )

            # Wait for user to send file
            file_msg: Message = await bot.listen(m.chat.id)

            # Delete the initial prompt message
            await prompt_msg.delete()

            # Create new status message for all subsequent updates
            status_message = await m.reply_text("🔄 **FFmpeg Processing Status**\n\n🔍 Checking file type...")

            if file_msg.video:
                media = file_msg.video
                ext = os.path.splitext(media.file_name or media.file_id)[1] or ".mp4"
            elif file_msg.document and file_msg.document.file_name.lower().endswith(".mkv"):
                media = file_msg.document
                ext = ".mkv"
            else:
                await status_message.edit_text(
                    "❌ **FFmpeg Processing Status**\n\n"
                    "❌ Invalid file. Please send a supported video or .mkv file.\n\n"
                    "Please use /pro to try again."
                )
                return

            ensure_dir(download_dir)
            original_name = media.file_name or f"input_{file_msg.id}{ext}"
            file_name = os.path.join(download_dir, original_name)

            # Update status to downloading
            await status_message.edit_text(
                f"🔄 **FFmpeg Processing Status**\n\n"
                f"📥 Downloading file: `{original_name}`\n\n"
                f"Please wait..."
            )

            # Download the file with progress bar
            def format_size(bytes):
                for unit in ['B', 'KB', 'MB', 'GB']:
                    if bytes < 1024:
                        return f"{bytes:.2f} {unit}"
                    bytes /= 1024
                return f"{bytes:.2f} TB"

            def format_time(seconds):
                minutes, seconds = divmod(int(seconds), 60)
                hours, minutes = divmod(minutes, 60)
                if hours:
                    return f"{hours}h {minutes}m {seconds}s"
                return f"{minutes}m {seconds}s"

            def get_progress_bar(percentage, length=20):
                filled = int(percentage / 100 * length)
                return f"[{'█' * filled}{'░' * (length - filled)}]"

            async def download_with_progress(bot, message, file_id, file_name, status_message):
                start_time = time.time()
                last_update = 0

                def progress(current, total):
                    nonlocal last_update
                    now = time.time()
                    if now - last_update < 1 and current != total:
                        return

                    percentage = (current / total) * 100
                    elapsed = now - start_time
                    speed = current / elapsed if elapsed > 0 else 0
                    eta = (total - current) / speed if speed > 0 else 0

                    cpu = psutil.cpu_percent()
                    ram = psutil.virtual_memory()

                    progress_text = (
                        f"🔄 **FFmpeg Processing Status**\n\n"
                        f"📥 Downloading File\n\n"
                        f"{get_progress_bar(percentage)} {percentage:.1f}%\n"
                        f"Downloaded: {format_size(current)} / {format_size(total)}\n"
                        f"Speed: {format_size(speed)}/s\n"
                        f"ETA: {format_time(eta)} | Elapsed: {format_time(elapsed)}\n"
                        f"Total Time: {format_time(eta + elapsed)}\n\n"
                        f"CPU: {cpu}% | RAM: {format_size(ram.used)}/{format_size(ram.total)}"
                    )

                    asyncio.create_task(status_message.edit_text(progress_text))
                    last_update = now

                file_path = await bot.download_media(
                    message=file_id,
                    file_name=file_name,
                    progress=progress
                )

                return file_path

            # Use the new download function
            local_in = await download_with_progress(bot, m, file_msg, file_name, status_message)

            # Update status to prompt for FFmpeg args
            await status_message.edit_text(
                "🔄 **FFmpeg Processing Status**\n\n"
                f"✅ Downloaded: `{os.path.basename(local_in)}`\n\n"
                "📝 Send your **ffmpeg** arguments.\n"
                "For example: `-vf scale=1280:720 -c:v libx264 -crf 23`\n"
                "Type `help` to see more examples."
            )

            # Wait for FFmpeg arguments
            cmd_msg: Message = await bot.listen(m.chat.id)
            ff_args = cmd_msg.text.strip()
            await cmd_msg.delete()

            if ff_args.lower() in ("help", "?", "examples"):
                examples = (
                    "`-vf scale=1280:720 -c:v libx264 -crf 23`\n"
                    "`-q:v 2 -preset slow`\n"
                    "`-c:v copy -c:a copy` (stream copy/no re-encode)"
                )
                await status_message.edit_text(
                    f"🔄 **FFmpeg Processing Status**\n\n"
                    f"✅ Downloaded: `{os.path.basename(local_in)}`\n\n"
                    f"📋 Here are some example ffmpeg args:\n{examples}\n\n"
                    "Now please send your ffmpeg arguments:"
                )
                cmd_msg = await bot.listen(m.chat.id)
                ff_args = cmd_msg.text.strip()
                await cmd_msg.delete()

            base_name, _ = os.path.splitext(original_name)
            local_out = os.path.join(download_dir, f"{base_name} @Anime_Surge.mkv")
            cmd = f"ffmpeg -i '{local_in}' {ff_args} '{local_out}'"

            # Update status to processing
            await status_message.edit_text(
                f"🔄 **FFmpeg Processing Status**\n\n"
                f"✅ Downloaded: `{os.path.basename(local_in)}`\n"
                f"⚙️ Processing with ffmpeg...\n`{ff_args}`"
            )

            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                err_msg = stderr.decode(errors="ignore").strip()
                logging.error(f"FFmpeg processing failed for file {file_name}. Full error message:\n{err_msg}")
                await status_message.edit_text(
                    f"❌ **FFmpeg Processing Status**\n\n"
                    f"✅ Downloaded: `{os.path.basename(local_in)}`\n"
                    f"❌ Processing failed\n\n"
                    f"Error message is too long, sending separately..."
                )
                await send_message_in_parts(bot, m.chat.id, f"❌ FFmpeg Error:\n`{err_msg}`")
                for path in (local_in, local_out):
                    try:
                        if os.path.exists(path):
                            os.remove(path)
                    except OSError as e:
                        logging.error(f"Error removing file {path}: {e}")
                return

            # Update status to uploading
            await status_message.edit_text(
                f"🔄 **FFmpeg Processing Status**\n\n"
                f"✅ Downloaded: `{os.path.basename(local_in)}`\n"
                f"✅ Processing complete\n"
                f"📤 Uploading processed file..."
            )

            await m.reply_chat_action(ChatAction.UPLOAD_DOCUMENT)
            await m.reply_document(local_out, caption="✅ Here is your processed file.")

            if test_feature.get(m.chat.id, True):
                await m.reply_text(f"Here is the FFmpeg command used:\n```bash\n{ff_args}\n```")

            # Clean up files
            for path in (local_in, local_out):
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError as e:
                    logging.error(f"Error removing file {path}: {e}")

            # Delete the status message after completion
            await status_message.delete()

        except Exception as e:
            logging.error(f"Unexpected error in pro_handler: {e}")
            if 'status_message' in locals():
                await status_message.edit_text("❌ An error occurred during processing. Please try again.")
            await send_message_in_parts(bot, m.chat.id, f"❌ An unexpected error occurred: {e}")
            # Clean up any remaining files
            for path in (local_in, local_out):
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except (OSError, NameError) as e:
                    logging.error(f"Error removing file during cleanup: {e}")