const axios = require('axios');
const prisma = require('../config/db');

const PARK4NIGHT_BASE_URL = 'https://guest.park4night.com/services/V4.1';

/**
 * Fetch places from Park4night API based on coordinates.
 * Proxies the request and caches the results in the database.
 */
const getPlaces = async (latitude, longitude) => {
  try {
    const response = await axios.get(`${PARK4NIGHT_BASE_URL}/lieuxGetFilter.php`, {
      params: { latitude, longitude }
    });

    const places = response.data.lieux || [];

    // Cache places in the database
    for (const place of places) {
      await prisma.place.upsert({
        where: { id: parseInt(place.id) },
        update: {
          name: place.titre,
          latitude: parseFloat(place.latitude),
          longitude: parseFloat(place.longitude),
          type: place.code_type,
          description: place.description,
          address: place.adresse,
          rating: parseFloat(place.note_moyenne) || 0,
          rawData: place,
          lastFetched: new Date()
        },
        create: {
          id: parseInt(place.id),
          name: place.titre,
          latitude: parseFloat(place.latitude),
          longitude: parseFloat(place.longitude),
          type: place.code_type,
          description: place.description,
          address: place.adresse,
          rating: parseFloat(place.note_moyenne) || 0,
          rawData: place,
          lastFetched: new Date()
        }
      });
    }

    return places;
  } catch (error) {
    console.error('Error fetching from Park4night:', error.message);
    throw error;
  }
};

/**
 * Fetch reviews for a specific place.
 */
const getReviews = async (placeId) => {
  try {
    const response = await axios.get(`${PARK4NIGHT_BASE_URL}/commGet.php`, {
      params: { lieu_id: placeId }
    });
    return response.data;
  } catch (error) {
    console.error('Error fetching reviews from Park4night:', error.message);
    throw error;
  }
};

module.exports = {
  getPlaces,
  getReviews
};
