"""MyGearCard workshop server."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from .catalog import CATEGORIES, image_prompt, infer_category, make_card_meta
from .config import CARDS, SAMPLES, UPLOADS, WEB, effective_settings, provider_status
from .db import get_card, get_order, get_upload, init_db, insert_card, insert_order, insert_upload, list_cards, list_orders, update_order
from .imaging import extension_for, render_card, safe_path, sample_art, sniff, vision_data_url
from .providers import ProviderError, analyze_image, enrich_copy, generate_image

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("mygearcard")

ID_RE = re.compile(r"^[a-f0-9]{12}$")
ORDER_RE = re.compile(r"^MG-[A-F0-9]{8}$")
PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
POSTAL_RE = re.compile(r"^\d{6}$")
SAMPLE_NAMES = {"laptop": "轻薄笔记本", "keyboard": "机械键盘", "car": "夜色跑车"}
NEXT_STATUS = {
    "待印刷": {"印刷中", "已取消"},
    "印刷中": {"已发货", "已取消"},
    "已发货": {"已完成"},
}


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _order_id() -> str:
    return "MG-" + uuid.uuid4().hex[:8].upper()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    SAMPLES.mkdir(parents=True, exist_ok=True)
    for name in SAMPLE_NAMES:
        dest = SAMPLES / f"{name}.jpg"
        if not dest.exists():
            sample_art(name).save(dest, format="JPEG", quality=90)
    yield


app = FastAPI(title="MyGearCard", version="1.0.0", lifespan=lifespan)


@app.exception_handler(ProviderError)
async def provider_error(_request, exc: ProviderError):
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(StarletteHTTPException)
async def http_error(_request, exc: StarletteHTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else "请求没有通过"
    return JSONResponse(status_code=exc.status_code, content={"detail": detail})


@app.exception_handler(RequestValidationError)
async def validation_error(_request, _exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"detail": "提交的内容不完整，请检查必填项。"})


class GenerateIn(BaseModel):
    upload_id: str
    name: str = Field(min_length=1, max_length=40)
    category: str = "other"
    provider: str
    note: str = ""


class OrderIn(BaseModel):
    card_id: str
    quantity: int = Field(ge=1, le=20)
    recipient: str
    phone: str
    province: str
    city: str
    district: str
    address: str
    postal_code: str = ""
    note: str = ""


class StatusIn(BaseModel):
    status: str
    carrier: str = ""
    tracking_no: str = ""


def _clean(value: str, limit: int) -> str:
    return " ".join((value or "").split())[:limit]


def _require_id(value: str, pattern: re.Pattern[str], label: str) -> str:
    if not pattern.match(value or ""):
        raise HTTPException(404, f"找不到这张{label}")
    return value


def _card_out(row) -> dict:
    return {
        "id": row["id"],
        "upload_id": row["upload_id"],
        "provider": row["provider"],
        "name": row["name"],
        "category": row["category"],
        "prompt": row["prompt"],
        "art_url": f"/media/cards/{row['id']}",
        "copy_source": row["copy_source"],
        "meta": json.loads(row["meta_json"]),
        "created_at": row["created_at"],
    }


def _order_out(row) -> dict:
    contact = json.loads(row["contact_json"])
    card = get_card(row["card_id"])
    return {
        "id": row["id"],
        "card_id": row["card_id"],
        "card_name": card["name"] if card else "",
        "art_url": f"/media/cards/{row['card_id']}" if card else "",
        "quantity": row["quantity"],
        "unit_price": row["unit_price"],
        "shipping_fee": row["shipping_fee"],
        "total": row["total"],
        "status": row["status"],
        "carrier": row["carrier"],
        "tracking_no": row["tracking_no"],
        "contact": contact,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _store_upload(raw: bytes, filename: str) -> dict:
    mime = sniff(raw)
    if mime is None:
        raise HTTPException(400, "请上传 JPG、PNG、WebP 或 GIF 图片。")
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(400, "图片请小于 8MB。")
    upload_id = _new_id()
    stored = f"{upload_id}{extension_for(mime)}"
    (UPLOADS / stored).write_bytes(raw)
    insert_upload(upload_id, filename or stored, mime, f"uploads/{stored}")
    return {"id": upload_id, "filename": filename or stored, "url": f"/media/uploads/{upload_id}", "mime": mime}


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/config")
def config():
    settings = effective_settings()
    status = provider_status(settings)
    status["categories"] = [
        {"id": key, "label": spec["label"]}
        for key, spec in CATEGORIES.items()
    ]
    return status


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "没有读到图片。")
    return _store_upload(raw, file.filename or "upload")


@app.post("/api/samples/{name}")
def use_sample(name: str):
    if name not in SAMPLE_NAMES:
        raise HTTPException(404, "没有这张示例图。")
    path = SAMPLES / f"{name}.jpg"
    if not path.exists():
        sample_art(name).save(path, format="JPEG", quality=90)
    raw = path.read_bytes()
    stored = _store_upload(raw, f"{name}.jpg")
    stored["suggested_name"] = SAMPLE_NAMES[name]
    stored["suggested_category"] = name if name in CATEGORIES else "other"
    return stored


@app.post("/api/analyze")
async def analyze(body: dict):
    upload_id = _require_id(str(body.get("upload_id") or ""), ID_RE, "图片")
    provider = body.get("provider") or "local"
    if provider not in {"local", "external"}:
        raise HTTPException(400, "识别只能走本地视觉模型或外部接口。")
    row = get_upload(upload_id)
    if row is None:
        raise HTTPException(404, "找不到这张图片，请重新上传。")
    hint = _clean(str(body.get("hint") or ""), 80)
    data_url = vision_data_url(safe_path(row["relpath"]), row["mime"])
    raw_items = await analyze_image(provider, data_url, hint)
    items = []
    for item in raw_items[:3]:
        if not isinstance(item, dict):
            continue
        name = _clean(str(item.get("name") or ""), 40)
        if not name:
            continue
        category = item.get("category")
        category = infer_category(name, category if isinstance(category, str) else None)
        items.append(
            {
                "name": name,
                "category": category,
                "summary": _clean(str(item.get("summary") or ""), 80),
            }
        )
    if not items:
        raise HTTPException(502, "没有识别出装备，请直接填写名称。")
    return {"items": items}


@app.post("/api/generate")
async def generate(body: GenerateIn):
    upload_id = _require_id(body.upload_id, ID_RE, "图片")
    if body.provider not in {"local", "external", "photo"}:
        raise HTTPException(400, "请选择本地文生图、外部 API，或原图排版。")
    row = get_upload(upload_id)
    if row is None:
        raise HTTPException(404, "找不到这张图片，请重新上传。")
    name = _clean(body.name, 40)
    if not name:
        raise HTTPException(400, "先写上这件装备的名字。")
    note = _clean(body.note, 160)
    category = infer_category(name, body.category)
    meta = make_card_meta(name, category, body.provider, note)
    prompt = image_prompt(meta["name"], category, note)
    card_id = _new_id()
    source_path = safe_path(row["relpath"])
    temp_art: Path | None = None
    copy_source = "template"

    async def produce_art() -> Path:
        nonlocal temp_art
        if body.provider == "photo":
            return source_path
        raw = await generate_image(body.provider, prompt)
        mime = sniff(raw)
        if mime is None:
            raise ProviderError("模型返回的内容不是图片。")
        temp_art = CARDS / f"{card_id}-src{extension_for(mime)}"
        temp_art.write_bytes(raw)
        return temp_art

    async def cancel_copy(task: asyncio.Task | None) -> None:
        if task is None:
            return
        if task.done():
            with suppress(Exception):
                task.result()
            return
        task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await task

    copy_task = None
    if body.provider in {"local", "external"}:
        copy_task = asyncio.create_task(enrich_copy(body.provider, meta, note))
    try:
        art_path = await produce_art()
        if copy_task is not None:
            try:
                if await copy_task:
                    copy_source = "model"
            except Exception:
                log.info("copy enrichment failed", exc_info=True)
        meta["illustrator"] = {
            "local": "本地文生图",
            "external": "外部模型",
            "photo": "原图排版",
        }[body.provider]
        try:
            png = render_card(art_path, meta)
        except Exception as exc:
            log.exception("card render failed")
            raise HTTPException(500, "卡牌排版失败，请换一张图片再试。") from exc
    except ProviderError:
        await cancel_copy(copy_task)
        raise
    except HTTPException:
        await cancel_copy(copy_task)
        raise
    finally:
        if temp_art is not None and temp_art.exists():
            temp_art.unlink()

    out = CARDS / f"{card_id}.png"
    out.write_bytes(png)
    insert_card(
        {
            "id": card_id,
            "upload_id": upload_id,
            "provider": body.provider,
            "name": meta["name"],
            "category": category,
            "prompt": prompt,
            "relpath": f"cards/{card_id}.png",
            "mime": "image/png",
            "meta": meta,
            "copy_source": copy_source,
        }
    )
    return _card_out(get_card(card_id))


@app.get("/api/cards")
def cards(limit: int = 12):
    limit = max(1, min(24, limit))
    return {"cards": [_card_out(row) for row in list_cards(limit)]}


@app.get("/api/cards/{card_id}")
def card_detail(card_id: str):
    _require_id(card_id, ID_RE, "卡")
    row = get_card(card_id)
    if row is None:
        raise HTTPException(404, "找不到这张卡")
    return _card_out(row)


@app.post("/api/orders")
def create_order(body: OrderIn):
    _require_id(body.card_id, ID_RE, "卡")
    card = get_card(body.card_id)
    if card is None:
        raise HTTPException(404, "找不到要印刷的卡，请先生成一张。")
    recipient = _clean(body.recipient, 30)
    phone = _clean(body.phone, 20)
    province = _clean(body.province, 20)
    city = _clean(body.city, 20)
    district = _clean(body.district, 20)
    address = _clean(body.address, 120)
    postal = _clean(body.postal_code, 10)
    note = _clean(body.note, 200)
    if len(recipient) < 2:
        raise HTTPException(400, "请填写收件人。")
    if not PHONE_RE.match(phone):
        raise HTTPException(400, "请填写 11 位手机号。")
    if not province or not city or not district:
        raise HTTPException(400, "请把省、市、区都填上。")
    if len(address) < 5:
        raise HTTPException(400, "请填写详细地址，至少 5 个字。")
    if postal and not POSTAL_RE.match(postal):
        raise HTTPException(400, "邮编需要是 6 位数字，也可以留空。")
    settings = effective_settings()
    unit = settings["card_price_cents"]
    shipping = settings["shipping_cents"]
    total = unit * body.quantity + shipping
    order_id = _order_id()
    insert_order(
        {
            "id": order_id,
            "card_id": body.card_id,
            "quantity": body.quantity,
            "unit_price": unit,
            "shipping_fee": shipping,
            "total": total,
            "status": "待印刷",
            "contact": {
                "recipient": recipient,
                "phone": phone,
                "province": province,
                "city": city,
                "district": district,
                "address": address,
                "postal_code": postal,
                "note": note,
            },
        }
    )
    return _order_out(get_order(order_id))


@app.get("/api/orders")
def orders():
    return {"orders": [_order_out(row) for row in list_orders()]}


@app.get("/api/orders/{order_id}")
def order_detail(order_id: str):
    _require_id(order_id, ORDER_RE, "订单")
    row = get_order(order_id)
    if row is None:
        raise HTTPException(404, "找不到这张订单")
    return _order_out(row)


@app.patch("/api/orders/{order_id}")
def patch_order(order_id: str, body: StatusIn):
    _require_id(order_id, ORDER_RE, "订单")
    row = get_order(order_id)
    if row is None:
        raise HTTPException(404, "找不到这张订单")
    status = body.status.strip()
    allowed = NEXT_STATUS.get(row["status"], set())
    if status not in allowed:
        raise HTTPException(400, f"不能从「{row['status']}」改成「{status}」。")
    carrier = _clean(body.carrier, 20)
    tracking = _clean(body.tracking_no, 40)
    if status == "已发货" and len(tracking) < 4:
        raise HTTPException(400, "发货时请填写运单号。")
    update_order(order_id, status, carrier, tracking)
    return _order_out(get_order(order_id))


@app.get("/media/uploads/{upload_id}")
def media_upload(upload_id: str):
    _require_id(upload_id, ID_RE, "图片")
    row = get_upload(upload_id)
    if row is None:
        raise HTTPException(404, "找不到这张图片")
    path = safe_path(row["relpath"])
    if not path.is_file():
        raise HTTPException(404, "找不到这张图片")
    return FileResponse(path, media_type=row["mime"])


@app.get("/media/cards/{card_id}")
def media_card(card_id: str):
    _require_id(card_id, ID_RE, "卡")
    row = get_card(card_id)
    if row is None:
        raise HTTPException(404, "找不到这张卡")
    path = safe_path(row["relpath"])
    if not path.is_file():
        raise HTTPException(404, "找不到这张卡")
    return FileResponse(path, media_type="image/png")


_PAGE_HEADERS = {"Cache-Control": "no-cache"}


@app.get("/")
def index():
    return FileResponse(WEB / "index.html", headers=_PAGE_HEADERS)


@app.get("/orders")
def orders_page():
    return FileResponse(WEB / "orders.html", headers=_PAGE_HEADERS)


@app.get("/workshop")
def workshop_page():
    return FileResponse(WEB / "workshop.html", headers=_PAGE_HEADERS)


app.mount("/static", StaticFiles(directory=WEB), name="static")
