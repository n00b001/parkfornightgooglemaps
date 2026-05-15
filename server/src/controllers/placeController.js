const park4nightService = require('../services/park4night');

const getPlaces = async (req, res) => {
  const { lat, lng, type, minRating } = req.query;
  if (!lat || !lng) return res.status(400).json({ error: 'Lat/lng required' });
  try {
    let places = await park4nightService.getPlaces(lat, lng);
    if (type) places = places.filter(p => p.code_type === type);
    if (minRating) places = places.filter(p => parseFloat(p.note_moyenne) >= parseFloat(minRating));
    res.json(places);
  } catch (error) {
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
