"""
4-tier CC0 3D model download service.

Tier 0 — Local builtin GLB bundle (no network, instant)
Tier 1 — Poly Pizza v2/v1 dual-endpoint (free key: https://poly.pizza)
          Set env var: POLYPIZZA_API_KEY=<your_key>
Tier 2 — Sketchfab CC0 (free key: https://sketchfab.com/settings#api)
          Set env var: SKETCHFAB_API_KEY=<your_key>
Tier 3 — KhronosGroup glTF-Sample-Assets CDN (no key required)

Enhancements vs original:
  - Chinese→English keyword translation before every search
  - Synonym retry when first search returns zero results
  - GLB magic-byte validation (rejects HTML error pages / corrupt files)
  - PolyPizza v2 + v1 dual-endpoint with robust nested-URL extraction
  - Circuit-breakers prevent repeated 401/403 retries within a session
  - Query normalised once at entry; same canonical form used for cache key
"""

import os
import json
import hashlib
import urllib.request
import urllib.parse
import urllib.error

from backend.config import ASSETS_DOWNLOADED_DIR, POLYPIZZA_API_KEY, SKETCHFAB_API_KEY, GODOT_DIR

# Circuit-breaker: set True after first 401 so we never retry this session
_polypizza_dead = False
_sketchfab_dead = False

# ── Query normalisation ──────────────────────────────────────────────────────

_ZH_EN_MAP: dict[str, str] = {
    # Characters
    "人": "human", "人物": "human", "人类": "human", "角色": "character",
    "男人": "man", "女人": "woman", "男性": "man", "女性": "woman",
    "士兵": "soldier", "飞行员": "pilot", "宇航员": "astronaut",
    "警察": "police", "医生": "doctor", "工人": "worker",
    "机器人": "robot", "外星人": "alien", "怪物": "monster",
    "骑手": "rider", "球员": "player", "运动员": "athlete",
    # Vehicles
    "汽车": "car", "轿车": "car", "跑车": "sports car", "警车": "police car",
    "救护车": "ambulance", "卡车": "truck", "公交车": "bus", "面包车": "van",
    "坦克": "tank", "装甲车": "armored vehicle",
    # Aircraft
    "飞机": "airplane", "客机": "airliner", "战斗机": "fighter jet",
    "轰炸机": "bomber", "直升机": "helicopter", "火箭": "rocket",
    "飞船": "spaceship", "宇宙飞船": "spaceship", "飞碟": "ufo",
    # Watercraft
    "船": "boat", "轮船": "ship", "潜艇": "submarine", "快艇": "speedboat",
    # Animals
    "狐狸": "fox", "狗": "dog", "猫": "cat", "熊": "bear", "兔子": "rabbit",
    "鸭子": "duck", "鸟": "bird", "鸡": "chicken", "龙": "dragon",
    "恐龙": "dinosaur", "马": "horse", "狮子": "lion", "老虎": "tiger",
    "鱼": "fish", "鲨鱼": "shark", "蜘蛛": "spider",
    # Props / weapons
    "剑": "sword", "枪": "gun", "盾": "shield", "弓": "bow", "箭": "arrow",
    "锤子": "hammer", "斧头": "axe", "匕首": "dagger",
    # Objects
    "球": "ball", "篮球": "basketball", "足球": "soccer ball",
    "头盔": "helmet", "盔甲": "armor", "皇冠": "crown",
    "灯笼": "lantern", "灯": "lamp", "火把": "torch",
    "瓶子": "bottle", "箱子": "chest", "木桶": "barrel",
    "椅子": "chair", "桌子": "table", "床": "bed",
    "树": "tree", "植物": "plant", "花": "flower", "草": "grass",
    "骷髅": "skull", "骨架": "skeleton",
    # Environment / buildings
    "房子": "house", "建筑": "building", "城堡": "castle", "塔": "tower",
    "桥": "bridge", "石头": "rock",
    # Sci-fi / fantasy
    "水晶": "crystal", "宝石": "gem", "星球": "planet", "月亮": "moon",
}

