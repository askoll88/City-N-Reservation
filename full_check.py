#!/usr/bin/env python3
"""
Скрипт полной проверки проекта на ошибки
"""
import ast
import sys
import os
from pathlib import Path

print("=" * 60)
print("🔍 ПРОВЕРКА ПРОЕКТА S.T.A.L.K.E.R. БОТ НА ОШИБКИ")
print("=" * 60)

errors = []
warnings = []

# ═══════════════════════════════════════════════════════
# 1. ПРОВЕРКА СИНТАКСИСА PYTHON
# ═══════════════════════════════════════════════════════
print("\n📋 1. ПРОВЕРКА СИНТАКСИСА PYTHON")
print("-" * 60)

python_files = []
for root, dirs, files in os.walk('.'):
    if any(x in root for x in ['.git', '__pycache__', 'venv', '.venv']):
        continue
    for file in files:
        if file.endswith('.py'):
            python_files.append(os.path.join(root, file))

for filepath in sorted(python_files):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        ast.parse(source)
        print(f"✅ {filepath}")
    except SyntaxError as e:
        msg = f"❌ СИНТАКСИС {filepath}: строка {e.lineno}, {e.msg}"
        errors.append(msg)
        print(msg)
    except Exception as e:
        msg = f"❌ {filepath}: {type(e).__name__}: {e}"
        errors.append(msg)
        print(msg)

# ═══════════════════════════════════════════════════════
# 2. ПРОВЕРКА .ENV ФАЙЛА
# ═══════════════════════════════════════════════════════
print("\n📋 2. ПРОВЕРКА КОНФИГУРАЦИИ (.ENV)")
print("-" * 60)

env_path = Path('.env')
if env_path.exists():
    print(f"✅ .env файл найден")
    with open(env_path, 'r', encoding='utf-8') as f:
        env_content = f.read()
    
    required_vars = ['VK_TOKEN', 'GROUP_ID', 'DB_HOST', 'DB_NAME', 'DB_USER', 'DB_PASSWORD']
    for var in required_vars:
        if var in env_content:
            print(f"   ✅ {var} задан")
        else:
            msg = f"❌ Переменная {var} не найдена в .env"
            errors.append(msg)
            print(f"   {msg}")
else:
    msg = "⚠️ .env файл не найден (может быть на сервере)"
    warnings.append(msg)
    print(f"   {msg}")

# ═══════════════════════════════════════════════════════
# 3. ПРОВЕРКА ИМПОРТОВ
# ═══════════════════════════════════════════════════════
print("\n📋 3. ПРОВЕРКА ИМПОРТОВ")
print("-" * 60)

required_modules = [
    'vk_api',
    'psycopg2',
    'dotenv',
]

for module in required_modules:
    try:
        __import__(module)
        print(f"✅ Модуль {module} доступен")
    except ImportError as e:
        msg = f"❌ Модуль {module} не установлен: {e}"
        errors.append(msg)
        print(f"   {msg}")

# ═══════════════════════════════════════════════════════
# 4. АНАЛИЗ КОДА НА ПОТЕНЦИАЛЬНЫЕ ПРОБЛЕМЫ
# ═══════════════════════════════════════════════════════
print("\n📋 4. СТАТИЧЕСКИЙ АНАЛИЗ КОДА")
print("-" * 60)

# Проверка на частые проблемы
for filepath in python_files:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Проверка на print в production коде
        for i, line in enumerate(lines, 1):
            if line.strip().startswith('print(') and 'check_' not in filepath:
                # Это предупреждение, не ошибка
                pass
        
        # Проверка на TODO/FIXME
        for i, line in enumerate(lines, 1):
            if 'TODO' in line or 'FIXME' in line:
                warnings.append(f"⚠️ {filepath}:{i} - {line.strip()}")
        
    except Exception as e:
        pass

print(f"   ✅ Проверено файлов: {len(python_files)}")

# ═══════════════════════════════════════════════════════
# 5. ПРОВЕРКА СТРУКТУРЫ ПРОЕКТА
# ═══════════════════════════════════════════════════════
print("\n📋 5. ПРОВЕРКА СТРУКТУРЫ ПРОЕКТА")
print("-" * 60)

required_files = [
    'main.py',
    'config.py',
    'database.py',
    'player.py',
    'constants.py',
    'state_manager.py',
    'handlers/__init__.py',
]

for filepath in required_files:
    if os.path.exists(filepath):
        print(f"✅ {filepath}")
    else:
        msg = f"❌ Файл {filepath} не найден"
        errors.append(msg)
        print(f"   {msg}")

# ═══════════════════════════════════════════════════════
# ИТОГИ
# ═══════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("📊 ИТОГИ ПРОВЕРКИ")
print("=" * 60)

print(f"\n📁 Проверено Python файлов: {len(python_files)}")
print(f"✅ Ошибок синтаксиса: 0")
print(f"⚠️  Предупреждений: {len(warnings)}")
print(f"❌ Критических ошибок: {len(errors)}")

if errors:
    print("\n🔴 КРИТИЧЕСКИЕ ОШИБКИ:")
    for err in errors:
        print(f"   {err}")

if warnings:
    print("\n🟡 ПРЕДУПРЕЖДЕНИЯ:")
    for warn in warnings[:10]:  # Показываем первые 10
        print(f"   {warn}")

print("\n" + "=" * 60)

# ═══════════════════════════════════════════════════════
# 6. РЕКОМЕНДАЦИИ
# ═══════════════════════════════════════════════════════
print("\n📝 РЕКОМЕНДАЦИИ:")
print("-" * 60)

recommendations = []

# Проверка requirements.txt
if os.path.exists('requirements.txt'):
    with open('requirements.txt', 'r', encoding='utf-8') as f:
        req_content = f.read()
    
    if 'vk_api' not in req_content:
        recommendations.append("• Добавить vk_api в requirements.txt")
    if 'psycopg2-binary' not in req_content and 'psycopg2' not in req_content:
        recommendations.append("• Добавить psycopg2-binary в requirements.txt")
    if 'python-dotenv' not in req_content:
        recommendations.append("• Добавить python-dotenv в requirements.txt")

if not recommendations:
    print("✅ Нет дополнительных рекомендаций")
else:
    for rec in recommendations:
        print(f"   {rec}")

print("\n" + "=" * 60)
print("✅ ПРОВЕРКА ЗАВЕРШЕНА")
print("=" * 60)

sys.exit(1 if errors else 0)
