import os, json, time, html, asyncio
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes
)

BASE = os.path.dirname(os.path.abspath(__file__))


def load_env():
    path = os.path.join(BASE, ".env")
    if not os.path.exists(path):
        raise SystemExit("File .env tidak ditemukan di " + path)
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()


load_env()

URL = "https://llm.albiontools.fun/v1/chat/completions"
KEY = os.environ["ROUTER_KEY"]
MODEL = os.environ.get("ROUTER_MODEL", "kr/claude-sonnet-4.5")
PER_MENIT = 10
DL = os.path.realpath(os.path.expanduser("~/storage/shared/Download"))
COBA = 3
MAKS_KATA = 19
STICKMAN = ("a small white stickman with a round head, thick black outline "
            "and simple stick limbs")
AKHIR = ("No text, no letters, no subtitles, no speech. "
         "Vertical 9:16, 8 seconds.")

# User state untuk conversation
user_states = {}


def allowed_id():
    return os.environ.get("ALLOWED_ID", "").strip()


async def boleh(update):
    """Fail-closed: kalau ALLOWED_ID kosong, semua perintah sensitif ditolak."""
    a = allowed_id()
    if not a:
        await update.message.reply_text(
            "ALLOWED_ID di .env belum diisi, bot menolak semua perintah. "
            "Kirim /id, salin angkanya ke ALLOWED_ID, lalu restart bot.")
        return False
    return str(update.effective_user.id) == a


def baca(resp_text):
    t = resp_text.strip()
    if t.startswith("data:"):
        out = ""
        for line in t.splitlines():
            if line.startswith("data:") and "[DONE]" not in line:
                try:
                    d = json.loads(line[5:])
                    out += d["choices"][0]["delta"].get("content") or ""
                except Exception:
                    pass
        return out
    return json.loads(t)["choices"][0]["message"]["content"]


def ambil_json(txt):
    """Ambil objek JSON pertama-terakhir, tahan terhadap pagar kode atau kalimat pembuka."""
    a, b = txt.find("{"), txt.rfind("}")
    if a == -1 or b <= a:
        raise ValueError("JSON tidak ditemukan di balasan model")
    return json.loads(txt[a:b + 1])


def cek_scenes(data):
    sc = data.get("scenes") if isinstance(data, dict) else None
    if not isinstance(sc, list) or not sc:
        raise ValueError("daftar scenes kosong atau tidak ada")
    for i, s in enumerate(sc, 1):
        if (not isinstance(s, dict) or not str(s.get("narasi", "")).strip()
                or not str(s.get("prompt_video", "")).strip()):
            raise ValueError("scene %d tidak lengkap" % i)
    return sc


def scene_panjang(sc):
    """Nomor scene yang narasinya melebihi MAKS_KATA."""
    return [i for i, s in enumerate(sc, 1)
            if len(str(s["narasi"]).split()) > MAKS_KATA]


async def improve_prompt_with_ai(old_prompt: str, instruction: str, narasi: str = "") -> str:
    """
    Use LLM to improve video prompt based on instruction.
    
    Args:
        old_prompt: Current prompt
        instruction: Improvement instruction (preset or custom feedback)
        narasi: Scene narration for context
    
    Returns:
        Improved prompt
    """
    system_msg = (
        "You are a prompt engineer expert for AI image/video generation. "
        "Improve the given video prompt based on user feedback. "
        "Keep the stickman description EXACTLY as is (a small white stickman with a round head, thick black outline and simple stick limbs). "
        "Always end with: 'No text, no letters, no subtitles, no speech. Vertical 9:16, 8 seconds.' "
        "Make the prompt detailed, cinematic, and specific. Output ONLY the improved prompt, nothing else."
    )
    
    user_msg = f"""
Narasi scene (context): {narasi}

Current prompt:
{old_prompt}

Instruction:
{instruction}

Output the improved prompt (keep stickman description exact, keep ending exact):
"""
    
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(URL, json={
                "model": MODEL,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg}
                ]
            }, headers={"Authorization": "Bearer " + KEY})
        r.raise_for_status()
        improved = baca(r.text).strip()
        
        # Clean up if wrapped in quotes or code blocks
        improved = improved.strip('"\'`')
        if improved.startswith("```"):
            improved = "\n".join(improved.split("\n")[1:-1])
        
        return improved
    except Exception as e:
        print(f"[AI Improve] Error: {e}")
        # Fallback: return modified version manually
        if "ancient" in instruction.lower() or "historic" in instruction.lower():
            return f"Ancient 7th century {old_prompt}"
        elif "modern" in instruction.lower():
            return old_prompt.replace("historic", "ancient 7th century") + " No modern elements, no modern buildings, no modern technology."
        elif "dramatic" in instruction.lower():
            return old_prompt.replace("scene", "dramatic cinematic scene").replace("Camera", "Dynamic camera")
        else:
            return old_prompt


