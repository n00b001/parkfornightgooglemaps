const express = require("express");
const router = express.Router();
const placeController = require("../controllers/placeController");
router.get("/stats", placeController.getStats);
router.get("/", placeController.getPlaces);
router.get("/:id", placeController.getPlaceDetail);
router.get("/:id/reviews", placeController.getPlaceReviews);
module.exports = router;
