const prisma = require("../config/db");
const { transformPlace } = require("../services/placeTransform");

const getFavorites = async (req, res) => {
	if (!req.isAuthenticated())
		return res.status(401).json({ error: "Unauthorized" });
	try {
		const favorites = await prisma.favorite.findMany({
			where: { userId: req.user.id },
			include: {
				place: {
					include: {
						type: true,
						placeServices: { include: { service: true } },
					},
				},
			},
		});
		res.json(favorites.map((f) => ({ ...f, place: transformPlace(f.place) })));
	} catch (_error) {
		res.status(500).json({ error: "Failed" });
	}
};

const addFavorite = async (req, res) => {
	if (!req.isAuthenticated())
		return res.status(401).json({ error: "Unauthorized" });
	const { placeId } = req.body;
	try {
		const favorite = await prisma.favorite.upsert({
			where: {
				userId_placeId: { userId: req.user.id, placeId: parseInt(placeId) },
			},
			update: {},
			create: { userId: req.user.id, placeId: parseInt(placeId) },
		});
		res.json(favorite);
	} catch (_error) {
		res.status(500).json({ error: "Failed" });
	}
};

const removeFavorite = async (req, res) => {
	if (!req.isAuthenticated())
		return res.status(401).json({ error: "Unauthorized" });
	try {
		await prisma.favorite.delete({
			where: {
				userId_placeId: {
					userId: req.user.id,
					placeId: parseInt(req.params.id),
				},
			},
		});
		res.json({ success: true });
	} catch (_error) {
		res.status(500).json({ error: "Failed" });
	}
};

module.exports = { getFavorites, addFavorite, removeFavorite };