_SYNONYM_MAP: dict[str, list[str]] = {
    "human":      ["person", "character", "man", "figure"],
    "person":     ["human", "character", "figure"],
    "character":  ["human", "person", "figure"],
    "car":        ["vehicle", "automobile", "sedan"],
    "vehicle":    ["car", "automobile"],
    "airplane":   ["aircraft", "plane", "jet"],
    "aircraft":   ["airplane", "plane", "jet"],
    "spaceship":  ["spacecraft", "rocket", "ufo"],
    "spacecraft": ["spaceship", "rocket"],
    "rocket":     ["spaceship", "spacecraft"],
    "helicopter": ["aircraft", "rotorcraft"],
    "robot":      ["android", "mech", "figure"],
    "dragon":     ["dinosaur", "creature", "monster"],
    "dinosaur":   ["dragon", "creature"],
    "sword":      ["weapon", "blade", "dagger"],
    "gun":        ["weapon", "rifle", "pistol"],
    "building":   ["house", "structure", "tower"],
    "house":      ["building", "home"],
    "tree":       ["plant", "vegetation"],
    "boat":       ["ship", "vessel"],
    "ship":       ["boat", "vessel"],
    "tank":       ["military", "armored"],
    "horse":      ["animal", "creature"],
    "chest":      ["box", "container"],
    "barrel":     ["crate", "container"],
    "helmet":     ["armor", "gear"],
    "skull":      ["skeleton", "bone"],
    "fox":        ["animal", "wolf", "dog"],
    "duck":       ["bird", "chicken"],
    "basketball": ["ball", "sport"],
    "astronaut":  ["human", "soldier", "character"],
    "police":     ["human", "character", "soldier"],
    "soldier":    ["human", "character", "military"],
}


def _normalize_query(query: str) -> str:
    """Translate Chinese terms to English and clean the query string."""
    q = query.strip()
    if q in _ZH_EN_MAP:
        return _ZH_EN_MAP[q]
    for zh in sorted(_ZH_EN_MAP, key=len, reverse=True):
        if zh in q:
            q = q.replace(zh, " " + _ZH_EN_MAP[zh] + " ")
    return " ".join(q.lower().split())


def _is_valid_glb(path: str) -> bool:
    """Return True only if the file begins with the GLB magic bytes (glTF)."""
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"glTF"
    except Exception:
        return False


# ── Tier 0: Local builtin CC0 models (no network needed) ────────────────────
_BUILTIN_DIR = os.path.join(GODOT_DIR, "assets", "builtin")

# keyword → builtin filename   (longest/most-specific first)
_BUILTIN_CATALOG: list[tuple[str, str]] = [
    # Characters
    ("human",       "human.glb"),
    ("person",      "human.glb"),
    ("man",         "human.glb"),
    ("woman",       "human.glb"),
    ("character",   "human.glb"),
    ("pedestrian",  "human.glb"),
    ("soldier",     "human.glb"),
    ("pilot",       "human.glb"),
    ("player",      "human.glb"),
    ("basketball player", "human.glb"),
    ("basketball",  "ball.glb"),
    ("robot",       "robot.glb"),
    ("android",     "robot.glb"),
    ("alien",       "robot.glb"),
    # Vehicles
    ("police car",  "car.glb"),
    ("ambulance",   "car.glb"),
    ("sports car",  "car.glb"),
    ("race car",    "car.glb"),
    ("car",         "car.glb"),
    ("truck",       "car.glb"),
    ("bus",         "car.glb"),
    ("van",         "car.glb"),
    ("vehicle",     "car.glb"),
    # Aircraft / Space
    ("airplane",    "airplane.glb"),
    ("plane",       "airplane.glb"),
    ("jet",         "airplane.glb"),
    ("aircraft",    "airplane.glb"),
    ("rocket",      "airplane.glb"),
    ("spaceship",   "airplane.glb"),
    ("spacecraft",  "airplane.glb"),
    ("ufo",         "airplane.glb"),
    ("saucer",      "airplane.glb"),
    # Animals
    ("fox",         "fox.glb"),
    ("wolf",        "fox.glb"),
    ("dog",         "fox.glb"),
    ("cat",         "fox.glb"),
    ("animal",      "fox.glb"),
    ("bear",        "fox.glb"),
    ("duck",        "duck.glb"),
    ("bird",        "duck.glb"),
    ("chicken",     "duck.glb"),
    ("penguin",     "duck.glb"),
    # Fantasy
    ("dragon",      "dragon.glb"),
    ("dinosaur",    "dragon.glb"),
    ("wyvern",      "dragon.glb"),
    ("skull",       "skull.glb"),
    ("skeleton",    "skull.glb"),
    # Props
    ("lantern",     "lantern.glb"),
    ("lamp",        "lantern.glb"),
    ("torch",       "lantern.glb"),
    ("helmet",      "helmet.glb"),
    ("armor",       "helmet.glb"),
    ("bottle",      "bottle.glb"),
    ("container",   "bottle.glb"),
    ("ball",        "ball.glb"),
    ("cube",        "ball.glb"),
    ("block",       "ball.glb"),
    ("avocado",     "avocado.glb"),
    ("fruit",       "avocado.glb"),
    ("food",        "avocado.glb"),
    ("plant",       "avocado.glb"),
    ("tree",        "avocado.glb"),
]

