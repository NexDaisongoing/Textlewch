import os
import time
import logging
import psutil
import platform
import datetime
import subprocess
from pyrogram import filters
from pyrogram.types import Message

LOGS = logging.getLogger("System_Info")

def get_gpu_info():
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, check=True
        )
        name, mem_total, mem_used = result.stdout.strip().split(', ')
        return name, float(mem_total), float(mem_used)
    except Exception as e:
        LOGS.warning(f"GPU info not available via nvidia-smi: {e}")
        return "GPU Not Available", 0.0, 0.0

def register_system_info_handler(bot):
    @bot.on_message(filters.command("sysinfo"))
    async def system_info(client, message: Message):
        LOGS.info(f"Received /systeminfo from {message.from_user.id if message.from_user else 'Unknown'}")
        try:
            # CPU Info
            cpu_name = platform.processor() or "Unknown CPU (Colab?)"
            physical_cores = psutil.cpu_count(logical=False)
            logical_cores = psutil.cpu_count(logical=True)
            cpu_freq = psutil.cpu_freq()
            cpu_usage = psutil.cpu_percent(interval=1)

            # RAM Info
            virtual_memory = psutil.virtual_memory()
            total_ram = virtual_memory.total / (1024 ** 3)
            available_ram = virtual_memory.available / (1024 ** 3)
            used_ram = virtual_memory.used / (1024 ** 3)
            ram_usage = virtual_memory.percent

            # Disk Info
            partitions = psutil.disk_partitions()
            disk_info = ""
            for partition in partitions:
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    disk_info += (
                        f"\n🔹 **{partition.device}**: {usage.percent}% used "
                        f"({usage.used / (1024 ** 3):.2f} GB / {usage.total / (1024 ** 3):.2f} GB)"
                    )
                except PermissionError:
                    continue

            # GPU Info
            gpu_name, gpu_memory, gpu_usage = get_gpu_info()

            # Uptime
            boot_time = psutil.boot_time()
            uptime_seconds = time.time() - boot_time
            uptime = str(datetime.timedelta(seconds=int(uptime_seconds)))

            # Build the reply
            reply = (
                "🖥 **System Information (Colab)**\n"
                f"🔹 **Processor**: {cpu_name}\n"
                f"🔹 **Physical Cores**: {physical_cores}\n"
                f"🔹 **Logical Cores**: {logical_cores}\n"
                f"🔹 **Max Frequency**: {cpu_freq.max:.2f} MHz\n"
                f"🔹 **Current Frequency**: {cpu_freq.current:.2f} MHz\n"
                f"🔹 **CPU Usage**: {cpu_usage}%\n\n"
                f"🔹 **Total RAM**: {total_ram:.2f} GB\n"
                f"🔹 **Used RAM**: {used_ram:.2f} GB\n"
                f"🔹 **Available RAM**: {available_ram:.2f} GB\n"
                f"🔹 **RAM Usage**: {ram_usage}%\n\n"
                f"🔹 **Disk Info**: {disk_info}\n\n"
                f"🔹 **GPU**: {gpu_name}\n"
                f"🔹 **GPU Memory**: {gpu_memory:.2f} MB\n"
                f"🔹 **GPU Usage**: {gpu_usage:.2f} MB\n\n"
                f"🔹 **System Uptime**: {uptime}"
            )

            await message.reply_text(reply)
        except Exception as e:
            LOGS.error(f"Error in /systeminfo: {e}")
            await message.reply_text("❌ Failed to fetch system info. Possibly due to Colab limitations.")
