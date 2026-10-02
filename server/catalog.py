"""Card copy, categories, and the English prompt sent to image models."""

from __future__ import annotations

import hashlib

CATEGORIES: dict[str, dict] = {
    "laptop": {
        "label": "笔记本电脑",
        "type_name": "核心",
        "type_key": "core",
        "en": "a premium laptop computer, lid open, screen glowing softly",
        "keywords": ["笔记本", "笔电", "laptop", "macbook", "thinkpad", "xps"],
        "weakness": "没电",
        "retreat": 2,
        "attacks": [
            ("全核睿频", 2, "80", "本回合伤害+30，然后这张卡过热。"),
            ("合盖待发", 1, "", "回复40点HP，下回合不能出招。"),
        ],
        "flavors": [
            "风扇刚响了一下，像是认出了你的手。",
            "凌晨的光标还在跳，它也还醒着。",
        ],
    },
    "keyboard": {
        "label": "键盘",
        "type_name": "外设",
        "type_key": "peripheral",
        "en": "a mechanical keyboard with sculpted keycaps, top view, a few keys glowing",
        "keywords": ["键盘", "keyboard", "配列", "键帽", "hhkb"],
        "weakness": "进灰",
        "retreat": 1,
        "attacks": [
            ("连击手感", 2, "60", "投一次硬币，正面再造成30点伤害。"),
            ("宏指令", 1, "", "从弃牌区收回一张装备卡。"),
        ],
        "flavors": [
            "每一颗轴都记得你最常按的那一下。",
            "夜里只留一排灯，像一条跑道。",
        ],
    },
    "mouse": {
        "label": "鼠标",
        "type_name": "外设",
        "type_key": "peripheral",
        "en": "a sleek wireless mouse on a dark desk mat",
        "keywords": ["鼠标", "mouse", "轨迹球"],
        "weakness": "没电",
        "retreat": 1,
        "attacks": [
            ("瞬移点击", 1, "50", "可以选择新的攻击目标。"),
            ("无线潜伏", 2, "", "对手下回合不能撤退。"),
        ],
        "flavors": [
            "灯灭了之后，它还是一下就找到你。",
            "垫子边缘磨出了你自己的路线。",
        ],
    },
    "monitor": {
        "label": "显示器",
        "type_name": "视听",
        "type_key": "av",
        "en": "a widescreen computer monitor on a desk, screen showing abstract color",
        "keywords": ["显示器", "屏幕", "monitor", "带鱼屏"],
        "weakness": "反光",
        "retreat": 2,
        "attacks": [
            ("铺满视野", 2, "70", "对手的下一张卡伤害-20。"),
            ("深夜模式", 1, "", "治疗这张卡30点HP。"),
        ],
        "flavors": [
            "窗口叠着窗口，外面的天已经黑了。",
            "色准很好，连夜色都偏你喜欢的那一档。",
        ],
    },
    "audio": {
        "label": "耳机音箱",
        "type_name": "视听",
        "type_key": "av",
        "en": "premium over-ear headphones, dramatic studio light",
        "keywords": ["耳机", "音箱", "音响", "headphone", "耳塞", "监听"],
        "weakness": "噪音",
        "retreat": 1,
        "attacks": [
            ("压场低频", 2, "70", "对手下回合不能使用招式。"),
            ("单曲循环", 1, "", "这张卡下回合伤害+20。"),
        ],
        "flavors": [
            "戴上之后，房间就只剩下你在听的那条轨。",
            "单元振了一下，像在跟你打招呼。",
        ],
    },
    "gpu": {
        "label": "显卡",
        "type_name": "核心",
        "type_key": "core",
        "en": "a graphics card with a metal cooler and subtle light strips",
        "keywords": ["显卡", "gpu", "4090", "3090", "5080", "显核"],
        "weakness": "过热",
        "retreat": 3,
        "attacks": [
            ("光追倾泻", 3, "120", "这回合不能撤退。"),
            ("风扇全开", 1, "", "移除这张卡的过热。"),
        ],
        "flavors": [
            "侧板一盖上，整台机器就开始发光。",
            "它负责把你脑子里的画面算出来。",
        ],
    },
    "phone": {
        "label": "手机",
        "type_name": "终端",
        "type_key": "terminal",
        "en": "a flagship smartphone standing at a slight angle, dark glass",
        "keywords": ["手机", "phone", "iphone", "安卓"],
        "weakness": "碎屏",
        "retreat": 1,
        "attacks": [
            ("亮屏", 1, "40", "抽一张卡。"),
            ("夜间模式", 2, "60", "治疗20点HP。"),
        ],
        "flavors": [
            "口袋里的重量，是你随身带的一整间屋子。",
            "锁屏划开，今天才算开始。",
        ],
    },
    "camera": {
        "label": "相机",
        "type_name": "终端",
        "type_key": "terminal",
        "en": "a mirrorless camera with a lens, three-quarter view",
        "keywords": ["相机", "camera", "单反", "微单", "镜头"],
        "weakness": "没电",
        "retreat": 2,
        "attacks": [
            ("快门", 2, "80", "看对手的手牌顶上一张。"),
            ("长曝光", 1, "", "下回合这张卡伤害翻倍。"),
        ],
        "flavors": [
            "取景框里的世界，比外面安静一点。",
            "快门声很轻，轻到只想再按一次。",
        ],
    },
    "car": {
        "label": "汽车",
        "type_name": "座驾",
        "type_key": "ride",
        "en": "a modern sports car, three-quarter front view, night street, wet asphalt",
        "keywords": ["汽车", "跑车", "轿车", "越野", "机车", "suv", "轿跑"],
        "weakness": "爆胎",
        "retreat": 3,
        "attacks": [
            ("弹射起步", 3, "110", "若先攻，伤害+20。"),
            ("夜巡", 1, "", "对手下一招伤害-30。"),
        ],
        "flavors": [
            "仪表盘亮起来的时候，路就变成你的了。",
            "引擎盖还温着，像刚结束一场夜跑。",
        ],
    },
    "console": {
        "label": "游戏机",
        "type_name": "终端",
        "type_key": "terminal",
        "en": "a home game console with a controller beside it",
        "keywords": ["游戏机", "掌机", "switch", "ps5", "xbox", "主机"],
        "weakness": "读盘",
        "retreat": 2,
        "attacks": [
            ("读档", 1, "", "将这张卡的HP恢复到满。"),
            ("连招", 2, "70", "若上回合使用过招式，伤害+30。"),
        ],
        "flavors": [
            "手柄还停在暂停的那个画面上。",
            "加载条走完，房间里的灯可以再暗一点。",
        ],
    },
    "other": {
        "label": "其他",
        "type_name": "装备",
        "type_key": "other",
        "en": "a beloved personal gadget, single object, museum lighting",
        "keywords": [],
        "weakness": "磨损",
        "retreat": 1,
        "attacks": [
            ("上手", 1, "40", "抽一张卡。"),
            ("趁手一击", 2, "70", "这张卡下回合伤害+10。"),
        ],
        "flavors": [
            "用顺了手的东西，会慢慢长成你的一部分。",
            "它不贵在参数，贵在你还留着它。",
        ],
    },
}

