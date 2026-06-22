"""
Nexora Labs - YouTube Shorts Ranking Generator (No Narration)
Format: Top 5 ranking list, caption pendek reaktif, no voiceover — musik only
"""

import os
import json
import requests
from pathlib import Path

GROQ_API_KEY = os.environ["GROQ_API_KEY"]
OUTPUT_DIR   = Path("yt_output")

NICHE = "momen hewan paling lucu dan absurd"

# Durasi fix per segmen (detik) — ga lagi ngikutin panjang narasi
INTRO_DURATION = 2.0
ITEM_DURATION  = 3.5
OUTRO_DURATION = 2.0


def generate_ranking() -> dict:
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    system_prompt = f"""Kamu adalah penulis caption untuk channel YouTube Shorts ranking "Top 5" tentang {NICHE}.

PENTING: Video ini TANPA narasi/voiceover sama sekali — cuma musik dan caption singkat reaktif (mirip caption di video TikTok compilation kucing/hewan lucu).

Buat struktur ranking dari #5 (lumayan lucu) sampai #1 (PALING absurd, klimaks di akhir).

Untuk title, pecah jadi 3 bagian:
- "title_before": bagian sebelum kata yang di-highlight
- "title_highlight": SATU kata yang mau dikasih warna beda (biasanya nama hewan, contoh: "KUCING")
- "title_after": bagian setelah kata yang di-highlight
(Total title harus singkat, max 40 karakter, contoh: "RANKING MOMEN [KUCING] PALING ABSURD")

Untuk tiap item, kasih:
- "caption": caption SUPER PENDEK 1-3 kata gaya reaktif/meme (contoh: "Jumpscare", "Dead Inside", "Plot Twist", "Gak Masuk Akal", "Bukan Salah Gue") — JANGAN kalimat deskriptif panjang
- "visual_keyword": keyword BAHASA INGGRIS yang menggambarkan AKSI/GERAKAN dinamis, BUKAN pose statis. WAJIB pakai kata kerja aktif seperti: jumping, falling, running, chasing, zoomies, playing, surprised, startled, slipping, climbing, splashing. Contoh BAGUS: "dog zoomies funny", "cat falls off bed", "puppy slipping floor", "kitten attacking toy". Contoh BURUK (hindari): "cat sitting", "dog portrait", "rabbit looking" — ini menghasilkan footage diam/membosankan.

PENTING: Caption dan visual_keyword harus SELARAS — kalau caption "Jumpscare" maka keyword harus action yang bikin kaget (contoh: "cat startled jumping"), bukan keyword pasif.

Balas HANYA dengan JSON valid format ini, tanpa teks lain:
{{
  "title_before": "...",
  "title_highlight": "...",
  "title_after": "...",
  "items": [
    {{"rank": 5, "caption": "...", "visual_keyword": "..."}},
    {{"rank": 4, "caption": "...", "visual_keyword": "..."}},
    {{"rank": 3, "caption": "...", "visual_keyword": "..."}},
    {{"rank": 2, "caption": "...", "visual_keyword": "..."}},
    {{"rank": 1, "caption": "...", "visual_keyword": "..."}}
  ],
  "hashtags": ["tag1", "tag2", "tag3", "tag4", "tag5"]
}}"""

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Buatkan satu ranking Top 5 sekarang."}
        ],
        "temperature": 1.0,
        "max_tokens": 800
    }

    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers=headers, json=payload, timeout=30
    )
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"].strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


def main():
    print("🚀 Ranking Generator (No Narration) starting...")
    OUTPUT_DIR.mkdir(exist_ok=True)

    print("📝 Generating ranking structure via Groq...")
    data = generate_ranking()
    print(f"   Title: {data['title_before']} [{data['title_highlight']}] {data['title_after']}")

    with open(OUTPUT_DIR / "script.json", "w") as f:
        json.dump(data, f, indent=2)

    # Susun segmen dengan durasi FIX: intro -> item5 -> item4 -> ... -> item1 -> outro
    items_sorted = sorted(data["items"], key=lambda x: -x["rank"])  # 5,4,3,2,1

    segments = []
    current_offset = 0.0

    segments.append({"type": "intro", "start": current_offset,
                      "end": current_offset + INTRO_DURATION, "duration": INTRO_DURATION,
                      "visual_keyword": items_sorted[0]["visual_keyword"]})
    current_offset += INTRO_DURATION

    for item in items_sorted:
        segments.append({
            "type": "item", "rank": item["rank"], "caption": item["caption"],
            "visual_keyword": item["visual_keyword"],
            "start": current_offset, "end": current_offset + ITEM_DURATION,
            "duration": ITEM_DURATION
        })
        current_offset += ITEM_DURATION

    segments.append({"type": "outro", "start": current_offset,
                      "end": current_offset + OUTRO_DURATION, "duration": OUTRO_DURATION,
                      "visual_keyword": items_sorted[-1]["visual_keyword"]})
    current_offset += OUTRO_DURATION

    with open(OUTPUT_DIR / "segments.json", "w") as f:
        json.dump(segments, f, indent=2)

    print(f"✅ Done! Total durasi: {current_offset:.1f}s (tanpa voiceover)")
    print(f"   Segments: {OUTPUT_DIR / 'segments.json'}")


if __name__ == "__main__":
    main()
