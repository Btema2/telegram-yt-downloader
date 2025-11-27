# downloader_lib.py
import asyncio
import glob
import os
import re
import shutil
import time
from io import BytesIO
from pathlib import Path
from typing import Callable, List, Optional

import instaloader
import yt_dlp
from mutagen.id3 import APIC, ID3, TDRC, TIT2, TPE1, error
from mutagen.mp3 import MP3
from PIL import Image


# --- КЛАС ДЛЯ ПРОГРЕС-БАРУ (Тільки для yt-dlp) ---
class ProgressHook:
    def __init__(self, callback: Callable, loop: asyncio.AbstractEventLoop):
        self.callback = callback
        self.loop = loop
        self.last_update = 0
        self.update_interval = 3

    def __call__(self, d):
        if d["status"] == "downloading":
            now = time.time()
            if now - self.last_update > self.update_interval or d.get(
                "total_bytes"
            ) == d.get("downloaded_bytes"):
                self.last_update = now
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)
                if total > 0:
                    percent = downloaded / total * 100
                    bar_len = 15
                    filled_len = int(bar_len * percent / 100)
                    bar = "█" * filled_len + "░" * (bar_len - filled_len)
                    total_mb = total / 1024 / 1024
                    curr_mb = downloaded / 1024 / 1024
                    speed = d.get("speed", 0) or 0
                    speed_mb = speed / 1024 / 1024
                    text = (
                        f"📥 *Завантаження...*\n"
                        f"`[{bar}] {percent:.1f}%`\n"
                        f"💾 `{curr_mb:.1f}MB / {total_mb:.1f}MB`\n"
                        f"🚀 `{speed_mb:.1f} MB/s`"
                    )
                    asyncio.run_coroutine_threadsafe(self.callback(text), self.loop)
        elif d["status"] == "finished":
            asyncio.run_coroutine_threadsafe(
                self.callback("⚙️ *Обробка медіа...*"), self.loop
            )


# --- ОБРОБКА МЕТАДАНИХ ---
def _crop_and_embed_artwork(mp3_path: str, thumbnail_path: str):
    try:
        with Image.open(thumbnail_path) as img:
            width, height = img.size
            crop_size = min(width, height)
            left, top, right, bottom = (
                (width - crop_size) / 2,
                (height - crop_size) / 2,
                (width + crop_size) / 2,
                (height + crop_size) / 2,
            )
            cropped_img = img.crop((left, top, right, bottom))
            if cropped_img.mode in ("RGBA", "LA", "P"):
                cropped_img = cropped_img.convert("RGB")
            img_buffer = BytesIO()
            cropped_img.save(img_buffer, format="JPEG", quality=95)
            try:
                audio = MP3(mp3_path, ID3=ID3)
            except error:
                audio = MP3(mp3_path)
                audio.add_tags()
            audio.tags.delall("APIC")
            audio.tags.add(
                APIC(
                    encoding=3,
                    mime="image/jpeg",
                    type=3,
                    desc="Cover",
                    data=img_buffer.getvalue(),
                )
            )

            # Базові теги
            if not audio.tags.get("TIT2"):
                audio.tags.add(
                    TIT2(encoding=3, text=os.path.basename(mp3_path).split(".")[0])
                )
            if not audio.tags.get("TPE1"):
                audio.tags.add(TPE1(encoding=3, text="Unknown Artist"))

            audio.save()
            print(f"✓ Embedded artwork: {mp3_path}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)


def _fix_metadata(mp3_path: str, title: str = None, uploader: str = None):
    try:
        audio = MP3(mp3_path, ID3=ID3)
        if uploader and not audio.tags.get("TPE1"):
            audio.tags.add(TPE1(encoding=3, text=uploader))
        if title and not audio.tags.get("TIT2"):
            audio.tags.add(TIT2(encoding=3, text=title))
        if audio.tags and "TDRC" in audio.tags:
            date_str = str(audio.tags["TDRC"].text[0])
            if len(date_str) >= 4:
                audio.tags["TDRC"] = TDRC(encoding=3, text=date_str[:4])
        audio.save()
    except Exception as e:
        print(f"Error: {e}")


# --- YT-DLP (ДЛЯ ВСЬОГО, КРІМ INSTAGRAM) ---
def _download_generic_sync(
    url: str,
    session_dir: str,
    audio_only: bool,
    max_height: Optional[int] = None,
    progress_callback: Optional[Callable] = None,
    loop: Optional[asyncio.AbstractEventLoop] = None,
) -> Optional[List[str]]:
    ydl_opts = {
        "outtmpl": os.path.join(session_dir, "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "writethumbnail": True,
        "updatetime": False,
        "allow_playlist": False,
    }

    if progress_callback and loop:
        ydl_opts["progress_hooks"] = [ProgressHook(progress_callback, loop)]

    if audio_only:
        ydl_opts.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    },
                    {"key": "FFmpegMetadata", "add_metadata": True},
                ],
            }
        )
    else:
        # Логіка якості відео
        if max_height:
            format_str = f"bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]/best"
        else:
            format_str = "bestvideo+bestaudio/best"

        ydl_opts.update(
            {
                "format": format_str,
                "merge_output_format": "mp4",
                "postprocessors": [{"key": "FFmpegMetadata", "add_metadata": True}],
            }
        )

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

            if audio_only:
                base_path = ydl.prepare_filename(info)
                mp3_path = os.path.splitext(base_path)[0] + ".mp3"
                if not os.path.exists(mp3_path):
                    found = glob.glob(os.path.join(session_dir, "*.mp3"))
                    if found:
                        mp3_path = found[0]

                if os.path.exists(mp3_path):
                    # Пошук обкладинки
                    thumbnail_path = None
                    for f in glob.glob(os.path.join(session_dir, "*")):
                        if f.endswith((".jpg", ".webp", ".png")) and f != mp3_path:
                            thumbnail_path = f
                            break
                    if thumbnail_path:
                        _crop_and_embed_artwork(mp3_path, thumbnail_path)
                    _fix_metadata(
                        mp3_path, title=info.get("title"), uploader=info.get("uploader")
                    )
                    return [mp3_path]

            allowed = [".mp4", ".mkv", ".mov", ".webm", ".mp3"]
            return [
                os.path.join(session_dir, f)
                for f in os.listdir(session_dir)
                if os.path.splitext(f)[1].lower() in allowed
            ]
    except Exception as e:
        print(f"Error: {e}")
        return None


