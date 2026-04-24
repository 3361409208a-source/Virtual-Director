import os
from dotenv import load_dotenv

load_dotenv() # Load variables from .env


ROOT_DIR            = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR         = os.path.join(ROOT_DIR, "backend")
GODOT_DIR           = os.path.join(ROOT_DIR, "godot")
FRONTEND_PUBLIC_DIR = os.path.join(ROOT_DIR, "frontend", "public")

SCENE_CONTEXT_PATH    = os.path.join(BACKEND_DIR, "data", "scene_context.json")
SEQUENCE_PATH         = os.path.join(GODOT_DIR, "director_sequence.json")
GODOT_ASSETS_DIR      = os.path.join(GODOT_DIR, "assets")
ASSETS_DOWNLOADED_DIR = os.path.join(GODOT_ASSETS_DIR, "downloaded")
PROJECTS_DIR          = os.path.join(ROOT_DIR, "projects")

GODOT_EXECUTABLE    = r"D:\Program Files\Godot_v4.6.2-stable_win64.exe"
GODOT_SCENE         = "main.tscn"

# Renderer selection: 'godot' | 'blender'
RENDERER            = os.environ.get("RENDERER", "blender")
BLENDER_EXECUTABLE  = os.environ.get("BLENDER_EXECUTABLE", "")  # only needed if bpy not pip-installed

DEEPSEEK_API_KEY    = os.environ.get("DEEPSEEK_API_KEY", "")

DEEPSEEK_BASE_URL   = "https://api.deepseek.com"
DEEPSEEK_MODEL      = "deepseek-chat"

GLM_API_KEY       = os.environ.get("GLM_API_KEY", "")
GLM_BASE_URL      = "https://ai.gitee.com/v1"
GLM_MODEL         = "GLM-4.7-Flash"



# Optional: free API keys for model search/download
# Poly Pizza: register at https://poly.pizza  (free, no credit card)
# Sketchfab:  register at https://sketchfab.com/settings#api (free)
POLYPIZZA_API_KEY  = os.environ.get("POLYPIZZA_API_KEY",  "945e0cf46c8246a6bf4ecff940bc0c49")
SKETCHFAB_API_KEY  = os.environ.get("SKETCHFAB_API_KEY",  "")

SILICONFLOW_API_KEY  = os.environ.get("SILICONFLOW_API_KEY", "")
SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
SILICONFLOW_IMAGE_MODEL = "Kwai-Kolors/Kolors"

