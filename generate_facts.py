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
NICHE = "technology and artificial intelligence"

VOICE = "en-US-JennyNeural"  # suara TTS — natural, clear, cocok buat fact content


def generate_script() -> dict:
    """Generate fact script pakai Groq — dioptimasi buat ~45 detik narasi."""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    system_prompt = f"""You are a scriptwriter for a YouTube Shorts channel about surprising {NICHE} facts.

Write ONE short script following this exact structure:
1. HOOK (first sentence) — must grab attention immediately, create curiosity or disbelief
2. FACT — the core surprising fact, explained clearly
3. CONTEXT — 1-2 sentences of why it matters or a surprising implication
4. OUTRO — a short engaging closing line (NOT "like and subscribe", make it thought-provoking)

Rules:
- Total script: 110-140 words (fits ~45 seconds spoken aloud)
- Conversational, natural spoken English — NOT written/formal tone
- No emojis, no hashtags in the script itself
- Make it feel like a knowledgeable friend telling you something wild
- The fact must be genuinely interesting, specific, and ideally not super commonly known

Return ONLY valid JSON in this exact format, nothing else:
{{
  "title": "short catchy title for the video (max 60 chars)",
  "script": "the full narration script as one string",
  "hashtags": ["tag1", "tag2", "tag3", "tag4", "tag5"]
}}"""

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Generate one fact script now."}
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

    # Simpan timing buat caption sync nanti
    with open(OUTPUT_DIR / "word_timings.json", "w") as f:
        json.dump(word_boundaries, f, indent=2)

    print("✅ Done! Script + voiceover ready in yt_output/")


if __name__ == "__main__":
    main()
