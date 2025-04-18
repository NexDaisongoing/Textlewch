import os
import subprocess
from pyrogram import filters
from pyrogram.types import Message

# Colab-safe path for storing FFmpeg logs
FFMPEG_LOG_FILE_PATH = "/content/ffmpeg_logs.txt"

def create_ffmpeg_log_file(b):
    """Create the FFmpeg log file if it doesn't exist."""
    if not os.path.exists(FFMPEG_LOG_FILE_PATH):
        with open(FFMPEG_LOG_FILE_PATH, "w") as log_file:
            log_file.write("FFmpeg Logs - New Log File Created\n")
        return "New FFmpeg log file created."
    return "FFmpeg log file already exists."

def write_ffmpeg_log(log_message):
    """Write the FFmpeg log message to the log file."""
    with open(FFMPEG_LOG_FILE_PATH, "a") as log_file:
        log_file.write(log_message + "\n")

def find_ffmpeg_path():
    """Find the path to FFmpeg executable on the system and capture logs."""
    try:
        result = subprocess.run(['which', 'ffmpeg'],
                                capture_output=True,
                                text=True,
                                check=False)
        ffmpeg_path = result.stdout.strip().split('\n')[0] if result.returncode == 0 else None
        if ffmpeg_path:
            return ffmpeg_path, None
        else:
            return None, "FFmpeg not found in system paths."
    except Exception as e:
        return None, f"Error while searching for FFmpeg: {e}"

def run_ffmpeg_with_log(command):
    """Run FFmpeg command and capture both stdout and stderr logs."""
    try:
        # Run FFmpeg command and capture both stdout and stderr
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        stdout_log = result.stdout
        stderr_log = result.stderr

        # Store logs into the ffmpeg_logs.txt file
        write_ffmpeg_log(stdout_log)
        write_ffmpeg_log(stderr_log)

        return stdout_log, stderr_log
    except Exception as e:
        write_ffmpeg_log(f"Error running FFmpeg: {str(e)}")
        return None, f"Error running FFmpeg: {str(e)}"

# Register the /flogs command for FFmpeg log capture
def register_ffmpeg_logs_command(bot):
    @bot.on_message(filters.command("flogs"))
    async def handle_ffmpeg_command(client, message: Message):
        """Handles the /flogs command for FFmpeg logs."""
        ffmpeg_path, error_message = find_ffmpeg_path()

        if not ffmpeg_path:
            await message.reply_text(f"❌ {error_message}")
            return

        # Example command to run with FFmpeg (this can be changed as needed)
        ffmpeg_command = [ffmpeg_path, "-version"]

        # Run FFmpeg and capture its logs
        stdout_log, stderr_log = run_ffmpeg_with_log(ffmpeg_command)

        if stdout_log:
            response = f"✅ FFmpeg Logs:\n\n{stdout_log}\n\nError Logs (if any):\n{stderr_log}"
        else:
            response = f"❌ Error running FFmpeg:\n{stderr_log}"

        await message.reply_text(response)
        write_ffmpeg_log("FFmpeg command executed.")