def _try_builtin(actor_id: str, query: str, dest: str) -> bool:
    """Tier 0: match query against local bundled models. Copy to dest if found."""
    q = query.lower().strip()
    # longest match first (catalog is ordered most-specific first)
    matched_file = None
    for keyword, fname in _BUILTIN_CATALOG:
        if keyword in q:
            full = os.path.join(_BUILTIN_DIR, fname)
            if os.path.exists(full):
                matched_file = full
                print(f"[Tier0/Builtin] '{query}' → {fname}")
                break
    if not matched_file:
        return False
    import shutil
    try:
        shutil.copy2(matched_file, dest)
        return True
    except Exception as e:
        print(f"[Tier0/Builtin] copy failed: {e}")
        return False

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _get(url: str, extra_headers: dict | None = None, timeout: int = 15) -> bytes:
    headers = {"User-Agent": _UA, "Accept": "application/json, */*"}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _dest_path(actor_id: str, query: str) -> str:
    h = hashlib.md5(query.lower().strip().encode()).hexdigest()[:8]
    os.makedirs(ASSETS_DOWNLOADED_DIR, exist_ok=True)
    return os.path.join(ASSETS_DOWNLOADED_DIR, f"{actor_id}_{h}.glb")


def _save(url: str, dest: str, extra_headers: dict | None = None) -> bool:
    try:
        data = _get(url, extra_headers=extra_headers, timeout=30)
        with open(dest, "wb") as f:
            f.write(data)
        print(f"[AssetFetcher] Saved {len(data)//1024} KB → {dest}")
        return True
    except Exception as e:
        print(f"[AssetFetcher] Save failed {url}: {e}")
        return False


# ───────────────────────────────────────────────
# Tier 1: Poly Pizza
# ───────────────────────────────────────────────

def _polypizza_search(query: str, limit: int = 5) -> list[dict]:
    global _polypizza_dead
    if not POLYPIZZA_API_KEY or _polypizza_dead:
        return []
    # Try v2 first (JSON structure differs), then fall back to v1
    endpoints = [
        "https://api.poly.pizza/v2/models?" + urllib.parse.urlencode(
            {"q": query, "limit": limit, "format": "glb"}),
        "https://api.poly.pizza/v1/search?" + urllib.parse.urlencode(
            {"q": query, "limit": limit}),
    ]
    for url in endpoints:
        try:
            raw  = _get(url, extra_headers={"x-api-key": POLYPIZZA_API_KEY})
            data = json.loads(raw)
            results = (data.get("results") or data.get("resources")
                       or data.get("data") or data.get("models") or [])
            if results:
                print(f"[Tier1/PolyPizza] '{query}' → {len(results)} results")
                return results
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                _polypizza_dead = True
                print(f"[Tier1/PolyPizza] HTTP {e.code} — 熔断，本次会话跳过所有后续 Poly Pizza 请求")
                return []
            print(f"[Tier1/PolyPizza] HTTP {e.code}: {e.reason}")
        except Exception as e:
            print(f"[Tier1/PolyPizza] Error: {e}")
    return []


def _polypizza_glb_url(model: dict) -> str | None:
    # Walk nested paths common to v2 and v1 response shapes
    for key_path in [
        ("download", "glb"), ("download", "url"), ("download", "file"),
        ("files", "glb"),    ("files", "url"),
        ("Download", "glb"), ("Download", "url"),
    ]:
        node: object = model
        for k in key_path:
            if not isinstance(node, dict):
                break
            node = node.get(k)
        if isinstance(node, str) and node.startswith("http"):
            return node
    # Flat string fields
    for key in ("Download", "download", "download_url", "file_url", "url", "file"):
        v = model.get(key)
        if isinstance(v, str) and v.startswith("http"):
            return v
    # Any dict value with a URL
    for field in ("download", "Download", "files"):
        dl = model.get(field)
        if isinstance(dl, dict):
            url = dl.get("glb") or dl.get("url") or next(
                (v for v in dl.values() if isinstance(v, str) and v.startswith("http")), None)
            if url:
                return url
    return None


