const express = require('express');
const router = express.Router();
const reviewController = require('../controllers/reviewController');
router.get('/:placeId', reviewController.getPlaceReviews);
router.post('/', reviewController.addReview);
module.exports = router;
