const prisma = require("../src/config/db");
const park4night = require("../src/services/park4night");

jest.mock("../src/config/db", () => ({
	place: {
		findMany: jest.fn(),
		findUnique: jest.fn(),
		count: jest.fn(),
		upsert: jest.fn(),
	},
	review: {
		count: jest.fn(),
		findMany: jest.fn(),
	},
}));

jest.mock("../src/services/park4night", () => ({
	getPlaces: jest.fn(),
}));

// Mock LRU cache — no caching during tests so each call hits the DB mock
jest.mock("../src/services/lruCache", () => {
	class LRUCache {
		constructor() {}
		get() {
			return undefined;
		}
		set() {}
	}
	return LRUCache;
});

const placeController = require("../src/controllers/placeController");

describe("placeController Hybrid Fetching", () => {
	let req, res;

	beforeEach(() => {
		jest.clearAllMocks();
		req = { query: {}, params: {} };
		res = {
			status: jest.fn().mockReturnThis(),
			json: jest.fn(),
		};
		prisma.place.findMany.mockResolvedValue([]);
		prisma.place.count.mockResolvedValue(0);
		prisma.place.upsert.mockResolvedValue({});
	});

	it("should fetch from Park4Night API when DB is sparse", async () => {
		req.query = { lat: "48.8566", lng: "2.3522" };

		// DB has 5 recent places (less than 10)
		prisma.place.count.mockResolvedValue(5);

		const mockFreshPlaces = [
			{ id: 101, name: "New Place 1", latitude: 48.85, longitude: 2.35, type: "parking", rating: 4, rawData: {} },
		];
		park4night.getPlaces.mockResolvedValue(mockFreshPlaces);

		// After upsert, DB query returns the new place
		prisma.place.findMany.mockResolvedValue(mockFreshPlaces);

		await placeController.getPlaces(req, res);

		expect(prisma.place.count).toHaveBeenCalled();
		expect(park4night.getPlaces).toHaveBeenCalledWith(48.8566, 2.3522);
		expect(prisma.place.upsert).toHaveBeenCalled();
		expect(res.json).toHaveBeenCalledWith(mockFreshPlaces);
	});

	it("should NOT fetch from API when DB has enough recent places", async () => {
		req.query = { lat: "48.8566", lng: "2.3522" };

		// DB has 15 recent places (more than 10)
		prisma.place.count.mockResolvedValue(15);

		const mockPlaces = [{ id: 1, name: "Existing Place", latitude: 48.85, longitude: 2.35 }];
		prisma.place.findMany.mockResolvedValue(mockPlaces);

		await placeController.getPlaces(req, res);

		expect(prisma.place.count).toHaveBeenCalled();
		expect(park4night.getPlaces).not.toHaveBeenCalled();
		expect(prisma.place.upsert).not.toHaveBeenCalled();
		expect(res.json).toHaveBeenCalledWith(mockPlaces);
	});
});
