"""
Nexora Labs - YouTube Shorts Video Renderer
Stock footage (Pexels) + caption sinkron + voiceover -> final video
Fallback ke background generated kalau Pexels gagal/ga ketemu.
"""

import os
import json
import math
import subprocess
from pathlib import Path

import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

OUTPUT_DIR     = Path("yt_output")
W, H           = 1080, 1920
WORDS_PER_CAPTION = 3

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")


# ─── AUDIO HELPER ────────────────────────────────────────────
def get_audio_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())


# ─── PEXELS STOCK FOOTAGE ────────────────────────────────────
def search_pexels_video(keyword: str) -> str | None:
    """Cari 1 video portrait yang relevan, return URL file-nya atau None."""
    headers = {"Authorization": PEXELS_API_KEY}
    params  = {"query": keyword, "orientation": "portrait", "per_page": 5, "size": "medium"}

    try:
        resp = requests.get("https://api.pexels.com/videos/search",
                             headers=headers, params=params, timeout=20)
        resp.raise_for_status()
        videos = resp.json().get("videos", [])
        if not videos:
            return None

        video = videos[0]
        files = video.get("video_files", [])
        if not files:
            return None

        # Prioritaskan resolusi yang cukup tinggi (minimal width 720) biar ga blur
        # saat di-scale ke 1080x1920. Urutkan dari yang paling mendekati 1080 width.
        good_files = [f for f in files if f.get("width", 0) >= 720]
        candidates = good_files if good_files else files
        chosen = min(candidates, key=lambda f: abs(f.get("width", 0) - 1080))
        return chosen["link"]

    except Exception as e:
        print(f"   ⚠️  Pexels search error untuk '{keyword}': {e}")
        return None


def download_file(url: str, out_path: Path):
    r = requests.get(url, stream=True, timeout=60)
    r.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)


