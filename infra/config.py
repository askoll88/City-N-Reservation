import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем .env из корня проекта (../.env), с fallback на текущую рабочую директорию.
project_root_env = Path(__file__).resolve().parent.parent / '.env'
cwd_env = Path.cwd() / '.env'
load_dotenv(project_root_env if project_root_env.exists() else cwd_env)

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
START_MONEY = 2500
START_HEALTH = 100
MAX_HEALTH = 150
HEAL_COST_PER_HP = 50

# Лечение в больнице
# 1-е лечение бесплатно, далее цена зависит от фактической помощи, уровня и ранга.
# Итог ограничен персональным потолком: низкие ранги не платят взрослую цену.
HEAL_BASE_PRICE = 80               # базовая плата за приём (2-е и далее)
HEAL_HP_PRICE = 6                  # цена за 1 восстановленный HP
HEAL_ENERGY_PRICE = 2              # цена за 1 восстановленную энергию
HEAL_LEVEL_FEE = 8                 # мягкая добавка за уровень
HEAL_RANK_FEE = 25                 # мягкая добавка за тир ранга
HEAL_RANK_CAP_BASE = 350           # потолок для 1 ранга
HEAL_RANK_CAP_STEP = 300           # рост потолка за каждый следующий ранг
HEAL_RANK_CAP_LEVEL_STEP = 40      # рост потолка внутри текущего ранга по уровню
HEAL_PRICE_CAP = 25000             # абсолютный технический максимум лечения

# Максимальное HP персонажа: derived stat от уровня и выносливости.
# Старт при level=1/stamina=4 остаётся 100 HP, дальше рост идёт без расходников.
PLAYER_HP_BASE = int(os.getenv('PLAYER_HP_BASE', '56'))
PLAYER_HP_PER_LEVEL = int(os.getenv('PLAYER_HP_PER_LEVEL', '4'))
PLAYER_HP_PER_STAMINA = int(os.getenv('PLAYER_HP_PER_STAMINA', '10'))

# Исследование
RESEARCH_TIME = 30  # секунд
RESEARCH_BONUS_XP = 50

# Пассивный реген энергии в убежище
SHELTER_PASSIVE_ENERGY_REGEN_ENABLED = os.getenv('SHELTER_PASSIVE_ENERGY_REGEN_ENABLED', 'true').lower() == 'true'
SHELTER_PASSIVE_ENERGY_REGEN_INTERVAL_SEC = int(os.getenv('SHELTER_PASSIVE_ENERGY_REGEN_INTERVAL_SEC', '300'))  # +энергия раз в N сек
SHELTER_PASSIVE_ENERGY_REGEN_AMOUNT = int(os.getenv('SHELTER_PASSIVE_ENERGY_REGEN_AMOUNT', '1'))  # сколько энергии за тик
SHELTER_STORAGE_CAPACITY = int(os.getenv('SHELTER_STORAGE_CAPACITY', '80'))  # слоты шкафа (сумма quantity)

# Прогрессия уровней
MAX_PLAYER_LEVEL = int(os.getenv('MAX_PLAYER_LEVEL', '297'))
XP_POST20_BASE_DELTA = int(os.getenv('XP_POST20_BASE_DELTA', '3600'))
XP_POST20_LINEAR_GROWTH = int(os.getenv('XP_POST20_LINEAR_GROWTH', '180'))
XP_POST20_QUADRATIC_GROWTH = int(os.getenv('XP_POST20_QUADRATIC_GROWTH', '2200'))

# === Бой ===
BASE_CRIT_CHANCE = 5  # % базовый шанс крита
BASE_DODGE_CHANCE = 10  # % базовое уклонение
CRIT_MULTIPLIER = 2.0  # множитель урона при крите
FLEE_SUCCESS_CHANCE = 50  # % шанс убежать
STRENGTH_DAMAGE_PER_LEVEL = int(os.getenv('STRENGTH_DAMAGE_PER_LEVEL', '2'))  # +урон за 1 уровень силы

# === Класс ===
CLASS_CHANGE_COST = 500000
MIN_LEVEL_FOR_CLASS = 10

