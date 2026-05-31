import type { Handler } from "hono";
import { getSupabase } from "../utils/db.ts";
import { getUser, type SupabaseUser } from "../utils/auth.ts";

/**
 * GET /api/favorites
 */
export const getFavorites: Handler = async (c) => {
	const user = getUser(c);
	const supabase = getSupabase();

	const { data, error } = await supabase
		.from("favorite")
		.select(`
      *,
      place (
        *,
        type (id, englishName, originalCode),
        placeServices (placeId, serviceId, service (id, code, label, originalCode))
      )
    `)
		.eq("userId", user.id);

	if (error) {
		console.error("Error fetching favorites:", error.message);
		return c.json({ error: "Failed" }, 500);
	}

	return c.json(data ?? []);
};

/**
 * POST /api/favorites
 */
export const addFavorite: Handler = async (c) => {
	const user = getUser(c);
	const body = await c.req.json();
	const placeId = parseInt(body.placeId);
	const supabase = getSupabase();

	// Check if favorite already exists
	const { data: existing } = await supabase
		.from("favorite")
		.select("id")
		.eq("userId", user.id)
		.eq("placeId", placeId)
		.single();

	if (existing) {
		return c.json(existing);
	}

	const { data, error } = await supabase
		.from("favorite")
		.insert({ userId: user.id, placeId })
		.select()
		.single();

	if (error) {
		console.error("Error adding favorite:", error.message);
		return c.json({ error: "Failed" }, 500);
	}

	return c.json(data);
};

/**
 * DELETE /api/favorites/:id
 */
export const removeFavorite: Handler = async (c) => {
	const user = getUser(c);
	const placeId = parseInt(c.req.param("id"));
	const supabase = getSupabase();

	const { error } = await supabase
		.from("favorite")
		.delete()
		.eq("userId", user.id)
		.eq("placeId", placeId);

	if (error) {
		console.error("Error removing favorite:", error.message);
		return c.json({ error: "Failed" }, 500);
	}

	return c.json({ success: true });
};
