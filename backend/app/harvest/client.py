"""HTTP client for harvesting — curl_cffi impersonating Chrome to clear TLS/JA3 + HTTP2 WAFs
that 403 a plain fetcher, with polite per-instance throttling and an honest User-Agent.
"""

from __future__ import annotations

import time

from curl_cffi import requests

# Honest, identifying UA — we harvest only public product data and want to be reachable.
_USER_AGENT = "DSourceAI-catalog-harvester/0.1 (+https://github.com/udsy19/DSource-AI)"


class HarvestClient:
    def __init__(self, throttle_s: float = 0.6, impersonate: str = "chrome131") -> None:
        self.throttle_s = throttle_s
        self.impersonate = impersonate
        self._last = 0.0

    def get_json(self, url: str, params: dict | None = None) -> dict:
        self._throttle()
        resp = requests.get(
            url, params=params, headers={"User-Agent": _USER_AGENT},
            impersonate=self.impersonate, timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def _throttle(self) -> None:
        elapsed = time.time() - self._last
        if elapsed < self.throttle_s:
            time.sleep(self.throttle_s - elapsed)
        self._last = time.time()
