"""RN-009 — verificacao de robots.txt por host, com cache de 24h."""
from __future__ import annotations

import logging
import time
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

logger = logging.getLogger("zleilao.robots")

_cache: dict[str, tuple[RobotFileParser | None, float]] = {}
TTL = 24 * 3600


async def robots_allows(url: str, user_agent: str, path: str = "/") -> tuple[bool, str]:
    """Devolve (permitido, status) com status em allowed | disallowed | unknown.
    Sem robots.txt (404) ou erro de rede => permitido, status unknown."""
    parts = urlsplit(url)
    host_key = f"{parts.scheme}://{parts.netloc}"
    now = time.time()
    rp, ts = _cache.get(host_key, (None, 0.0))
    if rp is None or now - ts > TTL:
        rp = RobotFileParser()
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers={"User-Agent": user_agent}) as client:
                resp = await client.get(f"{host_key}/robots.txt")
            if resp.status_code == 200 and "<html" not in resp.text[:200].lower():
                rp.parse(resp.text.splitlines())
            else:
                _cache[host_key] = (None, now)
                return True, "unknown"
        except Exception as exc:
            logger.debug("robots.txt indisponivel em %s: %s", host_key, exc)
            _cache[host_key] = (None, now)
            return True, "unknown"
        _cache[host_key] = (rp, now)
    if rp is None:
        return True, "unknown"
    allowed = rp.can_fetch(user_agent, f"{host_key}{path}") and rp.can_fetch("*", f"{host_key}{path}")
    return allowed, "allowed" if allowed else "disallowed"
