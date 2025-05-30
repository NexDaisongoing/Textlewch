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

# Function to create the directory if it doesn't exist
def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

# Function to split messages that are too long
async def send_message_in_parts(bot, chat_id, message):
    max_length = 4096
    message_parts = [message[i:i+max_length] for i in range(0, len(message), max_length)]
    for part in message_parts:
        await bot.send_message(chat_id, part)

# Main handler function for the "pro" command
def pro_feature(bot: Client):
    @bot.on_message(filters.command("pro") & filters.private)
    async def pro_handler(_, m: Message):
        try:
            # Ask user to send a video or .mkv file
            await m.reply_text("📥 Please send me a video file or an .mkv document.")

            # Wait for the user to send the file
            file_msg: Message = await bot.listen(m.chat.id)

            # Check if it's a video
            if file_msg.video:
                media = file_msg.video
                ext = os.path.splitext(media.file_name or media.file_id)[1] or ".mp4"

            # Check if it's a .mkv document
            elif file_msg.document and file_msg.document.file_name.lower().endswith(".mkv"):
                media = file_msg.document
                ext = ".mkv"

            # If it's neither, send error
            else:
                return await m.reply_text("❌ Invalid file. Please send a supported video or .mkv file.")

            # Ensure the download directory exists
            ensure_dir(download_dir)

            file_name = os.path.join(download_dir, f"input_{file_msg.id}{ext}")

            # Download the file
            local_in = await file_msg.download(file_name=file_name)

            # Confirm download
            await m.reply_text(f"✅ Downloaded: `{os.path.basename(local_in)}`")

            # Ask for FFmpeg arguments
            help_text = (
                "Send your **ffmpeg** arguments.\n"
                "For example: `-vf scale=1280:720 -c:v libx264 -crf 23`\n"
                "Type `help` to see more examples."
            )
            await m.reply_text(help_text)

            # Listen for the user inputting ffmpeg args
            cmd_msg: Message = await bot.listen(m.chat.id)
            ff_args = cmd_msg.text.strip()

            # If user asks for help/examples
            if ff_args.lower() in ("help", "?", "examples"):
                examples = (
                    "`-vf scale=1280:720 -c:v libx264 -crf 23`\n"
                    "`-q:v 2 -preset slow`\n"
                    "`-c:v copy -c:a copy` (stream copy/no re-encode)"
                )
                await m.reply_text(
                    f"Here are some example ffmpeg args:\n{examples}\n\nNow please send your ffmpeg arguments:"
                )
                cmd_msg = await bot.listen(m.chat.id)
                ff_args = cmd_msg.text.strip()

            # Create output file path
            base, _ = os.path.splitext(local_in)
            local_out = f"{base}_pro.mkv"

            # Build the ffmpeg command
            cmd = f"ffmpeg -i '{local_in}' {ff_args} '{local_out}'"
            await m.reply_text(f"⚙️ Processing with ffmpeg...\n`{cmd}`")

            # Run the ffmpeg command
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            # Check if processing was successful
            if proc.returncode != 0:
                # Capture full error message
                err_msg = stderr.decode(errors="ignore").strip()
                logging.error(f"FFmpeg processing failed for file {file_name}. Full error message:\n{err_msg}")
                
                # Split and send long error messages
                await send_message_in_parts(bot, m.chat.id, f"❌ Processing failed:\n`{err_msg}`")
                return

            # Upload the processed file
            await m.reply_chat_action(ChatAction.UPLOAD_DOCUMENT)
            await m.reply_document(local_out, caption="✅ Here is your processed file.")

            # Clean up files
            for path in (local_in, local_out):
                try:
                    os.remove(path)
                except OSError as e:
                    logging.error(f"Error removing file {path}: {e}")

        except Exception as e:
            logging.error(f"Unexpected error in pro_handler: {e}")
            await send_message_in_parts(bot, m.chat.id, f"❌ An unexpected error occurred: {e}")