import type { Handler } from "hono";
import { getSupabase } from "../utils/db.ts";
import { getUser } from "../utils/auth.ts";

/**
 * GET /api/reviews/:placeId
 */
export const getReviews: Handler = async (c) => {
	const placeId = parseInt(c.req.param("placeId"));
	const supabase = getSupabase();

	const { data, error } = await supabase
		.from("review")
		.select(`
      *,
      user (id, email, name, avatar)
    `)
		.eq("placeId", placeId)
		.order("createdAt", { ascending: false });

	if (error) {
		console.error("Error fetching reviews:", error.message);
		return c.json({ error: "Failed" }, 500);
	}

	return c.json(data ?? []);
};

/**
 * POST /api/reviews
 */
export const addReview: Handler = async (c) => {
	const user = getUser(c);
	const body = await c.req.json();
	const placeId = parseInt(body.placeId);
	const content = body.content;
	const rating = parseInt(body.rating);
	const supabase = getSupabase();

	const { data, error } = await supabase
		.from("review")
		.insert({
			userId: user.id,
			placeId,
			content,
			rating,
		})
		.select()
		.single();

	if (error) {
		console.error("Error adding review:", error.message);
		return c.json({ error: "Failed" }, 500);
	}

	return c.json(data);
};
