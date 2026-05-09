"""Generate auto reaction commentary using Claude AI."""
import logging
import re
from dataclasses import dataclass

import anthropic

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config

logger = logging.getLogger(__name__)


@dataclass
class CommentaryBeat:
    timestamp: float    # seconds into the clip
    text: str           # commentary text
    emoji: str          # reaction emoji
    intensity: float    # 0.0-1.0 for overlay size/animation


class CommentaryGenerator:
    """Uses Claude to generate timed reaction commentary for a video clip."""

    _SYSTEM_PROMPT = (
        "You are an enthusiastic Roblox content reactor. "
        "Generate short, punchy reaction comments for a gameplay video. "
        "Keep each comment under 80 characters. Be energetic and fun. "
        "Use gaming slang appropriate for a Roblox audience."
    )

    _REACTION_MAP = {
        "funny": ("😂", 0.9),
        "epic": ("🔥", 1.0),
        "fail": ("💀", 0.85),
        "skill": ("⚡", 0.9),
        "surprise": ("😱", 0.95),
        "win": ("🏆", 1.0),
        "default": ("🎮", 0.7),
    }

    def __init__(self, api_key: str = config.ANTHROPIC_API_KEY):
        if not api_key:
            logger.warning(
                "ANTHROPIC_API_KEY not set — using fallback commentary."
            )
            self.client = None
        else:
            self.client = anthropic.Anthropic(api_key=api_key)

    def generate_for_clip(
        self,
        video_title: str,
        clip_duration: float,
        interval: int = config.COMMENTARY_INTERVAL,
    ) -> list[CommentaryBeat]:
        """Generate timed commentary beats for a clip.

        Args:
            video_title: Title of the Roblox video
            clip_duration: Duration of the clip in seconds
            interval: Seconds between each commentary beat

        Returns:
            List of CommentaryBeat objects timed throughout the clip
        """
        num_beats = max(1, int(clip_duration // interval))

        if self.client:
            return self._generate_ai_commentary(video_title, clip_duration, num_beats)
        return self._generate_fallback_commentary(clip_duration, num_beats)

    def _generate_ai_commentary(
        self, video_title: str, clip_duration: float, num_beats: int
    ) -> list[CommentaryBeat]:
        prompt = (
            f"I'm reacting to a Roblox video titled: '{video_title}'.\n"
            f"Generate {num_beats} reaction comments for a {clip_duration:.0f}s clip.\n"
            "Format each as: TIMESTAMP|REACTION_TYPE|COMMENT\n"
            "REACTION_TYPE must be one of: funny, epic, fail, skill, surprise, win, default\n"
            f"Timestamps should be spread evenly across 0-{clip_duration:.0f} seconds.\n"
            "Example: 15|epic|No way he pulled that off!!"
        )

        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=500,
                system=self._SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            return self._parse_ai_response(message.content[0].text, clip_duration)
        except Exception as e:
            logger.warning("Claude API error: %s — using fallback.", e)
            return self._generate_fallback_commentary(clip_duration, num_beats)

    def _parse_ai_response(
        self, response: str, clip_duration: float
    ) -> list[CommentaryBeat]:
        beats: list[CommentaryBeat] = []
        for line in response.strip().splitlines():
            line = line.strip()
            if not line or "|" not in line:
                continue
            parts = line.split("|", 2)
            if len(parts) < 3:
                continue
            try:
                ts_str = re.sub(r"[^\d.]", "", parts[0])
                timestamp = float(ts_str)
                if timestamp > clip_duration:
                    continue
                reaction_type = parts[1].strip().lower()
                text = parts[2].strip()[:config.MAX_COMMENTARY_LENGTH]
                emoji, intensity = self._REACTION_MAP.get(
                    reaction_type, self._REACTION_MAP["default"]
                )
                beats.append(
                    CommentaryBeat(
                        timestamp=timestamp,
                        text=text,
                        emoji=emoji,
                        intensity=intensity,
                    )
                )
            except (ValueError, IndexError):
                continue
        return beats

    def _generate_fallback_commentary(
        self, clip_duration: float, num_beats: int
    ) -> list[CommentaryBeat]:
        """Static fallback commentary when Claude API is unavailable."""
        fallbacks = [
            ("funny", "LOL this is too funny! 💀"),
            ("epic", "BRO HE DID NOT JUST DO THAT! 🔥"),
            ("skill", "Actually insane mechanics right here ⚡"),
            ("surprise", "WAIT WHAT?! 😱"),
            ("win", "W moment, absolute W 🏆"),
            ("fail", "Nah bro just got cooked 💀"),
            ("default", "Okay this game goes crazy tho 🎮"),
        ]
        interval = clip_duration / max(num_beats, 1)
        beats = []
        for i in range(num_beats):
            reaction_type, text = fallbacks[i % len(fallbacks)]
            emoji, intensity = self._REACTION_MAP[reaction_type]
            beats.append(
                CommentaryBeat(
                    timestamp=i * interval + interval * 0.5,
                    text=text,
                    emoji=emoji,
                    intensity=intensity,
                )
            )
        return beats
