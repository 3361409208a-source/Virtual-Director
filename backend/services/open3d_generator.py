import base64
import json
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from backend.config import GODOT_DIR, OPEN3D_GENERATOR_URL

CUSTOM_DIR = os.path.join(GODOT_DIR, "assets", "custom")


class Open3DGeneratorUnavailable(RuntimeError):
    pass


def _safe_name(name: str) -> str:
    return re.sub(r"[^\w\-]", "_", name).strip("_") or "open3d_model"


def _copy_glb_to_custom(src: str, model_name: str) -> str:
    os.makedirs(CUSTOM_DIR, exist_ok=True)
    filename = f"{_safe_name(model_name)}.glb"
    dest = os.path.join(CUSTOM_DIR, filename)
    shutil.copyfile(src, dest)
    return dest


def _download_glb(url: str) -> str:
    with urllib.request.urlopen(url, timeout=600) as resp:
        data = resp.read()
    fd, path = tempfile.mkstemp(suffix=".glb")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return path


def _decode_json_response(payload: bytes, base_url: str) -> str:
    data = json.loads(payload.decode("utf-8"))
    if data.get("glb_base64"):
        fd, path = tempfile.mkstemp(suffix=".glb")
        with os.fdopen(fd, "wb") as f:
            f.write(base64.b64decode(data["glb_base64"]))
        return path
    if data.get("path") and os.path.exists(data["path"]):
        return data["path"]
    if data.get("url"):
        url = data["url"]
        if url.startswith("/"):
            url = base_url + url
        return _download_glb(url)
    raise Open3DGeneratorUnavailable("Open3D service did not return glb_base64/path/url")


def generate_open3d_asset(prompt: str, model_name: str = "open3d_model") -> dict:
    if not OPEN3D_GENERATOR_URL:
        return _generate_local_shape(prompt, model_name)

    payload = json.dumps({"prompt": prompt, "format": "glb"}).encode("utf-8")
    req = urllib.request.Request(
        f"{OPEN3D_GENERATOR_URL}/generate",
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json, model/gltf-binary"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            content_type = resp.headers.get("Content-Type", "")
            body = resp.read()
    except urllib.error.URLError as exc:
        raise Open3DGeneratorUnavailable(f"Open3D service request failed: {exc}") from exc

    if "model/gltf-binary" in content_type or body[:4] == b"glTF":
        fd, tmp_path = tempfile.mkstemp(suffix=".glb")
        with os.fdopen(fd, "wb") as f:
            f.write(body)
    else:
        tmp_path = _decode_json_response(body, OPEN3D_GENERATOR_URL)

    dest = _copy_glb_to_custom(tmp_path, model_name)
    try:
        if Path(tmp_path).exists() and Path(tmp_path).resolve() != Path(dest).resolve():
            os.remove(tmp_path)
    except Exception:
        pass

    return {
        "filename": os.path.basename(dest),
        "path": dest,
        "url": f"/api/models/custom/{os.path.basename(dest)}",
        "size_kb": os.path.getsize(dest) // 1024,
    }
