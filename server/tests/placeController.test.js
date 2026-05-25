const placeController = require('../src/controllers/placeController');
const park4nightService = require('../src/services/park4night');
const db = require('../src/config/db');

jest.mock('../src/services/park4night');
jest.mock('../src/config/db', () => ({
  place: {
    findMany: jest.fn(),
    upsert: jest.fn(),
  },
}));

describe('placeController', () => {
  let req, res;

  beforeEach(() => {
    jest.clearAllMocks();
    req = { query: {}, params: {} };
    res = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn(),
    };
  });

  describe('getPlaces', () => {
    it('should return 400 when lat/lng missing', async () => {
      await placeController.getPlaces(req, res);
      expect(res.status).toHaveBeenCalledWith(400);
      expect(res.json).toHaveBeenCalledWith({ error: 'Lat/lng required' });
    });

    it('should return cached places when available', async () => {
      req.query = { lat: '48.8566', lng: '2.3522' };
      const cachedPlaces = [
        {
          id: 1,
          name: 'Test Place',
          latitude: 48.8566,
          longitude: 2.3522,
          type: 'cc',
          description: 'A test place',
          address: 'Paris',
          rating: 4.5,
          rawData: { id: 1, titre: 'Test Place' },
          lastFetched: new Date(),
        },
      ];
      db.place.findMany.mockResolvedValue(cachedPlaces);

      await placeController.getPlaces(req, res);
      expect(res.json).toHaveBeenCalled();
      const result = res.json.mock.calls[0][0];
      expect(result).toHaveLength(1);
    });

    it('should fetch from Park4Night when no cache', async () => {
      req.query = { lat: '48.8566', lng: '2.3522' };
      db.place.findMany.mockResolvedValue([]);
      const apiPlaces = [
        {
          id: 1,
          name: 'API Place',
          latitude: 48.8566,
          longitude: 2.3522,
          type: 'cc',
          description: 'From API',
          address: 'Paris',
          rating: 4.0,
          rawData: { id: 1, titre: 'API Place' },
        },
      ];
      park4nightService.getPlaces.mockResolvedValue(apiPlaces);
      db.place.upsert.mockResolvedValue({});

      await placeController.getPlaces(req, res);
      expect(park4nightService.getPlaces).toHaveBeenCalledWith(48.8566, 2.3522);
      expect(db.place.upsert).toHaveBeenCalled();
      expect(res.json).toHaveBeenCalled();
    });

    it('should filter by type', async () => {
      req.query = { lat: '48.8566', lng: '2.3522', type: 'cc' };
      const cachedPlaces = [
        {
          id: 1, name: 'CC Place', latitude: 48.8566, longitude: 2.3522,
          type: 'cc', description: '', address: '', rating: 4.5,
          rawData: { id: 1, titre: 'CC Place' }, lastFetched: new Date(),
        },
        {
          id: 2, name: 'P Place', latitude: 48.8566, longitude: 2.3522,
          type: 'p', description: '', address: '', rating: 3.5,
          rawData: { id: 2, titre: 'P Place' }, lastFetched: new Date(),
        },
      ];
      db.place.findMany.mockResolvedValue(cachedPlaces);

      await placeController.getPlaces(req, res);
      const result = res.json.mock.calls[0][0];
      expect(result).toHaveLength(1);
      expect(result[0].id).toBe(1);
    });

    it('should filter by minRating', async () => {
      req.query = { lat: '48.8566', lng: '2.3522', minRating: '4' };
      const cachedPlaces = [
        {
          id: 1, name: 'Good Place', latitude: 48.8566, longitude: 2.3522,
          type: 'cc', description: '', address: '', rating: 4.5,
          rawData: { id: 1, titre: 'Good Place' }, lastFetched: new Date(),
        },
        {
          id: 2, name: 'Bad Place', latitude: 48.8566, longitude: 2.3522,
          type: 'cc', description: '', address: '', rating: 3.0,
          rawData: { id: 2, titre: 'Bad Place' }, lastFetched: new Date(),
        },
      ];
      db.place.findMany.mockResolvedValue(cachedPlaces);

      await placeController.getPlaces(req, res);
      const result = res.json.mock.calls[0][0];
      expect(result).toHaveLength(1);
      expect(result[0].id).toBe(1);
    });

    it('should sort by rating', async () => {
      req.query = { lat: '48.8566', lng: '2.3522', sortBy: 'rating' };
      const cachedPlaces = [
        {
          id: 1, name: 'Low', latitude: 48.8566, longitude: 2.3522,
          type: 'cc', description: '', address: '', rating: 3.0,
          rawData: { id: 1, titre: 'Low' }, lastFetched: new Date(),
        },
        {
          id: 2, name: 'High', latitude: 48.8566, longitude: 2.3522,
          type: 'cc', description: '', address: '', rating: 5.0,
          rawData: { id: 2, titre: 'High' }, lastFetched: new Date(),
        },
      ];
      db.place.findMany.mockResolvedValue(cachedPlaces);

      await placeController.getPlaces(req, res);
      const result = res.json.mock.calls[0][0];
      expect(result[0].id).toBe(2);
    });
  });

  describe('getReviews', () => {
    it('should return reviews from Park4Night', async () => {
      req.params = { id: '123' };
      const mockReviews = { commentaires: [{ id: 1, texte: 'Great!' }] };
      park4nightService.getReviews.mockResolvedValue(mockReviews);

      await placeController.getReviews(req, res);
      expect(park4nightService.getReviews).toHaveBeenCalledWith('123');
      expect(res.json).toHaveBeenCalledWith(mockReviews);
    });

    it('should return 500 on error', async () => {
      req.params = { id: '123' };
      park4nightService.getReviews.mockRejectedValue(new Error('API error'));

      await placeController.getReviews(req, res);
      expect(res.status).toHaveBeenCalledWith(500);
      expect(res.json).toHaveBeenCalledWith({ error: 'Failed' });
    });
  });
});
