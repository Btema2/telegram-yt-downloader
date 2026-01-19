# downloader_lib.py
import asyncio
import glob
import json
import os
import re
import shutil
import time
from io import BytesIO
from pathlib import Path
from typing import Callable, List, Optional

import aiohttp
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


async def _download_tiktok_async(url: str, session_dir: str) -> Optional[List[str]]:
    api_url = "https://www.tikwm.com/api/"
    params = {"url": url, "hd": 1}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, data=params) as resp:
                if resp.status != 200:
                    print(f"TikWM Error: {resp.status}")
                    return None
                data = await resp.json()

        if data.get("code") != 0:
            print(f"TikWM API Error: {data.get('msg')}")
            return None

        data_obj = data.get("data", {})
        images = data_obj.get("images")
        video = data_obj.get("play")

        downloaded_files = []

        async with aiohttp.ClientSession() as session:
            if images:
                for i, img_url in enumerate(images):
                    async with session.get(img_url) as img_resp:
                        if img_resp.status == 200:
                            path = os.path.join(session_dir, f"image_{i}.jpg")
                            with open(path, "wb") as f:
                                f.write(await img_resp.read())
                            downloaded_files.append(path)
            elif video:
                async with session.get(video) as vid_resp:
                    if vid_resp.status == 200:
                        path = os.path.join(session_dir, "video.mp4")
                        with open(path, "wb") as f:
                            f.write(await vid_resp.read())
                        downloaded_files.append(path)

        return downloaded_files if downloaded_files else None

    except Exception as e:
        print(f"TikTok Download Error: {e}")
        return None


async def _download_threads_async(url: str, session_dir: str) -> Optional[List[str]]:
    # Fix potential domain typo (threads.com -> threads.net)
    url = re.sub(r"threads\.com", "threads.net", url, flags=re.IGNORECASE)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Sec-Fetch-Mode": "navigate",
    }

    print(f"Fetching Threads URL: {url}")

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    print(f"Threads page load failed: {response.status}")
                    return None
                text = await response.text()
        except Exception as e:
            print(f"Threads network error: {e}")
            return None

        # Extract unique media URLs
        media_urls = set()

        # Extract shortcode to isolate the specific post
        shortcode_match = re.search(r"/post/([^/?#]+)", url)
        shortcode = shortcode_match.group(1) if shortcode_match else None

        if shortcode:
            # Scoped extraction via data-sjs JSON injection
            # Matches <script ... data-sjs >...
            pattern = re.compile(r"<script[^>]*data-sjs[^>]*>(.*?)</script>", re.DOTALL)
            matches = pattern.findall(text)

            target_node = None
            for json_text in matches:
                try:
                    data = json.loads(json_text)
                    found = _find_node_with_code(data, shortcode)
                    if found:
                        target_node = found
                        break
                except Exception:
                    pass

            if target_node:
                print(f"Extraction: Found precise node for shortcode {shortcode}")

                # Helper to extract best URL
                def extract_best_url(node, key):
                    if key == "video_versions" and node.get(key):
                        return node[key][0]["url"]
                    if key == "image_versions2" and node.get(key):
                        cands = node[key].get("candidates", [])
                        if cands:
                            # Sort by width DESC
                            cands.sort(key=lambda x: x.get("width", 0), reverse=True)
                            return cands[0]["url"]
                    return None

                # 1. Carousel
                if target_node.get("carousel_media"):
                    for item in target_node["carousel_media"]:
                        v_url = extract_best_url(item, "video_versions")
                        if v_url:
                            media_urls.add(v_url)
                        else:
                            i_url = extract_best_url(item, "image_versions2")
                            if i_url:
                                media_urls.add(i_url)

                # 2. Single Video
                v_url = extract_best_url(target_node, "video_versions")
                if v_url:
                    media_urls.add(v_url)
                elif not target_node.get("carousel_media"):
                    # 3. Single Image
                    i_url = extract_best_url(target_node, "image_versions2")
                    if i_url:
                        media_urls.add(i_url)
            else:
                print("DEBUG: Could not locate post payload in page scripts.")
        else:
            print("Could not parse shortcode from URL.")

        if not media_urls:
            print("No media found in Threads scraping (Precise Mode).")
            # DEBUG: Dump text
            with open("debug_threads_fail.html", "w") as f:
                f.write(text)
            return None

        final_paths = []

        # Limit the number of downloads to top 10 to avoid blasting
        download_queue = list(media_urls)[:10]

        for i, m_url in enumerate(download_queue):
            # Determine extension
            ext = ".mp4" if ".mp4" in m_url or "_mp4" in m_url else ".jpg"
            filename = f"threads_{int(time.time())}_{i}{ext}"
            filepath = os.path.join(session_dir, filename)

            try:
                print(f"Downloading media: {m_url}")
                async with session.get(m_url) as resp:
                    if resp.status == 200:
                        with open(filepath, "wb") as f:
                            while True:
                                chunk = await resp.content.read(1024 * 1024)
                                if not chunk:
                                    break
                                f.write(chunk)
                        final_paths.append(filepath)
                    else:
                        print(f"Failed to download media item: {resp.status}")
            except Exception as e:
                print(f"Error downloading specific item: {e}")

        return final_paths if final_paths else None


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

    url_lower = url.lower()

    try:
        # 1. Instagram -> Instaloader
        if "instagram.com" in url_lower:
            if progress_callback:
                await progress_callback("📥 *Завантаження через Instaloader...*")
            return await _download_instagram_post_async(url, session_dir)

        # 2. TikTok -> TikWM
        elif "tiktok.com" in url_lower:
            if progress_callback:
                await progress_callback("📥 *Завантаження TikTok...*")
            return await _download_tiktok_async(url, session_dir)

        # 3. Threads -> Cobalt
        elif "threads.net" in url_lower or "threads.com" in url_lower:
            if progress_callback:
                await progress_callback("📥 *Завантаження Threads...*")
            return await _download_threads_async(url, session_dir)

        # 4. YouTube -> YT-DLP
        elif "youtube.com" in url_lower or "youtu.be" in url_lower:
            return await loop.run_in_executor(
                None,
                lambda: _download_generic_sync(
                    url, session_dir, audio_only, max_height, progress_callback, loop
                ),
            )

        # 5. Інші сервіси (відключено за запитом)
        else:
            if progress_callback:
                await progress_callback(
                    "❌ Цей сервіс зараз не підтримується.\nПрацює тільки YouTube, Instagram, TikTok, Threads."
                )
            # Затримка, щоб користувач встиг прочитати повідомлення перед видаленням
            await asyncio.sleep(5)
            return None

    except Exception as e:
        print(f"Error: {e}")
        if os.path.exists(session_dir):
            shutil.rmtree(session_dir)
        return None


def _find_node_with_code(data, code):
    if isinstance(data, dict):
        if data.get("code") == code:
            return data
        for k, v in data.items():
            res = _find_node_with_code(v, code)
            if res:
                return res
    elif isinstance(data, list):
        for item in data:
            res = _find_node_with_code(item, code)
            if res:
                return res
    return None
