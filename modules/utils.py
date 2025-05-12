import time
import math
import os
from pyrogram.errors import FloodWait

class Timer:
    def __init__(self, time_between=5):
        self.start_time = time.time()
        self.time_between = time_between

    def can_send(self):
        if time.time() > (self.start_time + self.time_between):
            self.start_time = time.time()
            return True
        return False


from datetime import datetime,timedelta

#lets do calculations
def hrb(value, digits= 2, delim= "", postfix=""):
    """Return a human-readable file size.
    """
    if value is None:
        return None
    chosen_unit = "B"
    for unit in ("KiB", "MiB", "GiB", "TiB"):
        if value > 1000:
            value /= 1024
            chosen_unit = unit
        else:
            break
    return f"{value:.{digits}f}" + delim + chosen_unit + postfix

def hrt(seconds, precision = 0):
    """Return a human-readable time delta as a string.
    """
    pieces = []
    value = timedelta(seconds=seconds)
    

    if value.days:
        pieces.append(f"{value.days}d")

    seconds = value.seconds

    if seconds >= 3600:
        hours = int(seconds / 3600)
        pieces.append(f"{hours}h")
        seconds -= hours * 3600

    if seconds >= 60:
        minutes = int(seconds / 60)
        pieces.append(f"{minutes}m")
        seconds -= minutes * 60

    if seconds > 0 or not pieces:
        pieces.append(f"{seconds}s")

    if not precision:
        return "".join(pieces)

    return "".join(pieces[:precision])



timer = Timer()

# Powered By Ankush
async def progress_bar(current, total, reply, start):
    if timer.can_send():
        now = time.time()
        diff = now - start
        if diff < 1:
            return
        else:
            perc = f"{current * 100 / total:.1f}%"
            elapsed_time = round(diff)
            speed = current / elapsed_time
            remaining_bytes = total - current
            if speed > 0:
                eta_seconds = remaining_bytes / speed
                eta = hrt(eta_seconds, precision=1)
            else:
                eta = "-"
            sp = str(hrb(speed)) + "/s"
            tot = hrb(total)
            cur = hrb(current)
            bar_length = 11
            completed_length = int(current * bar_length / total)
            remaining_length = bar_length - completed_length
            progress_bar = "◆" * completed_length + "◇" * remaining_length
            
            try:
                await reply.edit(f'\n `╭─⌯══⟰ 𝐔𝐩𝐥𝐨𝐝𝐢𝐧𝐠 ⟰══⌯──★ \n├⚡ {progress_bar}|﹝{perc}﹞ \n├🚀 Speed » {sp} \n├📟 Processed » {cur}\n├🧲 Size - ETA » {tot} - {eta} \n`├𝐁𝐲 » 𝐖𝐃 𝐙𝐎𝐍𝐄\n╰─══ ✪ @Opleech_WD ✪ ══─★\n') 
            except FloodWait as e:
                time.sleep(e.x)

"""
Utility functions for formatting and display in the FFmpeg processor.
"""

def format_size(size_bytes: int) -> str:
    """
    Format a size in bytes to a human-readable string.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Formatted string (e.g., "15.2 MB")
    """
    if size_bytes < 0:
        return "0 B"
        
    # Define units and thresholds
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(size_bytes)
    unit_index = 0
    
    # Scale to appropriate unit
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
        
    # Format with appropriate precision
    if size < 10:
        return f"{size:.2f} {units[unit_index]}"
    elif size < 100:
        return f"{size:.1f} {units[unit_index]}"
    else:
        return f"{int(size)} {units[unit_index]}"

def format_time(seconds: float) -> str:
    """
    Format seconds to HH:MM:SS format.
    
    Args:
        seconds: Time duration in seconds
        
    Returns:
        Formatted time string
    """
    if seconds is None or seconds < 0:
        return "00:00:00"
        
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def get_progress_bar(percent: float, width: int = 20) -> str:
    """
    Generate an ASCII progress bar.
    
    Args:
        percent: Progress percentage (0-100)
        width: Width of the progress bar in characters
        
    Returns:
        Progress bar string
    """
    percent = max(0, min(100, percent))  # Clamp to 0-100
    filled_len = int(width * percent / 100)
    
    # Create the bar with appropriate characters
    bar = '█' * filled_len + '░' * (width - filled_len)
    
    return f"[{bar}]"

