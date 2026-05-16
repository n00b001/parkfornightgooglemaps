const park4nightService = require('../services/park4night');

const prisma = require('../config/db');

const getPlaces = async (req, res) => {
  const { lat, lng, type, minRating, sortBy } = req.query;
  if (!lat || !lng) return res.status(400).json({ error: 'Lat/lng required' });

  const latitude = parseFloat(lat);
  const longitude = parseFloat(lng);
  const range = 0.5;

  try {
    // Check for recent cached data within range
    const recentPlaces = await prisma.place.findMany({
      where: {
        latitude: { gte: latitude - range, lte: latitude + range },
        longitude: { gte: longitude - range, lte: longitude + range },
        lastFetched: { gte: new Date(Date.now() - 24 * 60 * 60 * 1000) }
      }
    });

    let places;
    if (recentPlaces.length > 0) {
      places = recentPlaces.map(p => ({
        id: p.id,
        name: p.name,
        latitude: p.latitude,
        longitude: p.longitude,
        type: p.type,
        description: p.description,
        address: p.address,
        rating: p.rating,
        rawData: p.rawData
      }));
    } else {
      places = await park4nightService.getPlaces(latitude, longitude);

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
            rawData: place.rawData,
            lastFetched: new Date()
          }
        });
      }
    }

    let filteredPlaces = places;
    if (type) filteredPlaces = filteredPlaces.filter(p => p.type === type);
    if (minRating) filteredPlaces = filteredPlaces.filter(p => p.rating >= parseFloat(minRating));

    if (sortBy === 'rating') {
      filteredPlaces.sort((a, b) => b.rating - a.rating);
    } else if (sortBy === 'distance') {
      filteredPlaces.sort((a, b) => {
        const distA = Math.sqrt(Math.pow(a.latitude - latitude, 2) + Math.pow(a.longitude - longitude, 2));
        const distB = Math.sqrt(Math.pow(b.latitude - latitude, 2) + Math.pow(b.longitude - longitude, 2));
        return distA - distB;
      });
    }

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
