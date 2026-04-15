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

# Лечение в больнице
# 1-е лечение бесплатно, далее: base + (level-1) * multiplier, с потолком cap
HEAL_BASE_PRICE = 100          # базовая цена за лечение (2-е и далее)
HEAL_LEVEL_MULTIPLIER = 50     # добавка за каждый уровень игрока
HEAL_PRICE_CAP = 3000          # максимальная цена лечения

# Прокачка максимального HP через расходники (мягкий кап для баланса)
HP_UPGRADE_PER_LEVEL = int(os.getenv('HP_UPGRADE_PER_LEVEL', '3'))   # +3 HP за 1 апгрейд
HP_UPGRADE_MAX_LEVEL = int(os.getenv('HP_UPGRADE_MAX_LEVEL', '10'))  # максимум +30 HP

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
BASE_ARTIFACT_SLOTS = 3
MAX_ARTIFACT_SLOTS = 10
MIN_LEVEL_FOR_ARTIFACT_SLOT = 25
ARTIFACT_SLOT_COSTS = {
    4:  500,
    5:  750,
    6:  1000,
    7:  1500,
    8:  2000,
    9:  2500,
    10: 3000,
}

# === Кэш ===
CACHE_TTL = 60  # секунд
MAX_CACHED_PLAYERS = 100
ENABLE_PLAYER_CACHE = os.getenv('ENABLE_PLAYER_CACHE', 'false').lower() == 'true'

# === Обработка апдейтов ===
BOT_WORKERS = int(os.getenv('BOT_WORKERS', '8'))
BOT_QUEUE_MAX = int(os.getenv('BOT_QUEUE_MAX', '2000'))
BOT_QUEUE_PUT_TIMEOUT = float(os.getenv('BOT_QUEUE_PUT_TIMEOUT', '0.2'))

# === Выброс (Emission) ===
EMISSION_ENABLED = os.getenv('EMISSION_ENABLED', 'true').lower() == 'true'
EMISSION_MIN_INTERVAL_HOURS = int(os.getenv('EMISSION_MIN_INTERVAL_HOURS', '4'))   # мин интервал между выбросами
EMISSION_MAX_INTERVAL_HOURS = int(os.getenv('EMISSION_MAX_INTERVAL_HOURS', '10'))  # макс интервал
EMISSION_WARNING_MINUTES = int(os.getenv('EMISSION_WARNING_MINUTES', '15'))       # время предупреждения
EMISSION_DURATION_MINUTES = int(os.getenv('EMISSION_DURATION_MINUTES', '30'))     # длительность выброса
EMISSION_AFTERMATH_MINUTES = int(os.getenv('EMISSION_AFTERMATH_MINUTES', '60'))   # время последствий (бонусы)

# Шанс отмены выброса (как в игре S.T.A.L.K.E.R.)
EMISSION_CANCEL_CHANCE = float(os.getenv('EMISSION_CANCEL_CHANCE', '0.15'))  # 15% шанс отмены

# Урон выброса для игроков в Зоне
EMISSION_DAMAGE_PCT_MIN = float(os.getenv('EMISSION_DAMAGE_PCT_MIN', '0.30'))  # 30% HP
EMISSION_DAMAGE_PCT_MAX = float(os.getenv('EMISSION_DAMAGE_PCT_MAX', '0.60'))  # 60% HP
EMISSION_RADIATION = int(os.getenv('EMISSION_RADIATION', '25'))                 # радиация
EMISSION_ITEM_LOSS_CHANCE = float(os.getenv('EMISSION_ITEM_LOSS_CHANCE', '0.15')) # шанс потерять предмет
EMISSION_ITEM_LOSS_MAX = int(os.getenv('EMISSION_ITEM_LOSS_MAX', '2'))           # макс потерянных предметов

# Бонусы после выброса
EMISSION_BONUS_ARTIFACT_CHANCE = float(os.getenv('EMISSION_BONUS_ARTIFACT_CHANCE', '0.50'))  # +50% шанс артефактов
EMISSION_BONUS_RARE_ENEMY_CHANCE = float(os.getenv('EMISSION_BONUS_RARE_ENEMY_CHANCE', '0.20'))  # шанс редкого врага

# "Тихие часы" — когда выброс НЕ запускается (по UTC)
# По умолчанию: 02:00–07:00 UTC (ночное время, когда большинство спит)
EMISSION_QUIET_HOUR_START = int(os.getenv('EMISSION_QUIET_HOUR_START', '2'))
EMISSION_QUIET_HOUR_END = int(os.getenv('EMISSION_QUIET_HOUR_END', '7'))

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

# === NPC Магазины (не P2P) ===
SHOP_ROTATION_HOURS = int(os.getenv('SHOP_ROTATION_HOURS', '1'))
SHOP_FEATURED_DISCOUNT_PCT = int(os.getenv('SHOP_FEATURED_DISCOUNT_PCT', '15'))
SHOP_STOCK_DEFAULT = int(os.getenv('SHOP_STOCK_DEFAULT', '6'))
SHOP_STOCK_RARE = int(os.getenv('SHOP_STOCK_RARE', '4'))
SHOP_STOCK_UNIQUE = int(os.getenv('SHOP_STOCK_UNIQUE', '3'))
SHOP_STOCK_LEGENDARY = int(os.getenv('SHOP_STOCK_LEGENDARY', '2'))
SHOP_BUY_MULT_FLOOR = float(os.getenv('SHOP_BUY_MULT_FLOOR', '0.70'))
SHOP_BUY_MULT_CEIL = float(os.getenv('SHOP_BUY_MULT_CEIL', '1.35'))
SHOP_SELL_MULT_FLOOR = float(os.getenv('SHOP_SELL_MULT_FLOOR', '0.70'))
SHOP_SELL_MULT_CEIL = float(os.getenv('SHOP_SELL_MULT_CEIL', '1.50'))

# === Retry для БД ===
DB_MAX_RETRIES = 3
DB_RETRY_DELAY = 1  # секунд

# === Прочее ===
DEBUG = os.getenv('DEBUG', '').lower() == 'true'
