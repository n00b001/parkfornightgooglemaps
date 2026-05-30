const visitController = require('../src/controllers/visitController');
const db = require('../src/config/db');

jest.mock('../src/config/db', () => ({
  visit: {
    upsert: jest.fn(),
    findMany: jest.fn(),
  },
}));

describe('visitController', () => {
  let req, res;

  beforeEach(() => {
    jest.clearAllMocks();
    req = { body: {}, params: {}, user: { id: 1 }, isAuthenticated: jest.fn(() => true) };
    res = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn(),
    };
  });

  describe('recordVisit', () => {
    it('should return 401 when not authenticated', async () => {
      req.isAuthenticated = jest.fn(() => false);
      await visitController.recordVisit(req, res);
      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({ error: 'Unauthorized' });
    });

    it('should record a visit', async () => {
      req.body = { placeId: '10' };
      const mockVisit = { id: 1, userId: 1, placeId: 10, visitedAt: new Date() };
      db.visit.upsert.mockResolvedValue(mockVisit);

      await visitController.recordVisit(req, res);
      expect(db.visit.upsert).toHaveBeenCalledWith({
        where: { userId_placeId: { userId: 1, placeId: 10 } },
        update: { visitedAt: expect.any(Date) },
        create: { userId: 1, placeId: 10 },
      });
      expect(res.json).toHaveBeenCalledWith(mockVisit);
    });

    it('should return 500 on error', async () => {
      req.body = { placeId: '10' };
      db.visit.upsert.mockRejectedValue(new Error('DB error'));
      await visitController.recordVisit(req, res);
      expect(res.status).toHaveBeenCalledWith(500);
      expect(res.json).toHaveBeenCalledWith({ error: 'Failed' });
    });
  });

  describe('getVisits', () => {
    it('should return 401 when not authenticated', async () => {
      req.isAuthenticated = jest.fn(() => false);
      await visitController.getVisits(req, res);
      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({ error: 'Unauthorized' });
    });

    it('should return user visits', async () => {
      const mockVisits = [
        { id: 1, userId: 1, placeId: 10, visitedAt: new Date(), place: { id: 10, name: 'Place 10' } },
      ];
      db.visit.findMany.mockResolvedValue(mockVisits);

      await visitController.getVisits(req, res);
      expect(db.visit.findMany).toHaveBeenCalledWith({
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

    it('should return 500 on error', async () => {
      db.visit.findMany.mockRejectedValue(new Error('DB error'));
      await visitController.getVisits(req, res);
      expect(res.status).toHaveBeenCalledWith(500);
      expect(res.json).toHaveBeenCalledWith({ error: 'Failed' });
    });
  });
});
