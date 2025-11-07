import asyncio
import logging
import os
import shutil
from functools import wraps
from typing import List

from dotenv import load_dotenv
load_dotenv()

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (FSInputFile, InlineKeyboardButton,
                           InlineKeyboardMarkup, InputMediaPhoto,
                           InputMediaVideo)

from downloader_lib import download_media, get_available_formats

# --- Налаштування ---
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_FILE_LIMIT = 50 * 1024 * 1024  # 50 MB
TELEGRAM_PHOTO_LIMIT = 10 * 1024 * 1024 # 10 MB
logging.basicConfig(level=logging.INFO)

# --- Зчитування списку дозволених ID з .env ---
ALLOWED_IDS_STR = os.getenv("ALLOWED_USER_IDS", "")
ALLOWED_USER_IDS = {
    int(user_id) for user_id in ALLOWED_IDS_STR.split(",") if user_id.strip()
}

if not ALLOWED_USER_IDS:
    logging.warning(
        "Увага: список дозволених ID порожній! Бот не буде відповідати нікому."
    )

storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# --- Декоратор для перевірки доступу ---
def allowed_users_only(func):
    """Декоратор, який перевіряє, чи є ID користувача у білому списку."""

    @wraps(func)
    async def wrapper(update: types.Update, *args, **kwargs):
        if isinstance(update, types.CallbackQuery):
            user_id = update.from_user.id
            message = update.message
        elif isinstance(update, types.Message):
            user_id = update.from_user.id
            message = update
        else:
            return

        if user_id in ALLOWED_USER_IDS:
            return await func(update, *args, **kwargs)
        else:
            await message.reply(
                "❌ **Доступ обмежено.**\n\n"
                "Вас немає у системі. Для отримання доступу, будь ласка, зверніться до розробників",
                parse_mode="Markdown",
            )

    return wrapper


class DownloadStates(StatesGroup):
    awaiting_format_id = State()


