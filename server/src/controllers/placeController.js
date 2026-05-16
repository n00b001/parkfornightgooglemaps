const park4nightService = require('../services/park4night');
const prisma = require('../config/db');

const getPlaces = async (req, res) => {
  const { lat, lng, type, minRating, search, sortBy } = req.query;

  if (!lat || !lng) return res.status(400).json({ error: 'Lat/lng required' });

  try {
    // 1. Try to find in DB first to check for fresh data
    const latitude = parseFloat(lat);
    const longitude = parseFloat(lng);
    const range = 0.5; // Reduced range from 1 to 0.5 (~55km) for better performance

    let where = {
      latitude: { gte: latitude - range, lte: latitude + range },
      longitude: { gte: longitude - range, lte: longitude + range }
    };

    // Check if we have recent data for this area
    const recentPlace = await prisma.place.findFirst({
      where: {
        ...where,
        lastFetched: { gte: new Date(Date.now() - 1000 * 60 * 60 * 24) } // 24 hours
      }
    });

    // 2. If no recent data, fetch from Park4night
    if (!recentPlace) {
      const p4nPlaces = await park4nightService.getPlaces(lat, lng);

      // Cache in DB (Upsert) - limit to avoid overwhelming DB
      // In a real app, we'd use a background queue
      const upsertPromises = p4nPlaces.slice(0, 50).map(p => {
        const id = parseInt(p.id);
        return prisma.place.upsert({
          where: { id },
          update: {
            name: p.titre || '',
            latitude: parseFloat(p.latitude),
            longitude: parseFloat(p.longitude),
            type: p.code_type || '',
            address: p.adresse || '',
            rating: parseFloat(p.note_moyenne) || 0,
            rawData: p,
            lastFetched: new Date()
          },
          create: {
            id,
            name: p.titre || '',
            latitude: parseFloat(p.latitude),
            longitude: parseFloat(p.longitude),
            type: p.code_type || '',
            address: p.adresse || '',
            rating: parseFloat(p.note_moyenne) || 0,
            rawData: p
          }
        });
      });
      await Promise.all(upsertPromises);
    }

    // 3. Query from DB with full filters/sorting
    if (type) where.type = type;
    if (minRating) where.rating = { gte: parseFloat(minRating) };
    if (search) {
      where.OR = [
        { name: { contains: search, mode: 'insensitive' } },
        { address: { contains: search, mode: 'insensitive' } }
      ];
    }

    let orderBy = {};
    if (sortBy === 'rating') {
      orderBy = { rating: 'desc' };
    }

    const places = await prisma.place.findMany({
      where,
      orderBy: Object.keys(orderBy).length ? orderBy : undefined,
      take: 100 // Limit results for performance
    });

    res.json(places);
  } catch (error) {
    console.error('Error in getPlaces:', error);
    res.status(500).json({ error: 'Failed to fetch places' });
  }
};

const getReviews = async (req, res) => {
  try {
    const reviews = await park4nightService.getReviews(req.params.id);
    res.json(reviews);
  } catch (error) {
    res.status(500).json({ error: 'Failed to fetch reviews' });
  }
};

module.exports = { getPlaces, getReviews };
