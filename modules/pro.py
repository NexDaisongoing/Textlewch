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



def pro_feature(bot: Client) -> None:
    """
    Registers the /pro command to process videos with FFmpeg interactively.
    """
    register_test_toggle(bot)

    @bot.on_message(filters.command("pro") & filters.private)
    async def pro_handler(_, msg: Message):
        chat_id = msg.chat.id
        # Initialize toggle if missing
        feature_toggles.setdefault(chat_id, True)

        try:
            # 1️⃣ Prompt for input file
            prompt = await msg.reply_text(
                "🔄 **FFmpeg Pro**\n\nSend a video or .mkv file."
            )
            file_msg: Message = await bot.listen(chat_id)
            await prompt.delete()

            # 2️⃣ Start status message: downloading
            status = await msg.reply_text(
                "🔄 **FFmpeg Pro**\n\n📥 Downloading..."
            )

            # Validate and download
            if file_msg.video:
                media = file_msg.video
                ext = os.path.splitext(media.file_name or media.file_id)[1] or ".mp4"
            elif file_msg.document and file_msg.document.file_name.lower().endswith('.mkv'):
                media = file_msg.document
                ext = '.mkv'
            else:
                await status.edit_text(
                    "❌ **FFmpeg Pro**\n\nInvalid file. Try /pro again."
                )
                return

            # Ensure directory
            ensure_dir(download_dir)
            original_name = media.file_name or f"input_{file_msg.id}{ext}"
            local_input = os.path.join(download_dir, original_name)
            await media.download(file_name=local_input)

            # 3️⃣ Prompt for FFmpeg arguments
            await status.edit_text(
                f"🔄 **FFmpeg Pro**\n\n✅ Downloaded `{original_name}`\n\n📝 Send FFmpeg args or 'help' for examples."
            )
            cmd_msg: Message = await bot.listen(chat_id)
            ff_args = cmd_msg.text.strip()
            await cmd_msg.delete()

            # Show examples if requested
            if ff_args.lower() in ('help', '?', 'examples'):
                examples = (
                    "-vf scale=1280:720 -c:v libx264 -crf 23", 
                    "-q:v 2 -preset slow",
                    "-c:v copy -c:a copy"
                )
                await status.edit_text(
                    "🔄 **FFmpeg Pro**\n\nExamples:\n" + '\n'.join(f"`{e}`" for e in examples)
                    + "\n\nNow send your args."
                )
                cmd_msg = await bot.listen(chat_id)
                ff_args = cmd_msg.text.strip()
                await cmd_msg.delete()

            # 4️⃣ Processing
            base, _ = os.path.splitext(original_name)
            output_path = os.path.join(download_dir, f"{base} @Anime_Surge.mkv")
            await status.edit_text(
                "🔄 **FFmpeg Pro**\n\n⚙️ Running FFmpeg..."
            )

            process = await asyncio.create_subprocess_shell(
                f"ffmpeg -i '{local_input}' {ff_args} '{output_path}'",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, err = await process.communicate()

            if process.returncode != 0:
                err_text = err.decode(errors='ignore')
                logging.error(f"FFmpeg error: {err_text}")
                await status.edit_text(
                    "❌ **FFmpeg Pro**\n\nProcessing failed."
                )
                await send_long_message(bot, chat_id, f"Error details:\n`{err_text}`")
                os.remove(local_input)
                return

            # 5️⃣ Upload result
            await status.edit_text(
                "📤 **FFmpeg Pro**\n\nUploading file..."
            )
            await msg.reply_chat_action(ChatAction.UPLOAD_DOCUMENT)
            await msg.reply_document(output_path, caption="✅ Done!")

            # Optional: echo command if /test is on
            if feature_toggles[chat_id]:
                await msg.reply_text(f"`ffmpeg {ff_args}`", parse_mode='markdown')

            # 6️⃣ Cleanup & final status
            for path in (local_input, output_path):
                try:
                    os.remove(path)
                except OSError:
                    pass

            await status.edit_text(
                "✅ **FFmpeg Pro** Complete!\nUse /pro again to process another file."
            )

        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            await send_long_message(bot, chat_id, f"❌ Unexpected error:\n`{e}`")

