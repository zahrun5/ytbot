import os, glob, json, asyncio, textwrap
from telegram import Update
from yt import upload
from telegram.ext import ContextTypes

BASE = os.path.dirname(os.path.abspath(__file__))
VOICE = "id-ID-ArdiNeural"
PICS = os.path.realpath(os.path.expanduser("~/storage/shared/Pictures"))
VF = ("scale=1080:1920:force_original_aspect_ratio=decrease,"
      "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30")
IMG = (".jpg", ".jpeg", ".png", ".webp")
VID = (".mp4", ".mov", ".webm", ".mkv")
VOL_KLIP = 0.3
MAX_TG = 49 * 1024 * 1024  # batas upload bot Telegram 50 MB
FONT = (glob.glob("/system/fonts/Roboto*.ttf")
        + glob.glob("/system/fonts/*.ttf") + [""])[0]
ENC = ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-ar", "44100", "-ac", "2"]

KUNCI = asyncio.Lock()  # satu proses /buat dalam satu waktu


async def jalan(*cmd):
    p = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await p.communicate()
    if p.returncode != 0:
        raise RuntimeError(err.decode()[-300:])
    return out.decode()


async def tts(teks, mp3):
    if os.path.exists(mp3) and os.path.getsize(mp3) > 0:
        return
    for n in range(8):
        try:
            await jalan("edge-tts", "--voice", VOICE,
                        "--text=" + teks, "--write-media", mp3)
            await asyncio.sleep(3)
            return
        except Exception:
            if n == 7:
                raise
            await asyncio.sleep(5 + n * 5)


async def durasi(path):
    out = await jalan("ffprobe", "-v", "error", "-show_entries",
                      "format=duration", "-of", "csv=p=0", path)
    return float(out.strip())


async def ada_audio(path):
    out = await jalan("ffprobe", "-v", "error", "-select_streams", "a",
                      "-show_entries", "stream=codec_type", "-of", "csv=p=0", path)
    return bool(out.strip())


def sub(pdir, i, teks, dn):
    kata = teks.split()
    potong = [" ".join(kata[k:k + 6]) for k in range(0, len(kata), 6)]
    total = len(kata) or 1
    out = ""
    t0 = 0.0
    for j, ptg in enumerate(potong):
        t1 = t0 + dn * len(ptg.split()) / total
        tf = "%s/t%02d_%d.txt" % (pdir, i + 1, j)
        with open(tf, "w") as f:
            f.write(textwrap.fill(ptg, 20))
        out += (",drawtext=fontfile=%s:textfile=%s:expansion=none"
                ":fontcolor=white:fontsize=56:box=1:boxcolor=black@0.5"
                ":boxborderw=18:line_spacing=10:x=(w-text_w)/2"
                ":y=h-text_h-380:enable='between(t,%.2f,%.2f)'") % (FONT, tf, t0, t1)
        t0 = t1
    return out


def folder_aman(nama):
    """Hanya izinkan folder di dalam PICS (blok path absolut dan ../)."""
    fg = os.path.realpath(os.path.join(PICS, nama))
    if fg == PICS or fg.startswith(PICS + os.sep):
        return fg
    return None


async def buat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    a = os.environ.get("ALLOWED_ID", "").strip()
    if not a:
        await update.message.reply_text(
            "ALLOWED_ID di .env belum diisi, bot menolak perintah ini. "
            "Kirim /id, isi ALLOWED_ID, lalu restart bot.")
        return
    if str(update.effective_user.id) != a:
        return
    if not context.args:
        daftar = sorted(glob.glob(os.path.join(BASE, "proyek", "*", "scenes.json")))
        if daftar:
            pdir = os.path.dirname(daftar[-1])
            mdir_file = pdir + "/media_dir.txt"
            hint = ""
            if os.path.exists(mdir_file):
                hint = "\nFolder media: " + open(mdir_file).read().strip()
            await update.message.reply_text(
                "Format: /buat <timestamp>\n"
                "Contoh: /buat " + os.path.basename(pdir) +
                "\n\nNaskah terbaru: " + os.path.basename(pdir) + hint)
        else:
            await update.message.reply_text(
                "Format: /buat <timestamp>\nBelum ada naskah. Jalankan /naskah dulu.")
        return
    if KUNCI.locked():
        await update.message.reply_text(
            "Masih ada proses /buat yang berjalan, tunggu selesai dulu.")
        return
    async with KUNCI:
        await proses(update, " ".join(context.args))


