"""
Scene draft storage service.
Stores and retrieves scene drafts for user review before final rendering.
"""
import os
import json
import uuid
from datetime import datetime
from backend.config import PROJECTS_DIR

_DRAFT_DIR = os.path.join(PROJECTS_DIR, "drafts")
os.makedirs(_DRAFT_DIR, exist_ok=True)


def _draft_path(draft_id: str) -> str:
    return os.path.join(_DRAFT_DIR, f"{draft_id}.json")


def create_draft(prompt: str, scene_data: dict) -> str:
    """Create a new scene draft and return its ID."""
    draft_id = str(uuid.uuid4())
    draft = {
        "draft_id": draft_id,
        "prompt": prompt,
        "status": "draft",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        **scene_data,
        "user_notes": ""
    }
    with open(_draft_path(draft_id), "w", encoding="utf-8") as f:
        json.dump(draft, f, indent=2, ensure_ascii=False)
    return draft_id


def get_draft(draft_id: str) -> dict | None:
    """Get a scene draft by ID."""
    path = _draft_path(draft_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def update_draft(draft_id: str, updates: dict) -> dict | None:
    """Update a scene draft with new data."""
    draft = get_draft(draft_id)
    if not draft:
        return None
    draft.update(updates)
    draft["updated_at"] = datetime.now().isoformat()
    with open(_draft_path(draft_id), "w", encoding="utf-8") as f:
        json.dump(draft, f, indent=2, ensure_ascii=False)
    return draft


def list_drafts() -> list[dict]:
    """List all scene drafts."""
    drafts = []
    for filename in os.listdir(_DRAFT_DIR):
        if filename.endswith(".json"):
            with open(os.path.join(_DRAFT_DIR, filename), "r", encoding="utf-8") as f:
                drafts.append(json.load(f))
    return sorted(drafts, key=lambda x: x["created_at"], reverse=True)


def delete_draft(draft_id: str) -> bool:
    """Delete a scene draft."""
    path = _draft_path(draft_id)
    if not os.path.exists(path):
        return False
    os.remove(path)
    return True
