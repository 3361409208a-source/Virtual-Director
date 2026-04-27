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
        for fname in os.listdir(dir_path):
            if not fname.lower().endswith(".glb"):
                continue
            full = os.path.join(dir_path, fname)
            stat = os.stat(full)
            result.append({
                "id":       f"{cat}/{fname}",
                "category": cat,
                "filename": fname,
                "name":     os.path.splitext(fname)[0],
                "size_kb":  stat.st_size // 1024,
                "url":      f"/api/models/{cat}/{fname}",
                "mtime":    stat.st_mtime,
            })
    # Sort newest first
    result.sort(key=lambda m: m["mtime"], reverse=True)
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
    model: str = "astron-code-latest"
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
        "你是3D建模技术总监，擅长用基本体最大化还原复杂视觉形象。\n"
        "可用形状：box(长方体)、sphere(球体)、cylinder(圆柱)、cone(圆锥)、capsule(胶囊=圆柱+半球端)\n"
        "可用材质：颜色(RGBA)、metallic(金属度0-1)、roughness(粗糙度0-1)、emissive(自发光)\n"
        + base_ctx +
        "\n═══ 核心工作流：先深度分析，再拼装 ═══\n"
        "输出tool call前，必须先用中文完成以下分析：\n"
        "\n【步骤1】视觉特征提取：列出描述中所有可识别的视觉特征，按重要性排序。\n"
        "  例「清朝官服僵尸」→ ①清朝官帽(顶珠+帽翅) ②深蓝长袍 ③胸前补子 ④宽袖 ⑤双手前伸 ⑥跳跃 ⑦苍白皮肤\n"
        "\n【步骤2】近似策略：对每个特征，思考如何用基本体最佳近似：\n"
        "  - 识别性特征(缺少则无法辨认)→重点还原，用更多零件+精准颜色+材质\n"
        "  - 暗示性特征→1-2个零件+精准颜色暗示即可\n"
        "  - 无法用基本体表达→跳过，零件预算分配给可表达的识别性特征\n"
        "  例：官帽=capsule帽体+小sphere顶珠+两个thin box帽翅(3零件高度识别)\n"
        "  例：补子=躯干前叠加thin box金色(r=0.85,g=0.7,b=0.2,metallic=0.6)(1零件暗示刺绣)\n"
        "  例：盔甲=box+metallic=0.8,roughness=0.3(金属质感)\n"
        "  例：魔法光效=sphere+emissive{r:0.2,g:0.5,b:1,intensity:3}\n"
        "\n【步骤3】零件预算：复杂度决定总零件数(12-25)，识别性特征占60%，暗示性30%，基础10%\n"
        "\n═══ 形状选择指南 ═══\n"
        "- box：方形结构(躯干/车身/建筑/衣袍面板/帽子帽翅/装饰板)\n"
        "- sphere：球形(头部/顶珠/球体/眼球/关节球)\n"
        "- cylinder：柱形(手臂/腿/轮子/树干/管道/武器杆)\n"
        "- cone：锥形(帽子尖顶/塔尖/锥形屋顶/裙摆/锥形武器)\n"
        "- capsule：胶囊(人体躯干/肢体/圆角柱体/手指/脖子)\n"
        "\n═══ 拼装规范 ═══\n"
        "- 原点(0,0,0)=模型底部中心，Y朝上\n"
        "- 人形：身高1.8m，躯干capsule{x:0.45,y:0.6,z:0.25}@y=0.6 | 头sphere{x:0.25}@y=1.4 | 手臂/腿cylinder\n"
        "- 车辆：车身box{x:1.8,y:0.5,z:4.0} | 4轮cylinder@四角 | 车顶box{x:1.4,y:0.4,z:2.0}\n"
        "- 飞机：机身box{x:0.8,y:0.6,z:6.0} | 主翼box{x:10,y:0.15,z:2.0} | 尾翼box{x:3,y:0.12,z:1.0}\n"
        "- 最少零件：人体12+ | 车辆8+ | 飞机6+ | 建筑5+ | 武器3+ | 复杂角色(服饰/装备)18+\n"
        "\n═══ 颜色精准匹配（最强视觉识别信号）═══\n"
        "- 红(0.9,0.1,0.1) | 金属(0.6,0.62,0.65) | 皮肤(0.9,0.75,0.6) | 苍白(0.85,0.82,0.78)\n"
        "- 深蓝官服(0.08,0.1,0.35) | 黑(0.1,0.1,0.1) | 金(0.85,0.7,0.2) | 木(0.55,0.35,0.15)\n"
        "- 绿(0.15,0.6,0.15) | 白(0.95,0.95,0.95) | 棕(0.45,0.3,0.15) | 紫(0.5,0.15,0.6)\n"
        "\n═══ 材质属性指南 ═══\n"
        "- metallic: 布料/皮肤=0, 木头=0, 金属盔甲=0.8, 黄金=1.0, 玻璃=0.3\n"
        "- roughness: 镜面/丝绸=0.2, 金属=0.3, 皮肤=0.7, 布料=0.9, 哑光=1.0\n"
        "- emissive: 仅用于发光体(灯/火焰/魔法/屏幕), 普通物体不要设置\n"
        "- color.a: 透明度, 玻璃=0.3-0.5, 半透明=0.5-0.8, 不透明=1.0(默认)\n"
        "\n═══ 高级技巧 ═══\n"
        "- 叠加法：主体表面叠加thin box暗示图案/装饰(补子/铠甲纹章/腰带)\n"
        "- 颜色分割：同部位不同色零件拼接(上衣下裳/左袖右袖)\n"
        "- 姿态表达：旋转零件表达动作(手臂前伸=arm cylinder旋转90°朝前)\n"
        "- 层次感：外层零件略大于内层，形成衣袍/铠甲覆盖效果\n"
        "- 材质区分：同色不同材质(金色布料vs金色金属)靠metallic/roughness区分\n"
        "- model_name 英文snake_case | description 中文一句话\n"
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
