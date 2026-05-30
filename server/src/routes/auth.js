const express = require("express");
const passport = require("passport");
const router = express.Router();

router.get("/google", (req, res, next) => {
	const { returnTo } = req.query;
	const state = returnTo
		? Buffer.from(JSON.stringify({ returnTo })).toString("base64")
		: undefined;
	passport.authenticate("google", { scope: ["profile", "email"], state })(
		req,
		res,
		next,
	);
});

router.get("/google/callback", (req, res, next) => {
	passport.authenticate(
		"google",
		{ failureRedirect: "/auth/login" },
		(err, user, info) => {
			if (err) {
				console.error("Google OAuth callback error:", err.message, err.stack);
				return res
					.status(500)
					.json({ error: "Authentication failed", message: err.message });
			}
			if (!user) {
				return res.status(401).json({
					error: "Authentication failed",
					message: info?.message,
				});
			}
			req.login(user, (loginErr) => {
				if (loginErr) {
					console.error(
						"Login session error:",
						loginErr.message,
						loginErr.stack,
					);
					return res.status(500).json({
						error: "Session creation failed",
						message: loginErr.message,
					});
				}

				let returnTo = process.env.CLIENT_URL;
				if (req.query.state) {
					try {
						const state = JSON.parse(
							Buffer.from(req.query.state, "base64").toString(),
						);
						if (state.returnTo) {
							returnTo = state.returnTo;
						}
					} catch (e) {
						console.error("Error parsing state:", e);
					}
				}

				if (returnTo && !returnTo.startsWith("http")) {
					returnTo = `https://${returnTo}`;
				}

				res.redirect(returnTo);
			});
		},
	)(req, res, next);
});

router.get("/me", (req, res) => res.json(req.user || null));

router.get("/logout", (req, res) => {
	req.logout((err) => {
		if (err) return res.status(500).json({ error: "Failed to logout" });
		req.session.destroy();
		res.clearCookie("connect.sid");
		res.json({ success: true });
	});
});

module.exports = router;
