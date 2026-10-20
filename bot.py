import os, json, re, time, html, asyncio
import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

def load_env():
    for line in open(os.path.expanduser("~/ytbot/.env")):
        if "=" in line:
            k, v = line.strip().split("=", 1)
            os.environ[k] = v
load_env()

URL = "https://llm.albiontools.fun/v1/chat/completions"
KEY = os.environ["ROUTER_KEY"]
MODEL = os.environ.get("ROUTER_MODEL", "kr/claude-sonnet-4.5")
ALLOWED = os.environ.get("ALLOWED_ID", "")
PER_MENIT = 10
GAYA = "simple flat vector illustration, same white stickman character with round head and thick black outline, minimal pastel background, clean icons, vertical 9:16"

def boleh(update):
    return (not ALLOWED) or str(update.effective_user.id) == ALLOWED

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

async def minta_naskah(menit, tema):
    n = menit * PER_MENIT
    sistem = (
        "Kamu penulis naskah video tutorial singkat berbahasa Indonesia, satu langkah jelas per scene. "
        f"Buat tepat {n} scene. Narasi antar scene harus mengalir menyambung seperti orang bercerita, pakai kata penghubung, bukan poin terpisah. Tiap scene punya 'narasi' (15-18 kata, "
        "bahasa Indonesia, enak dibaca keras) dan 'prompt_gambar' "
        "(bahasa Inggris, 1-2 kalimat, deskriptif). "
        f"Semua prompt_gambar harus diakhiri dengan gaya tetap ini: {GAYA}. "
        "Tokoh utama selalu stickman yang sama di semua scene. "
        'Balas HANYA JSON: {"judul":"","deskripsi":"","tag":[],'
        '"scenes":[{"narasi":"","prompt_gambar":""}]}'
    )
    body = {"model": MODEL, "stream": False, "messages": [
        {"role": "system", "content": sistem},
        {"role": "user", "content": "Tema: " + tema}]}
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(URL, json=body,
                         headers={"Authorization": "Bearer " + KEY})
    r.raise_for_status()
    txt = baca(r.text).strip()
    txt = re.sub(r"^\x60{3}(?:json)?|\x60{3}$", "", txt, flags=re.M).strip()
    return json.loads(txt)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot aktif. Coba /naskah 1 tema video")

async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ID kamu: " + str(update.effective_user.id))

async def naskah(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not boleh(update):
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
    folder = os.path.expanduser("~/ytbot/proyek/" + time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(folder, exist_ok=True)
    with open(folder + "/scenes.json", "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    await update.message.reply_text(
        "JUDUL: %s\n\n%s\n\nTersimpan di: %s" % (
            data.get("judul", ""), data.get("deskripsi", ""), folder))
    for i, s in enumerate(data.get("scenes", []), 1):
        await update.message.reply_text(
            "<b>Scene %d</b> - %s\n\n<code>%s</code>" % (
                i, html.escape(s.get("narasi", "")),
                html.escape(s.get("prompt_gambar", ""))),
            parse_mode="HTML")
        await asyncio.sleep(1.1)

app = Application.builder().token(os.environ["BOT_TOKEN"]).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("id", myid))
app.add_handler(CommandHandler("naskah", naskah))
from buat import buat
app.add_handler(CommandHandler("buat", buat))
app.run_polling()
