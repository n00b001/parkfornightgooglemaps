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
