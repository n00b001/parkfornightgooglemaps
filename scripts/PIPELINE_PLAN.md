# Pipeline Fix Plan: WebP-Only R2 Upload + Non-WebP Cleanup

## Problem
- 24GB of images in Cloudflare R2 bucket (both .jpg AND .webp)
- Will be charged for anything over 10GB
- Local images: 228,976 .jpg files, 0 .webp files
- Pipeline uploads images as-is (no format conversion)

## Root Cause
The `r2_worker.py` and `r2_uploader.py` modules:
1. Find local images (prefers .jpg, falls back to .webp)
2. Upload the file AS-IS with the original extension
3. R2 key includes the original extension (.jpg or .webp)

So if a .jpg file exists locally, it gets uploaded as .jpg to R2.

## Solution

### Phase 1: Fix the pipeline to ONLY upload WebP

**Files to modify:**

1. **`scripts/pipeline/pyproject.toml`** — Add Pillow dependency
2. **`scripts/pipeline/image_downloader.py`** — Save downloaded images as .webp instead of .jpg
3. **`scripts/pipeline/r2_worker.py`** — Only look for .webp files, always use .webp R2 keys
4. **`scripts/pipeline/r2_uploader.py`** — Only look for .webp files, always use .webp R2 keys

**Conversion strategy:**
- Image downloader: download as .jpg temporarily, then immediately convert to .webp using Pillow (quality=85), then delete .jpg
- R2 uploader: only find .webp files, R2 keys always end in .webp
- Content-Type always "image/webp"

### Phase 2: Delete non-WebP files from R2 bucket

**New script: `scripts/pipeline/cleanup_r2.py`**
- List all objects in R2 bucket
- Filter for non-.webp files (.jpg, .jpeg, .png, etc.)
- Bulk delete using boto3 `delete_objects` (up to 1000 per request)
- Progress bars + logging
- Dry-run mode to preview what would be deleted

### Phase 3: Convert existing local .jpg files to .webp

**New script: `scripts/pipeline/convert_local_images.py`**
- Convert all existing .jpg files in `scripts/data/images/` to .webp
- Multithreaded (32 workers)
- Progress bars + logging
- Delete .jpg after successful conversion
- Checkpoint-based (resume on restart)

## Implementation Order

1. ✅ Write requirements to PIPELINE_REQUIREMENTS.md
2. ⬜ Add Pillow dependency to pyproject.toml
3. ⬜ Modify image_downloader.py to save as .webp
4. ⬜ Modify r2_worker.py to only upload .webp
5. ⬜ Modify r2_uploader.py to only upload .webp
6. ⬜ Create cleanup_r2.py script (delete non-WebP from bucket)
7. ⬜ Create convert_local_images.py script (convert local .jpg → .webp)
8. ⬜ Test with --limit 10
9. ⬜ STOP for review

## Testing Strategy
- Test each change with --limit 10 places
- Verify: images downloaded as .webp, uploaded as .webp, R2 keys end in .webp
- Verify: cleanup script lists correct files for deletion (dry-run first)
- Verify: local conversion script converts correctly

## Key Decisions
- WebP quality: 85 (good balance of size vs quality for photos)
- Conversion happens at download time (new images) AND via batch script (existing images)
- R2 keys always use .webp extension regardless of source format
- Old .jpg files in R2 are deleted (not kept as fallback)
