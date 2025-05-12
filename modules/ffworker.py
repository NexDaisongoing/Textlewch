import os
import re
import json
import time
import shlex
import logging
import asyncio
import psutil
from typing import Tuple, Dict, Any, Optional

from utils import format_size, format_time, get_progress_bar

DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "./downloads")

async def process_with_ffmpeg(bot, m, input_path, status_msg):
    try:
        if not isinstance(input_path, str):
            return await status_msg.edit_text("❌ Invalid input path: Must be a string")
        if not os.path.isfile(input_path):
            return await status_msg.edit_text(f"❌ Input file does not exist: {input_path}")
        try:
            with open(input_path, 'rb') as f:
                f.read(1024)
        except Exception as e:
            return await status_msg.edit_text(f"❌ Cannot read input file: {str(e)}")

        probe_cmd = [
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,r_frame_rate,avg_frame_rate,duration,bit_rate,nb_frames,codec_name:format=duration,bit_rate,size',
            '-of', 'json', input_path
        ]
        proc_probe = await asyncio.create_subprocess_exec(*probe_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await proc_probe.communicate()
        if proc_probe.returncode != 0:
            return await status_msg.edit_text(f"❌ Error getting video info:\n{err.decode().strip()}")

        data = json.loads(out.decode())
        stream = data.get("streams", [{}])[0]
        fmt = data.get("format", {})
        total_duration = float(stream.get("duration") or fmt.get("duration") or 0)
        fr = stream.get("r_frame_rate", "25/1")
        frame_rate = eval(fr) if '/' in fr else float(fr)
        total_size = os.path.getsize(input_path)
        input_codec = stream.get("codec_name", "unknown")

        await status_msg.edit_text(
            "📂 Input File Info:\n"
            f"▫️ Size: {format_size(total_size)}\n"
            f"▫️ Duration: {format_time(total_duration)}\n"
            f"▫️ Resolution: {stream.get('width', 'N/A')}x{stream.get('height', 'N/A')}\n"
            f"▫️ Codec: {input_codec}\n\n"
            "⚙️ Send your FFmpeg command:"
        )

        cmd_msg = await bot.listen(m.chat.id)
        ffmpeg_cmd = cmd_msg.text.strip()

        base_name = os.path.splitext(os.path.basename(input_path))[0]
        output_path = os.path.join(DOWNLOAD_DIR, f"{base_name}_processed.mkv")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        full_cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'info', '-stats', '-y', '-i', input_path] + shlex.split(ffmpeg_cmd) + [output_path]
        logging.info(f"Running FFmpeg command: {' '.join(full_cmd)}")

        try:
            proc = await asyncio.create_subprocess_exec(
                *full_cmd, 
                stdout=asyncio.subprocess.PIPE, 
                stderr=asyncio.subprocess.PIPE
            )
        except Exception as e:
            return await status_msg.edit_text(f"❌ Failed to start FFmpeg: {str(e)}")

        progress_data = {
            'frame': 0, 'fps': 0.0, 'time': 0.0, 'bitrate': 0.0, 
            'speed': 0.0, 'size_kb': 0, 'q': 0.0, 'dup': 0, 'drop': 0
        }
        start_time = time.time()
        ffmpeg_running = asyncio.Event()
        ffmpeg_running.set()

        async def read_ffmpeg_log():
            patterns = {
                'frame':   r"frame=\s*(\d+)",
                'fps':     r"fps=\s*([\d\.]+)",
                'time':    r"time=(\d+):(\d+):(\d+\.\d+)",
                'time_alt': r"time=(\d+\.\d+)",
                'bitrate': r"bitrate=\s*([\d\.]+)\s*k?b/s",
                'speed':   r"speed=\s*([\d\.]+)x",
                'size_kb': r"size=\s*(\d+)\s*k?b?",
                'q':       r"q=\s*([\d\.]+)",
                'dup':     r"dup=\s*(\d+)",
                'drop':    r"drop=\s*(\d+)"
            }

            while True:
                line = await proc.stderr.readline()
                if not line:
                    ffmpeg_running.clear()
                    break

                text_line = line.decode(errors="ignore").strip()

                time_match = re.search(patterns['time'], text_line)
                if time_match:
                    h, m, s = map(float, time_match.groups())
                    progress_data["time"] = h * 3600 + m * 60 + s
                else:
                    time_alt_match = re.search(patterns['time_alt'], text_line)
                    if time_alt_match:
                        progress_data["time"] = float(time_alt_match.group(1))

                for key in ['frame', 'fps', 'bitrate', 'speed', 'size_kb', 'q', 'dup', 'drop']:
                    match = re.search(patterns[key], text_line)
                    if match:
                        try:
                            val = float(match.group(1)) if '.' in match.group(1) else int(match.group(1))
                            progress_data[key] = val
                        except:
                            pass

        async def update_message_loop():
            last_update_time = 0
            while ffmpeg_running.is_set() or not proc.returncode:
                now = time.time()
                if now - last_update_time < 2:
                    await asyncio.sleep(0.5)
                    continue

                last_update_time = now
                percent = (progress_data['time'] / total_duration) * 100 if total_duration > 0 else 0
                speed = progress_data['speed'] if progress_data['speed'] > 0 else 0.1
                eta = (total_duration - progress_data['time']) / speed if total_duration > progress_data['time'] else 0

                output_size = max(progress_data['size_kb'] * 1024, 1)
                compression_ratio = total_size / output_size if output_size else 1
                estimated_final_size = output_size * (total_duration / progress_data['time']) if progress_data['time'] > 0 else 0

                cpu = psutil.cpu_percent()
                ram = psutil.virtual_memory()

                stats_text = (
                    "🔄 Encoding Progress:\n\n"
                    f"{get_progress_bar(percent)} {percent:.1f}%\n"
                    f" Duration: {format_time(progress_data['time'])} / {format_time(total_duration)}\n"
                    f" Frames: {progress_data['frame']} @ {progress_data['fps']:.1f} FPS\n"
                    f" Quality: q={progress_data['q']:.1f}\n"
                    f" Size: {format_size(progress_data['size_kb'] * 1024)} (Est. Final: {format_size(estimated_final_size)})\n"
                    f" Bitrate: {progress_data['bitrate']:.1f}kbps | Speed: {progress_data['speed']:.1f}x\n"
                    f" ETA: {format_time(eta)}\n"
                    f" CPU: {cpu}% | RAM: {format_size(ram.used)}/{format_size(ram.total)}\n"
                    f"\n<code>{ffmpeg_cmd}</code>"
                )
                try:
                    await status_msg.edit_text(stats_text)
                except Exception as e:
                    logging.error(f"Failed to update status message: {e}")

                if proc.returncode is not None and not ffmpeg_running.is_set():
                    break

                await asyncio.sleep(0.5)

        async def monitor_ffmpeg():
            while proc.returncode is None:
                if proc.returncode is not None:
                    ffmpeg_running.clear()
                    break
                await asyncio.sleep(1)

        await asyncio.gather(
            read_ffmpeg_log(),
            update_message_loop(),
            monitor_ffmpeg()
        )

        return_code = await proc.wait()
        if return_code != 0 or not os.path.exists(output_path):
            return await status_msg.edit_text(
                f"❌ FFmpeg process failed with return code {return_code}\n\n"
                f"Last command: <code>{ffmpeg_cmd}</code>"
            )

        final_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
        processing_time = time.time() - start_time
        compression_ratio = total_size / max(final_size, 1)

        await status_msg.edit_text(
            f"✅ Done!\n\n"
            f"▫️ Original: {format_size(total_size)}\n"
            f"▫️ Final:    {format_size(final_size)}\n"
            f"▫️ Ratio:    {compression_ratio:.2f}x\n"
            f"▫️ Time:     {format_time(processing_time)}"
        )
        return output_path

    except Exception as e:
        logging.error(f"FFmpeg processing failed: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Error occurred:\n{e}")
        return None