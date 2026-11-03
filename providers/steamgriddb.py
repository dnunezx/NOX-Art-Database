"""Official SteamGridDB API v2; credentials never leave API requests."""
import os
from urllib.parse import quote, urlencode

from noxart.http import AuthenticationError

BASE = "https://www.steamgriddb.com/api/v2"


class ResponseError(RuntimeError):
    pass


class SteamGridDB:
    def __init__(self, client, token=None, refresh=False):
        self.token = token if token is not None else os.environ.get("STEAMGRIDDB_API_KEY", "")
        if not self.token.strip():
            raise AuthenticationError("STEAMGRIDDB_API_KEY is missing; configure the Actions secret")
        self.client, self.refresh = client, refresh

    def request(self, path, collection=False):
        response = self.client.json(BASE + path, ["www.steamgriddb.com"],
                                    {"Authorization": "Bearer " + self.token}, self.refresh)
        if not isinstance(response, dict) or response.get("success") is not True:
            raise ResponseError("SteamGridDB returned an unsuccessful or invalid response")
        data = response.get("data")
        if not isinstance(data, list if collection else dict):
            raise ResponseError("SteamGridDB response has an invalid data field")
        if collection and any(not isinstance(row, dict) for row in data):
            raise ResponseError("SteamGridDB returned an invalid item")
        return data

    def search(self, query):
        rows = self.request("/search/autocomplete/" + quote(query, safe=""), collection=True)
        for row in rows:
            self.validate_game(row)
        return rows

    @staticmethod
    def validate_game(row):
        if type(row.get("id")) is not int or row["id"] <= 0 or not isinstance(row.get("name"), str):
            raise ResponseError("Invalid SteamGridDB game identity")
        if row.get("release_date") is not None and type(row["release_date"]) not in (int, float):
            raise ResponseError("Invalid SteamGridDB release date")

    def game(self, ident):
        row = self.request(f"/games/id/{ident}")
        self.validate_game(row)
        if row["id"] != ident:
            raise ResponseError("SteamGridDB game ID does not match request")
        return row

    def grids(self, ident, size):
        query = urlencode({"dimensions": f"{size}x{size}", "types": "static",
                           "nsfw": "false", "humor": "false", "epilepsy": "false"})
        rows = self.request(f"/grids/game/{ident}?{query}", collection=True)
        for row in rows:
            if (type(row.get("id")) is not int or row["id"] <= 0
                    or not isinstance(row.get("url"), str)
                    or type(row.get("width")) is not int or type(row.get("height")) is not int):
                raise ResponseError("Invalid SteamGridDB grid metadata")
        return rows

    def grid(self, ident):
        row = self.request(f"/grids/{ident}")
        if row.get("id") != ident or not isinstance(row.get("url"), str):
            raise ResponseError("Invalid selected SteamGridDB asset")
        return row
