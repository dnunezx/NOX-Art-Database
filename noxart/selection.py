"""Rank metadata deterministically without claiming to classify visual content."""
import math


def acceptable(row, size=None):
    width, height = row.get("width"), row.get("height")
    if width != height or width not in (512, 1024) or (size and width != size):
        return False
    if row.get("mime") and row["mime"] not in {"image/png", "image/jpeg", "image/webp"}:
        return False
    if row.get("type", "static") != "static":
        return False
    if any(row.get(flag) not in (None, False, 0, "false", "0") for flag in ("nsfw", "humor", "epilepsy", "animated")):
        return False
    return True


def score(row):
    value = row.get("score", 0)
    return float(value) if type(value) in (int, float) and math.isfinite(value) else 0


def ranked(rows, size=None):
    return sorted((r for r in rows if acceptable(r, size)), key=lambda r: (r["width"] != 512, -score(r), r["id"]))
