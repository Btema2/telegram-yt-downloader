# 📥 Universal Media Bot (Telegram)

A powerful bot for downloading media from **YouTube, Instagram, TikTok, SoundCloud, Spotify**, and other platforms.

🚀 **Main Feature:** Supports downloading and sending files up to **2000 MB** (even on mobile!).

---

## 🔥 Features
*   📹 **YouTube:** Quality selection (1080p, 720p...), progress bar, ad-free downloads.
*   🎧 **Music:** Automatic MP3 downloads from YouTube Music, SoundCloud, Spotify with **covers and metadata**.
*   📸 **Instagram:** Download Reels, Stories, and carousel posts using a real account.
*   💽 **Local API Server:** Uses a local Telegram server to bypass the standard 50 MB upload limit.
*   📊 **Progress Bar:** Live viewing of the download progress.
*   🔐 **Private Access:** The bot works only for allowed users.

---

## 🧠 Installation on Debian/Ubuntu (Server/PC) - Automated

To make the installation as easy as possible on Debian/Ubuntu with a `fish` or `bash` shell, an automated setup script is provided. It will install all dependencies, compile the Telegram Bot API server, set up the Python environment, and configure `systemd` user services to keep the bot and server running in the background automatically, even after a reboot.

### Steps:
1. Clone the repository to your Debian/Ubuntu machine:
   ```bash
   git clone https://github.com/Btema2/telegram-yt-downloader.git
   cd telegram-yt-downloader
   ```
2. Make the script executable and run it:
   ```bash
   chmod +x auto_deploy.sh
   ./auto_deploy.sh
   ```
3. Follow the on-screen prompts to enter your Bot Token, API ID, API Hash (from my.telegram.org), and Allowed User IDs. 

The script will handle everything else, including starting the services in the background.

---

## 💻 Manual Installation on Linux (Ubuntu / General)

### 1. System Requirements
Install Python, FFmpeg, and Git.
*   **Ubuntu/Debian:** `sudo apt install python3 python3-venv ffmpeg git build-essential cmake gperf zlib1g-dev libssl-dev`

### 2. Install Telegram Bot API (C++ Server)
The local server is required for the 2000 MB limit.
*   **Ubuntu/Debian:** [See official compilation instructions](https://github.com/tdlib/telegram-bot-api) or compile from source.

### 3. Install the Bot
```bash
git clone https://github.com/Btema2/telegram-yt-downloader.git
cd telegram-yt-downloader

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 📱 Installation on Android (Termux)
**Note:** To get the **2000 MB** limit on your phone, we will compile the Telegram server manually. This takes 30-60 minutes and requires ~2 GB of space.

### Step 1: Termux Preparation
Download Termux from [F-Droid](https://f-droid.org/en/packages/com.termux/).
Open the terminal and enter:
```bash
termux-setup-storage
pkg update && pkg upgrade -y
# Build tools for the server and bot runtime
pkg install git cmake clang make zlib openssl gperf python ffmpeg libjpeg-turbo -y
```

### Step 2: Compile the Server (Telegram Bot API)
This is the longest step. Do not minimize the app during the process.
```bash
# 1. Download server code
git clone --recursive https://github.com/tdlib/telegram-bot-api.git
cd telegram-bot-api

# 2. Create build folder
mkdir build
cd build

# 3. Configure
cmake -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=$PREFIX ..

# 4. RUN BUILD (This takes time!)
cmake --build . --target install -j4
```
*If the phone heats up or freezes, replace `-j4` with `-j2`.*

Verify success with: `telegram-bot-api --version`

### Step 3: Install the Bot
Open a **new session** (swipe right -> New Session) or return to the home folder:
```bash
cd ~
git clone https://github.com/Btema2/telegram-yt-downloader.git
cd telegram-yt-downloader

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## ⚙️ Configuration (.env)

If you are not using `auto_deploy.sh`, create a `.env` file manually:
```bash
cp .env.example .env
nano .env
```

Fill it out (get `API_ID` and `API_HASH` from [my.telegram.org](https://my.telegram.org)):

```ini
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
ALLOWED_USER_IDS=12345678,87654321
INSTAGRAM_USERNAME=YOUR_USERNAME

# --- SETUP FOR 2000 MB (Linux & Termux) ---
LOCAL_API_URL=http://localhost:8081
SHARED_FOLDER=downloads

# Get these details at my.telegram.org (App development tools) 
TELEGRAM_API_ID=1234567
TELEGRAM_API_HASH=abcdef1234567890...
```

---

## 🔑 Login to Instagram (Important!)
To download from Instagram, you need to create a session file. Enter the command (on PC or Termux):

```bash
instaloader --login=YOUR_USERNAME
```
Enter your password. This will create a session file that the bot will pick up automatically.

---

## 🚀 How to Run Manually (Linux & Termux)

If you didn't use `auto_deploy.sh`, you need to keep **two processes** running simultaneously. Use two terminal tabs.

### Tab 1: Local Server (C++)
Handles sending large files.
```bash
telegram-bot-api --api-id=YOUR_API_ID --api-hash=YOUR_API_HASH --local
```

### Tab 2: Bot (Python)
Handles logic and downloading.
```bash
cd telegram-yt-downloader
source venv/bin/activate
python main_bot.py
```

---

## 🛠 Commands
*   `/start` — Check if the bot is working.
*   `/clean` — Clear the `downloads` folder from garbage (available only to allowed users).
*   **Links** — Just send a link to TikTok, YouTube, Instagram, etc.

## 📜 License
```MIT License.

Copyright (c) 2025 Btema2

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```