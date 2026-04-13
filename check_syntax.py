import ast
import sys
import os

files = [
    'main.py',
    'config.py', 
    'database.py',
    'player.py',
    'state_manager.py',
    'errors.py',
    'constants.py',
    'classes.py',
    'anomalies.py',
    'enemies.py',
    'locations.py',
    'npcs.py',
    'handlers/admin.py',
    'handlers/combat.py',
    'handlers/commands.py',
    'handlers/inventory.py',
    'handlers/keyboards.py',
    'handlers/location.py',
    'handlers/market.py',
    'handlers/npc.py',
]

print("=" * 50)
print("ПРОВЕРКА СИНТАКСИСА PYTHON")
print("=" * 50)

errors = []
for filepath in files:
    if not os.path.exists(filepath):
        errors.append(f"❌ НЕ НАЙДЕН: {filepath}")
        continue
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        ast.parse(source)
        print(f"✅ OK: {filepath}")
    except SyntaxError as e:
        error_msg = f"❌ СИНТАКСИС {filepath}: строка {e.lineno}, {e.msg}"
        errors.append(error_msg)
        print(error_msg)
    except Exception as e:
        error_msg = f"❌ ОШИБКА {filepath}: {type(e).__name__}: {e}"
        errors.append(error_msg)
        print(error_msg)

print("=" * 50)
if errors:
    print(f"\nНАЙДЕНО ОШИБОК: {len(errors)}")
    for err in errors:
        print(err)
    sys.exit(1)
else:
    print("\n✅ ВСЕ ФАЙЛЫ ПРОШЛИ ПРОВЕРКУ СИНТАКСИСА")
    sys.exit(0)
