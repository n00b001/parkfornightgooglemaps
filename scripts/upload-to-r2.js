#!/usr/bin/env node
/**
 * Upload all WebP images to Cloudflare R2
 *
 * Features:
 * - Parallel workers (configurable, default 8)
 * - Colored progress bar with timestamps and ETA
 * - Skip already-uploaded files (headObject check)
 * - Linear backoff retry for failures
 * - Checkpoint file for resuming interrupted uploads
 */

const { S3Client, PutObjectCommand, HeadObjectCommand } = require('@aws-sdk/client-s3');
const fs = require('fs');
const path = require('path');

// ── Configuration ──────────────────────────────────────────────
const CONFIG_PATH = path.join(__dirname, 'r2-config.json');
const IMAGES_DIR = path.join(__dirname, 'data', 'images', 'places');
const CHECKPOINT_PATH = path.join(__dirname, 'r2-checkpoint.json');
const NUM_WORKERS = parseInt(process.env.R2_WORKERS || '8', 10);
const R2_PREFIX = 'places'; // objects stored as places/{place_id}/{photo_id}_thumb.webp

// ── Colors ─────────────────────────────────────────────────────
const RESET = '\x1b[0m';
const BOLD = '\x1b[1m';
const GREEN = '\x1b[32m';
const YELLOW = '\x1b[33m';
const RED = '\x1b[31m';
const BLUE = '\x1b[34m';
const CYAN = '\x1b[36m';

// ── Helpers ────────────────────────────────────────────────────
function timestamp() {
  return new Date().toISOString().substr(11, 8);
}

function log(color, ...args) {
  console.log(`${color}[${timestamp()}]${RESET}`, ...args);
}

function info(...args) { log(BLUE, ...args); }
function success(...args) { log(GREEN, ...args); }
function warn(...args) { log(YELLOW, ...args); }
function error(...args) { log(RED, ...args); }

// ── Progress Bar ───────────────────────────────────────────────
let totalFiles = 0;
let completed = 0;
let skipped = 0;
let failed = 0;
let bytesUploaded = 0;
const startTime = Date.now();

function updateProgress() {
  const elapsed = (Date.now() - startTime) / 1000;
  const rate = completed > 0 ? completed / elapsed : 0;
  const remaining = totalFiles - completed;
  const eta = rate > 0 ? remaining / rate : 0;

  const pct = totalFiles > 0 ? (completed / totalFiles) * 100 : 0;
  const barWidth = 40;
  const filled = Math.round((pct / 100) * barWidth);
  const bar = '█'.repeat(filled) + '░'.repeat(barWidth - filled);

  const bytesMB = (bytesUploaded / (1024 * 1024)).toFixed(1);
  const etaStr = eta > 3600
    ? `${(eta / 3600).toFixed(1)}h`
    : eta > 60
      ? `${Math.round(eta / 60)}m`
      : `${Math.round(eta)}s`;

  const rateStr = `${rate.toFixed(1)}/s`;

  process.stdout.write(`\r${CYAN}${BOLD} Uploading${RESET} [${bar}] ${pct.toFixed(1)}% | ${completed}/${totalFiles} files | ${GREEN}${skipped} skipped${RESET} | ${RED}${failed} failed${RESET} | ${YELLOW}${bytesMB} MB${RESET} | ${rateStr} | ETA: ${etaStr}`);
}

// ── Checkpoint ─────────────────────────────────────────────────
function loadCheckpoint() {
  try {
    if (fs.existsSync(CHECKPOINT_PATH)) {
      return JSON.parse(fs.readFileSync(CHECKPOINT_PATH, 'utf8'));
    }
  } catch (e) {
    warn('Failed to load checkpoint:', e.message);
  }
  return { uploaded: new Set(), failed: {} };
}

function saveCheckpoint(uploadedSet, failedMap) {
  // Save periodically - convert Set to array for JSON
  const data = {
    uploaded: [...uploadedSet],
    failed: failedMap,
    lastUpdated: new Date().toISOString()
  };
  fs.writeFileSync(CHECKPOINT_PATH, JSON.stringify(data, null, 2));
}

let checkpoint;

// ── S3 Client ──────────────────────────────────────────────────
const config = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));

const s3Client = new S3Client({
  region: config.region || 'auto',
  endpoint: config.endpoint,
  credentials: {
    accessKeyId: config.accessKeyId,
    secretAccessKey: config.secretAccessKey,
  },
  maxAttempts: 0, // we handle retries ourselves
});

// ── Retry with Linear Backoff ──────────────────────────────────
async function withRetry(fn, operation, maxRetries = 5) {
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (err) {
      if (attempt === maxRetries) throw err;

      // Linear backoff: 10ms, 100ms, 500ms, 1s, 2s
      const delay = Math.min([10, 100, 500, 1000, 2000][attempt] || 2000, 5000);
      warn(`Retry ${attempt + 1}/${maxRetries} after ${delay}ms: ${operation} - ${err.message}`);
      await new Promise(r => setTimeout(r, delay));
    }
  }
}

// ── Check if object exists in R2 ───────────────────────────────
async function objectExists(key) {
  try {
    await withRetry(() => s3Client.send(new HeadObjectCommand({ Bucket: config.bucket, Key: key })), `head ${key}`);
    return true;
  } catch (e) {
    if (e.name === 'NotFound' || e.$metadata?.httpStatusCode === 404) return false;
    throw e; // rethrow non-404 errors
  }
}

