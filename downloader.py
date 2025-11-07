import os
import sys
import glob
from typing import Optional
from io import BytesIO

import yt_dlp
from colorama import Fore, Style, init
from PIL import Image
from mutagen.mp3 import MP3
from mutagen.id3 import APIC, error, ID3, TDRC

# Ініціалізація colorama
init(autoreset=True)

# Стилі для красивого виводу
INFO = Fore.CYAN + Style.BRIGHT
SUCCESS = Fore.GREEN + Style.BRIGHT
ERROR = Fore.RED + Style.BRIGHT
PROMPT = Fore.YELLOW + Style.BRIGHT
HEADER = Fore.MAGENTA + Style.BRIGHT


def clear_screen():
    """Очищує екран консолі."""
    os.system("cls" if os.name == "nt" else "clear")


def print_banner():
    """Малює красивий банер."""
    banner = r"""
    
__________ ________ __________ 
\______   \\_____  \\______   \
 |    |  _/ /   |   \|    |  _/
 |    |   \/    |    \    |   \
 |______  /\_______  /______  /
        \/         \/       \/ 
    """
    print(HEADER + banner)
    print(INFO + "    Welcome to the ultimate console media downloader!")
    print("-" * 60)


def _crop_and_embed_artwork(mp3_path: str, thumbnail_path: str):
    """
    Обрізає обкладинку до квадрата 1:1 з центру та вбудовує її
    в метадані MP3 файлу.
    """
    try:
        # Обрізаємо зображення
        with Image.open(thumbnail_path) as img:
            width, height = img.size
            crop_size = min(width, height)
            
            left = (width - crop_size) / 2
            top = (height - crop_size) / 2
            right = (width + crop_size) / 2
            bottom = (height + crop_size) / 2
            
            cropped_img = img.crop((left, top, right, bottom))

            # Вбудовуємо обрізане зображення
            try:
                audio = MP3(mp3_path, ID3=ID3)
            except error:
                audio = MP3(mp3_path)
                audio.add_tags()
            
            audio.tags.delall('APIC')
            
            img_buffer = BytesIO()
            if cropped_img.mode in ('RGBA', 'LA', 'P'):
                cropped_img = cropped_img.convert('RGB')
            cropped_img.save(img_buffer, format='JPEG', quality=95)
            
            audio.tags.add(
                APIC(
                    encoding=3,
                    mime='image/jpeg',
                    type=3,
                    desc='Cover',
                    data=img_buffer.getvalue()
                )
            )
            audio.save()
            print(SUCCESS + f"✓ Embedded cropped artwork into {os.path.basename(mp3_path)}")

    except Exception as e:
        print(ERROR + f"Warning: Could not process or embed artwork: {e}")
    finally:
        if os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)
            print(SUCCESS + "✓ Cleaned up thumbnail file")


def _fix_date_metadata(mp3_path: str):
    """Виправляє дату в метаданих, залишаючи тільки рік."""
    try:
        audio = MP3(mp3_path, ID3=ID3)
        if audio.tags and 'TDRC' in audio.tags:
            date_str = str(audio.tags['TDRC'].text[0])
            if len(date_str) >= 4:
                year = date_str[:4]
                audio.tags['TDRC'] = TDRC(encoding=3, text=year)
                audio.save()
                print(SUCCESS + f"✓ Fixed date metadata to year only: {year}")
    except Exception as e:
        print(ERROR + f"Warning: Could not fix date metadata: {e}")


def get_available_formats(url: str):
    """Отримує та виводить відфільтрований список форматів."""
    print(INFO + "\n🔎 Fetching available formats, please wait...")
    ydl_opts = {"quiet": True}

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        print(SUCCESS + "✅ Formats found! Here are the best options:\n")
        print(PROMPT + f"{'ID':<8} | {'Extension':<10} | {'Resolution':<20} | {'Notes'}")
        print("-" * 70)

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
            elif height and height not in resolutions_added:
                if f.get("acodec") != "none" or not any(
                    x.get("height") == height and x.get("acodec") != "none"
                    for x in formats
                ):
                    filtered_formats.append(f)
                    resolutions_added.add(height)

        for f in filtered_formats[:25]:
            note = f.get("format_note", "") or f.get("resolution", "audio only")
            if f.get("vcodec") == "none":
                note += " (audio only)"
            elif f.get("acodec") == "none":
                note += " (video only)"
            print(
                f"{f.get('format_id', ''):<8} | {f.get('ext', ''):<10} | "
                f"{f.get('resolution', 'audio only'):<20} | {note}"
            )

        print("-" * 70)
        print(INFO + "💡 Tip: For best quality, combine video and audio IDs with '+', e.g., 137+140")

    except Exception as e:
        print(ERROR + f"❌ Failed to get formats: {e}")


