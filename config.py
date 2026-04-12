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
DB_POOL_MIN = int(os.getenv('DB_POOL_MIN', '2'))
DB_POOL_MAX = int(os.getenv('DB_POOL_MAX', '30'))

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
ENABLE_PLAYER_CACHE = os.getenv('ENABLE_PLAYER_CACHE', 'false').lower() == 'true'

# === Обработка апдейтов ===
BOT_WORKERS = int(os.getenv('BOT_WORKERS', '8'))
BOT_QUEUE_MAX = int(os.getenv('BOT_QUEUE_MAX', '2000'))
BOT_QUEUE_PUT_TIMEOUT = float(os.getenv('BOT_QUEUE_PUT_TIMEOUT', '0.2'))

# === P2P Рынок игроков ===
MARKET_MIN_LEVEL = int(os.getenv('MARKET_MIN_LEVEL', '10'))
MARKET_MAX_LISTINGS_PER_USER = int(os.getenv('MARKET_MAX_LISTINGS_PER_USER', '5'))
MARKET_LISTING_FEE_PCT = float(os.getenv('MARKET_LISTING_FEE_PCT', '1.5'))
MARKET_SALE_FEE_PCT = float(os.getenv('MARKET_SALE_FEE_PCT', '8.0'))
MARKET_LISTING_TTL_HOURS = int(os.getenv('MARKET_LISTING_TTL_HOURS', '48'))
MARKET_PRICE_MIN_MULT_COMMON = float(os.getenv('MARKET_PRICE_MIN_MULT_COMMON', '0.70'))
MARKET_PRICE_MAX_MULT_COMMON = float(os.getenv('MARKET_PRICE_MAX_MULT_COMMON', '1.80'))
MARKET_PRICE_MIN_MULT_RARE = float(os.getenv('MARKET_PRICE_MIN_MULT_RARE', '0.60'))
MARKET_PRICE_MAX_MULT_RARE = float(os.getenv('MARKET_PRICE_MAX_MULT_RARE', '2.20'))
MARKET_PRICE_MIN_MULT_UNIQUE = float(os.getenv('MARKET_PRICE_MIN_MULT_UNIQUE', '0.60'))
MARKET_PRICE_MAX_MULT_UNIQUE = float(os.getenv('MARKET_PRICE_MAX_MULT_UNIQUE', '2.00'))
MARKET_PRICE_MIN_MULT_LEGENDARY = float(os.getenv('MARKET_PRICE_MIN_MULT_LEGENDARY', '0.70'))
MARKET_PRICE_MAX_MULT_LEGENDARY = float(os.getenv('MARKET_PRICE_MAX_MULT_LEGENDARY', '1.60'))

# === Retry для БД ===
DB_MAX_RETRIES = 3
DB_RETRY_DELAY = 1  # секунд

# === Прочее ===
DEBUG = os.getenv('DEBUG', '').lower() == 'true'
