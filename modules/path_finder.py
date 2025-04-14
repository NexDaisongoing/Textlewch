import os
import subprocess
import asyncio
import time
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from utils import generate_progress_bar


def is_ffmpeg_installed():
    try:
        result = subprocess.run(['which', 'ffmpeg'], capture_output=True, text=True)
        return result.returncode == 0
    except Exception:
        return False


def find_ffmpeg_path():
    if is_ffmpeg_installed():
        return subprocess.getoutput("which ffmpeg")
    return None


async def install_ffmpeg_with_progress(message: Message):
    progress_msg = await message.reply_text("Starting FFmpeg installation...")

    proc = await asyncio.create_subprocess_exec(
        'apt', 'install', '-y', 'ffmpeg',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )

    total = 360  # Simulated total size in MB
    downloaded = 0
    start_time = time.time()

    last_update_time = time.time()

    while True:
        line = await proc.stdout.readline()
        if not line:
            break

        downloaded = min(total, downloaded + 4)  # Simulate download progress
        elapsed = time.time() - start_time
        eta = max(0, ((total - downloaded) / (downloaded / elapsed))) if downloaded else 0

        # Update progress every 3-4 seconds to avoid flooding
        if time.time() - last_update_time >= 3:  # Update after every 3 seconds
            progress = generate_progress_bar(
                current_mb=downloaded,
                total_mb=total,
                speed_kbps=300,
                elapsed=time.strftime('%H:%M:%S', time.gmtime(elapsed)),
                eta=time.strftime('%H:%M:%S', time.gmtime(eta))
            )
            await progress_msg.edit_text(progress)
            last_update_time = time.time()  # Reset the last update time
        
        await asyncio.sleep(0.5)

    await proc.wait()

    if is_ffmpeg_installed():
        path = find_ffmpeg_path()
        await progress_msg.edit_text(f"✅ FFmpeg installed successfully.\nPath: `{path}`")
    else:
        await progress_msg.edit_text("❌ FFmpeg installation failed. Please try manually.")


def register_ffmpeg_path_handler(bot):
    @bot.on_message(filters.command("path"))
    async def handle_path_command(client, message: Message):
        ffmpeg_path = find_ffmpeg_path()
        if ffmpeg_path:
            await message.reply_text(f"✅ FFmpeg found at:\n`{ffmpeg_path}`")
        else:
            await message.reply_text(
                "❌ FFmpeg is not installed.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Install FFmpeg", callback_data="install_ffmpeg")]
                ])
            )

    @bot.on_callback_query(filters.regex("install_ffmpeg"))
    async def handle_ffmpeg_install_cb(client, callback_query):
        await callback_query.answer()
        await install_ffmpeg_with_progress(callback_query.message)