# Баг-аудит City-N Reservation Bot

> **Дата:** 14 апреля 2026  
> **Файлы проверены:** 12  
> **Багов найдено:** 42  
> **Исправлено:** 15 (CRITICAL + HIGH + MEDIUM x5)  
> **Ложные срабатывания:** 1 (#14)  
> **Осталось:** 27 (MEDIUM + LOW)

---

## ✅ Исправленные (10)

| # | Файл | Severity | Баг |
|---|------|----------|-----|
| 1 | `handlers/admin.py` | CRITICAL | `EMISSION_PHASE_CANCELLED` не импортирован → `NameError` |
| 2 | `handlers/inventory.py` | CRITICAL | `handle_buy_artifact` — артефакт добавляется дважды |
| 3 | `random_events.py` | CRITICAL | `player.user_id` → `AttributeError` (`TempPlayer` имеет `vk_id`) |
| 4 | `handlers/combat.py` | CRITICAL | `_combat_state_ref` не определён для `mutant_hunt` |
| 5 | `database.py` | HIGH | `get_active_emission` ищет `'active'` вместо `'impact'` |
| 6 | `database.py` | HIGH | `unequip_shells_bag` уничтожает ВСЕ гильзы |
| 7 | `random_events.py` | HIGH | `silent_horror` зациклен — финальная стадия недостижима |
| 8 | `handlers/commands.py` | HIGH | "Назад" в магазине — мёртвый код (`clear_shop_cache` не вызывается) |
| 9 | `main.py` | HIGH | "Назад" из инвентаря → город вместо кпп |
| 10 | `handlers/combat.py` | HIGH | `_skill_cooldowns` по `user_id`, `_active_skill_effects` по `player.vk_id` |

---

## 🟡 MEDIUM (14 — рекомендуется исправить)

| # | Файл | Строка | Баг |
|---|------|--------|-----|
| 11 | `state_manager.py` | 339-344 | ~~**TOCTOU race в `set_market_my_listings_page`**~~ — ✅ Исправлено: добавлен `LockedDict.update()` для атомарного read-modify-write |
| 12 | `main.py` | 460-474 | ~~**`lock.locked()` в `_process_callback_event`**~~ — ✅ Исправлено: заменено на `with lock:` контекстный менеджер, выделена `_do_callback_processing()` |
| 13 | `handlers/inventory.py` | ~1467 | ~~**`handle_sell_artifact` — несоответствие цены**~~ — ✅ Исправлено: формула `int(base_price * player.sell_bonus)` заменена на `int(base_price * (1 + player.sell_bonus / 100))` — совпадает с `sell_item_transaction` |
| 14 | `handlers/inventory.py` | ~675 | ~~**`handle_buy_item` не проверяет вес**~~ — ❌ Ложное срабатывание: `player.buy_item()` уже проверяет вес (строка 1047-1048 в `player.py`) |
| 15 | `handlers/market.py` | ~444 | ~~**`handle_market_input` дублирует `searching = True`**~~ — ✅ Исправлено: объединено в один атомарный `_market_browse_state.update()` вызов |
| 16 | `handlers/commands.py` | 17-20 vs 34-38 | **Затенение импортов** — `get_research_status`, `cancel_research` импортируются из `handlers.combat`, затем перезаписываются импортом из `state_manager`. Хрупкий код |
| 17 | `state_manager.py` | 260 | **`cleanup_inactive_states` никогда не вызывается** — состояния боя/исследования/покупок копятся в памяти. Memory leak при долгих сессиях бота |
| 18 | `random_events.py` | ~1955 | **Эффект `shells` не сохраняется в БД** — `_apply_event_choice` меняет `player.shells`, но не вызывает `database.update_user_stats` → гильзы из ивентов теряются |
| 19 | `random_events.py` | ~1930-1960 | **Эффект `reputation` игнорируется** — несколько ивентов имеют `"reputation": 10`, но `apply_event_choice` не обрабатывает этот тип эффекта |
| 20 | `random_events.py` | ~2007 | **`_apply_random_loot` использует `player.user_id`** — может не существовать в контексте исследования (остались 2-3 места, не все исправлены) |
| 21 | `database.py` | ~2493 | **`claim_daily_rewards` — импорт `STREAK_BONUSES` внутри функции** — если `daily_quests.py` изменится, краш при получении награды |
| 22 | `database.py` | ~2541 | **`reset_daily_quests_if_needed` — UTC vs `CURRENT_DATE`** — Python проверяет UTC дату, SQL использует `CURRENT_DATE` (серверный часовой пояс). Квесты могут сбрасываться в неожиданное время |
| 23 | `handlers/combat.py` | ~371 | **`TempPlayer.max_energy = player.max_health`** — семантически неверно. Если код когда-либо использует `temp_player.max_energy`, получит значение HP |
| 24 | `handlers/admin.py` | 6 и 12 | **Дублированный `import database`** — код-качество |

---

## 🟢 LOW (18 — косметические / не критичные)

| # | Файл | Строка | Баг |
|---|------|--------|-----|
| 25 | `database.py` | ~1367 | **SQL injection в `admin_set_user_field`** — `f"SET {field} = %s"` — защищён frozenset whitelist, но паттерн опасен при будущих изменениях |
| 26 | `database.py` | ~670 | **Мёртвая ветка `_insert_item` для 11-tuple** — `elif len(item) == 11: ... pass` — предметы с 11 элементами молча пропускаются |
| 27 | `database.py` | ~2048 | **`remove_shells` — `GREATEST(0, ...)` никогда не срабатывает** — `WHERE shells >= %s` предотвращает обновление, `GREATEST` мёртвый код |
| 28 | `database.py` | ~1725 | **`cursor.description` check в `get_market_user_listings`** — хрупкая проверка, должна всегда возвращать результат COUNT |
| 29 | `database.py` | ~1598 | **`get_market_listing_info` имеет side-effect** — вызывает `_expire_market_listings_tx` с `FOR UPDATE`, меняя данные при "чтении" |
| 30 | `database.py` | ~650 | **`_seed_items` не обновляет `backpack_bonus`/`rarity` при конфликте** — `ON CONFLICT DO UPDATE` не обновляет все поля, возможны устаревшие данные |
| 31 | `database.py` | ~2734 | **`record_emission_damage` создаёт таблицу при каждом вызове** — `CREATE TABLE IF NOT EXISTS` должен быть в `init_emission_table()` |
| 32 | `handlers/combat.py` | ~236 | **Docstring после кода в `handle_explore_time`** — `"""..."""` стоит после `cleanup_research_timers()`, это строка-выражение, а не докстринг |
| 33 | `handlers/combat.py` | ~445 | **`_select_research_event` — мёртвый код** — функция определена, но никогда не вызывается (заменена на `_select_research_event_by_chance`) |
| 34 | `handlers/combat.py` | ~493 | **`_combat_state` не используется в `_handle_research_event`** — импортируется но не используется |
| 35 | `handlers/combat.py` | ~1591 | **Второй `burst_count` в `_apply_skill_effect` — мёртвый код** — `elif "burst_count" in effect` после первого такого же — никогда не сработает. Навык пулемётчика "Шквал огня" не работает |
| 36 | `handlers/combat.py` | ~1959 | **`create_combat_keyboard()` без аргументов** — не покажет кнопку навыков (player=None) |
| 37 | `handlers/inventory.py` | ~1014 | **Shop cache не очищается при выходе из диалога** — `clear_shop_cache` вызывается только при входе в магазин, кэш копится в памяти |
| 38 | `handlers/inventory.py` | ~928 | **`handle_drop_item_by_index` отправляет 2 сообщения** — сначала обновлённый раздел, затем сообщение о дропе. Могут прийти в неправильном порядке |
| 39 | `handlers/market.py` | ~44 | **`_format_listing` — хрупкие `row['key']` без `.get()`** — если SQL-запрос изменится, KeyError. Сейчас работает, но хрупко |
| 40 | `main.py` | 254 | **`handle_event_response` вызывается дважды** — один раз в priority 3.6, второй раз в priority 7. Избыточная работа |
| 41 | `main.py` | 260 | **Нет `return` после `handle_unknown_command`** — стиль/консистентность (все остальные exit paths имеют `return`) |
| 42 | `handlers/commands.py` | 423-428 | **Мёртвый `is_at_kpp` check в `handle_kpp_shop_commands`** — после первой проверки `current_location_id == 'кпп'` гарантированно, вторая всегда False |

---

## 📊 Сводка по приоритетам

| Приоритет | Кол-во | Рекомендация |
|-----------|--------|--------------|
| 🔴 CRITICAL | 0 (было 4) | ✅ Все исправлены |
| 🟠 HIGH | 0 (было 6) | ✅ Все исправлены |
| 🟡 MEDIUM | 9 | Исправить в ближайшем обновлении |
| 🟢 LOW | 18 | Исправить по мере возможности |

---

## 🎯 Топ-5 для следующего спринта (MEDIUM)

1. **#17** — `cleanup_inactive_states` никогда не вызывается → memory leak
2. **#18** — Гильзы из ивентов теряются (не сохраняются в БД)
3. **#19** — Репутация из ивентов игнорируется
4. **#11** — TOCTOU race в маркете (пагинация)
5. **#12** — `lock.locked()` может вызвать `RuntimeError`

---

## 📝 Примечания

- Баги #1-10 были исправлены в этом спринте
- Баги #11-24 требуют изменений в логике (риск регрессии)
- Баги #25-42 — косметические / мёртвый код / code smell
- Все исправления прошли `py_compile` без ошибок
