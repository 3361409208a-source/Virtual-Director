from pydantic import BaseModel
from typing import Literal


class PromptRequest(BaseModel):
    prompt: str
    model: Literal["deepseek-chat", "deepseek-reasoner", "deepseek-v4-flash", "deepseek-v4-pro", "GLM-4.7-Flash", "astron-code-latest"] = "astron-code-latest"
    renderer: Literal["godot", "blender"] = "godot"





class SSEEvent(BaseModel):
    step: str
    msg: str
