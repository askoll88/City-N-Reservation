# Этап 1: архитектура карты

Дата: 2026-04-28

## Что сделано

Добавлен новый слой структурированной карты: `game/map_schema.py`.

Старый `models/locations.LOCATIONS` сохранен как runtime-источник описаний, exits и legacy actions. Это важно: текущая навигация, клавиатуры, обработчики и старые команды продолжают работать без переписывания.

Новый слой строит нормализованные записи локаций поверх legacy-данных.

## Структура записи локации

Каждая локация теперь может быть представлена как map-record:

```python
{
    "id": "дорога_нии",
    "name": "🔬 Дорога на НИИ",
    "region": "science",
    "type": "route",
    "level_min": 1,
    "level_max": 5,
    "danger": "medium",
    "tags": ["research", "science", "route", "anomaly", "radiation", "artifacts"],
    "requires": {},
    "exits": {...},
    "activities": ["research", "combat", "anomaly"],
    "loot_profile": "scientific",
    "legacy_actions": [...]
}
```

Обязательные поля этапа 1:

- `id`
- `name`
- `region`
- `type`
- `level_min`
- `level_max`
- `danger`
- `tags`
- `requires`
- `exits`
- `activities`
- `loot_profile`

## Типы локаций

Добавлены разрешенные типы:

- `hub`
- `route`
- `field`
- `dungeon`
- `resource_job`
- `raid`
- `boss_arena`
- `safehouse`

Сейчас текущая карта размечена так:

| Локация | Тип | Регион |
|---|---|---|
| `город` | `hub` | `city` |
| `кпп` | `hub` | `checkpoint` |
| `больница` | `safehouse` | `city` |
| `черный рынок` | `hub` | `city` |
| `убежище` | `safehouse` | `city` |
| `инвентарь` | `hub` | `system` |
| `дорога_военная_часть` | `route` | `military` |
| `дорога_нии` | `route` | `science` |
| `дорога_зараженный_лес` | `route` | `forest` |

## Валидатор карты

Добавлен единый валидатор:

- `validate_map_schema() -> list[str]`
- `assert_valid_map_schema()`

Валидатор проверяет:

- у каждой legacy-локации есть metadata;
- `id` совпадает с ключом;
- `name` и `region` не пустые;
- `type` входит в разрешенный набор;
- `level_min <= level_max`;
- `danger` входит в разрешенный набор;
- `tags` и `activities` являются `list[str]`;
- `requires` является валидным словарем требований;
- все exits указывают на существующие локации;
- все `RESEARCH_LOCATIONS` имеют `research` activity;
- все `RESEARCH_LOCATIONS` имеют модификаторы, врагов, дроп, уровни и drop-balance;
- все safe locations имеют `danger=safe` и тип `hub` или `safehouse`.

## Требования доступа

Валидатор уже понимает будущие ключи `requires`:

- `level`
- `level_min`
- `rank_tier`
- `key`
- `keys`
- `item`
- `items`
- `flag`
- `flags`
- `quest_flag`
- `quest_flags`
- `reputation`
- `equipped`
- `radiation_max`
- `artifact_slots`
- `money`

На этапе 1 требования только валидируются как схема. Реальная проверка игрока будет на этапе 2 через `can_enter_location`.

## Helper API для следующих этапов

Добавлены read-only функции:

- `get_map_location(location_id)`
- `get_map_locations()`
- `get_locations_by_region(region)`
- `get_locations_by_type(location_type)`
- `get_research_map_locations()`

Их задача: экран карты, система доступа и будущие онлайн-события должны работать через нормализованные записи, а не напрямую через сырой `LOCATIONS`.

## Тесты

Добавлен файл: `tests/test_map_schema.py`.

Проверяет:

- новый map-layer совместим со старым `LOCATIONS`;
- все записи имеют обязательные поля архитектуры;
- валидатор проходит текущую базу;
- research-зоны размечены как `route` и имеют `research` activity;
- safe-зоны безопасны и имеют правильные типы;
- helper API возвращает структурированные записи;
- validator требований принимает будущие access-shapes и отклоняет мусор.

## Что важно не забыть на этапе 2

Следующий этап должен не менять эту схему, а начать использовать поле `requires`:

- добавить `can_enter_location(player, location_id)`;
- возвращать понятную причину отказа;
- показывать требования в UI;
- поддержать мягкое предупреждение при недоуровне;
- не ломать текущие свободные переходы города/КПП.

## Ограничения этапа 1

- Новые локации с большой карты еще не добавлены.
- `LOCATIONS` пока не заменен новой структурой, а обернут сверху.
- `requires` валидируется как форма, но не применяется к игроку.
- Экран карты еще не реализован.
- `world_state` еще не реализован.
