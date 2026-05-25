const axios = require('axios');

const PARK4NIGHT_BASE_URL = 'https://guest.park4night.com/services/V4.1';

const getPlaces = async (latitude, longitude) => {
  try {
    const response = await axios.get(`${PARK4NIGHT_BASE_URL}/lieuxGetFilter.php`, {
      params: { latitude, longitude }
    });
    const places = (response.data.lieux || []).map(p => ({
      id: parseInt(p.id),
      name: p.titre,
      latitude: parseFloat(p.latitude),
      longitude: parseFloat(p.longitude),
      type: p.code_type,
      description: p.description,
      address: p.adresse,
      rating: parseFloat(p.note_moyenne) || 0,
      rawData: p
    }));
    return places;
  } catch (error) {
    console.error('Error fetching from Park4night:', error.message);
    throw error;
  }
};

const getReviews = async (placeId) => {
  const response = await axios.get(`${PARK4NIGHT_BASE_URL}/commGet.php`, {
    params: { lieu_id: placeId }
  });
  return response.data;
};

module.exports = { getPlaces, getReviews };
