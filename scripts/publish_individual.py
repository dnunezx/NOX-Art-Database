from pathlib import Path
from noxart.individual import individual_index

if __name__ == "__main__":
    result = individual_index(Path.cwd())
    print(f"Individual index: {sum(e['status'] == 'available' for e in result['games'].values())} hosted PNGs, {len(result['games'])} titles")