def _try_polypizza(actor_id: str, query: str, dest: str) -> bool:
    results = _polypizza_search(query)
    # Retry: drop multi-word to last single keyword
    if not results and len(query.split()) > 1:
        results = _polypizza_search(query.split()[-1])
    # Retry: synonym expansion
    if not results:
        core = query.split()[-1]
        for syn in _SYNONYM_MAP.get(core, [])[:2]:
            results = _polypizza_search(syn)
            if results:
                break
    for m in results:
        url = _polypizza_glb_url(m)
        if not url:
            continue
        if _save(url, dest) and _is_valid_glb(dest):
            return True
        if os.path.exists(dest):
            os.remove(dest)   # discard invalid file so cache stays clean
    return False


# ───────────────────────────────────────────────
# Tier 2: Sketchfab
# ───────────────────────────────────────────────

def _sketchfab_search(query: str, count: int = 5) -> list[dict]:
    """Search Sketchfab for downloadable CC0 GLB models."""
    global _sketchfab_dead
    if not SKETCHFAB_API_KEY or _sketchfab_dead:
        return []
    qs = urllib.parse.urlencode({
        "q": query, "count": count,
        "downloadable": "true", "license": "cc0",
        "type": "models",
    })
    url = f"https://api.sketchfab.com/v3/models?{qs}"
    try:
        raw  = _get(url, extra_headers={"Authorization": f"Token {SKETCHFAB_API_KEY}"})
        data = json.loads(raw)
        results = data.get("results", [])
        print(f"[Tier2/Sketchfab] '{query}' → {len(results)} results")
        return results
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            _sketchfab_dead = True
            print(f"[Tier2/Sketchfab] HTTP {e.code} — 熔断")
        else:
            print(f"[Tier2/Sketchfab] HTTP {e.code}: {e.reason}")
    except Exception as e:
        print(f"[Tier2/Sketchfab] Error: {e}")
    return []


def _sketchfab_download_url(uid: str) -> str | None:
    """Get the temporary GLB download URL for a Sketchfab model."""
    url = f"https://api.sketchfab.com/v3/models/{uid}/download"
    try:
        raw  = _get(url, extra_headers={"Authorization": f"Token {SKETCHFAB_API_KEY}"})
        data = json.loads(raw)
        return (
            data.get("gltf", {}).get("url")
            or data.get("glb",  {}).get("url")
        )
    except Exception as e:
        print(f"[Tier2/Sketchfab] Download URL error for {uid}: {e}")
        return None


def _try_sketchfab(actor_id: str, query: str, dest: str) -> bool:
    results = _sketchfab_search(query)
    # Retry: single keyword
    if not results and len(query.split()) > 1:
        results = _sketchfab_search(query.split()[-1])
    # Retry: synonyms
    if not results:
        core = query.split()[-1]
        for syn in _SYNONYM_MAP.get(core, [])[:2]:
            results = _sketchfab_search(syn)
            if results:
                break
    for m in results:
        uid = m.get("uid")
        if not uid:
            continue
        dl_url = _sketchfab_download_url(uid)
        if not dl_url:
            continue
        if _save(dl_url, dest, extra_headers={"Authorization": f"Token {SKETCHFAB_API_KEY}"}) and _is_valid_glb(dest):
            return True
        if os.path.exists(dest):
            os.remove(dest)
    return False


# ───────────────────────────────────────────────
# Tier 3: KhronosGroup + Quaternius stable CDN (no key)
# Maps common search keywords to known stable CC0 GLB URLs
# ───────────────────────────────────────────────

# New confirmed repo: glTF-Sample-Assets (replaces archived glTF-Sample-Models)
# Only models with verified glTF-Binary subdirectory are listed here.
_KGLTF = "https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/main/Models"

