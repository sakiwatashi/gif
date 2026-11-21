"""Core engine for fetching YouTube & Bilibili video metadata and generating high-quality GIFs."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import parse_qs, urlparse

import yt_dlp
from yt_dlp.postprocessor.ffmpeg import FFmpegPostProcessor
from yt_dlp.utils import download_range_func


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"))


def get_bundle_dir() -> Path:
    """Return directory containing read-only bundled assets (static/, bin/)."""
    if is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


def get_app_dir() -> Path:
    """Return directory next to the .exe (when frozen) or source folder."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _resolve_writable_output_dir() -> Path:
    preferred = get_app_dir() / "outputs"
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        probe = preferred / ".write_test"
        probe.write_bytes(b"ok")
        probe.unlink(missing_ok=True)
        return preferred
    except OSError:
        fallback = Path.home() / "Videos" / "YT-to-GIF"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


BASE_DIR = get_bundle_dir()
APP_DIR = get_app_dir()
OUTPUT_DIR = _resolve_writable_output_dir()
TEMP_DIR = Path(tempfile.gettempdir()) / "yt_to_gif_temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)


QUALITY_PRESETS = {
    "high": {
        "label": "高畫質",
        "max_colors": 256,
        "stats_mode": "diff",
        "dither": "sierra2_4a",
    },
    "medium": {
        "label": "均衡",
        "max_colors": 128,
        "stats_mode": "diff",
        "dither": "bayer:bayer_scale=3",
    },
    "compact": {
        "label": "輕量小檔",
        "max_colors": 64,
        "stats_mode": "diff",
        "dither": "bayer:bayer_scale=5",
    },
}


@dataclass
class GifResult:
    filename: str
    filepath: str
    file_size: int
    width: int
    height: int
    duration: float
    fps: int
    title: str
    video_id: str
    platform: str
    start_time: float
    end_time: float
    created_at: float

    def to_dict(self) -> dict:
        return asdict(self)


_CACHED_FFMPEG: Optional[str] = None


def get_ffmpeg_executable() -> str:
    """Return path to ffmpeg.exe and ensure its parent folder is on PATH for yt-dlp."""
    global _CACHED_FFMPEG
    if _CACHED_FFMPEG and Path(_CACHED_FFMPEG).exists():
        return _CACHED_FFMPEG

    exe_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    candidates: list[Path] = [
        get_bundle_dir() / "bin" / exe_name,
        get_app_dir() / "bin" / exe_name,
    ]
    for cand in candidates:
        if cand.exists():
            _ensure_on_path(cand.parent)
            _CACHED_FFMPEG = str(cand)
            return _CACHED_FFMPEG

    found = shutil.which("ffmpeg")
    if found:
        _CACHED_FFMPEG = found
        return _CACHED_FFMPEG

    try:
        import imageio_ffmpeg  # type: ignore

        src = Path(imageio_ffmpeg.get_ffmpeg_exe())
        if src.exists():
            shim_dir = TEMP_DIR / "bin"
            shim_dir.mkdir(parents=True, exist_ok=True)
            dst = shim_dir / exe_name
            if not dst.exists() or dst.stat().st_size != src.stat().st_size:
                shutil.copy2(src, dst)
            _ensure_on_path(shim_dir)
            _CACHED_FFMPEG = str(dst)
            return _CACHED_FFMPEG
    except Exception:
        pass

    raise RuntimeError("找不到 ffmpeg，請確認程式完整或系統已安裝 ffmpeg。")


def _ensure_on_path(folder: Path) -> None:
    folder_str = str(folder)
    current = os.environ.get("PATH", "")
    parts = current.split(os.pathsep) if current else []
    if folder_str not in parts:
        os.environ["PATH"] = folder_str + os.pathsep + current
    for k, v in list(FFmpegPostProcessor._version_cache.items()):
        if not v:
            FFmpegPostProcessor._version_cache.pop(k, None)


# Proactively register bundled ffmpeg on PATH at import time before any yt-dlp call
try:
    get_ffmpeg_executable()
