import ast
import os
import sys


def iter_python_files():
    skipped_dirs = {".git", "__pycache__", "venv", ".venv"}
    for root, dirs, filenames in os.walk("."):
        dirs[:] = [d for d in dirs if d not in skipped_dirs]
        for filename in filenames:
            if filename.endswith(".py"):
                yield os.path.relpath(os.path.join(root, filename), ".")

print("=" * 50)
print("ПРОВЕРКА СИНТАКСИСА PYTHON")
print("=" * 50)

errors = []
for filepath in sorted(iter_python_files()):
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
