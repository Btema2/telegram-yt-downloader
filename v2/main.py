import os
import re
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile
from dotenv import load_dotenv
import yt_dlp

load_dotenv()
bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()

PATTERNS = [r'(https?://)?(www\.)?(tiktok\.com|vt\.tiktok\.com|vm\.tiktok\.com)/\S+', 
            r'(https?://)?(www\.)?instagram\.com/(p|reel|reels)/\S+']

def extract_url(text: str) -> str | None:
    for pattern in PATTERNS:
        if match := re.search(pattern, text):
            url = match.group(0)
            return url if url.startswith('http') else 'https://' + url
    return None

async def download_video(url: str) -> tuple[str | None, str | None]:
    ydl_opts = {
        'format': 'best',
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {'tiktok': {'webpage_download': True}},
    }
    try:
        def download():
            os.makedirs('downloads', exist_ok=True)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info), info.get('ext', 'mp4')
        return await asyncio.get_event_loop().run_in_executor(None, download)
    except Exception as e:
        print(f"Памылка: {e}")
        return None, None

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.reply("Прывітанне! Адпраў спасылку на TikTok або Instagram.")

@dp.message(F.text)
async def handle_url(message: types.Message):
    if not message.text or not (url := extract_url(message.text)):
        return
    
    status_msg = await message.reply("Спампоўваю...")
    try:
        filename, ext = await download_video(url)
        if not filename or not os.path.exists(filename):
            await status_msg.edit_text("Не атрымалася спампаваць.")
            return
        
        file = FSInputFile(filename)
        await (message.reply_photo(file) if ext in ['jpg', 'jpeg', 'png', 'webp'] else message.reply_video(file))
        await status_msg.delete()
        os.remove(filename)
    except Exception as e:
        await status_msg.edit_text(f"Памылка: {str(e)}")

async def main():
    print("Бот запушчаны!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())