import os
import asyncio
import logging
from pyrogram import filters, Client
from pyrogram.types import Message
from pyrogram.enums import ChatAction
from pyromod import listen
from collections import deque

# Set up logging configuration to capture only errors
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_errors.log'),
    ]
)

# Directory where files are stored and processed
download_dir = "./downloads/batch"

# Function to create the directory if it doesn't exist
def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

# Function to split messages that are too long
async def send_message_in_parts(bot, chat_id, message):
    max_length = 4096
    message_parts = [message[i:i+max_length] for i in range(0, len(message), max_length)]
    for part in message_parts:
        await bot.send_message(chat_id, part)

# Process a single file with ffmpeg
async def process_file(bot, chat_id, file_info, ff_args):
    try:
        file_path = file_info["path"]
        file_name = os.path.basename(file_path)
        
        # Get original name to create branded output filename
        original_name = file_info.get("original_name", os.path.basename(file_path))
        base_name, ext = os.path.splitext(original_name)
        
        # Create output file path with @Anime_Surge branding
        output_filename = f"{base_name} @Anime_Surge{ext}"
        local_out = os.path.join(os.path.dirname(file_path), output_filename)

        # Build the ffmpeg command
        cmd = f"ffmpeg -i '{file_path}' {ff_args} '{local_out}'"
        await bot.send_message(chat_id, f"⚙️ Processing {file_name}...\n`{cmd}`")

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
            await send_message_in_parts(bot, chat_id, f"❌ Processing {file_name} failed:\n`{err_msg}`")
            return False, None

        # Success
        return True, local_out
    except Exception as e:
        logging.error(f"Error processing file {file_path}: {e}")
        await bot.send_message(chat_id, f"❌ Error processing {os.path.basename(file_path)}: {e}")
        return False, None

# Batch processing worker function
async def batch_worker(bot, chat_id, queue, ff_args, semaphore):
    while queue:
        async with semaphore:
            if not queue:  # Check again in case queue emptied while waiting
                break
                
            file_info = queue.popleft()
            
            # Process the file
            success, output_path = await process_file(bot, chat_id, file_info, ff_args)
            
            if success:
                # Upload the processed file
                await bot.send_chat_action(chat_id, ChatAction.UPLOAD_DOCUMENT)
                try:
                    # Get original filename for the caption
                    original_name = file_info.get("original_name", os.path.basename(file_info['path']))
                    await bot.send_document(
                        chat_id, 
                        output_path, 
                        caption=f"✅ Processed: {original_name}",
                        file_name=os.path.basename(output_path)  # Ensure the file is sent with the branded name
                    )
                except Exception as e:
                    await bot.send_message(
                        chat_id,
                        f"❌ Failed to upload processed file: {os.path.basename(output_path)}\nError: {e}"
                    )
                
                # Clean up files
                try:
                    os.remove(file_info["path"])
                    os.remove(output_path)
                except OSError as e:
                    logging.error(f"Error removing files: {e}")

# Main handler function for the "batch" command
def batch_feature(bot: Client):
    @bot.on_message(filters.command("batch") & filters.private)
    async def batch_handler(_, m: Message):
        try:
            chat_id = m.chat.id
            user_id = m.from_user.id
            
            # Ask for FFmpeg arguments first
            help_text = (
                "First, send your **ffmpeg** arguments for batch processing.\n"
                "For example: `-vf scale=1280:720 -c:v libx264 -crf 23`\n"
                "Type `help` to see more examples."
            )
            await m.reply_text(help_text)

            # Listen for the user inputting FFmpeg args
            cmd_msg: Message = await bot.listen(chat_id)
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
                cmd_msg = await bot.listen(chat_id)
                ff_args = cmd_msg.text.strip()

            # Ensure the download directory exists
            ensure_dir(download_dir)
            
            # Prepare to collect files
            await m.reply_text(
                "📥 Now send me your video files one by one.\n"
                "Send `/bs` when you're done to start batch processing."
            )
            
            # Collect files in a queue
            file_queue = deque()
            
            while True:
                file_msg: Message = await bot.listen(chat_id)
                
                # Check if user wants to start processing
                if file_msg.text and file_msg.text.startswith("/bs"):
                    break
                
                # Check if it's a video
                if file_msg.video:
                    media = file_msg.video
                    ext = os.path.splitext(media.file_name or f"video_{file_msg.id}")[1] or ".mp4"
                    file_type = "video"
                
                # Check if it's a supported document
                elif file_msg.document and any(file_msg.document.file_name.lower().endswith(ext) 
                                             for ext in [".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv"]):
                    media = file_msg.document
                    ext = os.path.splitext(media.file_name)[1]
                    file_type = "document"
                
                # If it's neither, send error and continue
                else:
                    await m.reply_text("❌ Unsupported file. Please send a video file.")
                    continue
                
                # Get original filename and create a unique path
                if file_type == "video":
                    original_name = media.file_name or f"video_{file_msg.id}{ext}"
                else:  # document
                    original_name = media.file_name
                
                # Create a unique path with original name preserved
                safe_filename = ''.join(c if c.isalnum() or c in '._- ' else '_' for c in original_name)
                file_path = os.path.join(download_dir, safe_filename)
                
                # Ensure unique path by adding number if needed
                counter = 1
                while os.path.exists(file_path):
                    base_name, extension = os.path.splitext(safe_filename)
                    file_path = os.path.join(download_dir, f"{base_name}_{counter}{extension}")
                    counter += 1
                
                # Download the file
                await m.reply_text(f"⬇️ Downloading file {len(file_queue) + 1}: {original_name}")
                try:
                    local_path = await file_msg.download(file_name=file_path)
                    file_queue.append({
                        "id": file_msg.id,
                        "path": local_path,
                        "type": file_type,
                        "original_name": original_name
                    })
                    await m.reply_text(f"✅ Downloaded: `{os.path.basename(local_path)}` ({len(file_queue)} files in queue)")
                except Exception as e:
                    await m.reply_text(f"❌ Failed to download file: {e}")
            
            # Check if there are any files to process
            if not file_queue:
                return await m.reply_text("❌ No files to process.")
            
            # Confirm batch processing is starting
            await m.reply_text(
                f"🚀 Starting batch processing of {len(file_queue)} files with the following FFmpeg arguments:\n"
                f"`{ff_args}`\n\n"
                f"Processing up to 5 files simultaneously."
            )
            
            # Create a semaphore to limit concurrent processing to 5 files
            semaphore = asyncio.Semaphore(5)
            
            # Start the batch processing
            await batch_worker(bot, chat_id, file_queue, ff_args, semaphore)
            
            # Notify when all files are done
            await m.reply_text("✅ Batch processing complete!")
            
        except Exception as e:
            logging.error(f"Unexpected error in batch_handler: {e}")
            await send_message_in_parts(bot, chat_id, f"❌ An unexpected error occurred: {e}")
    
    # Add command handler for /bs outside of batch processing
    @bot.on_message(filters.command("bs") & filters.private)
    async def bs_outside_batch(_, m: Message):
        await m.reply_text("❗ Use /bs only after starting batch processing with /batch command.")