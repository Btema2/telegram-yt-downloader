# 📥 Універсальний Медіа Бот (Telegram)

Потужний бот для завантаження медіа з **YouTube, Instagram, TikTok, SoundCloud, Spotify** та інших платформ.

🚀 **Головна фішка:** Підтримка завантаження та надсилання файлів розміром до **2000 МБ** (навіть на телефоні!).

---

## 🔥 Можливості
*   📹 **YouTube:** Вибір якості (1080p, 720p...), прогрес-бар, завантаження без реклами.
*   🎧 **Музика:** Автоматичне завантаження MP3 з YouTube Music, SoundCloud, Spotify з **обкладинками та метаданими**.
*   📸 **Instagram:** Завантаження Reels, Stories, Постів (каруселі) через реальний акаунт.
*   💾 **Local API Server:** Використання локального сервера Telegram для обходу ліміту в 50 МБ.
*   📊 **Прогрес-бар:** Живе відображення процесу завантаження.
*   🔐 **Приватний доступ:** Бот працює тільки для обраних користувачів.

---

## 🐧 Встановлення на Linux (PC / VPS)

### 1. Системні вимоги
Встановіть Python, FFmpeg та Git.
*   **Arch Linux:** `sudo pacman -S python ffmpeg git base-devel`
*   **Ubuntu:** `sudo apt install python3 python3-venv ffmpeg git build-essential`

### 2. Встановлення Telegram Bot API (C++ Server)
Для ліміту 2000 МБ потрібен локальний сервер.
*   **Arch Linux (AUR):** `yay -S telegram-bot-api`
*   **Ubuntu/Debian:** [Див. офіційну інструкцію з компіляції](https://github.com/tdlib/telegram-bot-api).

### 3. Встановлення бота
```bash
git clone https://github.com/Btema2/telegram-yt-downloader.git
cd telegram-yt-downloader

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 📱 Встановлення на Android (Termux)
**Увага:** Щоб отримати ліміт **2000 МБ** на телефоні, ми скомпілюємо сервер Telegram вручну. Це займе 30-60 хвилин і потребує ~2 ГБ місця.

### Крок 1: Підготовка Termux
Завантажте Termux з [F-Droid](https://f-droid.org/en/packages/com.termux/).
Відкрийте термінал і введіть:
```bash
termux-setup-storage
pkg update && pkg upgrade -y
# Інструменти для збірки сервера та роботи бота
pkg install git cmake clang make zlib openssl gperf python ffmpeg libjpeg-turbo -y
```

### Крок 2: Компіляція сервера (Telegram Bot API)
Це найдовший етап. Не звертайте додаток під час процесу.
```bash
# 1. Скачуємо код сервера
git clone --recursive https://github.com/tdlib/telegram-bot-api.git
cd telegram-bot-api

# 2. Створюємо папку для збірки
mkdir build
cd build

# 3. Налаштовуємо (Конфігурація)
cmake -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=$PREFIX ..

# 4. ЗАПУСК ЗБІРКИ (Це займе час!)
cmake --build . --target install -j4
```
*Якщо телефон гріється або висне, замініть `-j4` на `-j2`.*

Перевірте успіх командою: `telegram-bot-api --version`

### Крок 3: Встановлення бота
Відкрийте **нову сесію** (свайп вправо -> New Session) або поверніться в домашню папку:
```bash
cd ~
git clone https://github.com/Btema2/telegram-yt-downloader.git
cd telegram-yt-downloader

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## ⚙️ Налаштування (.env)

Створіть файл `.env`:
```bash
cp .env.example .env
nano .env
```

Заповніть його (дані для `API_ID` та `API_HASH` візьміть на [my.telegram.org](https://my.telegram.org)):

```ini
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
ALLOWED_USER_IDS=12345678,87654321
INSTAGRAM_USERNAME=YOUR_USERNAME

# --- НАЛАШТУВАННЯ ДЛЯ 2000 МБ (Linux & Termux) ---
LOCAL_API_URL=http://localhost:8081
SHARED_FOLDER=downloads

# Отримайте ці дані на my.telegram.org (App development tools)
TELEGRAM_API_ID=1234567
TELEGRAM_API_HASH=abcdef1234567890...
```

---

## 🔑 Вхід в Instagram (Важливо!)
Щоб завантажувати з Instagram, потрібно створити файл сесії. Введіть команду (на ПК або в Termux):

```bash
instaloader --login=ВАШ_ЛОГІН
```
Введіть пароль. Це створить файл сесії, який бот підхопить автоматично.

---

## 🚀 Як запускати (Linux & Termux)

Вам потрібно тримати запущеними **два процеси** одночасно. Використовуйте дві вкладки терміналу.

### Вкладка 1: Локальний сервер (C++)
Він відповідає за надсилання великих файлів.
```bash
telegram-bot-api --api-id=ВАШ_API_ID --api-hash=ВАШ_API_HASH --local
```

### Вкладка 2: Бот (Python)
Він обробляє логіку та завантаження.
```bash
cd telegram-yt-downloader
source venv/bin/activate
python main_bot.py
```

---

## 🛠 Команди
*   `/start` — Перевірка роботи.
*   `/clean` — Очистити папку `downloads` від сміття (доступно тільки дозволеним користувачам).
*   **Посилання** — Просто надішліть лінк на TikTok, YouTube, Instagram тощо.

## 📜 Ліцензія
```MIT License.
MIT License.

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