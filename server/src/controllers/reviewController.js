const prisma = require('../config/db');

const addReview = async (req, res) => {
  if (!req.isAuthenticated()) return res.status(401).json({ error: 'Unauthorized' });
  const { placeId, content, rating } = req.body;
  try {
    const review = await prisma.review.create({
      data: { userId: req.user.id, placeId: parseInt(placeId), content, rating: parseInt(rating) }
    });
    res.json(review);
  } catch (error) {
    res.status(500).json({ error: 'Failed' });
  }
};

const getPlaceReviews = async (req, res) => {
  try {
    const reviews = await prisma.review.findMany({
      where: { placeId: parseInt(req.params.placeId) },
      include: { user: true },
      orderBy: { createdAt: 'desc' }
    });
    res.json(reviews);
  } catch (error) {
    res.status(500).json({ error: 'Failed' });
  }
};

module.exports = { addReview, getPlaceReviews };
