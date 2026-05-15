const park4nightService = require('../services/park4night');
const prisma = require('../config/db');

const getPlaces = async (req, res) => {
  const { lat, lng, type, minRating, search, sortBy } = req.query;

  try {
    let places = [];

    // Fetch and cache if lat/lng are provided
    if (lat && lng) {
      const p4nPlaces = await park4nightService.getPlaces(lat, lng);

      // Upsert places into database
      await Promise.all(p4nPlaces.map(p =>
        prisma.place.upsert({
          where: { id: parseInt(p.id) },
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
            id: parseInt(p.id),
            name: p.titre || '',
            latitude: parseFloat(p.latitude),
            longitude: parseFloat(p.longitude),
            type: p.code_type || '',
            address: p.adresse || '',
            rating: parseFloat(p.note_moyenne) || 0,
            rawData: p
          }
        })
      ));
    }

    // Build query
    const query = {
      where: {}
    };

    if (type) {
      query.where.type = type;
    }

    if (minRating) {
      query.where.rating = { gte: parseFloat(minRating) };
    }

    if (search) {
      query.where.OR = [
        { name: { contains: search, mode: 'insensitive' } },
        { address: { contains: search, mode: 'insensitive' } }
      ];
    }

    if (sortBy === 'rating') {
      query.orderBy = { rating: 'desc' };
    }

    // If we have lat/lng, we might want to limit to nearby,
    // but for now let's just return what we have or filter by proximity if needed.
    // For simplicity, let's return all matching places.

    const dbPlaces = await prisma.place.findMany(query);

    // Convert back to the format expected by frontend (which seems to use P4N format from rawData)
    const results = dbPlaces.map(p => ({
      ...p.rawData,
      id: p.id,
      titre: p.name,
      latitude: p.latitude,
      longitude: p.longitude,
      code_type: p.type,
      adresse: p.address,
      note_moyenne: p.rating
    }));

    res.json(results);
  } catch (error) {
    console.error('Error in getPlaces:', error);
    res.status(500).json({ error: 'Failed to fetch places' });
  }
};

const getReviews = async (req, res) => {
  try {
    const p4nReviews = await park4nightService.getReviews(req.params.id);

    // Also get local reviews
    const localReviews = await prisma.review.findMany({
      where: { placeId: parseInt(req.params.id) },
      include: { user: true }
    });

    // Combine them
    // P4N reviews are in p4nReviews.commentaires
    const combined = [
      ...(p4nReviews.commentaires || []).map(r => ({
        id: `p4n-${r.id}`,
        content: r.txt,
        rating: parseInt(r.note),
        user: { name: r.pseudo },
        createdAt: r.date_crea
      })),
      ...localReviews.map(r => ({
        id: r.id,
        content: r.content,
        rating: r.rating,
        user: { name: r.user.name },
        createdAt: r.createdAt
      }))
    ];

    res.json(combined);
  } catch (error) {
    console.error('Error in getReviews:', error);
    res.status(500).json({ error: 'Failed to fetch reviews' });
  }
};

module.exports = { getPlaces, getReviews };
