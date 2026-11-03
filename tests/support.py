import shutil
import tempfile
from pathlib import Path

from noxart.common import read_json, write_json
from noxart.pipeline import generate
from scripts.create_samples import create

REPOSITORY = Path(__file__).resolve().parents[1]


class ArtworkFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copy(REPOSITORY / "config.json", self.root / "config.json")
        self.config = read_json(self.root / "config.json")
        self.games = create(self.root)
        write_json(self.root / "database/games.json", self.games)

    def build(self):
        return generate(self.root)

    def database(self):
        return read_json(self.root / "database/games.json")
