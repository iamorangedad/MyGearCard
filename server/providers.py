"""Local and external model calls.

Image backends:
- a1111: Automatic1111 / SD.Next  POST {base}/sdapi/v1/txt2img
- openai: OpenAI-compatible       POST {base}/images/generations

Vision and card copy use an OpenAI-compatible chat endpoint.
"""

from __future__ import annotations

import base64
import json
import logging
import re

import httpx

from .catalog import COPY_SYSTEM, apply_model_copy, copy_user_prompt
from .config import effective_settings

log = logging.getLogger("mygearcard")


class ProviderError(Exception):
    pass


def _join(base: str, path: str) -> str:
    return base.rstrip("/") + "/" + path.lstrip("/")


def _headers(api_key: str) -> dict:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _error_text(response: httpx.Response) -> str:
    if response.status_code in {401, 403}:
        return "模型服务拒绝了密钥，请到设置里检查。"
    try:
        payload = response.json()
    except json.JSONDecodeError:
        payload = None
    message = ""
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            message = str(err.get("message") or "")
        elif isinstance(err, str):
            message = err
        message = message or str(payload.get("detail") or payload.get("message") or "")
    message = re.sub(r"\s+", " ", message).strip()
    if len(message) > 180:
        message = message[:180] + "…"
    if message:
        return f"模型服务返回 {response.status_code}：{message}"
    return f"模型服务返回 {response.status_code}。"


def _extract_json(text: str):
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        return json.loads(raw[start : end + 1])
    raise ValueError("没有解析到 JSON")


def _message_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(str(part.get("text") or ""))
        return "\n".join(parts)
    return str(content or "")


async def _request(method: str, url: str, api_key: str, payload: dict | None, timeout: float) -> httpx.Response:
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=8.0)) as client:
            response = await client.request(method, url, headers=_headers(api_key), json=payload)
    except httpx.ConnectError as exc:
        raise ProviderError("连不上模型服务。请确认它已经启动，地址和端口没有写错。") from exc
    except httpx.TimeoutException as exc:
        raise ProviderError("模型响应超时。本地出图可以把分辨率和步数调低后再试。") from exc
    except httpx.HTTPError as exc:
        raise ProviderError("连接模型服务时中断了，请再试一次。") from exc
    return response


def _image_target(settings: dict, provider: str) -> tuple[str, str, str, str]:
    if provider == "local":
        backend = settings["local_image_backend"]
        base = settings["local_image_base_url"]
        model = settings["local_image_model"]
        key = settings["local_image_api_key"]
        if not base:
            raise ProviderError("还没填写本地出图地址。")
        if backend == "openai" and not model:
            raise ProviderError("本地 OpenAI 兼容出图需要填写模型名。")
        return backend, base, model, key
    if provider == "external":
        base = settings["external_image_base_url"]
        model = settings["external_image_model"]
        key = settings["external_image_api_key"]
        if not base or not model or not key:
            raise ProviderError("外部出图还没配齐地址、模型名和密钥。")
        return "openai", base, model, key
    raise ProviderError("未知的出图方式。")


def _vision_target(settings: dict, provider: str) -> tuple[str, str, str]:
    if provider == "local":
        base = settings["local_vision_base_url"]
        model = settings["local_vision_model"]
        key = settings["local_vision_api_key"]
        if not base or not model:
            raise ProviderError("还没配置本地视觉模型。你可以跳过识别，直接填写装备名称。")
        return base, model, key
    if provider == "external":
        base = settings["external_vision_base_url"]
        model = settings["external_vision_model"]
        key = settings["external_vision_api_key"]
        if not base or not model or not key:
            raise ProviderError("外部识别还没配齐地址、模型名和密钥。你可以先手动填写装备名称。")
        return base, model, key
    raise ProviderError("未知的识别方式。")


