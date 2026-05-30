const prisma = require("../src/config/db");

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

jest.mock("../src/services/park4night", () => ({
	getPlaces: jest.fn(),
	getReviews: jest.fn(),
}));

const park4night = require("../src/services/park4night");
const placeController = require("../src/controllers/placeController");

describe("placeController", () => {
	let req, res;

	beforeEach(() => {
		jest.clearAllMocks();
		req = { query: {}, params: {} };
		res = {
			status: jest.fn().mockReturnThis(),
			json: jest.fn(),
		};
		prisma.place.findMany.mockResolvedValue([]);
		prisma.place.findUnique.mockResolvedValue(null);
		prisma.place.count.mockResolvedValue(0);
		prisma.review.findMany.mockResolvedValue([]);
		prisma.review.count.mockResolvedValue(0);
	});

	describe("getPlaces", () => {
		it("should return 400 when lat/lng missing", async () => {
			await placeController.getPlaces(req, res);
			expect(res.status).toHaveBeenCalledWith(400);
			expect(res.json).toHaveBeenCalledWith({ error: "Lat/lng required" });
		});

		it("should return places from Prisma sorted by distance", async () => {
			req.query = { lat: "48.8566", lng: "2.3522" };
			const mockPlaces = [
				{ id: 1, name: "Far", latitude: 49.0, longitude: 3.0 },
				{ id: 2, name: "Close", latitude: 48.86, longitude: 2.36 },
			];
			prisma.place.findMany.mockResolvedValue(mockPlaces);

			await placeController.getPlaces(req, res);
			expect(prisma.place.findMany).toHaveBeenCalled();
			const returned = res.json.mock.calls[0][0];
			expect(returned[0].name).toBe("Close");
			expect(returned[1].name).toBe("Far");
		});

		it("should respect the limit parameter", async () => {
			req.query = { lat: "48.8566", lng: "2.3522", limit: "2" };
			const mockPlaces = Array.from({ length: 5 }, (_, i) => ({
				id: i,
				name: `Place ${i}`,
				latitude: 48.8566 + i * 0.01,
				longitude: 2.3522 + i * 0.01,
			}));
			prisma.place.findMany.mockResolvedValue(mockPlaces);

			await placeController.getPlaces(req, res);
			const returned = res.json.mock.calls[0][0];
			expect(returned.length).toBe(2);
		});

		it("should cap limit at MAX_PLACES_LIMIT (200)", async () => {
			req.query = { lat: "48.8566", lng: "2.3522", limit: "9999" };
			const mockPlaces = Array.from({ length: 250 }, (_, i) => ({
				id: i,
				name: `Place ${i}`,
				latitude: 48.8566 + i * 0.001,
				longitude: 2.3522 + i * 0.001,
			}));
			prisma.place.findMany.mockResolvedValue(mockPlaces);

			await placeController.getPlaces(req, res);
			const returned = res.json.mock.calls[0][0];
			expect(returned.length).toBe(200);
		});

		it("should return empty array when no places found", async () => {
			req.query = { lat: "48.8566", lng: "2.3522" };
			prisma.place.findMany.mockResolvedValue([]);

			await placeController.getPlaces(req, res);
			expect(res.json).toHaveBeenCalledWith([]);
		});

		it("should return 500 on error", async () => {
			req.query = { lat: "48.8566", lng: "2.3522" };
			prisma.place.findMany.mockRejectedValue(new Error("DB error"));

			await placeController.getPlaces(req, res);
			expect(res.status).toHaveBeenCalledWith(500);
			expect(res.json).toHaveBeenCalledWith({
				error: "Failed to fetch places",
				details: "DB error",
			});
		});
	});

	describe("getPlaceDetail", () => {
		it("should return place detail from Prisma", async () => {
			req.params = { id: "123" };
			const mockPlace = { id: 123, name: "Test Place" };
			prisma.place.findUnique.mockResolvedValue(mockPlace);

			await placeController.getPlaceDetail(req, res);
			expect(prisma.place.findUnique).toHaveBeenCalled();
			expect(res.json).toHaveBeenCalledWith(mockPlace);
		});

		it("should return 404 when place not found", async () => {
			req.params = { id: "999" };
			prisma.place.findUnique.mockResolvedValue(null);

			await placeController.getPlaceDetail(req, res);
			expect(res.status).toHaveBeenCalledWith(404);
			expect(res.json).toHaveBeenCalledWith({ error: "Place not found" });
		});

		it("should return 500 on error", async () => {
			req.params = { id: "123" };
			prisma.place.findUnique.mockRejectedValue(new Error("DB error"));

			await placeController.getPlaceDetail(req, res);
			expect(res.status).toHaveBeenCalledWith(500);
			expect(res.json).toHaveBeenCalledWith({
				error: "Failed to fetch place",
				details: "DB error",
			});
		});
	});

	describe("getPlaceReviews", () => {
		it("should return reviews from DB and P4N", async () => {
			req.params = { id: "123" };
			const mockLocalReviews = [
				{ id: "1", content: "Great!", rating: 5, user: { name: "Test User" } },
			];
			const mockP4nReviews = [
				{ id: "2", commentaire: "Good", note: 4, auteur: "P4N User", date: "2023-01-01" },
			];
			prisma.review.findMany.mockResolvedValue(mockLocalReviews);
			park4night.getReviews.mockResolvedValue(mockP4nReviews);

			await placeController.getPlaceReviews(req, res);
			expect(prisma.review.findMany).toHaveBeenCalledWith({
				where: { placeId: 123 },
				include: { user: true },
				orderBy: { createdAt: "desc" },
			});
			expect(park4night.getReviews).toHaveBeenCalledWith(123);
			const returned = res.json.mock.calls[0][0];
			expect(returned.reviews.length).toBe(2);
			expect(returned.reviews[0].author).toBe("Test User");
			expect(returned.reviews[1].author).toBe("P4N User");
		});

		it("should return empty reviews when none exist", async () => {
			req.params = { id: "123" };
			prisma.review.findMany.mockResolvedValue([]);
			park4night.getReviews.mockResolvedValue([]);

			await placeController.getPlaceReviews(req, res);
			expect(res.json).toHaveBeenCalledWith({ reviews: [] });
		});
	});

	describe("getStats", () => {
		it("should return stats from DB", async () => {
			prisma.place.count.mockResolvedValue(100);
			prisma.review.count.mockResolvedValue(500);

			await placeController.getStats(req, res);
			expect(prisma.place.count).toHaveBeenCalled();
			expect(res.json).toHaveBeenCalledWith({
				totalPlaces: 100,
				totalReviews: 500,
				placesWithReviews: 100,
			});
		});
	});
});
