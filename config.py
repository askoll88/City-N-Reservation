import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем .env из директории с config.py
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

# VK API
VK_TOKEN = os.getenv('VK_TOKEN')
GROUP_ID = os.getenv('GROUP_ID')

# Проверка обязательных переменных
if not VK_TOKEN or not GROUP_ID:
    raise ValueError(
        "TOKEN or GROUP_ID not found in config.py. "
        "Please check your .env file and ensure VK_TOKEN and GROUP_ID are set."
    )

# PostgreSQL
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'stalker_game')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')

