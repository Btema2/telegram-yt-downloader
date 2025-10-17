# YouTube Music Downloader Script

A simple Python script to download audio from YouTube Music as a tagged MP3 file.
Uses yt-dlp. Created for personal telegram bot

## Prerequisites

- Python 3.8+
- FFmpeg

## Installation

1. Clone the repository:
   ```bash
   git clone <your-repo-url>
   cd <your-repo-name>
   ```

2. Create and activate a virtual environment:
    ``` bash
    python -m venv venv
    source venv/bin/activate
    ```

3. Install dependencies:
    ``` bash
    pip install -r requirements.txt
    ```

## Usage
``` bash
python downloader.py "https://music.youtube.com/watch?v=..."
```

File will be saved to /downloads