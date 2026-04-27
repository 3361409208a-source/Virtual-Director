import os
import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from backend.config import GODOT_DIR

router = APIRouter()

_CATEGORIES = {
    "builtin":    os.path.join(GODOT_DIR, "assets", "builtin"),
    "downloaded": os.path.join(GODOT_DIR, "assets", "downloaded"),
    "custom":     os.path.join(GODOT_DIR, "assets", "custom"),
}

# ── List all models ──────────────────────────────────────────────────────────

@router.get("/models")
def list_models():
    result = []
    for cat, dir_path in _CATEGORIES.items():
        if not os.path.isdir(dir_path):
            continue
        for fname in sorted(os.listdir(dir_path)):
            if not fname.lower().endswith(".glb"):
                continue
            full = os.path.join(dir_path, fname)
            result.append({
                "id":       f"{cat}/{fname}",
                "category": cat,
                "filename": fname,
                "name":     os.path.splitext(fname)[0],
                "size_kb":  os.path.getsize(full) // 1024,
                "url":      f"/api/models/{cat}/{fname}",
            })
    return {"models": result}


# ── Serve a model file ───────────────────────────────────────────────────────

@router.get("/models/{category}/{filename}")
def get_model_file(category: str, filename: str):
    if category not in _CATEGORIES:
        raise HTTPException(status_code=404, detail="Unknown category")
    if not filename.lower().endswith(".glb"):
        raise HTTPException(status_code=400, detail="Only GLB files supported")
    path = os.path.join(_CATEGORIES[category], filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Model not found")
    return FileResponse(
        path,
        media_type="model/gltf-binary",
        filename=filename,
        headers={"Access-Control-Allow-Origin": "*"},
    )


# ── Upload a custom model ────────────────────────────────────────────────────

@router.post("/models/upload")
async def upload_model(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".glb"):
        raise HTTPException(status_code=400, detail="Only .glb files are accepted")
    custom_dir = _CATEGORIES["custom"]
    os.makedirs(custom_dir, exist_ok=True)
    dest = os.path.join(custom_dir, file.filename)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    size_kb = os.path.getsize(dest) // 1024
    return {
        "ok":       True,
        "filename": file.filename,
        "size_kb":  size_kb,
        "url":      f"/api/models/custom/{file.filename}",
    }


# ── Delete a custom model ────────────────────────────────────────────────────

@router.delete("/models/custom/{filename}")
def delete_custom_model(filename: str):
    if not filename.lower().endswith(".glb"):
        raise HTTPException(status_code=400, detail="Only GLB files supported")
    path = os.path.join(_CATEGORIES["custom"], filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    os.remove(path)
    return {"ok": True}
