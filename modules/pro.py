import os
import asyncio
import logging
from pyrogram import filters, Client
from pyrogram.types import Message
from pyrogram.enums import ChatAction
from pyromod import listen  # For listening to user messages

# Set up logging configuration to capture only errors
logging.basicConfig(
    level=logging.ERROR,  # Only log errors (not debug or info)
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_errors.log'),  # Log errors to a file
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

# Handler for /test toggle command
def register_test_toggle(bot: Client):
    @bot.on_message(filters.command("test") & filters.private)
    async def toggle_test(_, m: Message):
        cmd = m.text.strip().lower()
        if len(cmd.split()) == 1:
            # Show status
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

# Main handler function for the "pro" command
def pro_feature(bot: Client):
    # Register toggle
    register_test_toggle(bot)

    @bot.on_message(filters.command("pro") & filters.private)
    async def pro_handler(_, m: Message):
        try:
            # Default test flag on
            if m.chat.id not in test_feature:
                test_feature[m.chat.id] = True

            status_message = await m.reply_text("🔄 **FFmpeg Processing Status**\n\n📥 Please send me a video file or an .mkv document.")
            file_msg: Message = await bot.listen(m.chat.id)

            await status_message.edit_text("🔄 **FFmpeg Processing Status**\n\n🔍 Checking file type...")

            if file_msg.video:
                media = file_msg.video
                ext = os.path.splitext(media.file_name or media.file_id)[1] or ".mp4"
            elif file_msg.document and file_msg.document.file_name.lower().endswith(".mkv"):
                media = file_msg.document
                ext = ".mkv"
            else:
                return await status_message.edit_text(
                    "❌ **FFmpeg Processing Status**\n\n❌ Invalid file. Please send a supported video or .mkv file.\n\nPlease use /pro to try again."
                )

            ensure_dir(download_dir)
            original_name = media.file_name or f"input_{file_msg.id}{ext}"
            file_name = os.path.join(download_dir, original_name)

            await status_message.edit_text(f"🔄 **FFmpeg Processing Status**\n\n📥 Downloading file: `{original_name}`\n\nPlease wait...")
            local_in = await file_msg.download(file_name=file_name)

            help_text = (
                "🔄 **FFmpeg Processing Status**\n\n"
                f"✅ Downloaded: `{os.path.basename(local_in)}`\n\n"
                "📝 Send your **ffmpeg** arguments.\n"
                "For example: `-vf scale=1280:720 -c:v libx264 -crf 23`\n"
                "Type `help` to see more examples."
            )
            await status_message.edit_text(help_text)

            cmd_msg: Message = await bot.listen(m.chat.id)
            ff_args = cmd_msg.text.strip()

            if ff_args.lower() in ("help", "?", "examples"):
                examples = (
                    "`-vf scale=1280:720 -c:v libx264 -crf 23`\n"
                    "`-q:v 2 -preset slow`\n"
                    "`-c:v copy -c:a copy` (stream copy/no re-encode)"
                )
                await status_message.edit_text(
                    f"🔄 **FFmpeg Processing Status**\n\n"
                    f"✅ Downloaded: `{os.path.basename(local_in)}`\n\n"
                    f"📋 Here are some example ffmpeg args:\n{examples}\n\nNow please send your ffmpeg arguments:"
                )
                cmd_msg = await bot.listen(m.chat.id)
                ff_args = cmd_msg.text.strip()

            base_name, _ = os.path.splitext(original_name)
            local_out = os.path.join(download_dir, f"{base_name} @Anime_Surge.mkv")
            cmd = f"ffmpeg -i '{local_in}' {ff_args} '{local_out}'"

            await status_message.edit_text(
                f"🔄 **FFmpeg Processing Status**\n\n"
                f"✅ Downloaded: `{os.path.basename(local_in)}`\n"
                f"⚙️ Processing with ffmpeg...\n`{cmd}`"
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
                    f"❌ Processing failed\n\nError message is too long, sending separately..."
                )
                await send_message_in_parts(bot, m.chat.id, f"❌ FFmpeg Error:\n`{err_msg}`")
                os.remove(local_in)
                return

            await status_message.edit_text(
                f"🔄 **FFmpeg Processing Status**\n\n"
                f"✅ Downloaded: `{os.path.basename(local_in)}`\n"
                f"✅ Processing complete\n"
                f"📤 Uploading processed file..."
            )

            await m.reply_chat_action(ChatAction.UPLOAD_DOCUMENT)
            await m.reply_document(local_out, caption="✅ Here is your processed file.")

            # If test feature enabled, send ffmpeg command in monospace
            if test_feature.get(m.chat.id, True):
                await m.reply_text(f"Here is the FFmpeg command used:\n```bash\n{cmd}\n```")

            await status_message.edit_text(
                f"✅ **FFmpeg Processing Complete**\n\n"
                f"✅ Downloaded: `{os.path.basename(local_in)}`\n"
                f"✅ Processing complete\n"
                f"✅ File uploaded\n"
                f"🧹 Cleaning up temporary files..."
            )

            for path in (local_in, local_out):
                try:
                    os.remove(path)
                except OSError as e:
                    logging.error(f"Error removing file {path}: {e}")

            await status_message.edit_text(
                f"✅ **FFmpeg Processing Complete**\n\n"
                f"✅ Downloaded: `{os.path.basename(local_in)}`\n"
                f"✅ Processing complete\n"
                f"✅ File uploaded\n"
                f"✅ Temporary files cleaned\n\n"
                f"Use /pro to process another file."
            )

        except Exception as e:
            logging.error(f"Unexpected error in pro_handler: {e}")
            await send_message_in_parts(bot, m.chat.id, f"❌ An unexpected error occurred: {e}")
