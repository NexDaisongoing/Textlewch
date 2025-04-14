import os
from pyrogram import filters
from pyrogram.types import Message

# Colab-friendly path for storing logs
LOG_FILE_PATH = "/content/logs.txt"

# Create a new log file if it doesn't exist
def create_log_file():
    if not os.path.exists(LOG_FILE_PATH):
        with open(LOG_FILE_PATH, "w") as log_file:
            log_file.write("Log file created.\n")
        return "New log file created."
    return "Log file already exists."

# Write log to logs.txt
def write_log(log_message):
    with open(LOG_FILE_PATH, "a") as log_file:
        log_file.write(log_message + "\n")

# Fetch recent 'n' lines from logs.txt
def fetch_recent_logs(n=500):
    if os.path.exists(LOG_FILE_PATH):
        with open(LOG_FILE_PATH, "r") as log_file:
            lines = log_file.readlines()
            recent_logs = lines[-n:]
        return "".join(recent_logs)
    return "Log file not found."

# Fetch all logs from logs.txt
def get_all_logs():
    if os.path.exists(LOG_FILE_PATH):
        with open(LOG_FILE_PATH, "r") as log_file:
            all_logs = log_file.read()
        return all_logs
    return "Log file not found."

# Register the /rlogs and /logs commands
def register_logs_commands(bot):
    """Handles the registration of /rlogs and /logs commands."""
    
    @bot.on_message(filters.command("rlogs"))
    async def recent_logs_command(client, message: Message):
        """Handles the /rlogs command for recent logs."""
        recent_logs = fetch_recent_logs(500)  # Fetch recent 500 lines
        await message.reply_text(f"📋 Recent Logs:\n{recent_logs}")

    @bot.on_message(filters.command("logs"))
    async def all_logs_command(client, message: Message):
        """Handles the /logs command for all logs."""
        all_logs = get_all_logs()  # Fetch all logs
        await message.reply_text(f"📋 All Logs:\n{all_logs}")
    
    write_log("Bot commands registered.")