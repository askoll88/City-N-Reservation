"""
Централизованная обработка ошибок
"""
import logging
import traceback
from functools import wraps

from infra import config

logger = logging.getLogger(__name__)


class GameError(Exception):
    """Базовый класс ошибок игры"""
    def __init__(self, message: str, user_message: str = None):
        super().__init__(message)
        self.user_message = user_message or "Произошла ошибка. Попробуй ещё раз."


class DatabaseError(GameError):
    """Ошибка базы данных"""
    pass


class PlayerNotFoundError(GameError):
    """Игрок не найден"""
    def __init__(self, user_id: int):
        super().__init__(
            f"Player {user_id} not found",
            "Твой профиль не найден. Напиши 'начать' для регистрации."
        )


class InsufficientFundsError(GameError):
    """Недостаточно денег"""
    def __init__(self, required: int, available: int):
        super().__init__(
            f"Insufficient funds: need {required}, have {available}",
            f"Недостаточно денег. Нужно: {required:,} руб., у тебя: {available:,} руб."
        )


class ItemNotFoundError(GameError):
    """Предмет не найден"""
    def __init__(self, item_name: str):
        super().__init__(
            f"Item '{item_name}' not found",
            f"Предмет '{item_name}' не найден."
        )


class LocationError(GameError):
    """Ошибка локации"""
    pass


def with_error_handling(func):
    """Декоратор для централизованной обработки ошибок"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except PlayerNotFoundError as e:
            logger.warning(f"Player not found: {e}")
            # args[0] обычно vk, args[1] обычно user_id
            if len(args) >= 2:
                try:
                    args[0].messages.send(
                        user_id=args[1],
                        message=e.user_message,
                        random_id=0
                    )
                except:
                    pass
        except InsufficientFundsError as e:
            logger.warning(f"Insufficient funds: {e}")
            if len(args) >= 2:
                try:
                    args[0].messages.send(
                        user_id=args[1],
                        message=e.user_message,
                        random_id=0
                    )
                except:
                    pass
        except GameError as e:
            logger.error(f"Game error in {func.__name__}: {e}")
            if len(args) >= 2:
                try:
                    args[0].messages.send(
                        user_id=args[1],
                        message=e.user_message,
                        random_id=0
                    )
                except:
                    pass
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}")
            traceback.print_exc()
            if len(args) >= 2:
                try:
                    args[0].messages.send(
                        user_id=args[1],
                        message="⚠️ Произошла техническая ошибка. Мы уже работаем над её исправлением.",
                        random_id=0
                    )
                except:
                    pass
    return wrapper


def log_error(func):
    """Декоратор только для логирования ошибок"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {e}")
            traceback.print_exc()
            raise
    return wrapper
