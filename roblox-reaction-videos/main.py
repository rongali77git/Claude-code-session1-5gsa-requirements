#!/usr/bin/env python3
"""Roblox Auto Reaction Video Generator — entry point.

Usage:
    python main.py --help
    python main.py run --max-videos 5
    python main.py run --query "Roblox funny moments" --no-ai
"""
import logging
from pathlib import Path

import click

from src.utils import setup_logging
import config

logger = logging.getLogger(__name__)


@click.group()
@click.option("--log-level", default="INFO", help="Logging level (DEBUG/INFO/WARNING)")
def cli(log_level: str):
    """Roblox Auto Reaction Video Generator.

    Only processes Creative Commons (CC BY) licensed Roblox videos
    to ensure full copyright compliance.
    """
    setup_logging(log_level)


@cli.command()
@click.option("--query", default=config.YOUTUBE_SEARCH_QUERY, show_default=True,
              help="YouTube search query for Roblox videos")
@click.option("--max-videos", default=3, show_default=True,
              help="Number of reaction videos to produce")
@click.option("--clip-duration", default=config.CLIP_DURATION, show_default=True,
              help="Length of each clip in seconds")
@click.option("--no-ai", is_flag=True, default=False,
              help="Disable Claude AI commentary (use fallback text)")
@click.option("--output-dir", default=str(config.OUTPUT_DIR), show_default=True,
              help="Directory to save output videos")
def run(
    query: str,
    max_videos: int,
    clip_duration: int,
    no_ai: bool,
    output_dir: str,
):
    """Fetch top CC-licensed Roblox videos and generate reaction videos."""
    from src.video_fetcher import VideoFetcher
    from src.video_downloader import VideoDownloader
    from src.commentary_generator import CommentaryGenerator
    from src.reaction_composer import ReactionComposer

    if no_ai:
        config.ENABLE_AI_COMMENTARY = False

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    click.echo(click.style("\n=== Roblox Auto Reaction Video Generator ===", fg="red", bold=True))
    click.echo(f"Query          : {query}")
    click.echo(f"Max videos     : {max_videos}")
    click.echo(f"Clip duration  : {clip_duration}s")
    click.echo(f"AI commentary  : {'disabled' if no_ai else 'enabled'}")
    click.echo(f"License filter : Creative Commons (CC BY) ONLY")
    click.echo(f"Output dir     : {output_path}\n")

    # 1. Fetch top CC-licensed videos
    click.echo("[1/4] Searching YouTube for CC-licensed Roblox videos...")
    try:
        fetcher = VideoFetcher()
        videos = fetcher.fetch_top_cc_videos(query=query, max_results=max_videos)
    except Exception as e:
        click.echo(click.style(f"ERROR: {e}", fg="red"))
        raise SystemExit(1)

    if not videos:
        click.echo(click.style(
            "No Creative Commons Roblox videos found. Try a different query.",
            fg="yellow",
        ))
        raise SystemExit(0)

    click.echo(f"Found {len(videos)} CC-licensed video(s):\n")
    for i, v in enumerate(videos, 1):
        from src.utils import format_views
        click.echo(f"  {i}. {v.title[:60]} ({format_views(v.view_count)} views)")
        click.echo(f"     by {v.channel_title} | {v.youtube_url}")
    click.echo()

    # 2. Download clips
    click.echo("[2/4] Downloading clips...")
    downloader = VideoDownloader(clip_duration=clip_duration)
    downloaded = downloader.download_batch(videos)

    if not downloaded:
        click.echo(click.style("No clips downloaded successfully.", fg="red"))
        raise SystemExit(1)

    # 3. Generate commentary
    click.echo("[3/4] Generating AI commentary...")
    generator = CommentaryGenerator() if config.ENABLE_AI_COMMENTARY else CommentaryGenerator(api_key="")

    # 4. Compose reaction videos
    click.echo("[4/4] Composing reaction videos...")
    composer = ReactionComposer()
    output_files: list[Path] = []

    for video, clip_path in downloaded:
        click.echo(f"\n  Composing: {video.title[:60]}")
        beats = generator.generate_for_clip(
            video_title=video.title,
            clip_duration=float(clip_duration),
        )
        try:
            out = composer.compose(
                video=video,
                clip_path=clip_path,
                beats=beats,
                output_dir=output_path,
            )
            output_files.append(out)
            click.echo(click.style(f"  ✓ Saved: {out.name}", fg="green"))
        except Exception as e:
            click.echo(click.style(f"  ✗ Failed: {e}", fg="red"))
            logger.exception("Composition failed for %s", video.video_id)

    # Summary
    click.echo(click.style(f"\n=== Done! {len(output_files)}/{len(downloaded)} videos created ===", fg="green", bold=True))
    for f in output_files:
        click.echo(f"  {f}")

    click.echo(click.style(
        "\nAll content is Creative Commons licensed. "
        "Credit original creators in your video description!",
        fg="cyan",
    ))


@cli.command()
@click.option("--query", default=config.YOUTUBE_SEARCH_QUERY)
@click.option("--max-results", default=10)
def search(query: str, max_results: int):
    """Search and list top CC-licensed Roblox videos (no download)."""
    from src.video_fetcher import VideoFetcher
    from src.utils import format_views

    setup_logging("INFO")
    fetcher = VideoFetcher()
    videos = fetcher.fetch_top_cc_videos(query=query, max_results=max_results)

    click.echo(click.style(
        f"\nTop {len(videos)} CC-Licensed Roblox Videos", bold=True
    ))
    click.echo("=" * 60)
    for i, v in enumerate(videos, 1):
        click.echo(f"\n{i}. {v.title}")
        click.echo(f"   Channel  : {v.channel_title}")
        click.echo(f"   Views    : {format_views(v.view_count)}")
        click.echo(f"   License  : CC BY (Creative Commons)")
        click.echo(f"   URL      : {v.youtube_url}")
        click.echo(f"   Credit   : {v.attribution}")


if __name__ == "__main__":
    cli()
