# downloader_lib.py
import asyncio
import glob
import os
import shutil
import time
from io import BytesIO
from pathlib import Path
from typing import List, Optional

import instaloader
import yt_dlp
from mutagen.id3 import APIC, ID3, TDRC, TIT2, TPE1, error
from mutagen.mp3 import MP3
from PIL import Image

# --- ЛОГІКА ОБРОБКИ МЕТАДАНИХ (ВЗЯТО ПРЯМО З ВАШОГО КОДУ) ---


def _crop_and_embed_artwork(mp3_path: str, thumbnail_path: str):
    """
    Обрізає обкладинку до квадрата 1:1 з центру та вбудовує її
    в метадані MP3 файлу.
    """
    try:
        with Image.open(thumbnail_path) as img:
            width, height = img.size
            crop_size = min(width, height)
            left, top = (width - crop_size) / 2, (height - crop_size) / 2
            right, bottom = (width + crop_size) / 2, (height + crop_size) / 2
            cropped_img = img.crop((left, top, right, bottom))

            try:
                audio = MP3(mp3_path, ID3=ID3)
            except error:
                audio = MP3(mp3_path)
                audio.add_tags()

            audio.tags.delall("APIC")
            img_buffer = BytesIO()
            if cropped_img.mode in ("RGBA", "LA", "P"):
                cropped_img = cropped_img.convert("RGB")
            cropped_img.save(img_buffer, format="JPEG", quality=95)

            audio.tags.add(
                APIC(
                    encoding=3,
                    mime="image/jpeg",
                    type=3,
                    desc="Cover",
                    data=img_buffer.getvalue(),
                )
            )
            # Додаємо теги, щоб вони не були порожніми
            if not audio.tags.get("TIT2"):
                audio.tags.add(
                    TIT2(encoding=3, text=os.path.basename(mp3_path).split(".")[0])
                )
            if not audio.tags.get("TPE1"):
                audio.tags.add(TPE1(encoding=3, text="Unknown Artist"))

            audio.save()
            print(f"✓ Embedded cropped artwork into {os.path.basename(mp3_path)}")
    except Exception as e:
        print(f"Warning: Could not process or embed artwork: {e}")
    finally:
        if os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)
            print("✓ Cleaned up thumbnail file")


def _fix_date_metadata(mp3_path: str):
    """Виправляє дату в метаданих, залишаючи тільки рік."""
    try:
        audio = MP3(mp3_path, ID3=ID3)
        if audio.tags and "TDRC" in audio.tags:
            date_str = str(audio.tags["TDRC"].text[0])
            if len(date_str) >= 4:
                year = date_str[:4]
                audio.tags["TDRC"] = TDRC(encoding=3, text=year)
                audio.save()
                print(f"✓ Fixed date metadata to year only: {year}")
    except Exception as e:
        print(f"Warning: Could not fix date metadata: {e}")


# --- ОСНОВНА ФУНКЦІЯ ЗАВАНТАЖЕННЯ (АДАПТОВАНА ВАША ФУНКЦІЯ) ---


def _download_youtube_audio_sync(url: str, session_dir: str) -> Optional[str]:
    """
    Синхронна функція, що повністю копіює логіку з вашого downloader.py.
    """
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(session_dir, "%(title)s.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            },
            {
                "key": "FFmpegMetadata",
            },
        ],
        "writethumbnail": True,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            base_path = ydl.prepare_filename(info)
            base_name, _ = os.path.splitext(base_path)
            mp3_path = base_name + ".mp3"

            if not os.path.exists(mp3_path):
                print(f"ERROR: MP3 file not found at '{mp3_path}'")
                return None

            thumbnail_path = None
            possible_extensions = ["jpg", "jpeg", "png", "webp", "gif"]
            for ext in possible_extensions:
                candidate = f"{base_name}.{ext}"
                if os.path.exists(candidate):
                    thumbnail_path = candidate
                    break

            if not thumbnail_path:
                # Пошук через glob, як у вашому прикладі
                title_sanitized = (
                    ydl.prepare_filename(info)
                    .rsplit(os.path.sep, 1)[-1]
                    .rsplit(".", 1)[0]
                )
                for ext in possible_extensions:
                    pattern = os.path.join(session_dir, f"{title_sanitized}.{ext}")
                    matches = glob.glob(pattern)
                    if matches:
                        thumbnail_path = matches[0]
                        break

            if thumbnail_path and os.path.exists(thumbnail_path):
                print(f"✓ Thumbnail found: {os.path.basename(thumbnail_path)}")
                _crop_and_embed_artwork(mp3_path, thumbnail_path)
            else:
                print("Warning: Thumbnail file not found")

            _fix_date_metadata(mp3_path)
            return mp3_path
    except Exception as e:
        print(f"❌ An error occurred in _download_youtube_audio_sync: {e}")
        return None


