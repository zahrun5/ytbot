# ytbot

A Telegram bot that runs on Android (Termux) to automate AI short-video creation and uploads to YouTube & Facebook.

**Workflow:**
1. Use bot menu to generate an AI script (narration + video prompts per scene)
2. Auto-generate AI images via `ag/gemini-3.1-flash-image` OR manually download videos
3. Assemble the final video with TTS narration, subtitles, and upload to YouTube/Facebook

---

## Requirements

- Android with [Termux](https://termux.dev) and storage access granted
- Python 3.10+
- `ffmpeg` and `ffprobe`
- A Telegram bot token ([create one via @BotFather](https://t.me/botfather))
- An LLM API key (compatible with OpenAI chat completions format)
- A Google Cloud project with YouTube Data API v3 enabled

---

## Installation

```bash
# 1. Clone the repo
git clone https://github.com/zahrun5/ytbot.git
cd ytbot

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install system packages (Termux)
pkg install ffmpeg

# 4. Grant storage access (Termux)
termux-setup-storage
```

---

## Configuration

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

Edit `.env`:

```
BOT_TOKEN=        # Telegram bot token from @BotFather
ROUTER_KEY=       # Your LLM API key
ROUTER_MODEL=     # Model ID (default: kr/claude-sonnet-4.5)
LLM_BASE_URL=     # API base URL (default: https://llm.albiontools.fun/v1)
ALLOWED_ID=       # Your Telegram user ID (see below)

# Upload target: youtube, facebook, or both
UPLOAD_TARGET=youtube

# Facebook (optional - only if you want to upload to Facebook)
FACEBOOK_PAGE_ID=
FACEBOOK_PAGE_ACCESS_TOKEN=
FACEBOOK_USER_ACCESS_TOKEN=
FACEBOOK_APP_ID=
FACEBOOK_APP_SECRET=
```

To find your Telegram user ID, start the bot first (without `ALLOWED_ID` set), then send `/id` to the bot.

---

## Google / YouTube Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project, enable **YouTube Data API v3**
3. Create OAuth 2.0 credentials (Desktop app type), download as `client_secret.json` and place it in the `ytbot/` folder
4. Run the login helper once to authorize:

```bash
python login.py
```

This opens a local OAuth flow and saves `token.json`. The token refreshes automatically after that.

---

## Facebook Setup (Optional)

If you want to upload to Facebook, follow these steps:

### 1. Create Facebook App

1. Go to [Meta for Developers](https://developers.facebook.com)
2. Create a new app
3. Add "Pages" permission
4. Note your **App ID** and **App Secret** from Settings → Basic

### 2. Get User Access Token

1. Go to [Graph API Explorer](https://developers.facebook.com/tools/explorer)
2. Select your app
3. Click **Get Access Token** → **Get User Access Token**
4. Select permissions:
   - `pages_show_list`
   - `pages_read_engagement`
   - `pages_manage_posts`
   - `pages_manage_video`
   - `public_profile`
5. Copy the token

### 3. Get Page Access Token (Never Expiring)

Facebook user tokens expire in 1-2 hours, but page tokens derived from a **long-lived user token** will **NEVER expire** unless you change your password or revoke app access!

Fill in your initial credentials in `.env`:
```bash
FACEBOOK_PAGE_ID=<your-page-id>
FACEBOOK_USER_ACCESS_TOKEN=<paste-user-token-here>
FACEBOOK_APP_ID=<your-app-id>
FACEBOOK_APP_SECRET=<your-app-secret>
```

Then check and generate your page token:
```bash
python -c "import fb_auth; print(fb_auth.status())"
```

To verify if your token is permanent, check it on [Facebook Access Token Debugger](https://developers.facebook.com/tools/debug/accesstoken/). Look at **Expires**: if it says **"Never"**, you are all set forever!

Even if the token ever becomes invalid, `fb_auth.py` automatically exchanges the user token, retrieves a fresh page token from `/me/accounts`, and saves it back to `.env` without interrupting bot operation.

---

## Running the Bot

```bash
python bot.py
```

Keep it running in the background with `tmux` or `nohup`:

```bash
nohup python bot.py &
```

---

## Bot Commands

The bot now uses **interactive buttons** instead of text commands!

| Command | Description |
|---------|-------------|
| `/start` | Show main menu with buttons |
| `/id` | Show your Telegram user ID |

### Main Menu Buttons

| Button | Function |
|--------|----------|
| 📝 **Buat Naskah** | Generate AI video script (interactive - bot will ask for duration and topic) |
| 🖼️ **Generate Images (AI)** | Auto-generate images for all scenes using `ag/gemini-3.1-flash-image` |
| 🎬 **Buat Video** | Assemble video from media files and upload |
| 📤 **Upload Settings** | Choose upload target: YouTube only, Facebook only, or Both |
| 📊 **Status** | View bot status and credentials |

---

## Usage Example

### Step 1 — Generate a script

1. Send `/start` to the bot
2. Click **📝 Buat Naskah**
3. Bot will ask: "Berapa menit durasi video?" → Reply with `2`
4. Bot will ask: "Kirim tema/topik video" → Reply with `the fall of the Roman Empire`

The bot will:
- Call the LLM to create a script with 20 scenes (10 scenes/minute)
- Save it to `proyek/<timestamp>/scenes.json`
- Create a media staging folder in `Downloads/ytbot-<timestamp>`
- Send each scene's narration and video prompt to the chat

### Step 2 — Generate images (AI) OR manual download

**Option A: Auto-generate with AI (Recommended)**

1. Click **🖼️ Generate Images (AI)**
2. Bot will generate images for all scenes automatically using `ag/gemini-3.1-flash-image`
3. Images saved to the media folder

**Option B: Manual download (for video clips)**

Use the video prompts from each scene with an AI video generator (e.g. Google Flow, Kling, Runway).

Place the generated clips (`.mp4`, `.mov`) or images (`.jpg`, `.png`) into the media folder shown by the bot:

```
/storage/emulated/0/Download/ytbot-20261021-004229
```

File order is determined by modification time, so download them in scene order.

### Step 3 — Assemble and upload

1. Click **🎬 Buat Video**
2. Confirm the project

The bot will:
- Generate TTS narration per scene (Indonesian voice: `id-ID-ArdiNeural`)
- Burn timed word-by-word subtitles onto each clip
- Encode all clips to 1080x1920 (9:16) H.264/AAC
- Concatenate into a single `video.mp4`
- Send the video via Telegram (if under 50 MB)
- Upload to YouTube and/or Facebook based on your **Upload Settings**

### Upload Settings

Click **📤 Upload Settings** to choose:
- **YouTube only** - Upload to YouTube as private
- **Facebook only** - Upload to your Facebook Page
- **Both** - Upload to both platforms simultaneously

---

## Project Structure

```
ytbot/
├── bot.py              # Telegram bot entry point (button-based UI)
├── buat.py             # Video assembly and encoding
├── yt.py               # YouTube upload via Data API v3
├── fb_auth.py          # Facebook authentication helper
├── ai_image.py         # AI image generation via ag/gemini-3.1-flash-image
├── login.py            # One-time Google OAuth2 login
├── requirements.txt    # Python dependencies
├── .env.example        # Environment variable template
├── .gitignore
└── proyek/             # Generated project folders (gitignored)
    └── <timestamp>/
        ├── scenes.json     # AI-generated script
        ├── media_dir.txt   # Path to the media staging folder
        ├── s01.mp3 ...     # TTS audio per scene
        ├── k01.mp4 ...     # Encoded clip per scene
        ├── list.txt        # FFmpeg concat list
        └── video.mp4       # Final output
```

---

## Notes

- Only one video assembly process can run at a time. The bot will reject concurrent requests.
- If the number of media files does not match the number of scenes, files are cycled or truncated by order.
- Videos over 50 MB are not sent via Telegram but are still uploaded to YouTube/Facebook. The file path is shown in chat.
- The LLM API endpoint is configured at `llm.albiontools.fun`. To use a different provider, change `LLM_BASE_URL` in `.env`.
- AI image generation uses `ag/gemini-3.1-flash-image` model via 9router.
- Facebook tokens are automatically refreshed when expired (requires `FACEBOOK_APP_ID` and `FACEBOOK_APP_SECRET`).

---

## New Features (v2.0)

✅ **Button-based UI** - No more typing commands, just click buttons!  
✅ **AI Image Generation** - Auto-generate images using `ag/gemini-3.1-flash-image`  
✅ **Facebook Upload** - Upload to Facebook Page in addition to YouTube  
✅ **Upload Settings** - Choose YouTube only, Facebook only, or both  
✅ **Interactive Flow** - Bot asks questions step-by-step for better UX  

---

## Migration from v1.x

Old commands still work for backwards compatibility:
- `/naskah 2 topic` → Still works, but use button menu for better experience
- `/buat timestamp` → Still works

New `.env` variables (add to your existing `.env`):
```
LLM_BASE_URL=https://llm.albiontools.fun/v1
UPLOAD_TARGET=youtube
FACEBOOK_PAGE_ID=
FACEBOOK_PAGE_ACCESS_TOKEN=
FACEBOOK_USER_ACCESS_TOKEN=
FACEBOOK_APP_ID=
FACEBOOK_APP_SECRET=
```
