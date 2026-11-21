"""FastAPI web server and standalone EXE entrypoint for YouTube to GIF Studio."""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import os
import socket
import sys
import threading
import time
import uuid
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from gif_engine import (
    OUTPUT_DIR,
    fetch_video_info,
    generate_gif,
    get_bundle_dir,
    is_frozen,
    parse_timestamp,
)

STATIC_DIR = get_bundle_dir() / "static"

app = FastAPI(title="YouTube / Bilibili → GIF 製作工具", version="1.2.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

EXECUTOR = ThreadPoolExecutor(max_workers=2)
JOBS_LOCK = threading.Lock()
JOBS: dict[str, dict] = {}


class VideoInfoRequest(BaseModel):
    url: str = Field(..., min_length=3)


class CreateGifRequest(BaseModel):
    url: str = Field(..., min_length=3)
    start: str | float | int
    end: str | float | int
    width: int = Field(default=480, ge=160, le=1280)
    fps: int = Field(default=12, ge=5, le=30)
    speed: float = Field(default=1.0, ge=0.25, le=4.0)
    quality: Literal["high", "medium", "compact"] = "high"
    mode: Literal["normal", "reverse", "boomerang"] = "normal"
    video_title: Optional[str] = None


def _safe_output_path(filename: str) -> Path:
    if not filename or Path(filename).name != filename or not filename.lower().endswith(".gif"):
        raise HTTPException(status_code=400, detail="無效的檔案名稱")
    path = (OUTPUT_DIR / filename).resolve()
    if path.parent != OUTPUT_DIR.resolve():
        raise HTTPException(status_code=400, detail="無效的檔案路徑")
    return path


def _serialize_item(meta: dict) -> dict:
    filename = meta["filename"]
    encoded = quote(filename)
    return {
        **meta,
        "gif_url": f"/api/files/{encoded}",
        "download_url": f"/api/files/{encoded}?download=1",
    }


def _run_job(job_id: str, req: CreateGifRequest) -> None:
    def on_progress(pct: int, stage: str, msg: str) -> None:
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if job:
                job["progress"] = pct
                job["stage"] = stage
                job["message"] = msg
                job["updated_at"] = time.time()

    try:
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "running"
            JOBS[job_id]["updated_at"] = time.time()

        result = generate_gif(
            req.url,
            req.start,
            req.end,
            width=req.width,
            fps=req.fps,
            speed=req.speed,
            quality=req.quality,
            mode=req.mode,
            video_title=req.video_title,
            progress_cb=on_progress,
        )
        with JOBS_LOCK:
            JOBS[job_id].update(
                {
                    "status": "done",
                    "progress": 100,
                    "stage": "done",
                    "message": "GIF 製作完成！",
                    "result": _serialize_item(result.to_dict()),
                    "updated_at": time.time(),
                }
            )
    except Exception as exc:
        with JOBS_LOCK:
            JOBS[job_id].update(
                {
                    "status": "error",
                    "stage": "error",
                    "message": str(exc),
                    "error": str(exc),
                    "updated_at": time.time(),
                }
            )


@app.get("/", response_class=HTMLResponse)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def api_health() -> dict:
    return {"status": "ok", "output_dir": str(OUTPUT_DIR)}


@app.post("/api/info")
async def api_video_info(req: VideoInfoRequest) -> dict:
    try:
        return await asyncio.to_thread(fetch_video_info, req.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/jobs")
async def api_create_job(req: CreateGifRequest) -> dict:
    try:
        start_sec = parse_timestamp(req.start)
        end_sec = parse_timestamp(req.end)
        if end_sec <= start_sec:
            raise ValueError("結束時間必須大於開始時間。")
        if end_sec - start_sec < 0.2:
            raise ValueError("片段長度至少需要 0.2 秒。")
        if end_sec - start_sec > 60:
            raise ValueError("單次 GIF 片段長度上限為 60 秒。")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job_id = uuid.uuid4().hex[:12]
    now = time.time()
    with JOBS_LOCK:
        JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "progress": 0,
            "stage": "queued",
            "message": "已加入排程，準備開始...",
            "error": None,
            "result": None,
            "created_at": now,
            "updated_at": now,
        }

    EXECUTOR.submit(_run_job, job_id, req)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
async def api_get_job(job_id: str) -> dict:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="找不到此製作任務")
        return dict(job)


@app.get("/api/files/{filename}")
async def api_get_file(filename: str, download: int = Query(default=0)) -> FileResponse:
    path = _safe_output_path(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="找不到檔案")

    headers = {}
    if download:
        encoded = quote(filename)
        headers["Content-Disposition"] = (
            f'attachment; filename="clip.gif"; filename*=UTF-8\'\'{encoded}'
        )
    return FileResponse(path, media_type="image/gif", headers=headers)


@app.get("/api/history")
async def api_history() -> list[dict]:
    items: list[dict] = []
    if not OUTPUT_DIR.exists():
        return items
    for gif_file in OUTPUT_DIR.glob("*.gif"):
        meta_file = gif_file.with_suffix(".json")
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                meta["filename"] = gif_file.name
                meta["file_size"] = gif_file.stat().st_size
                items.append(_serialize_item(meta))
                continue
            except Exception:
                pass
        stat = gif_file.stat()
        items.append(
            _serialize_item(
                {
                    "filename": gif_file.name,
                    "filepath": str(gif_file),
                    "file_size": stat.st_size,
                    "width": 0,
                    "height": 0,
                    "duration": 0,
                    "fps": 0,
                    "title": gif_file.stem,
                    "video_id": "",
                    "start_time": 0,
                    "end_time": 0,
                    "created_at": stat.st_mtime,
                }
            )
        )
    items.sort(key=lambda x: x.get("created_at", 0), reverse=True)
    return items[:30]


@app.delete("/api/files/{filename}")
async def api_delete_file(filename: str) -> dict:
    path = _safe_output_path(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="找不到檔案")
    path.unlink(missing_ok=True)
    path.with_suffix(".json").unlink(missing_ok=True)
    return {"deleted": filename}


def _find_available_port(preferred: int = 8765, host: str = "127.0.0.1") -> int:
    for port in range(preferred, preferred + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


def _open_browser_when_ready(host: str, port: int, url: str) -> None:
    deadline = time.time() + 15.0
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.3)
            if sock.connect_ex((host, port)) == 0:
                webbrowser.open(url)
                return
        time.sleep(0.2)


def _init_utf8_console() -> None:
    if os.name == "nt":
        try:
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def main() -> None:
    _init_utf8_console()
    parser = argparse.ArgumentParser(description="YT -> GIF Studio 伺服器")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="啟動後不要自動開啟瀏覽器",
    )
    args = parser.parse_args()

    port = _find_available_port(args.port, args.host)
    url = f"http://{args.host}:{port}"

    print("=" * 56)
    print("  YT / Bilibili -> GIF Studio 已啟動！")
    print(f"  開啟網址：{url}")
    print(f"  GIF 輸出位置：{OUTPUT_DIR}")
    print("  提示：使用期間請保持此視窗開啟，關閉視窗即可結束程式。")
    print("=" * 56, flush=True)

    should_open_browser = not args.no_browser and (is_frozen() or args.port == 8765)
    if should_open_browser:
        threading.Thread(
            target=_open_browser_when_ready,
            args=(args.host, port, url),
            daemon=True,
        ).start()

    uvicorn.run(
        app,
        host=args.host,
        port=port,
        log_level="warning",
        access_log=False,
    )


if __name__ == "__main__":
    main()