// ── Upload single file ─────────────────────────────────────────
async function uploadFile(filePath, r2Key) {
  const fileBody = fs.createReadStream(filePath);
  const stat = fs.statSync(filePath);

  await withRetry(
    () => s3Client.send(new PutObjectCommand({
      Bucket: config.bucket,
      Key: r2Key,
      Body: fileBody,
      ContentType: 'image/webp',
    })),
    `put ${r2Key}`,
    5
  );

  return stat.size;
}

// ── Collect all WebP files ─────────────────────────────────────
function collectFiles() {
  const files = [];
  const places = fs.readdirSync(IMAGES_DIR);

  for (const placeId of places) {
    const placeDir = path.join(IMAGES_DIR, placeId);
    if (!fs.statSync(placeDir).isDirectory()) continue;

    const photoFiles = fs.readdirSync(placeDir).filter(f => f.endsWith('.webp'));
    for (const photoFile of photoFiles) {
      const r2Key = `${R2_PREFIX}/${placeId}/${photoFile}`;
      files.push({
        filePath: path.join(placeDir, photoFile),
        r2Key,
      });
    }
  }

  return files;
}

// ── Worker Pool ────────────────────────────────────────────────
async function workerPool(files, checkpointData) {
  const queue = [...files];
  const workers = [];

  for (let i = 0; i < Math.min(NUM_WORKERS, queue.length); i++) {
    workers.push((async () => {
      while (queue.length > 0) {
        const item = queue.pop();
        if (!item) continue;

        // Check if already uploaded (checkpoint or R2)
        if (checkpointData.uploaded.has(item.r2Key)) {
          skipped++;
          completed++;
          updateProgress();
          continue;
        }

        try {
          const exists = await objectExists(item.r2Key);
          if (exists) {
            checkpointData.uploaded.add(item.r2Key);
            skipped++;
            completed++;
            updateProgress();
            continue;
          }

          const bytes = await uploadFile(item.filePath, item.r2Key);
          bytesUploaded += bytes;
          checkpointData.uploaded.add(item.r2Key);
          completed++;

          // Remove from failed if it was there
          delete checkpointData.failed[item.r2Key];

          updateProgress();
        } catch (err) {
          failed++;
          checkpointData.failed[item.r2Key] = err.message;
          error(`Failed: ${item.r2Key} - ${err.message}`);
          updateProgress();
        }

        // Save checkpoint every 1000 files
        if (completed % 1000 === 0) {
          saveCheckpoint(checkpointData.uploaded, checkpointData.failed);
        }
      }
    })());
  }

  await Promise.all(workers);
}

// ── Main ───────────────────────────────────────────────────────
async function main() {
  console.log(`\n${BOLD}${CYAN}═══════════════════════════════════════════════════════${RESET}`);
  console.log(`${BOLD}${CYAN}  Cloudflare R2 Image Uploader${RESET}`);
  console.log(`${BOLD}${CYAN}═══════════════════════════════════════════════════════${RESET}\n`);

  info(`Bucket: ${config.bucket}`);
  info(`Endpoint: ${config.endpoint}`);
  info(`Workers: ${NUM_WORKERS}`);
  info(`Images directory: ${IMAGES_DIR}`);

  // Load checkpoint
  checkpoint = loadCheckpoint();
  if (checkpoint.uploaded.length > 0) {
    info(`Resuming from checkpoint: ${checkpoint.uploaded.length} files already uploaded`);
  }

  // Collect files
  info('Scanning for WebP files...');
  const files = collectFiles();
  totalFiles = files.length;
  info(`Found ${BOLD}${totalFiles.toLocaleString()}${RESET} WebP images across places`);

  // Test connection
  info('Testing R2 connection...');
  try {
    // Try to list a single object to verify credentials work
    await s3Client.send(new HeadObjectCommand({
      Bucket: config.bucket,
      Key: '_test_',
    }));
  } catch (e) {
    if (e.name === 'NotFound' || e.$metadata?.httpStatusCode === 404) {
      success('R2 connection OK');
    } else {
      error(`R2 connection failed: ${e.message}`);
      process.exit(1);
    }
  }

  // Calculate estimated size
  let totalSize = 0;
  for (const file of files) {
    try {
      totalSize += fs.statSync(file.filePath).size;
    } catch {}
  }
  info(`Total size: ${(totalSize / (1024 * 1024 * 1024)).toFixed(2)} GB`);

  console.log(`\n${BOLD}Starting upload...${RESET}\n`);

  // Run upload
  await workerPool(files, checkpoint);

  // Final save
  saveCheckpoint(checkpoint.uploaded, checkpoint.failed);

  // Summary
  console.log('\n');
  console.log(`${BOLD}${CYAN}═══════════════════════════════════════════════════════${RESET}`);
  console.log(`${BOLD}${CYAN}  Upload Complete${RESET}`);
  console.log(`${BOLD}${CYAN}═══════════════════════════════════════════════════════${RESET}`);
  console.log(``);
  success(`${completed.toLocaleString()} files processed`);
  info(`${skipped.toLocaleString()} skipped (already uploaded)`);
  if (failed > 0) {
    error(`${failed.toLocaleString()} failed`);
  } else {
    success('No failures!');
  }
  info(`${(bytesUploaded / (1024 * 1024)).toFixed(1)} MB uploaded`);
  const elapsed = ((Date.now() - startTime) / 1000).toFixed(0);
  info(`Elapsed: ${elapsed}s`);
  console.log(`\nCheckpoint saved to: ${CHECKPOINT_PATH}\n`);

  if (failed > 0) {
    process.exit(1);
  }
}

main().catch(err => {
  error('Fatal error:', err.message);
  console.error(err);
  process.exit(1);
});
