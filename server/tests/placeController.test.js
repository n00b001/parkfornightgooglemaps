const placeController = require("../src/controllers/placeController");
const localData = require("../src/services/localData");

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
	});

	describe("getPlaces", () => {
		it("should return 400 when lat/lng missing", async () => {
			await placeController.getPlaces(req, res);
			expect(res.status).toHaveBeenCalledWith(400);
			expect(res.json).toHaveBeenCalledWith({ error: "Lat/lng required" });
		});

		it("should return places from local data", async () => {
			req.query = { lat: "48.8566", lng: "2.3522" };
			const mockPlaces = [
				{ id: 1, name: "Test Place", latitude: 48.8566, longitude: 2.3522 },
			];
			localData.getAllPlaces.mockReturnValue(mockPlaces);

			await placeController.getPlaces(req, res);
			expect(localData.getAllPlaces).toHaveBeenCalledWith({
				lat: 48.8566,
				lng: 2.3522,
				type: undefined,
				minRating: undefined,
				sortBy: undefined,
			});
			expect(res.json).toHaveBeenCalledWith(mockPlaces);
		});

		it("should filter by type", async () => {
			req.query = { lat: "48.8566", lng: "2.3522", type: "cc" };
			const mockPlaces = [{ id: 1, name: "CC Place", type: { code: "cc" } }];
			localData.getAllPlaces.mockReturnValue(mockPlaces);

			await placeController.getPlaces(req, res);
			expect(localData.getAllPlaces).toHaveBeenCalledWith({
				lat: 48.8566,
				lng: 2.3522,
				type: "cc",
				minRating: undefined,
				sortBy: undefined,
			});
			expect(res.json).toHaveBeenCalledWith(mockPlaces);
		});

		it("should filter by minRating", async () => {
			req.query = { lat: "48.8566", lng: "2.3522", minRating: "4" };
			const mockPlaces = [{ id: 1, name: "Good Place", rating: 4.5 }];
			localData.getAllPlaces.mockReturnValue(mockPlaces);

			await placeController.getPlaces(req, res);
			expect(localData.getAllPlaces).toHaveBeenCalledWith({
				lat: 48.8566,
				lng: 2.3522,
				type: undefined,
				minRating: "4",
				sortBy: undefined,
			});
		});

		it("should sort by rating", async () => {
			req.query = { lat: "48.8566", lng: "2.3522", sortBy: "rating" };
			const mockPlaces = [
				{ id: 2, name: "High", rating: 5.0 },
				{ id: 1, name: "Low", rating: 3.0 },
			];
			localData.getAllPlaces.mockReturnValue(mockPlaces);

			await placeController.getPlaces(req, res);
			expect(localData.getAllPlaces).toHaveBeenCalledWith({
				lat: 48.8566,
				lng: 2.3522,
				type: undefined,
				minRating: undefined,
				sortBy: "rating",
			});
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
		it("should return place detail", async () => {
			req.params = { id: "123" };
			const mockPlace = { id: 123, name: "Test Place" };
			localData.getPlaceById.mockReturnValue(mockPlace);

			await placeController.getPlaceDetail(req, res);
			expect(localData.getPlaceById).toHaveBeenCalledWith("123");
			expect(res.json).toHaveBeenCalledWith(mockPlace);
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
