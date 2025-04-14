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

def progress_bar(current, total, message, start_time):
    """
    Display a progress bar for uploads/downloads in Telegram
    
    Args:
        current (int): Current progress
        total (int): Total size
        message (Message): Message object to edit
        start_time (float): Time when the operation started
    """
    if total == 0:
        return
    
    now = time.time()
    elapsed_time = now - start_time
    
    if elapsed_time == 0:
        return
    
    speed = current / elapsed_time
    percent = current * 100 / total
    eta = round((total - current) / speed) if speed > 0 else 0
    
    # Format time
    def format_time(seconds):
        hours = seconds // 3600
        seconds %= 3600
        minutes = seconds // 60
        seconds %= 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    # Format size
    def sizeof_fmt(num, suffix='B'):
        for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
            if abs(num) < 1024.0:
                return f"{num:.2f}{unit}{suffix}"
            num /= 1024.0
        return f"{num:.2f}Yi{suffix}"
    
    # Create progress bar
    progress_length = 20
    completed_length = int(round(progress_length * current / float(total)))
    remaining_length = progress_length - completed_length
    progress_bar = '█' * completed_length + '░' * remaining_length
    
    # Create status text
    status = (
        f"**Progress**: {current}/{total} ({percent:.2f}%)\n"
        f"**Speed**: {sizeof_fmt(speed)}/s\n"
        f"**ETA**: {format_time(eta)}\n"
        f"**Elapsed**: {format_time(int(elapsed_time))}\n"
        f"[{progress_bar}]"
    )
    
    # Edit message with new status
    try:
        message.edit(status)
    except Exception as e:
        print(f"Error updating progress: {e}")

