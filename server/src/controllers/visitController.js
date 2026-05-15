const prisma = require('../config/db');

const recordVisit = async (req, res) => {
  if (!req.isAuthenticated()) return res.status(401).json({ error: 'Unauthorized' });
  const { placeId } = req.body;
  try {
    const visit = await prisma.visit.upsert({
      where: { userId_placeId: { userId: req.user.id, placeId: parseInt(placeId) } },
      update: { visitedAt: new Date() },
      create: { userId: req.user.id, placeId: parseInt(placeId) }
    });
    res.json(visit);
  } catch (error) {
    res.status(500).json({ error: 'Failed' });
  }
};

const getVisits = async (req, res) => {
  if (!req.isAuthenticated()) return res.status(401).json({ error: 'Unauthorized' });
  try {
    const visits = await prisma.visit.findMany({
      where: { userId: req.user.id },
      include: { place: true }
    });
    res.json(visits);
  } catch (error) {
    res.status(500).json({ error: 'Failed' });
  }
};

module.exports = { recordVisit, getVisits };
