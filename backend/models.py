from pydantic import BaseModel
from typing import Literal


class PromptRequest(BaseModel):
    prompt: str
    model: Literal["deepseek-chat", "deepseek-reasoner"] = "deepseek-chat"


class SSEEvent(BaseModel):
    step: str
    msg: str
