const express = require('express');
const router = express.Router();
const visitController = require('../controllers/visitController');
router.get('/', visitController.getVisits);
router.post('/', visitController.recordVisit);
module.exports = router;
