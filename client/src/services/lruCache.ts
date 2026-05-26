/**
 * Simple LRU cache with TTL for client-side use.
 */
class LRUCache<K, V> {
	private cache: Map<K, { value: V; expiresAt: number }>;

	constructor(
		private maxSize = 100,
		private ttlMs = 5 * 60 * 1000,
	) {
		this.cache = new Map();
	}

	get(key: K): V | undefined {
		const entry = this.cache.get(key);
		if (!entry) return undefined;

		if (Date.now() > entry.expiresAt) {
			this.cache.delete(key);
			return undefined;
		}

		// Move to end (most recently used)
		this.cache.delete(key);
		this.cache.set(key, entry);
		return entry.value;
	}

	set(key: K, value: V): void {
		if (this.cache.size >= this.maxSize && !this.cache.has(key)) {
			const oldestKey = this.cache.keys().next().value as K | undefined;
			if (oldestKey) this.cache.delete(oldestKey);
		}

		this.cache.set(key, {
			value,
			expiresAt: Date.now() + this.ttlMs,
		});
	}

	get size(): number {
		return this.cache.size;
	}

	clear(): void {
		this.cache.clear();
	}
}

export default LRUCache;
