"""
Nexora Labs - YouTube Shorts Fact Generator
Script (Groq) + Voiceover (edge-tts, gratis) + caption timing
"""

import os
import json
import asyncio
import requests
from pathlib import Path

GROQ_API_KEY = os.environ["GROQ_API_KEY"]
OUTPUT_DIR   = Path("yt_output")

# Niche: fakta unik tech & AI — bisa diganti sesuai mood/niche lain
NICHE = "teknologi dan kecerdasan buatan (AI)"

VOICE = "id-ID-ArdiNeural"  # suara TTS Indonesia — natural, cocok buat narasi fakta


def generate_script() -> dict:
    """Generate fact script pakai Groq — dioptimasi buat ~45 detik narasi."""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    system_prompt = f"""Kamu adalah penulis script untuk channel YouTube Shorts tentang fakta-fakta {NICHE} yang mengejutkan.

Tulis SATU script pendek dengan struktur ini:
1. HOOK (kalimat pertama) — harus langsung menarik perhatian, bikin penasaran atau kaget
2. FAKTA — fakta utama yang mengejutkan, dijelaskan dengan jelas
3. KONTEKS — 1-2 kalimat tentang kenapa ini penting atau implikasi mengejutkannya
4. OUTRO — kalimat penutup pendek yang engaging (JANGAN "like and subscribe", buat yang bikin orang mikir)

Aturan:
- Total script: 110-140 kata (pas buat ~45 detik narasi)
- Bahasa Indonesia santai, gaya ngomong natural — JANGAN bahasa formal/tulisan
- Tanpa emoji, tanpa hashtag di dalam script
- Bikin kayak temen yang ngerti banyak hal lagi cerita sesuatu yang gila
- Faktanya harus benar-benar menarik, spesifik, dan idealnya bukan yang udah umum diketahui

Balas HANYA dengan JSON valid format ini, tanpa teks lain:
{{
  "title": "judul singkat yang catchy buat video (max 60 karakter)",
  "script": "script narasi lengkap sebagai satu string",
  "hashtags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "visual_keywords": ["english keyword 1", "english keyword 2", "english keyword 3"]
}}

Catatan untuk visual_keywords: berikan 3 kata kunci dalam BAHASA INGGRIS yang cocok untuk mencari stock footage video di Pexels yang merepresentasikan topik fakta ini secara visual (misal: "artificial intelligence", "brain technology", "computer code"). Urutkan dari yang paling relevan."""

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Buatkan satu script fakta sekarang."}
        ],
        "temperature": 1.0,
        "max_tokens": 600
    }

    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers=headers, json=payload, timeout=30
    )
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"].strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


async def generate_voiceover(text: str, out_path: Path) -> list:
    """Generate voiceover pakai edge-tts (gratis) + ambil word-timing buat caption."""
    import edge_tts

    communicate = edge_tts.Communicate(text, VOICE, rate="+5%")
    word_boundaries = []

    with open(out_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                word_boundaries.append({
                    "text": chunk["text"],
                    "offset": chunk["offset"] / 10_000_000,   # ke detik
                    "duration": chunk["duration"] / 10_000_000
                })

    return word_boundaries


def get_audio_duration(path: Path) -> float:
    import subprocess
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())


def estimate_word_timings(text: str, duration: float) -> list:
    """Fallback kalau voice ga support WordBoundary — estimasi rata berdasarkan panjang kata."""
    words = text.split()
    total_chars = sum(len(w) for w in words) or 1
    timings = []
    t = 0.0
    for w in words:
        weight = len(w) / total_chars
        dur = weight * duration
        timings.append({"text": w, "offset": t, "duration": dur})
        t += dur
    return timings


def main():
    print("🚀 YouTube Facts Generator starting...")
    OUTPUT_DIR.mkdir(exist_ok=True)

    print("📝 Generating script via Groq...")
    data = generate_script()
    print(f"   Title: {data['title']}")
    print(f"   Script ({len(data['script'].split())} words): {data['script'][:80]}...")

    # Simpan script + metadata
    with open(OUTPUT_DIR / "script.json", "w") as f:
        json.dump(data, f, indent=2)

    print("🔊 Generating voiceover (edge-tts)...")
    audio_path = OUTPUT_DIR / "voiceover.mp3"
    word_boundaries = asyncio.run(generate_voiceover(data["script"], audio_path))
    print(f"   Audio saved: {audio_path}")
    print(f"   Word timings captured: {len(word_boundaries)} words")

    # Fallback: kalau voice ga ngirim WordBoundary, estimasi manual
    if not word_boundaries:
        print("   ⚠️  No WordBoundary data — pakai estimasi manual")
        duration = get_audio_duration(audio_path)
        word_boundaries = estimate_word_timings(data["script"], duration)
        print(f"   Estimated {len(word_boundaries)} word timings dari durasi {duration:.1f}s")

    # Simpan timing buat caption sync nanti
    with open(OUTPUT_DIR / "word_timings.json", "w") as f:
        json.dump(word_boundaries, f, indent=2)

    print("✅ Done! Script + voiceover ready in yt_output/")


if __name__ == "__main__":
    main()