# --- АСИНХРОННІ ОБГОРТКИ ТА ІНШІ ЗАВАНТАЖУВАЧІ ---


async def _download_with_yt_dlp(
    url: str, session_dir: str, audio_only: bool, format_id: Optional[str]
) -> Optional[List[str]]:
    if audio_only:
        loop = asyncio.get_event_loop()
        final_path = await loop.run_in_executor(
            None, _download_youtube_audio_sync, url, session_dir
        )
        return [final_path] if final_path else None
    else:
        # Стандартна логіка для відео
        ydl_opts = {
            "format": format_id
            or "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": os.path.join(session_dir, "%(title)s.%(ext)s"),
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: ydl.download([url]))
        return [os.path.join(session_dir, f) for f in os.listdir(session_dir)]


async def _download_instagram_post_async(
    url: str, session_dir: str
) -> Optional[List[str]]:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, lambda: _download_instagram_post_sync(url, session_dir)
    )
    allowed_extensions = [".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov"]
    return [
        os.path.join(session_dir, f)
        for f in os.listdir(session_dir)
        if os.path.splitext(f)[1].lower() in allowed_extensions
    ]


def _download_instagram_post_sync(url: str, session_dir: str):
    username = os.getenv("INSTAGRAM_USERNAME")
    if not username:
        raise ValueError("INSTAGRAM_USERNAME не встановлено у .env")
    try:
        L = instaloader.Instaloader(
            download_pictures=True,
            download_videos=True,
            save_metadata=False,
            compress_json=False,
            filename_pattern="{shortcode}_{date_utc}_UTC_{mediaid}",
        )
        L.load_session_from_file(username)
        shortcode = url.split("/")[-2]
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        L.download_post(post, target=Path(session_dir))
    except Exception as e:
        print(f"ERROR: Помилка в Instaloader: {e}")
        raise


# --- ГОЛОВНА ФУНКЦІЯ-ДИСПЕТЧЕР ---
async def download_media(
    url: str, audio_only: bool = False, format_id: Optional[str] = None
) -> Optional[List[str]]:
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


async def get_available_formats(url: str) -> str:
    loop = asyncio.get_event_loop()
    ydl_opts = {"quiet": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(
                None, lambda: ydl.extract_info(url, download=False)
            )
        output_lines = ["*ID* | *Розширення* | *Роздільна здатність* | *Нотатки*\n`"]
        filtered_formats, resolutions_added, audio_added = [], set(), False
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
            if (
                height
                and height not in resolutions_added
                and (
                    f.get("acodec") != "none"
                    or not any(
                        x.get("height") == height and x.get("acodec") != "none"
                        for x in formats
                    )
                )
            ):
                filtered_formats.append(f)
                resolutions_added.add(height)
        for f in filtered_formats[:25]:
            format_id, ext, resolution = (
                f.get("format_id", ""),
                f.get("ext", ""),
                f.get("resolution", "audio only"),
            )
            note = f.get("format_note", "") or resolution
            if f.get("vcodec") == "none":
                note += " (лише аудіо)"
            elif f.get("acodec") == "none":
                note += " (лише відео)"
            output_lines.append(
                f"`{format_id:<4}`| `{ext:<11}`| `{resolution:<20}`| {note}"
            )
        output_lines.append(
            "`\n💡 *Порада:* Для найкращої якості комбінуйте ID: `137+140`."
        )
        return "\n".join(output_lines)
    except Exception as e:
        print(f"Помилка отримання форматів: {e}")
        return "Не вдалося отримати інформацію про формати для цього посилання."
