"""UI helper functions for consistent text HUD across the game."""

from __future__ import annotations


def _clamp(value: int, min_value: int, max_value: int) -> int:
    return max(min_value, min(max_value, value))


def pct(current: int, max_value: int) -> int:
    max_value = max(1, int(max_value))
    current = _clamp(int(current), 0, max_value)
    return int((current / max_value) * 100)


def bar(current: int, max_value: int, width: int = 12, fill: str = "#", empty: str = "-") -> str:
    """ASCII progress bar like [####------]."""
    max_value = max(1, int(max_value))
    current = _clamp(int(current), 0, max_value)
    width = max(4, int(width))
    filled = int((current / max_value) * width)
    return "[" + (fill * filled) + (empty * (width - filled)) + "]"


def meter_line(label: str, current: int, max_value: int, width: int = 12) -> str:
    value_pct = pct(current, max_value)
    return f"{label:<9} {bar(current, max_value, width=width)} {current}/{max_value} ({value_pct}%)"


def title(text: str) -> str:
    return f"== {text.upper()} =="


def section(text: str) -> str:
    return f"-- {text.upper()} --"
