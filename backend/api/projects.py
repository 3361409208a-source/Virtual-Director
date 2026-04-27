from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from backend.services.project_store import list_projects, get_project, get_project_video_path
import backend.config as config

router = APIRouter()


class ConfigUpdate(BaseModel):
    enable_model_search: bool | None = None


@router.get("/config")
def get_config():
    """Get current configuration."""
    return {"enable_model_search": config.ENABLE_MODEL_SEARCH}


@router.post("/config")
def update_config(cfg: ConfigUpdate):
    """Update configuration (runtime only, not persisted to .env)."""
    if cfg.enable_model_search is not None:
        config.ENABLE_MODEL_SEARCH = cfg.enable_model_search
    return {"enable_model_search": config.ENABLE_MODEL_SEARCH}


@router.get("/projects")
def get_projects(limit: int = 50, offset: int = 0):
    """List saved projects with pagination (newest first)."""
    return {"projects": list_projects(limit=limit, offset=offset)}


@router.get("/projects/{pid}")
def get_project_detail(pid: str):
    """Get full project: meta + chat + sequence (meta fields flattened to top level)."""
    data = get_project(pid)
    if not data:
        return JSONResponse(status_code=404, content={"error": "Project not found"})
    # Flatten: merge meta dict into top level so frontend can access detail.id, detail.prompt etc.
    flat = {**data.get("meta", {}), **{k: v for k, v in data.items() if k != "meta"}}
    return flat

@router.get("/projects/{pid}/video")
def get_project_video(pid: str):
    """Stream the MP4 video for a project."""
    path = get_project_video_path(pid)
    if not path:
        return JSONResponse(status_code=404, content={"error": "Video not found"})
    return FileResponse(path, media_type="video/mp4", filename="video.mp4")
