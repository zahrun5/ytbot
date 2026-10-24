"""
AI Image Module - Generate foto via ag/gemini-3.1-flash-image
Menggunakan provider 9r (llm.albiontools.fun) untuk generate gambar AI
sebagai alternatif manual download dari Google Flow.
"""

import os
import base64
import re
import time
import requests

AI_IMAGE_MODEL = "ag/gemini-3.1-flash-image"


def _get_api_config():
    """Ambil config API dari environment."""
    base_url = os.environ.get("LLM_BASE_URL", "https://llm.albiontools.fun/v1")
    api_key = os.environ.get("ROUTER_KEY", "")
    
    return {
        "base_url": base_url,
        "api_key": api_key,
    }


def generate_image(prompt: str, output_path: str, max_retry: int = 3) -> str:
    """
    Generate foto AI berdasarkan detailed prompt menggunakan ag/gemini-3.1-flash-image.

    Args:
        prompt: detailed prompt deskripsi gambar (bahasa Inggris)
        output_path: path output file (.jpg)
        max_retry: jumlah percobaan ulang

    Returns:
        path file foto yang sudah disimpan
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    cfg = _get_api_config()

    # Prompt enhancement untuk video background
    generation_prompt = (
        f"{prompt}. "
        "Professional photography, cinematic, high quality, no text, no watermark, "
        "no subtitles, suitable for video background, realistic, 9:16 vertical aspect ratio."
    )

    print(f"[AI Image] Generating: {prompt[:80]}...")

    last_error = None
    for attempt in range(1, max_retry + 1):
        try:
            response = requests.post(
                f"{cfg['base_url']}/chat/completions",
                headers={
                    "Authorization": f"Bearer {cfg['api_key']}",
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0 (Linux; Android) ytbot/1.0",
                },
                json={
                    "model": AI_IMAGE_MODEL,
                    "messages": [{"role": "user", "content": generation_prompt}],
                    "stream": False,
                },
                timeout=60,
            )
            response.raise_for_status()

            if not response.text.strip():
                raise ValueError("Response kosong dari AI image provider")

            content = response.json()["choices"][0]["message"]["content"]

            # Ekstrak base64 dari format: ![...](data:image/jpeg;base64,<data>)
            match = re.search(
                r'!\[.*?\]\(data:image/(\w+);base64,([A-Za-z0-9+/=\s]+)\)',
                content
            )
            if not match:
                # Fallback: cari data URL tanpa markdown wrapper
                match = re.search(
                    r'data:image/(\w+);base64,([A-Za-z0-9+/=\s]+)',
                    content
                )

            if not match:
                raise ValueError(f"Tidak ditemukan image data dalam response. Content: {content[:200]}")

            img_data = match.group(2).replace("\n", "").replace(" ", "")
            img_bytes = base64.b64decode(img_data)

            with open(output_path, "wb") as f:
                f.write(img_bytes)

            print(f"[AI Image] Foto disimpan: {output_path} ({len(img_bytes)//1024} KB)")
            return output_path

        except Exception as e:
            last_error = str(e)
            print(f"[AI Image] Attempt {attempt}/{max_retry} gagal: {e}")
            if attempt < max_retry:
                time.sleep(3 * attempt)

    raise RuntimeError(f"AI Image gagal setelah {max_retry} percobaan: {last_error}")


def generate_all(scenes: list, media_dir: str) -> list:
    """
    Generate foto AI untuk semua scenes.

    Args:
        scenes: list scene dari LLM output (tiap scene punya 'prompt_video')
        media_dir: direktori output untuk menyimpan images

    Returns:
        list path foto, sesuai urutan scenes
    """
    os.makedirs(media_dir, exist_ok=True)
    foto_paths = []
    
    for i, scene in enumerate(scenes):
        output_path = os.path.join(media_dir, f"scene_{i+1:02d}.jpg")
        
        # Gunakan prompt_video dari scene
        prompt = scene.get("prompt_video", "")
        if not prompt:
            # Fallback kalau tidak ada prompt_video
            prompt = f"Beautiful cinematic scene, dramatic lighting, high quality photography"
        
        try:
            path = generate_image(prompt, output_path)
        except Exception as e:
            print(f"[AI Image] Gagal generate foto scene {i+1}: {e}. Coba fallback prompt...")
            try:
                fallback_prompt = "Beautiful inspirational landscape with dramatic lighting, cinematic photography"
                path = generate_image(fallback_prompt, output_path)
            except Exception as e2:
                raise RuntimeError(f"AI Image fallback juga gagal untuk scene {i+1}: {e2}")
        
        foto_paths.append(path)
    
    return foto_paths


if __name__ == "__main__":
    # Test
    test_prompt = "A beautiful sunset over mountains, cinematic photography"
    output = "/tmp/test_image.jpg"
    try:
        result = generate_image(test_prompt, output)
        print(f"Success: {result}")
    except Exception as e:
        print(f"Error: {e}")
