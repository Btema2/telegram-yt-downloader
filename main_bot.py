# main_bot.py
import asyncio
import logging
import os
import shutil
import time
from functools import wraps
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()

from aiogram import Bot, Dispatcher, F, types  # noqa: E402
from aiogram.filters import CommandStart  # noqa: E402
from aiogram.fsm.context import FSMContext  # noqa: E402
from aiogram.fsm.state import State, StatesGroup  # noqa: E402
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402
from aiogram.types import (  # noqa: E402
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
)

from downloader_lib import download_media, get_available_formats  # noqa: E402

# --- Налаштування (без змін) ---
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_FILE_LIMIT = 50 * 1024 * 1024
TELEGRAM_PHOTO_LIMIT = 10 * 1024 * 1024
logging.basicConfig(level=logging.INFO)
ALLOWED_IDS_STR = os.getenv("ALLOWED_USER_IDS", "")
ALLOWED_USER_IDS = {int(uid) for uid in ALLOWED_IDS_STR.split(",") if uid.strip()}
if not ALLOWED_USER_IDS:
    logging.warning("Увага: список дозволених ID порожній!")
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# --- ДЕКОРАТОР (ПОВЕРНЕНО ДО НАДІЙНОЇ ВЕРСІЇ) ---
def allowed_users_only(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Перший аргумент - це завжди об'єкт події (Message або CallbackQuery)
        event = args[0]

        user = event.from_user

        # Визначаємо, куди відповідати
        if isinstance(event, types.Message):
            message_to_reply = event
        elif isinstance(event, types.CallbackQuery):
            message_to_reply = event.message
        else:
            return  # Невідомий тип події

        if user and message_to_reply and user.id in ALLOWED_USER_IDS:
            return await func(*args, **kwargs)
        elif message_to_reply:
            await message_to_reply.reply(
                "❌ **Доступ обмежено.**", parse_mode="Markdown"
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
async def send_welcome(message: types.Message, *args, **kwargs):
    await message.reply(
        "Привіт! 👋\n\nЯ універсальний завантажувач медіа.\nПросто надішли мені посилання, і я все зроблю!"
    )


@dp.callback_query(F.data.startswith("yt_"))
@allowed_users_only
async def handle_youtube_choice(
    callback_query: types.CallbackQuery, state: FSMContext, *args, **kwargs
):
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
            f"Ось доступні формати:\n\n{formats_text}\n\nНадішліть мені ID бажаного формату.",
            parse_mode="Markdown",
        )
        await state.set_state(DownloadStates.awaiting_format_id)
    await callback_query.answer()


@dp.message(DownloadStates.awaiting_format_id)
@allowed_users_only
async def process_manual_format_id(
    message: types.Message, state: FSMContext, *args, **kwargs
):
    format_id = message.text
    user_data = await state.get_data()
    url = user_data.get("url")
    if not url or not format_id:
        await message.reply("Щось пішло не так, URL або ID формату не знайдено.")
        await state.clear()
        return
    await message.reply(
        f"Прийнято ID: `{format_id}`. Починаю завантаження...", parse_mode="Markdown"
    )
    await process_download(message, url, format_id=format_id.strip())
    await state.clear()


@dp.message(F.text)
@allowed_users_only
async def handle_url(message: types.Message, state: FSMContext, *args, **kwargs):
    if not message.text or not (
        "http" in message.text and " " not in message.text.strip()
    ):
        return
    url = message.text.strip()
    is_audio_service = "music.youtube.com" in url or "soundcloud.com" in url
    if is_audio_service:
        await process_download(message, url, audio_only=True)
    elif "youtube.com" in url or "youtu.be" in url:
        await state.update_data(url=url)
        await message.reply(
            "Виявлено посилання на YouTube. Оберіть дію:",
            reply_markup=get_youtube_keyboard(),
        )
    else:
        await process_download(message, url, audio_only=False)


# --- ОСНОВНА ФУНКЦІЯ ОБРОБКИ (ЗБЕРЕЖЕНО ВИПРАВЛЕННЯ ДЛЯ ОБКЛАДИНКИ) ---
async def process_download(
    message: types.Message,
    url: str,
    audio_only: bool = False,
    format_id: Optional[str] = None,
):
    msg = await message.reply("📥 Завантаження почалося...")
    file_paths: Optional[List[str]] = None
    download_dir: Optional[str] = None

    try:
        file_paths = await download_media(
            url, audio_only=audio_only, format_id=format_id
        )

        if file_paths:
            # Даємо файловій системі час на збереження метаданих перед відправкою
            await asyncio.sleep(0.5)
            download_dir = os.path.dirname(file_paths[0])

        if not file_paths or not file_paths[0]:
            await msg.edit_text(
                "❌ Не вдалося завантажити медіа. Перевірте посилання або спробуйте пізніше."
            )
            return

        if audio_only:
            await msg.edit_text("🚀 Надсилаю аудіо...")
            for file_path in file_paths:
                if os.path.exists(file_path):
                    # Надсилаємо з унікальним іменем, щоб уникнути кешування TG
                    unique_filename = f"{os.path.basename(file_path).rsplit('.', 1)[0]}_{int(time.time())}.mp3"
                    await message.reply_audio(
                        FSInputFile(file_path, filename=unique_filename)
                    )
            await msg.delete()
            return

        # Логіка для відео та фото
        media_to_send, files_too_large = [], []
        for file_path in file_paths:
            file_size = os.path.getsize(file_path)
            ext = os.path.splitext(file_path)[1].lower()
            limit = (
                TELEGRAM_PHOTO_LIMIT
                if ext in [".jpg", ".jpeg", ".png"]
                else TELEGRAM_FILE_LIMIT
            )
            if file_size > limit:
                files_too_large.append(
                    f"{os.path.basename(file_path)} ({file_size / 1e6:.1f} МБ)"
                )
                continue
            if ext in [".jpg", ".jpeg", ".png", ".webp"]:
                media_to_send.append(InputMediaPhoto(media=FSInputFile(file_path)))
            elif ext in [".mp4", ".mkv", ".mov"]:
                media_to_send.append(InputMediaVideo(media=FSInputFile(file_path)))

        if files_too_large:
            error_msg = "⚠️ **Деякі файли завеликі:**\n" + "\n".join(
                f"• {f}" for f in files_too_large
            )
            if media_to_send:
                error_msg += "\n\n✅ Інші файли буде надіслано."
            await message.reply(error_msg, parse_mode="Markdown")

        if not media_to_send:
            await msg.edit_text("❌ Не знайдено медіафайлів для надсилання.")
            return

        await msg.edit_text(f"🚀 Надсилаю {len(media_to_send)} файл(ів)...")
        if len(media_to_send) > 1:
            for i in range(0, len(media_to_send), 10):
                await message.reply_media_group(media=media_to_send[i : i + 10])
        elif media_to_send:
            single_media = media_to_send[0]
            if isinstance(single_media, InputMediaPhoto):
                await message.reply_photo(single_media.media)
            else:
                await message.reply_video(single_media.media)
        await msg.delete()

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
    if not API_TOKEN:
        logging.critical("Помилка: не знайдено TELEGRAM_BOT_TOKEN в .env файлі.")
        return
    bot = Bot(token=API_TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
