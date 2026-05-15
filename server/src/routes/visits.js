const express = require('express');
const router = express.Router();
const visitController = require('../controllers/visitController');

router.post('/', visitController.recordVisit);
router.get('/', visitController.getVisits);

module.exports = router;
