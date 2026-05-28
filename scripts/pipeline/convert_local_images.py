#!/usr/bin/env python3
"""
Local Image Converter.

Converts all existing .jpg images in scripts/data/images/ to .webp format.
Multithreaded (32 workers), with checkpoint resume and progress bars.

Usage:
    # Convert all images:
    uv run python convert_local_images.py

    # Dry run (list files that would be converted):
    uv run python convert_local_images.py --dry-run

    # Limit to first N files (for testing):
    uv run python convert_local_images.py --limit 100
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TransferSpeedColumn,
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import IMAGES_DIR  # type: ignore[import-not-found]

console = Console()
logger = logging.getLogger("convert")

# Checkpoint file for resume capability
CHECKPOINT_FILE = os.path.join(os.path.dirname(IMAGES_DIR), "convert_checkpoint.json")


def load_checkpoint() -> set[str]:
    """Load set of already-converted file paths from checkpoint."""
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, encoding="utf-8") as f:
            data = json.load(f)
            return set(data.get("converted", []))
    return set()


def save_checkpoint(converted: set[str]) -> None:
    """Save checkpoint of converted files."""
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump({"converted": list(converted)}, f, indent=2)


def find_jpg_files(images_dir: str) -> list[Path]:
    """Find all .jpg files in the images directory."""
    jpg_files = []
    for root, _dirs, files in os.walk(images_dir):
        for filename in files:
            if filename.lower().endswith((".jpg", ".jpeg")):
                jpg_files.append(Path(root) / filename)
    return jpg_files


def convert_to_webp(jpg_path: Path) -> tuple[str, bool, str]:
    """Convert a single JPG to WebP. Returns (path, success, error_msg)."""
    webp_path = jpg_path.with_suffix(".webp")

    try:
        with Image.open(jpg_path) as img:
            # Convert RGBA/P to RGB for WebP lossy
            if img.mode in ("RGBA", "P"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[3])
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

            jpg_size = jpg_path.stat().st_size
            img.save(webp_path, "WEBP", quality=85, method=6)
            webp_size = webp_path.stat().st_size

            # Delete original JPG
            jpg_path.unlink()

            reduction = (1 - webp_size / jpg_size) * 100 if jpg_size > 0 else 0
            return (str(jpg_path), True, f"{reduction:+.1f}%")

    except Exception as e:
        # Clean up partial WebP if it exists
        if webp_path.exists():
            webp_path.unlink()
        return (str(jpg_path), False, str(e))


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert local JPG images to WebP")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files that would be converted without actually converting",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit to first N files (for testing)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=32,
        help="Number of parallel workers (default: 32)",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore checkpoint and convert all files",
    )

    args = parser.parse_args()

    console.print("\n[bold cyan]\u2554═══════════════════════════════════════\u2557[/bold cyan]")
    console.print("[bold cyan]\u2551  Local Image Converter (JPG -> WebP) \u2551[/bold cyan]")
    console.print("[bold cyan]\u255a═══════════════════════════════════════\u255d[/bold cyan]\n")

    # Setup logging
    log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"convert_{time.strftime('%Y%m%d_%H%M%S')}.log")
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    console.print(f"  Images dir: [cyan]{IMAGES_DIR}[/cyan]")
    console.print(f"  Log file: [cyan]{log_file}[/cyan]\n")

    # Find all JPG files
    console.print("[bold]Scanning for JPG files...[/bold]")
    jpg_files = find_jpg_files(IMAGES_DIR)
    console.print(f"  Found: [cyan]{len(jpg_files):,}[/cyan] JPG files\n")

    if not jpg_files:
        console.print("[bold green]No JPG files found. Nothing to do.[/bold green]")
        return

    # Load checkpoint (skip already converted)
    if not args.no_resume:
        converted = load_checkpoint()
        jpg_files = [f for f in jpg_files if str(f) not in converted]
        if converted:
            console.print(
                f"  Resuming: [green]{len(converted):,}[/green] already converted (skipped)\n"
            )

    # Apply limit
    if args.limit:
        jpg_files = jpg_files[: args.limit]
        console.print(f"  Limit: [yellow]{args.limit}[/yellow] files\n")

    # Calculate total size
    total_size = sum(f.stat().st_size for f in jpg_files if f.exists())
    total_size_gb = total_size / (1024**3)
    console.print(f"  Total size: [cyan]{total_size_gb:.2f} GB[/cyan]\n")

    if args.dry_run:
        console.print("[bold yellow]=== DRY RUN ===[/bold yellow]")
        console.print(f"\n  Would convert {len(jpg_files):,} files:")
        for f in jpg_files[:20]:
            size_mb = f.stat().st_size / (1024**2) if f.exists() else 0
            console.print(f"    {f.name} ({size_mb:.2f} MB)")
        if len(jpg_files) > 20:
            console.print(f"    ... and {len(jpg_files) - 20:,} more")
        return

    # Convert
    console.print(
        f"\n[bold]Converting {len(jpg_files):,} files with {args.workers} workers...[/bold]\n"
    )
    start_time = time.time()

    converted_set = load_checkpoint() if not args.no_resume else set()
    total_converted = len(converted_set)
    total_failed = 0
    total_saved_bytes = 0

    with Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("\u2022"),
        TransferSpeedColumn(),
        TextColumn("\u2022"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Converting", total=len(jpg_files))

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(convert_to_webp, jpg_path): jpg_path for jpg_path in jpg_files
            }

            for future in as_completed(futures):
                jpg_path = futures[future]
                try:
                    path, success, message = future.result()
                    if success:
                        converted_set.add(path)
                        total_converted += 1

                        # Track conversion (JPG is deleted after conversion)
                        # Message contains reduction percentage like "-45.2%"

                        # Save checkpoint periodically
                        if total_converted % 1000 == 0:
                            save_checkpoint(converted_set)
                    else:
                        total_failed += 1
                        logger.error(f"Failed to convert {path}: {message}")

                except Exception as e:
                    total_failed += 1
                    logger.error(f"Unexpected error for {jpg_path}: {e}")

                progress.update(task, completed=total_converted + total_failed)

    elapsed = time.time() - start_time

    # Save final checkpoint
    save_checkpoint(converted_set)

    # Summary
    console.print("\n[bold green]\u2554═══════════════════════════════════════\u2557[/bold green]")
    console.print("[bold green]\u2551  Conversion Complete!                \u2551[/bold green]")
    console.print("[bold green]\u255a═══════════════════════════════════════\u255d[/bold green]")
    console.print(f"  Converted: [green]{total_converted:,}[/green]")
    console.print(f"  Failed: [red]{total_failed:,}[/red]")
    console.print(f"  Time: [cyan]{elapsed:.1f}s[/cyan]")

    if elapsed > 0:
        rate = total_converted / elapsed
        console.print(f"  Rate: [cyan]{rate:.0f} files/s[/cyan]")

    logger.info(
        f"Conversion complete: converted={total_converted}, "
        f"failed={total_failed}, time={elapsed:.1f}s"
    )


if __name__ == "__main__":
    main()
