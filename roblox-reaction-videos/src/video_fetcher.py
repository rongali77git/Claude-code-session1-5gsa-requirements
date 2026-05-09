"""Fetch top Roblox videos with Creative Commons license from YouTube."""
import logging
from dataclasses import dataclass
from typing import Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))
import config

logger = logging.getLogger(__name__)


@dataclass
class VideoInfo:
    video_id: str
    title: str
    channel_title: str
    view_count: int
    duration: str
    license: str
    description: str
    thumbnail_url: str

    @property
    def youtube_url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"

    @property
    def attribution(self) -> str:
        return f'"{self.title}" by {self.channel_title} (CC BY) - {self.youtube_url}'


class VideoFetcher:
    """Fetches top Roblox videos filtered to Creative Commons license only."""

    def __init__(self, api_key: str = config.YOUTUBE_API_KEY):
        if not api_key:
            raise ValueError(
                "YOUTUBE_API_KEY is required. Get one at "
                "https://console.developers.google.com/"
            )
        self.youtube = build("youtube", "v3", developerKey=api_key)

    def fetch_top_cc_videos(
        self,
        query: str = config.YOUTUBE_SEARCH_QUERY,
        max_results: int = config.YOUTUBE_MAX_RESULTS,
    ) -> list[VideoInfo]:
        """Search YouTube for top Roblox videos with Creative Commons license.

        Args:
            query: Search query (e.g. 'Roblox' or 'Roblox funny moments')
            max_results: Number of videos to return

        Returns:
            List of VideoInfo sorted by view count (highest first)
        """
        logger.info(
            "Searching YouTube for CC-licensed '%s' videos (top %d)",
            query,
            max_results,
        )
        try:
            search_response = (
                self.youtube.search()
                .list(
                    part="snippet",
                    q=query,
                    type="video",
                    videoLicense="creativeCommon",  # CC license ONLY
                    order=config.YOUTUBE_ORDER,
                    videoDuration=config.YOUTUBE_VIDEO_DURATION,
                    maxResults=max_results * 2,  # over-fetch; filter below
                    safeSearch="moderate",
                )
                .execute()
            )
        except HttpError as e:
            logger.error("YouTube search failed: %s", e)
            raise

        video_ids = [
            item["id"]["videoId"]
            for item in search_response.get("items", [])
        ]

        if not video_ids:
            logger.warning("No CC-licensed Roblox videos found.")
            return []

        return self._fetch_video_details(video_ids, max_results)

    def _fetch_video_details(
        self, video_ids: list[str], limit: int
    ) -> list[VideoInfo]:
        """Fetch full metadata and verify CC license for each video ID."""
        try:
            details_response = (
                self.youtube.videos()
                .list(
                    part="snippet,contentDetails,statistics,status",
                    id=",".join(video_ids),
                )
                .execute()
            )
        except HttpError as e:
            logger.error("YouTube video details fetch failed: %s", e)
            raise

        videos: list[VideoInfo] = []
        for item in details_response.get("items", []):
            # Double-check license is Creative Commons
            if item["status"].get("license") != "creativeCommon":
                logger.debug(
                    "Skipping %s: not CC licensed", item["id"]
                )
                continue

            snippet = item["snippet"]
            stats = item.get("statistics", {})
            thumbnails = snippet.get("thumbnails", {})
            thumbnail_url = (
                thumbnails.get("high", {}).get("url")
                or thumbnails.get("medium", {}).get("url")
                or ""
            )

            videos.append(
                VideoInfo(
                    video_id=item["id"],
                    title=snippet.get("title", "Unknown"),
                    channel_title=snippet.get("channelTitle", "Unknown"),
                    view_count=int(stats.get("viewCount", 0)),
                    duration=item["contentDetails"].get("duration", "PT0S"),
                    license="creativeCommon",
                    description=snippet.get("description", "")[:500],
                    thumbnail_url=thumbnail_url,
                )
            )

        videos.sort(key=lambda v: v.view_count, reverse=True)
        logger.info(
            "Found %d CC-licensed videos (returning top %d)",
            len(videos),
            limit,
        )
        return videos[:limit]
