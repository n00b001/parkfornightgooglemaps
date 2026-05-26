const LRUCache = require("../src/services/lruCache");

describe("LRUCache", () => {
	let cache;

	beforeEach(() => {
		cache = new LRUCache(3, 100); // max 3 entries, 100ms TTL
	});

	it("should get and set values", () => {
		cache.set("a", 1);
		expect(cache.get("a")).toBe(1);
	});

	it("should return undefined for missing keys", () => {
		expect(cache.get("missing")).toBeUndefined();
	});

	it("should evict oldest entry when at capacity", () => {
		cache.set("a", 1);
		cache.set("b", 2);
		cache.set("c", 3);
		cache.set("d", 4); // should evict "a"

		expect(cache.get("a")).toBeUndefined();
		expect(cache.get("b")).toBe(2);
		expect(cache.get("c")).toBe(3);
		expect(cache.get("d")).toBe(4);
	});

	it("should update MRU order on get", () => {
		cache.set("a", 1);
		cache.set("b", 2);
		cache.set("c", 3);

		cache.get("a"); // access "a" to make it most recently used
		cache.set("d", 4); // should evict "b" (oldest)

		expect(cache.get("a")).toBe(1);
		expect(cache.get("b")).toBeUndefined();
	});

	it("should expire entries after TTL", async () => {
		const shortCache = new LRUCache(3, 50); // 50ms TTL
		shortCache.set("a", 1);
		expect(shortCache.get("a")).toBe(1);

		await new Promise((resolve) => setTimeout(resolve, 60));
		expect(shortCache.get("a")).toBeUndefined();
	});

	it("should report correct size", () => {
		expect(cache.size).toBe(0);
		cache.set("a", 1);
		expect(cache.size).toBe(1);
		cache.set("b", 2);
		expect(cache.size).toBe(2);
	});

	it("should clear all entries", () => {
		cache.set("a", 1);
		cache.set("b", 2);
		cache.clear();
		expect(cache.size).toBe(0);
		expect(cache.get("a")).toBeUndefined();
	});
});
