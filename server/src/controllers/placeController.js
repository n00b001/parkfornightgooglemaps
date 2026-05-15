const park4nightService = require('../services/park4night');

const prisma = require('../config/db');

const getPlaces = async (req, res) => {
  const { lat, lng, type, minRating } = req.query;
  if (!lat || !lng) return res.status(400).json({ error: 'Lat/lng required' });
  try {
    const places = await park4nightService.getPlaces(lat, lng);

    // Cache places in DB
    for (const place of places) {
      await prisma.place.upsert({
        where: { id: place.id },
        update: {
          name: place.name,
          latitude: place.latitude,
          longitude: place.longitude,
          type: place.type,
          description: place.description,
          address: place.address,
          rating: place.rating,
          rawData: place.rawData,
          lastFetched: new Date()
        },
        create: {
          id: place.id,
          name: place.name,
          latitude: place.latitude,
          longitude: place.longitude,
          type: place.type,
          description: place.description,
          address: place.address,
          rating: place.rating,
          rawData: place.rawData
        }
      });
    }

    let filteredPlaces = places;
    if (type) filteredPlaces = filteredPlaces.filter(p => p.type === type);
    if (minRating) filteredPlaces = filteredPlaces.filter(p => p.rating >= parseFloat(minRating));

    res.json(filteredPlaces.map(p => ({ ...p.rawData, id: p.id }))); // Return rawData with consistent ID for frontend
  } catch (error) {
    console.error(error);
    res.status(500).json({ error: 'Failed' });
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
