const express = require("express");
const router = express.Router();
const { getPlaceImage, getIcon } = require("../controllers/imageController");

// Place photos: /images/:placeId/:filename
router.get("/:placeId/:filename", getPlaceImage);

// Vehicle icons: /images/icons/:filename
router.get("/icons/:filename", getIcon);

module.exports = router;