# --- INSTALOADER (ВАША ОРИГІНАЛЬНА ФУНКЦІЯ) ---
def _download_instagram_post_sync(url: str, session_dir: str):
    print("DEBUG: Instaloader starting...")
    username = os.getenv("INSTAGRAM_USERNAME")
    if not username:
        raise ValueError("INSTAGRAM_USERNAME не встановлено у .env")
    try:
        L = instaloader.Instaloader(
            download_pictures=True,
            download_videos=True,
            save_metadata=False,
            compress_json=False,
            # Ваша оригінальна схема імен
            filename_pattern="{shortcode}_{date_utc}_UTC_{mediaid}",
            # Додаємо User-Agent, щоб Інста менше блокувала
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        )
        try:
            L.load_session_from_file(username)
            print("DEBUG: Session loaded successfully")
        except FileNotFoundError:
            print("DEBUG: Session file not found, trying without session")
        except Exception as e:
            print(f"DEBUG: Session load error: {e}")

        # Витягуємо shortcode
        match = re.search(r"instagram\.com/(?:p|reel|tv)/([^/?#&]+)", url)
        if match:
            shortcode = match.group(1)
        else:
            # Fallback
            shortcode = url.split("/")[-2]

        print(f"DEBUG: Downloading shortcode {shortcode}")
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        L.download_post(post, target=Path(session_dir))
        print("DEBUG: Instaloader finished")
    except Exception as e:
        print(f"Error: {e}")
        raise


async def _download_instagram_post_async(
    url: str, session_dir: str
) -> Optional[List[str]]:
    loop = asyncio.get_event_loop()
    try:
        # Виконуємо синхронну функцію в окремому потоці
        await loop.run_in_executor(
            None, lambda: _download_instagram_post_sync(url, session_dir)
        )
        allowed_extensions = [".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov"]
        files = [
            os.path.join(session_dir, f)
            for f in os.listdir(session_dir)
            if os.path.splitext(f)[1].lower() in allowed_extensions
        ]
        return files
    except Exception as e:
        print(f"Error: {e}")
        return None


# --- MAIN ENTRY ---
async def download_media(
    url: str,
    audio_only: bool = False,
    max_height: Optional[int] = None,
    progress_callback: Optional[Callable] = None,
) -> Optional[List[str]]:
    base_dir = "downloads"
    session_dir = os.path.join(base_dir, str(time.time_ns()))
    os.makedirs(session_dir, exist_ok=True)
    loop = asyncio.get_event_loop()

    try:
        # 1. Instagram -> Instaloader (Тільки він!)
        if "instagram.com" in url:
            if progress_callback:
                await progress_callback("📥 *Завантаження через Instaloader...*")
            return await _download_instagram_post_async(url, session_dir)

        # 2. Все інше -> YT-DLP
        else:
            return await loop.run_in_executor(
                None,
                lambda: _download_generic_sync(
                    url, session_dir, audio_only, max_height, progress_callback, loop
                ),
            )

    except Exception as e:
        print(f"Error: {e}")
        if os.path.exists(session_dir):
            shutil.rmtree(session_dir)
        return None