async def _decode_image_payload(data: dict) -> bytes:
    items = data.get("data") if isinstance(data, dict) else None
    if not items:
        images = data.get("images") if isinstance(data, dict) else None
        if images and isinstance(images, list):
            return base64.b64decode(images[0])
        raise ProviderError("模型没有返回图片。")
    item = items[0]
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"])
    url = item.get("url")
    if not url:
        raise ProviderError("模型的返回里没有图片数据。")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=8.0)) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        raise ProviderError("图片地址下载失败。") from exc
    if response.status_code >= 400:
        raise ProviderError("图片地址下载失败。")
    return response.content


async def generate_image(provider: str, prompt: str) -> bytes:
    settings = effective_settings()
    backend, base, model, key = _image_target(settings, provider)
    if backend == "a1111":
        payload = {
            "prompt": prompt,
            "negative_prompt": (
                "text, letters, watermark, logo, frame, border, blurry, low quality, "
                "person, hands, extra limbs"
            ),
            "steps": settings["local_image_steps"],
            "width": settings["local_image_width"],
            "height": settings["local_image_height"],
            "cfg_scale": 7,
            "sampler_name": "Euler a",
        }
        response = await _request("POST", _join(base, "/sdapi/v1/txt2img"), key, payload, 180)
        if response.status_code >= 400:
            raise ProviderError(_error_text(response))
        try:
            encoded = response.json()["images"][0]
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ProviderError("本地 WebUI 没有返回图片。请确认启动时加了 --api。") from exc
        return base64.b64decode(encoded)

    size = "1024x1024" if provider == "external" else (
        f"{settings['local_image_width']}x{settings['local_image_height']}"
    )
    payload = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": size,
        "response_format": "b64_json",
    }
    response = await _request("POST", _join(base, "/images/generations"), key, payload, 180)
    if response.status_code >= 400 and "response_format" in response.text:
        payload.pop("response_format", None)
        response = await _request("POST", _join(base, "/images/generations"), key, payload, 180)
    if response.status_code >= 400:
        raise ProviderError(_error_text(response))
    try:
        return await _decode_image_payload(response.json())
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderError("没有从接口响应里解析出图片。") from exc


async def analyze_image(provider: str, data_url: str, hint: str) -> list[dict]:
    settings = effective_settings()
    base, model, key = _vision_target(settings, provider)
    hint_line = f"用户补充：{hint.strip()}。" if hint.strip() else ""
    prompt = (
        "看这张照片，找出最适合做成收藏卡的 1 到 3 件物品。"
        "优先：笔记本电脑、键盘、鼠标、显示器、耳机、显卡、手机、相机、汽车、游戏机。"
        f"{hint_line}"
        '只返回 JSON：{"items":[{"name":"简短中文名","category":"laptop|keyboard|mouse|monitor|audio|gpu|phone|camera|car|console|other","summary":"一句话"}]}'
    )
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
    }
    response = await _request("POST", _join(base, "/chat/completions"), key, payload, 90)
    if response.status_code >= 400:
        raise ProviderError(_error_text(response))
    try:
        content = _message_text(response.json()["choices"][0]["message"]["content"])
        parsed = _extract_json(content)
    except Exception as exc:
        raise ProviderError("视觉模型没有返回可识别的装备名称，请直接手填。") from exc
    items = parsed.get("items") if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        raise ProviderError("视觉模型没有返回装备列表，请直接手填。")
    return items


async def enrich_copy(provider: str, meta: dict, note: str) -> bool:
    if provider not in {"local", "external"}:
        return False
    settings = effective_settings()
    try:
        base, model, key = _vision_target(settings, provider)
    except ProviderError:
        return False
    payload = {
        "model": model,
        "temperature": 0.7,
        "messages": [
            {"role": "system", "content": COPY_SYSTEM},
            {
                "role": "user",
                "content": copy_user_prompt(meta["name"], meta["category"], note),
            },
        ],
    }
    try:
        response = await _request("POST", _join(base, "/chat/completions"), key, payload, 40)
        if response.status_code >= 400:
            log.info("card copy skipped: %s", _error_text(response))
            return False
        content = _message_text(response.json()["choices"][0]["message"]["content"])
        return apply_model_copy(meta, _extract_json(content))
    except Exception:
        log.info("card copy fell back to the built-in template", exc_info=True)
        return False

