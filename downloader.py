import os
import sys

import yt_dlp
from colorama import Fore, Style, init

# Ініціалізуємо colorama (autoreset=True означає, що кожен print повертатиметься до стандартного кольору)
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


def get_available_formats(url: str):
    """Отримує та виводить відфільтрований список форматів."""
    print(INFO + "\n🔎 Fetching available formats, please wait...")
    ydl_opts = {"quiet": True}

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        print(SUCCESS + "✅ Formats found! Here are the best options:\n")
        print(
            PROMPT + f"{'ID':<8} | {'Extension':<10} | {'Resolution':<20} | {'Notes'}"
        )
        print("-" * 70)

        # Логіка фільтрації, адаптована з бота
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

        for f in filtered_formats[:25]:  # Обмежимо для читабельності
            note = f.get("format_note", "") or f.get("resolution", "audio only")
            if f.get("vcodec") == "none":
                note += " (audio only)"
            elif f.get("acodec") == "none":
                note += " (video only)"
            print(
                f"{f.get('format_id', ''):<8} | {f.get('ext', ''):<10} | {f.get('resolution', 'audio only'):<20} | {note}"
            )

        print("-" * 70)
        print(
            INFO
            + "💡 Tip: For best quality, combine video and audio IDs with '+', e.g., 137+140"
        )

    except Exception as e:
        print(ERROR + f"❌ Failed to get formats: {e}")


def progress_hook(d):
    """Функція-хук для відображення прогресу завантаження."""
    if d["status"] == "downloading":
        # Отримуємо дані про прогрес
        total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate")
        downloaded_bytes = d.get("downloaded_bytes")
        speed = d.get("speed")
        eta = d.get("eta")

        if total_bytes and downloaded_bytes is not None:
            percent = downloaded_bytes / total_bytes * 100
            # Форматуємо швидкість та час
            speed_str = f"{speed / 1024 / 1024:.2f} MB/s" if speed else "N/A"
            eta_str = f"{eta}s" if eta is not None else "N/A"

            # Виводимо прогрес-бар в одному рядку
            sys.stdout.write(
                f"\r{INFO}Downloading: {int(percent):>3}% | "
                f"{downloaded_bytes // 1024 // 1024:.1f}/{total_bytes // 1024 // 1024:.1f} MB "
                f"| Speed: {speed_str} | ETA: {eta_str}"
            )
            sys.stdout.flush()
    elif d["status"] == "finished":
        print(SUCCESS + f"\n✅ Download finished! File saved as: {d['filename']}")


def download_media(url: str, audio_only: bool = False, format_id: str = None):
    """Основна функція завантаження."""
    # Створюємо папки, якщо їх немає
    video_dir = os.path.join("downloads", "video")
    audio_dir = os.path.join("downloads", "audio")
    os.makedirs(video_dir, exist_ok=True)
    os.makedirs(audio_dir, exist_ok=True)

    ydl_opts = {
        "progress_hooks": [progress_hook],
    }

    if audio_only:
        ydl_opts.update(
            {
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
        )
    else:
        if not format_id:
            format_id = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        ydl_opts.update(
            {
                "format": format_id,
                "outtmpl": os.path.join(video_dir, "%(title)s.%(ext)s"),
            }
        )

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
        print("  [2] Download Audio Only (MP3)")
        print("  [3] Choose format manually")
        print("  [4] Back to main menu")
        choice = input(PROMPT + ">> ")

        if choice == "1":
            download_media(url, audio_only=False)
            break
        elif choice == "2":
            download_media(url, audio_only=True)
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
            print(SUCCESS + "Goodbye!")
            break
        else:
            print(ERROR + "Invalid choice, please select 1 or 2.")
            input(INFO + "Press Enter to continue...")


if __name__ == "__main__":
    main()
