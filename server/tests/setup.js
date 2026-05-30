// Jest setup — inject required environment variables before module loading.
// server/src/index.js throws if PORT, DIRECT_URL, or SESSION_SECRET are missing.
process.env.PORT = '3100';
process.env.DIRECT_URL = 'postgresql://postgres:postgres@localhost:5432/postgres';
process.env.SESSION_SECRET = 'test-secret';