ILLUSTRATORS = {
    "local": "本地文生图",
    "external": "外部模型",
    "photo": "原图排版",
}

RARITIES = (
    (0, "普通", 1),
    (4, "稀有", 2),
    (7, "史诗", 3),
    (9, "传说", 4),
)

NEGATIVE_PROMPT = (
    "text, letters, words, caption, watermark, logo, signature, border, frame, "
    "ui, blurry, low quality, deformed, person, human, hands, fingers, duplicate"
)


def clip(value, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def infer_category(name: str, category: str | None) -> str:
    if category in CATEGORIES and category != "other":
        return category
    lowered = (name or "").lower()
    for key, spec in CATEGORIES.items():
        if key == "other":
            continue
        for word in spec["keywords"]:
            if word.lower() in lowered:
                return key
    if category in CATEGORIES:
        return category
    return "other"


def _digest(name: str) -> int:
    return int(hashlib.sha256(name.encode("utf-8")).hexdigest(), 16)


def _rarity(roll: int) -> tuple[str, int]:
    name, stars = "普通", 1
    for threshold, label, count in RARITIES:
        if roll >= threshold:
            name, stars = label, count
    return name, stars


def make_card_meta(name: str, category: str, provider: str, note: str = "") -> dict:
    category = infer_category(name, category)
    spec = CATEGORIES[category]
    digest = _digest(f"{name}|{note}")
    rarity, stars = _rarity(digest % 10)
    hp = 90 + (digest % 80)
    attacks = []
    for index, (atk_name, cost, damage, text) in enumerate(spec["attacks"]):
        shown = damage
        if damage:
            delta = (-10, 0, 0, 10, 20)[(digest + index) % 5]
            shown = str(max(20, int(damage) + delta))
        attacks.append(
            {
                "name": atk_name,
                "cost": cost,
                "damage": shown,
                "text": text,
            }
        )
    flavor = spec["flavors"][digest % len(spec["flavors"])]
    return {
        "name": clip(name, 24),
        "category": category,
        "category_label": spec["label"],
        "type_name": spec["type_name"],
        "type_key": spec["type_key"],
        "hp": hp,
        "rarity": rarity,
        "rarity_stars": stars,
        "number": f"{(digest % 150) + 1:03d}",
        "weakness": spec["weakness"],
        "retreat": spec["retreat"],
        "attacks": attacks,
        "flavor": flavor,
        "illustrator": ILLUSTRATORS.get(provider, "工坊"),
        "series": "TECH & RIDE",
    }


def apply_model_copy(meta: dict, data: dict) -> bool:
    """Replace attacks and flavor when the model returned usable copy."""
    if not isinstance(data, dict):
        return False
    cleaned = []
    raw_attacks = data.get("attacks")
    if isinstance(raw_attacks, list):
        for attack in raw_attacks[:2]:
            if not isinstance(attack, dict):
                continue
            title = clip(attack.get("name") or "", 8).replace("…", "")
            text = clip(attack.get("text") or "", 32).replace("…", "")
            if not title or not text:
                continue
            damage = "".join(ch for ch in str(attack.get("damage") or "") if ch.isdigit())[:3]
            try:
                cost = int(attack.get("cost", 1))
            except (TypeError, ValueError):
                cost = 1
            cleaned.append(
                {
                    "name": title,
                    "cost": min(3, max(1, cost)),
                    "damage": damage,
                    "text": text,
                }
            )
    changed = False
    if cleaned:
        if len(cleaned) == 1 and meta.get("attacks"):
            cleaned.append(meta["attacks"][-1])
        meta["attacks"] = cleaned[:2]
        changed = True
    flavor = clip(data.get("flavor") or "", 32).replace("…", "")
    if flavor:
        meta["flavor"] = flavor
        changed = True
    return changed


def image_prompt(name: str, category: str, note: str = "") -> str:
    spec = CATEGORIES.get(category) or CATEGORIES["other"]
    extra = f" Extra direction: {clip(note, 160)}." if note.strip() else ""
    return (
        "Full-bleed trading card artwork of exactly one object, no border. "
        f"Subject: {spec['en']}. It is specifically: {clip(name, 80)}. "
        "Centered, three-quarter or hero view, dramatic museum lighting, "
        "rich saturated color, fine material detail, a faint colored energy glow, "
        "dark painterly background, no people, no hands, no text, no letters, "
        "no logo, no watermark, no frame."
        + extra
    )


COPY_SYSTEM = (
    "你给原创装备收藏卡写招式。语气短、具体、有一点热爱。"
    "不要提到宝可梦、皮卡丘或任何现成卡牌里的角色和招式名。只输出 JSON。"
)


def copy_user_prompt(name: str, category: str, note: str) -> str:
    label = CATEGORIES.get(category, CATEGORIES["other"])["label"]
    extra = note.strip() or "无"
    return (
        f"装备名称：{clip(name, 40)}\n种类：{label}\n补充：{clip(extra, 80)}\n"
        "输出 JSON，不要 markdown：\n"
        '{"attacks":[{"name":"四到六字","cost":1,"damage":"60","text":"不超过24个字"},'
        '{"name":"四到六字","cost":2,"damage":"","text":"不超过24个字"}],'
        '"flavor":"不超过26个字"}\n'
        "恰好两个招式。damage 用数字字符串，没有伤害就用空字符串。"
    )