def get_stock_footage_multi(keywords: list, max_clips: int = 3, clip_duration: int = 12) -> Path | None:
    """Download beberapa clip dari keyword berbeda, gabung jadi 1 background yang berganti-ganti."""
    downloaded = []
    for i, kw in enumerate(keywords[:max_clips]):
        print(f"   🔍 Searching Pexels: '{kw}'...")
        url = search_pexels_video(kw)
        if url:
            raw_path = OUTPUT_DIR / f"raw_clip_{i}.mp4"
            print(f"   ⬇️  Downloading clip {i+1}...")
            try:
                download_file(url, raw_path)
                downloaded.append(raw_path)
            except Exception as e:
                print(f"   ⚠️  Gagal download clip {i+1}: {e}")

    if not downloaded:
        return None

    # Normalize tiap clip: scale+crop ke 1080x1920, potong durasi tetap, re-encode konsisten
    # biar bisa di-concat dengan aman (codec/resolusi/fps harus sama).
    normalized = []
    for i, raw in enumerate(downloaded):
        norm_path = OUTPUT_DIR / f"norm_clip_{i}.mp4"
        cmd = [
            "ffmpeg", "-y", "-i", str(raw),
            "-t", str(clip_duration),
            "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30",
            "-an",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            str(norm_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            normalized.append(norm_path)
        else:
            print(f"   ⚠️  Gagal normalize clip {i+1}: {result.stderr[-500:]}")

    if not normalized:
        return None

    # Gabung semua clip jadi 1 sequence yang berganti-ganti
    concat_list_path = OUTPUT_DIR / "concat_list.txt"
    with open(concat_list_path, "w") as f:
        for p in normalized:
            f.write(f"file '{p.resolve()}'\n")

    sequence_path = OUTPUT_DIR / "background_sequence.mp4"
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list_path),
        "-c", "copy",
        str(sequence_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("FFMPEG CONCAT ERROR:", result.stderr[-1000:])
        return None

    print(f"   ✅ {len(normalized)} clip digabung jadi 1 sequence")
    return sequence_path


# ─── FALLBACK: GENERATED BACKGROUND ──────────────────────────
def generate_fallback_background() -> Path:
    """Background tech/AI theme kalau Pexels gagal — neural network look."""
    cx, cy = W // 2, H // 2

    arr = np.zeros((H, W, 3), dtype=np.uint8)
    for y in range(H):
        ratio = y / H
        arr[y, :, 0] = int(5 + 8 * (1 - ratio))
        arr[y, :, 1] = int(8 + 12 * (1 - ratio))
        arr[y, :, 2] = int(15 + 25 * (1 - ratio))
    img = Image.fromarray(arr)

    glow = Image.new("RGB", (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for r in range(500, 0, -4):
        t = 1 - (r / 500)
        col = (int(10 * t**2), int(120 * t**2.2), int(160 * t**2))
        gd.ellipse([cx-r, cy-r-150, cx+r, cy+r-150], fill=col)
    glow_blur = glow.filter(ImageFilter.GaussianBlur(radius=50))
    img = Image.blend(img, glow_blur, alpha=0.5)
    draw = ImageDraw.Draw(img)

    np.random.seed(42)
    nodes = [(np.random.randint(60, W-60), np.random.randint(150, H-150)) for _ in range(22)]
    for (x1, y1) in nodes:
        dists = sorted(nodes, key=lambda p: (p[0]-x1)**2 + (p[1]-y1)**2)
        for (x2, y2) in dists[1:3]:
            if math.hypot(x2-x1, y2-y1) < 420:
                draw.line([x1, y1, x2, y2], fill=(0, 120, 160), width=1)
    for (x, y) in nodes:
        r = np.random.choice([2, 3, 4])
        draw.ellipse([x-r, y-r, x+r, y+r], fill=(80, 220, 255))
        draw.ellipse([x-r-4, y-r-4, x+r+4, y+r+4], outline=(0, 150, 200))

    out_path = OUTPUT_DIR / "background.jpg"
    img.save(out_path, "JPEG", quality=90)
    return out_path


# ─── CAPTIONS (.ass) ─────────────────────────────────────────
def sec_to_ass_time(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def generate_subtitles(word_timings: list) -> Path:
    """Caption dengan opaque box di belakang teks — lebih kebaca di atas video asli."""
    header = """[Script Info]
Title: Nexora Facts Captions
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Poppins,80,&H00FFFFFF,&H0000D4FF,&H00000000,&H99000000,1,0,0,0,100,100,0,0,3,0,0,5,60,60,420,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for i in range(0, len(word_timings), WORDS_PER_CAPTION):
        chunk = word_timings[i:i + WORDS_PER_CAPTION]
        if not chunk:
            continue
        start = chunk[0]["offset"]
        end   = chunk[-1]["offset"] + chunk[-1]["duration"]
        text  = " ".join(w["text"] for w in chunk).upper()
        lines.append(
            f"Dialogue: 0,{sec_to_ass_time(start)},{sec_to_ass_time(end)},"
            f"Default,,0,0,0,,{text}"
        )

    out_path = OUTPUT_DIR / "captions.ass"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(lines))
    return out_path


# ─── RENDER FINAL VIDEO ───────────────────────────────────────
def render_with_stock_footage(clip_path: Path, audio_path: Path, ass_path: Path, duration: float) -> Path:
    out_path = OUTPUT_DIR / "final_video.mp4"

    vf_filter = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},"
        f"format=yuv420p,"
        f"eq=brightness=-0.05:saturation=0.9,"
        f"ass={ass_path}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", str(clip_path),
        "-i", str(audio_path),
        "-vf", vf_filter,
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        str(out_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("FFMPEG ERROR:", result.stderr[-3000:])
        raise RuntimeError("ffmpeg render gagal (stock footage)")
    return out_path


def render_with_fallback_bg(bg_path: Path, audio_path: Path, ass_path: Path, duration: float) -> Path:
    out_path = OUTPUT_DIR / "final_video.mp4"
    zoom_expr = "min(zoom+0.0004,1.15)"

    vf_filter = (
        f"scale=1300:-1,crop={W}:{H},"
        f"zoompan=z='{zoom_expr}':d=1:s={W}x{H}:fps=30,"
        f"format=yuv420p,"
        f"ass={ass_path}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(bg_path),
        "-i", str(audio_path),
        "-vf", vf_filter,
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        str(out_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("FFMPEG ERROR:", result.stderr[-3000:])
        raise RuntimeError("ffmpeg render gagal (fallback bg)")
    return out_path


def main():
    print("🚀 Video Renderer starting...")

    with open(OUTPUT_DIR / "word_timings.json") as f:
        word_timings = json.load(f)

    with open(OUTPUT_DIR / "script.json") as f:
        script_data = json.load(f)

    audio_path = OUTPUT_DIR / "voiceover.mp3"
    duration = get_audio_duration(audio_path)
    print(f"   Audio duration: {duration:.1f}s")

    print("💬 Generating synced captions...")
    ass_path = generate_subtitles(word_timings)

    keywords = script_data.get("visual_keywords", [])
    clip_path = None

    if PEXELS_API_KEY and keywords:
        print("🎥 Mencari stock footage di Pexels...")
        clip_path = get_stock_footage_multi(keywords)

    if clip_path:
        print("🎬 Rendering dengan stock footage...")
        final_path = render_with_stock_footage(clip_path, audio_path, ass_path, duration)
    else:
        print("⚠️  Stock footage tidak ditemukan — pakai background fallback")
        bg_path = generate_fallback_background()
        final_path = render_with_fallback_bg(bg_path, audio_path, ass_path, duration)

    print(f"✅ Done! Final video: {final_path}")


if __name__ == "__main__":
    main()
