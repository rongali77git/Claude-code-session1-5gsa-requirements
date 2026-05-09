"""Download Creative Commons Roblox video clips using yt-dlp."""
import logging
import subprocess
from pathlib import Path

from tqdm import tqdm

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from src.video_fetcher import VideoInfo

logger = logging.getLogger(__name__)


class VideoDownloader:
    """Downloads a short clip from a CC-licensed YouTube video."""

    def __init__(
        self,
        output_dir: Path = config.CLIPS_DIR,
        start_offset: int = config.CLIP_START_OFFSET,
        clip_duration: int = config.CLIP_DURATION,
    ):
        self.output_dir = output_dir
        self.start_offset = start_offset
        self.clip_duration = clip_duration

    def download_clip(self, video: VideoInfo) -> Path | None:
        """Download a clip from a CC-licensed video.

        Uses yt-dlp's --download-sections to grab only the needed portion,
        avoiding full-video downloads and reducing storage/bandwidth.

        Args:
            video: Verified CC-licensed VideoInfo object

        Returns:
            Path to downloaded clip file, or None on failure
        """
        out_path = self.output_dir / f"{video.video_id}.mp4"

        if out_path.exists():
            logger.info("Clip already downloaded: %s", out_path)
            return out_path

        start = self.start_offset
        end = start + self.clip_duration
        section_arg = f"*{start}-{end}"  # yt-dlp section syntax

        cmd = [
            "yt-dlp",
            "--format", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]",
            "--merge-output-format", "mp4",
            "--download-sections", section_arg,
            "--force-keyframes-at-cuts",
            "--no-playlist",
            "--quiet",
            "--no-warnings",
            "--output", str(out_path),
            video.youtube_url,
        ]

        logger.info(
            "Downloading clip %ds-%ds from '%s' (%s)",
            start,
            end,
            video.title,
            video.video_id,
        )
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode != 0:
                logger.error(
                    "yt-dlp failed for %s:\n%s",
                    video.video_id,
                    result.stderr,
                )
                return None
        except subprocess.TimeoutExpired:
            logger.error("Download timed out for %s", video.video_id)
            return None
        except FileNotFoundError:
            logger.error(
                "yt-dlp not found. Install with: pip install yt-dlp"
            )
            raise

        if not out_path.exists():
            logger.error("Download completed but file missing: %s", out_path)
            return None

        logger.info("Clip saved: %s (%.1f MB)", out_path, out_path.stat().st_size / 1e6)
        return out_path

    def download_batch(
        self, videos: list[VideoInfo]
    ) -> list[tuple[VideoInfo, Path]]:
        """Download clips for multiple videos with progress tracking."""
        results: list[tuple[VideoInfo, Path]] = []
        for video in tqdm(videos, desc="Downloading clips", unit="video"):
            clip_path = self.download_clip(video)
            if clip_path:
                results.append((video, clip_path))
        return results
