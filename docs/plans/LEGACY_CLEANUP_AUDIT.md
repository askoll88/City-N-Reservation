# Legacy Cleanup Audit

Дата: 2026-05-24

Цель: зафиксировать оставшиеся legacy-слои в проекте, чтобы позже убрать их отдельными безопасными этапами.

## Приоритет 1 — рыбалка

- [ ] Удалить продажу legacy-рыбы из обычного инвентаря.
  - Код: `game/fishing/service.py`, `sell_luchik_fish`.
  - Сейчас рыбный шкаф уже живёт в таблице `user_fish_locker`, поэтому старый путь через инвентарь больше не нужен.

- [ ] Удалить `sell_luchik_fish_transaction`.
  - Код: `infra/database.py`.
  - Это старая продажа фиксированных рыб из `user_inventory`.

- [ ] Удалить `LUCHIK_FISH_PRICES` и `LUCHIK_SOUP_FISH`, если после чистки они нигде не используются.
  - Код: `infra/database.py`.

- [ ] Удалить `cook_luchik_fish_soup_transaction`.
  - Код: `infra/database.py`.
  - Это обратная совместимость старого вызова базовой ухи.

## Приоритет 2 — ранги

- [ ] Проверить, есть ли реальные данные ранга только в legacy-флаге `rank_tier`.
  - Код: `infra/database.py`, `get_user_rank_tier`.

- [ ] Если `users.rank_tier` уже гарантированно заполнен, убрать fallback на `user_flags.rank_tier`.
  - Код: `infra/database.py`, `get_user_rank_tier`.

- [ ] Убрать запись ранга обратно в legacy-флаг.
  - Код: `infra/database.py`, `set_user_rank_tier`.

## Приоритет 3 — экипировка и старая схема пользователей

- [ ] Разобрать `_migrate_legacy_schema`.
  - Код: `infra/database.py`.
  - Сейчас переносит старые `equipped_*`, `menu_state`, `newbie_kit_received`.

- [ ] Проверить, можно ли считать таблицу `user_equipment` единственным источником экипировки.

- [ ] После проверки убрать перенос старых `equipped_*` колонок.

- [ ] Отдельно решить, оставляем ли совместимые поля `equipped_weapon`, `equipped_armor_*` в результате `get_user_by_vk`.
  - Важно: много runtime-кода ещё читает эти поля, поэтому сначала нужен рефактор чтения экипировки.

## Приоритет 4 — gacha legacy flags

- [ ] Проверить legacy flags для валют и состояния баннеров.
  - Код: `infra/database.py`, `get_gacha_currency_balance`, `update_gacha_currency_balance`, `get_gacha_user_state`, `set_gacha_user_state`.
  - Код: `game/gacha/service.py`, вызовы с `legacy_flag` и `legacy_flags`.

- [ ] Если все данные перенесены в `gacha_currency_balances` и `gacha_user_state`, убрать fallback/sync через flags.

## Приоритет 5 — карта

- [ ] Зафиксировать решение по `models.locations.LOCATIONS`.
  - Сейчас `game/map_schema.py` построен поверх legacy `LOCATIONS`.
  - Это не баг, но архитектурный долг: новый map-layer зависит от старого runtime-источника.

- [ ] Если будем убирать legacy-карту, сначала перенести runtime-навигацию, описания, exits и actions в нормализованную модель.

## Приоритет 6 — классы

- [ ] Проверить актуальность нормализации старых class id.
  - Код: `models/classes.py`, `normalize_class_id`.

- [ ] Если в БД больше нет старых class id, убрать legacy mapping.

## Примечания

- Не удалять большие legacy-слои без проверки реальной БД.
- Начинать с рыбалки: она новая, данных у игроков ещё не было, поэтому там чистка самая безопасная.
- Для рангов, gacha и экипировки сначала нужен короткий DB-аудит: сколько строк реально используют старый формат.
