/**
 * Simple LRU cache with TTL.
 * Uses a Map to track insertion order (most recently used at end).
 */
class LRUCache {
	constructor(maxSize = 100, ttlMs = 5 * 60 * 1000) {
		this.maxSize = maxSize;
		this.ttlMs = ttlMs;
		this.cache = new Map(); // key -> { data, expiresAt }
	}

	get(key) {
		const entry = this.cache.get(key);
		if (!entry) return undefined;

		// Expired
		if (Date.now() > entry.expiresAt) {
			this.cache.delete(key);
			return undefined;
		}

		// Move to end (most recently used)
		this.cache.delete(key);
		this.cache.set(key, entry);
		return entry.data;
	}

	set(key, data) {
		// Evict oldest if at capacity
		if (this.cache.size >= this.maxSize && !this.cache.has(key)) {
			const oldestKey = this.cache.keys().next().value;
			this.cache.delete(oldestKey);
		}

		this.cache.set(key, {
			data,
			expiresAt: Date.now() + this.ttlMs,
		});
	}

	get size() {
		return this.cache.size;
	}

	clear() {
		this.cache.clear();
	}
}

module.exports = LRUCache;
