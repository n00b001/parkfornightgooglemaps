const express = require('express');
const passport = require('passport');
const router = express.Router();

router.get('/google', (req, res, next) => {
  const { returnTo } = req.query;
  const state = returnTo ? Buffer.from(JSON.stringify({ returnTo })).toString('base64') : undefined;
  passport.authenticate('google', { scope: ['profile', 'email'], state })(req, res, next);
});

router.get('/google/callback',
  passport.authenticate('google', { failureRedirect: '/login' }),
  (req, res) => {
    let returnTo = process.env.CLIENT_URL || '/';
    if (req.query.state) {
      try {
        const state = JSON.parse(Buffer.from(req.query.state, 'base64').toString());
        if (state.returnTo) {
          returnTo = state.returnTo;
        }
      } catch (e) {
        console.error('Error parsing state:', e);
      }
    }

    if (returnTo && !returnTo.startsWith('http')) {
      returnTo = `https://${returnTo}`;
    }

    res.redirect(returnTo);
  }
);

router.get('/me', (req, res) => res.json(req.user || null));

module.exports = router;
