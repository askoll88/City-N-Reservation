import ast
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = ("handlers", "game", "models")
FORBIDDEN_TEXT_MARKERS = ("**", "<b>", "</b>", "```")


class PlainTextUiTests(unittest.TestCase):
    def test_user_facing_string_literals_do_not_use_markdown_or_html(self):
        files = [PROJECT_ROOT / "main.py"]
        for directory in SCAN_DIRS:
            files.extend((PROJECT_ROOT / directory).glob("*.py"))

        violations = []
        for path in files:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                    continue
                value = node.value
                for marker in FORBIDDEN_TEXT_MARKERS:
                    if marker in value:
                        rel_path = path.relative_to(PROJECT_ROOT)
                        violations.append(f"{rel_path}:{node.lineno}: {marker}")

        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
