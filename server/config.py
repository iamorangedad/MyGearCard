"""Paths and deployment settings.

Configuration comes from the process environment and the project .env file.
There is no settings page.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

DATA = ROOT / "data"
UPLOADS = DATA / "uploads"
CARDS = DATA / "cards"
SAMPLES = DATA / "samples"
DB_PATH = DATA / "mygearcard.db"
WEB = ROOT / "web"

DEFAULTS: dict = {
    "local_vision_base_url": "http://127.0.0.1:11434/v1",
    "local_vision_model": "llava",
    "local_vision_api_key": "ollama",
    "local_image_backend": "a1111",
    "local_image_base_url": "http://127.0.0.1:7860",
    "local_image_model": "",
    "local_image_api_key": "",
    "local_image_steps": 22,
    "local_image_width": 768,
    "local_image_height": 512,
    "external_vision_base_url": "https://api.openai.com/v1",
    "external_vision_model": "gpt-4o-mini",
    "external_vision_api_key": "",
    "external_image_base_url": "https://api.openai.com/v1",
    "external_image_model": "dall-e-3",
    "external_image_api_key": "",
    "card_price_cents": 2900,
    "shipping_cents": 1200,
}

INT_KEYS = {
    "local_image_steps",
    "local_image_width",
    "local_image_height",
    "card_price_cents",
    "shipping_cents",
}

ENV_MAP = {
    "MYGEAR_LOCAL_VISION_BASE_URL": "local_vision_base_url",
    "MYGEAR_LOCAL_VISION_MODEL": "local_vision_model",
    "MYGEAR_LOCAL_VISION_API_KEY": "local_vision_api_key",
    "MYGEAR_LOCAL_IMAGE_BACKEND": "local_image_backend",
    "MYGEAR_LOCAL_IMAGE_BASE_URL": "local_image_base_url",
    "MYGEAR_LOCAL_IMAGE_MODEL": "local_image_model",
    "MYGEAR_LOCAL_IMAGE_API_KEY": "local_image_api_key",
    "MYGEAR_LOCAL_IMAGE_STEPS": "local_image_steps",
    "MYGEAR_LOCAL_IMAGE_WIDTH": "local_image_width",
    "MYGEAR_LOCAL_IMAGE_HEIGHT": "local_image_height",
    "MYGEAR_EXTERNAL_VISION_BASE_URL": "external_vision_base_url",
    "MYGEAR_EXTERNAL_VISION_MODEL": "external_vision_model",
    "MYGEAR_EXTERNAL_VISION_API_KEY": "external_vision_api_key",
    "MYGEAR_EXTERNAL_IMAGE_BASE_URL": "external_image_base_url",
    "MYGEAR_EXTERNAL_IMAGE_MODEL": "external_image_model",
    "MYGEAR_EXTERNAL_IMAGE_API_KEY": "external_image_api_key",
    "MYGEAR_CARD_PRICE_CENTS": "card_price_cents",
    "MYGEAR_SHIPPING_CENTS": "shipping_cents",
}


def ensure_dirs() -> None:
    for path in (DATA, UPLOADS, CARDS, SAMPLES):
        path.mkdir(parents=True, exist_ok=True)


def _env_layer() -> dict:
    found = {}
    for env_name, key in ENV_MAP.items():
        raw = os.getenv(env_name)
        if raw is None or raw.strip() == "":
            continue
        found[key] = raw.strip()
    return found


def effective_settings() -> dict:
    ensure_dirs()
    data = dict(DEFAULTS)
    for key, value in _env_layer().items():
        data[key] = value
    return _coerce_all(data)


def _coerce_all(data: dict) -> dict:
    cleaned = dict(DEFAULTS)
    for key in DEFAULTS:
        cleaned[key] = _coerce(key, data.get(key, DEFAULTS[key]))
    return cleaned


def _coerce(key: str, value):
    if key in INT_KEYS:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = int(DEFAULTS[key])
        if key == "local_image_steps":
            return max(8, min(40, number))
        if key in {"local_image_width", "local_image_height"}:
            number = max(384, min(1024, number))
            return number - (number % 64) or 384
        if key == "card_price_cents":
            return max(100, min(200000, number))
        if key == "shipping_cents":
            return max(0, min(50000, number))
        return number
    if key == "local_image_backend":
        return value if value in {"a1111", "openai"} else "a1111"
    text = "" if value is None else str(value).strip()
    return text


def provider_status(settings: dict | None = None) -> dict:
    s = settings or effective_settings()
    local_image_ready = bool(s["local_image_base_url"]) and (
        s["local_image_backend"] == "a1111" or bool(s["local_image_model"])
    )
    return {
        "local_vision": bool(s["local_vision_base_url"] and s["local_vision_model"]),
        "local_image": local_image_ready,
        "external_vision": bool(
            s["external_vision_base_url"]
            and s["external_vision_model"]
            and s["external_vision_api_key"]
        ),
        "external_image": bool(
            s["external_image_base_url"]
            and s["external_image_model"]
            and s["external_image_api_key"]
        ),
        "prices": {
            "unit": s["card_price_cents"],
            "shipping": s["shipping_cents"],
        },
        "local_image_backend": s["local_image_backend"],
    }
