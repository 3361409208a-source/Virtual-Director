import os
import re
import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from backend.config import GODOT_DIR
from backend.services.llm import llm_call
from backend.tools.definitions import ai_model_tool
from backend.services.glb_builder import build_glb

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


# ── AI Generate a model ──────────────────────────────────────────────────────

class AIGenerateRequest(BaseModel):
    prompt: str
    model: str = "deepseek-chat"

@router.post("/models/ai-generate")
async def ai_generate_model(req: AIGenerateRequest):
    """Call LLM to generate a composite model, convert to GLB, save to custom/."""
    system = (
        "你是一位精通 3D 建模的技术总监（3D TD）。\n"
        "用 box（长方体）、sphere（球体）、cylinder（圆柱体）三种基本体拼装用户描述的模型。\n\n"
        "拼装规范：\n"
        "- 坐标原点(0,0,0)为模型几何中心底部，Y轴朝上\n"
        "- 人形：身高约 1.8m，躯干 box {x:0.45,y:0.6,z:0.25} y=0.6 | 头 sphere {x:0.25,y:0.25,z:0.25} y=1.4\n"
        "- 车辆：车身 box {x:1.8,y:0.5,z:4.0} | 4个车轮 cylinder {x:0.4,y:0.4,z:0.2} 四角\n"
        "- 飞机：机身 box {x:0.8,y:0.6,z:6.0} | 机翼 box {x:10,y:0.15,z:2.0}\n"
        "- 精细度：至少 6 个零件（人 8+，车 8+，飞机 6+）\n"
        "- 颜色必须符合描述：红色(r=0.9,g=0.1,b=0.1)，金属灰(r=0.6,g=0.62,b=0.65)，皮肤色(r=0.9,g=0.75,b=0.6)\n"
        "- model_name 使用英文 snake_case"
    )
    try:
        result = llm_call(system, req.prompt, ai_model_tool)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM 调用失败: {e}")

    parts = result.get("parts", [])
    if not parts:
        raise HTTPException(status_code=500, detail="模型生成失败：LLM 未返回零件数据")

    # Convert composite → GLB bytes
    try:
        glb_bytes = build_glb(parts)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GLB 构建失败: {e}")

    # Save to custom/
    model_name = re.sub(r"[^\w\-]", "_", result.get("model_name", "ai_model"))
    custom_dir = _CATEGORIES["custom"]
    os.makedirs(custom_dir, exist_ok=True)
    filename = f"{model_name}.glb"
    dest = os.path.join(custom_dir, filename)
    with open(dest, "wb") as f:
        f.write(glb_bytes)

    size_kb = len(glb_bytes) // 1024
    return {
        "ok":          True,
        "filename":    filename,
        "model_name":  model_name,
        "description": result.get("description", req.prompt),
        "parts_count": len(parts),
        "size_kb":     size_kb,
        "url":         f"/api/models/custom/{filename}",
        "parts":       parts,
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
