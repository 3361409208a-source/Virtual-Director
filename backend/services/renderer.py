import os
import subprocess
from backend.config import GODOT_EXECUTABLE, GODOT_DIR, GODOT_SCENE, FRONTEND_PUBLIC_DIR


def do_godot(avi_path: str) -> None:
    """Launch Godot in --write-movie mode to render the scene to an AVI file."""
    os.makedirs(FRONTEND_PUBLIC_DIR, exist_ok=True)
    command = [GODOT_EXECUTABLE, "--write-movie", avi_path, GODOT_SCENE]
    result = subprocess.run(command, cwd=GODOT_DIR, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Godot 渲染失败: {result.stderr[-400:]}")


def do_ffmpeg(avi_path: str, mp4_path: str) -> None:
    """Convert AVI to H.264 MP4 for browser playback."""
    cmd = [
        "ffmpeg", "-y", "-i", avi_path,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", mp4_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"视频转换失败: {result.stderr[-400:]}")
