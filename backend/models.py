from pydantic import BaseModel
from typing import Literal


class PromptRequest(BaseModel):
    prompt: str
    model: Literal["deepseek-v4-flash", "deepseek-v4-pro", "glm-4-flash"] = "deepseek-v4-flash"




class SSEEvent(BaseModel):
    step: str
    msg: str