def get_youtube_keyboard():
    buttons = [
        [
            InlineKeyboardButton(
                text="📥 Відео (найкраща якість)", callback_data="yt_best_video"
            )
        ],
        [InlineKeyboardButton(text="🎵 Аудіо (MP3)", callback_data="yt_audio_only")],
        [
            InlineKeyboardButton(
                text="⚙️ Вибрати якість вручну", callback_data="yt_choose_quality"
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- Обробники з доданим декоратором ---


@dp.message(CommandStart())
@allowed_users_only
async def send_welcome(message: types.Message):
    await message.reply(
        "Привіт! 👋\n\nЯ універсальний завантажувач медіа.\n"
        "Просто надішли мені посилання, і я все зроблю!\n\n"
        "📸 **Instagram:** Для завантаження всіх фото з каруселі потрібні cookies.\n"
        "Детальніше: https://github.com/yt-dlp/yt-dlp#authentication-with-cookies"
    )


@dp.callback_query(F.data.startswith("yt_"))
@allowed_users_only
async def handle_youtube_choice(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.edit_text("Обробляю ваш вибір...")
    action = callback_query.data
    user_data = await state.get_data()
    url = user_data.get("url")
    if not url:
        await callback_query.message.edit_text("Помилка: URL не знайдено.")
        return

    if action == "yt_best_video":
        await process_download(callback_query.message, url, audio_only=False)
    elif action == "yt_audio_only":
        await process_download(callback_query.message, url, audio_only=True)
    elif action == "yt_choose_quality":
        formats_text = await get_available_formats(url)
        await callback_query.message.answer(
            f"Ось доступні формати:\n\n{formats_text}\n\n"
            "Надішліть мені ID бажаного формату.",
            parse_mode="Markdown",
        )
        await state.set_state(DownloadStates.awaiting_format_id)
    await callback_query.answer()


@dp.message(DownloadStates.awaiting_format_id)
@allowed_users_only
async def process_manual_format_id(message: types.Message, state: FSMContext):
    format_id = message.text
    user_data = await state.get_data()
    url = user_data.get("url")
    if not url:
        await message.reply("Щось пішло не так, URL не знайдено.")
        await state.clear()
        return

    await message.reply(
        f"Прийнято ID: `{format_id}`. Починаю завантаження...", parse_mode="Markdown"
    )
    await process_download(message, url, format_id=format_id)
    await state.clear()


@dp.message(F.text)
@allowed_users_only
async def handle_url(message: types.Message, state: FSMContext):
    if not ("http" in message.text and " " not in message.text.strip()):
        return

    url = message.text.strip()
    
    is_audio_service = "music.youtube.com" in url or "soundcloud.com" in url
    
    if is_audio_service:
        await process_download(message, url, audio_only=True)
    elif "youtube.com" in url or "youtu.be" in url:
        await message.reply(
            "Виявлено посилання на YouTube. Оберіть дію:",
            reply_markup=get_youtube_keyboard(),
        )
        await state.update_data(url=url)
    else:
        await process_download(message, url, audio_only=False)


async def process_download(
    message: types.Message, url: str, audio_only: bool = False, format_id: str = None
):
    msg = await message.reply("📥 Завантаження почалося...")
    file_paths: List[str] | None = None
    download_dir: str | None = None

    try:
        file_paths = await download_media(
            url, audio_only=audio_only, format_id=format_id
        )

        if file_paths:
            download_dir = os.path.dirname(file_paths[0])

        if not file_paths:
            error_msg = "❌ Не вдалося завантажити медіа."
            
            if "instagram.com" in url:
                error_msg += (
                    "\n\n⚠️ **Для Instagram потрібна авторизація!**\n\n"
                    "Щоб завантажити всі фото/відео з каруселі:\n"
                    "1️⃣ Встанови розширення 'Get cookies.txt LOCALLY'\n"
                    "2️⃣ Увійди в Instagram у браузері\n"
                    "3️⃣ Експортуй cookies у файл\n"
                    "4️⃣ Вкажи шлях у .env: `INSTAGRAM_COOKIES_PATH=шлях`\n\n"
                    "Без cookies завантажується тільки перший елемент каруселі."
                )
            
            await msg.edit_text(error_msg, parse_mode="Markdown")
            return
        
        logging.info(f"Готово до відправки {len(file_paths)} файлів")

        if audio_only:
            await msg.edit_text("🚀 Надсилаю аудіо...")
            for file_path in file_paths:
                await message.reply_audio(FSInputFile(file_path))
            await msg.delete()
            return

        media_to_send = []
        files_too_large = []
        
        for file_path in file_paths:
            file_size = os.path.getsize(file_path)
            ext = os.path.splitext(file_path)[1].lower()
            
            limit = TELEGRAM_PHOTO_LIMIT if ext in ['.jpg', '.jpeg', '.png', '.webp'] else TELEGRAM_FILE_LIMIT
            
            if file_size > limit:
                file_size_mb = file_size / 1024 / 1024
                files_too_large.append(f"{os.path.basename(file_path)} ({file_size_mb:.1f} МБ)")
                continue

            if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                media_to_send.append(InputMediaPhoto(media=FSInputFile(file_path)))
            elif ext in ['.mp4', '.mkv', '.avi', '.mov']:
                media_to_send.append(InputMediaVideo(media=FSInputFile(file_path)))
            else:
                logging.warning(f"Невідомий тип файлу: {file_path}. Пропускаю.")
        
        if files_too_large:
            error_message = (
                f"⚠️ **Деякі файли занадто великі для Telegram:**\n"
                + "\n".join(f"• {f}" for f in files_too_large) +
                "\n\nTelegram обмежує розмір файлів (до 50 МБ для відео та 10 МБ для фото)."
            )
            if media_to_send:
                error_message += "\n\n✅ Інші файли будуть надіслані."
            else:
                await msg.edit_text(error_message, parse_mode="Markdown")
                return
            await message.reply(error_message, parse_mode="Markdown")
        
        if not media_to_send:
            await msg.edit_text("❌ Не знайдено медіафайлів для надсилання.")
            return

        await msg.edit_text(f"🚀 Надсилаю {len(media_to_send)} файл(ів)...")

        if len(media_to_send) > 1:
            for i in range(0, len(media_to_send), 10):
                batch = media_to_send[i:i+10]
                await message.reply_media_group(media=batch)
        elif len(media_to_send) == 1:
            single_media = media_to_send[0]
            if isinstance(single_media, InputMediaPhoto):
                await message.reply_photo(single_media.media)
            else:
                await message.reply_video(single_media.media)

        await msg.delete()
        
        if "instagram.com" in url and len(file_paths) == 1 and len(media_to_send) == 1:
            await message.reply(
                "⚠️ Завантажено лише 1 файл.\n\n"
                "Якщо це карусель з кількома фото/відео, вам потрібна авторизація через cookies.\n"
                "Детальніше: напишіть /start",
                parse_mode="Markdown"
            )

    except Exception as e:
        logging.error(f"Помилка в process_download: {e}", exc_info=True)
        await msg.edit_text(f"❌ Сталася неочікувана помилка: {e}")
    finally:
        if download_dir and os.path.exists(download_dir):
            try:
                shutil.rmtree(download_dir)
                logging.info(f"Видалено директорію: {download_dir}")
            except Exception as e:
                logging.error(f"Не вдалося видалити директорію {download_dir}: {e}")


async def main() -> None:
    bot = Bot(token=API_TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    if not API_TOKEN:
        logging.error("Помилка: не знайдено TELEGRAM_BOT_TOKEN.")
    else:
        asyncio.run(main())