def progress_hook(d):
    """Функція-хук для відображення прогресу завантаження."""
    if d["status"] == "downloading":
        total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate")
        downloaded_bytes = d.get("downloaded_bytes")
        speed = d.get("speed")
        eta = d.get("eta")

        if total_bytes and downloaded_bytes is not None:
            percent = downloaded_bytes / total_bytes * 100
            speed_str = f"{speed / 1024 / 1024:.2f} MB/s" if speed else "N/A"
            eta_str = f"{eta}s" if eta is not None else "N/A"

            sys.stdout.write(
                f"\r{INFO}Downloading: {int(percent):>3}% | "
                f"{downloaded_bytes // 1024 // 1024:.1f}/{total_bytes // 1024 // 1024:.1f} MB "
                f"| Speed: {speed_str} | ETA: {eta_str}"
            )
            sys.stdout.flush()
    elif d["status"] == "finished":
        print(SUCCESS + f"\n✅ Download finished!")


def download_ytmusic_with_metadata(url: str) -> Optional[str]:
    """
    Завантажує аудіо з YouTube Music як MP3 з покращеними метаданими
    та обрізаною квадратною обкладинкою.
    """
    audio_dir = os.path.join("downloads", "audio")
    os.makedirs(audio_dir, exist_ok=True)

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(audio_dir, '%(title)s.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }, {
            'key': 'FFmpegMetadata',
        }],
        'writethumbnail': True,
        'progress_hooks': [progress_hook],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(INFO + "\n📥 Downloading audio with metadata...")
            info = ydl.extract_info(url, download=True)
            
            base_path = ydl.prepare_filename(info)
            mp3_path = os.path.splitext(base_path)[0] + '.mp3'
            
            if not os.path.exists(mp3_path):
                raise FileNotFoundError(f"Postprocessing failed to create MP3 file: {mp3_path}")
            
            print(SUCCESS + f"✓ Audio downloaded: {os.path.basename(mp3_path)}")
            
            # Шукаємо файл обкладинки
            base_name = os.path.splitext(base_path)[0]
            possible_extensions = ['jpg', 'jpeg', 'png', 'webp', 'gif']
            thumbnail_path = None
            
            for ext in possible_extensions:
                candidate = f"{base_name}.{ext}"
                if os.path.exists(candidate):
                    thumbnail_path = candidate
                    break
            
            if not thumbnail_path:
                download_dir = os.path.dirname(base_path)
                title = info.get('title', '')
                for ext in possible_extensions:
                    pattern = os.path.join(download_dir, f"{title}.{ext}")
                    matches = glob.glob(pattern)
                    if matches:
                        thumbnail_path = matches[0]
                        break
            
            if thumbnail_path and os.path.exists(thumbnail_path):
                print(SUCCESS + f"✓ Thumbnail found: {os.path.basename(thumbnail_path)}")
                _crop_and_embed_artwork(mp3_path, thumbnail_path)
            else:
                print(ERROR + "Warning: Thumbnail file not found")
            
            _fix_date_metadata(mp3_path)
            
            return mp3_path
            
    except Exception as e:
        print(ERROR + f"❌ An error occurred: {e}")
        return None


def download_media(url: str, audio_only: bool = False, format_id: str = None):
    """Основна функція завантаження відео."""
    video_dir = os.path.join("downloads", "video")
    os.makedirs(video_dir, exist_ok=True)

    if not format_id:
        format_id = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
    
    ydl_opts = {
        'format': format_id,
        'outtmpl': os.path.join(video_dir, '%(title)s.%(ext)s'),
        'progress_hooks': [progress_hook],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        print(ERROR + f"\n❌ An error occurred during download: {e}")


def handle_download_session():
    """Керує сесією завантаження для одного посилання."""
    url = input(PROMPT + "\n🔗 Enter the media URL: ")
    if not url.strip().startswith("http"):
        print(ERROR + "Invalid URL. Please try again.")
        return

    while True:
        print(INFO + "\nWhat would you like to do?")
        print("  [1] Download Video (Best available quality)")
        print("  [2] Download Audio (MP3 with enhanced metadata & artwork)")
        print("  [3] Choose format manually")
        print("  [4] Back to main menu")
        choice = input(PROMPT + ">> ")

        if choice == "1":
            download_media(url, audio_only=False)
            break
        elif choice == "2":
            result = download_ytmusic_with_metadata(url)
            if result:
                print(SUCCESS + f"\n[SUCCESS] File saved to: {result}")
            else:
                print(ERROR + "\n[FAILED] Could not download the audio.")
            break
        elif choice == "3":
            get_available_formats(url)
            format_id = input(PROMPT + "\nEnter the format ID (e.g., 22 or 137+140): ")
            if format_id.strip():
                download_media(url, audio_only=False, format_id=format_id.strip())
            else:
                print(ERROR + "No format ID entered.")
            break
        elif choice == "4":
            return
        else:
            print(ERROR + "Invalid choice, please try again.")


def main():
    """Головний цикл програми."""
    while True:
        clear_screen()
        print_banner()
        print("  [1] Download a new media file")
        print("  [2] Exit")
        main_choice = input(PROMPT + ">> ")

        if main_choice == "1":
            handle_download_session()
            input(INFO + "\nPress Enter to return to the main menu...")
        elif main_choice == "2":
            print(SUCCESS + "Goodbye! 👋")
            break
        else:
            print(ERROR + "Invalid choice, please select 1 or 2.")
            input(INFO + "Press Enter to continue...")


if __name__ == "__main__":
    main()