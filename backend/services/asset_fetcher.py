"""
3-tier CC0 3D model download service.

Tier 1 — Poly Pizza (requires free API key from https://poly.pizza)
          Set env var: POLYPIZZA_API_KEY=<your_key>

Tier 2 — Sketchfab (requires free API key from https://sketchfab.com/settings#api)
          Set env var: SKETCHFAB_API_KEY=<your_key>

Tier 3 — KhronosGroup / Quaternius CDN fallback (no key, keyword→stable URL map)
          Always works, limited selection.
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
_sketchfab_dead  = False

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
    qs = urllib.parse.urlencode({"q": query, "limit": limit})
    url = f"https://api.poly.pizza/v1/search?{qs}"
    try:
        raw  = _get(url, extra_headers={"x-api-key": POLYPIZZA_API_KEY})
        data = json.loads(raw)
        results = data.get("results") or data.get("resources") or data.get("data") or data.get("models") or []
        print(f"[Tier1/PolyPizza] '{query}' → {len(results)} results")
        return results
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            _polypizza_dead = True
            print(f"[Tier1/PolyPizza] HTTP {e.code} — 熔断，本次会话跳过所有后续 Poly Pizza 请求")
        else:
            print(f"[Tier1/PolyPizza] HTTP {e.code}: {e.reason}")
    except Exception as e:
        print(f"[Tier1/PolyPizza] Error: {e}")
    return []


def _polypizza_glb_url(model: dict) -> str | None:
    for key in ("Download", "download", "download_url", "file"):
        v = model.get(key)
        if isinstance(v, str) and v.startswith("http"):
            return v
    dl = model.get("download") or model.get("Download")
    if isinstance(dl, dict):
        return dl.get("glb") or next(iter(dl.values()), None)
    return None


def _try_polypizza(actor_id: str, query: str, dest: str) -> bool:
    results = _polypizza_search(query)
    if not results and len(query.split()) > 2:
        results = _polypizza_search(query.split()[-1])  # retry single keyword
    for m in results:
        url = _polypizza_glb_url(m)
        if url and _save(url, dest):
            return True
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
    if not results and len(query.split()) > 2:
        results = _sketchfab_search(query.split()[-1])
    for m in results:
        uid = m.get("uid")
        if not uid:
            continue
        dl_url = _sketchfab_download_url(uid)
        if dl_url and _save(dl_url, dest, extra_headers={"Authorization": f"Token {SKETCHFAB_API_KEY}"}):
            return True
    return False


# ───────────────────────────────────────────────
# Tier 3: KhronosGroup + Quaternius stable CDN (no key)
# Maps common search keywords to known stable CC0 GLB URLs
# ───────────────────────────────────────────────

# New confirmed repo: glTF-Sample-Assets (replaces archived glTF-Sample-Models)
# Only models with verified glTF-Binary subdirectory are listed here.
_KGLTF = "https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/main/Models"

# keyword → (display_name, glb_url)   — all URLs confirmed to have GLB variant
_FALLBACK_CATALOG: dict[str, tuple[str, str]] = {
    # ── Vehicles ──────────────────────────────────────────────────────────────
    "truck":      ("CesiumMilkTruck", f"{_KGLTF}/CesiumMilkTruck/glTF-Binary/CesiumMilkTruck.glb"),
    "car":        ("CesiumMilkTruck", f"{_KGLTF}/CesiumMilkTruck/glTF-Binary/CesiumMilkTruck.glb"),
    "vehicle":    ("CesiumMilkTruck", f"{_KGLTF}/CesiumMilkTruck/glTF-Binary/CesiumMilkTruck.glb"),
    # ── Aircraft ──────────────────────────────────────────────────────────────
    "plane":      ("CesiumMilkTruck", f"{_KGLTF}/CesiumMilkTruck/glTF-Binary/CesiumMilkTruck.glb"),
    "jet":        ("CesiumMilkTruck", f"{_KGLTF}/CesiumMilkTruck/glTF-Binary/CesiumMilkTruck.glb"),
    "aircraft":   ("CesiumMilkTruck", f"{_KGLTF}/CesiumMilkTruck/glTF-Binary/CesiumMilkTruck.glb"),
    "airliner":   ("CesiumMilkTruck", f"{_KGLTF}/CesiumMilkTruck/glTF-Binary/CesiumMilkTruck.glb"),
    "fighter":    ("CesiumMilkTruck", f"{_KGLTF}/CesiumMilkTruck/glTF-Binary/CesiumMilkTruck.glb"),
    "bomber":     ("CesiumMilkTruck", f"{_KGLTF}/CesiumMilkTruck/glTF-Binary/CesiumMilkTruck.glb"),
    "helicopter": ("CesiumMilkTruck", f"{_KGLTF}/CesiumMilkTruck/glTF-Binary/CesiumMilkTruck.glb"),
    "rocket":     ("CesiumMilkTruck", f"{_KGLTF}/CesiumMilkTruck/glTF-Binary/CesiumMilkTruck.glb"),
    # ── Characters ────────────────────────────────────────────────────────────
    "human":      ("CesiumMan",       f"{_KGLTF}/CesiumMan/glTF-Binary/CesiumMan.glb"),
    "person":     ("CesiumMan",       f"{_KGLTF}/CesiumMan/glTF-Binary/CesiumMan.glb"),
    "man":        ("CesiumMan",       f"{_KGLTF}/CesiumMan/glTF-Binary/CesiumMan.glb"),
    "walker":     ("CesiumMan",       f"{_KGLTF}/CesiumMan/glTF-Binary/CesiumMan.glb"),
    "soldier":    ("CesiumMan",       f"{_KGLTF}/CesiumMan/glTF-Binary/CesiumMan.glb"),
    "pilot":      ("CesiumMan",       f"{_KGLTF}/CesiumMan/glTF-Binary/CesiumMan.glb"),
    "alien":      ("RiggedFigure",    f"{_KGLTF}/RiggedFigure/glTF-Binary/RiggedFigure.glb"),
    "robot":      ("RiggedFigure",    f"{_KGLTF}/RiggedFigure/glTF-Binary/RiggedFigure.glb"),
    "creature":   ("RiggedFigure",    f"{_KGLTF}/RiggedFigure/glTF-Binary/RiggedFigure.glb"),
    # ── Animals ───────────────────────────────────────────────────────────────
    "fox":        ("Fox",             f"{_KGLTF}/Fox/glTF-Binary/Fox.glb"),
    "animal":     ("Fox",             f"{_KGLTF}/Fox/glTF-Binary/Fox.glb"),
    "wolf":       ("Fox",             f"{_KGLTF}/Fox/glTF-Binary/Fox.glb"),
    "dog":        ("Fox",             f"{_KGLTF}/Fox/glTF-Binary/Fox.glb"),
    "duck":       ("Duck",            f"{_KGLTF}/Duck/glTF-Binary/Duck.glb"),
    "bird":       ("Duck",            f"{_KGLTF}/Duck/glTF-Binary/Duck.glb"),
    # ── Space / Sci-fi ────────────────────────────────────────────────────────
    "ufo":        ("CesiumMilkTruck", f"{_KGLTF}/CesiumMilkTruck/glTF-Binary/CesiumMilkTruck.glb"),
    "spaceship":  ("CesiumMilkTruck", f"{_KGLTF}/CesiumMilkTruck/glTF-Binary/CesiumMilkTruck.glb"),
    "spacecraft": ("CesiumMilkTruck", f"{_KGLTF}/CesiumMilkTruck/glTF-Binary/CesiumMilkTruck.glb"),
    "saucer":     ("CesiumMilkTruck", f"{_KGLTF}/CesiumMilkTruck/glTF-Binary/CesiumMilkTruck.glb"),
    # ── Fantasy ───────────────────────────────────────────────────────────────
    "dragon":     ("DragonDispersion", f"{_KGLTF}/DragonDispersion/glTF-Binary/DragonDispersion.glb"),
    "monster":    ("DragonDispersion", f"{_KGLTF}/DragonDispersion/glTF-Binary/DragonDispersion.glb"),
    "skull":      ("ScatteringSkull",  f"{_KGLTF}/ScatteringSkull/glTF-Binary/ScatteringSkull.glb"),
    "skeleton":   ("ScatteringSkull",  f"{_KGLTF}/ScatteringSkull/glTF-Binary/ScatteringSkull.glb"),
}


def _try_fallback(actor_id: str, query: str, dest: str) -> tuple[bool, str]:
    """
    Match query keywords against the fallback catalog.
    Tries exact word match first, then substring containment.
    Returns (success, matched_name).
    """
    words = query.lower().split()
    # Pass 1: exact word match
    for word in words:
        entry = _FALLBACK_CATALOG.get(word)
        if entry:
            name, url = entry
            print(f"[Tier3/Fallback] '{query}' matched '{word}' → {name}")
            return _save(url, dest), name
    # Pass 2: substring — catalog key contained in any query word (e.g. "aircraft" in "aircraft")
    query_lower = query.lower()
    for key, entry in _FALLBACK_CATALOG.items():
        if key in query_lower:
            name, url = entry
            print(f"[Tier3/Fallback] '{query}' substring matched '{key}' → {name}")
            return _save(url, dest), name
    return False, ""


# ───────────────────────────────────────────────
# Public entry point
# ───────────────────────────────────────────────

def fetch_model(actor_id: str, query: str, on_progress=None) -> str | None:
    """
    Try all 3 tiers to get a GLB for `query`. Returns local path or None.
    Progress messages are emitted via on_progress(msg) if provided.
    """
    def _cb(msg: str):
        if on_progress:
            try:
                on_progress(msg)
            except Exception:
                pass

    dest = _dest_path(actor_id, query)
    if os.path.exists(dest):
        _cb(f"📦 {actor_id}: 使用缓存模型")
        return dest

    # —— Tier 0: Local builtin models (instant, no network) ——
    _cb(f"🗄️ [Tier0] 检查内置模型库: {query}")
    if _try_builtin(actor_id, query, dest):
        size_kb = os.path.getsize(dest) // 1024
        _cb(f"✅ {actor_id}: 内置模型匹配成功 ({size_kb} KB)")
        return dest

    # —— Tier 1: Poly Pizza ——
    if POLYPIZZA_API_KEY:
        _cb(f"🔍 [Tier1] Poly Pizza 搜索: {query}")
        if _try_polypizza(actor_id, query, dest):
            size_kb = os.path.getsize(dest) // 1024
            _cb(f"✅ {actor_id}: Poly Pizza 下载完成 ({size_kb} KB)")
            return dest
        _cb(f"↪️ Poly Pizza 无结果，尝试 Tier 2...")
    else:
        _cb("⚠️ Poly Pizza key 未配置，跳过")

    # —— Tier 2: Sketchfab ——
    if SKETCHFAB_API_KEY:
        _cb(f"� [Tier2] Sketchfab 搜索: {query}")
        if _try_sketchfab(actor_id, query, dest):
            size_kb = os.path.getsize(dest) // 1024
            _cb(f"✅ {actor_id}: Sketchfab 下载完成 ({size_kb} KB)")
            return dest
        _cb("↪️ Sketchfab 无结果，尝试 Tier 3...")
    else:
        _cb("⚠️ Sketchfab key 未配置，跳过")

    # —— Tier 3: KhronosGroup CDN fallback ——
    _cb(f"📦 [Tier3] 关键词匹配备用库: {query}")
    ok, name = _try_fallback(actor_id, query, dest)
    if ok:
        size_kb = os.path.getsize(dest) // 1024
        _cb(f"✅ {actor_id}: 匹配备用模型 [{name}] ({size_kb} KB)")
        return dest

    _cb(f"❌ {actor_id}: 所有源均失败，退回内置积木")
    return None
