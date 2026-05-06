"""
Scene Generator — 场景建模服务
用 AI 规划整体场景布局，再为每个物体单独生成 GLB，最终输出场景描述符 JSON。
"""
import asyncio
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from backend.config import GODOT_DIR
from backend.services.llm import llm_call, set_model
from backend.services.glb_builder import build_glb
from backend.tools.definitions import scene_layout_tool, ai_model_tool

CUSTOM_DIR = os.path.join(GODOT_DIR, "assets", "custom")

_SCENE_SYSTEM = (
    "你是世界级的 3D 场景总导演，擅长构建充满故事感的沉浸式世界。\n"
    "\n═══ [场景规划哲学] ═══\n"
    "你思考的不是单个模型，而是整个世界的空间构成：\n"
    "- 【主视觉锚点】：场景中最引人注目的核心建筑或标志物（放置在原点附近）\n"
    "- 【空间层次】：前景细节物 → 中景主体 → 远景背景，形成纵深感\n"
    "- 【故事密度】：每个物体都有存在的理由，共同讲述一个场景故事\n"
    "\n═══ [输出要求] ═══\n"
    "- 规划 5-12 个独立物体，覆盖结构、道具、植被等类别\n"
    "- 为每个物体提供精准的英文建模提示词（model_prompt），要具体描述材质/颜色/风格\n"
    "- 设计合理的空间坐标，让场景有层次感\n"
    "- 每个物体都要独特，避免重复\n"
    "开始你的场景构想："
)

_OBJ_SYSTEM = (
    "你是超现实数字生命架构师，正在为一个大型场景生成单个物体模型。\n"
    "该物体将被放置在一个完整场景中，必须与周边环境风格一致。\n"
    "要求：30-50 个零件，材质精细，可以加入奇异的发光或透明元素。\n"
    "直接输出 JSON，不要解释。"
)


def _build_object_glb(obj: dict, llm_model: str, progress_cb=None) -> dict | None:
    """为单个场景物体生成 GLB 文件，返回物体信息+文件路径。"""
    obj_id = obj.get("id", "unknown")
    prompt = obj.get("model_prompt", obj.get("name", ""))
    name = obj.get("name", obj_id)

    if progress_cb:
        progress_cb(f"🔧 [{name}] 正在建模...")

    try:
        set_model(llm_model)
        result = llm_call(_OBJ_SYSTEM, prompt, ai_model_tool)
        parts = result.get("parts", [])
        if not parts:
            if progress_cb:
                progress_cb(f"⚠️ [{name}] LLM 未返回零件数据，跳过")
            return None

        glb_bytes = build_glb(parts)
        safe_id = re.sub(r"[^\w\-]", "_", obj_id)
        filename = f"scene_{safe_id}.glb"
        os.makedirs(CUSTOM_DIR, exist_ok=True)
        dest = os.path.join(CUSTOM_DIR, filename)
        with open(dest, "wb") as f:
            f.write(glb_bytes)

        if progress_cb:
            progress_cb(f"✅ [{name}] GLB 生成完成 ({len(glb_bytes)//1024} KB, {len(parts)} 零件)")

        return {
            **obj,
            "filename": filename,
            "url": f"/api/models/custom/{filename}",
            "parts_count": len(parts),
            "size_kb": len(glb_bytes) // 1024,
        }
    except Exception as e:
        if progress_cb:
            progress_cb(f"❌ [{name}] 生成失败: {e}")
        return None


async def generate_scene(
    prompt: str,
    llm_model: str = "deepseek-v4-flash",
    token_cb=None,
    thinking_cb=None,
    progress_cb=None,
) -> dict:
    """
    主入口：规划场景 → 并行生成每个物体 GLB → 返回场景描述符
    Returns:
      {
        "scene_name": str,
        "scene_description": str,
        "objects": [ { ...obj_meta, "filename", "url", "parts_count" }, ... ],
        "scene_json_path": str,   # 保存的场景 JSON 文件路径
        "total_objects": int,
        "success_count": int,
      }
    """
    def _cb(msg: str):
        if progress_cb:
            progress_cb(msg)

    _cb("🌍 场景导演正在规划世界布局...")

    # ── Step 1: 规划场景布局 ──
    set_model(llm_model)
    layout = await asyncio.to_thread(
        llm_call,
        _SCENE_SYSTEM,
        prompt,
        scene_layout_tool,
        token_cb,
        thinking_cb,
    )

    objects_plan = layout.get("objects", [])
    scene_name = layout.get("scene_name", "ai_scene")
    scene_desc = layout.get("scene_description", prompt)

    _cb(f"📋 场景规划完成：{scene_name}，共 {len(objects_plan)} 个物体")
    _cb(f"📝 {scene_desc}")

    if not objects_plan:
        raise RuntimeError("场景规划失败：LLM 未返回任何物体")

    # ── Step 2: 并行生成每个物体 GLB ──
    _cb(f"⚙️ 开始并行生成 {len(objects_plan)} 个模型...")

    results = []
    max_workers = min(len(objects_plan), 4)

    def _task(obj):
        return _build_object_glb(obj, llm_model, progress_cb=_cb)

    built = await asyncio.to_thread(
        lambda: list(_run_parallel(objects_plan, _task, max_workers))
    )

    results = [r for r in built if r is not None]
    success_count = len(results)

    _cb(f"🎬 场景建模完成！成功 {success_count}/{len(objects_plan)} 个物体")

    # ── Step 3: 保存场景描述符 JSON ──
    scene_data = {
        "scene_name": scene_name,
        "scene_description": scene_desc,
        "objects": results,
    }

    safe_name = re.sub(r"[^\w\-]", "_", scene_name)
    json_path = os.path.join(CUSTOM_DIR, f"{safe_name}.scene.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(scene_data, f, ensure_ascii=False, indent=2)

    return {
        "scene_name": scene_name,
        "scene_description": scene_desc,
        "objects": results,
        "scene_json_path": json_path,
        "total_objects": len(objects_plan),
        "success_count": success_count,
    }


def _run_parallel(items, task_fn, max_workers):
    """使用线程池并行执行任务，按完成顺序 yield 结果。"""
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(task_fn, item): item for item in items}
        for future in as_completed(futures):
            try:
                yield future.result()
            except Exception:
                yield None
