/**
 * Extract user info from the Authorization header JWT.
 * Supabase platform verifies the JWT signature before the handler runs
 * (when verify_jwt = true, the default). We just decode the payload.
 */
export function getAuthUser(req: Request): { id: string; email: string } {
	const authHeader = req.headers.get("Authorization");
	if (!authHeader) throw new Error("Missing Authorization header");

	const token = authHeader.replace("Bearer ", "");
	if (!token) throw new Error("Missing token");

	const payload = decodeJwt(token);
	if (!payload || !payload.sub) {
		throw new Error("Invalid JWT");
	}

	return { id: payload.sub, email: payload.email };
}

function decodeJwt(token: string): Record<string, unknown> | null {
	try {
		const parts = token.split(".");
		if (parts.length !== 3) throw new Error("Invalid JWT format");
		return JSON.parse(atob(parts[1]));
	} catch {
		return null;
	}
}
