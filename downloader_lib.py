import yt_dlp
import os
import asyncio

def _get_ydl_opts(progress_hook=None, audio_only=False, format_id=None):
    """Допоміжна функція для генерації конфігурації yt-dlp."""
    video_dir = os.path.join('downloads', 'video')
    audio_dir = os.path.join('downloads', 'audio')
    os.makedirs(video_dir, exist_ok=True)
    os.makedirs(audio_dir, exist_ok=True)

    if audio_only:
        return {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(audio_dir, '%(title)s.%(ext)s'),
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
            'progress_hooks': [progress_hook] if progress_hook else [],
            'quiet': True,
        }
    else:
        if not format_id:
            format_id = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        return {
            'format': format_id,
            'outtmpl': os.path.join(video_dir, '%(title)s.%(ext)s'),
            'progress_hooks': [progress_hook] if progress_hook else [],
            'quiet': True,
        }

async def download_media(url: str, audio_only: bool = False, format_id: str = None) -> str | None:
    """
    Асинхронний завантажувач медіа. Повертає шлях до файлу або None у разі помилки.
    """
    loop = asyncio.get_event_loop()
    ydl_opts = _get_ydl_opts(audio_only=audio_only, format_id=format_id)
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(
                None, lambda: ydl.extract_info(url, download=True)
            )
            filename = ydl.prepare_filename(info)
            if audio_only:
                base, _ = os.path.splitext(filename)
                return f"{base}.mp3"
            return filename
    except Exception as e:
        print(f"Помилка завантаження: {e}")
        return None

# --- ПОВНІСТЮ ОНОВЛЕНА ФУНКЦІЯ ---
async def get_available_formats(url: str) -> str | None:
    """
    Повертає відформатований та ВІДФІЛЬТРОВАНИЙ рядок зі списком доступних форматів,
    щоб уникнути перевищення ліміту повідомлень Telegram.
    """
    loop = asyncio.get_event_loop()
    ydl_opts = {'quiet': True}
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(
                None, lambda: ydl.extract_info(url, download=False)
            )
        
        output_lines = ["*ID* | *Розширення* | *Роздільна здатність* | *Нотатки*\n`"]
        filtered_formats = []
        # Використовуємо set, щоб відстежувати вже додані унікальні роздільні здатності
        resolutions_added = set()
        audio_added = False

        # Сортуємо формати за якістю (висотою кадру), від найкращої до найгіршої
        formats = sorted(info.get('formats', []), key=lambda f: (f.get('height', 0) or 0, f.get('tbr', 0) or 0), reverse=True)
        
        for f in formats:
            # Пропускаємо формати без URL, вони недоступні
            if not f.get('url'):
                continue

            # --- Логіка фільтрації ---
            height = f.get('height')
            
            # Додаємо найкращий аудіо-формат
            if f.get('vcodec') == 'none' and not audio_added:
                filtered_formats.append(f)
                audio_added = True
                continue

            # Додаємо відео-формати з унікальною роздільною здатністю
            if height and height not in resolutions_added:
                # Віддаємо перевагу форматам, де є і відео, і аудіо (прогресивні)
                if f.get('acodec') != 'none':
                    filtered_formats.append(f)
                    resolutions_added.add(height)
                # Або додаємо відео без звуку, якщо прогресивного формату з такою роздільною здатністю немає
                elif f.get('acodec') == 'none' and not any(x.get('height') == height and x.get('acodec') != 'none' for x in formats):
                    filtered_formats.append(f)
                    resolutions_added.add(height)

        # Обмежимо кількість форматів про всяк випадок (наприклад, 15 найкращих)
        if len(filtered_formats) > 15:
            filtered_formats = filtered_formats[:25]

        for f in filtered_formats:
            format_id = f.get('format_id')
            ext = f.get('ext')
            resolution = f.get('resolution', 'audio only')
            note = f.get('format_note', '')
            if not note: note = resolution

            if f.get('vcodec') == 'none': note += " (лише аудіо)"
            elif f.get('acodec') == 'none': note += " (лише відео)"
            
            output_lines.append(f"`{format_id:<4}`| `{ext:<11}`| `{resolution:<20}`| {note}")
        
        # Додаємо корисну підказку
        output_lines.append("`\n💡 *Порада:* Для найкращої якості ви можете комбінувати ID відео та аудіо через `+`, наприклад: `137+140`.")
        
        return "\n".join(output_lines)

    except Exception as e:
        print(f"Помилка отримання форматів: {e}")
        return "Не вдалося отримати інформацію про формати для цього посилання."