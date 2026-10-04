#!/usr/bin/env python3
"""Check the configured image backend. Does not generate a picture."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx

from server.config import effective_settings


def main() -> int:
    which = sys.argv[1] if len(sys.argv) > 1 else "local"
    settings = effective_settings()
    if which == "local":
        base = settings["local_image_base_url"].rstrip("/")
        key = settings["local_image_api_key"]
        if settings["local_image_backend"] == "a1111":
            url = base + "/sdapi/v1/sd-models"
        else:
            url = base + "/models"
    elif which == "external":
        base = settings["external_image_base_url"].rstrip("/")
        key = settings["external_image_api_key"]
        if not base or not key or not settings["external_image_model"]:
            print("外部出图还没配齐地址、模型名和密钥。")
            return 2
        url = base + "/models"
    else:
        print("用法: python3 scripts/probe_image_api.py [local|external]")
        return 2

    headers = {"Authorization": f"Bearer {key}"} if key else {}
    print(f"GET {url}")
    try:
        response = httpx.get(url, headers=headers, timeout=8.0)
    except httpx.ConnectError:
        print("连不上。请确认模型服务已经启动，地址和端口没有写错。")
        return 1
    except httpx.TimeoutException:
        print("连接超时。")
        return 1
    print(f"HTTP {response.status_code}")
    if response.status_code in {401, 403}:
        print("密钥被拒绝。")
        return 1
    if response.status_code >= 400:
        print(response.text[:300])
        return 1
    try:
        payload = response.json()
    except ValueError:
        print("服务有响应，但不是 JSON。WebUI 需要带 --api 启动。")
        return 1
    names = []
    if isinstance(payload, list):
        names = [str(item.get("title") or item.get("model_name") or "") for item in payload if isinstance(item, dict)]
    elif isinstance(payload, dict) and isinstance(payload.get("data"), list):
        names = [str(item.get("id") or "") for item in payload["data"] if isinstance(item, dict)]
    shown = [name for name in names if name][:8]
    if shown:
        print("看到的模型:")
        for name in shown:
            print(f"  {name}")
    else:
        print("连上了。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
