# ytbot

A Telegram bot that runs on Android (Termux) to automate AI short-video creation and YouTube uploads.

**Workflow:**
1. Send `/naskah` to generate an AI script (narration + video prompts per scene)
2. Generate AI video clips from the prompts using a tool like Google Flow
3. Place the clips in the media folder the bot created
4. Send `/buat` to assemble the final video with TTS narration, subtitles, and upload to YouTube

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
ALLOWED_ID=       # Your Telegram user ID (see below)
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

| Command | Description |
|---------|-------------|
| `/start` | Show available commands |
| `/id` | Show your Telegram user ID |
| `/naskah <minutes 1-3> <topic>` | Generate an AI video script |
| `/buat <project-timestamp>` | Assemble video from media files and upload to YouTube |

---

## Usage Example

### Step 1 — Generate a script

```
/naskah 2 the fall of the Roman Empire
```

The bot will:
- Call the LLM to create a script with 20 scenes (10 scenes/minute)
- Save it to `proyek/<timestamp>/scenes.json`
- Create a media staging folder in `Downloads/ytbot-<timestamp>`
- Send each scene's narration and video prompt to the chat

### Step 2 — Generate video clips

Use the video prompts from each scene with an AI video generator (e.g. Google Flow, Kling, Runway).

Place the generated clips (`.mp4`, `.mov`) or images (`.jpg`, `.png`) into the media folder shown by the bot:

```
/storage/emulated/0/Download/ytbot-20261021-004229
```

File order is determined by modification time, so download them in scene order.

### Step 3 — Assemble and upload

```
/buat 20261021-004229
```

The bot will:
- Generate TTS narration per scene (Indonesian voice: `id-ID-ArdiNeural`)
- Burn timed word-by-word subtitles onto each clip
- Encode all clips to 1080x1920 (9:16) H.264/AAC
- Concatenate into a single `video.mp4`
- Send the video via Telegram (if under 50 MB)
- Upload to YouTube as **private**

---

## Project Structure

```
ytbot/
├── bot.py              # Telegram bot entry point
├── buat.py             # Video assembly and encoding
├── yt.py               # YouTube upload via Data API v3
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

- Only one `/buat` process can run at a time. The bot will reject concurrent requests.
- If the number of media files does not match the number of scenes, files are cycled or truncated by order.
- Videos over 50 MB are not sent via Telegram but are still uploaded to YouTube. The file path is shown in chat.
- The LLM API endpoint is configured at `llm.albiontools.fun`. To use a different provider, change the `URL` constant in `bot.py`.
