from pydantic import BaseModel
from typing import Literal


class PromptRequest(BaseModel):
    prompt: str
    model: str = "astron-code-latest"
    worker_model: str = "auto"
    renderer: Literal["godot", "blender"] = "godot"





class SSEEvent(BaseModel):
    step: str
    msg: str
