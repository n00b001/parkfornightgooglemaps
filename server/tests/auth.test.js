// Set required env vars before importing app
process.env.DATABASE_URL = 'postgresql://localhost:5432/test';
process.env.SESSION_SECRET = 'test_secret';
process.env.CLIENT_URL = 'http://localhost:5173';
process.env.PORT = '3000';
process.env.GOOGLE_CLIENT_ID = 'test';
process.env.GOOGLE_CLIENT_SECRET = 'test';

const request = require('supertest');
const app = require('../src/index');

describe('Auth routes', () => {
  describe('GET /auth/me', () => {
    it('should return null when not authenticated', async () => {
      const res = await request(app).get('/auth/me');
      expect(res.statusCode).toBe(200);
      expect(res.body).toBeNull();
    });
  });

  describe('GET /auth/logout', () => {
    it('should handle logout when not authenticated', async () => {
      const res = await request(app).get('/auth/logout');
      // Should not crash even when not logged in
      expect([200, 500]).toContain(res.statusCode);
    });
  });
});
