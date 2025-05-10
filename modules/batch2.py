import os
import asyncio
import logging
import signal
from pyrogram import filters, Client
from pyrogram.types import Message
from pyrogram.enums import ChatAction
from pyromod import listen  # for bot.listen()

# ——— Configuration ———
logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("bot_errors.log")]
)

DOWNLOAD_ROOT = "./downloads/batches"
MAX_CONCURRENT = 5          # Max simultaneous ffmpeg jobs
START_DELAY = 10            # Seconds between starting first 5 jobs

# ——— In‑memory State Stores ———
pending_files = {}   # chat_id → list of (file_id, original_filename)
batch_counters = {}  # chat_id → int
batch_args = {}      # chat_id → ffmpeg args (str)
batch_states = {}    # chat_id → "collecting"|"await_args"|"ready"|None
batch_tasks = {}     # chat_id → list of asyncio.Task
batch_procs = {}     # chat_id → list of subprocess.Process

# ——— Helpers ———
def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def split_long(text, chunk=4096):
    return [text[i : i + chunk] for i in range(0, len(text), chunk)]

async def send_long(bot, chat_id, text):
    for part in split_long(text):
        await bot.send_message(chat_id, part)

# ——— Core Processing Coroutine ———
async def process_batch(bot: Client, chat_id: int):
    files = pending_files[chat_id][:]
    args = batch_args[chat_id]
    batch_no = batch_counters[chat_id]

    sem = asyncio.Semaphore(MAX_CONCURRENT)
    delays = [i * START_DELAY for i in range(MAX_CONCURRENT)]
    tasks = []
    procs = []
    batch_procs[chat_id] = procs

    async def run_file(idx, file_id, orig_name, delay):
        await asyncio.sleep(delay)
        async with sem:
            # Download
            await bot.send_message(chat_id, f"⬇️ Downloading `{orig_name}`…")
            dest_dir = os.path.join(DOWNLOAD_ROOT, f"batch_{batch_no}")
            ensure_dir(dest_dir)
            local_in = await bot.download_media(file_id, file_name=os.path.join(dest_dir, orig_name))

            # Build output path preserving original filename
            base, _ = os.path.splitext(orig_name)
            out_path = os.path.join(dest_dir, f"{base}_batch{batch_no}.mkv")

            await bot.send_message(chat_id, f"⚙️ Running ffmpeg on `{orig_name}`…")
            cmd = f"ffmpeg -i '{local_in}' {args} '{out_path}'"
            proc = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            procs.append(proc)
            _, stderr = await proc.communicate()

            if proc.returncode != 0:
                err = stderr.decode(errors="ignore")
                logging.error(f"[Batch {batch_no}] `{orig_name}` error: {err}")
                await send_long(bot, chat_id, f"❌ `{orig_name}` failed:\n`{err}`")
            else:
                await bot.send_chat_action(chat_id, ChatAction.UPLOAD_DOCUMENT)
                await bot.send_document(chat_id, out_path, caption=f"✅ `{orig_name}` done.")

            # Cleanup
            for p in (local_in, out_path):
                try: os.remove(p)
                except: pass

    # Launch first up to MAX_CONCURRENT with staggered delays
    for i, (fid, fname) in enumerate(files[:MAX_CONCURRENT]):
        tasks.append(asyncio.create_task(run_file(i, fid, fname, delays[i])))

    # Rolling‑window scheduler for the rest
    async def schedule_rest():
        started = len(tasks)
        total = len(files)
        while started < total:
            # Wait until any slot frees
            await sem.acquire()
            sem.release()
            fid, fname = files[started]
            tasks.append(asyncio.create_task(run_file(started, fid, fname, 0)))
            started += 1

    scheduler = asyncio.create_task(schedule_rest())
    tasks.append(scheduler)
    batch_tasks[chat_id] = tasks

    # Await all tasks
    await asyncio.gather(*tasks, return_exceptions=True)
    await bot.send_message(chat_id, f"🎉 Batch #{batch_no} complete!")

    # Reset state
    batch_states[chat_id] = None
    pending_files[chat_id].clear()
    batch_args.pop(chat_id, None)
    batch_tasks.pop(chat_id, None)
    batch_procs.pop(chat_id, None)

# ——— Feature Registration ———
def batch_feature(bot: Client):
    @bot.on_message(filters.command("batch2") & filters.private)
    async def start_batch(_, m: Message):
        cid = m.chat.id
        batch_counters[cid] = batch_counters.get(cid, 0) + 1
        pending_files[cid] = []
        batch_states[cid] = "collecting"
        ensure_dir(os.path.join(DOWNLOAD_ROOT, f"batch_{batch_counters[cid]}"))
        await m.reply_text(
            f"📦 Started Batch #{batch_counters[cid]}.\n"
            "Send me all your videos/.mkv files. When done, send /end."
        )

    @bot.on_message(filters.command("end") & filters.private)
    async def end_collection(_, m: Message):
        cid = m.chat.id
        if batch_states.get(cid) != "collecting":
            return await m.reply_text("⚠️ No active batch. Use /batch first.")
        batch_states[cid] = "await_args"
        count = len(pending_files[cid])
        await m.reply_text(f"✅ Collected {count} files. Now send your ffmpeg args (or “help”).")

    @bot.on_message(filters.command("nuke") & filters.private)
    async def nuke_batch(_, m: Message):
        cid = m.chat.id
        # cancel asyncio tasks
        for t in batch_tasks.get(cid, []):
            t.cancel()
        # kill subprocesses
        for p in batch_procs.get(cid, []):
            try: p.send_signal(signal.SIGKILL)
            except: pass
        # reset
        batch_states[cid] = None
        pending_files[cid].clear()
        batch_args.pop(cid, None)
        batch_tasks.pop(cid, None)
        batch_procs.pop(cid, None)
        await m.reply_text("💥 All ongoing downloads & ffmpeg jobs have been nuked.")

    @bot.on_message(filters.command("s") & filters.private)
    async def start_processing(_, m: Message):
        cid = m.chat.id
        if batch_states.get(cid) != "ready":
            return await m.reply_text("⚠️ Finish with /end & send args before /s.")
        await m.reply_text("🚀 Launching batch processing…")
        asyncio.create_task(process_batch(bot, cid))

    @bot.on_message(filters.private & ~filters.command(["batch","end","s","nuke"]))
    async def catch_all(_, m: Message):
        cid = m.chat.id
        state = batch_states.get(cid)

        if state == "collecting":
            media = m.video or (
                m.document if m.document and m.document.file_name.lower().endswith(".mkv") else None
            )
            if not media:
                return await m.reply_text("❌ Please send a video or .mkv document.")
            fname = media.file_name or f"{media.file_unique_id}.mkv"
            pending_files[cid].append((media.file_id, fname))
            await m.reply_text(f"✔️ Collected `{fname}`")

        elif state == "await_args":
            txt = m.text.strip()
            if txt.lower() in ("help","?","examples"):
                await m.reply_text(
                    "Examples:\n"
                    "`-vf scale=1280:720 -c:v libx264 -crf 23`\n"
                    "`-q:v 2 -preset slow`\n"
                    "`-c:v copy -c:a copy`\n\nNow send your ffmpeg args:"
                )
                return
            batch_args[cid] = txt
            batch_states[cid] = "ready"
            await m.reply_text(
                f"📥 FFmpeg args set. {len(pending_files[cid])} files queued.\n"
                "Send /s to start processing."
            )

    return bot