async def minta_naskah(menit, tema):
    n = menit * PER_MENIT
    sistem = (
        "Kamu penulis naskah video pendek berbahasa Indonesia yang tiap scene-nya "
        "dibuat jadi satu klip AI berdurasi 8 detik. "
        f"Buat tepat {n} scene, satu langkah atau gagasan jelas per scene. "
        "Narasi antar scene harus mengalir menyambung seperti orang bercerita, "
        "pakai kata penghubung, bukan poin terpisah. "
        "Tiap scene punya 'narasi' (14-17 kata, bahasa Indonesia, enak dibaca keras, "
        "jangan lebih dari 17 kata) dan 'prompt_video' (bahasa Inggris, 2-3 kalimat). "
        "prompt_video mendeskripsikan adegan sinematik yang REALISTIS sesuai topik: "
        "benda, tempat, dan orang lain tampil realistis dan BUKAN stickman. "
        "Sebut juga aksi stickman di scene itu dan gerak kameranya. "
        "Untuk topik tutorial atau tips, stickman adalah pelaku langkahnya. "
        "Untuk topik sejarah, tokoh, atau peradaban, stickman adalah pemandu yang "
        "berdiri atau berjalan di dalam masa itu sebagai pengamat, sedangkan tokoh "
        "dan dunianya realistis. "
        f"Stickman selalu karakter yang sama di semua scene, dan setiap prompt_video "
        f"harus menyebutnya dengan deskripsi persis ini: {STICKMAN}. "
        "Jangan minta teks, tulisan, label, angka, atau subtitle muncul di gambar. "
        f"Setiap prompt_video harus diakhiri kalimat ini: {AKHIR} "
        'Balas HANYA JSON: {"judul":"","deskripsi":"","tag":[],'
        '"scenes":[{"narasi":"","prompt_video":""}]}'
    )
    body = {"model": MODEL, "stream": False, "messages": [
        {"role": "system", "content": sistem},
        {"role": "user", "content": "Tema: " + tema}]}
    terbaik, galat = None, None
    for percobaan in range(COBA):
        try:
            async with httpx.AsyncClient(timeout=180) as c:
                r = await c.post(URL, json=body,
                                 headers={"Authorization": "Bearer " + KEY})
            r.raise_for_status()
            data = ambil_json(baca(r.text))
            sc = cek_scenes(data)
            if len(sc) == n and not scene_panjang(sc):
                return data
            terbaik = data
        except Exception as e:
            galat = e
        if percobaan < COBA - 1:
            await asyncio.sleep(2)
    if terbaik is not None:
        return terbaik
    raise galat or RuntimeError("naskah gagal dibuat")


# ============================================================
# KEYBOARD MENU
# ============================================================

def main_keyboard():
    """Main menu keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Buat Naskah", callback_data="menu_naskah")],
        [InlineKeyboardButton("🖼️ Generate Images (AI)", callback_data="menu_generate")],
        [InlineKeyboardButton("🔄 Regenerate Scene", callback_data="menu_regenerate")],
        [InlineKeyboardButton("🎬 Buat Video", callback_data="menu_buat")],
        [InlineKeyboardButton("⬆️ Upload Ulang", callback_data="menu_reupload")],
        [InlineKeyboardButton("📤 Upload Settings", callback_data="menu_upload")],
        [InlineKeyboardButton("📊 Status", callback_data="menu_status")],
    ])


async def safe_send_message(context, chat_id, text, reply_markup=None, parse_mode="Markdown"):
    """Send message with automatic fallback if markdown parsing fails."""
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
    except Exception as e:
        if "parse entities" in str(e).lower() or "can't find end" in str(e).lower():
            # Markdown error - fallback to plain text
            plain_text = text.replace("*", "").replace("_", "").replace("`", "").replace("[", "").replace("]", "")
            await context.bot.send_message(
                chat_id=chat_id,
                text=plain_text,
                reply_markup=reply_markup
            )
        else:
            raise


def upload_settings_keyboard():
    """Keyboard untuk upload settings."""
    target = os.environ.get("UPLOAD_TARGET", "youtube")
    
    yt_mark = "✅" if target == "youtube" else "⚪"
    fb_mark = "✅" if target == "facebook" else "⚪"
    both_mark = "✅" if target == "both" else "⚪"
    
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{yt_mark} YouTube only", callback_data="upload_youtube")],
        [InlineKeyboardButton(f"{fb_mark} Facebook only", callback_data="upload_facebook")],
        [InlineKeyboardButton(f"{both_mark} Both", callback_data="upload_both")],
        [InlineKeyboardButton("◀️ Kembali", callback_data="back_main")],
    ])


# ============================================================
# HANDLERS
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /start - show main menu."""
    await update.message.reply_text(
        "🎬 *YTBot - AI Video Generator*\n\n"
        "Bot untuk generate video AI otomatis dengan narasi dan upload ke YouTube/Facebook.\n\n"
        "Pilih menu di bawah:",
        reply_markup=main_keyboard(),
        parse_mode="Markdown"
    )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /id."""
    await update.message.reply_text("ID kamu: " + str(update.effective_user.id))


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk semua button callback."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    data = query.data
    
    # Check permission untuk menu sensitif
    a = allowed_id()
    if a and str(user_id) != a and data not in ["back_main"]:
        await query.edit_message_text("❌ Kamu tidak punya akses ke bot ini.")
        return
    
    # Main menu
    if data == "back_main":
        await query.edit_message_text(
            "🎬 *YTBot - AI Video Generator*\n\n"
            "Pilih menu di bawah:",
            reply_markup=main_keyboard(),
            parse_mode="Markdown"
        )
    
    # Menu Naskah
    elif data == "menu_naskah":
        user_states[user_id] = {"action": "naskah_menit"}
        await query.edit_message_text(
            "📝 *Buat Naskah Video*\n\n"
            "Berapa menit durasi video yang mau kamu buat?\n"
            "Kirim angka 1-3 (menit).",
            parse_mode="Markdown"
        )
    
    # Menu Generate Images
    elif data == "menu_generate":
        # Cari project terbaru
        import glob
        daftar = sorted(glob.glob(os.path.join(BASE, "proyek", "*", "scenes.json")))
        if not daftar:
            await query.edit_message_text(
                "❌ Belum ada naskah. Buat naskah dulu lewat menu 'Buat Naskah'.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Kembali", callback_data="back_main")
                ]])
            )
            return
        
        pdir = os.path.dirname(daftar[-1])
        timestamp = os.path.basename(pdir)
        user_states[user_id] = {"action": "generate", "timestamp": timestamp}
        
        await query.edit_message_text(
            f"🖼️ *Generate Images (AI)*\n\n"
            f"Project: `{timestamp}`\n\n"
            f"Akan generate images untuk semua scenes menggunakan AI.\n"
            f"Lanjutkan?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Ya, Generate!", callback_data="confirm_generate")],
                [InlineKeyboardButton("◀️ Batal", callback_data="back_main")],
            ]),
            parse_mode="Markdown"
        )
    
    # Confirm generate
    elif data == "confirm_generate":
        state = user_states.get(user_id, {})
        timestamp = state.get("timestamp")
        if not timestamp:
            await query.edit_message_text("❌ Session expired, coba lagi.")
            return
        
        await query.edit_message_text("🖼️ Generating images... Mohon tunggu...")
        
        try:
            import ai_image
            pdir = os.path.join(BASE, "proyek", timestamp)
            sj = pdir + "/scenes.json"
            
            with open(sj) as f:
                meta = json.load(f)
            scenes = meta["scenes"]
            
            mdir_file = pdir + "/media_dir.txt"
            if os.path.exists(mdir_file):
                media_dir = open(mdir_file).read().strip()
            else:
                media_dir = os.path.join(DL, "ytbot-" + timestamp)
                os.makedirs(media_dir, exist_ok=True)
                with open(mdir_file, "w") as f:
                    f.write(media_dir)
            
            paths = await asyncio.to_thread(ai_image.generate_all, scenes, media_dir)
            
            await context.bot.send_message(
                chat_id=user_id,
                text=f"✅ *Generate selesai!*\n\n"
                     f"Generated {len(paths)} images.\n"
                     f"Folder: `{media_dir}`\n\n"
                     f"Selanjutnya: pilih 'Buat Video' untuk render.",
                parse_mode="Markdown",
                reply_markup=main_keyboard()
            )
            
        except Exception as e:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"❌ Gagal: {str(e)[:300]}",
                reply_markup=main_keyboard()
            )
    
    # Menu Regenerate Scene
    elif data == "menu_regenerate":
        import glob
        daftar = sorted(glob.glob(os.path.join(BASE, "proyek", "*", "scenes.json")))
        if not daftar:
            await query.edit_message_text(
                "❌ Belum ada naskah. Buat naskah dulu lewat menu 'Buat Naskah'.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Kembali", callback_data="back_main")
                ]])
            )
            return
        
        pdir = os.path.dirname(daftar[-1])
        timestamp = os.path.basename(pdir)
        
        # Load scenes
        with open(daftar[-1]) as f:
            meta = json.load(f)
        scenes = meta["scenes"]
        
        user_states[user_id] = {"action": "regenerate_select", "timestamp": timestamp}
        
        await query.edit_message_text(
            f"🔄 *Regenerate Scene*\n\n"
            f"Project: `{timestamp}`\n"
            f"Total scenes: {len(scenes)}\n\n"
            f"Kirim nomor scene yang mau di-regenerate (1-{len(scenes)})\n"
            f"Contoh: 5",
            parse_mode="Markdown"
        )
    
    # Preset improvements
    elif data.startswith("preset_"):
        parts = data.split("_")
        preset_type = parts[1]
        scene_num = int(parts[2])
        
        state = user_states.get(user_id, {})
        timestamp = state.get("timestamp")
        
        if not timestamp:
            await query.edit_message_text("❌ Session expired, coba lagi.")
            return
        
        await query.edit_message_text(f"⏳ Memperbaiki prompt dengan preset '{preset_type}'...")
        
        try:
            pdir = os.path.join(BASE, "proyek", timestamp)
            sj = pdir + "/scenes.json"
            
            with open(sj, "r") as f:
                meta = json.load(f)
            
            scenes = meta["scenes"]
            scene = scenes[scene_num - 1]
            old_prompt = scene.get("prompt_video", "")
            
            # Define preset instructions
            preset_instructions = {
                "ancient": "Make this prompt more ancient and historic. Add specific details about 7th century Arabia, ancient architecture, traditional clothing, and remove any hint of modern elements.",
                "nomodern": "Remove all modern elements from this prompt. Emphasize ancient/historic setting, traditional architecture, oil lamps instead of electric lights, no modern technology or buildings.",
                "dramatic": "Make this scene more dramatic and cinematic. Add more tension, dynamic camera movements, dramatic lighting, and intense atmosphere.",
                "lighting": "Improve the lighting description to be more cinematic and visually appealing. Add golden hour, dramatic shadows, or atmospheric lighting details."
            }
            
            instruction = preset_instructions.get(preset_type, "Improve this prompt")
            
            # Call LLM to improve prompt
            new_prompt = await improve_prompt_with_ai(old_prompt, instruction, scene.get("narasi", ""))
            
            # Save to file
            scenes[scene_num - 1]["prompt_video"] = new_prompt
            with open(sj, "w") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
            
            await context.bot.send_message(
                chat_id=user_id,
                text=f"✅ *Prompt Diperbaiki!*\n\n"
                     f"*Prompt baru:*\n`{new_prompt[:200]}...`\n\n"
                     f"Lanjut regenerate?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Ya, Regenerate!", callback_data=f"confirm_regen_{scene_num}")],
                    [InlineKeyboardButton("🔄 Perbaiki lagi", callback_data=f"back_to_scene_{scene_num}")],
                    [InlineKeyboardButton("◀️ Batal", callback_data="back_main")],
                ]),
                parse_mode="Markdown"
            )
            
        except Exception as e:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"❌ Gagal: {str(e)[:300]}",
                reply_markup=main_keyboard()
            )
    
    # Back to scene selection (after preset)
    elif data.startswith("back_to_scene_"):
        scene_num = int(data.replace("back_to_scene_", ""))
        state = user_states.get(user_id, {})
        timestamp = state.get("timestamp")
        
        if not timestamp:
            await query.edit_message_text("❌ Session expired, coba lagi.")
            return
        
        pdir = os.path.join(BASE, "proyek", timestamp)
        sj = pdir + "/scenes.json"
        
        with open(sj) as f:
            meta = json.load(f)
        scene = meta["scenes"][scene_num - 1]
        
        await query.edit_message_text(
            f"🔄 *Regenerate Scene {scene_num}*\n\n"
            f"Narasi: {scene.get('narasi', '')}\n\n"
            f"Prompt saat ini:\n`{scene.get('prompt_video', '')[:120]}...`\n\n"
            f"Pilih cara perbaiki prompt:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Regenerate (prompt sama)", callback_data=f"confirm_regen_{scene_num}")],
                [InlineKeyboardButton("🏛️ Lebih kuno/historic", callback_data=f"preset_ancient_{scene_num}"),
                 InlineKeyboardButton("🚫 Hindari modern", callback_data=f"preset_nomodern_{scene_num}")],
                [InlineKeyboardButton("🎭 Lebih dramatis", callback_data=f"preset_dramatic_{scene_num}"),
                 InlineKeyboardButton("🌅 Lighting lebih bagus", callback_data=f"preset_lighting_{scene_num}")],
                [InlineKeyboardButton("✏️ Feedback custom (AI)", callback_data=f"custom_feedback_{scene_num}")],
                [InlineKeyboardButton("◀️ Batal", callback_data="back_main")],
            ]),
            parse_mode="Markdown"
        )
    
    # Custom feedback
    elif data.startswith("custom_feedback_"):
        scene_num = int(data.replace("custom_feedback_", ""))
        state = user_states.get(user_id, {})
        timestamp = state.get("timestamp")
        
        if not timestamp:
            await query.edit_message_text("❌ Session expired, coba lagi.")
            return
        
        pdir = os.path.join(BASE, "proyek", timestamp)
        sj = pdir + "/scenes.json"
        
        with open(sj) as f:
            meta = json.load(f)
        scene = meta["scenes"][scene_num - 1]
        
        user_states[user_id] = {
            "action": "custom_feedback",
            "timestamp": timestamp,
            "scene_num": scene_num
        }
        
        await query.edit_message_text(
            f"✏️ *Custom Feedback - Scene {scene_num}*\n\n"
            f"Prompt saat ini:\n`{scene.get('prompt_video', '')[:150]}...`\n\n"
            f"*Kirim instruksi perbaikan* (bahasa Indonesia ok):\n\n"
            f"Contoh:\n"
            f"• 'terlalu modern, harusnya zaman Arabia kuno'\n"
            f"• 'kurang dramatis, tambahin efek pencahayaan'\n"
            f"• 'adegan kurang tegang, bikin lebih epic'\n"
            f"• 'hindari bangunan modern, fokus arsitektur kuno'",
            parse_mode="Markdown"
        )
    
    # Edit prompt before regenerate (keep old manual edit feature)
    elif data.startswith("edit_prompt_"):
        scene_num = int(data.replace("edit_prompt_", ""))
        state = user_states.get(user_id, {})
        timestamp = state.get("timestamp")
        
        if not timestamp:
            await query.edit_message_text("❌ Session expired, coba lagi.")
            return
        
        pdir = os.path.join(BASE, "proyek", timestamp)
        sj = pdir + "/scenes.json"
        
        with open(sj) as f:
            meta = json.load(f)
        scenes = meta["scenes"]
        scene = scenes[scene_num - 1]
        
        user_states[user_id] = {
            "action": "edit_prompt", 
            "timestamp": timestamp, 
            "scene_num": scene_num
        }
        
        await query.edit_message_text(
            f"✏️ *Edit Prompt - Scene {scene_num}*\n\n"
            f"Prompt saat ini:\n`{scene.get('prompt_video', '')}`\n\n"
            f"Kirim prompt baru (bahasa Inggris).\n\n"
            f"Tips untuk hindari modern:\n"
            f"- Tambah: 'ancient', 'historic', '7th century'\n"
            f"- Tambah: 'no modern buildings, no cars, no technology'\n"
            f"- Spesifik: 'mud-brick houses', 'traditional robes', 'desert landscape'",
            parse_mode="Markdown"
        )
    
    # Confirm regenerate
    elif data.startswith("confirm_regen_"):
        scene_num = int(data.replace("confirm_regen_", ""))
        state = user_states.get(user_id, {})
        timestamp = state.get("timestamp")
        
        if not timestamp:
            await query.edit_message_text("❌ Session expired, coba lagi.")
            return
        
        await query.edit_message_text(f"🖼️ Regenerating scene {scene_num}... Mohon tunggu...")
        
        try:
            import ai_image
            pdir = os.path.join(BASE, "proyek", timestamp)
            sj = pdir + "/scenes.json"
            
            with open(sj) as f:
                meta = json.load(f)
            scenes = meta["scenes"]
            
            if scene_num < 1 or scene_num > len(scenes):
                raise ValueError(f"Scene {scene_num} tidak ada (total {len(scenes)} scenes)")
            
            scene = scenes[scene_num - 1]
            
            mdir_file = pdir + "/media_dir.txt"
            if os.path.exists(mdir_file):
                media_dir = open(mdir_file).read().strip()
            else:
                media_dir = os.path.join(DL, "ytbot-" + timestamp)
                os.makedirs(media_dir, exist_ok=True)
            
            output_path = os.path.join(media_dir, f"scene_{scene_num:02d}.jpg")
            prompt = scene.get("prompt_video", "Beautiful cinematic scene")
            
            path = await asyncio.to_thread(ai_image.generate_image, prompt, output_path)
            
            await context.bot.send_message(
                chat_id=user_id,
                text=f"✅ *Scene {scene_num} regenerated!*\n\n"
                     f"File: `{path}`\n\n"
                     f"Preview:",
                parse_mode="Markdown"
            )
            
            # Send image preview
            try:
                with open(path, "rb") as img:
                    await context.bot.send_photo(
                        chat_id=user_id,
                        photo=img,
                        caption=f"Scene {scene_num}: {scene.get('narasi', '')[:100]}"
                    )
            except Exception:
                pass
            
            await context.bot.send_message(
                chat_id=user_id,
                text="Mau regenerate scene lain?",
                reply_markup=main_keyboard()
            )
            
        except Exception as e:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"❌ Gagal: {str(e)[:300]}",
                reply_markup=main_keyboard()
            )
    
    # Menu Buat Video
    elif data == "menu_buat":
        import glob
        daftar = sorted(glob.glob(os.path.join(BASE, "proyek", "*", "scenes.json")))
        if not daftar:
            await query.edit_message_text(
                "❌ Belum ada naskah. Buat naskah dulu.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Kembali", callback_data="back_main")
                ]])
            )
            return
        
        pdir = os.path.dirname(daftar[-1])
        timestamp = os.path.basename(pdir)
        user_states[user_id] = {"action": "buat", "timestamp": timestamp}
        
        mdir_file = pdir + "/media_dir.txt"
        hint = ""
        if os.path.exists(mdir_file):
            hint = f"\n\nFolder media: `{open(mdir_file).read().strip()}`"
        
        await query.edit_message_text(
            f"🎬 *Buat Video*\n\n"
            f"Project terbaru: `{timestamp}`{hint}\n\n"
            f"Pastikan sudah ada media (images/videos) di folder.\n"
            f"Lanjutkan proses?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Ya, Proses!", callback_data="confirm_buat")],
                [InlineKeyboardButton("◀️ Batal", callback_data="back_main")],
            ]),
            parse_mode="Markdown"
        )
    
    # Confirm buat
    elif data == "confirm_buat":
        state = user_states.get(user_id, {})
        timestamp = state.get("timestamp")
        if not timestamp:
            await query.edit_message_text("❌ Session expired, coba lagi.")
            return
        
        await query.edit_message_text("🎬 Processing video... Ini akan memakan waktu lama, mohon sabar...")
        
        # Import dan jalankan proses buat
        from buat import proses, KUNCI
        
        # Check lock
        if KUNCI.locked():
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="❌ Masih ada proses video yang berjalan. Tunggu selesai dulu.",
                    reply_markup=main_keyboard()
                )
            except Exception:
                pass
            return
        
        async with KUNCI:
            try:
                # Kirim update (query) dan context ke proses
                await proses(query, timestamp, context)
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text="✅ Proses selesai!",
                        reply_markup=main_keyboard()
                    )
                except Exception:
                    # Ignore timeout on final message
                    pass
            except Exception as e:
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"❌ Gagal: {str(e)[:300]}",
                        reply_markup=main_keyboard()
                    )
                except Exception:
                    # Ignore timeout on error message
                    pass
    
    # Upload Settings
    elif data == "menu_upload":
        await query.edit_message_text(
            "📤 *Upload Settings*\n\n"
            "Pilih platform upload:",
            reply_markup=upload_settings_keyboard(),
            parse_mode="Markdown"
        )
    
    elif data.startswith("upload_"):
        target = data.replace("upload_", "")
        
        # Update .env
        env_path = os.path.join(BASE, ".env")
        lines = []
        found = False
        
        with open(env_path, "r") as f:
            for line in f:
                if line.strip().startswith("UPLOAD_TARGET="):
                    lines.append(f"UPLOAD_TARGET={target}\n")
                    found = True
                else:
                    lines.append(line)
        
        if not found:
            lines.append(f"UPLOAD_TARGET={target}\n")
        
        with open(env_path, "w") as f:
            f.writelines(lines)
        
        os.environ["UPLOAD_TARGET"] = target
        
        await query.answer(f"✅ Upload target: {target}")
        await query.edit_message_text(
            "📤 *Upload Settings*\n\n"
            "Pilih platform upload:",
            reply_markup=upload_settings_keyboard(),
            parse_mode="Markdown"
        )
    
    # Status
    elif data == "menu_status":
        import glob
        
        # Count projects
        projects = glob.glob(os.path.join(BASE, "proyek", "*", "scenes.json"))
        
        # Check credentials
        yt_status = "✅" if os.path.exists(os.path.join(BASE, "client_secret.json")) else "❌"
        
        import fb_auth
        fb_status = "✅" if fb_auth.page_id() and fb_auth.page_token() else "❌"
        
        upload_target = os.environ.get("UPLOAD_TARGET", "youtube")
        
        status_text = (
            "📊 *Status Bot*\n\n"
            f"Projects: {len(projects)}\n"
            f"YouTube: {yt_status}\n"
            f"Facebook: {fb_status}\n"
            f"Upload Target: {upload_target}\n"
        )
        
        await query.edit_message_text(
            status_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Kembali", callback_data="back_main")
            ]]),
            parse_mode="Markdown"
        )
    
    # Menu Upload Ulang
    elif data == "menu_reupload":
        import glob
        daftar = sorted(glob.glob(os.path.join(BASE, "proyek", "*", "video.mp4")))
        if not daftar:
            await query.edit_message_text(
                "❌ Belum ada video yang selesai dibuat.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Kembali", callback_data="back_main")
                ]])
            )
            return
        
        video_path = daftar[-1]
        pdir = os.path.dirname(video_path)
        timestamp = os.path.basename(pdir)
        
        # Load metadata
        sj = os.path.join(pdir, "scenes.json")
        if os.path.exists(sj):
            with open(sj) as f:
                meta = json.load(f)
            judul = meta.get("judul", "Video AI")
        else:
            judul = "Video AI"
        
        file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
        upload_target = os.environ.get("UPLOAD_TARGET", "youtube")
        
        user_states[user_id] = {"action": "reupload", "video_path": video_path, "pdir": pdir}
        
        await query.edit_message_text(
            f"⬆️ *Upload Ulang*\n\n"
            f"Video: `{timestamp}`\n"
            f"Judul: {judul}\n"
            f"Size: {file_size_mb:.1f} MB\n\n"
            f"Upload target saat ini: *{upload_target}*\n\n"
            f"Lanjutkan upload?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Ya, Upload!", callback_data="confirm_reupload")],
                [InlineKeyboardButton("📤 Ubah Target", callback_data="menu_upload")],
                [InlineKeyboardButton("◀️ Batal", callback_data="back_main")],
            ]),
            parse_mode="Markdown"
        )
    
    # Confirm reupload
    elif data == "confirm_reupload":
        state = user_states.get(user_id, {})
        video_path = state.get("video_path")
        pdir = state.get("pdir")
        
        if not video_path or not os.path.exists(video_path):
            await query.edit_message_text("❌ Video tidak ditemukan.")
            return
        
        await query.edit_message_text("⬆️ Uploading... Mohon tunggu...")
        
        try:
            # Load metadata
            sj = os.path.join(pdir, "scenes.json")
            with open(sj) as f:
                meta = json.load(f)
            
            upload_target = os.environ.get("UPLOAD_TARGET", "youtube")
            results = []
            
            # YouTube upload
            if upload_target in ["youtube", "both"]:
                try:
                    from yt import upload
                    link = await asyncio.to_thread(
                        upload, video_path, meta.get("judul", "Video AI"),
                        meta.get("deskripsi", ""), meta.get("tag", []), "private")
                    results.append(f"✅ YouTube: {link}")
                except Exception as e:
                    results.append(f"❌ YouTube: {str(e)[:200]}")
            
            # Facebook upload
            if upload_target in ["facebook", "both"]:
                try:
                    from buat import upload_facebook
                    fb_link = await upload_facebook(video_path, meta)
                    results.append(f"✅ Facebook: {fb_link}")
                except Exception as e:
                    results.append(f"❌ Facebook: {str(e)[:200]}")
            
            result_text = "⬆️ *Upload Selesai*\n\n" + "\n\n".join(results)
            
            await safe_send_message(
                context, user_id, result_text,
                reply_markup=main_keyboard()
            )
            
        except Exception as e:
            await safe_send_message(
                context, user_id,
                f"❌ Gagal: {str(e)[:300]}",
                reply_markup=main_keyboard()
            )


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk text messages (untuk conversation flow)."""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    state = user_states.get(user_id, {})
    action = state.get("action")
    
    # Custom feedback - input user feedback
    if action == "custom_feedback":
        timestamp = state.get("timestamp")
        scene_num = state.get("scene_num")
        
        if not timestamp or not scene_num:
            await update.message.reply_text("❌ Session expired, mulai lagi.")
            user_states.pop(user_id, None)
            return
        
        feedback = text
        await update.message.reply_text("⏳ AI sedang memperbaiki prompt berdasarkan feedback Anda...")
        
        try:
            pdir = os.path.join(BASE, "proyek", timestamp)
            sj = pdir + "/scenes.json"
            
            with open(sj, "r") as f:
                meta = json.load(f)
            
            scenes = meta["scenes"]
            scene = scenes[scene_num - 1]
            old_prompt = scene.get("prompt_video", "")
            narasi = scene.get("narasi", "")
            
            # Call AI to improve prompt based on custom feedback
            new_prompt = await improve_prompt_with_ai(old_prompt, feedback, narasi)
            
            # Save to file
            scenes[scene_num - 1]["prompt_video"] = new_prompt
            with open(sj, "w") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
            
            await update.message.reply_text(
                f"✅ *Prompt Diperbaiki!*\n\n"
                f"*Feedback Anda:* {feedback}\n\n"
                f"*Prompt baru:*\n`{new_prompt[:250]}...`\n\n"
                f"Lanjut regenerate?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Ya, Regenerate!", callback_data=f"confirm_regen_{scene_num}")],
                    [InlineKeyboardButton("🔄 Perbaiki lagi", callback_data=f"back_to_scene_{scene_num}")],
                    [InlineKeyboardButton("◀️ Batal", callback_data="back_main")],
                ]),
                parse_mode="Markdown"
            )
            
            user_states[user_id] = {
                "action": "regenerate_confirm",
                "timestamp": timestamp,
                "scene_num": scene_num
            }
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)[:300]}")
            user_states.pop(user_id, None)
        
        return
    
    # Edit prompt - input new prompt
    if action == "edit_prompt":
        timestamp = state.get("timestamp")
        scene_num = state.get("scene_num")
        
        if not timestamp or not scene_num:
            await update.message.reply_text("❌ Session expired, mulai lagi.")
            user_states.pop(user_id, None)
            return
        
        # Save new prompt to scenes.json
        pdir = os.path.join(BASE, "proyek", timestamp)
        sj = pdir + "/scenes.json"
        
        try:
            with open(sj, "r") as f:
                meta = json.load(f)
            
            scenes = meta["scenes"]
            old_prompt = scenes[scene_num - 1].get("prompt_video", "")
            scenes[scene_num - 1]["prompt_video"] = text
            
            # Save updated scenes
            with open(sj, "w") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
            
            await update.message.reply_text(
                f"✅ *Prompt Updated!*\n\n"
                f"Prompt baru tersimpan untuk scene {scene_num}.\n\n"
                f"Lanjut regenerate dengan prompt baru?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Ya, Regenerate!", callback_data=f"confirm_regen_{scene_num}")],
                    [InlineKeyboardButton("◀️ Batal", callback_data="back_main")],
                ]),
                parse_mode="Markdown"
            )
            
            user_states[user_id] = {
                "action": "regenerate_confirm",
                "timestamp": timestamp,
                "scene_num": scene_num
            }
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error update prompt: {str(e)[:200]}")
            user_states.pop(user_id, None)
        
        return
    
    # Regenerate - input scene number
    if action == "regenerate_select":
        if not text.isdigit():
            await update.message.reply_text(
                "❌ Kirim angka nomor scene saja.\n"
                "Contoh: 5"
            )
            return
        
        scene_num = int(text)
        timestamp = state.get("timestamp")
        
        if not timestamp:
            await update.message.reply_text("❌ Session expired, mulai lagi.")
            user_states.pop(user_id, None)
            return
        
        # Load scenes to validate
        import glob
        pdir = os.path.join(BASE, "proyek", timestamp)
        sj = pdir + "/scenes.json"
        
        try:
            with open(sj) as f:
                meta = json.load(f)
            scenes = meta["scenes"]
            
            if scene_num < 1 or scene_num > len(scenes):
                await update.message.reply_text(
                    f"❌ Scene {scene_num} tidak ada. Total scenes: {len(scenes)}\n"
                    f"Kirim angka 1-{len(scenes)}"
                )
                return
            
            scene = scenes[scene_num - 1]
            
            # Show confirmation with edit options
            await update.message.reply_text(
                f"🔄 *Regenerate Scene {scene_num}*\n\n"
                f"Narasi: {scene.get('narasi', '')}\n\n"
                f"Prompt saat ini:\n`{scene.get('prompt_video', '')[:120]}...`\n\n"
                f"Pilih cara perbaiki prompt:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Regenerate (prompt sama)", callback_data=f"confirm_regen_{scene_num}")],
                    [InlineKeyboardButton("🏛️ Lebih kuno/historic", callback_data=f"preset_ancient_{scene_num}"),
                     InlineKeyboardButton("🚫 Hindari modern", callback_data=f"preset_nomodern_{scene_num}")],
                    [InlineKeyboardButton("🎭 Lebih dramatis", callback_data=f"preset_dramatic_{scene_num}"),
                     InlineKeyboardButton("🌅 Lighting lebih bagus", callback_data=f"preset_lighting_{scene_num}")],
                    [InlineKeyboardButton("✏️ Feedback custom (AI)", callback_data=f"custom_feedback_{scene_num}")],
                    [InlineKeyboardButton("◀️ Batal", callback_data="back_main")],
                ]),
                parse_mode="Markdown"
            )
            
            user_states[user_id]["scene_num"] = scene_num
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)[:200]}")
            user_states.pop(user_id, None)
        
        return
    
    # Naskah - input menit
    if action == "naskah_menit":
        if not text.isdigit() or not 1 <= int(text) <= 3:
            await update.message.reply_text(
                "❌ Kirim angka 1-3 saja."
            )
            return
        
        user_states[user_id]["menit"] = int(text)
        user_states[user_id]["action"] = "naskah_tema"
        
        await update.message.reply_text(
            "✅ Durasi: " + text + " menit\n\n"
            "Sekarang kirim tema/topik video.\n"
            "Contoh: sejarah kerajaan Majapahit"
        )
    
    # Naskah - input tema
    elif action == "naskah_tema":
        menit = state.get("menit")
        if not menit:
            await update.message.reply_text("❌ Session expired, mulai lagi.")
            user_states.pop(user_id, None)
            return
        
        tema = text
        await update.message.reply_text("⏳ Sedang bikin naskah, tunggu sebentar...")
        
        try:
            data = await minta_naskah(menit, tema)
        except Exception as e:
            await update.message.reply_text("❌ Gagal: %s %s" % (type(e).__name__, str(e)[:200]))
            user_states.pop(user_id, None)
            return
        
        folder = os.path.join(BASE, "proyek", time.strftime("%Y%m%d-%H%M%S"))
        os.makedirs(folder, exist_ok=True)
        with open(folder + "/scenes.json", "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        scenes = data["scenes"]
        media_dir = os.path.join(DL, "ytbot-" + os.path.basename(folder))
        os.makedirs(media_dir, exist_ok=True)
        with open(folder + "/media_dir.txt", "w") as f:
            f.write(media_dir)
        
        catatan = ""
        if len(scenes) != menit * PER_MENIT:
            catatan += "\n\n⚠️ Model membuat %d scene (target %d)." % (
                len(scenes), menit * PER_MENIT)
        panjang = scene_panjang(scenes)
        if panjang:
            catatan += ("\n\n⚠️ Narasi scene %s lebih dari %d kata, "
                        "bisa melebihi klip 8 detik." % (
                            ", ".join(map(str, panjang)), MAKS_KATA))
        
        await update.message.reply_text(
            "✅ *NASKAH SELESAI*\n\n"
            "*JUDUL:* %s\n\n%s%s\n\n"
            "Tersimpan di: `%s`\n\n"
            "Folder media: `%s`" % (
                data.get("judul", ""), data.get("deskripsi", ""), catatan,
                folder, media_dir),
            parse_mode="Markdown"
        )
        
        # Send scenes
        for i, s in enumerate(scenes, 1):
            await update.message.reply_text(
                "<b>Scene %d</b> - %s\n\n<code>%s</code>" % (
                    i, html.escape(s.get("narasi", "")),
                    html.escape(s.get("prompt_video", ""))),
                parse_mode="HTML")
            await asyncio.sleep(1.1)
        
        await update.message.reply_text(
            "Selanjutnya pilih:\n"
            "🖼️ Generate Images (AI) - untuk auto-generate\n"
            "🎬 Buat Video - kalau sudah ada media",
            reply_markup=main_keyboard()
        )
        
        user_states.pop(user_id, None)


# ============================================================
# MAIN
# ============================================================

from buat import buat  # legacy command support

app = Application.builder().token(os.environ["BOT_TOKEN"]).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("id", myid))
app.add_handler(CommandHandler("buat", buat))  # legacy support
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
app.run_polling()
