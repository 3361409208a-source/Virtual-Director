"""
review.py — 半自动审核桥接层

generate 流在 merge 完成后会创建一个 ReviewSession，然后挂起等待。
前端通过以下端点控制：
  POST /api/review/{sid}/confirm    → 用户确认，继续渲染
  POST /api/review/{sid}/reject     → 用户放弃，终止流
  POST /api/review/{sid}/update     → 用户修改了某块数据，更新 session 中的 sequence
"""
import asyncio
import time
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# ── 全局 session 注册表 ──────────────────────────────────────────────────────
_sessions: dict[str, "ReviewSession"] = {}


class ReviewSession:
    def __init__(self, sid: str, sequence: dict):
        self.sid = sid
        self.sequence = sequence          # 当前 sequence，用户可修改后写回
        self.created_at = time.time()
        self._event = asyncio.Event()     # 等待用户决策
        self.decision: Optional[str] = None   # "confirm" | "reject"

    async def wait(self, timeout: float = 600.0) -> str:
        """挂起直到用户做出决策（或超时自动 reject）。"""
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            self.decision = "reject"
        return self.decision or "reject"

    def resolve(self, decision: str, sequence: Optional[dict] = None):
        self.decision = decision
        if sequence is not None:
            self.sequence = sequence
        self._event.set()


def create_session(sid: str, sequence: dict) -> "ReviewSession":
    sess = ReviewSession(sid, sequence)
    _sessions[sid] = sess
    return sess


def get_session(sid: str) -> "ReviewSession":
    sess = _sessions.get(sid)
    if not sess:
        raise HTTPException(status_code=404, detail=f"Session {sid} not found")
    return sess


def remove_session(sid: str):
    _sessions.pop(sid, None)


# ── Request / Response Models ────────────────────────────────────────────────

class UpdateBody(BaseModel):
    sequence: dict


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/review/{sid}/confirm")
async def confirm_review(sid: str, body: UpdateBody):
    """用户确认（可同时提交最新的 sequence）。"""
    sess = get_session(sid)
    sess.resolve("confirm", body.sequence)
    return {"ok": True}


@router.post("/review/{sid}/reject")
async def reject_review(sid: str):
    """用户取消，终止本次生成。"""
    sess = get_session(sid)
    sess.resolve("reject")
    return {"ok": True}


@router.get("/review/{sid}/sequence")
async def get_sequence(sid: str):
    """获取当前 session 的 sequence（前端刷新用）。"""
    sess = get_session(sid)
    return {"sequence": sess.sequence}
