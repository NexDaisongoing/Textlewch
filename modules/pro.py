import os import asyncio from pyrogram import Client, filters from pyrogram.types import Message from pyromod import listen  # Enables await bot.listen(chat_id) for step-by-step flows

Directory where incoming and processed files are stored

download_dir = "./downloads/pro"

Ensure that the download directory exists

def ensure_dir(path): if not os.path.isdir(path): os.makedirs(path, exist_ok=True)

@Client.on_message(filters.command("pro") & filters.private) async def pro_handler(bot: Client, m: Message): """ Multi-step handler for /pro: 1. Ask for a video or .mkv file 2. Download it 3. Ask for ffmpeg arguments (with a help option) 4. Run ffmpeg 5. Upload the result 6. Cleanup """ # Step 1: Request file await m.reply_text("📥 Please send me a video file or an .mkv document.") file_msg: Message = await bot.listen(m.chat.id)

# Validate file type
if file_msg.video:
    media = file_msg.video
    ext = os.path.splitext(media.file_name or media.file_id)[1] or ".mp4"
elif file_msg.document and file_msg.document.file_name.lower().endswith(".mkv"):
    media = file_msg.document
    ext = ".mkv"
else:
    return await m.reply_text(
        "❌ Invalid file. Please send a supported video (any) or an .mkv file. Try `/pro` again when ready."
    )

# Step 2: Download incoming file
ensure_dir(download_dir)
local_in = await file_msg.download(
    file_name=os.path.join(download_dir, f"input_{m.message_id}{ext}")
)
await m.reply_text(f"✅ Downloaded: `{os.path.basename(local_in)}`")

# Step 3: Ask for ffmpeg arguments
help_text = (
    "Send your **ffmpeg** arguments.\n"
    "For example: `-vf scale=1280:720 -c:v libx264 -crf 23`\n"
    "Type `help` to see more examples."
)
await m.reply_text(help_text)
cmd_msg: Message = await bot.listen(m.chat.id)
ff_args = cmd_msg.text.strip()

# Offer examples if user asks
if ff_args.lower() in ("help", "?", "examples"):
    examples = (
        "`-vf scale=1280:720 -c:v libx264 -crf 23`\n"
        "`-q:v 2 -preset slow`\n"
        "`-c:v copy -c:a copy` (stream copy/no re-encode)"
    )
    await m.reply_text(f"Here are some example ffmpeg args:\n{examples}\n\nNow please send your ffmpeg arguments:")
    cmd_msg = await bot.listen(m.chat.id)
    ff_args = cmd_msg.text.strip()

# Step 4: Run ffmpeg
base, _ = os.path.splitext(local_in)
local_out = f"{base}_pro.mkv"
cmd = f"ffmpeg -i '{local_in}' {ff_args} '{local_out}'"
await m.reply_text(f"⚙️ Processing: `{cmd}`")
proc = await asyncio.create_subprocess_shell(
    cmd,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
stdout, stderr = await proc.communicate()

if proc.returncode != 0:
    err_msg = stderr.decode(errors="ignore").strip().splitlines()[-1]
    return await m.reply_text(f"❌ Processing failed:\n`{err_msg}`")

# Step 5: Upload processed file
await m.reply_chat_action("upload_document")
await m.reply_document(local_out, caption="✅ Here is your processed file.")

# Step 6: Cleanup temporary files
for path in (local_in, local_out):
    try:
        os.remove(path)
    except OSError:
        pass