except Exception:
    pass


def _extract_embedded_url(text: str) -> str:
    """If user pasted share text like '【標題】 https://b23.tv/xxx', extract the URL."""
    raw = (text or "").strip()
    m = re.search(r"https?://[^\s<>\"'\]）】]+", raw, re.IGNORECASE)
    if m:
        return m.group(0).rstrip(".,;!?，。；！？")
    return raw


def extract_video_id(url: str) -> Optional[str]:
    """Extract the 11-character YouTube video ID from common YouTube URL formats."""
    if not url:
        return None
    raw = _extract_embedded_url(url)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", raw):
        return raw

    if not re.match(r"^https?://", raw, re.IGNORECASE):
        raw = "https://" + raw

    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host.startswith("m."):
        host = host[2:]

    if host == "youtu.be":
        vid = parsed.path.lstrip("/").split("/")[0]
        return vid if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid) else None

    if host in {"youtube.com", "youtube-nocookie.com", "music.youtube.com"}:
        if parsed.path == "/watch":
            vid = parse_qs(parsed.query).get("v", [None])[0]
            return vid if vid and re.fullmatch(r"[A-Za-z0-9_-]{11}", vid) else None
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2 and parts[0] in {"shorts", "embed", "live", "v"}:
            vid = parts[1]
            return vid if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid) else None

    return None


def parse_bilibili_url(url: str) -> Optional[tuple[str, str, int]]:
    """Parse Bilibili URL or BV/av ID, returning (canonical_url, id_hint, page)."""
    raw = _extract_embedded_url(url)
    if not raw:
        return None

    # Bare BV ID (e.g. BV1hryaz6E1u)
    bv_bare = re.fullmatch(r"(BV[0-9A-Za-z]{10})", raw)
    if bv_bare:
        bvid = bv_bare.group(1)
        return f"https://www.bilibili.com/video/{bvid}/", bvid, 1

    # Bare av ID (e.g. av170001)
    av_bare = re.fullmatch(r"(av\d+)", raw, re.IGNORECASE)
    if av_bare:
        avid = av_bare.group(1).lower()
        return f"https://www.bilibili.com/video/{avid}/", avid, 1

    normalized = raw if re.match(r"^https?://", raw, re.IGNORECASE) else "https://" + raw
    parsed = urlparse(normalized)
    host = (parsed.hostname or "").lower()

    if host in {"b23.tv", "www.b23.tv"}:
        code = parsed.path.strip("/").split("/")[0]
        if code:
            return f"https://b23.tv/{code}", code, 1
        return None

    if host == "bilibili.com" or host.endswith(".bilibili.com"):
        qs = parse_qs(parsed.query)
        try:
            page = max(1, int(qs.get("p", ["1"])[0]))
        except (ValueError, TypeError):
            page = 1

        # /video/BV... or /video/av...
        m_bv = re.search(r"/(BV[0-9A-Za-z]{10})", parsed.path)
        if m_bv:
            bvid = m_bv.group(1)
            suffix = f"?p={page}" if page > 1 else ""
            return f"https://www.bilibili.com/video/{bvid}/{suffix}", bvid, page

        m_av = re.search(r"/(av\d+)", parsed.path, re.IGNORECASE)
        if m_av:
            avid = m_av.group(1).lower()
            suffix = f"?p={page}" if page > 1 else ""
            return f"https://www.bilibili.com/video/{avid}/{suffix}", avid, page

        # /bangumi/play/ep... or ss...
        m_ep = re.search(r"/bangumi/play/((?:ep|ss)\d+)", parsed.path, re.IGNORECASE)
        if m_ep:
            epid = m_ep.group(1).lower()
            return f"https://www.bilibili.com/bangumi/play/{epid}", epid, 1

        # /festival/... ?bvid=BV...
        bvid_q = qs.get("bvid", [None])[0]
        if bvid_q and re.fullmatch(r"BV[0-9A-Za-z]{10}", bvid_q):
            suffix = f"?p={page}" if page > 1 else ""
            return f"https://www.bilibili.com/video/{bvid_q}/{suffix}", bvid_q, page

    return None


