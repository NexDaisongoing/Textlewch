import os
import time
import logging
from pyrogram import Client
from pyrogram.types import Message

from bar import upload_progress_bar
from process import get_duration, generate_thumbnail

logger = logging.getLogger(__name__)

async def send_doc(bot: Client, m: Message, caption, file_path, reply_caption, progress_msg=None, count=0, name=None):
    """Send a document (file) to Telegram chat"""
    if not name:
        name = os.path.basename(file_path)
    
    if progress_msg:
        await progress_msg.delete()
    
    reply = await m.reply_text(f"Uploading » `{name}`")
    time.sleep(1)
    start_time = time.time()
    
    try:
        # Send the document with progress tracking
        await m.reply_document(
            file_path, 
            caption=reply_caption,
            progress=upload_progress_bar,
            progress_args=(reply, start_time)
        )
        
        count += 1
        await reply.delete()
        time.sleep(1)
        os.remove(file_path)
        
    except Exception as e:
        logger.error(f"Failed to send document: {e}")
        await m.reply_text(f"❌ Failed to send document: {str(e)}")
    
    time.sleep(3)
    return count


async def send_vid(bot: Client, m: Message, caption, filename, thumb, name, progress_msg=None):
    """Send a video to Telegram chat with proper formatting and thumbnails"""
    try:
        # Generate thumbnail if needed
        if thumb == "no":
            thumbnail = generate_thumbnail(filename)
        else:
            thumbnail = thumb
            
        # Clean up progress message if present
        if progress_msg:
            await progress_msg.delete()
            
        # Create a new reply for upload progress tracking
        reply = await m.reply_text(f"**⥣ Uploading ...** » `{name}`")
        
        # Get video duration
        dur = int(get_duration(filename))
        start_time = time.time()
        
        try:
            # Try to send as video with proper metadata
            await m.reply_video(
                filename,
                caption=caption,
                supports_streaming=True,
                height=720,
                width=1280,
                thumb=thumbnail,
                duration=dur,
                progress=upload_progress_bar,
                progress_args=(reply, start_time)
            )
        except Exception as e:
            # If video sending fails, fallback to document
            logger.error(f"Failed to send video: {e}")
            await reply.edit(f"❌ Failed to send as video. Sending as document...")
            
            await m.reply_document(
                filename,
                caption=caption,
                progress=upload_progress_bar,
                progress_args=(reply, start_time)
            )
            
    except Exception as e:
        await m.reply_text(f"❌ Error during upload: {str(e)}")
        logger.exception("Upload error")
    
    finally:
        # Clean up files
        if os.path.exists(filename):
            os.remove(filename)
        if os.path.exists(f"{filename}.jpg"):
            os.remove(f"{filename}.jpg")
        if os.path.exists(reply):
            await reply.delete()
