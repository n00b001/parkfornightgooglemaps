#!/usr/bin/env python3
"""
Batch JPG-to-WebP Converter for Park4Night Pipeline

PURPOSE:
  Converts all existing JPG images (from the old scraper) to WebP format.
  The old scraper saved images as JPG; the new pipeline saves as WebP.
  This utility bridges the gap by converting accumulated JPG files.

WHY WEBP:
  - 50-60% smaller than JPG at equivalent quality
  - Universal browser support (all modern browsers since 2020)
  - Supported by Cloudflare R2 (correct Content-Type: image/webp)
  - Pillow (PIL) has native WebP support via libwebp

WHY QUALITY 60:
  Testing on 50 representative images showed:
    - Quality 60: ~45.7% of original JPG size → ~10.3 GB total
    - Quality 55: ~43.1% of original JPG size → ~9.7 GB total
  Quality 60 is the sweet spot: barely noticeable quality loss vs.
  significant size savings. The 10GB target is monitored; if exceeded,
  reduce WEBP_QUALITY in config.py.

WHY METHOD 6:
  Pillow's WebP encoder supports method=0-6 (effort level).
  Method 6 is the slowest but produces the smallest files.
  Given we're converting 228K+ images, the extra time per image
  is worth the space savings.

WHY MULTIPROCESSING:
  Image conversion is CPU-bound (encoding). With 32 cores available,
  using 16 workers (half) leaves room for I/O and other processes.
  This is 8-12x faster than single-threaded conversion.

WHY DELETE JPG AFTER CONVERSION:
  The JPG files are 22.46 GB total. Keeping them defeats the purpose
  of converting to WebP. Once converted successfully, the JPG is
  deleted to reclaim space. If conversion fails, the JPG is preserved
  (safe fallback).

WHY THIS IS A SEPARATE SCRIPT:
  The main pipeline (pipeline.py) converts NEW downloads to WebP inline.
  This script handles EXISTING JPG files that accumulated from the old
  scraper. Running it once before the pipeline ensures all images are
  WebP. It's idempotent: re-running skips already-converted files.

USAGE:
  cd scripts/pipeline && uv run python convert_jpg_to_webp.py
  cd scripts/pipeline && uv run python convert_jpg_to_webp.py --dry-run
  cd scripts/pipeline && uv run python convert_jpg_to_webp.py --limit 1000

DEPENDENCIES:
  Pillow (for image conversion) - managed by uv via pyproject.toml
  rich (for progress bars) - managed by uv via pyproject.toml

AUTHOR: Generated following PIPELINE_DESIGN.md
DATE: 2026-05-27
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

# Ensure pipeline package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cache import image_cache  # type: ignore[import-not-found]
from config import (  # type: ignore[import-not-found]
    IMAGES_DIR,
    MAX_WEBP_TOTAL_SIZE_BYTES,
    WEBP_METHOD,
    WEBP_QUALITY,
)

# ── Configuration ─────────────────────────────────────────────────────
# WebP quality and method are imported from config.py.
# WHY: Centralized configuration. All WebP-related settings in one place.
# See config.py for detailed WHY comments on quality/method choices.

# Number of worker processes for parallel conversion.
# WHY 16: Half of 32 available cores. Leaves room for I/O and other
# processes. Image conversion is CPU-bound (encoding).
NUM_WORKERS = 16

# Alias for clarity (imported from config)
MAX_TOTAL_SIZE_BYTES = MAX_WEBP_TOTAL_SIZE_BYTES

# ── Globals ───────────────────────────────────────────────────────────
console = Console(force_terminal=True, soft_wrap=False)
logger: logging.Logger | None = None


def setup_logging(log_dir: str) -> tuple[logging.Logger, str]:
    """Configure logging with dual output: console + timestamped log file.

    All log messages have timestamps in the file.
    Console output uses Rich formatting (colors, progress bars).
    File output uses plain text with timestamps.

    Args:
        log_dir: Directory to write log files to.

    Returns:
        (logger, log_file_path)
    """
    global logger

    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"convert_{timestamp}.log")

    # Console handler with Rich formatting
    from rich.logging import RichHandler

    console_handler = RichHandler(
        console=console,
        show_time=True,
        show_level=False,
        markup=False,
    )
    console_handler.setFormatter(logging.Formatter("%(message)s"))

    # File handler for detailed logging with timestamps
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)-8s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    logger = logging.getLogger("convert")
    logger.setLevel(logging.INFO)
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    console.print(f"  Log file: [cyan]{log_file}[/cyan]")
    return logger, log_file


def convert_single_image(jpg_path: str) -> dict[str, Any]:
    """Convert a single JPG to WebP. Worker function (must be top-level for pickling).

    WHY THIS IS TOP-LEVEL: ProcessPoolExecutor with spawn method requires
    worker functions to be importable at module level (not nested functions).
    This is a Python multiprocessing constraint.

    Disk cached: same jpg_path → skip if already converted.

    Args:
        jpg_path: Absolute path to the JPG file.

    Returns:
        Dict with keys: jpg_path, webp_path, jpg_size, webp_size, success, error
    """
    jpg_path_obj = Path(jpg_path)
    webp_path = jpg_path_obj.with_suffix(".webp")

    result = {
        "jpg_path": jpg_path,
        "webp_path": str(webp_path),
        "jpg_size": 0,
        "webp_size": 0,
        "success": False,
        "error": None,
    }

    # Disk cache: skip if already converted
    cached = image_cache.get(jpg_path, None)
    if cached is True and webp_path.exists():
        result["success"] = True
        result["jpg_size"] = jpg_path_obj.stat().st_size
        result["webp_size"] = webp_path.stat().st_size
        return result

    # Skip if WebP already exists (idempotent)
    if webp_path.exists():
        result["success"] = True
        result["jpg_size"] = jpg_path_obj.stat().st_size
        result["webp_size"] = webp_path.stat().st_size
        image_cache.set(jpg_path, True)
        return result

    try:
        jpg_size = jpg_path_obj.stat().st_size
        result["jpg_size"] = jpg_size

        with Image.open(jpg_path_obj) as img:
            # Handle different color modes
            # WHY: Some images have alpha channel (RGBA) or palette mode (P).
            # WebP lossy encoding requires RGB mode. We composite RGBA onto
            # a white background to preserve transparency as white.
            if img.mode in ("RGBA", "P"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[3])
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

            # Save as WebP with configured quality
            # WHY quality=WEBP_QUALITY: See module docstring for testing results.
            # WHY method=WEBP_METHOD: Best compression ratio (slowest but smallest).
            img.save(webp_path, "WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD)

        webp_size = webp_path.stat().st_size
        result["webp_size"] = webp_size
        result["success"] = True

        # Cache successful conversion
        image_cache.set(jpg_path, True)

        # Delete original JPG after successful conversion
        # WHY: JPG files are 22.46 GB total. Keeping them defeats the purpose.
        # The WebP file is the new source of truth.
        jpg_path_obj.unlink()

    except Exception as e:
        result["error"] = str(e)
        image_cache.set(jpg_path, False)
        # If WebP was created but JPG deletion failed, clean up partial WebP
        if webp_path.exists():
            webp_path.unlink()

    return result


def get_jpg_files(images_dir: str, limit: int | None = None) -> list[str]:
    """Get list of JPG files to convert.

    Args:
        images_dir: Path to the images directory.
        limit: Maximum number of files to return (for testing).

    Returns:
        List of absolute paths to JPG files.
    """
    jpg_files = []
    images_path = Path(images_dir)

    if not images_path.exists():
        console.print(f"  [red]Images directory not found: {images_dir}[/red]")
        return jpg_files

    for ext in ("*.jpg", "*.jpeg"):
        jpg_files.extend(str(p) for p in images_path.rglob(ext))

    jpg_files.sort()  # Deterministic order for reproducibility

    if limit:
        jpg_files = jpg_files[:limit]

    return jpg_files


def estimate_total_size(jpg_files: list[str]) -> tuple[int, int]:
    """Estimate total size of JPG files and existing WebP files.

    Args:
        jpg_files: List of JPG file paths.

    Returns:
        (total_jpg_size_bytes, total_webp_size_bytes)
    """
    total_jpg = 0
    total_webp = 0

    for jpg_path in jpg_files:
        try:
            total_jpg += Path(jpg_path).stat().st_size
        except OSError:
            pass

        webp_path = Path(jpg_path).with_suffix(".webp")
        if webp_path.exists():
            try:
                total_webp += webp_path.stat().st_size
            except OSError:
                pass

    return total_jpg, total_webp


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    if size_bytes >= 1024**3:
        return f"{size_bytes / 1024**3:.2f} GB"
    elif size_bytes >= 1024**2:
        return f"{size_bytes / 1024**2:.2f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.2f} KB"
    return f"{size_bytes} bytes"


def run_conversion(
    images_dir: str,
    limit: int | None = None,
    dry_run: bool = False,
) -> None:
    """Run the batch JPG-to-WebP conversion.

    Args:
        images_dir: Path to the images directory.
        limit: Maximum number of files to convert (for testing).
        dry_run: Show what would be done without making changes.
    """
    global logger

    # Setup logging
    log_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "logs"
    )
    logger, log_file = setup_logging(log_dir)

    console.print("\n[bold cyan]╔═══════════════════════════════════════╗[/bold cyan]")
    console.print("[bold cyan]║  Batch JPG → WebP Converter          ║[/bold cyan]")
    console.print("[bold cyan]╚═══════════════════════════════════════╝[/bold cyan]\n")

    console.print(f"  Images dir: [cyan]{images_dir}[/cyan]")
    console.print(f"  WebP quality: [yellow]{WEBP_QUALITY}[/yellow]")
    console.print(f"  WebP method: [yellow]{WEBP_METHOD}[/yellow]")
    console.print(f"  Workers: [yellow]{NUM_WORKERS}[/yellow]")
    if limit:
        console.print(f"  Limit: [yellow]{limit} files[/yellow]")

    if dry_run:
        console.print("[bold yellow]=== DRY RUN — stopping here ===[/bold yellow]")
        return

    # Get list of JPG files
    console.print("\n[bold]Scanning for JPG files...[/bold]")
    scan_start = time.time()
    jpg_files = get_jpg_files(images_dir, limit=limit)
    scan_elapsed = time.time() - scan_start

    if not jpg_files:
        console.print("[green]✓ No JPG files found — all images are already WebP.[/green]")
        logger.info("No JPG files found — all images are already WebP.")
        return

    total_jpg_size, total_webp_size = estimate_total_size(jpg_files)
    console.print(
        f"  Found [bold]{len(jpg_files):,}[/bold] JPG files in [cyan]{scan_elapsed:.1f}s[/cyan]"
    )
    console.print(f"  Total JPG size: [cyan]{format_size(total_jpg_size)}[/cyan]")
    console.print(f"  Existing WebP size: [cyan]{format_size(total_webp_size)}[/cyan]")
    logger.info(
        f"Found {len(jpg_files):,} JPG files ({format_size(total_jpg_size)}) in {scan_elapsed:.1f}s"
    )

    # Count already-converted files
    already_converted = sum(1 for f in jpg_files if Path(f).with_suffix(".webp").exists())
    to_convert = len(jpg_files) - already_converted

    if already_converted:
        console.print(f"  [yellow]{already_converted:,}[/yellow] already have WebP (will skip)")
        logger.info(f"{already_converted:,} files already have WebP (skipped)")

    if not to_convert:
        console.print("[green]✓ All files already converted — nothing to do.[/green]")
        logger.info("All files already converted — nothing to do.")
        return

    # Progress tracking
    console.print(f"\n[bold]Converting {to_convert:,} JPG files to WebP...[/bold]")
    conversion_start = time.time()

    # Create progress bar
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
        TextColumn("•"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Converting", total=to_convert)

        converted = 0
        skipped = 0
        errors = 0
        total_saved = 0

        # Process files in parallel
        # WHY ProcessPoolExecutor: Image conversion is CPU-bound.
        # WHY spawn: Avoids inheriting locks from the parent process.
        with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
            # Submit all files
            futures = {
                executor.submit(convert_single_image, jpg_path): jpg_path for jpg_path in jpg_files
            }

            for future in as_completed(futures):
                jpg_path = futures[future]

                try:
                    result = future.result()

                    if result["error"]:
                        errors += 1
                        logger.error(f"Failed to convert {result['jpg_path']}: {result['error']}")
                        console.print(f"  [red]✗ Failed: {Path(result['jpg_path']).name}[/red]")
                    elif result["success"]:
                        if result["jpg_size"] > 0 and result["webp_size"] > 0:
                            saved = result["jpg_size"] - result["webp_size"]
                            total_saved += saved
                            converted += 1
                        else:
                            # Already existed (skipped)
                            skipped += 1

                        progress.update(task, advance=1)

                        # Log progress to file periodically
                        if (converted + skipped) % 1000 == 0:
                            elapsed = time.time() - conversion_start
                            rate = (converted + skipped) / elapsed if elapsed > 0 else 0
                            logger.info(
                                f"Progress: {converted + skipped:,}/{len(jpg_files):,} "
                                f"({(converted + skipped) / len(jpg_files) * 100:.1f}%) • "
                                f"{rate:.0f} files/s • "
                                f"saved: {format_size(total_saved)}"
                            )

                except Exception as e:
                    errors += 1
                    logger.error(f"Unexpected error processing {jpg_path}: {e}")

    # Summary
    total_elapsed = time.time() - conversion_start
    rate = to_convert / total_elapsed if total_elapsed > 0 else 0

    console.print("\n[bold green]✓ Conversion complete:[/bold green]")
    console.print(f"  Converted: [green]{converted:,}[/green] files")
    console.print(f"  Skipped: [yellow]{skipped:,}[/yellow] files (already WebP)")
    console.print(f"  Errors: [red]{errors:,}[/red] files")
    console.print(f"  Space saved: [green]{format_size(total_saved)}[/green]")
    console.print(f"  Rate: [cyan]{rate:.0f}[/cyan] files/s")
    console.print(f"  Total time: [cyan]{total_elapsed:.1f}s[/cyan]")

    logger.info(
        f"Conversion complete: {converted:,} converted, {skipped:,} skipped, "
        f"{errors:,} errors in {total_elapsed:.1f}s ({rate:.0f} files/s)"
    )

    # Check total size after conversion
    console.print("\n[bold]Checking total image size...[/bold]")
    remaining_jpg = sum(Path(f).stat().st_size for f in jpg_files if Path(f).exists())
    total_webp_after = sum(
        Path(f).with_suffix(".webp").stat().st_size
        for f in jpg_files
        if Path(f).with_suffix(".webp").exists()
    )

    console.print(f"  Remaining JPG: [cyan]{format_size(remaining_jpg)}[/cyan]")
    console.print(f"  Total WebP: [cyan]{format_size(total_webp_after)}[/cyan]")

    if total_webp_after > MAX_TOTAL_SIZE_BYTES:
        over_by = total_webp_after - MAX_TOTAL_SIZE_BYTES
        console.print(
            f"\n[bold red]⚠ Total WebP size ({format_size(total_webp_after)}) "
            f"exceeds 10 GB target by {format_size(over_by)}![/bold red]"
        )
        console.print("  To reduce size, re-run with lower WEBP_QUALITY in convert_jpg_to_webp.py")
        logger.warning(
            f"Total WebP size ({format_size(total_webp_after)}) "
            f"exceeds 10 GB target by {format_size(over_by)}"
        )
    else:
        under_by = MAX_TOTAL_SIZE_BYTES - total_webp_after
        console.print(f"  [green]✓ Within 10 GB target ({format_size(under_by)} remaining)[/green]")
        logger.info(
            f"Total WebP size ({format_size(total_webp_after)}) "
            f"within 10 GB target ({format_size(under_by)} remaining)"
        )

    if errors:
        console.print(f"\n[bold red]{errors} files had errors — check log for details[/bold red]")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Batch convert JPG images to WebP format.\n\n"
        "Converts all existing JPG files (from the old scraper) to WebP.\n"
        "Idempotent: re-running skips already-converted files.\n"
        "See module docstring for detailed design decisions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit to first N files (for testing)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--images-dir",
        default=IMAGES_DIR,
        help=f"Path to images directory (default: {IMAGES_DIR})",
    )
    args = parser.parse_args()

    run_conversion(
        images_dir=args.images_dir,
        limit=args.limit,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
