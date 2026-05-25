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
HUNT_DURATION_SECONDS = 5 * 60
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
        description="меньше риска, чаще мелкая добыча или пустой след",
    ),
    "ambush": HuntingTactic(
        id="ambush",
        label="Засада у солонца",
        energy_cost=12,
        risk=12,
        score_bonus=4,
        rare_bonus=3,
        description="сбалансированная охота с нормальным шансом трофея",
    ),
    "deep": HuntingTactic(
        id="deep",
        label="Глубокий след",
        energy_cost=18,
        risk=22,
        score_bonus=12,
        rare_bonus=10,
        description="выше шанс редкой добычи, но больше шанс нарваться на зверя",
    ),
}


ANIMALS = {
    "empty": [
        ("Пустой след", [], 25, 0),
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


def _get_state(vk_id: int) -> dict | None:
    state = database.get_runtime_state(vk_id, HUNTING_STATE_KEY)
    return state if isinstance(state, dict) and state else None


def _set_state(vk_id: int, state: dict):
    database.set_runtime_state(vk_id, HUNTING_STATE_KEY, state)


def _clear_state(vk_id: int):
    database.clear_runtime_state(vk_id, HUNTING_STATE_KEY)


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
        logger.warning("Картинка Белого Долговязого не найдена: %s", PALE_WATCHER_IMAGE_PATH)
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
        logger.exception("Не удалось загрузить картинку Белого Долговязого: user_id=%s", user_id)
        return None


def _pale_watcher_hunting_note(omen_count: int, done: bool = False) -> str | None:
    if done:
        return "После той встречи угодья будто вычеркнули тебя. Следов больше нет. Даже странных."
    if omen_count >= PALE_WATCHER_REQUIRED_OMENS:
        return "Метки в угодьях на месте, но смотреть на них неприятно. Кажется, лес ждёт твоего следующего шага."
    if omen_count == 2:
        return "Вспоминается гильза на пне. Вроде мелочь, а в угодья идти уже не так спокойно."
    if omen_count == 1:
        return "После того босого следа лес кажется тише обычного."
    return None


def _format_pale_watcher_omen(omen_count: int, tactic: HuntingTactic) -> str:
    if omen_count <= 1:
        omen_text = (
            "Сначала ты решаешь, что это усталость.\n\n"
            "Лес не замолкает сразу. Он выцветает по звуку, слой за слоем: сперва пропадают дальние птицы, "
            "потом шорох мелких лап, потом мокрый скрип стволов. Остаётся только твоё дыхание, и оно звучит "
            "слишком громко, будто ты дышишь не для себя, а чтобы кто-то мог легче считать вдохи.\n\n"
            "На мягкой земле рядом с твоей старой меткой продавлен след босой ноги. Не свежий и не старый — "
            "такой, словно земля вспомнила его только сейчас. Пятка узкая, пальцы вытянуты, шаг невозможный: "
            "отпечаток начинается там, куда человек не достал бы без разбега, а рядом нет ни сломанной ветки, "
            "ни смазанного края, ни второй опоры.\n\n"
            "Ты долго стоишь над ним и внезапно понимаешь, что рука уже лежит на оружии. Не потому что ты решил. "
            "Тело решило раньше головы."
        )
    elif omen_count == 2:
        omen_text = (
            "Ты сбиваешься с маршрута на знакомом участке.\n\n"
            "Компас не бесится, метки на месте, тропа та же, но каждый поворот выводит тебя к одному и тому же "
            "низкому пню. На нём лежит твоя вчерашняя гильза. Ты точно забрал её. Ты помнишь щелчок металла "
            "в кармане, помнишь грязь под ногтем, помнишь, как проверял патронташ перед выходом.\n\n"
            "Теперь гильза стоит вертикально, донцем вверх. На краю донца нацарапана короткая черта, потом вторая, "
            "потом третья. Они похожи не на счет и не на знак. Скорее на терпеливую проверку: сколько раз ты "
            "ещё вернёшься сюда, прежде чем поймёшь, что тебя не путают, а ведут.\n\n"
            "Холод поднимается от поясницы к затылку. Ты не видишь никого. Именно это хуже всего. Лес оставляет "
            "для тебя место в тишине, и ты начинаешь бояться его занять."
        )
    else:
        omen_text = (
            "На обратной тропе ты находишь свои метки перевёрнутыми внутрь леса.\n\n"
            "Не сорванными, не испорченными, не случайно сдвинутыми ветром. Аккуратно перевёрнутыми. Каждая "
            "бирка висит на том же сучке, но смотрит в чащу, как маленькая стрелка, которой больше не нужен ты.\n\n"
            "Под последней меткой кора вспорота тонкими параллельными линиями. Не когтями: слишком ровно. "
            "Не ножом: слишком глубоко для такого чистого края. Из прорезей медленно сочится тёмная древесная "
            "влага, и на секунду тебе кажется, что ствол дышит через рану.\n\n"
            "Ты уже не думаешь о добыче. Ты думаешь о том, как далеко до заимки, слышит ли тебя Лесник, "
            "и почему собственные шаги позади звучат на один лишний удар. Когда оборачиваешься, тропа пуста. "
            "Но сердце всё равно пропускает удар, потому что пустота успела посмотреть в ответ."
        )
    return (
        f"🐾 Охота сорвалась: {tactic.label}.\n\n"
        f"{omen_text}\n\n"
        "Ты уходишь без добычи и почти не помнишь дорогу назад. Уже у границы угодий приходит самая мерзкая мысль: "
        "всё это время ты спешил не выбраться из леса, а успеть до того, как тебя позовут по имени."
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


def _finish_pale_watcher_death(player, vk, user_id: int, tactic: HuntingTactic) -> bool:
    from handlers.keyboards import create_location_keyboard

    messages = [
        (
            "Ты понимаешь, что сегодня всё закончится, ещё до первого настоящего признака.\n\n"
            "Не приходит мысль. Приходит телесная уверенность, древняя и тупая, как боль от удара. "
            "Кожа на спине стягивается так, будто под куртку насыпали ледяной золы. Пальцы немеют на ремне оружия, "
            "и ремень кажется чужим: слишком тонким, слишком поздним, смешным предметом из мира, где опасность "
            "можно остановить железом.\n\n"
            "Лес вокруг не молчит. Он слушает. Каждая ветка, каждая мокрая ямка, каждая чёрная щель между корнями "
            "держит паузу вместе с тобой. Ты делаешь шаг — и слышишь, как где-то далеко повторяют этот шаг. "
            "Не эхом. Не зверем. Слишком ровно. Слишком терпеливо."
        ),
        (
            "Потом ты видишь его.\n\n"
            "Не вспышкой и не движением. Он просто оказывается там, где секунду назад было расстояние между "
            "деревьями. Долговязый, бледный, чудовищно высокий. Не худой — вытянутый, будто тело когда-то было "
            "человеческим, а потом его долго тянули вверх за кости, пока суставы не стали неправильными.\n\n"
            "Плечи почти касаются нижних веток. Шея слишком длинная и неподвижная. Голова слегка наклонена, "
            "как у того, кто прислушивается не к словам, а к работе сердца. Кожа матовая, без живого оттенка, "
            "натянутая на острые ключицы и плоскую грудь. На лице нет ни оскала, ни злобы, ни голода. Только "
            "гладкая, страшная сосредоточенность существа, которое уже знает, чем ты закончишься.\n\n"
            "Руки висят ниже колен. Пальцы длинные, тонкие, неподвижные, будто ими никогда не брали вещи — "
            "только указывали, ломали или вытаскивали. Он не рычит. Не скалится. Не делает ни шага. В этом и есть "
            "самое страшное: ему не нужно приближаться, чтобы ты понял расстояние между вами неправильно. "
            "Оно уже принадлежит ему.\n\n"
            "Ты пытаешься вспомнить, как дышать тихо. Как поднимать оружие. Как кричать. Ничего не вспоминается. "
            "В голове остаётся только детская, унизительная мысль: если не шевелиться, может быть, тебя не выберут."
        ),
        (
            "Ты мешкаешь ровно настолько, насколько нужно живому человеку.\n\n"
            "Белая рука вытягивается без замаха. Движение почти ленивое, будто он не нападает, а заканчивает "
            "дело, начатое давно: тем следом в грязи, той гильзой на пне, тем лишним шагом за спиной.\n\n"
            "Пальцы складываются в узкий белый клин и входят точно в центр грудины.\n\n"
            "Не как когти. Не как нож. Хуже. Сухой удар проходит сквозь одежду, ремни и кость так буднично, "
            "что мозг первую долю секунды отказывается принимать случившееся. Ты слышишь внутри себя короткий "
            "треск — не громкий, почти домашний, как ломается тонкая доска. Потом грудина раскрывается горячей "
            "чёрной болью, и весь воздух, который был в тебе, разом становится чужим.\n\n"
            "Ты пытаешься вдохнуть, но грудь больше не слушается. В горле поднимается влажный хрип. Руки "
            "хватают его запястье и находят только холодную гладкую кожу, сухую и неподвижную, как корень под "
            "зимней землёй. Он держит тебя на вытянутой руке, без усилия. Ноги ищут опору, скребут грязь, "
            "цепляют мох, но тело уже не весит для него ничего.\n\n"
            "Боль приходит волнами: сперва в груди, потом в спине, потом где-то глубоко под рёбрами, где всё "
            "становится мокрым и неправильным. Мир сжимается до его лица над тобой, до мокрой коры сбоку, "
            "до запаха земли и железа, до собственного хрипа, который звучит стыдно и жалко.\n\n"
            "Последнее, что ты успеваешь понять: он не злится. Не торопится. Не радуется. Он просто смотрит, "
            "как из тебя уходит жизнь, с тем же пустым терпением, с каким человек смотрит на дверь, которую "
            "давно пора было открыть."
        ),
    ]
    attachment = _upload_pale_watcher_image(vk, user_id)
    for index, message in enumerate(messages):
        if index == 1:
            vk_messages.send(
                vk,
                user_id=user_id,
                message=message,
                attachment=attachment,
                random_id=0,
            )
        else:
            vk.messages.send(user_id=user_id, message=message, random_id=0)

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
            "☠️ Легенда угодий: Белый Долговязый.\n\n"
            "Ты погиб.\n"
            f"Тактика охоты: {tactic.label}.\n"
            f"Потеряно: {lost_money} руб., {lost_exp} опыта.\n\n"
            "Очнулся ты уже в больнице. Лесник потом скажет только одно: "
            "«Значит, байка всё-таки выбрала тебя.»"
        ),
        keyboard=create_location_keyboard(player.current_location_id, getattr(player, "level", None)).get_keyboard(),
        random_id=0,
    )
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
        "Выбери тактику. Охота займёт около 5 минут и не заменяет обычное исследование.",
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
        lines.append("Сейчас у тебя уже идёт охота.")
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
    state = {
        "started_at": _now(),
        "duration": HUNT_DURATION_SECONDS,
        "tactic": tactic.id,
        "seed": random.randint(1, 2_000_000_000),
    }
    _set_state(user_id, state)
    vk.messages.send(
        user_id=user_id,
        message=(
            f"🐾 Ты начал охоту: {tactic.label}.\n\n"
            f"Потрачено: {tactic.energy_cost}⚡.\n"
            "Лесник учил: на охоте важна не скорость, а момент. Вернись через несколько минут и проверь след."
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
            message=f"🐾 След ещё не закрылся.\nОсталось примерно: {max(1, remaining // 60)} мин. {remaining % 60} сек.",
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
            f"🐾 Охота завершена: {animal_name}.\n\n"
            "След ушёл в мокрый валежник. Ты нашёл место лёжки, но добычу брать было уже поздно."
        )
    else:
        result_text = (
            f"🐾 Охота завершена: {animal_name}.\n\n"
            "Добыча:\n"
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
        message = "🐾 Ты свернул охоту и вернулся к меткам. Потраченную энергию уже не вернуть."
    else:
        message = "🐾 Сейчас у тебя нет активной охоты."
    vk.messages.send(
        user_id=user_id,
        message=message,
        keyboard=create_hunting_grounds_keyboard(active=False).get_keyboard(),
        random_id=0,
    )
    return True


def handle_hunting_command(player, vk, user_id: int, text: str) -> bool:
    normalized = (text or "").strip().lower()
    if normalized in {"охотиться", "охота", "угодья"}:
        show_hunting_menu(player, vk, user_id)
        return True
    if normalized in {"проверить охоту", "проверить", "след", "идти"}:
        return check_hunt(player, vk, user_id)
    if normalized in {"отменить охоту", "отмена охоты", "отмена", "стоп"}:
        return cancel_hunt(player, vk, user_id)
    tactic_id = TACTIC_ALIASES.get(normalized)
    if tactic_id:
        return start_hunt(player, vk, user_id, tactic_id)
    return False
