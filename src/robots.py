"""Lecture de robots.txt avec jokers '*' et '$' (urllib.robotparser les gere mal)."""
import re
import requests
from   config   import USER_AGENT, TIMEOUT_S

class Robots:
    def __init__(self, robots_url: str = None, text: str = None):
        if text is None:
            r = requests.get(robots_url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_S)
            r.raise_for_status()
            text   = r.text
        self.raw   = text
        self.rules = []
        applies    = False
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            k, v = (x.strip() for x in line.split(":", 1))
            k = k.lower()
            if k == "user-agent":
                applies = v == "*"
            elif k == "disallow" and applies and v:
                self.rules.append(self._to_regex(v))

    @staticmethod
    def _to_regex(pattern: str):
        anchored = pattern.endswith("$")
        body = re.escape(pattern.rstrip("$")).replace(r"\*", ".*")
        return re.compile("^" + body + ("$" if anchored else ""))

    def allowed(self, url: str) -> bool:
        path = re.sub(r"^https?://[^/]+", "", url) or "/"
        return not any(rx.search(path) for rx in self.rules)
