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

# === Настройки игры ===
START_MONEY = 10000
START_HEALTH = 100
MAX_HEALTH = 150
HEAL_COST_PER_HP = 50

# Исследование
RESEARCH_TIME = 30  # секунд
RESEARCH_BONUS_XP = 50

# === Бой ===
BASE_CRIT_CHANCE = 5  # % базовый шанс крита
BASE_DODGE_CHANCE = 10  # % базовое уклонение
CRIT_MULTIPLIER = 2.0  # множитель урона при крите
FLEE_SUCCESS_CHANCE = 50  # % шанс убежать

# === Класс ===
CLASS_CHANGE_COST = 500000
MIN_LEVEL_FOR_CLASS = 10

# === Артефакты ===
MAX_ARTIFACT_SLOTS = 3
ARTIFACT_SLOT_COST = 10000

# === Кэш ===
CACHE_TTL = 60  # секунд
MAX_CACHED_PLAYERS = 100

# === Retry для БД ===
DB_MAX_RETRIES = 3
DB_RETRY_DELAY = 1  # секунд

# === Прочее ===
DEBUG = os.getenv('DEBUG', '').lower() == 'true'

