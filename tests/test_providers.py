"""Provider calls against a fake HTTP transport. No network, no API charges."""

from __future__ import annotations

import asyncio
import base64
import json
import os

import httpx
import pytest

from server import providers
from server.catalog import make_card_meta
from server.config import effective_settings

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

SETTINGS = {
    "local_image_backend": "a1111",
    "local_image_base_url": "http://sd.test",
    "local_image_model": "",
    "local_image_api_key": "",
    "local_image_steps": 20,
    "local_image_width": 512,
    "local_image_height": 512,
    "local_vision_base_url": "http://vision.test/v1",
    "local_vision_model": "llava",
    "local_vision_api_key": "ollama",
    "external_image_base_url": "https://api.example.test/v1",
    "external_image_model": "dall-e-3",
    "external_image_api_key": "sk-test",
    "external_vision_base_url": "https://api.example.test/v1",
    "external_vision_model": "gpt-4o-mini",
    "external_vision_api_key": "sk-test",
}


def use_settings(monkeypatch, **overrides):
    data = dict(SETTINGS)
    data.update(overrides)
    monkeypatch.setattr(providers, "effective_settings", lambda: data)
    return data


def install_transport(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real(*args, **kwargs)

    monkeypatch.setattr(providers.httpx, "AsyncClient", factory)


def test_local_a1111_posts_txt2img(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"images": [base64.b64encode(PNG).decode()]})

    use_settings(monkeypatch)
    install_transport(monkeypatch, handler)
    image = asyncio.run(providers.generate_image("local", "a keyboard"))
    assert image == PNG
    assert seen["url"] == "http://sd.test/sdapi/v1/txt2img"
    assert seen["auth"] is None
    assert seen["body"]["steps"] == 20
    assert seen["body"]["width"] == 512
    assert seen["body"]["height"] == 512
    assert "keyboard" in seen["body"]["prompt"]


def test_external_sends_bearer_and_square_size(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(PNG).decode()}]})

    use_settings(monkeypatch)
    install_transport(monkeypatch, handler)
    image = asyncio.run(providers.generate_image("external", "a laptop"))
    assert image == PNG
    assert seen["url"] == "https://api.example.test/v1/images/generations"
    assert seen["auth"] == "Bearer sk-test"
    assert seen["body"]["model"] == "dall-e-3"
    assert seen["body"]["size"] == "1024x1024"
    assert seen["body"]["response_format"] == "b64_json"


def test_external_retries_without_response_format_then_downloads_url(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path.endswith("/images/generations"):
            if len(calls) == 1:
                return httpx.Response(400, text="unknown parameter response_format")
            return httpx.Response(200, json={"data": [{"url": "https://cdn.example.test/card.png"}]})
        assert request.url.host == "cdn.example.test"
        return httpx.Response(200, content=PNG)

    use_settings(monkeypatch)
    install_transport(monkeypatch, handler)
    image = asyncio.run(providers.generate_image("external", "a mouse"))
    assert image == PNG
    assert calls == [
        "https://api.example.test/v1/images/generations",
        "https://api.example.test/v1/images/generations",
        "https://cdn.example.test/card.png",
    ]


def test_rejected_key(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid api key"}})

    use_settings(monkeypatch)
    install_transport(monkeypatch, handler)
    with pytest.raises(providers.ProviderError, match="密钥"):
        asyncio.run(providers.generate_image("external", "a car"))


def test_connection_refused(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    use_settings(monkeypatch)
    install_transport(monkeypatch, handler)
    with pytest.raises(providers.ProviderError, match="连不上模型服务"):
        asyncio.run(providers.generate_image("local", "a car"))


def test_external_image_requires_key(monkeypatch):
    use_settings(monkeypatch, external_image_api_key="")

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not call the network")

    install_transport(monkeypatch, handler)
    with pytest.raises(providers.ProviderError, match="密钥"):
        asyncio.run(providers.generate_image("external", "a car"))


def test_analyze_reads_fenced_json(monkeypatch):
    payload = {
        "items": [
            {"name": "机械键盘", "category": "keyboard", "summary": "银色键帽"},
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "gpt-4o-mini"
        assert request.headers["authorization"] == "Bearer sk-test"
        content = "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": content}}]},
        )

    use_settings(monkeypatch)
    install_transport(monkeypatch, handler)
    items = asyncio.run(
        providers.analyze_image("external", "data:image/jpeg;base64,aa", "")
    )
    assert items[0]["name"] == "机械键盘"
    assert items[0]["category"] == "keyboard"


def test_enrich_copy_replaces_attacks(monkeypatch):
    meta = make_card_meta("机械键盘", "keyboard", "external")

    def handler(request: httpx.Request) -> httpx.Response:
        content = json.dumps(
            {
                "attacks": [
                    {"name": "连打", "cost": 1, "damage": "60", "text": "连续按下三次。"},
                    {"name": "静音", "cost": 2, "damage": "", "text": "下一招伤害减少。"},
                ],
                "flavor": "键帽还温着。",
            },
            ensure_ascii=False,
        )
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    use_settings(monkeypatch)
    install_transport(monkeypatch, handler)
    ok = asyncio.run(providers.enrich_copy("external", meta, ""))
    assert ok is True
    assert meta["attacks"][0]["name"] == "连打"
    assert meta["flavor"] == "键帽还温着。"


def test_enrich_copy_keeps_template_when_service_fails(monkeypatch):
    meta = make_card_meta("机械键盘", "keyboard", "local")
    original = meta["attacks"][0]["name"]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "busy"}})

    use_settings(monkeypatch)
    install_transport(monkeypatch, handler)
    ok = asyncio.run(providers.enrich_copy("local", meta, ""))
    assert ok is False
    assert meta["attacks"][0]["name"] == original


@pytest.mark.skipif(os.getenv("MYGEAR_LIVE_EXTERNAL") != "1", reason="set MYGEAR_LIVE_EXTERNAL=1 to call the real API")
def test_live_external_image_returns_png():
    settings = effective_settings()
    if not settings["external_image_api_key"]:
        pytest.skip("external image key is empty")
    image = asyncio.run(
        providers.generate_image("external", "a single mechanical keyboard, no text")
    )
    assert image[:8] == b"\x89PNG\r\n\x1a\n"
