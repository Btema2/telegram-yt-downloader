#main_bot.py
import asyncio
import logging
import os
from functools import wraps
from typing import List

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
# Додано імпорти для медіагруп
from aiogram.types import (FSInputFile, InlineKeyboardButton,
                           InlineKeyboardMarkup, InputMediaPhoto,
                           InputMediaVideo)
from dotenv import load_dotenv

from downloader_lib import download_media, get_available_formats

# --- Налаштування ---
load_dotenv()
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_FILE_LIMIT = 50 * 1024 * 1024  # 50 MB
# Ліміт для фотографій трохи менший
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
        "Просто надішли мені посилання, і я все зроблю!"
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
    
    # Визначаємо, чи обробляти як аудіо за замовчуванням
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
        # Для всіх інших посилань (включаючи Instagram)
        await process_download(message, url, audio_only=False)


async def process_download(
    message: types.Message, url: str, audio_only: bool = False, format_id: str = None
):
    msg = await message.reply("📥 Завантаження почалося...")
    file_paths: List[str] | None = None

    try:
        file_paths = await download_media(
            url, audio_only=audio_only, format_id=format_id
        )

        if not (file_paths and all(os.path.exists(p) for p in file_paths)):
            await msg.edit_text("❌ Не вдалося завантажити медіа.")
            return

        # --- НОВА ЛОГІКА ОБРОБКИ ФАЙЛІВ ---
        
        # 1. Обробка аудіо (залишається простою, бо зазвичай це один файл)
        if audio_only:
            await msg.edit_text("🚀 Надсилаю аудіо...")
            for file_path in file_paths:
                await message.reply_audio(FSInputFile(file_path))
            await msg.delete()
            return

        # 2. Обробка фото та відео
        media_to_send = []
        for file_path in file_paths:
            file_size = os.path.getsize(file_path)
            ext = os.path.splitext(file_path)[1].lower()
            
            # Перевірка розміру
            limit = TELEGRAM_PHOTO_LIMIT if ext in ['.jpg', '.jpeg', '.png', '.webp'] else TELEGRAM_FILE_LIMIT
            if file_size > limit:
                file_size_mb = file_size / 1024 / 1024
                error_message = (
                    f"❌ **Один з файлів занадто великий** ({file_size_mb:.1f} МБ).\n\n"
                    f"Telegram обмежує розмір файлів (до 50 МБ для відео/документів та 10 МБ для фото)."
                )
                await msg.edit_text(error_message, parse_mode="Markdown")
                return # Перериваємо всю операцію

            # Створюємо об'єкти для медіагрупи
            if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                media_to_send.append(InputMediaPhoto(media=FSInputFile(file_path)))
            elif ext in ['.mp4', '.mkv', '.avi', '.mov']:
                media_to_send.append(InputMediaVideo(media=FSInputFile(file_path)))
            else:
                 logging.warning(f"Невідомий тип файлу: {file_path}. Спробую надіслати як документ.")
                 # Якщо щось невідоме - можна спробувати як документ, але поки пропускаємо
                 pass
        
        if not media_to_send:
            await msg.edit_text("❌ Не знайдено медіафайлів для надсилання.")
            return

        await msg.edit_text("🚀 Надсилаю файли...")

        # Надсилаємо один файл або групу
        if len(media_to_send) > 1:
            await message.reply_media_group(media=media_to_send)
        elif len(media_to_send) == 1:
            # Використовуємо відповідний метод для одного файлу
            single_file_path = file_paths[0]
            if isinstance(media_to_send[0], InputMediaPhoto):
                await message.reply_photo(FSInputFile(single_file_path))
            else:
                await message.reply_video(FSInputFile(single_file_path))

        await msg.delete()

    except Exception as e:
        logging.error(f"Помилка в process_download: {e}", exc_info=True)
        await msg.edit_text(f"❌ Сталася неочікувана помилка: {e}")
    finally:
        # Очищуємо всі завантажені файли
        if file_paths:
            for file_path in file_paths:
                if os.path.exists(file_path):
                    os.remove(file_path)


async def main() -> None:
    bot = Bot(token=API_TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    if not API_TOKEN:
        logging.error("Помилка: не знайдено TELEGRAM_BOT_TOKEN.")
    else:
        asyncio.run(main())