require("dotenv").config();
const express = require("express");
const cors = require("cors");
const session = require("express-session");
const pgSession = require("connect-pg-simple")(session);
const { Pool } = require("pg");
const passport = require("./config/passport");

const authRoutes = require("./routes/auth");
const placeRoutes = require("./routes/places");
const favoriteRoutes = require("./routes/favorites");
const reviewRoutes = require("./routes/reviews");
const visitRoutes = require("./routes/visits");

// Required environment variables — fail fast if missing
const requiredEnv = [
	"DATABASE_URL",
	"SESSION_SECRET",
	"CLIENT_URL",
	"PORT",
	"GOOGLE_CLIENT_ID",
	"GOOGLE_CLIENT_SECRET",
];
for (const env of requiredEnv) {
	if (!process.env[env]) {
		throw new Error(`Missing required environment variable: ${env}`);
	}
}

const app = express();
const PORT = process.env.PORT;

if (process.env.NODE_ENV === "production") {
	app.set("trust proxy", 1);
}

// PostgreSQL connection (Supabase)
const isSupabase = process.env.DATABASE_URL.includes("pooler.supabase.com");
const pgPool = new Pool({
	connectionString: process.env.DATABASE_URL,
	ssl: isSupabase ? { rejectUnauthorized: false } : false,
});

app.use(
	cors({
		origin: process.env.CLIENT_URL,
		credentials: true,
	}),
);
app.use(express.json());

app.use(
	session({
		store: new pgSession({
			pool: pgPool,
			tableName: "Session",
			createTableIfMissing: true,
		}),
		secret: process.env.SESSION_SECRET,
		resave: false,
		saveUninitialized: false,
		cookie: {
			maxAge: 30 * 24 * 60 * 60 * 1000,
			secure: process.env.NODE_ENV === "production",
			sameSite: process.env.NODE_ENV === "production" ? "none" : "lax",
		},
	}),
);

app.use(passport.initialize());
app.use(passport.session());

// Handle passport errors (e.g., verifier throws)
if (typeof passport.on === "function") {
	passport.on("authenticateFailure", (info) => {
		console.error("Passport authentication failure:", info);
	});
}

app.use("/auth", authRoutes);
app.use("/api/places", placeRoutes);
app.use("/api/favorites", favoriteRoutes);
app.use("/api/reviews", reviewRoutes);
app.use("/api/visits", visitRoutes);

app.get("/health", (_req, res) => res.send("OK"));

// Global error handling middleware
app.use((err, _req, res, _next) => {
	console.error("Unhandled error:", err.message, err.stack);
	res
		.status(500)
		.json({ error: "Internal Server Error", message: err.message });
});

if (require.main === module) {
	app.listen(PORT, () => {
		console.log(`Server running on port ${PORT}`);
	});
}

module.exports = app;
