"""
Nexora Labs - YouTube Shorts Video Renderer (No Narration)
Top 5 ranking — visual per item (Pexels) + list overlay progresif + title highlight
"""

import os
import json
import subprocess
from pathlib import Path

import requests
from PIL import ImageFont

OUTPUT_DIR     = Path("yt_output")
W, H           = 1080, 1920
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
FONT           = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
DEFAULT_KEYWORD = "funny animals playing"

TITLE_SIZE = 58
HIGHLIGHT_COLOR = "#f59e0b"


# ─── PEXELS ──────────────────────────────────────────────────
def search_pexels_video(keyword: str) -> str | None:
    headers = {"Authorization": PEXELS_API_KEY}
    params  = {"query": keyword, "orientation": "portrait", "per_page": 5, "size": "medium"}
    try:
        resp = requests.get("https://api.pexels.com/videos/search",
                             headers=headers, params=params, timeout=20)
        resp.raise_for_status()
        videos = resp.json().get("videos", [])
        if not videos:
            return None
        files = videos[0].get("video_files", [])
        if not files:
            return None
        good_files = [f for f in files if f.get("width", 0) >= 720]
        candidates = good_files if good_files else files
        chosen = min(candidates, key=lambda f: abs(f.get("width", 0) - 1080))
        return chosen["link"]
    except Exception as e:
        print(f"   ⚠️  Pexels error untuk '{keyword}': {e}")
        return None


def download_file(url: str, out_path: Path):
    r = requests.get(url, stream=True, timeout=60)
    r.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)


def get_clip_for_segment(keyword: str, duration: float, out_path: Path) -> bool:
    url = search_pexels_video(keyword)
    if not url:
        return False

    raw_path = out_path.with_suffix(".raw.mp4")
    try:
        download_file(url, raw_path)
    except Exception as e:
        print(f"   ⚠️  Download gagal: {e}")
        return False

    cmd = [
        "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(raw_path),
        "-t", str(duration),
        "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30",
        "-an",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        str(out_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    raw_path.unlink(missing_ok=True)
    if result.returncode != 0:
        print(f"   ⚠️  Normalize gagal: {result.stderr[-500:]}")
        return False
    return True


def build_background_sequence(segments: list) -> Path:
    clips_dir = OUTPUT_DIR / "clips"
    clips_dir.mkdir(exist_ok=True)

    clip_paths = []
    for i, seg in enumerate(segments):
        keyword = seg.get("visual_keyword", DEFAULT_KEYWORD)
        duration = seg["duration"]
        clip_path = clips_dir / f"clip_{i}.mp4"

        print(f"   🔍 Segmen {i} ({seg['type']}): '{keyword}' ({duration:.1f}s)...")
        ok = get_clip_for_segment(keyword, duration, clip_path)
        if not ok:
            print(f"   ⚠️  Fallback ke default keyword...")
            ok = get_clip_for_segment(DEFAULT_KEYWORD, duration, clip_path)
        if not ok:
            raise RuntimeError(f"Gagal dapat clip buat segmen {i}")
        clip_paths.append(clip_path)

    concat_list_path = OUTPUT_DIR / "concat_list.txt"
    with open(concat_list_path, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p.resolve()}'\n")

    sequence_path = OUTPUT_DIR / "background_sequence.mp4"
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list_path), "-c", "copy", str(sequence_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("FFMPEG CONCAT ERROR:", result.stderr[-1000:])
        raise RuntimeError("Gagal gabung clip jadi sequence")
    return sequence_path


# ─── TEXT OVERLAY ────────────────────────────────────────────
def escape_text(text: str) -> str:
    return (text.replace("\\", "\\\\\\\\")
                .replace(":", "\\:")
                .replace("'", "\u2019")
                .replace("%", "\\%"))


def measure_width(text: str, size: int) -> int:
    font = ImageFont.truetype(FONT, size)
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0]


def build_title_filters(before: str, highlight: str, after: str) -> list:
    """Title 1 baris dengan 1 kata di-highlight warna beda, center. Auto-shrink kalau kepanjangan."""
    parts = []
    if before.strip():
        parts.append((before.strip() + " ", "white"))
    parts.append((highlight.strip(), HIGHLIGHT_COLOR))
    if after.strip():
        parts.append((" " + after.strip(), "white"))

    max_width = W - 120  # margin kiri-kanan 60px
    size = TITLE_SIZE
    widths = [measure_width(text.upper(), size) for text, _ in parts]
    total_width = sum(widths)

    # Auto-shrink font kalau melebihi lebar layar
    if total_width > max_width:
        scale = max_width / total_width
        size = max(28, int(size * scale))
        widths = [measure_width(text.upper(), size) for text, _ in parts]
        total_width = sum(widths)

    start_x = max(20, (W - total_width) // 2)
    box_pad = 18
    box_h   = size + box_pad * 2

    filters = [
        f"drawbox=x={start_x - box_pad}:y={100 - box_pad}:"
        f"w={total_width + box_pad*2}:h={box_h}:color=black@0.45:t=fill"
    ]
    cursor_x = start_x
    for (text, color), w in zip(parts, widths):
        esc = escape_text(text.upper())
        filters.append(
            f"drawtext=fontfile={FONT}:text='{esc}':fontcolor={color}:fontsize={size}:"
            f"x={cursor_x}:y=100"
        )
        cursor_x += w

    return filters


def build_overlay_filters(script_data: dict, segments: list) -> str:
    filters = build_title_filters(
        script_data["title_before"], script_data["title_highlight"], script_data["title_after"]
    )

    item_segments = [s for s in segments if s["type"] == "item"]
    item_segments_display = sorted(item_segments, key=lambda x: x["rank"])

    list_y_start = 280
    row_height   = 130

    for idx, seg in enumerate(item_segments_display):
        y = list_y_start + idx * row_height
        rank = seg["rank"]

        filters.append(
            f"drawtext=fontfile={FONT}:text='{rank}.':fontcolor={HIGHLIGHT_COLOR}:fontsize=64:"
            f"x=60:y={y}"
        )

        caption_esc = escape_text(seg["caption"].upper())
        reveal_time = seg["start"]
        filters.append(
            f"drawtext=fontfile={FONT}:text='{caption_esc}':fontcolor=white:fontsize=46:"
            f"x=160:y={y+8}:enable='gte(t,{reveal_time:.2f})'"
        )

    return ",".join(filters)


# ─── FINAL RENDER (tanpa voiceover, audio diam) ───────────────
def render_final(bg_path: Path, overlay_filters: str, total_duration: float) -> Path:
    out_path = OUTPUT_DIR / "final_video.mp4"
    vf = f"format=yuv420p,{overlay_filters}"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(bg_path),
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        "-t", str(total_duration),
        str(out_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("FFMPEG ERROR:", result.stderr[-3000:])
        raise RuntimeError("Render final gagal")
    return out_path


def main():
    print("🚀 Video Renderer (No Narration) starting...")

    with open(OUTPUT_DIR / "script.json") as f:
        script_data = json.load(f)
    with open(OUTPUT_DIR / "segments.json") as f:
        segments = json.load(f)

    total_duration = segments[-1]["end"]

    print("🎥 Membangun background sequence dari Pexels...")
    bg_path = build_background_sequence(segments)

    print("💬 Menyusun overlay ranking list...")
    overlay_filters = build_overlay_filters(script_data, segments)

    print("🎬 Rendering final video...")
    final_path = render_final(bg_path, overlay_filters, total_duration)

    print(f"✅ Done! Final video: {final_path}")


if __name__ == "__main__":
    main()
