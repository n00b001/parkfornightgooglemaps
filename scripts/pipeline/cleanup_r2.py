#!/usr/bin/env python3
"""
R2 Bucket Cleanup Script.

Lists all non-WebP files in the R2 bucket and deletes them in bulk.
Uses boto3 delete_objects (up to 1000 keys per request).

Usage:
    # Dry run (list files that would be deleted):
    uv run python cleanup_r2.py --dry-run

    # Actually delete non-WebP files:
    uv run python cleanup_r2.py

    # Custom config path:
    uv run python cleanup_r2.py --config /path/to/r2-config.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time

from boto3 import client as r2_client
from botocore.exceptions import ClientError
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
)

console = Console()

# Non-WebP extensions to delete
NON_WEBP_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif"}


def load_config(config_path: str) -> dict:
    """Load R2 configuration from JSON file."""
    if not os.path.exists(config_path):
        console.print(f"[bold red]ERROR:[/bold red] Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    required_keys = ["accessKeyId", "secretAccessKey", "endpoint", "bucket"]
    for key in required_keys:
        if key not in config:
            console.print(f"[bold red]ERROR:[/bold red] Missing key in config: {key}")
            sys.exit(1)

    return config


def create_r2_client(config: dict):
    """Create an R2-compatible S3 client."""
    return r2_client(
        "s3",
        endpoint_url=config["endpoint"],
        aws_access_key_id=config["accessKeyId"],
        aws_secret_access_key=config["secretAccessKey"],
        region_name=config.get("region", "auto"),
    )


def list_all_objects(r2, bucket: str) -> list[dict]:
    """List all objects in the bucket using pagination."""
    all_objects = []
    paginator = r2.get_paginator("list_objects_v2")

    with Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("\u2022"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Listing objects", total=None)

        for page in paginator.paginate(Bucket=bucket):
            objects = page.get("Contents", [])
            all_objects.extend(objects)
            progress.update(task, completed=len(all_objects), visible=True)

    return all_objects


def filter_non_webp(objects: list[dict]) -> list[dict]:
    """Filter objects to only those with non-WebP extensions."""
    non_webp = []
    for obj in objects:
        key = obj["Key"]
        # Check if key ends with a non-WebP extension
        for ext in NON_WEBP_EXTENSIONS:
            if key.lower().endswith(ext):
                non_webp.append(obj)
                break
    return non_webp


def delete_in_batches(
    r2,
    bucket: str,
    objects: list[dict],
    batch_size: int = 1000,
) -> tuple[int, int]:
    """Delete objects in batches. Returns (deleted, failed)."""
    total = len(objects)
    deleted = 0
    failed = 0

    with Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("\u2022"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Deleting objects", total=total)

        for i in range(0, total, batch_size):
            batch = objects[i : i + batch_size]
            keys = [{"Key": obj["Key"]} for obj in batch]

            try:
                response = r2.delete_objects(
                    Bucket=bucket,
                    Delete={"Objects": keys, "Quiet": True},
                )

                # Count successful deletions
                deleted_count = len(batch)
                errors = response.get("Errors", [])
                deleted_count -= len(errors)

                deleted += deleted_count
                failed += len(errors)

                if errors:
                    for error in errors:
                        logging.getLogger("cleanup").error(
                            f"Failed to delete {error.get('Key')}: {error.get('Message')}"
                        )

            except ClientError as e:
                failed += len(batch)
                logging.getLogger("cleanup").error(f"Batch delete error: {e}")

            progress.update(task, completed=i + len(batch))

    return deleted, failed


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete non-WebP files from R2 bucket")
    parser.add_argument(
        "--config",
        default=os.path.join(os.path.dirname(__file__), "..", "upload", "r2-config.json"),
        help="Path to R2 config JSON",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files that would be deleted without actually deleting",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Number of objects to delete per request (default: 1000)",
    )

    args = parser.parse_args()

    console.print("\n[bold cyan]\u2554═══════════════════════════════════════\u2557[/bold cyan]")
    console.print("[bold cyan]\u2551  R2 Bucket Cleanup (Non-WebP Files) \u2551[/bold cyan]")
    console.print("[bold cyan]\u255a═══════════════════════════════════════\u255d[/bold cyan]\n")

    # Load config
    config = load_config(args.config)
    bucket = config["bucket"]
    console.print(f"  Bucket: [cyan]{bucket}[/cyan]")
    console.print(f"  Dry run: [cyan]{args.dry_run}[/cyan]\n")

    # Setup logging
    log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"cleanup_{time.strftime('%Y%m%d_%H%M%S')}.log")
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.getLogger("cleanup").info(f"Cleanup started (dry_run={args.dry_run})")
    console.print(f"  Log file: [cyan]{log_file}[/cyan]\n")

    # Create R2 client
    r2 = create_r2_client(config)

    # List all objects
    console.print("[bold]Listing all objects in bucket...[/bold]")
    all_objects = list_all_objects(r2, bucket)
    console.print(f"  Total objects: [cyan]{len(all_objects):,}[/cyan]\n")

    # Filter non-WebP
    non_webp = filter_non_webp(all_objects)
    webp_count = len(all_objects) - len(non_webp)

    console.print(f"  WebP files: [green]{webp_count:,}[/green] (keeping)")
    console.print(f"  Non-WebP files: [red]{len(non_webp):,}[/red] (to delete)\n")

    if not non_webp:
        console.print("[bold green]No non-WebP files found. Nothing to do.[/bold green]")
        return

    # Show breakdown by extension
    ext_counts: dict[str, int] = {}
    for obj in non_webp:
        key = obj["Key"]
        for ext in NON_WEBP_EXTENSIONS:
            if key.lower().endswith(ext):
                ext_counts[ext] = ext_counts.get(ext, 0) + 1
                break

    console.print("  Breakdown by extension:")
    for ext, count in sorted(ext_counts.items(), key=lambda x: -x[1]):
        console.print(f"    [red]{ext}[/red]: {count:,}")
    console.print()

    # Calculate total size
    total_size_bytes = sum(obj.get("Size", 0) for obj in non_webp)
    total_size_gb = total_size_bytes / (1024**3)
    console.print(f"  Total size to free: [red]{total_size_gb:.2f} GB[/red]\n")

    if args.dry_run:
        console.print("[bold yellow]=== DRY RUN — no files were deleted ===[/bold yellow]")
        # Show first 20 files that would be deleted
        console.print("\n  First 20 files that would be deleted:")
        for obj in non_webp[:20]:
            size_mb = obj.get("Size", 0) / (1024**2)
            console.print(f"    {obj['Key']} ({size_mb:.2f} MB)")
        if len(non_webp) > 20:
            console.print(f"    ... and {len(non_webp) - 20:,} more")
        return

    # Confirm deletion
    console.print(
        f"[bold yellow]WARNING:[/bold yellow] This will permanently delete "
        f"[bold red]{len(non_webp):,}[/bold red] files "
        f"([bold red]{total_size_gb:.2f} GB[/bold red])."
    )
    console.print("Type 'delete' to confirm:")
    confirmation = input("> ")

    if confirmation.strip().lower() != "delete":
        console.print("[yellow]Cancelled.[/yellow]")
        return

    # Delete
    console.print("\n[bold]Deleting non-WebP files...[/bold]\n")
    start_time = time.time()
    deleted, failed = delete_in_batches(r2, bucket, non_webp, batch_size=args.batch_size)
    elapsed = time.time() - start_time

    # Summary
    console.print("\n[bold green]\u2554═══════════════════════════════════════\u2557[/bold green]")
    console.print("[bold green]\u2551  Cleanup Complete!                   \u2551[/bold green]")
    console.print("[bold green]\u255a═══════════════════════════════════════\u255d[/bold green]")
    console.print(f"  Deleted: [green]{deleted:,}[/green]")
    console.print(f"  Failed: [red]{failed:,}[/red]")
    console.print(f"  Time: [cyan]{elapsed:.1f}s[/cyan]")

    if deleted > 0:
        freed_gb = (total_size_bytes / deleted * deleted) / (1024**3) if deleted else 0
        console.print(f"  Freed: [green]{freed_gb:.2f} GB[/green]")

    logging.getLogger("cleanup").info(
        f"Cleanup complete: deleted={deleted}, failed={failed}, time={elapsed:.1f}s"
    )


if __name__ == "__main__":
    main()
