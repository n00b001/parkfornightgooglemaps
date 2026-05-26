const placeController = require("../src/controllers/placeController");
const localData = require("../src/services/localData");
const prisma = require("../src/config/db");
const park4night = require("../src/services/park4night");

jest.mock("../src/config/db", () => ({
	place: {
		findMany: jest.fn(),
		findUnique: jest.fn(),
		upsert: jest.fn(),
	},
}));

jest.mock("../src/services/park4night", () => ({
	getPlaces: jest.fn(),
	getPlaceDetail: jest.fn(),
}));

jest.mock("../src/services/localData", () => ({
	getAllPlaces: jest.fn(),
	getPlaceById: jest.fn(),
	getPlaceReviews: jest.fn(),
	getStats: jest.fn(),
	loadData: jest.fn(),
}));

describe("placeController", () => {
	let req, res;

	beforeEach(() => {
		jest.clearAllMocks();
		req = { query: {}, params: {} };
		res = {
			status: jest.fn().mockReturnThis(),
			json: jest.fn(),
		};
		// Set default mock implementations
		prisma.place.findMany.mockResolvedValue([]);
		prisma.place.findUnique.mockResolvedValue(null);
		prisma.place.upsert.mockImplementation((args) => Promise.resolve(args.create || args.update));
		park4night.getPlaces.mockResolvedValue([]);
		park4night.getPlaceDetail.mockResolvedValue(null);
	});

	describe("getPlaces", () => {
		it("should return 400 when lat/lng missing", async () => {
			await placeController.getPlaces(req, res);
			expect(res.status).toHaveBeenCalledWith(400);
			expect(res.json).toHaveBeenCalledWith({ error: "Lat/lng required" });
		});

		it("should return places from Prisma database", async () => {
			req.query = { lat: "48.8566", lng: "2.3522" };
			const mockPlaces = Array(15).fill({ id: 1, name: "Prisma Place" });
			prisma.place.findMany.mockResolvedValue(mockPlaces);

			await placeController.getPlaces(req, res);
			expect(prisma.place.findMany).toHaveBeenCalled();
			expect(res.json).toHaveBeenCalledWith(mockPlaces);
		});

		it("should return places from Live API when DB has few results", async () => {
			req.query = { lat: "48.8566", lng: "2.3522" };
			prisma.place.findMany.mockResolvedValue([]);
			const mockLivePlaces = [{ id: 1, name: "Live Place", latitude: 48.8, longitude: 2.3 }];
			park4night.getPlaces.mockResolvedValue(mockLivePlaces);
			prisma.place.upsert.mockResolvedValue(mockLivePlaces[0]);

			await placeController.getPlaces(req, res);
			expect(park4night.getPlaces).toHaveBeenCalled();
			expect(prisma.place.upsert).toHaveBeenCalled();
			expect(res.json).toHaveBeenCalledWith(mockLivePlaces);
		});

		it("should return places from local data as fallback", async () => {
			req.query = { lat: "48.8566", lng: "2.3522" };
			prisma.place.findMany.mockResolvedValue([]);
			park4night.getPlaces.mockResolvedValue([]);
			const mockLocalPlaces = [{ id: 1, name: "Local Place" }];
			localData.getAllPlaces.mockReturnValue(mockLocalPlaces);

			await placeController.getPlaces(req, res);
			expect(localData.getAllPlaces).toHaveBeenCalled();
			expect(res.json).toHaveBeenCalledWith(mockLocalPlaces);
		});


		it("should return 500 on error", async () => {
			req.query = { lat: "48.8566", lng: "2.3522" };
			localData.getAllPlaces.mockImplementation(() => {
				throw new Error("Local data error");
			});

			await placeController.getPlaces(req, res);
			expect(res.status).toHaveBeenCalledWith(500);
			expect(res.json).toHaveBeenCalledWith({
				error: "Failed to fetch places",
				details: "Local data error",
			});
		});
	});

	describe("getPlaceDetail", () => {
		it("should return place detail from Prisma", async () => {
			req.params = { id: "123" };
			const mockPlace = { id: 123, name: "Prisma Place" };
			prisma.place.findUnique.mockResolvedValue(mockPlace);

			await placeController.getPlaceDetail(req, res);
			expect(prisma.place.findUnique).toHaveBeenCalled();
			expect(res.json).toHaveBeenCalledWith(mockPlace);
		});

		it("should return place detail from Live API", async () => {
			req.params = { id: "123" };
			prisma.place.findUnique.mockResolvedValue(null);
			const mockLivePlace = { id: 123, name: "Live Place" };
			park4night.getPlaceDetail.mockResolvedValue(mockLivePlace);
			prisma.place.upsert.mockResolvedValue(mockLivePlace);

			await placeController.getPlaceDetail(req, res);
			expect(park4night.getPlaceDetail).toHaveBeenCalledWith(123);
			expect(res.json).toHaveBeenCalledWith(mockLivePlace);
		});

		it("should return 404 when place not found", async () => {
			req.params = { id: "999" };
			localData.getPlaceById.mockReturnValue(null);

			await placeController.getPlaceDetail(req, res);
			expect(res.status).toHaveBeenCalledWith(404);
			expect(res.json).toHaveBeenCalledWith({ error: "Place not found" });
		});

		it("should return 500 on error", async () => {
			req.params = { id: "123" };
			localData.getPlaceById.mockImplementation(() => {
				throw new Error("Local data error");
			});

			await placeController.getPlaceDetail(req, res);
			expect(res.status).toHaveBeenCalledWith(500);
			expect(res.json).toHaveBeenCalledWith({
				error: "Failed to fetch place",
				details: "Local data error",
			});
		});
	});

	describe("getPlaceReviews", () => {
		it("should return reviews from local data", async () => {
			req.params = { id: "123" };
			const mockReviews = [{ id: "1", place_id: 123, text: "Great!" }];
			localData.getPlaceReviews.mockReturnValue(mockReviews);

			await placeController.getPlaceReviews(req, res);
			expect(localData.getPlaceReviews).toHaveBeenCalledWith("123");
			expect(res.json).toHaveBeenCalledWith(mockReviews);
		});

		it("should return empty array when no reviews", async () => {
			req.params = { id: "123" };
			localData.getPlaceReviews.mockReturnValue([]);

			await placeController.getPlaceReviews(req, res);
			expect(res.json).toHaveBeenCalledWith([]);
		});

		it("should return 500 on error", async () => {
			req.params = { id: "123" };
			localData.getPlaceReviews.mockImplementation(() => {
				throw new Error("Local data error");
			});

			await placeController.getPlaceReviews(req, res);
			expect(res.status).toHaveBeenCalledWith(500);
			expect(res.json).toHaveBeenCalledWith({
				error: "Failed to fetch reviews",
				details: "Local data error",
			});
		});
	});

	describe("getStats", () => {
		it("should return stats", async () => {
			const mockStats = {
				totalPlaces: 30606,
				totalReviews: 296067,
				placesWithReviews: 22560,
			};
			localData.getStats.mockReturnValue(mockStats);

			await placeController.getStats(req, res);
			expect(localData.getStats).toHaveBeenCalled();
			expect(res.json).toHaveBeenCalledWith(mockStats);
		});

		it("should return 500 on error", async () => {
			localData.getStats.mockImplementation(() => {
				throw new Error("Local data error");
			});

			await placeController.getStats(req, res);
			expect(res.status).toHaveBeenCalledWith(500);
			expect(res.json).toHaveBeenCalledWith({
				error: "Failed to fetch stats",
				details: "Local data error",
			});
		});
	});
});
