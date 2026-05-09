# Roblox Auto Reaction Video Generator

Automatically creates reaction-style videos on top Roblox content — **only using Creative Commons (CC BY) licensed videos** to ensure full copyright compliance.

## How It Works

```
┌─────────────────────────────────────────────────────┐
│  🎮 REACTING TO: Top Roblox Moments #42             │
├────────────────────────────┬────────────────────────┤
│                            │   📹 LIVE               │
│   ROBLOX CC VIDEO CLIP     │   REACTION CAM          │
│         (68%)              │       (32%)             │
│                            │                         │
│  😱 OMG HE DID NOT DO THAT!│  🔥😂⚡ 👏💀🎮         │
├────────────────────────────┴────────────────────────┤
│  ▶ ━━━━━━━━━━━━━━━━━━  0:42/1:30  CC BY Licensed    │
└─────────────────────────────────────────────────────┘
```

## Copyright Safety

| Feature | Detail |
|---|---|
| **License filter** | Only CC BY (Creative Commons Attribution) videos |
| **API verification** | Double-checks license on every video via YouTube Data API |
| **Clip only** | Downloads a 90-second clip, not the full video |
| **Attribution** | Original creator credited in video and description |
| **Transformative** | Reaction format adds commentary, layout, and new content |

> **Note**: Creative Commons Attribution (CC BY) allows you to share and adapt
> the material for any purpose, including commercially, as long as you credit
> the original creator. This tool embeds the credit automatically.

## Installation

```bash
# 1. Clone and enter directory
git clone <repo-url>
cd roblox-reaction-videos

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure API keys
cp .env.example .env
# Edit .env and add your YouTube API key (and optionally Anthropic key)
```

### Getting API Keys

- **YouTube Data API v3** (required): [console.developers.google.com](https://console.developers.google.com) → Create Project → Enable YouTube Data API v3 → Credentials → API Key
- **Anthropic Claude API** (optional, for AI commentary): [console.anthropic.com](https://console.anthropic.com) — if omitted, fallback commentary is used

## Usage

```bash
# Search CC-licensed Roblox videos (preview mode, no download)
python main.py search --query "Roblox" --max-results 10

# Generate 3 reaction videos from top CC Roblox content
python main.py run --max-videos 3

# Custom query, longer clips, no AI
python main.py run --query "Roblox funny moments" --max-videos 5 --clip-duration 120 --no-ai

# Full help
python main.py --help
python main.py run --help
```

## Output

Each reaction video includes:
- **1920×1080** output at 30 FPS
- Split-screen: game footage (left) + reaction panel (right)
- Auto-generated AI commentary bubbles timed throughout the clip
- Attribution overlay with original creator credit
- CC BY license disclaimer in footer

Files are saved to `output/` as `roblox_reaction_{video_id}_{timestamp}.mp4`.

## Project Structure

```
roblox-reaction-videos/
├── main.py                  # CLI entry point
├── config.py                # All configuration constants
├── requirements.txt
├── .env.example             # API key template
└── src/
    ├── video_fetcher.py     # YouTube API — finds CC videos
    ├── video_downloader.py  # yt-dlp clip downloader
    ├── commentary_generator.py  # Claude AI reaction commentary
    ├── reaction_composer.py     # MoviePy video composition
    └── utils.py             # Shared utilities
```

## Video Description Template

When uploading, use this description to satisfy CC BY attribution:

```
Reacting to top Roblox content!

--- Original Content Attribution (CC BY) ---
"[Video Title]" by [Channel Name]
https://youtube.com/watch?v=[VIDEO_ID]
Licensed under Creative Commons Attribution (CC BY)

[Repeat for each clip used]

All gameplay footage in this video is licensed under Creative Commons Attribution.
Reaction commentary, editing, and presentation are original content.
```
