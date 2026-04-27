from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.generate import router as generate_router
from backend.api.projects import router as projects_router
from backend.api.test_render import router as test_render_router
from backend.api.models import router as models_router
from backend.api.review import router as review_router

app = FastAPI(
    title="Virtual Director API",
    description="Multi-agent AI pipeline for procedural 3D video generation via Godot.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(generate_router, prefix="/api")
app.include_router(projects_router, prefix="/api")
app.include_router(test_render_router, prefix="/api")
app.include_router(models_router, prefix="/api")
app.include_router(review_router, prefix="/api")

# 启动命令: uvicorn backend.main:app --reload
