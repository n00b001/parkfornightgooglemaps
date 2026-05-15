const prisma = require('../config/db');

const getFavorites = async (req, res) => {
  if (!req.isAuthenticated()) return res.status(401).json({ error: 'Unauthorized' });

  try {
    const favorites = await prisma.favorite.findMany({
      where: { userId: req.user.id },
      include: { place: true }
    });
    res.json(favorites);
  } catch (error) {
    res.status(500).json({ error: 'Failed to fetch favorites' });
  }
};

const addFavorite = async (req, res) => {
  if (!req.isAuthenticated()) return res.status(401).json({ error: 'Unauthorized' });
  const { placeId } = req.body;

  try {
    const favorite = await prisma.favorite.create({
      data: {
        userId: req.user.id,
        placeId: parseInt(placeId)
      }
    });
    res.json(favorite);
  } catch (error) {
    res.status(500).json({ error: 'Failed to add favorite' });
  }
};

const removeFavorite = async (req, res) => {
  if (!req.isAuthenticated()) return res.status(401).json({ error: 'Unauthorized' });
  const { placeId } = req.params;

  try {
    await prisma.favorite.delete({
      where: {
        userId_placeId: {
          userId: req.user.id,
          placeId: parseInt(placeId)
        }
      }
    });
    res.json({ success: true });
  } catch (error) {
    res.status(500).json({ error: 'Failed to remove favorite' });
  }
};

module.exports = {
  getFavorites,
  addFavorite,
  removeFavorite
};
