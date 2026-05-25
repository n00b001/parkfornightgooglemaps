const reviewController = require('../src/controllers/reviewController');
const db = require('../src/config/db');

jest.mock('../src/config/db', () => ({
  review: {
    create: jest.fn(),
    findMany: jest.fn(),
  },
}));

describe('reviewController', () => {
  let req, res;

  beforeEach(() => {
    jest.clearAllMocks();
    req = { body: {}, params: {}, user: { id: 1 }, isAuthenticated: jest.fn(() => true) };
    res = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn(),
    };
  });

  describe('addReview', () => {
    it('should return 401 when not authenticated', async () => {
      req.isAuthenticated = jest.fn(() => false);
      await reviewController.addReview(req, res);
      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({ error: 'Unauthorized' });
    });

    it('should create a review', async () => {
      req.body = { placeId: '123', content: 'Great spot!', rating: '5' };
      const mockReview = { id: 1, userId: 1, placeId: 123, content: 'Great spot!', rating: 5 };
      db.review.create.mockResolvedValue(mockReview);

      await reviewController.addReview(req, res);
      expect(db.review.create).toHaveBeenCalledWith({
        data: { userId: 1, placeId: 123, content: 'Great spot!', rating: 5 },
      });
      expect(res.json).toHaveBeenCalledWith(mockReview);
    });

    it('should return 500 on error', async () => {
      req.body = { placeId: '123', content: 'Bad spot', rating: '1' };
      db.review.create.mockRejectedValue(new Error('DB error'));

      await reviewController.addReview(req, res);
      expect(res.status).toHaveBeenCalledWith(500);
      expect(res.json).toHaveBeenCalledWith({ error: 'Failed' });
    });
  });

  describe('getPlaceReviews', () => {
    it('should return reviews for a place', async () => {
      req.params = { placeId: '123' };
      const mockReviews = [
        { id: 1, userId: 1, placeId: 123, content: 'Great!', rating: 5, user: { id: 1, name: 'User' } },
      ];
      db.review.findMany.mockResolvedValue(mockReviews);

      await reviewController.getPlaceReviews(req, res);
      expect(db.review.findMany).toHaveBeenCalledWith({
        where: { placeId: 123 },
        include: { user: true },
        orderBy: { createdAt: 'desc' },
      });
      expect(res.json).toHaveBeenCalledWith(mockReviews);
    });

    it('should return 500 on error', async () => {
      req.params = { placeId: '123' };
      db.review.findMany.mockRejectedValue(new Error('DB error'));

      await reviewController.getPlaceReviews(req, res);
      expect(res.status).toHaveBeenCalledWith(500);
      expect(res.json).toHaveBeenCalledWith({ error: 'Failed' });
    });
  });
});
