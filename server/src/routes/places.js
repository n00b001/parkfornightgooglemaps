const express = require('express');
const router = express.Router();
const placeController = require('../controllers/placeController');
router.get('/', placeController.getPlaces);
router.get('/:id/reviews', placeController.getReviews);
module.exports = router;
