import os
import json
import shutil
from datetime import datetime
from typing import Optional
from backend.config import PROJECTS_DIR

os.makedirs(PROJECTS_DIR, exist_ok=True)

def _proj_dir(pid: str) -> str:
    return os.path.join(PROJECTS_DIR, pid)

def create_project(prompt: str, model: str) -> str:
    """Create a new project directory and return its ID."""
    pid = datetime.now().strftime("%Y%m%d_%H%M%S")
    d = _proj_dir(pid)
    os.makedirs(d, exist_ok=True)
    meta = {
        "id": pid,
        "prompt": prompt,
        "model": model,
        "created_at": datetime.now().isoformat(),
        "status": "generating",
    }
    with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    with open(os.path.join(d, "chat.json"), "w", encoding="utf-8") as f:
        json.dump([], f, ensure_ascii=False, indent=2)
    return pid

def append_chat_entry(pid: str, entry: dict) -> None:
    """Append a single chat log entry."""
    path = os.path.join(_proj_dir(pid), "chat.json")
    entries: list = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            entries = json.load(f)
    entries.append(entry)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

def save_sequence(pid: str, sequence: dict) -> None:
    """Save the director_sequence.json for the project."""
    with open(os.path.join(_proj_dir(pid), "sequence.json"), "w", encoding="utf-8") as f:
        json.dump(sequence, f, ensure_ascii=False, indent=2)

def finalize_project(pid: str, video_copied: bool = False) -> None:
    """Mark project as completed."""
    meta_path = os.path.join(_proj_dir(pid), "meta.json")
    if not os.path.exists(meta_path):
        return
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    meta["status"] = "done" if video_copied else "no_video"
    meta["finished_at"] = datetime.now().isoformat()
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

def save_video(pid: str, src_video_path: str) -> bool:
    """Copy the generated MP4 into the project directory."""
    if not os.path.exists(src_video_path):
        return False
    dst = os.path.join(_proj_dir(pid), "video.mp4")
    shutil.copy2(src_video_path, dst)
    return True

def list_projects() -> list[dict]:
    """Return list of project metadata (newest first)."""
    projects = []
    for name in os.listdir(PROJECTS_DIR):
        d = os.path.join(PROJECTS_DIR, name)
        meta_path = os.path.join(d, "meta.json")
        if not os.path.isdir(d) or not os.path.exists(meta_path):
            continue
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        meta["has_video"] = os.path.exists(os.path.join(d, "video.mp4"))
        meta["has_sequence"] = os.path.exists(os.path.join(d, "sequence.json"))
        projects.append(meta)
    projects.sort(key=lambda p: p.get("created_at", ""), reverse=True)
    return projects

def get_project(pid: str) -> Optional[dict]:
    """Return full project data: meta + chat + sequence."""
    d = _proj_dir(pid)
    if not os.path.exists(d):
        return None
    result: dict = {}
    meta_path = os.path.join(d, "meta.json")
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            result["meta"] = json.load(f)
    chat_path = os.path.join(d, "chat.json")
    if os.path.exists(chat_path):
        with open(chat_path, "r", encoding="utf-8") as f:
            result["chat"] = json.load(f)
    seq_path = os.path.join(d, "sequence.json")
    if os.path.exists(seq_path):
        with open(seq_path, "r", encoding="utf-8") as f:
            result["sequence"] = json.load(f)
    result["has_video"] = os.path.exists(os.path.join(d, "video.mp4"))
    return result

def get_project_video_path(pid: str) -> Optional[str]:
    p = os.path.join(_proj_dir(pid), "video.mp4")
    return p if os.path.exists(p) else None
