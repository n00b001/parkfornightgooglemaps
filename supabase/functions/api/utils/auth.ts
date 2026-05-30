import type { Context, MiddlewareHandler } from "hono";
import { createClient } from "npm:@supabase/supabase-js@2";

export interface SupabaseUser {
	id: string;
	email: string | null;
	name: string | null;
	avatar: string | null;
}

/**
 * Hono middleware that verifies the Supabase JWT from the Authorization header.
 * Sets `c.get('user')` to the decoded user object.
 * Returns 401 if the token is invalid or missing.
 */
export const authenticateRequest: MiddlewareHandler = async (c, next) => {
	const authHeader = c.req.header("Authorization");
	if (!authHeader || !authHeader.startsWith("Bearer ")) {
		return c.json({ error: "Unauthorized" }, 401);
	}

	const token = authHeader.slice(7);

	const supabase = createClient(
		Deno.env.get("SUPABASE_URL")!,
		Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
	);

	const {
		data: { user },
		error,
	} = await supabase.auth.getUser(token);
	if (error || !user) {
		return c.json({ error: "Unauthorized" }, 401);
	}

	const supabaseUser: SupabaseUser = {
		id: user.id,
		email: user.email,
		name: user.user_metadata?.full_name || user.user_metadata?.name || null,
		avatar: user.user_metadata?.avatar_url || null,
	};

	c.set("user", supabaseUser);
	await next();
};

/**
 * Get the authenticated user from the Hono context.
 */
export function getUser(c: Context): SupabaseUser {
	return c.get("user");
}
