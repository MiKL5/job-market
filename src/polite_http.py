"""Session HTTP polie. Ce fichier ne s'appelle PAS http.py : il masquerait le module standard `http`,
dont `requests` depend, des que src/ est dans le chemin d'import."""
import time
import requests
from   config   import USER_AGENT, DELAY_S, TIMEOUT_S

class PoliteSession:
    def __init__(self, delay_s=DELAY_S):
        self.delay_s = delay_s
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "fr-FR,fr;q=0.9"})
        self._last = 0.0

    def get(self, url, **kw):
        wait = self.delay_s - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        try:
            return self.s.get(url, timeout=TIMEOUT_S, **kw)
        finally:
            self._last = time.monotonic()
