import type { Handler } from "hono";
import { getSupabase } from "../utils/db.ts";
import { getUser } from "../utils/auth.ts";

/**
 * GET /api/visits
 */
export const getVisits: Handler = async (c) => {
	const user = getUser(c);
	const supabase = getSupabase();

	const { data, error } = await supabase
		.from("visit")
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
		console.error("Error fetching visits:", error.message);
		return c.json({ error: "Failed" }, 500);
	}

	return c.json(data ?? []);
};

/**
 * POST /api/visits
 */
export const recordVisit: Handler = async (c) => {
	const user = getUser(c);
	const body = await c.req.json();
	const placeId = parseInt(body.placeId);
	const supabase = getSupabase();

	// Upsert: check if exists, update or insert
	const { data: existing } = await supabase
		.from("visit")
		.select("id, visitedAt")
		.eq("userId", user.id)
		.eq("placeId", placeId)
		.single();

	if (existing) {
		// Update visitedAt
		const { data, error } = await supabase
			.from("visit")
			.update({ visitedAt: new Date().toISOString() })
			.eq("userId", user.id)
			.eq("placeId", placeId)
			.select()
			.single();

		if (error) {
			console.error("Error updating visit:", error.message);
			return c.json({ error: "Failed" }, 500);
		}
		return c.json(data);
	}

	// Insert new visit
	const { data, error } = await supabase
		.from("visit")
		.insert({
			userId: user.id,
			placeId,
			visitedAt: new Date().toISOString(),
		})
		.select()
		.single();

	if (error) {
		console.error("Error recording visit:", error.message);
		return c.json({ error: "Failed" }, 500);
	}

	return c.json(data);
};
