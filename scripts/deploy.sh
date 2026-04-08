#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR=/opt/stalker_bot
VENV_DIR="$TARGET_DIR/.venv"
SERVICE_FILE=/etc/systemd/system/stalker_bot.service

mkdir -p "$TARGET_DIR"
cd "$TARGET_DIR"

if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f "$TARGET_DIR/.env" ]; then
  echo "WARNING: .env file not found in $TARGET_DIR. Create it from .env.example and set VK_TOKEN and GROUP_ID."
fi

install -m 644 "$TARGET_DIR/scripts/stalker_bot.service" "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable stalker_bot.service
systemctl restart stalker_bot.service