_MAN   = f"{_KGLTF}/CesiumMan/glTF-Binary/CesiumMan.glb"
_TRUCK = f"{_KGLTF}/CesiumMilkTruck/glTF-Binary/CesiumMilkTruck.glb"
_FIG   = f"{_KGLTF}/RiggedFigure/glTF-Binary/RiggedFigure.glb"
_FOX   = f"{_KGLTF}/Fox/glTF-Binary/Fox.glb"
_DUCK  = f"{_KGLTF}/Duck/glTF-Binary/Duck.glb"
_DRAG  = f"{_KGLTF}/DragonDispersion/glTF-Binary/DragonDispersion.glb"
_SKULL = f"{_KGLTF}/ScatteringSkull/glTF-Binary/ScatteringSkull.glb"
_HELM  = f"{_KGLTF}/FlightHelmet/glTF-Binary/FlightHelmet.glb"
_BOX   = f"{_KGLTF}/Box/glTF-Binary/Box.glb"
_AVOC  = f"{_KGLTF}/Avocado/glTF-Binary/Avocado.glb"
_DUCK2 = f"{_KGLTF}/RubberDuck/glTF-Binary/RubberDuck.glb"

# keyword → (display_name, glb_url)
_FALLBACK_CATALOG: dict[str, tuple[str, str]] = {
    # ── Vehicles ──────────────────────────────────────────────────────────────
    "truck":        ("CesiumMilkTruck",  _TRUCK),
    "car":          ("CesiumMilkTruck",  _TRUCK),
    "vehicle":      ("CesiumMilkTruck",  _TRUCK),
    "bus":          ("CesiumMilkTruck",  _TRUCK),
    "van":          ("CesiumMilkTruck",  _TRUCK),
    "ambulance":    ("CesiumMilkTruck",  _TRUCK),
    # ── Aircraft (FlightHelmet is the only aircraft-adjacent KG sample) ────────
    "plane":        ("FlightHelmet",     _HELM),
    "airplane":     ("FlightHelmet",     _HELM),
    "jet":          ("FlightHelmet",     _HELM),
    "aircraft":     ("FlightHelmet",     _HELM),
    "airliner":     ("FlightHelmet",     _HELM),
    "fighter":      ("FlightHelmet",     _HELM),
    "bomber":       ("FlightHelmet",     _HELM),
    "helicopter":   ("FlightHelmet",     _HELM),
    "rocket":       ("RiggedFigure",     _FIG),
    # ── Characters ────────────────────────────────────────────────────────────
    "human":        ("CesiumMan",        _MAN),
    "person":       ("CesiumMan",        _MAN),
    "man":          ("CesiumMan",        _MAN),
    "woman":        ("CesiumMan",        _MAN),
    "walker":       ("CesiumMan",        _MAN),
    "soldier":      ("CesiumMan",        _MAN),
    "pilot":        ("FlightHelmet",     _HELM),
    "astronaut":    ("FlightHelmet",     _HELM),
    "character":    ("CesiumMan",        _MAN),
    "figure":       ("RiggedFigure",     _FIG),
    "alien":        ("RiggedFigure",     _FIG),
    "robot":        ("RiggedFigure",     _FIG),
    "android":      ("RiggedFigure",     _FIG),
    "creature":     ("RiggedFigure",     _FIG),
    # ── Animals ───────────────────────────────────────────────────────────────
    "fox":          ("Fox",              _FOX),
    "wolf":         ("Fox",              _FOX),
    "dog":          ("Fox",              _FOX),
    "cat":          ("Fox",              _FOX),
    "animal":       ("Fox",              _FOX),
    "duck":         ("Duck",             _DUCK),
    "rubber duck":  ("RubberDuck",       _DUCK2),
    "bird":         ("Duck",             _DUCK),
    "chicken":      ("Duck",             _DUCK),
    # ── Space / Sci-fi ────────────────────────────────────────────────────────
    "ufo":          ("RiggedFigure",     _FIG),
    "spaceship":    ("RiggedFigure",     _FIG),
    "spacecraft":   ("RiggedFigure",     _FIG),
    "saucer":       ("RiggedFigure",     _FIG),
    # ── Fantasy ───────────────────────────────────────────────────────────────
    "dragon":       ("DragonDispersion", _DRAG),
    "dinosaur":     ("DragonDispersion", _DRAG),
    "monster":      ("DragonDispersion", _DRAG),
    "skull":        ("ScatteringSkull",  _SKULL),
    "skeleton":     ("ScatteringSkull",  _SKULL),
    # ── Props / objects ───────────────────────────────────────────────────────
    "helmet":       ("FlightHelmet",     _HELM),
    "box":          ("Box",              _BOX),
    "cube":         ("Box",              _BOX),
    "crate":        ("Box",              _BOX),
    "avocado":      ("Avocado",          _AVOC),
    "fruit":        ("Avocado",          _AVOC),
    "food":         ("Avocado",          _AVOC),
}


