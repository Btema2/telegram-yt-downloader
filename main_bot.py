import logging
import os
import asyncio
from dotenv import load_dotenv
from functools import wraps

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

from downloader_lib import download_media, get_available_formats

# --- Налаштування ---
load_dotenv()
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_FILE_LIMIT = 50 * 1024 * 1024 
logging.basicConfig(level=logging.INFO)

# --- Зчитування списку дозволених ID з .env ---
# У .env файлі це має виглядати так: ALLOWED_USER_IDS=12345678,98765432,11122233
ALLOWED_IDS_STR = os.getenv("ALLOWED_USER_IDS", "")
# Використовуємо set для дуже швидкої перевірки
ALLOWED_USER_IDS = {int(user_id) for user_id in ALLOWED_IDS_STR.split(',') if user_id.strip()}

if not ALLOWED_USER_IDS:
    logging.warning("Увага: список дозволених ID порожній! Бот не буде відповідати нікому.")

storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# --- Декоратор для перевірки доступу ---
def allowed_users_only(func):
    """Декоратор, який перевіряє, чи є ID користувача у білому списку."""
    @wraps(func)
    async def wrapper(update: types.Update, *args, **kwargs):
        # Визначаємо, звідки прийшов запит (повідомлення чи кнопка)
        if isinstance(update, types.CallbackQuery):
            user_id = update.from_user.id
            message = update.message # Щоб мати куди відповідати
        elif isinstance(update, types.Message):
            user_id = update.from_user.id
            message = update
        else:
            return # Невідомий тип оновлення

        if user_id in ALLOWED_USER_IDS:
            return await func(update, *args, **kwargs)
        else:
            # Відповідаємо користувачу, що йому відмовлено у доступі
            await message.reply(
                "❌ **Доступ обмежено.**\n\n"
                "Вас немає у системі. Для отримання доступу, будь ласка, зверніться до розробників",
                parse_mode='Markdown'
            )
    return wrapper

class DownloadStates(StatesGroup):
    awaiting_format_id = State()

def get_youtube_keyboard():
    buttons = [
        [InlineKeyboardButton(text="📥 Відео (найкраща якість)", callback_data="yt_best_video")],
        [InlineKeyboardButton(text="🎵 Аудіо (MP3)", callback_data="yt_audio_only")],
        [InlineKeyboardButton(text="⚙️ Вибрати якість вручну", callback_data="yt_choose_quality")],
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

@dp.callback_query(F.data.startswith('yt_'))
@allowed_users_only
async def handle_youtube_choice(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.edit_text(f"Обробляю ваш вибір...")
    action = callback_query.data
    user_data = await state.get_data()
    url = user_data.get("url")
    if not url:
        await callback_query.message.edit_text("Помилка: URL не знайдено.")
        return

    if action == 'yt_best_video':
        await process_download(callback_query.message, url, audio_only=False)
    elif action == 'yt_audio_only':
        await process_download(callback_query.message, url, audio_only=True)
    elif action == 'yt_choose_quality':
        formats_text = await get_available_formats(url)
        await callback_query.message.answer(
            f"Ось доступні формати:\n\n{formats_text}\n\n"
            "Надішліть мені ID бажаного формату.",
            parse_mode='Markdown'
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

    await message.reply(f"Прийнято ID: `{format_id}`. Починаю завантаження...", parse_mode='Markdown')
    await process_download(message, url, format_id=format_id)
    await state.clear()

@dp.message(F.text)
@allowed_users_only
async def handle_url(message: types.Message, state: FSMContext):
    # Перевіряємо, чи є в тексті посилання, щоб бот не реагував на звичайні повідомлення в групі
    if not ('http' in message.text and ' ' not in message.text.strip()):
        return

    url = message.text.strip()

    if "music.youtube.com" in url:
        await process_download(message, url, audio_only=True)
    elif "youtube.com" in url or "youtu.be" in url:
        await message.reply("Виявлено посилання на YouTube. Оберіть дію:", reply_markup=get_youtube_keyboard())
        await state.update_data(url=url)
    else:
        await process_download(message, url, audio_only=False)

async def process_download(message: types.Message, url: str, audio_only: bool = False, format_id: str = None):
    # Використовуємо .reply(), щоб в групі було зрозуміло, на яке повідомлення відповідає бот
    msg = await message.reply("📥 Завантаження почалося...")
    file_path = None

    try:
        file_path = await download_media(url, audio_only=audio_only, format_id=format_id)

        if not (file_path and os.path.exists(file_path)):
            await msg.edit_text("❌ Не вдалося завантажити медіа.")
            return

        file_size = os.path.getsize(file_path)

        if file_size > TELEGRAM_FILE_LIMIT:
            file_size_mb = file_size / 1024 / 1024
            error_message = (
                f"❌ **Файл занадто великий** ({file_size_mb:.1f} МБ).\n\n"
                "Telegram не дозволяє ботам надсилати файли понад 50 МБ.\n\n"
                "**💡 Що робити?**\n"
                "Надішліть посилання ще раз і натисніть '⚙️ Вибрати якість вручну', "
                "а потім оберіть формат з меншою роздільною здатністю."
            )
            await msg.edit_text(error_message, parse_mode='Markdown')
            return

        await msg.edit_text("🚀 Надсилаю файл...")
        if audio_only:
            await message.reply_audio(FSInputFile(file_path))
        else:
            await message.reply_video(FSInputFile(file_path))
        
        await msg.delete()

    except Exception as e:
        await msg.edit_text(f"❌ Сталася неочікувана помилка: {e}")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

async def main() -> None:
    bot = Bot(token=API_TOKEN)
    await dp.start_polling(bot)

if __name__ == '__main__':
    if not API_TOKEN:
        logging.error("Помилка: не знайдено TELEGRAM_BOT_TOKEN.")
    else:
        asyncio.run(main())