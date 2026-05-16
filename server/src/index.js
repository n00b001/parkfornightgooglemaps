require('dotenv').config();
const express = require('express');
const cors = require('cors');
const session = require('express-session');
const pgSession = require('connect-pg-simple')(session);
const { Pool } = require('pg');
const passport = require('./config/passport');
const prisma = require('./config/db');

const authRoutes = require('./routes/auth');
const placeRoutes = require('./routes/places');
const favoriteRoutes = require('./routes/favorites');
const reviewRoutes = require('./routes/reviews');
const visitRoutes = require('./routes/visits');

const app = express();
const PORT = process.env.PORT || 5000;

let pgPool;
if (process.env.DATABASE_URL) {
  pgPool = new Pool({
    connectionString: process.env.DATABASE_URL
  });
}

app.use(cors({
  origin: (process.env.CLIENT_URL && !process.env.CLIENT_URL.startsWith('http')) ? `https://${process.env.CLIENT_URL}` : (process.env.CLIENT_URL || 'http://localhost:5173'),
  credentials: true
}));
app.use(express.json());

if (pgPool) {
  app.use(session({
    store: new pgSession({
      pool: pgPool,
      tableName: 'Session'
    }),
    secret: process.env.SESSION_SECRET || 'park4night_secret',
    resave: false,
    saveUninitialized: false,
    cookie: {
      maxAge: 30 * 24 * 60 * 60 * 1000,
      secure: process.env.NODE_ENV === 'production'
    }
  }));
} else {
  app.use(session({
    secret: 'temp_secret',
    resave: false,
    saveUninitialized: false
  }));
}

app.use(passport.initialize());
app.use(passport.session());

app.use('/auth', authRoutes);
app.use('/api/places', placeRoutes);
app.use('/api/favorites', favoriteRoutes);
app.use('/api/reviews', reviewRoutes);
app.use('/api/visits', visitRoutes);

app.get('/health', (req, res) => res.send('OK'));

if (require.main === module) {
  app.listen(PORT, () => {
    console.log(`Server running on port ${PORT}`);
  });
}

module.exports = app;
