from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.services.scene_draft_store import create_draft, get_draft, update_draft, list_drafts, delete_draft

router = APIRouter()


class SceneDraftRequest(BaseModel):
    prompt: str
    scene: dict
    actors: list[dict]
    cameras: list[dict]


class SceneDraftUpdate(BaseModel):
    scene: dict | None = None
    actors: list[dict] | None = None
    cameras: list[dict] | None = None
    user_notes: str | None = None
    status: str | None = None


@router.post("/draft")
def create_scene_draft(req: SceneDraftRequest):
    """Create a new scene draft from AI generation."""
    draft_data = {
        "scene": req.scene,
        "actors": req.actors,
        "cameras": req.cameras
    }
    draft_id = create_draft(req.prompt, draft_data)
    draft = get_draft(draft_id)
    return draft


@router.get("/draft/{draft_id}")
def get_scene_draft(draft_id: str):
    """Get a scene draft by ID."""
    draft = get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft


@router.get("/drafts")
def list_scene_drafts():
    """List all scene drafts."""
    return {"drafts": list_drafts()}


@router.put("/draft/{draft_id}")
def update_scene_draft(draft_id: str, updates: SceneDraftUpdate):
    """Update a scene draft (for user modifications)."""
    update_data = {}
    if updates.scene is not None:
        update_data["scene"] = updates.scene
    if updates.actors is not None:
        update_data["actors"] = updates.actors
    if updates.cameras is not None:
        update_data["cameras"] = updates.cameras
    if updates.user_notes is not None:
        update_data["user_notes"] = updates.user_notes
    if updates.status is not None:
        update_data["status"] = updates.status

    draft = update_draft(draft_id, update_data)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft


@router.delete("/draft/{draft_id}")
def delete_scene_draft(draft_id: str):
    """Delete a scene draft."""
    if not delete_draft(draft_id):
        raise HTTPException(status_code=404, detail="Draft not found")
    return {"success": True}


@router.post("/draft/{draft_id}/confirm")
def confirm_scene_draft(draft_id: str):
    """Confirm a scene draft and mark it as approved for rendering."""
    draft = update_draft(draft_id, {"status": "approved"})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft
