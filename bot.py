import os, json, time, html, asyncio
import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

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
COBA = 3
MAKS_KATA = 19  # lebih dari ini narasi bisa melebihi klip 8 detik
STICKMAN = ("a small white stickman with a round head, thick black outline "
            "and simple stick limbs")
AKHIR = ("No text, no letters, no subtitles, no speech. "
         "Vertical 9:16, 8 seconds.")


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
            terbaik = data  # valid tapi belum pas, simpan sebagai cadangan
        except Exception as e:
            galat = e
        if percobaan < COBA - 1:
            await asyncio.sleep(2)
    if terbaik is not None:
        return terbaik
    raise galat or RuntimeError("naskah gagal dibuat")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bot aktif.\n/naskah <menit 1-3> <tema> : bikin naskah\n"
        "/buat <nama folder> : rakit video dari media di Pictures\n/id : lihat ID kamu")


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ID kamu: " + str(update.effective_user.id))


async def naskah(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await boleh(update):
        return
    a = context.args
    if len(a) < 2 or not a[0].isdigit() or not 1 <= int(a[0]) <= 3:
        await update.message.reply_text(
            "Format: /naskah <menit 1-3> <tema>\n"
            "Contoh: /naskah 1 sejarah kerajaan Majapahit")
        return
    menit, tema = int(a[0]), " ".join(a[1:])
    await update.message.reply_text("Sedang bikin naskah, tunggu sebentar...")
    try:
        data = await minta_naskah(menit, tema)
    except Exception as e:
        await update.message.reply_text("Gagal: %s %s" % (type(e).__name__, str(e)[:200]))
        return
    folder = os.path.join(BASE, "proyek", time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(folder, exist_ok=True)
    with open(folder + "/scenes.json", "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    scenes = data["scenes"]
    catatan = ""
    if len(scenes) != menit * PER_MENIT:
        catatan += "\n\nCatatan: model membuat %d scene (target %d)." % (
            len(scenes), menit * PER_MENIT)
    panjang = scene_panjang(scenes)
    if panjang:
        catatan += ("\n\nCatatan: narasi scene %s lebih dari %d kata, "
                    "bisa melebihi klip 8 detik." % (
                        ", ".join(map(str, panjang)), MAKS_KATA))
    await update.message.reply_text(
        "JUDUL: %s\n\n%s%s\n\nTersimpan di: %s" % (
            data.get("judul", ""), data.get("deskripsi", ""), catatan, folder))
    for i, s in enumerate(scenes, 1):
        await update.message.reply_text(
            "<b>Scene %d</b> - %s\n\n<code>%s</code>" % (
                i, html.escape(s.get("narasi", "")),
                html.escape(s.get("prompt_video", ""))),
            parse_mode="HTML")
        await asyncio.sleep(1.1)


from buat import buat  # setelah load_env()

app = Application.builder().token(os.environ["BOT_TOKEN"]).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("id", myid))
app.add_handler(CommandHandler("naskah", naskah))
app.add_handler(CommandHandler("buat", buat))
app.run_polling()