def normalize_video_url(url: str) -> tuple[str, str, str, int]:
    """Validate and normalize a YouTube or Bilibili URL.

    Returns (canonical_url, video_id, platform, page).
    """
    bili = parse_bilibili_url(url)
    if bili:
        canonical, vid, page = bili
        return canonical, vid, "bilibili", page

    yt_id = extract_video_id(url)
    if yt_id:
        return f"https://www.youtube.com/watch?v={yt_id}", yt_id, "youtube", 1

    raise ValueError(
        "無法辨識有效的影片網址，請貼上 YouTube（youtube.com / youtu.be）或 Bilibili（bilibili.com / b23.tv / BV號）連結。"
    )


def normalize_youtube_url(url: str) -> tuple[str, str]:
    """Backward-compatible helper returning (canonical_url, video_id)."""
    canonical, vid, _, _ = normalize_video_url(url)
    return canonical, vid


def _build_bilibili_embed_url(video_id: str, page: int = 1) -> Optional[str]:
    if not video_id:
        return None
    # yt-dlp returns e.g. 'BV1hryaz6E1u' or 'BV1hryaz6E1u_p2'
    base_id = video_id.split("_p")[0]
    if re.fullmatch(r"BV[0-9A-Za-z]{10}", base_id):
        return f"https://player.bilibili.com/player.html?bvid={base_id}&page={page}&high_quality=1&autoplay=0"
    m_av = re.fullmatch(r"av(\d+)", base_id, re.IGNORECASE)
    if m_av:
        return f"https://player.bilibili.com/player.html?aid={m_av.group(1)}&page={page}&high_quality=1&autoplay=0"
    return None


def parse_timestamp(value: str | float | int) -> float:
    """Parse timestamps like '15', '0:15', '1:23.5', '01:02:03' into seconds."""
    if isinstance(value, (int, float)):
        if value < 0:
            raise ValueError("時間不能小於 0。")
        return float(value)

    text = str(value).strip()
    if not text:
        raise ValueError("時間欄位不能為空。")

    text = text.replace("：", ":").replace("．", ".").replace("。", ".")

    hms_match = re.fullmatch(
        r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?", text, re.IGNORECASE
    )
    if hms_match and any(hms_match.groups()):
        h = float(hms_match.group(1) or 0)
        m = float(hms_match.group(2) or 0)
        s = float(hms_match.group(3) or 0)
        return h * 3600 + m * 60 + s

    parts = text.split(":")
    if len(parts) == 1:
        sec = float(parts[0])
    elif len(parts) == 2:
        sec = int(parts[0]) * 60 + float(parts[1])
    elif len(parts) == 3:
        sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    else:
        raise ValueError(f"無效的時間格式：{value}")

    if sec < 0:
        raise ValueError("時間不能小於 0。")
    return round(sec, 3)


def format_timestamp(seconds: float) -> str:
    """Format seconds into MM:SS or HH:MM:SS (with decimals if non-integer)."""
    seconds = max(0.0, float(seconds))
    total_int = int(seconds)
    frac = round(seconds - total_int, 2)
    h = total_int // 3600
    m = (total_int % 3600) // 60
    s = total_int % 60
    frac_str = f"{frac:.2f}".lstrip("0").rstrip("0") if frac > 0 else ""
    if frac_str == ".":
        frac_str = ""
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}{frac_str}"
    return f"{m:02d}:{s:02d}{frac_str}"


def _sanitize_filename_stem(text: str, max_len: int = 40) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", text or "video")
    cleaned = re.sub(r"\s+", "_", cleaned).strip("._ ")
    if not cleaned:
        cleaned = "video"
    return cleaned[:max_len]


