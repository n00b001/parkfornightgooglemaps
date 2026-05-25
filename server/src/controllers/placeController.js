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
    let places;
    try {
      const recentPlaces = await prisma.place.findMany({
        where: {
          latitude: { gte: latitude - range, lte: latitude + range },
          longitude: { gte: longitude - range, lte: longitude + range },
          lastFetched: { gte: new Date(Date.now() - 24 * 60 * 60 * 1000) }
        }
      });

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
        console.log(`Serving ${places.length} cached places for (${latitude}, ${longitude})`);
      }
    } catch (dbError) {
      console.error('Database query error:', dbError.message);
      // If DB is not available, fall through to fetch from Park4Night API
      places = undefined;
    }

    // Fetch from Park4Night API if no cached data
    if (!places || places.length === 0) {
      try {
        places = await park4nightService.getPlaces(latitude, longitude);
        console.log(`Fetched ${places.length} places from Park4Night API for (${latitude}, ${longitude})`);
      } catch (apiError) {
        console.error('Park4Night API error:', apiError.message);
        // Return empty array instead of 500 - client has offline caching
        return res.json([]);
      }

      // Cache places in DB (non-blocking - don't fail if DB is down)
      if (places.length > 0) {
        try {
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
          console.log(`Cached ${places.length} places in database`);
        } catch (cacheError) {
          console.error('Failed to cache places in DB:', cacheError.message);
          // Continue - we still have the data from the API
        }
      }
    }

    let filteredPlaces = places || [];
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

    res.json(filteredPlaces.map(p => ({ ...p.rawData, id: p.id })));
  } catch (error) {
    console.error('Unexpected error in getPlaces:', error.message, error.stack);
    res.status(500).json({ error: 'Failed to fetch places', details: error.message });
  }
};

const getReviews = async (req, res) => {
  try {
    const reviews = await park4nightService.getReviews(req.params.id);
    res.json(reviews);
  } catch (error) {
    console.error('Error fetching reviews:', error.message);
    res.status(500).json({ error: 'Failed to fetch reviews', details: error.message });
  }
};

module.exports = { getPlaces, getReviews };