# === Артефакты ===
BASE_ARTIFACT_SLOTS = 3
MAX_ARTIFACT_SLOTS = 10
ARTIFACT_SLOT_REQUIREMENTS = {
    4: {"level": 20, "cost": 12000},
    5: {"level": 35, "cost": 22000},
    6: {"level": 50, "cost": 36000},
    7: {"level": 65, "cost": 56000},
    8: {"level": 80, "cost": 84000},
    9: {"level": 100, "cost": 120000},
    10: {"level": 120, "cost": 170000},
}
MIN_LEVEL_FOR_ARTIFACT_SLOT = min(v["level"] for v in ARTIFACT_SLOT_REQUIREMENTS.values())
ARTIFACT_SLOT_COSTS = {slot: int(req["cost"]) for slot, req in ARTIFACT_SLOT_REQUIREMENTS.items()}

# === Мешочки для гильз ===
# Линейная прогрессия у Военного на КПП: от стартового до эндгейм-варианта к 120 уровню.
SHELLS_BAG_REQUIREMENTS = {
    "Маленький мешочек": {"level": 8, "cost": 6000},
    "Средний мешочек": {"level": 24, "cost": 18000},
    "Большой мешочек": {"level": 50, "cost": 42000},
    "Профессиональный мешочек": {"level": 85, "cost": 90000},
    "Легендарный мешочек": {"level": 120, "cost": 180000},
}
SHELLS_BAG_ORDER = tuple(SHELLS_BAG_REQUIREMENTS.keys())
MIN_LEVEL_FOR_SHELLS_BAG = min(v["level"] for v in SHELLS_BAG_REQUIREMENTS.values())

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
EMISSION_MIN_INTERVAL_HOURS = int(os.getenv('EMISSION_MIN_INTERVAL_HOURS', '48'))  # 2 дня
EMISSION_MAX_INTERVAL_HOURS = int(os.getenv('EMISSION_MAX_INTERVAL_HOURS', '96'))  # 4 дня
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
EMISSION_BONUS_ARTIFACT_CHANCE = float(os.getenv('EMISSION_BONUS_ARTIFACT_CHANCE', '1.00'))  # +100% шанс артефактов
EMISSION_BONUS_RARE_ENEMY_CHANCE = float(os.getenv('EMISSION_BONUS_RARE_ENEMY_CHANCE', '0.35'))  # шанс редкого врага
EMISSION_BONUS_COMBAT_REWARD_MULT = float(os.getenv('EMISSION_BONUS_COMBAT_REWARD_MULT', '1.30'))  # +30% к наградам за бой

# === Ограниченные глобальные ивенты ===
LIMITED_EVENTS_ENABLED = os.getenv('LIMITED_EVENTS_ENABLED', 'true').lower() == 'true'
LIMITED_EVENT_MIN_INTERVAL_MINUTES = int(os.getenv('LIMITED_EVENT_MIN_INTERVAL_MINUTES', '300'))
LIMITED_EVENT_MAX_INTERVAL_MINUTES = int(os.getenv('LIMITED_EVENT_MAX_INTERVAL_MINUTES', '540'))
LIMITED_EVENT_ANNOUNCE_MINUTES = int(os.getenv('LIMITED_EVENT_ANNOUNCE_MINUTES', '15'))

# "Тихие часы" — когда выброс НЕ запускается (по UTC)
# По умолчанию: 02:00–07:00 UTC (ночное время, когда большинство спит)
EMISSION_QUIET_HOUR_START = int(os.getenv('EMISSION_QUIET_HOUR_START', '2'))
EMISSION_QUIET_HOUR_END = int(os.getenv('EMISSION_QUIET_HOUR_END', '7'))

# === P2P Рынок игроков ===
MARKET_MIN_LEVEL = int(os.getenv('MARKET_MIN_LEVEL', '25'))
BLACK_MARKET_MIN_LEVEL = int(os.getenv('BLACK_MARKET_MIN_LEVEL', '1'))
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
SHOP_BUY_MULT_FLOOR = float(os.getenv('SHOP_BUY_MULT_FLOOR', '0.90'))
SHOP_BUY_MULT_CEIL = float(os.getenv('SHOP_BUY_MULT_CEIL', '1.20'))
SHOP_SELL_MULT_FLOOR = float(os.getenv('SHOP_SELL_MULT_FLOOR', '0.35'))
SHOP_SELL_MULT_CEIL = float(os.getenv('SHOP_SELL_MULT_CEIL', '0.65'))

# === Retry для БД ===
DB_MAX_RETRIES = 3
DB_RETRY_DELAY = 1  # секунд

# === Прочее ===
DEBUG = os.getenv('DEBUG', '').lower() == 'true'
