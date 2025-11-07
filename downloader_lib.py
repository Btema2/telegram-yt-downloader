import asyncio
import os
import shutil
import time
from pathlib import Path
from typing import List

import instaloader
import yt_dlp

# --- Нова логіка для Instagram ---


async def _download_instagram_post_async(
    url: str, session_dir: str
) -> List[str] | None:
    """Завантажує пост з Instagram за допомогою instaloader."""
    loop = asyncio.get_event_loop()

    # Запускаємо синхронну бібліотеку instaloader в окремому потоці
    await loop.run_in_executor(
        None, lambda: _download_instagram_post_sync(url, session_dir)
    )

    # Збираємо список файлів, ігноруючи .json.xz та .txt файли
    allowed_extensions = [".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov"]
    filenames = [
        os.path.join(session_dir, f)
        for f in os.listdir(session_dir)
        if os.path.splitext(f)[1].lower() in allowed_extensions
    ]

    return filenames


def _download_instagram_post_sync(url: str, session_dir: str):
    """Синхронна частина для роботи з instaloader."""
    username = os.getenv("INSTAGRAM_USERNAME")
    if not username:
        raise ValueError("INSTAGRAM_USERNAME не встановлено у .env")

    try:
        L = instaloader.Instaloader(
            download_pictures=True,
            download_videos=True,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            filename_pattern="{shortcode}_{date_utc}_UTC_{mediaid}",  # Спрощений шаблон
        )

        print("INFO: Спроба завантажити сесію для Instaloader...")
        L.load_session_from_file(username)
        print("INFO: Сесія успішно завантажена.")

        shortcode = url.split("/")[-2]
        post = instaloader.Post.from_shortcode(L.context, shortcode)

        print(f"INFO: Починаю завантаження поста Instagram {shortcode}...")
        L.download_post(post, target=Path(session_dir))
        print("INFO: Завантаження поста Instagram завершено.")

    except instaloader.exceptions.LoginRequiredException:
        print(
            "ERROR: Сесія Instaloader недійсна або відсутня. Запустіть 'instaloader --login=YOUR_USERNAME'"
        )
        raise
    except Exception as e:
        print(f"ERROR: Помилка в Instaloader: {e}")
        raise


# --- Існуюча логіка для yt-dlp ---


def _get_ydl_opts(download_dir: str, audio_only: bool, format_id: str | None):
    """Готує конфігурацію для yt-dlp."""
    os.makedirs(download_dir, exist_ok=True)

    common_opts = {
        "quiet": False,
        "no_warnings": False,
        "verbose": True,
    }

    if audio_only:
        opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
        }
    else:
        opts = {
            "format": format_id if format_id else "best",
            "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),
        }

    opts.update(common_opts)
    return opts


async def _download_with_yt_dlp(
    url: str, session_dir: str, audio_only: bool, format_id: str | None
) -> List[str] | None:
    """Завантажує медіа за допомогою yt-dlp."""
    loop = asyncio.get_event_loop()
    ydl_opts = _get_ydl_opts(session_dir, audio_only, format_id)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        print(f"INFO: Починаю завантаження з {url} за допомогою yt-dlp...")
        await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))

    filenames = [os.path.join(session_dir, f) for f in os.listdir(session_dir)]
    return filenames


# --- Головна функція ---


async def download_media(
    url: str, audio_only: bool = False, format_id: str = None
) -> List[str] | None:
    """
    Визначає тип посилання і викликає відповідний завантажувач.
    """
    base_download_path = "downloads"
    session_dir = os.path.join(base_download_path, str(time.time_ns()))
    os.makedirs(session_dir, exist_ok=True)

    try:
        if "instagram.com" in url:
            return await _download_instagram_post_async(url, session_dir)
        else:
            return await _download_with_yt_dlp(url, session_dir, audio_only, format_id)
    except Exception as e:
        print(f"Помилка в download_media: {e}")
        if os.path.exists(session_dir):
            shutil.rmtree(session_dir)
        return None


# Функція get_available_formats залишається без змін, вона потрібна для YouTube
async def get_available_formats(url: str) -> str | None:
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
            format_id, ext = f.get("format_id"), f.get("ext")
            resolution = f.get("resolution", "audio only")
            note = f.get("format_note", "") or resolution
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