async def proses(update, nama):
    # Cek apakah argumen adalah timestamp folder proyek
    pdir_cek = os.path.join(BASE, "proyek", nama)
    sj_cek = pdir_cek + "/scenes.json"
    mdir_file = pdir_cek + "/media_dir.txt"

    if os.path.isdir(pdir_cek) and os.path.exists(sj_cek):
        # Mode timestamp: pakai media_dir.txt kalau ada, fallback ke Pictures/nama
        pdir = pdir_cek
        sj = sj_cek
        if os.path.exists(mdir_file):
            fg = open(mdir_file).read().strip()
        else:
            fg = folder_aman(nama)
            if fg is None:
                await update.message.reply_text(
                    "media_dir.txt tidak ditemukan dan nama folder tidak valid di Pictures.")
                return
    else:
        # Mode lama: cari folder di Pictures, pakai naskah terbaru
        fg = folder_aman(nama)
        if fg is None:
            await update.message.reply_text(
                "Folder proyek '" + nama + "' tidak ditemukan di proyek/ "
                "dan bukan folder valid di Pictures: " + PICS)
            return
        daftar = sorted(glob.glob(os.path.join(BASE, "proyek", "*", "scenes.json")))
        if not daftar:
            await update.message.reply_text("Belum ada naskah. Jalankan /naskah dulu.")
            return
        sj = daftar[-1]
        pdir = os.path.dirname(sj)

    if not os.path.isdir(fg):
        await update.message.reply_text("Folder media tidak ditemukan: " + fg)
        return
    media = sorted((f for f in glob.glob(fg + "/*")
                    if f.lower().endswith(IMG + VID)), key=os.path.getmtime)
    if not media:
        await update.message.reply_text("Tidak ada gambar/video di folder: " + fg)
        return
    try:
        with open(sj) as f:
            meta = json.load(f)
        scenes = meta["scenes"]
        if not scenes:
            raise ValueError("scenes kosong")
    except Exception as e:
        await update.message.reply_text("Naskah rusak (%s): %s" % (sj, str(e)[:200]))
        return
    pesan = "%d scene, %d file (gambar/video)." % (len(scenes), len(media))
    if len(media) != len(scenes):
        pesan += " Jumlahnya beda, file diulang/dipotong sesuai urutan waktu unduh."
    await update.message.reply_text(pesan + " Mulai proses...")
    klips = []
    try:
        for i, s in enumerate(scenes):
            mp3 = "%s/s%02d.mp3" % (pdir, i + 1)
            klip = "%s/k%02d.mp4" % (pdir, i + 1)
            f = media[i % len(media)]
            await tts(s["narasi"], mp3)
            dn = await durasi(mp3) + 0.25
            st = sub(pdir, i, s["narasi"], dn)
            if f.lower().endswith(VID):
                fc = ("[0:v]" + VF + ",tpad=stop_mode=clone:stop_duration=30"
                      + st + "[v]")
                if await ada_audio(f):
                    fc += (";[0:a]volume=" + str(VOL_KLIP) + "[a0];[1:a]apad[a1];"
                           "[a0][a1]amix=inputs=2:normalize=0[a]")
                else:
                    fc += ";[1:a]apad[a]"
                cmd = (["ffmpeg", "-y", "-i", f, "-i", mp3,
                        "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
                        "-t", "%.2f" % dn] + ENC + [klip])
            else:
                cmd = (["ffmpeg", "-y", "-loop", "1", "-i", f, "-i", mp3,
                        "-vf", VF + st, "-af", "apad",
                        "-t", "%.2f" % dn] + ENC + [klip])
            await jalan(*cmd)
            klips.append(klip)
            if (i + 1) % 4 == 0:
                await update.message.reply_text(
                    "Scene %d/%d selesai" % (i + 1, len(scenes)))
        with open(pdir + "/list.txt", "w") as f:
            for k in klips:
                f.write("file '%s'\n" % k)
        hasil = pdir + "/video.mp4"
        await jalan("ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", pdir + "/list.txt", "-c", "copy", hasil)
    except Exception as e:
        await update.message.reply_text("Gagal: %s" % str(e)[:300])
        return

    ukuran = os.path.getsize(hasil)
    if ukuran > MAX_TG:
        await update.message.reply_text(
            "Video jadi (%.0f MB), terlalu besar untuk dikirim lewat Telegram. "
            "File: %s" % (ukuran / 1048576, hasil))
    else:
        await update.message.reply_text("Video jadi, mengirim...")
        try:
            with open(hasil, "rb") as v:
                await update.message.reply_video(
                    v, read_timeout=300, write_timeout=300, connect_timeout=60)
        except Exception as e:
            await update.message.reply_text(
                "Kirim video ke Telegram gagal: %s" % str(e)[:200])

    await update.message.reply_text("Mengupload ke YouTube (private)...")
    try:
        link = await asyncio.to_thread(
            upload, hasil, meta.get("judul", "Video AI"),
            meta.get("deskripsi", ""), meta.get("tag", []), "private")
        await update.message.reply_text("Terupload (private): " + link)
    except Exception as e:
        await update.message.reply_text("Upload gagal: %s" % str(e)[:300])
