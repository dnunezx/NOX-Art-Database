from noxart.common import safe_path


def candidates(game, root, client, config, refresh=False):
    source = game.get("source") or {}
    if refresh and source.get("provider") not in {None, "local"}:
        return []
    if source.get("path"):
        path = safe_path(root / "sources", source["path"])
        if path.is_file():
            return [{"provider": "local", **source, "path": source["path"]}]
    # Exact Title ID directory names only; title similarity never establishes identity.
    names = [f"{game['title_id']}.png"] + [f"{game['title_id']}/{name}" for name in ("ICON0.PNG", "PIC0.PNG", "PIC1.PNG")]
    return [{"provider": "local", "path": name, "redistribution": "unverified"}
            for name in names if safe_path(root / "sources", name).is_file()]
