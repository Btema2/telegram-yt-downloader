#!/bin/bash
set -e

# Кольори для виводу
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Автоматичне налаштування Telegram YT Downloader (Debian/Ubuntu) ===${NC}"

# 1. Запит даних у користувача
echo -e "\n${BLUE}[1/6] Налаштування змінних оточення...${NC}"
if [ ! -f .env ]; then
    read -p "Введіть TELEGRAM_BOT_TOKEN: " bot_token
    read -p "Введіть ваші ALLOWED_USER_IDS (через кому, напр. 12345678,87654321): " user_ids
    read -p "Введіть ваш API_ID (з my.telegram.org): " api_id
    read -p "Введіть ваш API_HASH (з my.telegram.org): " api_hash

    cat > .env <<EOL
TELEGRAM_BOT_TOKEN=${bot_token}
ALLOWED_USER_IDS=${user_ids}
LOCAL_API_URL=http://localhost:8081
API_ID=${api_id}
API_HASH=${api_hash}
EOL
    echo -e "${GREEN}Файл .env створено!${NC}"
else
    echo ".env файл вже існує. Використовую його."
    source .env
    api_id=$API_ID
    api_hash=$API_HASH
fi

# 2. Встановлення системних пакетів
echo -e "\n${BLUE}[2/6] Встановлення залежностей Debian/Ubuntu...${NC}"
SUDO=""
if [ "$EUID" -ne 0 ]; then
    SUDO="sudo"
fi
$SUDO apt-get update
$SUDO apt-get install -y build-essential cmake gperf zlib1g-dev libssl-dev git python3 python3-pip python3-venv ffmpeg

# 3. Завантаження та збірка Telegram Bot API (якщо не зібрано)
echo -e "\n${BLUE}[3/6] Налаштування Telegram Bot API Server...${NC}"
if [ ! -f "telegram-bot-api/build/telegram-bot-api" ]; then
    echo "Компіляція Telegram Bot API. Це може зайняти 5-15 хвилин..."
    if [ ! -d "telegram-bot-api" ]; then
        git clone --recursive https://github.com/tdlib/telegram-bot-api.git
    fi
    cd telegram-bot-api
    rm -rf build && mkdir build && cd build
    cmake -DCMAKE_BUILD_TYPE=Release ..
    make -j$(nproc)
    cd ../..
    echo -e "${GREEN}Telegram Bot API скомпільовано!${NC}"
else
    echo "Сервер вже скомпільовано, пропускаємо."
fi

# 4. Налаштування Python
echo -e "\n${BLUE}[4/6] Налаштування Python віртуального середовища...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo -e "${GREEN}Залежності Python встановлено!${NC}"

# ... решта незмінна ...
# 5. Створення systemd сервісів (user-level)
echo -e "\n${BLUE}[5/6] Створення systemd сервісів для фонової роботи...${NC}"

mkdir -p ~/.config/systemd/user
WORK_DIR=$(pwd)
TG_API_BIN="${WORK_DIR}/telegram-bot-api/build/telegram-bot-api"

# Сервіс сервера Telegram Bot API
cat > ~/.config/systemd/user/telegram-bot-api.service <<EOL
[Unit]
Description=Local Telegram Bot API Server
After=network.target

[Service]
Type=simple
ExecStart=${TG_API_BIN} --local --api-id=${api_id} --api-hash=${api_hash} --dir=${WORK_DIR}/tg-api-workdir
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOL

# Сервіс самого бота
cat > ~/.config/systemd/user/tg-media-bot.service <<EOL
[Unit]
Description=Telegram Media Downloader Bot
After=network.target telegram-bot-api.service

[Service]
Type=simple
WorkingDirectory=${WORK_DIR}
ExecStart=${WORK_DIR}/venv/bin/python3 main_bot.py
Restart=always
RestartSec=5
Environment="PATH=${WORK_DIR}/venv/bin:%E/PATH"

[Install]
WantedBy=default.target
EOL

systemctl --user daemon-reload

# 6. Запуск і додавання в автозавантаження
echo -e "\n${BLUE}[6/6] Запуск сервісів та додавання в автозавантаження...${NC}"
systemctl --user enable --now telegram-bot-api.service
systemctl --user enable --now tg-media-bot.service

# Дозволити сервісам користувача працювати навіть після виходу з ssh
loginctl enable-linger $USER

echo -e "\n${GREEN}======================================================================${NC}"
echo -e "${GREEN}ГОТОВО! Ваш бот та локальний сервер успішно встановлені та запущені.${NC}"
echo -e "======================================================================"
echo -e "🔗 Локальний Telegram API сервер працює за адресою: http://localhost:8081"
echo -e "🔄 Бот підключено до локального сервера (через LOCAL_API_URL у .env)."
echo -e "📦 Тепер ви можете надсилати та приймати файли розміром до 2 ГБ!"
echo -e ""
echo -e "📋 Перевірити статус API сервера: ${BLUE}systemctl --user status telegram-bot-api${NC}"
echo -e "📋 Перевірити статус бота:        ${BLUE}systemctl --user status tg-media-bot${NC}"
echo -e "📋 Подивитись логи бота:          ${BLUE}journalctl --user -u tg-media-bot -f${NC}"
