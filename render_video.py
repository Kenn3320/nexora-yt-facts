"""
Nexora Labs - YouTube Shorts Video Renderer
Background tech-themed + caption sinkron + voiceover -> final video
"""

import json
import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

OUTPUT_DIR = Path("yt_output")
W, H = 1080, 1920

WORDS_PER_CAPTION = 3  # jumlah kata per caption chunk


def get_audio_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())


def generate_background() -> Path:
    """Background tech/AI theme: dark navy + glowing circuit nodes."""
    cx, cy = W // 2, H // 2

    # Base gradient (dark navy -> black)
    arr = np.zeros((H, W, 3), dtype=np.uint8)
    for y in range(H):
        ratio = y / H
        arr[y, :, 0] = int(5 + 8 * (1 - ratio))
        arr[y, :, 1] = int(8 + 12 * (1 - ratio))
        arr[y, :, 2] = int(15 + 25 * (1 - ratio))
    img = Image.fromarray(arr)
    draw = ImageDraw.Draw(img)

    # Glow blob (cyan) behind center
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for r in range(500, 0, -4):
        t = 1 - (r / 500)
        col = (int(10 * t**2), int(120 * t**2.2), int(160 * t**2))
        gd.ellipse([cx-r, cy-r-150, cx+r, cy+r-150], fill=col)
    glow_blur = glow.filter(ImageFilter.GaussianBlur(radius=50))
    img = Image.blend(img, glow_blur, alpha=0.5)
    draw = ImageDraw.Draw(img)

    # Circuit-style connected nodes (neural network look)
    np.random.seed(42)  # konsisten tiap render biar branding stabil
    n_nodes = 22
    nodes = []
    for i in range(n_nodes):
        x = np.random.randint(60, W - 60)
        y = np.random.randint(150, H - 150)
        nodes.append((x, y))

    # Garis penghubung antar node yang berdekatan
    for i, (x1, y1) in enumerate(nodes):
        dists = sorted(nodes, key=lambda p: (p[0]-x1)**2 + (p[1]-y1)**2)
        for (x2, y2) in dists[1:3]:
            d = math.hypot(x2-x1, y2-y1)
            if d < 420:
                alpha = max(20, 70 - int(d/10))
                draw.line([x1, y1, x2, y2], fill=(0, 120, 160), width=1)

    # Node dots
    for (x, y) in nodes:
        r = np.random.choice([2, 3, 4])
        draw.ellipse([x-r, y-r, x+r, y+r], fill=(80, 220, 255))
        draw.ellipse([x-r-4, y-r-4, x+r+4, y+r+4], outline=(0, 150, 200))

    # Vignette gelap di tepi biar caption lebih terbaca
    vignette = Image.new("L", (W, H), 0)
    vd = ImageDraw.Draw(vignette)
    vd.rectangle([0, 0, W, 280], fill=255)
    vd.rectangle([0, H-500, W, H], fill=255)
    vignette = vignette.filter(ImageFilter.GaussianBlur(80))
    black = Image.new("RGB", (W, H), (0, 0, 0))
    img = Image.composite(black, img, vignette.point(lambda p: int(p*0.55)))

    out_path = OUTPUT_DIR / "background.jpg"
    img.save(out_path, "JPEG", quality=90)
    return out_path


def sec_to_ass_time(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def generate_subtitles(word_timings: list) -> Path:
    """Bikin file .ass — caption muncul per beberapa kata, sinkron suara."""
    header = """[Script Info]
Title: Nexora Facts Captions
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Poppins,84,&H00FFFFFF,&H0000D4FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,5,2,5,60,60,420,1

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


def render_final_video(bg_path: Path, audio_path: Path, ass_path: Path, duration: float):
    out_path = OUTPUT_DIR / "final_video.mp4"

    # zoompan butuh source agak lebih besar dari target biar ga upscale kasar
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

    print("🎬 Rendering final video...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("FFMPEG ERROR:", result.stderr[-3000:])
        raise RuntimeError("ffmpeg render failed")

    return out_path


def main():
    print("🚀 Video Renderer starting...")

    with open(OUTPUT_DIR / "word_timings.json") as f:
        word_timings = json.load(f)

    audio_path = OUTPUT_DIR / "voiceover.mp3"
    duration = get_audio_duration(audio_path)
    print(f"   Audio duration: {duration:.1f}s")

    print("🎨 Generating background...")
    bg_path = generate_background()

    print("💬 Generating synced captions...")
    ass_path = generate_subtitles(word_timings)

    final_path = render_final_video(bg_path, audio_path, ass_path, duration)
    print(f"✅ Done! Final video: {final_path}")


if __name__ == "__main__":
    main()