def _run_subprocess(cmd: list[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
    )


def fetch_video_info(url: str) -> dict:
    """Fetch video metadata for YouTube or Bilibili via yt-dlp Python API."""
    canonical_url, video_id, platform, page = normalize_video_url(url)
    ffmpeg = get_ffmpeg_executable()
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "ffmpeg_location": ffmpeg,
    }
    token = FFmpegPostProcessor._ffmpeg_location.set(ffmpeg)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            data = ydl.extract_info(canonical_url, download=False)
    except Exception as exc:
        raise RuntimeError(f"無法讀取影片資訊：{exc}") from exc
    finally:
        FFmpegPostProcessor._ffmpeg_location.reset(token)

    if not isinstance(data, dict):
        raise RuntimeError("無法解析影片資訊。")

    # If a multi-part Bilibili URL returns a playlist wrapper, pick the requested page entry
    if data.get("_type") == "playlist" and data.get("entries"):
        entries = [e for e in data["entries"] if e]
        if entries:
            idx = min(max(0, page - 1), len(entries) - 1)
            data = entries[idx]

    resolved_id = str(data.get("id") or video_id)
    embed_url = None
    if platform == "bilibili":
        embed_url = _build_bilibili_embed_url(resolved_id, page) or _build_bilibili_embed_url(
            video_id, page
        )
        default_thumb = ""
    else:
        default_thumb = f"https://i.ytimg.com/vi/{resolved_id}/hqdefault.jpg"

    return {
        "platform": platform,
        "video_id": resolved_id,
        "page": page,
        "url": data.get("webpage_url") or canonical_url,
        "embed_url": embed_url,
        "title": data.get("title") or f"{platform} ({resolved_id})",
        "duration": float(data.get("duration") or 0),
        "uploader": data.get("uploader") or data.get("channel") or "",
        "thumbnail": data.get("thumbnail") or default_thumb,
        "is_live": bool(data.get("is_live")),
    }


def probe_gif(filepath: Path) -> tuple[int, int, float]:
    """Read (width, height, duration_seconds) directly from a GIF file without ffprobe."""
    try:
        data = filepath.read_bytes()
    except OSError:
        return 0, 0, 0.0

    if len(data) < 13 or data[:6] not in (b"GIF87a", b"GIF89a"):
        return 0, 0, 0.0

    width, height = struct.unpack("<HH", data[6:10])
    packed = data[10]
    pos = 13

    if packed & 0x80:
        gct_size = 3 * (1 << ((packed & 0x07) + 1))
        pos += gct_size

    total_cs = 0
    n = len(data)

    def skip_sub_blocks(idx: int) -> int:
        while idx < n:
            block_size = data[idx]
            idx += 1
            if block_size == 0:
                break
            idx += block_size
        return idx

    while pos < n:
        sentinel = data[pos]
        pos += 1
        if sentinel == 0x3B:
            break
        elif sentinel == 0x21:
            if pos >= n:
                break
            label = data[pos]
            pos += 1
            if label == 0xF9 and pos + 5 <= n:
                block_size = data[pos]
                if block_size == 4:
                    delay_cs = struct.unpack("<H", data[pos + 2 : pos + 4])[0]
                    total_cs += delay_cs
            pos = skip_sub_blocks(pos)
        elif sentinel == 0x2C:
            if pos + 9 > n:
                break
            img_packed = data[pos + 8]
            pos += 9
            if img_packed & 0x80:
                lct_size = 3 * (1 << ((img_packed & 0x07) + 1))
                pos += lct_size
            pos += 1
            pos = skip_sub_blocks(pos)
        else:
            break

    return width, height, round(total_cs / 100.0, 2)


