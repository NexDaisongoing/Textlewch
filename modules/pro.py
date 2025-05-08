import os
import re
import asyncio
import logging
import time
import psutil
import shlex
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
        # Get input duration and info using ffprobe
        probe_cmd = [
            'ffprobe', 
            '-v', 'error', 
            '-select_streams', 'v:0',  # Select video stream
            '-show_entries', 'stream=width,height,r_frame_rate,avg_frame_rate,duration,bit_rate,nb_frames,codec_name:format=duration,bit_rate,size',
            '-of', 'json', 
            input_path
        ]
        
        probe_process = await asyncio.create_subprocess_exec(
            *probe_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await probe_process.communicate()
        
        # Handle possible ffprobe errors
        if probe_process.returncode != 0:
            await status_msg.edit_text(f"❌ Error getting video info: {stderr.decode().strip()}")
            return None
        
        try:
            import json
            probe_data = json.loads(stdout.decode())
            
            # Extract video information
            stream_info = probe_data.get('streams', [{}])[0]
            format_info = probe_data.get('format', {})
            
            # Get duration (try multiple sources)
            total_duration = float(stream_info.get('duration') or format_info.get('duration', 0))
            
            # Get frame rate
            frame_rate = stream_info.get('r_frame_rate', '25/1')
            if '/' in frame_rate:
                num, den = map(int, frame_rate.split('/'))
                frame_rate = num / den if den != 0 else 25
            else:
                frame_rate = float(frame_rate) if frame_rate else 25
                
            # Get total frames
            total_frames = int(stream_info.get('nb_frames', 0))
            if not total_frames and total_duration > 0:
                total_frames = int(total_duration * frame_rate)
                
            # Get resolution
            width = stream_info.get('width', 0)
            height = stream_info.get('height', 0)
            
            # Get bitrate
            input_bitrate = int(stream_info.get('bit_rate') or format_info.get('bit_rate', 0))
            
            # Get codec
            input_codec = stream_info.get('codec_name', 'unknown')
            
        except Exception as e:
            logging.error(f"Error parsing probe data: {str(e)}")
            total_duration = 0
            total_frames = 0
            frame_rate = 25
            width = 0
            height = 0
            input_bitrate = 0
            input_codec = 'unknown'
        
        # Get file size
        total_size = os.path.getsize(input_path)
        
        # Display input file information
        input_info = (
            "📂 Input File Information:\n"
            f"▫️ Size: {format_size(total_size)}\n"
            f"▫️ Duration: {format_time(total_duration)}\n"
            f"▫️ Resolution: {width}x{height}\n"
            f"▫️ Codec: {input_codec}\n"
            f"▫️ Bitrate: {input_bitrate/1000:.0f} kbps\n"
            f"▫️ Framerate: {frame_rate:.3f} fps\n\n"
            "⚙️ Send your FFmpeg command:"
        )
        
        await status_msg.edit_text(input_info)
        
        # Get user command with input info context
        cmd_msg = await bot.listen(m.chat.id)
        ffmpeg_cmd = cmd_msg.text.strip()
        await cmd_msg.delete()
        
        # Prepare and validate FFmpeg command
        ff_args = ffmpeg_cmd
        
        # Identify codec from command
        codec_match = re.search(r'-c:v\s+(\w+)', ff_args)
        target_codec = codec_match.group(1) if codec_match else "unknown"
        
        # Split the command correctly, handling quotes properly
        try:
            parsed_args = shlex.split(ff_args)
        except Exception as e:
            await status_msg.edit_text(f"❌ Error parsing command: {str(e)}")
            return None
            
        cmd = [
            'ffmpeg',
            '-hide_banner',
            '-loglevel', 'info',  # Ensure we get enough info for progress
            '-stats',             # Show progress statistics
            '-y',
            '-i', input_path,
            *parsed_args,
            output_path
        ]

        # Log the command for debugging
        logging.info(f"Running FFmpeg command: {' '.join(cmd)}")
        
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        output_path = os.path.join(DOWNLOAD_DIR, f"{base_name}_processed.mkv")
        
        # Notify user that processing is starting
        await status_msg.edit_text(
            f"🎬 Starting FFmpeg Processing\n\n"
            f"Input: {os.path.basename(input_path)}\n"
            f"Target Codec: {target_codec}\n"
            f"Command: <code>{ff_args}</code>"
        )
        
        # Start FFmpeg process
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # Initialize progress variables
        progress_data = {
            'frame': 0,
            'fps': 0,
            'time': 0,
            'bitrate': 0,
            'speed': 0,
            'size_kb': 0,
            'q': 0,  # Quality factor
            'dup': 0,  # Duplicate frames
            'drop': 0,  # Dropped frames
        }
        
        # Create update task
        last_update_time = 0
        UPDATE_INTERVAL = 2  # Update message every 2 seconds
        
        # Read stderr for progress updates
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
                
            decoded_line = line.decode("utf-8", errors="ignore").strip()
            if not decoded_line:
                continue
            
            # Log for debugging
            logging.debug(f"FFMPEG: {decoded_line}")
                
            # Parse progress information from stderr
            # Extract frame
            frame_match = re.search(r"frame=\s*(\d+)", decoded_line)
            if frame_match:
                progress_data['frame'] = int(frame_match.group(1))
            
            # Extract fps
            fps_match = re.search(r"fps=\s*([\d\.]+)", decoded_line)
            if fps_match and fps_match.group(1) != "0.0":
                progress_data['fps'] = float(fps_match.group(1))
            
            # Extract time
            time_match = re.search(r"time=\s*(\d+):(\d+):(\d+\.\d+)", decoded_line)
            if time_match:
                hours = int(time_match.group(1))
                minutes = int(time_match.group(2))
                seconds = float(time_match.group(3))
                progress_data['time'] = hours * 3600 + minutes * 60 + seconds
            
            # Extract bitrate
            bitrate_match = re.search(r"bitrate=\s*([\d\.]+)\s*kbits/s", decoded_line)
            if bitrate_match and bitrate_match.group(1) != "N/A":
                progress_data['bitrate'] = float(bitrate_match.group(1))
            
            # Extract speed
            speed_match = re.search(r"speed=\s*([\d\.]+)x", decoded_line)
            if speed_match:
                progress_data['speed'] = float(speed_match.group(1))
            
            # Extract size
            size_match = re.search(r"size=\s*(\d+)kB", decoded_line)
            if size_match:
                progress_data['size_kb'] = int(size_match.group(1))
                
            # Extract quality factor (q)
            q_match = re.search(r"q=\s*([\d\.]+)", decoded_line)
            if q_match:
                progress_data['q'] = float(q_match.group(1))
                
            # Extract duplicate frames
            dup_match = re.search(r"dup=\s*(\d+)", decoded_line)
            if dup_match:
                progress_data['dup'] = int(dup_match.group(1))
                
            # Extract dropped frames
            drop_match = re.search(r"drop=\s*(\d+)", decoded_line)
            if drop_match:
                progress_data['drop'] = int(drop_match.group(1))
            
            # Update status message at regular intervals
            current_time = time.time()
            if current_time - last_update_time >= UPDATE_INTERVAL and progress_data['time'] > 0:
                last_update_time = current_time
                
                # Calculate progress percentage based on time
                percentage = min(100, (progress_data['time'] / total_duration) * 100) if total_duration > 0 else 0
                
                # Calculate ETA
                elapsed = current_time - start_time
                if progress_data['speed'] > 0:
                    eta = (total_duration - progress_data['time']) / progress_data['speed']
                else:
                    remaining_time = total_duration - progress_data['time']
                    eta = remaining_time * (elapsed / max(0.1, progress_data['time']))
                
                # Get system resources
                cpu = psutil.cpu_percent()
                ram = psutil.virtual_memory()
                
                # Format output size
                output_size = progress_data['size_kb'] * 1024  # Convert KB to bytes
                speed_display = f"{progress_data['speed']:.2f}x" if progress_data['speed'] > 0 else "N/A"
                bitrate_display = f"{progress_data['bitrate']:.1f} kbits/s" if progress_data['bitrate'] > 0 else "N/A"
                
                # Calculate compression ratio so far
                compression_ratio = total_size / (output_size if output_size > 0 else total_size)
                
                # Calculate estimated final size
                est_final_size = output_size / (progress_data['time'] / total_duration) if progress_data['time'] > 0 else 0
                
                progress_text = (
                    "🔄 Encoding Progress:\n\n"
                    f"{get_progress_bar(percentage)} {percentage:.1f}%\n"
                    f"⏱️ Time: {format_time(progress_data['time'])} / {format_time(total_duration)}\n"
                    f"🎞️ Frames: {progress_data['frame']} @ {progress_data['fps']:.1f} FPS\n"
                    f"📊 Quality: q={progress_data['q']:.1f}\n"
                    f"📦 Size: {format_size(output_size)} (Est. Final: {format_size(est_final_size)})\n"
                    f"🔄 Compression: {compression_ratio:.2f}x\n"
                    f"📈 Bitrate: {bitrate_display} | ⚡ Speed: {speed_display}\n"
                    f"⏳ ETA: {format_time(eta)} | ⌛ Elapsed: {format_time(elapsed)}\n"
                )
                
                # Add duplicate/drop frames if available
                if progress_data['dup'] > 0 or progress_data['drop'] > 0:
                    progress_text += f"🔄 Dup: {progress_data['dup']} | 🗑️ Drop: {progress_data['drop']}\n"
                
                # Add system info and command
                progress_text += (
                    f"\n🖥️ CPU: {cpu}% | 🧠 RAM: {format_size(ram.used)}/{format_size(ram.total)}\n\n"
                    f"<code>{ff_args}</code>"
                )
                
                try:
                    await status_msg.edit_text(progress_text)
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        logging.warning(f"Progress update error: {e}")
        
        # Wait for process to complete
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="ignore").strip()
            error_lines = error_msg.split('\n')
            
            # Filter for meaningful error messages
            filtered_errors = []
            for line in error_lines:
                lower_line = line.lower()
                if "error" in lower_line or "invalid" in lower_line or "unable" in lower_line or "not found" in lower_line:
                    filtered_errors.append(line)
            
            # If no specific error lines found, take the last few lines
            if not filtered_errors:
                filtered_errors = error_lines[-10:]
                
            relevant_error = '\n'.join(filtered_errors)
            
            # Check for missing dependencies
            if "encoder not found" in error_msg:
                if "libx265" in error_msg:
                    relevant_error += "\n\nPossible issue: The libx265 encoder is not available in this FFmpeg build."
                elif "libx264" in error_msg:
                    relevant_error += "\n\nPossible issue: The libx264 encoder is not available in this FFmpeg build."
                else:
                    relevant_error += "\n\nPossible issue: The requested encoder is not available in this FFmpeg build."
            
            await status_msg.edit_text(
                f"❌ FFmpeg Processing Failed\n\n"
                f"Error: {relevant_error}\n\n"
                f"Command: <code>{ff_args}</code>"
            )
            return None
        
        # Check if output file exists and has size
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            await status_msg.edit_text(
                f"❌ FFmpeg Processing Failed\n\n"
                f"Output file is missing or empty. Check FFmpeg command."
            )
            return None
        
        # Final success message
        final_size = os.path.getsize(output_path)
        compression_ratio = (total_size / final_size) if final_size > 0 else 0
        
        # Get output file information
        probe_cmd = [
            'ffprobe', 
            '-v', 'error', 
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,r_frame_rate,duration,bit_rate,codec_name',
            '-of', 'json', 
            output_path
        ]
        
        probe_process = await asyncio.create_subprocess_exec(
            *probe_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await probe_process.communicate()
        
        output_width = output_height = output_bitrate = output_codec = "N/A"
        
        try:
            if probe_process.returncode == 0:
                probe_data = json.loads(stdout.decode())
                stream_info = probe_data.get('streams', [{}])[0]
                
                output_width = stream_info.get('width', 'N/A')
                output_height = stream_info.get('height', 'N/A')
                output_bitrate = int(stream_info.get('bit_rate', 0)) / 1000  # Convert to kbps
                output_codec = stream_info.get('codec_name', 'N/A')
        except Exception as e:
            logging.error(f"Error getting output file info: {str(e)}")
        
        processing_time = time.time() - start_time
        
        await status_msg.edit_text(
            f"✅ FFmpeg Processing Complete!\n\n"
            f"📊 Results:\n"
            f"▫️ Original Size: {format_size(total_size)}\n"
            f"▫️ Final Size: {format_size(final_size)}\n"
            f"▫️ Compression Ratio: {compression_ratio:.2f}x\n"
            f"▫️ Original Resolution: {width}x{height}\n"
            f"▫️ Output Resolution: {output_width}x{output_height}\n"
            f"▫️ Output Codec: {output_codec}\n"
            f"▫️ Output Bitrate: {output_bitrate:.0f} kbps\n"
            f"▫️ Processing Time: {format_time(processing_time)}\n\n"
            f"<code>{ff_args}</code>"
        )
        
        return output_path
    except Exception as e:
        logging.error(f"FFmpeg processing error: {str(e)}", exc_info=True)
        await status_msg.edit_text(f"❌ Error: {str(e)}")
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
                await m.reply_text(f"FFmpeg command used:\n```\n{ff_args}\n```")

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