def _try_fallback(actor_id: str, query: str, dest: str) -> tuple[bool, str]:
    """
    Match query keywords against the fallback catalog.
    Pass 1: exact word match. Pass 2: substring match. Pass 3: synonym match.
    Validates downloaded file is a real GLB before returning success.
    Returns (success, matched_name).
    """
    words = query.lower().split()

    def _attempt(key: str) -> tuple[bool, str]:
        entry = _FALLBACK_CATALOG.get(key)
        if not entry:
            return False, ""
        name, url = entry
        print(f"[Tier3/Fallback] '{query}' matched '{key}' → {name}")
        if _save(url, dest) and _is_valid_glb(dest):
            return True, name
        if os.path.exists(dest):
            os.remove(dest)
        return False, ""

    # Pass 1: exact word match
    for word in words:
        ok, name = _attempt(word)
        if ok:
            return True, name
    # Pass 2: substring — catalog key contained in query string
    query_lower = query.lower()
    for key in _FALLBACK_CATALOG:
        if key in query_lower:
            ok, name = _attempt(key)
            if ok:
                return True, name
    # Pass 3: synonym expansion
    for word in words:
        for syn in _SYNONYM_MAP.get(word, []):
            ok, name = _attempt(syn)
            if ok:
                return True, name
    return False, ""


# ───────────────────────────────────────────────
# Public entry point
# ───────────────────────────────────────────────

def fetch_model(actor_id: str, query: str, on_progress=None) -> str | None:
    """
    Try Tier 0-3 to obtain a GLB for `query`. Returns local path or None.
    `query` may be Chinese — it is normalised to English before any search.
    Progress messages are emitted via on_progress(msg) if provided.
    """
    def _cb(msg: str):
        if on_progress:
            try:
                on_progress(msg)
            except Exception:
                pass

    # Normalise once; use canonical form for cache key AND all tier searches
    norm = _normalize_query(query)
    if norm != query:
        print(f"[AssetFetcher] query normalised: '{query}' → '{norm}'")

    dest = _dest_path(actor_id, norm)
    if os.path.exists(dest):
        if _is_valid_glb(dest):
            _cb(f"📦 {actor_id}: 使用缓存模型")
            return dest
        # Stale / corrupt cache — delete and re-fetch
        os.remove(dest)
        print(f"[AssetFetcher] 缓存文件损坏已删除: {dest}")

    # —— Tier 0: Local builtin models (instant, no network) ——
    _cb(f"🗄️ [Tier0] 检查内置模型库: {norm}")
    if _try_builtin(actor_id, norm, dest):
        size_kb = os.path.getsize(dest) // 1024
        _cb(f"✅ {actor_id}: 内置模型匹配成功 ({size_kb} KB)")
        return dest

    # —— Tier 1: Poly Pizza ——
    if POLYPIZZA_API_KEY:
        _cb(f"🔍 [Tier1] Poly Pizza 搜索: {norm}")
        if _try_polypizza(actor_id, norm, dest):
            size_kb = os.path.getsize(dest) // 1024
            _cb(f"✅ {actor_id}: Poly Pizza 下载完成 ({size_kb} KB)")
            return dest
        _cb("↪️ Poly Pizza 无结果，尝试 Tier 2...")
    else:
        _cb("⚠️ Poly Pizza key 未配置，跳过")

    # —— Tier 2: Sketchfab ——
    if SKETCHFAB_API_KEY:
        _cb(f"🔍 [Tier2] Sketchfab 搜索: {norm}")
        if _try_sketchfab(actor_id, norm, dest):
            size_kb = os.path.getsize(dest) // 1024
            _cb(f"✅ {actor_id}: Sketchfab 下载完成 ({size_kb} KB)")
            return dest
        _cb("↪️ Sketchfab 无结果，尝试 Tier 3...")
    else:
        _cb("⚠️ Sketchfab key 未配置，跳过")

    # —— Tier 3: KhronosGroup CDN fallback ——
    _cb(f"📦 [Tier3] 关键词匹配备用库: {norm}")
    ok, name = _try_fallback(actor_id, norm, dest)
    if ok:
        size_kb = os.path.getsize(dest) // 1024
        _cb(f"✅ {actor_id}: 匹配备用模型 [{name}] ({size_kb} KB)")
        return dest

    _cb(f"❌ {actor_id}: 所有源均失败，退回内置积木")
    return None
