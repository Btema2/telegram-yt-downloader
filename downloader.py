import yt_dlp
import os
import sys
import argparse
from typing import Optional

def download_audio_from_ytmusic(url: str) -> Optional[str]:
    """
    Downloads audio from a YouTube Music URL, converts it to MP3,
    and embeds metadata including the thumbnail.

    Args:
        url: The full URL of the YouTube Music track.
             Example: 'https://music.youtube.com/watch?v=...'

    Returns:
        The file path to the created MP3 file on success, otherwise None.
    """
    # --- Configuration for yt-dlp ---
    ydl_opts = {
        # 1. Select the best quality audio-only stream.
        'format': 'bestaudio/best',

        # 2. Define the output filename template.
        # Creates files like: downloads/Artist Name - Track Title.mp3
        'outtmpl': 'downloads/%(artist)s - %(title)s.%(ext)s',

        # 3. List of postprocessors to run after download.
        'postprocessors': [{
            # Extracts audio from the downloaded file.
            'key': 'FFmpegExtractAudio',
            # Specifies the target audio format.
            'preferredcodec': 'mp3',
            # Sets the bitrate for the output MP3.
            'preferredquality': '192',
        }, {
            # Embeds the thumbnail into the audio file's metadata.
            'key': 'EmbedThumbnail',
        }, {
            # Writes metadata (like title, artist) to the file.
            'key': 'FFmpegMetadata',
        }],

        # Ensure the thumbnail is downloaded.
        'writethumbnail': True,

        # Suppress yt-dlp's own console output for cleaner integration.
        'quiet': True,
        
        # Prevent printing errors to stdout. We'll catch exceptions instead.
        'no_warnings': True,
    }

    # --- Execution ---
    try:
        # Create the 'downloads' directory if it doesn't exist.
        os.makedirs('downloads', exist_ok=True)

        # Create a YoutubeDL instance and run the download.
        # The 'with' statement ensures resources are properly cleaned up.
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Start the download and post-processing.
            # This returns a dictionary with video information.
            info = ydl.extract_info(url, download=True)

            # Determine the final path of the MP3 file.
            # `prepare_filename` gives the path based on the template,
            # but before the extension is changed by the postprocessor.
            base_path = ydl.prepare_filename(info)
            # We replace the original extension (e.g., .webm) with .mp3.
            final_path = os.path.splitext(base_path)[0] + '.mp3'
            
            # Verify that the final MP3 file was actually created.
            if not os.path.exists(final_path):
                raise FileNotFoundError(f"Postprocessing failed to create MP3 file: {final_path}")

            return final_path

    except yt_dlp.utils.DownloadError as e:
        # Handle specific download errors (e.g., video not available).
        print(f"Error: Download failed. {e}", file=sys.stderr)
        return None
    except Exception as e:
        # Handle other unexpected errors.
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        return None


# --- Test Block ---
# This code runs only when the script is executed directly (e.g., `python downloader.py`)
if __name__ == '__main__':
    # 1. Initialize the argument parser.
    parser = argparse.ArgumentParser(
        description="Download audio from a YouTube Music URL as a tagged MP3."
    )

    # 2. Define a required positional argument named 'url'.
    parser.add_argument(
        "url",
        type=str,
        help="The full URL of the YouTube Music track to download."
    )

    # 3. Parse the arguments provided by the user.
    args = parser.parse_args()

    # 4. Use the provided URL.
    print(f"-> Attempting to download audio from: {args.url}")
    result_path = download_audio_from_ytmusic(args.url)

    # 5. Report the result.
    if result_path:
        print(f"\n[SUCCESS]")
        print(f"File saved to: {result_path}")
    else:
        print("\n[FAILED]")
        print("Could not download the audio. Check error messages above.")