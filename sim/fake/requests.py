"""Fake HTTP: answers from sim/fixtures by URL keyword."""

import json

FIXTURES = {
    "open-meteo": "weather.json",
    "hacker-news": "hn.json",
}


class Response:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        return json.loads(self._body)

    @property
    def text(self):
        return self._body

    @property
    def content(self):
        return self._body.encode()

    def close(self):
        pass


def get(url, timeout=None, headers=None):
    import simpaths
    for key, name in FIXTURES.items():
        if key in url:
            with open(simpaths.FIXTURES + "/" + name) as f:
                return Response(200, f.read())
    return Response(404, "{}")
