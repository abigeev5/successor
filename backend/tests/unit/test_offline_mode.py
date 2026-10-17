import httpx
import pytest

from app.core.config import Settings
from app.core.http import OfflineModeViolation, check_offline_config, is_local_host_literal, make_http_client


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("localhost", True),
        ("api.localhost", True),
        ("127.0.0.1", True),
        ("10.1.2.3", True),
        ("192.168.0.10", True),
        ("172.16.5.5", True),
        ("::1", True),
        ("llm", True),  # docker compose service name
        ("8.8.8.8", False),
        ("", False),
        ("api.openai.com", None),  # needs DNS
    ],
)
def test_is_local_host_literal(host: str, expected: bool | None) -> None:
    assert is_local_host_literal(host) is expected


def test_offline_config_flags_external_urls() -> None:
    settings = Settings(
        offline_mode=True, llm_base_url="http://8.8.8.8/v1", embeddings_base_url="http://llm:8000/v1"
    )
    assert check_offline_config(settings) == ["http://8.8.8.8/v1"]


def test_offline_config_is_ignored_when_online() -> None:
    assert check_offline_config(Settings(offline_mode=False, llm_base_url="http://8.8.8.8/v1")) == []


def test_offline_config_rejects_gigachat() -> None:
    assert check_offline_config(Settings(offline_mode=True, llm_provider="gigachat"))


async def test_http_client_blocks_external_requests_in_offline_mode() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    settings = Settings(offline_mode=True)
    async with make_http_client(settings, transport=httpx.MockTransport(handler)) as client:
        assert (await client.get("http://llm:8000/v1/models")).text == "ok"
        with pytest.raises(OfflineModeViolation):
            await client.get("http://8.8.8.8/v1/models")
