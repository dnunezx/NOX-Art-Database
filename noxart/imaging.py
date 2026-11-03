from __future__ import annotations

import io
import math
import warnings
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError


def inspect_source(path, config):
    path = Path(path)
    if not 32 <= path.stat().st_size <= config["max_source_bytes"]:
        raise ValueError("Source file size outside allowed limits")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                width, height = image.size
                if width * height > config["max_pixels"] or min(width, height) < config["min_source_side"]:
                    raise ValueError("Source resolution outside allowed limits")
                if max(width, height) / min(width, height) > config["max_aspect_ratio"]:
                    raise ValueError("Source aspect ratio outside allowed limits")
                if image.format not in {"PNG", "JPEG", "WEBP"} or getattr(image, "n_frames", 1) != 1:
                    raise ValueError("Only static PNG, JPEG and WebP images are supported")
                image.verify()
            with Image.open(path) as image:
                image.load()
                rgba = image.convert("RGBA")
                if rgba.getchannel("A").getextrema()[1] == 0:
                    raise ValueError("Fully transparent source")
                rgb = Image.new("RGB", rgba.size, (32, 32, 40))
                rgb.paste(rgba, mask=rgba.getchannel("A"))
                stat = ImageStat.Stat(rgb.resize((64, 64)))
                if max(stat.stddev) == 0:
                    raise ValueError("Blank source image")
                notes = []
                if max(stat.stddev) < 5:
                    notes.append("Low color variation: inspect for placeholders or intentional minimalism")
                if path.stat().st_size < 1024:
                    notes.append("Suspiciously small source file: visual review required")
                return {"dimensions": [width, height], "warnings": notes}
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ValueError("Corrupt or unsafe source image") from error


def square_image(path, settings, size=512):
    method = settings.get("method", "auto")
    zoom = float(settings.get("zoom", 1))
    rotation = float(settings.get("rotation", 0))
    focal = settings.get("focal_point", [0.5, 0.5])
    if (method not in {"auto", "crop", "fit"} or not math.isfinite(zoom) or not 1 <= zoom <= 4
            or not math.isfinite(rotation) or abs(rotation) > 360 or len(focal) != 2
            or any(not math.isfinite(float(x)) or not 0 <= float(x) <= 1 for x in focal)
            or settings.get("background", "blur") not in {"blur", "dark"}):
        raise ValueError("Invalid processing settings")
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGBA")
    if rotation:
        image = image.rotate(rotation, Image.Resampling.BICUBIC, expand=True)
    # Opaque matte prevents transparent letterbox regions from becoming black bars.
    matte = Image.new("RGB", image.size, (32, 32, 40))
    matte.paste(image, mask=image.getchannel("A"))
    if settings.get("preserve_full") or (method == "auto" and max(image.size) / min(image.size) > 1.15):
        method = "fit"
    elif method == "auto":
        method = "crop"
    if method == "fit":
        background = ImageOps.fit(matte, (size, size), Image.Resampling.LANCZOS)
        if settings.get("background", "blur") == "blur":
            background = background.filter(ImageFilter.GaussianBlur(size / 24))
        background = ImageEnhance.Brightness(background).enhance(0.55)
        foreground = ImageOps.contain(image, (size, size), Image.Resampling.LANCZOS)
        background.paste(foreground, ((size - foreground.width) // 2, (size - foreground.height) // 2), foreground)
        result = background
    else:
        side = min(matte.size) / zoom
        left = min(max(float(focal[0]) * matte.width - side / 2, 0), matte.width - side)
        top = min(max(float(focal[1]) * matte.height - side / 2, 0), matte.height - side)
        result = matte.resize((size, size), Image.Resampling.LANCZOS, box=(left, top, left + side, top + side))
    return result, method


def save_png(image, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    data = buffer.getvalue()
    if not path.exists() or path.read_bytes() != data:
        temporary = path.with_suffix(".png.tmp")
        temporary.write_bytes(data)
        temporary.replace(path)


def validate_png(path, size, config):
    path = Path(path)
    if not path.is_file() or not 32 <= path.stat().st_size <= config["max_output_bytes"]:
        raise ValueError(f"Missing or oversized PNG: {path.name}")
    try:
        with Image.open(path) as image:
            if image.format != "PNG" or image.size != (size, size) or image.mode not in {"RGB", "RGBA"}:
                raise ValueError(f"Invalid PNG dimensions, format or mode: {path.name}")
            image.verify()
        with Image.open(path) as image:
            image.load()
    except (OSError, UnidentifiedImageError) as error:
        raise ValueError(f"Corrupt PNG: {path.name}") from error
