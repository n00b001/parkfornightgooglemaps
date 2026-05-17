const park4nightService = require('../services/park4night');
const prisma = require('../config/db');

const getPlaces = async (req, res) => {
  const { lat, lng, type, minRating, search, sortBy } = req.query;

  try {
    let places = [];

    // If search term is provided, we search in the local database primarily
    if (search) {
      places = await prisma.place.findMany({
        where: {
          OR: [
            { name: { contains: search, mode: 'insensitive' } },
            { address: { contains: search, mode: 'insensitive' } }
          ],
          ...(type && { type }),
          ...(minRating && { rating: { gte: parseFloat(minRating) } })
        },
        orderBy: sortBy === 'rating' ? { rating: 'desc' } : { lastFetched: 'desc' }
      });
      return res.json(places.map(p => p.rawData || p));
    }

    if (!lat || !lng) return res.status(400).json({ error: 'Lat/lng required for proximity search' });

    // 1. Try to get from Park4night API
    const apiPlaces = await park4nightService.getPlaces(lat, lng);

    // 2. Cache/Upsert in DB
    for (const p of apiPlaces) {
      try {
        await prisma.place.upsert({
          where: { id: parseInt(p.id) },
          update: {
            name: p.titre,
            latitude: parseFloat(p.latitude),
            longitude: parseFloat(p.longitude),
            type: p.code_type,
            description: p.description_complet || p.description,
            address: p.adresse,
            rating: parseFloat(p.note_moyenne) || 0,
            rawData: p,
            lastFetched: new Date()
          },
          create: {
            id: parseInt(p.id),
            name: p.titre,
            latitude: parseFloat(p.latitude),
            longitude: parseFloat(p.longitude),
            type: p.code_type,
            description: p.description_complet || p.description,
            address: p.adresse,
            rating: parseFloat(p.note_moyenne) || 0,
            rawData: p
          }
        });
      } catch (err) {
        console.error(`Failed to cache place ${p.id}:`, err.message);
      }
    }

    // 3. Return filtered and sorted results
    places = apiPlaces;
    if (type) places = places.filter(p => p.code_type === type);
    if (minRating) places = places.filter(p => parseFloat(p.note_moyenne) >= parseFloat(minRating));

    if (sortBy === 'rating') {
      places.sort((a, b) => parseFloat(b.note_moyenne || 0) - parseFloat(a.note_moyenne || 0));
    }

    res.json(places);
  } catch (error) {
    console.error('Error in getPlaces:', error);
    // Fallback to database if API fails
    try {
      const cachedPlaces = await prisma.place.findMany({
        where: {
          latitude: { gte: parseFloat(lat) - 0.5, lte: parseFloat(lat) + 0.5 },
          longitude: { gte: parseFloat(lng) - 0.5, lte: parseFloat(lng) + 0.5 }
        }
      });
      res.json(cachedPlaces.map(p => p.rawData));
    } catch (dbError) {
      res.status(500).json({ error: 'Failed to fetch places' });
    }
  }
};

const getReviews = async (req, res) => {
  try {
    const reviews = await park4nightService.getReviews(req.params.id);
    res.json(reviews);
  } catch (error) {
    res.status(500).json({ error: 'Failed' });
  }
};

module.exports = { getPlaces, getReviews };
