"""
Nexora Labs - YouTube Shorts Ranking Generator
Format: Top 5 ranking list (hewan lucu/absurd)
Script per item (Groq) + Voiceover per segmen (edge-tts) + concat
"""

import os
import json
import asyncio
import subprocess
import requests
from pathlib import Path

GROQ_API_KEY = os.environ["GROQ_API_KEY"]
OUTPUT_DIR   = Path("yt_output")

NICHE = "momen hewan paling lucu dan absurd"
VOICE = "id-ID-ArdiNeural"


def generate_ranking() -> dict:
    """Generate struktur ranking Top 5 pakai Groq."""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    system_prompt = f"""Kamu adalah penulis script untuk channel YouTube Shorts ranking "Top 5" tentang {NICHE}.

PENTING: Ini channel HEWAN tanpa wajah manusia sama sekali — fokus ke tingkah laku hewan yang lucu, absurd, atau ga terduga.

Buat struktur ranking dengan urutan dari #5 (paling biasa) sampai #1 (PALING absurd/lucu, klimaks di akhir).

Untuk tiap item, kasih:
- "label": teks singkat max 5 kata buat list overlay (contoh: "Kucing Takut Timun")
- "script": 1-2 kalimat narasi santai buat item ini, bikin penasaran, Bahasa Indonesia natural
- "visual_keyword": keyword BAHASA INGGRIS generik buat cari stock footage di Pexels (contoh: "cat funny scared", "dog playing water") — jangan terlalu spesifik karena harus ketemu video asli di stock footage

Aturan:
- Bahasa Indonesia santai, gaya cerita ke temen
- Tanpa emoji dalam script (boleh di label)
- Item harus ngalir dari yang "lumayan lucu" ke yang "paling gila/absurd"
- Intro dan outro pendek, jangan "like and subscribe"

Balas HANYA dengan JSON valid format ini, tanpa teks lain:
{{
  "title": "judul singkat catchy (max 50 karakter)",
  "intro": "1-2 kalimat pembuka yang bikin penasaran",
  "items": [
    {{"rank": 5, "label": "...", "script": "...", "visual_keyword": "..."}},
    {{"rank": 4, "label": "...", "script": "...", "visual_keyword": "..."}},
    {{"rank": 3, "label": "...", "script": "...", "visual_keyword": "..."}},
    {{"rank": 2, "label": "...", "script": "...", "visual_keyword": "..."}},
    {{"rank": 1, "label": "...", "script": "...", "visual_keyword": "..."}}
  ],
  "outro": "kalimat penutup pendek yang engaging",
  "hashtags": ["tag1", "tag2", "tag3", "tag4", "tag5"]
}}"""

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Buatkan satu ranking Top 5 sekarang."}
        ],
        "temperature": 1.0,
        "max_tokens": 1200
    }

    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers=headers, json=payload, timeout=30
    )
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"].strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


async def generate_segment_audio(text: str, out_path: Path):
    import edge_tts
    communicate = edge_tts.Communicate(text, VOICE, rate="+5%")
    with open(out_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])


def get_audio_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())


def main():
    print("🚀 Ranking Generator starting...")
    OUTPUT_DIR.mkdir(exist_ok=True)

    print("📝 Generating ranking structure via Groq...")
    data = generate_ranking()
    print(f"   Title: {data['title']}")

    with open(OUTPUT_DIR / "script.json", "w") as f:
        json.dump(data, f, indent=2)

    # Susun urutan segmen: intro -> item5 -> item4 -> ... -> item1 -> outro
    items_sorted = sorted(data["items"], key=lambda x: -x["rank"])  # 5,4,3,2,1
    segment_defs = [{"type": "intro", "text": data["intro"]}]
    for item in items_sorted:
        segment_defs.append({
            "type": "item", "rank": item["rank"], "label": item["label"],
            "visual_keyword": item["visual_keyword"], "text": item["script"]
        })
    segment_defs.append({"type": "outro", "text": data["outro"]})

    print("🔊 Generating voiceover per segmen...")
    audio_dir = OUTPUT_DIR / "segments"
    audio_dir.mkdir(exist_ok=True)

    segments = []
    current_offset = 0.0
    concat_lines = []

    for i, seg in enumerate(segment_defs):
        seg_path = audio_dir / f"seg_{i}.mp3"
        asyncio.run(generate_segment_audio(seg["text"], seg_path))
        dur = get_audio_duration(seg_path)

        entry = {
            "type": seg["type"],
            "start": current_offset,
            "end": current_offset + dur,
            "duration": dur
        }
        if seg["type"] == "item":
            entry["rank"] = seg["rank"]
            entry["label"] = seg["label"]
            entry["visual_keyword"] = seg["visual_keyword"]

        segments.append(entry)
        concat_lines.append(f"file '{seg_path.resolve()}'")
        current_offset += dur
        print(f"   Segmen {i} ({seg['type']}): {dur:.1f}s")

    # Gabung semua audio segmen jadi 1 file voiceover utuh
    concat_list_path = audio_dir / "concat_list.txt"
    with open(concat_list_path, "w") as f:
        f.write("\n".join(concat_lines))

    final_audio_path = OUTPUT_DIR / "voiceover.mp3"
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list_path), "-c", "copy", str(final_audio_path)
    ]
    subprocess.run(cmd, capture_output=True, text=True)

    with open(OUTPUT_DIR / "segments.json", "w") as f:
        json.dump(segments, f, indent=2)

    print(f"✅ Done! Total durasi: {current_offset:.1f}s")
    print(f"   Audio: {final_audio_path}")
    print(f"   Segments: {OUTPUT_DIR / 'segments.json'}")


if __name__ == "__main__":
    main()
