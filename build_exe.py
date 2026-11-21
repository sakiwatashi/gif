"""Build standalone single-file Windows EXE for YT -> GIF Studio."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

from make_icon import build_ico

ROOT = Path(__file__).resolve().parent
STAGING = ROOT / "build_staging"
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"
ASSETS_DIR = ROOT / "assets"


def main() -> None:
    print("[1/4] 產生應用程式圖示...")
    ico_path = ASSETS_DIR / "app.ico"
    build_ico(ico_path)

    print("[2/4] 準備精簡版 ffmpeg.exe...")
    bin_dir = STAGING / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg_src = Path(imageio_ffmpeg.get_ffmpeg_exe())
    ffmpeg_dst = bin_dir / "ffmpeg.exe"
    shutil.copy2(ffmpeg_src, ffmpeg_dst)
    print(f"      已複製 {ffmpeg_src.name} -> {ffmpeg_dst} ({ffmpeg_dst.stat().st_size / 1024 / 1024:.1f} MB)")

    print("[3/4] 執行 PyInstaller 打包單一 EXE...")
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--console",
        "--name",
        "YT-Bili-GIF-Studio",
        "--icon",
        str(ico_path),
        "--add-data",
        f"{ROOT / 'static'};static",
        "--add-binary",
        f"{ffmpeg_dst};bin",
        # Uvicorn / FastAPI dynamic imports
        "--hidden-import",
        "uvicorn.logging",
        "--hidden-import",
        "uvicorn.loops",
        "--hidden-import",
        "uvicorn.loops.auto",
        "--hidden-import",
        "uvicorn.protocols",
        "--hidden-import",
        "uvicorn.protocols.http",
        "--hidden-import",
        "uvicorn.protocols.http.auto",
        "--hidden-import",
        "uvicorn.protocols.http.h11_impl",
        "--hidden-import",
        "uvicorn.protocols.websockets",
        "--hidden-import",
        "uvicorn.protocols.websockets.auto",
        "--hidden-import",
        "uvicorn.lifespan",
        "--hidden-import",
        "uvicorn.lifespan.on",
        # Avoid bundling a duplicate copy of ffmpeg via imageio_ffmpeg
        "--exclude-module",
        "imageio_ffmpeg",
        "--exclude-module",
        "tkinter",
        "--exclude-module",
        "unittest",
        "--exclude-module",
        "pydoc",
        "--exclude-module",
        "test",
        str(ROOT / "server.py"),
    ]

    res = subprocess.run(cmd, cwd=str(ROOT))
    if res.returncode != 0:
        raise SystemExit(f"PyInstaller 打包失敗 (exit code {res.returncode})")

    exe_path = DIST_DIR / "YT-Bili-GIF-Studio.exe"
    if not exe_path.exists():
        raise SystemExit("打包完成但找不到 dist/YT-Bili-GIF-Studio.exe")

    print("[4/4] 打包完成！")
    print(f"      EXE 位置：{exe_path}")
    print(f"      檔案大小：{exe_path.stat().st_size / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    main()
