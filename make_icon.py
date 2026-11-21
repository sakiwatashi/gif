"""Generate a crisp multi-size Windows .ico icon for YT -> GIF Studio using stdlib only."""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path


def _make_png(size: int) -> bytes:
    """Render a rounded gradient square with a white play triangle as RGBA PNG."""
    pixels = bytearray(size * size * 4)
    radius = size * 0.22
    cx, cy = size / 2.0, size / 2.0

    # Triangle vertices (slightly shifted right for optical centering)
    ax, ay = size * 0.39, size * 0.30
    bx, by = size * 0.39, size * 0.70
    px_v, py_v = size * 0.71, size * 0.50

    def sign(x1, y1, x2, y2, x3, y3):
        return (x1 - x3) * (y2 - y3) - (x2 - x3) * (y1 - y3)

    def in_triangle(x, y):
        d1 = sign(x, y, ax, ay, bx, by)
        d2 = sign(x, y, bx, by, px_v, py_v)
        d3 = sign(x, y, px_v, py_v, ax, ay)
        has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
        has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
        return not (has_neg and has_pos)

    margin = size * 0.04
    half = size / 2.0 - margin

    for y in range(size):
        for x in range(size):
            # Signed distance to rounded box
            dx = abs((x + 0.5) - cx) - (half - radius)
            dy = abs((y + 0.5) - cy) - (half - radius)
            outside = math.hypot(max(dx, 0.0), max(dy, 0.0)) + min(max(dx, dy), 0.0) - radius
            alpha = max(0.0, min(1.0, 0.5 - outside))
            if alpha <= 0.0:
                continue

            # Coral-red to warm-orange diagonal gradient
            t = ((x / size) * 0.65 + (y / size) * 0.35)
            r = int(255)
            g = int(59 + (107 - 59) * t)
            b = int(92 + (74 - 92) * t)

            # Subtle glossy highlight near top
            if y < size * 0.45:
                boost = (1.0 - y / (size * 0.45)) * 18
                r = min(255, int(r + boost))
                g = min(255, int(g + boost))
                b = min(255, int(b + boost))

            # Anti-aliased play triangle (2x2 supersampling)
            hits = 0
            for sx in (0.25, 0.75):
                for sy in (0.25, 0.75):
                    if in_triangle(x + sx, y + sy):
                        hits += 1
            if hits > 0:
                blend = hits / 4.0
                r = int(r * (1 - blend) + 255 * blend)
                g = int(g * (1 - blend) + 255 * blend)
                b = int(b * (1 - blend) + 255 * blend)

            idx = (y * size + x) * 4
            pixels[idx] = r
            pixels[idx + 1] = g
            pixels[idx + 2] = b
            pixels[idx + 3] = int(alpha * 255)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    raw_rows = bytearray()
    stride = size * 4
    for y in range(size):
        raw_rows.append(0)  # filter type 0
        raw_rows.extend(pixels[y * stride : (y + 1) * stride])

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(raw_rows), 9))
        + chunk(b"IEND", b"")
    )


def build_ico(out_path: Path) -> None:
    sizes = [16, 32, 48, 64, 128, 256]
    images = [(s, _make_png(s)) for s in sizes]

    header = struct.pack("<HHH", 0, 1, len(images))
    entries = bytearray()
    offset = 6 + 16 * len(images)
    blobs = bytearray()

    for s, png in images:
        w = 0 if s >= 256 else s
        h = 0 if s >= 256 else s
        entries.extend(struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(png), offset))
        blobs.extend(png)
        offset += len(png)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(header + bytes(entries) + bytes(blobs))


if __name__ == "__main__":
    target = Path(__file__).resolve().parent / "assets" / "app.ico"
    build_ico(target)
    print(f"Generated icon: {target} ({target.stat().st_size} bytes)")
