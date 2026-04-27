import os
import re
import json
import shutil
import asyncio
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from backend.config import GODOT_DIR
from backend.services.llm import llm_call, set_model
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
    base_model: str = ""   # optional reference model name

def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

@router.post("/models/ai-generate")
async def ai_generate_model(req: AIGenerateRequest):
    """SSE streaming: streams LLM tokens then sends done/error event."""

    loop = asyncio.get_running_loop()
    token_q: asyncio.Queue = asyncio.Queue()

    def token_cb(tok: str):
        asyncio.run_coroutine_threadsafe(token_q.put({"type": "content", "msg": tok}), loop)

    def thinking_cb(tok: str):
        asyncio.run_coroutine_threadsafe(token_q.put({"type": "thinking", "msg": tok}), loop)

    base_ctx = ""
    if req.base_model:
        base_ctx = f"\n参考模型名称：{req.base_model}（以此为灵感来源，但须按用户描述重新设计）\n"

    system = (
        "你是一位精通 3D 建模的技术总监（3D TD）。\n"
        "用 box（长方体）、sphere（球体）、cylinder（圆柱体）三种基本体拼装用户描述的模型。\n"
        + base_ctx +
        "\n拼装规范：\n"
        "- 坐标原点(0,0,0)为模型几何中心底部，Y轴朝上\n"
        "- 人形：身高约1.8m，躯干box{x:0.45,y:0.6,z:0.25}@y=0.6 | 头sphere{x:0.25}@y=1.4 | 手臂/腿cylinder\n"
        "- 车辆：车身box{x:1.8,y:0.5,z:4.0} | 4个车轮cylinder@四角 | 车顶box{x:1.4,y:0.4,z:2.0}\n"
        "- 飞机：机身box{x:0.8,y:0.6,z:6.0} | 主翼box{x:10,y:0.15,z:2.0} | 尾翼box{x:3,y:0.12,z:1.0}\n"
        "- 最少零件数：人体8+ | 车辆8+ | 飞机6+ | 建筑5+ | 武器3+\n"
        "- 颜色必须精准匹配描述：红色(r=0.9,g=0.1,b=0.1) | 金属(r=0.6,g=0.62,b=0.65) | 皮肤(r=0.9,g=0.75,b=0.6)\n"
        "- model_name 英文snake_case | description 中文一句话\n"
        "- 先用中文思考拆解方案，再输出tool call"
    )

    async def stream():
        try:
            yield _sse({"step": "start", "msg": "🤖 AI 开始分析建模方案..."})

            # Run LLM in thread, stream tokens via queue
            result_holder: dict = {}
            err_holder:    dict = {}

            def run_llm():
                try:
                    set_model(req.model)
                    result_holder["r"] = llm_call(system, req.prompt, ai_model_tool, token_cb=token_cb, thinking_cb=thinking_cb)
                except Exception as e:
                    err_holder["e"] = e
                finally:
                    asyncio.run_coroutine_threadsafe(token_q.put(None), loop)

            import threading
            t = threading.Thread(target=run_llm, daemon=True)
            t.start()

            # Stream tokens as they arrive
            while True:
                tok = await token_q.get()
                if tok is None:
                    break
                if isinstance(tok, dict):
                    if tok["type"] == "thinking":
                        yield _sse({"step": "thinking", "msg": tok["msg"]})
                    else:
                        yield _sse({"step": "token", "msg": tok["msg"]})
                else:
                    yield _sse({"step": "token", "msg": tok})

            if "e" in err_holder:
                yield _sse({"step": "error", "msg": f"LLM 调用失败: {err_holder['e']}"})
                return

            result = result_holder.get("r", {})
            parts  = result.get("parts", [])
            if not parts:
                yield _sse({"step": "error", "msg": "模型生成失败：LLM 未返回零件数据"})
                return

            yield _sse({"step": "building", "msg": f"🔧 组装 {len(parts)} 个零件 → GLB..."})

            try:
                glb_bytes = await asyncio.to_thread(build_glb, parts)
            except Exception as e:
                yield _sse({"step": "error", "msg": f"GLB 构建失败: {e}"})
                return

            model_name = re.sub(r"[^\w\-]", "_", result.get("model_name", "ai_model"))
            custom_dir = _CATEGORIES["custom"]
            os.makedirs(custom_dir, exist_ok=True)
            filename = f"{model_name}.glb"
            dest = os.path.join(custom_dir, filename)
            with open(dest, "wb") as f:
                f.write(glb_bytes)

            size_kb = len(glb_bytes) // 1024
            yield _sse({
                "step":        "done",
                "msg":         f"✅ 模型生成完成：{filename} ({size_kb} KB)",
                "filename":    filename,
                "model_name":  model_name,
                "description": result.get("description", req.prompt),
                "parts_count": len(parts),
                "size_kb":     size_kb,
                "url":         f"/api/models/custom/{filename}",
            })

        except Exception as e:
            yield _sse({"step": "error", "msg": str(e)})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
