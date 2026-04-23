import os
import subprocess
from backend.config import GODOT_EXECUTABLE, GODOT_DIR, GODOT_SCENE, FRONTEND_PUBLIC_DIR


def do_godot(avi_path: str) -> None:
    """Launch Godot in --write-movie mode to render the scene to an AVI file."""
    os.makedirs(FRONTEND_PUBLIC_DIR, exist_ok=True)
    command = [GODOT_EXECUTABLE, "--write-movie", avi_path, GODOT_SCENE]
    result = subprocess.run(command, cwd=GODOT_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(f"[Godot] returncode: {result.returncode}")
    if result.stdout:
        print(f"[Godot stdout]\n{result.stdout[-1000:]}")
    if result.stderr:
        print(f"[Godot stderr]\n{result.stderr[-1000:]}")
    if result.returncode != 0:
        # "no debug info" messages are just missing symbols in the crash trace,
        # not a Godot script error. Show the full combined output.
        combined = (result.stdout + "\n" + result.stderr)[-800:]
        raise RuntimeError(f"Godot 渲染失败 (code={result.returncode}):\n{combined}")



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
