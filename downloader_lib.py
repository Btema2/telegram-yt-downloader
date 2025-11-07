# downloader_lib.py
import asyncio
import os
from typing import List

import yt_dlp

# Шлях до файлу cookies. Ми будемо брати його з .env для гнучкості
COOKIES_FILE_PATH = os.getenv("INSTAGRAM_COOKIES_PATH")


def _get_ydl_opts(url: str, progress_hook=None, audio_only=False, format_id=None):
    """Допоміжна функція для генерації конфігурації yt-dlp."""
    video_dir = os.path.join("downloads", "video")
    audio_dir = os.path.join("downloads", "audio")
    os.makedirs(video_dir, exist_ok=True)
    os.makedirs(audio_dir, exist_ok=True)

    # Базові налаштування
    common_opts = {
        "progress_hooks": [progress_hook] if progress_hook else [],
        "quiet": True,
        "noplaylist": False, # Дозволяємо завантажувати всі елементи з поста
    }

    # Додаємо cookies, якщо це посилання на Instagram і файл існує
    if "instagram.com" in url and COOKIES_FILE_PATH and os.path.exists(COOKIES_FILE_PATH):
        print(f"INFO: Використовую файл cookies для Instagram: {COOKIES_FILE_PATH}")
        common_opts['cookiefile'] = COOKIES_FILE_PATH

    if audio_only:
        opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(audio_dir, "%(title)s.%(ext)s"),
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
        }
    else:
        if not format_id:
            format_id = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        
        # Використовуємо шаблон з автонумерацією для Instagram та інших "галерей"
        if "instagram.com" in url:
            outtmpl = os.path.join(video_dir, "%(title)s_%(autonumber)s.%(ext)s")
        else:
            outtmpl = os.path.join(video_dir, "%(title)s.%(ext)s")
        
        opts = {
            "format": format_id,
            "outtmpl": outtmpl,
        }
    
    # Об'єднуємо загальні налаштування зі специфічними
    opts.update(common_opts)
    return opts


async def download_media(
    url: str, audio_only: bool = False, format_id: str = None
) -> List[str] | None:
    """
    Асинхронний завантажувач медіа.
    Повертає СПИСОК шляхів до файлів або None у разі помилки.
    """
    loop = asyncio.get_event_loop()
    # Передаємо URL в _get_ydl_opts
    ydl_opts = _get_ydl_opts(url, audio_only=audio_only, format_id=format_id)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(
                None, lambda: ydl.extract_info(url, download=True)
            )
            
            filenames = []
            
            # Перевіряємо, чи це галерея/плейлист (має ключ 'entries')
            if 'entries' in info and info['entries']:
                for entry in info['entries']:
                    filename = ydl.prepare_filename(entry)
                    if audio_only:
                        # Замінюємо розширення на mp3 після обробки
                        base, _ = os.path.splitext(filename)
                        final_path = f"{base}.mp3"
                        # Перевіряємо, чи файл існує, бо ffmpeg міг бути ще не завершений
                        if not os.path.exists(final_path):
                             filenames.append(filename) # додаємо оригінал, якщо mp3 ще немає
                        else:
                             filenames.append(final_path)
                    else:
                        filenames.append(filename)
            else:
                # Якщо це один медіафайл
                filename = ydl.prepare_filename(info)
                if audio_only:
                    base, _ = os.path.splitext(filename)
                    filenames.append(f"{base}.mp3")
                else:
                    filenames.append(filename)

            return filenames
            
    except Exception as e:
        print(f"Помилка завантаження: {e}")
        return None


async def get_available_formats(url: str) -> str | None:
    """
    Повертає відформатований та ВІДФІЛЬТРОВАНИЙ рядок зі списком доступних форматів,
    щоб уникнути перевищення ліміту повідомлень Telegram.
    """
    loop = asyncio.get_event_loop()
    ydl_opts = {"quiet": True}

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(
                None, lambda: ydl.extract_info(url, download=False)
            )

        output_lines = ["*ID* | *Розширення* | *Роздільна здатність* | *Нотатки*\n`"]
        filtered_formats = []
        resolutions_added = set()
        audio_added = False

        formats = sorted(
            info.get("formats", []),
            key=lambda f: (f.get("height", 0) or 0, f.get("tbr", 0) or 0),
            reverse=True,
        )

        for f in formats:
            if not f.get("url"):
                continue

            height = f.get("height")

            if f.get("vcodec") == "none" and not audio_added:
                filtered_formats.append(f)
                audio_added = True
                continue

            if height and height not in resolutions_added:
                if f.get("acodec") != "none":
                    filtered_formats.append(f)
                    resolutions_added.add(height)
                elif f.get("acodec") == "none" and not any(
                    x.get("height") == height and x.get("acodec") != "none"
                    for x in formats
                ):
                    filtered_formats.append(f)
                    resolutions_added.add(height)

        if len(filtered_formats) > 15:
            filtered_formats = filtered_formats[:25]

        for f in filtered_formats:
            format_id = f.get("format_id")
            ext = f.get("ext")
            resolution = f.get("resolution", "audio only")
            note = f.get("format_note", "")
            if not note:
                note = resolution

            if f.get("vcodec") == "none":
                note += " (лише аудіо)"
            elif f.get("acodec") == "none":
                note += " (лише відео)"

            output_lines.append(
                f"`{format_id:<4}`| `{ext:<11}`| `{resolution:<20}`| {note}"
            )

        output_lines.append(
            "`\n💡 *Порада:* Для найкращої якості ви можете комбінувати ID відео та аудіо через `+`, наприклад: `137+140`."
        )

        return "\n".join(output_lines)

    except Exception as e:
        print(f"Помилка отримання форматів: {e}")
        return "Не вдалося отримати інформацію про формати для цього посилання."