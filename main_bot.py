# main_bot.py
import asyncio
import logging
import os
import re
import shutil
from functools import wraps
from typing import Optional

from aiogram import Bot, Dispatcher, F, types
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
)
from dotenv import load_dotenv

from downloader_lib import download_media

load_dotenv()

# --- КОНФІГУРАЦІЯ ---
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
# Ліміт для локального сервера (2 ГБ)
LOCAL_SERVER_LIMIT = 2000 * 1024 * 1024
logging.basicConfig(level=logging.INFO)

ALLOWED_IDS_STR = os.getenv("ALLOWED_USER_IDS", "")
ALLOWED_USER_IDS = {int(uid) for uid in ALLOWED_IDS_STR.split(",") if uid.strip()}

LOCAL_API_URL = os.getenv("LOCAL_API_URL")

session = None
if LOCAL_API_URL:
    print(f"🔌 Використовується локальний Bot API сервер: {LOCAL_API_URL}")
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(LOCAL_API_URL),
        timeout=7200,  # 2 години таймаут
    )

storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# --- ДЕКОРАТОР ---
def allowed_users_only(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        event = args[0]
        user = event.from_user
        if isinstance(event, types.Message):
            pass
        elif isinstance(event, types.CallbackQuery):
            pass
        else:
            return
        if user and user.id in ALLOWED_USER_IDS:
            return await func(*args, **kwargs)

    return wrapper


# --- КЛАВІАТУРА ---
def get_quality_keyboard():
    buttons = [
        [
            InlineKeyboardButton(
                text="💎 Найкраща (1080p+)", callback_data="qual_best"
            ),
            InlineKeyboardButton(text="ᴴᴰ 720p", callback_data="qual_720"),
        ],
        [
            InlineKeyboardButton(text="📺 480p", callback_data="qual_480"),
            InlineKeyboardButton(text="📱 360p", callback_data="qual_360"),
        ],
        [
            InlineKeyboardButton(
                text="🎵 Тільки аудіо (MP3)", callback_data="qual_audio"
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- ДОПОМІЖНІ ---
def extract_url(text: str) -> Optional[str]:
    match = re.search(r"(https?://[^\s]+)", text)
    return match.group(1) if match else None


# --- ОБРОБНИКИ ---


@dp.message(CommandStart())
@allowed_users_only
async def send_welcome(message: types.Message):
    await message.reply("Привіт! Надішли посилання.\n\nКоманди:\n/clean - очистити кеш")


# --- КОМАНДА CLEAN ---
@dp.message(Command("clean"))
@allowed_users_only
async def handle_clean(message: types.Message):
    status_msg = await message.reply("🧹 Аналіз папки завантажень...")
    base_dir = "downloads"
    if not os.path.exists(base_dir):
        await status_msg.edit_text("✅ Папка чиста.")
        return

    deleted_files = 0
    deleted_folders = 0
    try:
        for filename in os.listdir(base_dir):
            file_path = os.path.join(base_dir, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                    deleted_files += 1
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
                    deleted_folders += 1
            except Exception as e:
                logging.debug(f"Could not remove {file_path}: {e}")
        await status_msg.edit_text(
            f"✅ Очищено.\nПапок: {deleted_folders}\nФайлів: {deleted_files}"
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ Помилка: {e}")


@dp.callback_query(F.data.startswith("qual_"))
@allowed_users_only
async def handle_quality_choice(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("⏳ Додано в чергу...", show_alert=False)
    await callback.message.edit_text("⏳ Ініціалізація...")

    data = await state.get_data()
    url = data.get("url")
    if not url:
        await callback.message.edit_text("❌ Посилання втрачено.")
        return

    action = callback.data
    audio_only = action == "qual_audio"
    max_height = None
    if action == "qual_720":
        max_height = 720
    elif action == "qual_480":
        max_height = 480
    elif action == "qual_360":
        max_height = 360

    await process_download(
        callback.message, url, audio_only=audio_only, max_height=max_height
    )


@dp.message(F.text)
@allowed_users_only
async def handle_text(message: types.Message, state: FSMContext):
    url = extract_url(message.text)
    if not url:
        return

    is_music_service = any(
        x in url
        for x in [
            "music.youtube.com",
            "soundcloud.com",
            "spotify.com",
            "deezer.com",
            "apple.com/music",
        ]
    )

    if is_music_service:
        await process_download(message, url, audio_only=True)
    elif ("youtube.com" in url or "youtu.be" in url) and "shorts" not in url:
        await state.update_data(url=url)
        await message.reply(
            "🎥 Виберіть якість відео:", reply_markup=get_quality_keyboard()
        )
    else:
        # Instagram, TikTok etc
        await process_download(message, url, audio_only=False)


async def process_download(
    message: types.Message,
    url: str,
    audio_only: bool = False,
    max_height: Optional[int] = None,
):
    status_msg = await message.answer("⏳ Підготовка...")

    async def update_progress(text: str):
        try:
            if status_msg.text != text:
                await status_msg.edit_text(text, parse_mode="Markdown")
        except TelegramBadRequest:
            pass
        except Exception as e:
            print(f"Error: {e}")

    download_dir = None
    try:
        file_paths = await download_media(
            url,
            audio_only=audio_only,
            max_height=max_height,
            progress_callback=update_progress,
        )

        if not file_paths:
            # ТИХИЙ РЕЖИМ ПРИ ПОМИЛЦІ
            try:
                await status_msg.delete()
            except Exception as e:
                logging.debug(f"Failed to delete status message: {e}")
            return

        download_dir = os.path.dirname(file_paths[0])
        await status_msg.edit_text("📤 *Відправляю...*", parse_mode="Markdown")

        media_group = []
        for file_path in file_paths:
            file_size = os.path.getsize(file_path)
            if file_size > LOCAL_SERVER_LIMIT:
                await message.reply("⚠️ Файл завеликий.")
                continue

            ext = os.path.splitext(file_path)[1].lower()
            file_obj = FSInputFile(file_path)

            if audio_only and ext in [".mp3", ".m4a", ".flac"]:
                await message.reply_audio(file_obj, request_timeout=7200)
            else:
                if ext in [".jpg", ".jpeg", ".png", ".webp"]:
                    media_group.append(InputMediaPhoto(media=file_obj))
                elif ext in [".mp4", ".mkv", ".mov", ".webm"]:
                    media_group.append(InputMediaVideo(media=file_obj))

        if media_group:
            if len(media_group) == 1:
                item = media_group[0]
                if isinstance(item, InputMediaPhoto):
                    await message.reply_photo(item.media, request_timeout=7200)
                else:
                    await message.reply_video(item.media, request_timeout=7200)
            else:
                for i in range(0, len(media_group), 10):
                    await message.reply_media_group(
                        media=media_group[i : i + 10], request_timeout=7200
                    )

        try:
            await status_msg.delete()
        except Exception as e:
            logging.debug(f"Error {download_dir}: {e}")

    except Exception as e:
        logging.error(f"Error: {e}")
        try:
            await status_msg.delete()
        except Exception as ex:
            logging.debug(f"Failed to delete status message after error: {ex}")
    finally:
        if download_dir and os.path.exists(download_dir):
            try:
                shutil.rmtree(download_dir)
            except Exception as e:
                logging.debug(
                    f"Failed to remove download directory {download_dir}: {e}"
                )


async def main():
    if not API_TOKEN:
        return
    bot = Bot(token=API_TOKEN, session=session)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
