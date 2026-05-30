// Set required env vars before importing app
process.env.DATABASE_URL = "postgresql://localhost:5432/test";
process.env.SESSION_SECRET = "test_secret";
process.env.CLIENT_URL = "http://localhost:5173";
process.env.PORT = "3000";
process.env.GOOGLE_CLIENT_ID = "test";
process.env.GOOGLE_CLIENT_SECRET = "test";

const request = require("supertest");
const app = require("../src/index");

describe("GET /health", () => {
	it("should return 200 OK", async () => {
		const res = await request(app).get("/health");
		expect(res.statusCode).toEqual(200);
		expect(res.text).toEqual("OK");
	});
});
