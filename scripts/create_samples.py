"""Create original geometric sample art, dedicated to CC0-1.0. No game art."""
import json
from pathlib import Path

from PIL import Image, ImageDraw

from noxart.common import write_json
from noxart.imaging import save_png


def create(root):
    root = Path(root)
    games = []
    for number, (name, dimensions, color) in enumerate((
        ("square", (640, 640), (60, 155, 230)),
        ("portrait", (480, 800), (230, 100, 65)),
        ("landscape", (960, 540), (130, 100, 225)),
        ("transparent", (640, 360), (60, 205, 160))), 1):
        image = Image.new("RGBA", dimensions, (15, 20, 35, 0 if name == "transparent" else 255))
        draw = ImageDraw.Draw(image)
        width, height = dimensions
        for i in range(12):
            inset = i * min(dimensions) // 28
            draw.rectangle((inset, inset, width - inset - 1, height - inset - 1), outline=(*color, 255), width=3)
        draw.ellipse((width // 3, height // 3, width * 2 // 3, height * 2 // 3), fill=(*color, 255))
        draw.text((width // 8, height // 8), "NOX SAMPLE / " + name.upper(), fill="white", font_size=24)
        save_png(image, root / f"sources/samples/{name}.png")
        games.append({"title_id": f"NOXS{number:05d}", "title": f"NOX synthetic {name} demo",
                      "platform": "PS3", "region": "DEMO", "artwork_status": "missing", "review_status": "pending",
                      "source": {"provider": "local", "path": f"samples/{name}.png", "attribution": "NOX Art Database original geometric demo",
                                 "license": "CC0-1.0", "permission_evidence": "sources/samples/LICENSE.txt",
                                 "redistribution": "approved"}})
    write_json(root / "examples/games.json", games)
    return games


if __name__ == "__main__":
    create(Path.cwd())
    print("Created four original fixtures; NOXS identifiers are synthetic, not real PS3 games")
