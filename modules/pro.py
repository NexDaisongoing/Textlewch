import os
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatAction
from pyromod import listen  # For interactive prompts

# Configure logger to record only errors
logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler('bot_errors.log')]
)

# Directory for downloads and outputs
download_dir = os.path.join('.', 'downloads', 'pro')
# In-memory toggle for the /test feature per chat
feature_toggles = {}


def ensure_dir(path: str) -> None:
    """
    Ensure a directory exists, creating it if necessary.
    """
    os.makedirs(path, exist_ok=True)


async def send_long_message(bot: Client, chat_id: int, text: str) -> None:
    """
    Splits long messages into chunks under Telegram limits.
    """
    max_len = 4096
    for i in range(0, len(text), max_len):
        await bot.send_message(chat_id, text[i:i + max_len])


def register_test_toggle(bot: Client) -> None:
    """
    Adds a /test command to turn the verbose feedback on/off.
    """
    @bot.on_message(filters.command("test") & filters.private)
    async def toggle(_, msg: Message):
        args = msg.text.split()
        current = feature_toggles.get(msg.chat.id, True)

        if len(args) == 1:
            status = 'ON' if current else 'OFF'
            await msg.reply_text(f"/test is {status}.")
        else:
            choice = args[1].lower()
            if choice in ('on', 'off'):
                feature_toggles[msg.chat.id] = (choice == 'on')
                await msg.reply_text(f"/test turned {choice.upper()}.")
            else:
                await msg.reply_text("Usage: /test on|off")



async def pro_handler(_, m: Message):  
    try:  
        # Default test flag on  
        if m.chat.id not in test_feature:  
            test_feature[m.chat.id] = True  

        # Initial status message
        status_message = await m.reply_text("🔄 **FFmpeg Processing Status**\n\n📥 Please send me a video file or an .mkv document.")  
        
        # Wait for user to send file
        file_msg: Message = await bot.listen(m.chat.id)  

        # Update status message and delete user's file message
        await status_message.edit_text("🔄 **FFmpeg Processing Status**\n\n🔍 Checking file type...")  
        await file_msg.delete()

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

        # Update status to downloading
        await status_message.edit_text(f"🔄 **FFmpeg Processing Status**\n\n📥 Downloading file: `{original_name}`\n\nPlease wait...")  
        local_in = await file_msg.download(file_name=file_name)  

        # Update status to prompt for FFmpeg args
        help_text = (  
            "🔄 **FFmpeg Processing Status**\n\n"  
            f"✅ Downloaded: `{os.path.basename(local_in)}`\n\n"  
            "📝 Send your **ffmpeg** arguments.\n"  
            "For example: `-vf scale=1280:720 -c:v libx264 -crf 23`\n"  
            "Type `help` to see more examples."  
        )  
        await status_message.edit_text(help_text)  

        # Wait for FFmpeg arguments
        cmd_msg: Message = await bot.listen(m.chat.id)  
        ff_args = cmd_msg.text.strip()  
        
        # Delete the user's FFmpeg command message
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
                f"📋 Here are some example ffmpeg args:\n{examples}\n\nNow please send your ffmpeg arguments:"  
            )  
            cmd_msg = await bot.listen(m.chat.id)  
            ff_args = cmd_msg.text.strip()  
            # Delete the user's second FFmpeg command message if they asked for help
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
                f"❌ Processing failed\n\nError message is too long, sending separately..."  
            )  
            await send_message_in_parts(bot, m.chat.id, f"❌ FFmpeg Error:\n`{err_msg}`")  
            os.remove(local_in)  
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

        # If test feature enabled, send ffmpeg command in monospace  
        if test_feature.get(m.chat.id, True):  
            await m.reply_text(f"Here is the FFmpeg command used:\n```bash\n{ff_args}\n```")  

        # Final status update
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