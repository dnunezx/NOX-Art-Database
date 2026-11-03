"""Static native squares only. No cropping, stretching, rotation or composition."""
import io
import warnings
from pathlib import Path

from PIL import Image, ImageStat, UnidentifiedImageError


def inspect_source(path, config):
    path = Path(path)
    if not 32 <= path.stat().st_size <= config["max_source_bytes"]:
        raise ValueError("Source file size outside allowed limits")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                if image.width * image.height > config["max_pixels"] or image.size not in {(512, 512), (1024, 1024)}:
                    raise ValueError("Source must be a native 512x512 or 1024x1024 square")
                if image.format not in {"PNG", "JPEG", "WEBP"} or getattr(image, "n_frames", 1) != 1:
                    raise ValueError("Only static PNG, JPEG and WebP images are supported")
                if image.mode not in {"RGB", "RGBA", "P", "L", "LA", "CMYK"}:
                    raise ValueError("Unsupported source color mode")
                dimensions, source_format = list(image.size), image.format
                image.verify()
            with Image.open(path) as image:
                image.load()
                rgba = image.convert("RGBA")
                if rgba.getchannel("A").getextrema()[1] == 0:
                    raise ValueError("Fully transparent source")
                stat = ImageStat.Stat(rgba.convert("RGB").resize((64, 64)))
                if max(stat.stddev) == 0:
                    raise ValueError("Blank source image")
                notes = ["Low color variation: inspect for placeholders or intentional minimalism"] if max(stat.stddev) < 5 else []
                return {"dimensions": dimensions, "format": source_format, "warnings": notes}
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError("Corrupt or unsafe source image") from None


def square_image(path, settings=None, size=512):
    with Image.open(path) as image:
        if image.size not in {(512, 512), (1024, 1024)} or getattr(image, "n_frames", 1) != 1:
            raise ValueError("Native static square artwork required; rectangular covers are never cropped")
        result = image.convert("RGBA" if image.mode in {"RGBA", "LA"} or "transparency" in image.info else "RGB")
    method = "native-square" if result.width == size else "downscale-square"
    if result.size != (size, size):
        result = result.resize((size, size), Image.Resampling.LANCZOS)
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
            if image.format != "PNG" or image.size != (size, size) or image.mode not in {"RGB", "RGBA"} or getattr(image, "n_frames", 1) != 1:
                raise ValueError(f"Invalid static PNG dimensions, format or mode: {path.name}")
            image.verify()
        with Image.open(path) as image:
            image.load()
    except (OSError, UnidentifiedImageError):
        raise ValueError(f"Corrupt PNG: {path.name}") from None
