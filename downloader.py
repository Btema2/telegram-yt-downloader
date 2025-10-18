import yt_dlp
import os
import sys
import argparse
from typing import Optional
from PIL import Image
from mutagen.mp3 import MP3
from mutagen.id3 import APIC, error, ID3, TDRC
from io import BytesIO
import glob

def _crop_and_embed_artwork(mp3_path: str, thumbnail_path: str):
    """
    Crops the thumbnail to a 1:1 square from the center and embeds it
    into the MP3 file's metadata.
    """
    try:
        # --- 1. Crop the image ---
        with Image.open(thumbnail_path) as img:
            width, height = img.size
            # Determine the size of the square
            crop_size = min(width, height)
            
            # Calculate coordinates for a center crop
            left = (width - crop_size) / 2
            top = (height - crop_size) / 2
            right = (width + crop_size) / 2
            bottom = (height + crop_size) / 2
            
            # Perform the crop
            cropped_img = img.crop((left, top, right, bottom))

            # --- 2. Embed the cropped image ---
            try:
                audio = MP3(mp3_path, ID3=ID3)
            except error:
                # If no ID3 tag exists, create one
                audio = MP3(mp3_path)
                audio.add_tags()
            
            # Remove any existing artwork
            audio.tags.delall('APIC')
            
            # Create a memory buffer for the image
            img_buffer = BytesIO()
            # Convert to RGB if it has an alpha channel (e.g., PNG, WEBP)
            if cropped_img.mode in ('RGBA', 'LA', 'P'):
                cropped_img = cropped_img.convert('RGB')
            cropped_img.save(img_buffer, format='JPEG', quality=95)
            
            audio.tags.add(
                APIC(
                    encoding=3,         # 3 is for UTF-8
                    mime='image/jpeg',  # Mime type
                    type=3,             # 3 is for the front cover
                    desc='Cover',
                    data=img_buffer.getvalue()
                )
            )
            audio.save()
            print(f"✓ Embedded cropped artwork into {os.path.basename(mp3_path)}")

    except Exception as e:
        print(f"Warning: Could not process or embed artwork: {e}", file=sys.stderr)
    finally:
        # --- 3. Clean up the original thumbnail file ---
        if os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)
            print(f"✓ Cleaned up thumbnail file")


def download_audio_from_ytmusic(url: str) -> Optional[str]:
    """
    Downloads audio from a YouTube Music URL, converts it to MP3,
    and embeds center-cropped 1:1 artwork.
    """
    # --- Configuration for yt-dlp ---
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }, {
            'key': 'FFmpegMetadata',
        }],
        'writethumbnail': True,
        'quiet': True,
        'no_warnings': True,
    }

    try:
        os.makedirs('downloads', exist_ok=True)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print("Downloading...")
            info = ydl.extract_info(url, download=True)
            
            # Get the final MP3 path
            base_path = ydl.prepare_filename(info)
            mp3_path = os.path.splitext(base_path)[0] + '.mp3'
            
            if not os.path.exists(mp3_path):
                raise FileNotFoundError(f"Postprocessing failed to create MP3 file: {mp3_path}")
            
            print(f"✓ Audio downloaded: {os.path.basename(mp3_path)}")
            
            # Find the thumbnail file - it could have various extensions
            base_name = os.path.splitext(base_path)[0]
            possible_extensions = ['jpg', 'jpeg', 'png', 'webp', 'gif']
            thumbnail_path = None
            
            for ext in possible_extensions:
                candidate = f"{base_name}.{ext}"
                if os.path.exists(candidate):
                    thumbnail_path = candidate
                    break
            
            # If not found with exact base name, search in directory
            if not thumbnail_path:
                download_dir = os.path.dirname(base_path)
                title = info.get('title', '')
                for ext in possible_extensions:
                    pattern = os.path.join(download_dir, f"{title}.{ext}")
                    matches = glob.glob(pattern)
                    if matches:
                        thumbnail_path = matches[0]
                        break
            
            if not thumbnail_path or not os.path.exists(thumbnail_path):
                print(f"Warning: Thumbnail file not found", file=sys.stderr)
            else:
                print(f"✓ Thumbnail found: {os.path.basename(thumbnail_path)}")
                # Call our custom function to crop and embed
                _crop_and_embed_artwork(mp3_path, thumbnail_path)
            
            # Fix the date metadata to be just the year
            try:
                audio = MP3(mp3_path, ID3=ID3)
                if audio.tags:
                    # Check if there's a TDRC tag (recording date)
                    if 'TDRC' in audio.tags:
                        date_str = str(audio.tags['TDRC'].text[0])
                        # Extract just the year (first 4 characters)
                        if len(date_str) >= 4:
                            year = date_str[:4]
                            audio.tags['TDRC'] = TDRC(encoding=3, text=year)
                            audio.save()
                            print(f"✓ Fixed date metadata to year only: {year}")
            except Exception as e:
                print(f"Warning: Could not fix date metadata: {e}", file=sys.stderr)
            
            return mp3_path
            
    except yt_dlp.utils.DownloadError as e:
        print(f"Error: Download failed. {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return None

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Download audio from YouTube Music as a tagged MP3 with 1:1 artwork."
    )
    parser.add_argument(
        "url",
        type=str,
        help="The full URL of the YouTube Music track to download."
    )
    args = parser.parse_args()

    print(f"-> Attempting to download audio from: {args.url}")
    result_path = download_audio_from_ytmusic(args.url)

    if result_path:
        print(f"\n[SUCCESS]")
        print(f"File saved to: {result_path}")
    else:
        print("\n[FAILED]")
        print("Could not download the audio. Check error messages above.")