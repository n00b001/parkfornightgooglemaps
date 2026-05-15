const axios = require('axios');
const prisma = require('../config/db');

const PARK4NIGHT_BASE_URL = 'https://guest.park4night.com/services/V4.1';

const getPlaces = async (latitude, longitude) => {
  try {
    const response = await axios.get(`${PARK4NIGHT_BASE_URL}/lieuxGetFilter.php`, {
      params: { latitude, longitude }
    });
    const places = response.data.lieux || [];
    return places;
  } catch (error) {
    console.error('Error fetching from Park4night:', error.message);
    throw error;
  }
};

const getReviews = async (placeId) => {
  try {
    const response = await axios.get(`${PARK4NIGHT_BASE_URL}/commGet.php`, {
      params: { lieu_id: placeId }
    });
    return response.data;
  } catch (error) {
    throw error;
  }
};

module.exports = { getPlaces, getReviews };
