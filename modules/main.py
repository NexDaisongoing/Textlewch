import os
import re
import sys
import json
import time
import asyncio
import requests
import subprocess

import core as helper
from utils import progress_bar
from vars import API_ID, API_HASH, BOT_TOKEN, WEBHOOK, PORT
from aiohttp import ClientSession
from pyromod import listen
from subprocess import getstatusoutput
from aiohttp import web

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from pyrogram.errors.exceptions.bad_request_400 import StickerEmojiInvalid
from pyrogram.types.messages_and_media import message
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from style import Ashu 

from core import handle_direct_link, process_with_ffmpeg, send_vid, is_direct_media_url, download_video

# Initialize the bot
bot = Client(
    "bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Define a filter for direct video links
direct_video_pattern = re.compile(r'https?://.*\.(mp4|mkv|avi|mov|webm|flv|3gp|wmv|m4v)(\?.*)?$', re.IGNORECASE)

# Define aiohttp routes
routes = web.RouteTableDef()

@routes.get("/", allow_head=True)
async def root_route_handler(request):
    return web.json_response("https://github.com/AshutoshGoswami24")

async def web_server():
    web_app = web.Application(client_max_size=30000000)
    web_app.add_routes(routes)
    return web_app

@bot.on_message(filters.command(["start"]))
async def account_login(bot: Client, m: Message):
    await m.reply_text(
       Ashu.START_TEXT, reply_markup=InlineKeyboardMarkup(
            [
                    [
                    InlineKeyboardButton("✜ ᴀsʜᴜᴛᴏsʜ ɢᴏsᴡᴀᴍɪ 𝟸𝟺 ✜" ,url="https://t.me/AshutoshGoswami24") ],
                    [
                    InlineKeyboardButton("🦋 𝐅𝐨𝐥𝐥𝐨𝐰 𝐌𝐞 🦋" ,url="https://t.me/AshuSupport") ]                               
            ]))
@bot.on_message(filters.command("stop"))
async def restart_handler(_, m):
    await m.reply_text("♦ 𝐒𝐭𝐨𝐩𝐩𝐞𝐭 ♦", True)
    os.execl(sys.executable, sys.executable, *sys.argv)



@bot.on_message(filters.command(["upload"]))
async def account_login(bot: Client, m: Message):
    editable = await m.reply_text('sᴇɴᴅ ᴍᴇ .ᴛxᴛ ғɪʟᴇ  ⏍')
    input: Message = await bot.listen(editable.chat.id)
    x = await input.download()
    await input.delete(True)

    path = f"./downloads/{m.chat.id}"

    try:
       with open(x, "r") as f:
           content = f.read()
       content = content.split("\n")
       links = []
       for i in content:
           links.append(i.split("://", 1))
       os.remove(x)
            # print(len(links)
    except:
           await m.reply_text("∝ 𝐈𝐧𝐯𝐚𝐥𝐢𝐝 𝐟𝐢𝐥𝐞 𝐢𝐧𝐩𝐮𝐭.")
           os.remove(x)
           return
    
   
    await editable.edit(f"ɪɴ ᴛxᴛ ғɪʟᴇ ᴛɪᴛʟᴇ ʟɪɴᴋ 🔗** **{len(links)}**\n\nsᴇɴᴅ ғʀᴏᴍ  ᴡʜᴇʀᴇ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴅᴏᴡɴʟᴏᴀᴅ ɪɴɪᴛᴀʟ ɪs `1`")
    input0: Message = await bot.listen(editable.chat.id)
    raw_text = input0.text
    await input0.delete(True)

    await editable.edit("∝ 𝐍𝐨𝐰 𝐏𝐥𝐞𝐚𝐬𝐞 𝐒𝐞𝐧𝐝 𝐌𝐞 𝐘𝐨𝐮𝐫 𝐁𝐚𝐭𝐜𝐡 𝐍𝐚𝐦𝐞")
    input1: Message = await bot.listen(editable.chat.id)
    raw_text0 = input1.text
    await input1.delete(True)
    

    await editable.edit(Ashu.Q1_TEXT)
    input2: Message = await bot.listen(editable.chat.id)
    raw_text2 = input2.text
    await input2.delete(True)
    try:
        if raw_text2 == "144":
            res = "256x144"
        elif raw_text2 == "240":
            res = "426x240"
        elif raw_text2 == "360":
            res = "640x360"
        elif raw_text2 == "480":
            res = "854x480"
        elif raw_text2 == "720":
            res = "1280x720"
        elif raw_text2 == "1080":
            res = "1920x1080" 
        else: 
            res = "UN"
    except Exception:
            res = "UN"
    
    # Add FFmpeg command prompt
    await editable.edit(Ashu.FFMPEG_TEXT)
    input_ffmpeg: Message = await bot.listen(editable.chat.id)
    custom_ffmpeg = input_ffmpeg.text
    await input_ffmpeg.delete(True)

    await editable.edit(Ashu.C1_TEXT)
    input3: Message = await bot.listen(editable.chat.id)
    raw_text3 = input3.text
    await input3.delete(True)
    highlighter  = f"️ ⁪⁬⁮⁮⁮"
    if raw_text3 == 'Robin':
        MR = highlighter 
    else:
        MR = raw_text3
   
    await editable.edit(Ashu.T1_TEXT)
    input6 = message = await bot.listen(editable.chat.id)
    raw_text6 = input6.text
    await input6.delete(True)
    await editable.delete()

    thumb = input6.text
    if thumb.startswith("http://") or thumb.startswith("https://"):
        getstatusoutput(f"wget '{thumb}' -O 'thumb.jpg'")
        thumb = "thumb.jpg"
    else:
        thumb == "no"

    if len(links) == 1:
        count = 1
    else:
        count = int(raw_text)

    try:
        for i in range(count - 1, len(links)):

            V = links[i][1].replace("file/d/","uc?export=download&id=").replace("www.youtube-nocookie.com/embed", "youtu.be").replace("?modestbranding=1", "").replace("/view?usp=sharing","") # .replace("mpd","m3u8")
            url = "https://" + V

            if "visionias" in url:
                async with ClientSession() as session:
                    async with session.get(url, headers={'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9', 'Accept-Language': 'en-US,en;q=0.9', 'Cache-Control': 'no-cache', 'Connection': 'keep-alive', 'Pragma': 'no-cache', 'Referer': 'http://www.visionias.in/', 'Sec-Fetch-Dest': 'iframe', 'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Site': 'cross-site', 'Upgrade-Insecure-Requests': '1', 'User-Agent': 'Mozilla/5.0 (Linux; Android 12; RMX2121) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Mobile Safari/537.36', 'sec-ch-ua': '"Chromium";v="107", "Not=A?Brand";v="24"', 'sec-ch-ua-mobile': '?1', 'sec-ch-ua-platform': '"Android"',}) as resp:
                        text = await resp.text()
                        url = re.search(r"(https://.*?playlist.m3u8.*?)\"", text).group(1)

            elif 'videos.classplusapp' in url:
             url = requests.get(f'https://api.classplusapp.com/cams/uploader/video/jw-signed-url?url={url}', headers={'x-access-token': 'eyJhbGciOiJIUzM4NCIsInR5cCI6IkpXVCJ9.eyJpZCI6MzgzNjkyMTIsIm9yZ0lkIjoyNjA1LCJ0eXBlIjoxLCJtb2JpbGUiOiI5MTcwODI3NzQyODkiLCJuYW1lIjoiQWNlIiwiZW1haWwiOm51bGwsImlzRmlyc3RMb2dpbiI6dHJ1ZSwiZGVmYXVsdExhbmd1YWdlIjpudWxsLCJjb3VudHJ5Q29kZSI6IklOIiwiaXNJbnRlcm5hdGlvbmFsIjowLCJpYXQiOjE2NDMyODE4NzcsImV4cCI6MTY0Mzg4NjY3N30.hM33P2ai6ivdzxPPfm01LAd4JWv-vnrSxGXqvCirCSpUfhhofpeqyeHPxtstXwe0'}).json()['url']

            elif '/master.mpd' in url:
             id =  url.split("/")[-2]
             url =  "https://d26g5bnklkwsh4.cloudfront.net/" + id + "/master.m3u8"

            name1 = links[i][0].replace("\t", "").replace(":", "").replace("/", "").replace("+", "").replace("#", "").replace("|", "").replace("@", "").replace("*", "").replace(".", "").replace("https", "").replace("http", "").strip()
            name = f'{str(count).zfill(3)}) {name1[:60]}'

            if "youtu" in url:
                ytf = f"b[height<={raw_text2}][ext=mp4]/bv[height<={raw_text2}][ext=mp4]+ba[ext=m4a]/b[ext=mp4]"
            else:
                ytf = f"b[height<={raw_text2}]/bv[height<={raw_text2}]+ba/b/bv+ba"

            if "jw-prod" in url:
                cmd = f'yt-dlp -o "{name}.mp4" "{url}"'
            else:
                cmd = f'yt-dlp -f "{ytf}" "{url}" -o "{name}.mp4"'

            try:  
                
                cc = f'**[ 🎥 ] Vid_ID:** {str(count).zfill(3)}.** {name1}{MR}.mkv\n✉️ 𝐁𝐚𝐭𝐜𝐡 » **{raw_text0}**'
                cc1 = f'**[ 📁 ] Pdf_ID:** {str(count).zfill(3)}. {name1}{MR}.pdf \n✉️ 𝐁𝐚𝐭𝐜𝐡 » **{raw_text0}**'
                if "drive" in url:
                    try:
                        ka = await helper.download(url, name)
                        copy = await bot.send_document(chat_id=m.chat.id,document=ka, caption=cc1)
                        count+=1
                        os.remove(ka)
                        time.sleep(1)
                    except FloodWait as e:
                        await m.reply_text(str(e))
                        time.sleep(e.x)
                        continue
                
                elif ".pdf" in url:
                    try:
                        cmd = f'yt-dlp -o "{name}.pdf" "{url}"'
                        download_cmd = f"{cmd} -R 25 --fragment-retries 25"
                        os.system(download_cmd)
                        copy = await bot.send_document(chat_id=m.chat.id, document=f'{name}.pdf', caption=cc1)
                        count += 1
                        os.remove(f'{name}.pdf')
                    except FloodWait as e:
                        await m.reply_text(str(e))
                        time.sleep(e.x)
                        continue
                else:
                    Show = f"❊⟱ 𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐢𝐧𝐠 ⟱❊ »\n\n📝 𝐍𝐚𝐦𝐞 » `{name}\n⌨ 𝐐𝐮𝐥𝐢𝐭𝐲 » {raw_text2}`\n\n**🔗 𝐔𝐑𝐋 »** `{url}`"
                    prog = await m.reply_text(Show)
                    res_file = await helper.download_video(url, cmd, name)
                    filename = res_file
                    await prog.delete(True)
                    # Pass the custom_ffmpeg parameter to send_vid
                    await helper.send_vid(bot, m, cc, filename, thumb, name, prog, custom_ffmpeg)
                    count += 1
                    time.sleep(1)

            except Exception as e:
                await m.reply_text(
                    f"⌘ 𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐢𝐧𝐠 𝐈𝐧𝐭𝐞𝐫𝐮𝐩𝐭𝐞𝐝\n{str(e)}\n⌘ 𝐍𝐚𝐦𝐞 » {name}\n⌘ 𝐋𝐢𝐧𝐤 » `{url}`"
                )
                continue

    except Exception as e:
        await m.reply_text(e)
    await m.reply_text("✅ 𝐒𝐮𝐜𝐜𝐞𝐬𝐬𝐟𝐮𝐥𝐥𝐲 𝐃𝐨𝐧𝐞")

# Command handler for direct media links
@Client.on_message(filters.command("direct") & filters.text)
async def direct_link_command(client, message: Message):
    """Download and process a direct media link"""
    # Check if the message contains a URL
    url = None
    if len(message.command) > 1:
        url = message.command[1]
    elif message.reply_to_message and message.reply_to_message.text:
        # Try to extract URL from the replied message
        urls = re.findall(r'(https?://[^\s]+)', message.reply_to_message.text)
        if urls:
            url = urls[0]
    
    if not url:
        await message.reply_text("❌ Please provide a direct media URL or reply to a message containing a URL.")
        return
    
    # Extract FFmpeg parameters if provided
    custom_ffmpeg = None
    ffmpeg_match = re.search(r'ffmpeg:(.+?)(?:\s|$)', message.text)
    if ffmpeg_match:
        custom_ffmpeg = ffmpeg_match.group(1).strip()
    
    # Extract custom filename if provided
    custom_filename = None
    filename_match = re.search(r'filename:(.+?)(?:\s|$)', message.text)
    if filename_match:
        custom_filename = filename_match.group(1).strip()
    
    # Handle the direct link
    await handle_direct_link(message, url, custom_filename, custom_ffmpeg)


# Auto-detect direct media links in messages
@Client.on_message(filters.regex(direct_video_pattern) & ~filters.command)
async def auto_direct_link_handler(client, message: Message):
    """Automatic handling of direct media links in messages"""
    urls = re.findall(r'(https?://[^\s]+\.(mp4|mkv|avi|mov|webm|flv|3gp|wmv|m4v)(\?.*)?)', message.text, re.IGNORECASE)
    
    if not urls:
        return
    
    # Extract the first URL found
    url = urls[0][0]
    
    # Ask user if they want to download the media
    confirm_msg = await message.reply_text(
        f"📽️ Direct media link detected: `{url}`\n\n"
        f"**Would you like to:**\n"
        f"- `!download` - Download and upload to Telegram\n"
        f"- `!process` - Download, process with FFmpeg, and upload\n"
        f"- `!cancel` - Ignore this link"
    )
    
    # Wait for user response
    @Client.on_message(filters.reply & filters.text & filters.user(message.from_user.id), group=123)
    async def wait_for_response(client, response):
        if response.reply_to_message.id != confirm_msg.id:
            return
        
        # Remove the handler
        client.remove_handler(wait_for_response, group=123)
        
        command = response.text.lower().strip()
        
        if command == "!download":
            await handle_direct_link(message, url)
        elif command == "!process":
            # Ask for FFmpeg parameters
            ffmpeg_msg = await message.reply_text(
                "Please provide FFmpeg parameters.\n\n"
                "Example: `-c:v libx264 -preset medium -crf 23 -c:a aac -b:a 128k`\n\n"
                "Or type `!default` for standard processing, or `!cancel` to cancel."
            )
            
            @Client.on_message(filters.reply & filters.text & filters.user(message.from_user.id), group=124)
            async def wait_for_ffmpeg(client, ffmpeg_response):
                if ffmpeg_response.reply_to_message.id != ffmpeg_msg.id:
                    return
                
                # Remove the handler
                client.remove_handler(wait_for_ffmpeg, group=124)
                
                ffmpeg_params = ffmpeg_response.text.strip()
                
                if ffmpeg_params.lower() == "!cancel":
                    await ffmpeg_msg.edit("Operation cancelled.")
                    return
                elif ffmpeg_params.lower() == "!default":
                    ffmpeg_params = "-c:v libx264 -preset medium -crf 23 -c:a aac -b:a 128k"
                
                await handle_direct_link(message, url, None, ffmpeg_params)
            
        elif command == "!cancel":
            await confirm_msg.edit("❌ Operation cancelled.")
        else:
            await confirm_msg.edit("❌ Invalid command. Operation cancelled.")


# Example command for downloading with custom FFmpeg processing
@Client.on_message(filters.command("process") & filters.text)
async def process_media_command(client, message: Message):
    """Process a media file with custom FFmpeg parameters"""
    # Check if the message contains necessary parameters
    if len(message.command) < 3:
        await message.reply_text(
            "❌ Please provide both URL and FFmpeg parameters.\n\n"
            "Usage: `/process URL \"FFmpeg parameters\"`\n\n"
            "Example: `/process https://example.com/video.mp4 \"-c:v libx264 -crf 23\"`"
        )
        return
    
    url = message.command[1]
    ffmpeg_params = ' '.join(message.command[2:])
    
    # Handle the media processing
    await handle_direct_link(message, url, None, ffmpeg_params)


# Command to show FFmpeg presets
@Client.on_message(filters.command("ffmpeg_presets"))
async def show_ffmpeg_presets(client, message: Message):
    """Show available FFmpeg presets"""
    presets = {
        "compress": "-c:v libx264 -preset slow -crf 28 -c:a aac -b:a 96k",
        "hevc": "-c:v libx265 -preset medium -crf 28 -c:a aac -b:a 128k",
        "fastcompress": "-c:v libx264 -preset ultrafast -crf 28 -c:a aac -b:a 96k",
        "hd": "-c:v libx264 -preset slow -crf 18 -c:a aac -b:a 192k",
        "gif": "-vf \"fps=10,scale=320:-1:flags=lanczos\" -c:v gif",
        "remux": "-c copy",
        "normalize_audio": "-c:v copy -c:a aac -af \"loudnorm=I=-16:LRA=11:TP=-1.5\" -b:a 192k"
    }
    
    preset_text = "**📋 Available FFmpeg Presets:**\n\n"
    for name, params in presets.items():
        preset_text += f"• **{name}**: `/process URL \"{params}\"`\n\n"
    
    await message.reply_text(preset_text)

async def main():
    if WEBHOOK:
        # Start the web server
        app = await web_server()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", PORT)
        await site.start()
        print(f"Web server started on port {PORT}")

if __name__ == "__main__":
    print("""
    █░█░█ █▀█ █▀█ █▀▄ █▀▀ █▀█ ▄▀█ █▀▀ ▀█▀     ▄▀█ █▀ █░█ █░█ ▀█▀ █▀█ █▀ █░█   
    ▀▄▀▄▀ █▄█ █▄█ █▄▀ █▄▄ █▀▄ █▀█ █▀░ ░█░     █▀█ ▄█ █▀█ █▄█ ░█░ █▄█ ▄█ █▀█ """)

    # Start the bot and web server concurrently
    async def start_bot():
        await bot.start()

    async def start_web():
        await main()

    loop = asyncio.get_event_loop()
    try:
        # Create tasks to run bot and web server concurrently
        loop.create_task(start_bot())
        loop.create_task(start_web())

        # Keep the main thread running until all tasks are complete
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        # Cleanup
        loop.stop()
