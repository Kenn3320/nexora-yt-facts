"""
Nexora Labs - YouTube Shorts Video Renderer
Format: Top 5 ranking list — visual per item (Pexels) + list overlay progresif
"""

import os
import json
import subprocess
from pathlib import Path

import requests

OUTPUT_DIR     = Path("yt_output")
W, H           = 1080, 1920
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
FONT           = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

DEFAULT_KEYWORD = "funny animals playing"  # buat intro/outro


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
    """Download + normalize 1 clip biar pas durasinya sama persis sama segmen narasi."""
    url = search_pexels_video(keyword)
    if not url:
        return False

    raw_path = out_path.with_suffix(".raw.mp4")
    try:
        download_file(url, raw_path)
    except Exception as e:
        print(f"   ⚠️  Download gagal: {e}")
        return False

    # stream_loop biar kalau clip lebih pendek dari durasi yang dibutuhkan, otomatis diulang
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
    """Download clip per segmen (durasi pas), gabung jadi 1 video utuh."""
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

        if ok:
            clip_paths.append(clip_path)
        else:
            raise RuntimeError(f"Gagal dapat clip buat segmen {i}")

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
    """Escape karakter spesial buat ffmpeg drawtext."""
    return (text.replace("\\", "\\\\\\\\")
                .replace(":", "\\:")
                .replace("'", "\u2019")
                .replace("%", "\\%"))


def build_overlay_filters(title: str, segments: list) -> str:
    """Bikin chain drawtext: title + nomor persisten + label yang reveal progresif."""
    filters = []

    # Title di atas (selalu tampil)
    title_esc = escape_text(title.upper())
    filters.append(
        f"drawtext=fontfile={FONT}:text='{title_esc}':fontcolor=white:fontsize=58:"
        f"x=(w-text_w)/2:y=90:box=1:boxcolor=black@0.45:boxborderw=20"
    )

    item_segments = [s for s in segments if s["type"] == "item"]
    # Urutkan tampilan dari rank 1 (atas) ke rank 5 (bawah)
    item_segments_display = sorted(item_segments, key=lambda x: x["rank"])

    list_y_start = 280
    row_height   = 130

    for idx, seg in enumerate(item_segments_display):
        y = list_y_start + idx * row_height
        rank = seg["rank"]

        # Nomor — selalu tampil dari awal
        filters.append(
            f"drawtext=fontfile={FONT}:text='{rank}.':fontcolor=#f59e0b:fontsize=64:"
            f"x=60:y={y}"
        )

        # Label — reveal begitu narasi item ini mulai, tetap tampil sampai akhir
        label_esc = escape_text(seg["label"].upper())
        reveal_time = seg["start"]
        filters.append(
            f"drawtext=fontfile={FONT}:text='{label_esc}':fontcolor=white:fontsize=48:"
            f"x=160:y={y+8}:enable='gte(t,{reveal_time:.2f})'"
        )

    return ",".join(filters)


# ─── FINAL RENDER ────────────────────────────────────────────
def render_final(bg_path: Path, audio_path: Path, overlay_filters: str) -> Path:
    out_path = OUTPUT_DIR / "final_video.mp4"

    vf = f"format=yuv420p,{overlay_filters}"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(bg_path),
        "-i", str(audio_path),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        str(out_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("FFMPEG ERROR:", result.stderr[-3000:])
        raise RuntimeError("Render final gagal")
    return out_path


def main():
    print("🚀 Video Renderer (Ranking format) starting...")

    with open(OUTPUT_DIR / "script.json") as f:
        script_data = json.load(f)
    with open(OUTPUT_DIR / "segments.json") as f:
        segments = json.load(f)

    audio_path = OUTPUT_DIR / "voiceover.mp3"

    print("🎥 Membangun background sequence dari Pexels...")
    bg_path = build_background_sequence(segments)

    print("💬 Menyusun overlay ranking list...")
    overlay_filters = build_overlay_filters(script_data["title"], segments)

    print("🎬 Rendering final video...")
    final_path = render_final(bg_path, audio_path, overlay_filters)

    print(f"✅ Done! Final video: {final_path}")


if __name__ == "__main__":
    main()
