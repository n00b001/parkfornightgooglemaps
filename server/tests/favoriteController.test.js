const favoriteController = require("../src/controllers/favoriteController");
const db = require("../src/config/db");

jest.mock("../src/config/db", () => ({
	favorite: {
		findMany: jest.fn(),
		upsert: jest.fn(),
		delete: jest.fn(),
	},
}));

describe("favoriteController", () => {
	let req, res;

	beforeEach(() => {
		jest.clearAllMocks();
		req = {
			body: {},
			params: {},
			user: { id: 1 },
			isAuthenticated: jest.fn(() => true),
		};
		res = {
			status: jest.fn().mockReturnThis(),
			json: jest.fn(),
		};
	});

	describe("getFavorites", () => {
		it("should return 401 when not authenticated", async () => {
			req.isAuthenticated = jest.fn(() => false);
			await favoriteController.getFavorites(req, res);
			expect(res.status).toHaveBeenCalledWith(401);
			expect(res.json).toHaveBeenCalledWith({ error: "Unauthorized" });
		});

		it("should return user favorites", async () => {
			const mockFavorites = [
				{ id: 1, userId: 1, placeId: 10, place: { id: 10, name: "Place 10" } },
			];
			db.favorite.findMany.mockResolvedValue(mockFavorites);

			await favoriteController.getFavorites(req, res);
			expect(db.favorite.findMany).toHaveBeenCalledWith({
				where: { userId: 1 },
				include: {
					place: {
						include: {
							type: true,
							placeServices: { include: { service: true } },
						},
					},
				},
			});
			expect(res.json).toHaveBeenCalled();
		});

		it("should return 500 on error", async () => {
			db.favorite.findMany.mockRejectedValue(new Error("DB error"));
			await favoriteController.getFavorites(req, res);
			expect(res.status).toHaveBeenCalledWith(500);
			expect(res.json).toHaveBeenCalledWith({ error: "Failed" });
		});
	});

	describe("addFavorite", () => {
		it("should return 401 when not authenticated", async () => {
			req.isAuthenticated = jest.fn(() => false);
			await favoriteController.addFavorite(req, res);
			expect(res.status).toHaveBeenCalledWith(401);
			expect(res.json).toHaveBeenCalledWith({ error: "Unauthorized" });
		});

		it("should add a favorite", async () => {
			req.body = { placeId: "10" };
			const mockFavorite = { id: 1, userId: 1, placeId: 10 };
			db.favorite.upsert.mockResolvedValue(mockFavorite);

			await favoriteController.addFavorite(req, res);
			expect(db.favorite.upsert).toHaveBeenCalledWith({
				where: { userId_placeId: { userId: 1, placeId: 10 } },
				update: {},
				create: { userId: 1, placeId: 10 },
			});
			expect(res.json).toHaveBeenCalledWith(mockFavorite);
		});

		it("should return 500 on error", async () => {
			req.body = { placeId: "10" };
			db.favorite.upsert.mockRejectedValue(new Error("DB error"));
			await favoriteController.addFavorite(req, res);
			expect(res.status).toHaveBeenCalledWith(500);
			expect(res.json).toHaveBeenCalledWith({ error: "Failed" });
		});
	});

	describe("removeFavorite", () => {
		it("should return 401 when not authenticated", async () => {
			req.isAuthenticated = jest.fn(() => false);
			req.params = { id: "10" };
			await favoriteController.removeFavorite(req, res);
			expect(res.status).toHaveBeenCalledWith(401);
			expect(res.json).toHaveBeenCalledWith({ error: "Unauthorized" });
		});

		it("should remove a favorite", async () => {
			req.params = { id: "10" };
			db.favorite.delete.mockResolvedValue({});

			await favoriteController.removeFavorite(req, res);
			expect(db.favorite.delete).toHaveBeenCalledWith({
				where: { userId_placeId: { userId: 1, placeId: 10 } },
			});
			expect(res.json).toHaveBeenCalledWith({ success: true });
		});

		it("should return 500 on error", async () => {
			req.params = { id: "10" };
			db.favorite.delete.mockRejectedValue(new Error("DB error"));
			await favoriteController.removeFavorite(req, res);
			expect(res.status).toHaveBeenCalledWith(500);
			expect(res.json).toHaveBeenCalledWith({ error: "Failed" });
		});
	});
});
