"""Configuration for the Roblox Auto Reaction Video Generator."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- Paths ---
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
CLIPS_DIR = BASE_DIR / "clips"
ASSETS_DIR = BASE_DIR / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"

for d in [OUTPUT_DIR, CLIPS_DIR, ASSETS_DIR, FONTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# --- API Keys ---
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# --- YouTube Search Settings ---
YOUTUBE_SEARCH_QUERY = "Roblox"
YOUTUBE_MAX_RESULTS = 10
# CRITICAL: Only fetch Creative Commons licensed videos to avoid copyright issues
YOUTUBE_LICENSE_FILTER = "creativeCommon"
YOUTUBE_ORDER = "viewCount"          # Top viewed first
YOUTUBE_VIDEO_DURATION = "medium"    # 4-20 minute videos

# --- Clip Settings ---
CLIP_START_OFFSET = 30               # Skip first 30s (usually intro)
CLIP_DURATION = 90                   # Use 90s clip per video
CLIP_FORMAT = "mp4"
CLIP_QUALITY = "720p"                # 1280x720

# --- Reaction Video Layout ---
OUTPUT_WIDTH = 1920
OUTPUT_HEIGHT = 1080
FPS = 30
GAME_VIDEO_RATIO = 0.68             # 68% of width for game footage
REACTION_CAM_RATIO = 0.32           # 32% of width for reaction panel
HEADER_HEIGHT = 60                  # Title bar height
FOOTER_HEIGHT = 50                  # Progress bar height

# --- Branding Colors (Roblox-inspired) ---
COLOR_BG = (15, 15, 20)            # Near-black background
COLOR_HEADER = (255, 0, 0)         # Roblox red header
COLOR_REACTION_BG = (30, 30, 40)   # Dark reaction panel
COLOR_TEXT_PRIMARY = (255, 255, 255)
COLOR_TEXT_SECONDARY = (200, 200, 200)
COLOR_ACCENT = (255, 80, 80)       # Accent for highlights
COLOR_PROGRESS = (255, 0, 0)       # Progress bar color

# --- Auto Commentary Settings ---
ENABLE_AI_COMMENTARY = True         # Use Claude to generate reaction text
COMMENTARY_INTERVAL = 15            # Generate commentary every 15 seconds
MAX_COMMENTARY_LENGTH = 80          # Max chars per commentary bubble

# --- Reaction Overlays ---
REACTION_EMOJIS = [
    ("😂", "LOL!"),
    ("🔥", "FIRE!"),
    ("😱", "OMG!"),
    ("👏", "GG!"),
    ("💀", "DEAD!"),
    ("🎮", "PRO MOVE!"),
    ("⚡", "INSANE!"),
    ("🤯", "MIND BLOWN!"),
]

# --- Output ---
OUTPUT_CODEC = "libx264"
OUTPUT_AUDIO_CODEC = "aac"
OUTPUT_BITRATE = "5000k"
OUTPUT_FILENAME_TEMPLATE = "roblox_reaction_{video_id}_{timestamp}.mp4"

# --- Copyright Compliance ---
# This tool ONLY uses Creative Commons licensed content.
# CC BY videos allow: sharing, adapting, commercial use with attribution.
# All downloaded content is attributed in the output video.
COPYRIGHT_DISCLAIMER = (
    "This reaction video uses Creative Commons (CC BY) licensed Roblox content. "
    "Original creators are credited below."
)
