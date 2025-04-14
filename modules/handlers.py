import re
from pyrogram import Client, filters
from pyrogram.types import Message
from core import (
    handle_direct_link,
    process_with_ffmpeg,
    send_vid,
    is_direct_media_url,
    download_video
)

# Define a filter for direct video links
direct_video_pattern = re.compile(
    r'https?://.*\.(mp4|mkv|avi|mov|webm|flv|3gp|wmv|m4v)(\?.*)?$',
    re.IGNORECASE
)

def register_handlers(bot: Client):

    @bot.on_message(filters.command(["direct"]) & filters.text)
    async def direct_link_command(client, message: Message):
        """Handle /direct command to download and process direct media links."""
        url = None
        if len(message.command) > 1:
            url = message.command[1]
        elif message.reply_to_message and message.reply_to_message.text:
            urls = re.findall(r'(https?://[^\s]+)', message.reply_to_message.text)
            if urls:
                url = urls[0]

        if not url:
            await message.reply_text("❌ Please provide a direct media URL or reply to a message containing a URL.")
            return

        # Optional: Extract FFmpeg params
        custom_ffmpeg = None
        ffmpeg_match = re.search(r'ffmpeg:(.+?)(?:\s|$)', message.text)
        if ffmpeg_match:
            custom_ffmpeg = ffmpeg_match.group(1).strip()

        # Optional: Extract filename
        custom_filename = None
        filename_match = re.search(r'filename:(.+?)(?:\s|$)', message.text)
        if filename_match:
            custom_filename = filename_match.group(1).strip()

        await handle_direct_link(message, url, custom_filename, custom_ffmpeg)

    @bot.on_message(filters.regex(direct_video_pattern) & ~filters.command([]))
    async def auto_direct_link_handler(client, message: Message):
        """Automatically handle direct video links in messages."""
        urls = re.findall(
            r'(https?://[^\s]+\.(mp4|mkv|avi|mov|webm|flv|3gp|wmv|m4v)(\?.*)?)',
            message.text, re.IGNORECASE
        )
        if not urls:
            return

        url = urls[0][0]

        confirm_msg = await message.reply_text(
            f"📽️ Direct media link detected: `{url}`\n\n"
            f"**Choose an option:**\n"
            f"- `!download` — Download and upload to Telegram\n"
            f"- `!process` — Download, process via FFmpeg, then upload\n"
            f"- `!cancel` — Cancel"
        )

        @bot.on_message(filters.reply & filters.text & filters.user(message.from_user.id), group=123)
        async def wait_for_response(client, response: Message):
            if response.reply_to_message.id != confirm_msg.id:
                return

            bot.remove_handler(wait_for_response, group=123)

            command = response.text.lower().strip()

            if command == "!download":
                await handle_direct_link(message, url)

            elif command == "!process":
                ffmpeg_msg = await message.reply_text(
                    "Please provide FFmpeg parameters.\n\n"
                    "Example: `-c:v libx264 -preset medium -crf 23 -c:a aac -b:a 128k`\n\n"
                    "Or type `!default` or `!cancel`."
                )

                @bot.on_message(filters.reply & filters.text & filters.user(message.from_user.id), group=124)
                async def wait_for_ffmpeg(client, ffmpeg_response: Message):
                    if ffmpeg_response.reply_to_message.id != ffmpeg_msg.id:
                        return

                    bot.remove_handler(wait_for_ffmpeg, group=124)

                    ffmpeg_params = ffmpeg_response.text.strip()
                    if ffmpeg_params.lower() == "!cancel":
                        await ffmpeg_msg.edit("❌ Operation cancelled.")
                        return
                    elif ffmpeg_params.lower() == "!default":
                        ffmpeg_params = "-c:v libx264 -preset medium -crf 23 -c:a aac -b:a 128k"

                    await handle_direct_link(message, url, None, ffmpeg_params)

            elif command == "!cancel":
                await confirm_msg.edit("❌ Operation cancelled.")
            else:
                await confirm_msg.edit("❌ Invalid command. Operation cancelled.")

    @bot.on_message(filters.command(["process"]) & filters.text)
    async def process_media_command(client, message: Message):
        """/process URL \"ffmpeg params\" — Custom FFmpeg media processing."""
        if len(message.command) < 3:
            await message.reply_text(
                "❌ Usage: `/process URL \"ffmpeg parameters\"`\n"
                "Example: `/process https://example.com/video.mp4 \"-c:v libx264 -crf 23\"`"
            )
            return

        url = message.command[1]
        ffmpeg_params = ' '.join(message.command[2:])
        await handle_direct_link(message, url, None, ffmpeg_params)

    @bot.on_message(filters.command(["ffmpeg_presets"]))
    async def show_ffmpeg_presets(client, message: Message):
        """/ffmpeg_presets — Show available FFmpeg presets."""
        presets = {
            "compress": "-c:v libx264 -preset slow -crf 28 -c:a aac -b:a 96k",
            "hevc": "-c:v libx265 -preset medium -crf 28 -c:a aac -b:a 128k",
            "fastcompress": "-c:v libx264 -preset ultrafast -crf 28 -c:a aac -b:a 96k",
            "hd": "-c:v libx264 -preset slow -crf 18 -c:a aac -b:a 192k",
            "gif": "-vf \"fps=10,scale=320:-1:flags=lanczos\" -c:v gif",
            "remux": "-c copy",
            "normalize_audio": "-c:v copy -c:a aac -af \"loudnorm=I=-16:LRA=11:TP=-1.5\" -b:a 192k"
        }

        text = "**📋 Available FFmpeg Presets:**\n\n"
        for name, params in presets.items():
            text += f"• **{name}**: `/process URL \"{params}\"`\n\n"

        await message.reply_text(text)

    print("✅ Handlers registered from handlers.py")