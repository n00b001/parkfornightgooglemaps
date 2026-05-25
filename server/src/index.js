require('dotenv').config();
const express = require('express');
const cors = require('cors');
const session = require('express-session');
const pgSession = require('connect-pg-simple')(session);
const { Pool } = require('pg');
const passport = require('./config/passport');

// Load local scraped data on startup
const localData = require('./services/localData');
localData.loadData();

const authRoutes = require('./routes/auth');
const placeRoutes = require('./routes/places');
const favoriteRoutes = require('./routes/favorites');
const reviewRoutes = require('./routes/reviews');
const visitRoutes = require('./routes/visits');

const app = express();
const PORT = process.env.PORT || 5000;

if (process.env.NODE_ENV === 'production') {
  app.set('trust proxy', 1);
}

let pgPool;
if (process.env.DATABASE_URL) {
  pgPool = new Pool({
    connectionString: process.env.DATABASE_URL,
    ssl: process.env.NODE_ENV === 'production' ? { rejectUnauthorized: false } : false
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
      tableName: 'Session',
      createTableIfMissing: true
    }),
    secret: process.env.SESSION_SECRET || 'park4night_secret',
    resave: false,
    saveUninitialized: false,
    cookie: {
      maxAge: 30 * 24 * 60 * 60 * 1000,
      secure: process.env.NODE_ENV === 'production',
      sameSite: process.env.NODE_ENV === 'production' ? 'none' : 'lax'
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

// Handle passport errors (e.g., verifier throws)
if (typeof passport.on === 'function') {
  passport.on('authenticateFailure', (info) => {
    console.error('Passport authentication failure:', info);
  });
}

app.use('/auth', authRoutes);
app.use('/api/places', placeRoutes);
app.use('/api/favorites', favoriteRoutes);
app.use('/api/reviews', reviewRoutes);
app.use('/api/visits', visitRoutes);

app.get('/health', (req, res) => res.send('OK'));

// Global error handling middleware
app.use((err, req, res, _next) => {
  console.error('Unhandled error:', err.message, err.stack);
  res.status(500).json({ error: 'Internal Server Error', message: err.message });
});

if (require.main === module) {
  app.listen(PORT, () => {
    console.log(`Server running on port ${PORT}`);
  });
}

module.exports = app;
