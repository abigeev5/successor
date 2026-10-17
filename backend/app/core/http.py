"""HTTP client for model providers with the OFFLINE_MODE guard (SPEC, 12).

In offline mode only local addresses are allowed: localhost, private / loopback / link-local IPs,
single-label hostnames (docker compose service names) and names that resolve to private IPs only.
"""

import asyncio
import ipaddress
import socket
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.config import Settings
from app.core.errors import AppError


class OfflineModeViolation(AppError):
    status_code = 503
    code = "offline_mode_violation"
    detail = "Обращение к внешнему адресу запрещено в закрытом режиме (OFFLINE_MODE)"


def _is_private_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def is_local_host_literal(host: str) -> bool | None:
    """True/False when decidable without DNS; None when the name has to be resolved."""
    host = host.strip("[]").lower().rstrip(".")
    if not host:
        return False
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return _is_private_ip(host)
    if "." not in host:
        return True  # compose service name, e.g. "llm" or "db"
    return None


def _all_private(infos: list[Any]) -> bool:
    addresses = {info[4][0] for info in infos}
    return bool(addresses) and all(_is_private_ip(a) for a in addresses)


def is_local_url(url: str) -> bool:
    """Synchronous check (startup). Resolves DNS names when needed."""
    host = urlsplit(url).hostname or ""
    literal = is_local_host_literal(host)
    if literal is not None:
        return literal
    try:
        return _all_private(socket.getaddrinfo(host, None))
    except OSError:
        return False


async def is_local_url_async(url: str) -> bool:
    host = urlsplit(url).hostname or ""
    literal = is_local_host_literal(host)
    if literal is not None:
        return literal
    try:
        return _all_private(await asyncio.get_running_loop().getaddrinfo(host, None))
    except OSError:
        return False


def check_offline_config(settings: Settings) -> list[str]:
    """Configured model URLs that are not local. Empty list = OK. Called at startup when offline."""
    if not settings.offline_mode:
        return []
    urls = [settings.llm_base_url, settings.embeddings_base_url, settings.vlm_base_url]
    bad = [u for u in urls if u and not is_local_url(u)]
    if settings.llm_provider == "gigachat":
        bad.append("gigachat (облачный API)")
    return bad


def make_http_client(settings: Settings, **kwargs: Any) -> httpx.AsyncClient:
    async def _guard(request: httpx.Request) -> None:
        if settings.offline_mode and not await is_local_url_async(str(request.url)):
            raise OfflineModeViolation()

    hooks = kwargs.pop("event_hooks", {})
    hooks.setdefault("request", []).append(_guard)
    kwargs.setdefault("timeout", settings.llm_timeout_s)
    return httpx.AsyncClient(event_hooks=hooks, **kwargs)


def make_sync_http_client(settings: Settings, **kwargs: Any) -> httpx.Client:
    """Synchronous twin of make_http_client (embeddings are called from worker threads)."""

    def _guard(request: httpx.Request) -> None:
        if settings.offline_mode and not is_local_url(str(request.url)):
            raise OfflineModeViolation()

    hooks = kwargs.pop("event_hooks", {})
    hooks.setdefault("request", []).append(_guard)
    kwargs.setdefault("timeout", settings.llm_timeout_s)
    return httpx.Client(event_hooks=hooks, **kwargs)