def generate_gif(
    url: str,
    start_time: str | float | int,
    end_time: str | float | int,
    *,
    width: int = 480,
    fps: int = 12,
    speed: float = 1.0,
    quality: str = "high",
    mode: str = "normal",
    output_dir: Path = OUTPUT_DIR,
    video_title: Optional[str] = None,
    progress_cb: Optional[Callable[[int, str, str], None]] = None,
) -> GifResult:
    """Download the requested YouTube or Bilibili clip and convert it to a high-quality GIF."""

    def report(pct: int, stage: str, msg: str) -> None:
        if progress_cb:
            progress_cb(pct, stage, msg)

    canonical_url, video_id, platform, _ = normalize_video_url(url)
    start_sec = parse_timestamp(start_time)
    end_sec = parse_timestamp(end_time)

    if end_sec <= start_sec:
        raise ValueError("結束時間必須大於開始時間。")

    clip_len = end_sec - start_sec
    if clip_len < 0.2:
        raise ValueError("片段長度至少需要 0.2 秒。")
    if clip_len > 60:
        raise ValueError("單次 GIF 片段長度上限為 60 秒，建議控制在 2~15 秒以獲得最佳檔案大小。")

    width = max(160, min(1280, int(width)))
    fps = max(5, min(30, int(fps)))
    speed = max(0.25, min(4.0, float(speed)))
    preset = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["high"])
    if mode not in {"normal", "reverse", "boomerang"}:
        mode = "normal"

    ffmpeg = get_ffmpeg_executable()

    report(5, "info", "讀取影片資訊中...")
    if not video_title:
        try:
            meta = fetch_video_info(canonical_url)
            video_title = meta["title"]
            video_id = meta.get("video_id") or video_id
            vid_duration = meta.get("duration") or 0
            if vid_duration > 0 and start_sec >= vid_duration:
                raise ValueError(
                    f"開始時間 ({format_timestamp(start_sec)}) 超過影片總長度 ({format_timestamp(vid_duration)})。"
                )
            if vid_duration > 0 and end_sec > vid_duration:
                end_sec = vid_duration
                clip_len = end_sec - start_sec
        except ValueError:
            raise
        except Exception:
            video_title = f"{platform}_{video_id}"

    output_dir.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    job_tmp = Path(tempfile.mkdtemp(prefix="ytgif_", dir=str(TEMP_DIR)))

    try:
        platform_label = "Bilibili" if platform == "bilibili" else "YouTube"
        report(
            15,
            "downloading",
            f"正在從 {platform_label} 下載片段 ({format_timestamp(start_sec)} ~ {format_timestamp(end_sec)})...",
        )
        clip_template = str(job_tmp / "clip.%(ext)s")

        target_height = max(360, min(1080, int(width * 1.25)))
        format_selector = (
            f"bestvideo[height<={target_height}][ext=mp4]/"
            f"bestvideo[height<={target_height}]/"
            f"best[height<={target_height}][ext=mp4]/"
            f"best[height<={target_height}]/bestvideo/best"
        )

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "ffmpeg_location": ffmpeg,
            "format": format_selector,
            "download_ranges": download_range_func(None, [(start_sec, end_sec)]),
            "force_keyframes_at_cuts": True,
            "outtmpl": clip_template,
        }

        token = FFmpegPostProcessor._ffmpeg_location.set(ffmpeg)
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(canonical_url, download=True)
        except Exception as exc:
            raise RuntimeError(f"下載影片片段失敗：{exc}") from exc
        finally:
            FFmpegPostProcessor._ffmpeg_location.reset(token)

        downloaded_files = [
            p for p in job_tmp.iterdir() if p.is_file() and p.name.startswith("clip.")
        ]
        if not downloaded_files:
            raise RuntimeError("下載完成但找不到暫存影片檔案。")
        clip_path = downloaded_files[0]

        report(60, "encoding", "正在分析色域並產生最佳化 GIF 調色盤...")

        base_filters: list[str] = []
        if abs(speed - 1.0) > 1e-3:
            base_filters.append(f"setpts=PTS/{speed:.4f}")
        base_filters.append(f"fps={fps}")
        base_filters.append(f"scale={width}:-1:flags=lanczos")

        if mode == "reverse":
            base_filters.append("reverse")
            pre_chain = ",".join(base_filters)
            filter_complex = (
                f"[0:v]{pre_chain},split[s0][s1];"
                f"[s0]palettegen=max_colors={preset['max_colors']}:stats_mode={preset['stats_mode']}[p];"
                f"[s1][p]paletteuse=dither={preset['dither']}"
            )
        elif mode == "boomerang":
            pre_chain = ",".join(base_filters)
            filter_complex = (
                f"[0:v]{pre_chain},split[fwd][rev_in];"
                f"[rev_in]reverse[rev];"
                f"[fwd][rev]concat=n=2:v=1:a=0,split[s0][s1];"
                f"[s0]palettegen=max_colors={preset['max_colors']}:stats_mode={preset['stats_mode']}[p];"
                f"[s1][p]paletteuse=dither={preset['dither']}"
            )
        else:
            pre_chain = ",".join(base_filters)
            filter_complex = (
                f"[0:v]{pre_chain},split[s0][s1];"
                f"[s0]palettegen=max_colors={preset['max_colors']}:stats_mode={preset['stats_mode']}[p];"
                f"[s1][p]paletteuse=dither={preset['dither']}"
            )

        stem = _sanitize_filename_stem(video_title)
        t_start_tag = format_timestamp(start_sec).replace(":", "-")
        t_end_tag = format_timestamp(end_sec).replace(":", "-")
        short_id = uuid.uuid4().hex[:6]
        filename = f"{stem}_{t_start_tag}_to_{t_end_tag}_{short_id}.gif"
        output_path = output_dir / filename

        report(75, "encoding", "正在編碼 GIF 動圖...")
        ff_cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(clip_path),
            "-filter_complex",
            filter_complex,
            "-loop",
            "0",
            str(output_path),
        ]
        ff_res = _run_subprocess(ff_cmd)
        if ff_res.returncode != 0 or not output_path.exists():
            err = (ff_res.stderr or ff_res.stdout or "").strip()
            raise RuntimeError(f"GIF 轉檔失敗：{err[-500:]}")

        report(95, "finalizing", "整理輸出資訊...")
        out_w, out_h, out_dur = probe_gif(output_path)
        if out_dur <= 0:
            out_dur = round((clip_len / speed) * (2 if mode == "boomerang" else 1), 2)

        file_size = output_path.stat().st_size
        result = GifResult(
            filename=filename,
            filepath=str(output_path),
            file_size=file_size,
            width=out_w or width,
            height=out_h,
            duration=round(out_dur, 2),
            fps=fps,
            title=video_title,
            video_id=video_id,
            platform=platform,
            start_time=start_sec,
            end_time=end_sec,
            created_at=time.time(),
        )

        meta_path = output_path.with_suffix(".json")
        meta_path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

        report(100, "done", "GIF 製作完成！")
        return result
    finally:
        shutil.rmtree(job_tmp, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="YouTube / Bilibili 片段轉 GIF 命令列工具")
    parser.add_argument("url", help="YouTube 或 Bilibili 影片網址 / ID")
    parser.add_argument("start", help="開始時間 (例如 0:15 或 95)")
    parser.add_argument("end", help="結束時間 (例如 0:22 或 102)")
    parser.add_argument("--width", type=int, default=480, help="GIF 寬度 (預設 480)")
    parser.add_argument("--fps", type=int, default=12, help="幀率 FPS (預設 12)")
    parser.add_argument("--speed", type=float, default=1.0, help="播放速度 (預設 1.0)")
    parser.add_argument(
        "--quality",
        choices=["high", "medium", "compact"],
        default="high",
        help="畫質模式 (預設 high)",
    )
    parser.add_argument(
        "--mode",
        choices=["normal", "reverse", "boomerang"],
        default="normal",
        help="播放模式 (normal / reverse / boomerang)",
    )
    args = parser.parse_args()

    def on_progress(pct: int, stage: str, msg: str) -> None:
        print(f"[{pct:3d}%] {msg}")

    result = generate_gif(
        args.url,
        args.start,
        args.end,
        width=args.width,
        fps=args.fps,
        speed=args.speed,
        quality=args.quality,
        mode=args.mode,
        progress_cb=on_progress,
    )
    print(f"\n完成！檔案位置：{result.filepath}")
    print(
        f"來源：{result.platform} | 尺寸：{result.width}x{result.height} | 長度：{result.duration}s | 大小：{result.file_size / 1024 / 1024:.2f} MB"
    )


if __name__ == "__main__":
    main()
