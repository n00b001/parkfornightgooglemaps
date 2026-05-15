const park4nightService = require('../services/park4night');

const getPlaces = async (req, res) => {
  const { lat, lng, type, minRating } = req.query;

  if (!lat || !lng) {
    return res.status(400).json({ error: 'Latitude and longitude are required' });
  }

  try {
    let places = await park4nightService.getPlaces(lat, lng);

    // Apply filters
    if (type) {
      places = places.filter(p => p.code_type === type);
    }
    if (minRating) {
      places = places.filter(p => parseFloat(p.note_moyenne) >= parseFloat(minRating));
    }

    res.json(places);
  } catch (error) {
    res.status(500).json({ error: 'Failed to fetch places' });
  }
};

const getReviews = async (req, res) => {
  const { id } = req.params;

  try {
    const reviews = await park4nightService.getReviews(id);
    res.json(reviews);
  } catch (error) {
    res.status(500).json({ error: 'Failed to fetch reviews' });
  }
};

module.exports = {
  getPlaces,
  getReviews
};
