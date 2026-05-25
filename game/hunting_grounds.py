"""
AFK-охота в лесных угодьях.

Это отдельная активность, не обычное исследование: игрок выбирает тактику,
ждёт таймер и получает результат по следу, риску и характеристикам.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
import logging
from pathlib import Path

from infra import database, vk_messages
from models.player import invalidate_player_cache

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]

HUNTING_GROUNDS_LOCATION = "охотничьи_угодья"
HUNTING_UNLOCK_FLAG = "forest_hunting_grounds_unlocked"
HUNTING_STATE_KEY = "hunting_grounds_state"
PALE_WATCHER_SCENE_STATE_KEY = "hunting_pale_watcher_scene"
HUNT_DURATION_SECONDS = 5 * 60
HUNT_DURATION_MIN_SECONDS = 4 * 60
HUNT_DURATION_MAX_SECONDS = 6 * 60
PALE_WATCHER_TRAIL_FLAG = "forest_hunting_pale_watcher_trail"
PALE_WATCHER_DONE_FLAG = "forest_hunting_pale_watcher_done"
PALE_WATCHER_ADMIN_FORCE_FLAG = "forest_hunting_pale_watcher_admin_force"
PALE_WATCHER_START_CHANCE = 0.00001  # 0.001%
PALE_WATCHER_NEXT_OMEN_CHANCE = 0.25
PALE_WATCHER_REQUIRED_OMENS = 3
PALE_WATCHER_IMAGE_PATH = PROJECT_ROOT / "Img" / "forest_legend" / "forest_legend.png"
PALE_WATCHER_IMAGE_PROMPT = (
    "A tall gaunt pale humanoid local forest legend, unnaturally long limbs, "
    "no visible fear, standing still between dark wet trees, washed-out skin, "
    "horror atmosphere, grounded post-apocalyptic forest, no gore"
)
_PALE_WATCHER_ATTACHMENT_CACHE: str | None = None
LEGEND_NAME = "Семнадцатый"


@dataclass(frozen=True)
class HuntingTactic:
    id: str
    label: str
    energy_cost: int
    risk: int
    score_bonus: int
    rare_bonus: int
    description: str


TACTICS: dict[str, HuntingTactic] = {
    "quiet": HuntingTactic(
        id="quiet",
        label="Тихая тропа",
        energy_cost=8,
        risk=6,
        score_bonus=-4,
        rare_bonus=-5,
        description="тихий выход с меньшим риском, но добыча обычно мелкая",
    ),
    "ambush": HuntingTactic(
        id="ambush",
        label="Засада у солонца",
        energy_cost=12,
        risk=12,
        score_bonus=4,
        rare_bonus=3,
        description="спокойная середина между риском и шансом на трофей",
    ),
    "deep": HuntingTactic(
        id="deep",
        label="Глубокий след",
        energy_cost=18,
        risk=22,
        score_bonus=12,
        rare_bonus=10,
        description="глубже в лес, выше шанс редкой добычи и опасной встречи",
    ),
}


ANIMALS = {
    "empty": [
        ("Пустая тропа", [], 25, 0),
        ("Сбитая тропа", [], 35, 0),
    ],
    "common": [
        ("Рыжая лиса", [("Лисий хвост", 1)], 70, 2),
        ("Дикая собака", [("Ломоть мяса", 1)], 60, 2),
        ("Подраненный кабан", [("Ломоть мяса", 1), ("Шкура кабана", 1)], 80, 3),
    ],
    "uncommon": [
        ("Серый волк", [("Шкура волка", 1), ("Ломоть мяса", 1)], 120, 4),
        ("Крупный кабан-секач", [("Шкура кабана", 1), ("Ломоть мяса", 2)], 140, 5),
        ("Лесной снорк", [("Кость снорка", 1)], 130, 5),
    ],
    "rare": [
        ("Старый медведь", [("Медвежий жир", 1), ("Медвежья шкура", 1)], 220, 7),
        ("Белая лиса", [("Лисий хвост", 2), ("Чистая звериная кость", 1)], 210, 7),
        ("Кровосос на лежке", [("Коготь кровососа", 1), ("Мутная железа", 1)], 240, 8),
    ],
    "mutant": [
        ("Клыкастая тень", [("Клык мутанта", 1), ("Мутная железа", 1)], 280, 10),
        ("Пятнистый медведь-мутант", [("Медвежий жир", 1), ("Клык мутанта", 1)], 320, 11),
    ],
}


TACTIC_ALIASES = {
    "тихая тропа": "quiet",
    "тихо": "quiet",
    "тихая": "quiet",
    "засада у солонца": "ambush",
    "засада": "ambush",
    "солонец": "ambush",
    "глубокий след": "deep",
    "глубоко": "deep",
    "след": "deep",
}


def _now() -> int:
    return int(time.time())


def _format_timer(seconds: int) -> str:
    seconds = max(0, int(seconds or 0))
    minutes, seconds = divmod(seconds, 60)
    if minutes <= 0:
        return f"{seconds} сек."
    return f"{minutes} мин. {seconds} сек."


def _roll_hunt_duration() -> int:
    return random.randint(HUNT_DURATION_MIN_SECONDS, HUNT_DURATION_MAX_SECONDS)


def _get_state(vk_id: int) -> dict | None:
    state = database.get_runtime_state(vk_id, HUNTING_STATE_KEY)
    return state if isinstance(state, dict) and state else None


def _set_state(vk_id: int, state: dict):
    database.set_runtime_state(vk_id, HUNTING_STATE_KEY, state)


def _clear_state(vk_id: int):
    database.clear_runtime_state(vk_id, HUNTING_STATE_KEY)


def _get_scene_state(vk_id: int) -> dict | None:
    state = database.get_runtime_state(vk_id, PALE_WATCHER_SCENE_STATE_KEY)
    return state if isinstance(state, dict) and state else None


def _set_scene_state(vk_id: int, state: dict):
    database.set_runtime_state(vk_id, PALE_WATCHER_SCENE_STATE_KEY, state)


def _clear_scene_state(vk_id: int):
    database.clear_runtime_state(vk_id, PALE_WATCHER_SCENE_STATE_KEY)


def _has_unlock(vk_id: int) -> bool:
    return (
        int(database.get_user_flag(vk_id, HUNTING_UNLOCK_FLAG, 0) or 0) > 0
        or int(database.get_user_flag(vk_id, "forest_hunting_unlocked", 0) or 0) > 0
    )


def _stat(player, name: str) -> int:
    return max(0, int(getattr(player, name, 0) or 0))


def _pick_tier(player, tactic: HuntingTactic, seed: int) -> tuple[str, bool]:
    rng = random.Random(seed)
    perception = _stat(player, "perception")
    luck = _stat(player, "luck")
    level = _stat(player, "level")
    score = rng.randint(1, 100)
    score += min(22, perception * 2)
    score += min(16, luck * 2)
    score += min(10, level // 3)
    score += tactic.score_bonus

    risk_chance = max(3, tactic.risk - perception // 2 - luck // 4)
    ambushed = rng.randint(1, 100) <= risk_chance
    if ambushed:
        score -= rng.randint(10, 22)

    rare_shift = tactic.rare_bonus
    if score < 36:
        return "empty", ambushed
    if score < 66:
        return "common", ambushed
    if score < 86:
        return "uncommon", ambushed
    if score < 98 - rare_shift:
        return "rare", ambushed
    return "mutant", ambushed


def _roll_pale_watcher_start(rng: random.Random, omen_count: int) -> bool:
    if omen_count > 0:
        return False
    return rng.random() < PALE_WATCHER_START_CHANCE


def _roll_pale_watcher_next_omen(rng: random.Random, omen_count: int) -> bool:
    if omen_count <= 0 or omen_count >= PALE_WATCHER_REQUIRED_OMENS:
        return False
    return rng.random() < PALE_WATCHER_NEXT_OMEN_CHANCE


def _upload_pale_watcher_image(vk, user_id: int) -> str | None:
    global _PALE_WATCHER_ATTACHMENT_CACHE
    if _PALE_WATCHER_ATTACHMENT_CACHE:
        return _PALE_WATCHER_ATTACHMENT_CACHE
    if not hasattr(vk, "photos"):
        return None
    if not PALE_WATCHER_IMAGE_PATH.exists():
        logger.warning("Картинка легенды '%s' не найдена: %s", LEGEND_NAME, PALE_WATCHER_IMAGE_PATH)
        return None

    try:
        import requests

        upload_server = vk.photos.getMessagesUploadServer(peer_id=user_id)
        with PALE_WATCHER_IMAGE_PATH.open("rb") as image_file:
            upload_response = requests.post(
                upload_server["upload_url"],
                files={"photo": image_file},
                timeout=20,
            )
        upload_response.raise_for_status()
        uploaded = upload_response.json()
        saved = vk.photos.saveMessagesPhoto(
            photo=uploaded["photo"],
            server=uploaded["server"],
            hash=uploaded["hash"],
        )
        if not saved:
            return None

        photo = saved[0]
        attachment = f"photo{photo['owner_id']}_{photo['id']}"
        access_key = photo.get("access_key")
        if access_key:
            attachment = f"{attachment}_{access_key}"
        _PALE_WATCHER_ATTACHMENT_CACHE = attachment
        return attachment
    except Exception:
        logger.exception("Не удалось загрузить картинку легенды '%s': user_id=%s", LEGEND_NAME, user_id)
        return None


def _pale_watcher_hunting_note(omen_count: int, done: bool = False) -> str | None:
    if done:
        return "После той встречи угодья будто вычеркнули тебя. Следов больше нет. Даже странных."
    if omen_count >= PALE_WATCHER_REQUIRED_OMENS:
        return "Метки в угодьях на месте, но смотреть на них неприятно. После третьего знамения туда уже не тянет."
    if omen_count == 2:
        return "Вспоминается гильза на пне. Вроде мелочь, а в угодья идти уже не так спокойно."
    if omen_count == 1:
        return "После того босого следа в угодьях замечаешь каждый лишний шорох."
    return None


def _format_pale_watcher_omen(omen_count: int, tactic: HuntingTactic) -> str:
    if omen_count <= 1:
        omen_text = (
            "Ты находишь босой след рядом со своей меткой.\n\n"
            "След слишком длинный. Пятка узкая, пальцы вытянуты. Второго отпечатка рядом нет, будто кто-то "
            "поставил ногу и просто исчез.\n\n"
            "Поначалу это не пугает. Скорее раздражает: в угодьях и без того хватает странностей. Но потом "
            "замечаешь, что рядом не слышно мелких птиц и насекомых. До этого они были, а теперь остался "
            "только твой сапог в мокрой земле.\n\n"
            "Ты ещё пару минут проверяешь землю вокруг, хотя уже понимаешь: нормального объяснения не будет. "
            "Уходишь без добычи."
        )
    elif omen_count == 2:
        omen_text = (
            "Ты три раза выходишь к одному и тому же пню.\n\n"
            "Метки на месте. Компас не чудит. Маршрут знакомый. Но каждый раз перед тобой снова этот пень.\n\n"
            "На нём стоит твоя гильза. Та самая, которую ты вчера забрал с земли и убрал в карман. Она стоит "
            "донцем вверх. На донце три короткие царапины.\n\n"
            "Ты не видишь никого. Не слышишь шагов. Никто не смеётся в кустах. От этого только хуже.\n\n"
            "В какой-то момент ты перестаёшь искать добычу и начинаешь считать, сколько осталось до заимки."
        )
    else:
        omen_text = (
            "На обратной тропе ты находишь свои метки перевёрнутыми внутрь леса.\n\n"
            "Их не сорвали и не сломали. Каждую просто развернули на том же сучке. Аккуратно, без спешки.\n\n"
            "Под последней меткой кора прорезана ровными линиями. Слишком ровно для зверя. Слишком глубоко "
            "для случайной ветки.\n\n"
            "Ты стоишь и понимаешь неприятную вещь: тебя не путают. Тебя ведут.\n\n"
            "Назад ты идёшь быстро, но не бежишь. Бежать почему-то кажется худшей идеей."
        )
    return (
        f"🐾 Вылазка сорвалась: {tactic.label}.\n\n"
        f"{omen_text}\n\n"
        "Лесник когда-то говорил про местную легенду. Тогда это звучало как байка для новичков. "
        "Сейчас уже не звучит."
    )


def _finish_pale_watcher_omen(player, vk, user_id: int, tactic: HuntingTactic, omen_count: int) -> bool:
    from handlers.keyboards import create_hunting_grounds_keyboard

    _clear_state(user_id)
    database.set_user_flag(user_id, PALE_WATCHER_TRAIL_FLAG, omen_count)
    invalidate_player_cache(user_id)
    vk.messages.send(
        user_id=user_id,
        message=_format_pale_watcher_omen(omen_count, tactic),
        keyboard=create_hunting_grounds_keyboard(active=False).get_keyboard(),
        random_id=0,
    )
    return True


PALE_WATCHER_SCENE_STEPS = [
    {
        "label": "Идти дальше",
        "message": (
            "🐾 Охота не складывается.\n\n"
            "След оборвался там, где не должен был. Добычи нет. Ветки не шевелятся, хотя минуту назад тянул "
            "лёгкий ветер.\n\n"
            "Ты стоишь среди деревьев и понимаешь, что это уже не охота. Это продолжение той самой байки, "
            "которую Лесник рассказывал вполголоса."
        ),
    },
    {
        "label": "Поднять оружие",
        "message": (
            "Между деревьями кто-то стоит.\n\n"
            "Сначала кажется, что это белый ствол. Потом ствол чуть меняет положение.\n\n"
            "Он слишком высокий для человека. Руки длинные, почти до колен. Кожа бледная, без нормального "
            "цвета. Лицо не звериное и не человеческое до конца: будто знакомые черты собрали неправильно "
            "и оставили без выражения.\n\n"
            "Он не прячется. Не рычит. Просто стоит и смотрит чуть мимо тебя, как будто уже знает, где ты "
            "окажешься через несколько секунд."
        ),
        "attachment": True,
    },
    {
        "label": "Отступить",
        "message": (
            "Ты пытаешься поднять оружие.\n\n"
            "Пальцы двигаются медленно. Слишком медленно. Ремень цепляется за рукав. В обычный день ты бы "
            "выругался. Сейчас даже на это не хватает воздуха.\n\n"
            "Он всё ещё стоит на месте. От этого хуже. Если бы он бросился, тело хотя бы поняло, что делать."
        ),
    },
    {
        "label": "Вдохнуть",
        "message": (
            "Ты делаешь шаг назад.\n\n"
            "Под ботинком хрустит ветка. Звук выходит громким, глупым, почти стыдным.\n\n"
            "Он больше не между деревьями. Он ближе.\n\n"
            "Ты не видел движения. Просто расстояние закончилось."
        ),
    },
    {
        "label": "Закрыть глаза",
        "message": (
            "Удар приходит в грудь.\n\n"
            "Его белая рука оказывается слишком близко. Внутри что-то сухо трещит. В груди ломается кость.\n\n"
            "Ты пытаешься вдохнуть, но вдох не получается. Только короткий хлюпающий мокрый звук. Ноги ещё ищут землю, "
            "руки ещё пытаются что-то удержать, но тело уже не слушается.\n\n"
            "Самое страшное приходит не от боли. Страшно от простой мысли: я всё ещё тут, всё ещё понимаю, "
            "что происходит, но уже ничего не могу исправить. Ни поднять оружие. Ни отползти. Ни позвать.\n\n"
            "Хочется домой. Не к трофеям, не к разговорам у костра, не к чужим рассказам о том, как надо было "
            "поступить. Просто домой. Туда, где тебя должны были дождаться и где тихо.\n\n"
            "Но тишина наступает здесь, мне уже спокойней."
        ),
    },
    {
        "message": (
            "Ты закрываешь глаза.\n\n"
            "На секунду становится легче. Не потому что боль ушла. Просто ты смирился со своей судьбой.\n\n"
            "Воздуха нет. Мысли путаются. Звуки становятся глухими и дальними.\n\n"
            "Последняя мысль простая и очень человеческая: надо было тогда поверить Леснику."
        ),
        "final": True,
    },
]


def _finish_pale_watcher_death(player, vk, user_id: int, tactic: HuntingTactic) -> bool:
    from handlers.keyboards import create_pale_watcher_scene_keyboard

    _clear_state(user_id)
    _set_scene_state(
        user_id,
        {
            "step": 0,
            "tactic": tactic.id,
            "started_at": _now(),
        },
    )
    first_step = PALE_WATCHER_SCENE_STEPS[0]
    vk_messages.send(
        vk,
        user_id=user_id,
        message=first_step["message"],
        keyboard=create_pale_watcher_scene_keyboard(first_step["label"]),
        random_id=0,
    )
    return True


def _complete_pale_watcher_death(player, vk, user_id: int, tactic: HuntingTactic) -> bool:
    from handlers.keyboards import create_location_keyboard

    old_money = max(0, int(getattr(player, "money", 0) or 0))
    old_exp = max(0, int(getattr(player, "experience", 0) or 0))
    lost_money = int(old_money * 0.20)
    lost_exp = int(old_exp * 0.15)
    player.money = max(0, old_money - lost_money)
    player.experience = max(0, old_exp - lost_exp)
    player.health = max(1, int(getattr(player, "max_health", 100) or 100) // 2)
    player.energy = 50
    player.radiation = 0
    player.current_location_id = "больница"

    _clear_state(user_id)
    _clear_scene_state(user_id)
    database.set_user_flag(user_id, PALE_WATCHER_TRAIL_FLAG, 0)
    database.set_user_flag(user_id, PALE_WATCHER_DONE_FLAG, 1)
    database.update_user_location(user_id, "больница")
    database.update_user_stats(
        user_id,
        health=player.health,
        energy=player.energy,
        radiation=0,
        money=player.money,
        experience=player.experience,
    )
    invalidate_player_cache(user_id)

    vk_messages.send(
        vk,
        user_id=user_id,
        message=(
            f"☠️ Легенда угодий: {LEGEND_NAME}.\n\n"
            "Ты погиб.\n"
            f"Тактика охоты: {tactic.label}.\n"
            f"Потеряно: {lost_money} руб., {lost_exp} опыта.\n\n"
            "Очнулся ты уже в больнице. Лесник долго молчит, потом говорит коротко:\n"
            "«После Семнадцатого не возвращаются. Тебе просто повезло. На этом всё.»"
        ),
        keyboard=create_location_keyboard(player.current_location_id, getattr(player, "level", None)).get_keyboard(),
        random_id=0,
    )
    return True


def handle_pale_watcher_scene_callback(player, vk, user_id: int, payload: dict | None = None) -> bool:
    from handlers.keyboards import create_pale_watcher_scene_keyboard

    state = _get_scene_state(user_id)
    if not state:
        vk_messages.send(vk, user_id=user_id, message="Эта сцена уже закрыта.", random_id=0)
        return True

    next_step = int(state.get("step", 0) or 0) + 1
    if next_step >= len(PALE_WATCHER_SCENE_STEPS):
        tactic = TACTICS.get(str(state.get("tactic") or "ambush"), TACTICS["ambush"])
        return _complete_pale_watcher_death(player, vk, user_id, tactic)

    state["step"] = next_step
    _set_scene_state(user_id, state)
    step = PALE_WATCHER_SCENE_STEPS[next_step]
    attachment = _upload_pale_watcher_image(vk, user_id) if step.get("attachment") else None
    keyboard = None
    if not step.get("final"):
        keyboard = create_pale_watcher_scene_keyboard(str(step["label"]))

    vk_messages.send(
        vk,
        user_id=user_id,
        message=str(step["message"]),
        attachment=attachment,
        keyboard=keyboard,
        random_id=0,
    )
    if step.get("final"):
        tactic = TACTICS.get(str(state.get("tactic") or "ambush"), TACTICS["ambush"])
        return _complete_pale_watcher_death(player, vk, user_id, tactic)
    return True


def _maybe_handle_pale_watcher(player, vk, user_id: int, state: dict, tactic: HuntingTactic) -> bool:
    seed = int(state.get("seed") or random.randint(1, 999999))
    rng = random.Random(seed + 701_337)
    admin_forced = (
        int(database.get_user_flag(user_id, PALE_WATCHER_ADMIN_FORCE_FLAG, 0) or 0) > 0
        and bool(database.is_user_admin(user_id))
    )
    if int(database.get_user_flag(user_id, PALE_WATCHER_DONE_FLAG, 0) or 0) > 0:
        return False

    omen_count = max(0, int(database.get_user_flag(user_id, PALE_WATCHER_TRAIL_FLAG, 0) or 0))
    if omen_count >= PALE_WATCHER_REQUIRED_OMENS:
        return _finish_pale_watcher_death(player, vk, user_id, tactic)

    if admin_forced or _roll_pale_watcher_start(rng, omen_count) or _roll_pale_watcher_next_omen(rng, omen_count):
        return _finish_pale_watcher_omen(player, vk, user_id, tactic, omen_count + 1)
    return False


def _format_menu(player, active: bool = False, user_id: int | None = None) -> str:
    lines = [
        "🐾 ОХОТНИЧЬИ УГОДЬЯ",
        "",
        "Выбери, как пойдёшь в лес. Вылазка займёт несколько минут и не заменяет обычное исследование.",
        "",
    ]
    for tactic in TACTICS.values():
        lines.append(f"• {tactic.label}: {tactic.energy_cost}⚡, {tactic.description}.")
    lines.extend([
        "",
        f"Твои факторы: восприятие {_stat(player, 'perception')}, удача {_stat(player, 'luck')}.",
    ])
    if user_id is not None:
        done = int(database.get_user_flag(user_id, PALE_WATCHER_DONE_FLAG, 0) or 0) > 0
        omen_count = max(0, int(database.get_user_flag(user_id, PALE_WATCHER_TRAIL_FLAG, 0) or 0))
        note = _pale_watcher_hunting_note(omen_count, done)
        if note:
            lines.extend(["", note])
    if active:
        lines.append("Ты уже оставил метки в угодьях. Можно вернуться к ним позже.")
    return "\n".join(lines)


def show_hunting_menu(player, vk, user_id: int):
    from handlers.keyboards import create_hunting_grounds_keyboard

    active = _get_state(user_id) is not None
    vk.messages.send(
        user_id=user_id,
        message=_format_menu(player, active=active, user_id=user_id),
        keyboard=create_hunting_grounds_keyboard(active=active).get_keyboard(),
        random_id=0,
    )


def start_hunt(player, vk, user_id: int, tactic_id: str):
    from handlers.keyboards import create_hunting_grounds_keyboard, create_location_keyboard

    if player.current_location_id != HUNTING_GROUNDS_LOCATION:
        return False
    if not _has_unlock(user_id):
        vk.messages.send(
            user_id=user_id,
            message="🌲 Лесник ещё не дал тебе метки к угодьям. Вернись в заимку и пройди его проверку.",
            keyboard=create_location_keyboard(player.current_location_id, player.level).get_keyboard(),
            random_id=0,
        )
        return True
    if _get_state(user_id):
        return check_hunt(player, vk, user_id)

    tactic = TACTICS[tactic_id]
    energy = int(getattr(player, "energy", 0) or 0)
    if energy < tactic.energy_cost:
        vk.messages.send(
            user_id=user_id,
            message=f"⚡ Не хватает энергии для охоты. Нужно {tactic.energy_cost}, у тебя {energy}.",
            keyboard=create_hunting_grounds_keyboard(active=False).get_keyboard(),
            random_id=0,
        )
        return True

    player.energy = energy - tactic.energy_cost
    database.update_user_stats(user_id, energy=player.energy)
    duration = _roll_hunt_duration()
    state = {
        "started_at": _now(),
        "duration": duration,
        "tactic": tactic.id,
        "seed": random.randint(1, 2_000_000_000),
    }
    _set_state(user_id, state)
    vk.messages.send(
        user_id=user_id,
        message=(
            f"🐾 Ты вышел в угодья: {tactic.label}.\n\n"
            f"Потрачено: {tactic.energy_cost}⚡.\n"
            f"Возвращайся к меткам примерно через {_format_timer(duration)}.\n"
            "Лесник учил: на охоте важен момент. Рано вернёшься — только распугаешь добычу."
        ),
        keyboard=create_hunting_grounds_keyboard(active=True).get_keyboard(),
        random_id=0,
    )
    return True


def check_hunt(player, vk, user_id: int):
    from handlers.keyboards import create_hunting_grounds_keyboard

    state = _get_state(user_id)
    if not state:
        show_hunting_menu(player, vk, user_id)
        return True

    now = _now()
    started = int(state.get("started_at", now) or now)
    duration = max(30, int(state.get("duration", HUNT_DURATION_SECONDS) or HUNT_DURATION_SECONDS))
    remaining = started + duration - now
    if remaining > 0:
        vk.messages.send(
            user_id=user_id,
            message=(
                "🐾 К меткам ещё рано.\n"
                "Дай тропе остыть после твоих шагов. Вернуться стоит примерно через "
                f"{_format_timer(remaining)}."
            ),
            keyboard=create_hunting_grounds_keyboard(active=True).get_keyboard(),
            random_id=0,
        )
        return True

    tactic = TACTICS.get(str(state.get("tactic") or "ambush"), TACTICS["ambush"])
    if _maybe_handle_pale_watcher(player, vk, user_id, state, tactic):
        return True

    tier, ambushed = _pick_tier(player, tactic, int(state.get("seed") or random.randint(1, 999999)))
    rng = random.Random(int(state.get("seed") or 1) + 17)
    animal_name, rewards, xp_gain, trail_value = rng.choice(ANIMALS[tier])

    reward_lines = []
    for item_name, qty in rewards:
        if database.add_item_to_inventory(user_id, item_name, qty):
            reward_lines.append(f"• {item_name} x{qty}")

    damage_line = ""
    if ambushed:
        hp_loss = rng.randint(8, 22) + (6 if tactic.id == "deep" else 0)
        energy_loss = rng.randint(3, 9)
        player.health = max(1, int(getattr(player, "health", 1) or 1) - hp_loss)
        player.energy = max(0, int(getattr(player, "energy", 0) or 0) - energy_loss)
        database.update_user_stats(user_id, health=player.health, energy=player.energy)
        damage_line = f"\n\n⚠️ Добыча дала отпор: -{hp_loss} HP, -{energy_loss}⚡."

    gained_xp = 0
    if xp_gain > 0:
        gained_xp = int(player.add_experience(xp_gain))

    if trail_value > 0:
        database.set_user_flag(user_id, "forest_hunting_trail_score", int(database.get_user_flag(user_id, "forest_hunting_trail_score", 0) or 0) + trail_value)

    _clear_state(user_id)
    invalidate_player_cache(user_id)

    if not reward_lines:
        result_text = (
            f"🐾 Итог вылазки: {animal_name}.\n\n"
            "След ушёл в мокрый валежник. Ты нашёл место лёжки, но добычу брать было уже поздно."
        )
    else:
        result_text = (
            f"🐾 Итог вылазки: {animal_name}.\n\n"
            "Трофеи:\n"
            + "\n".join(reward_lines)
        )
    if gained_xp:
        result_text += f"\n\nОпыт: +{gained_xp}."
    result_text += damage_line

    vk.messages.send(
        user_id=user_id,
        message=result_text,
        keyboard=create_hunting_grounds_keyboard(active=False).get_keyboard(),
        random_id=0,
    )
    return True


def cancel_hunt(player, vk, user_id: int):
    from handlers.keyboards import create_hunting_grounds_keyboard

    if _get_state(user_id):
        _clear_state(user_id)
        message = "🐾 Ты снял метки и вернулся к тропе. Потраченную энергию уже не вернуть."
    else:
        message = "🐾 Сейчас у тебя нет вылазки в угодьях."
    vk.messages.send(
        user_id=user_id,
        message=message,
        keyboard=create_hunting_grounds_keyboard(active=False).get_keyboard(),
        random_id=0,
    )
    return True


def handle_hunting_command(player, vk, user_id: int, text: str) -> bool:
    normalized = (text or "").strip().lower()
    if normalized in {"выйти на охоту", "охотиться", "охота", "угодья"}:
        show_hunting_menu(player, vk, user_id)
        return True
    if normalized in {
        "вернуться к меткам",
        "к меткам",
        "метки",
        "идти к меткам",
        "проверить след",
        "проверить охоту",
        "проверить",
        "след",
        "идти",
    }:
        return check_hunt(player, vk, user_id)
    if normalized in {"снять метки", "свернуть вылазку", "отменить охоту", "отмена охоты", "отмена", "стоп"}:
        return cancel_hunt(player, vk, user_id)
    tactic_id = TACTIC_ALIASES.get(normalized)
    if tactic_id:
        return start_hunt(player, vk, user_id, tactic_id)
    return False
