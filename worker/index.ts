/**
 * Cloudflare Worker entry point.
 *
 * Proxies /api/* requests to Supabase Edge Functions.
 * All other requests are served as static assets (Vite SPA build).
 */

const SUPABASE_URL = "https://vsfbbzqiljbtcesremjn.supabase.co";

export default {
	async fetch(request: Request, env: Record<string, unknown>): Promise<Response> {
		const url = new URL(request.url);

		// Proxy /api/* to Supabase Edge Functions
		if (url.pathname.startsWith("/api/")) {
			const edgeUrl = `${SUPABASE_URL}/functions/v1${url.pathname}${url.search}`;

			const headers = new Headers(request.headers);
			headers.set("host", `${SUPABASE_URL}`);

			const response = await fetch(edgeUrl, {
				method: request.method,
				headers,
				body: request.method !== "GET" && request.method !== "HEAD" ? request.body : undefined,
			});

			// Add CORS headers for direct browser access
			const corsHeaders = new Headers(response.headers);
			corsHeaders.set("Access-Control-Allow-Origin", url.origin);
			corsHeaders.set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS");
			corsHeaders.set("Access-Control-Allow-Headers", "Content-Type, Authorization");

			if (request.method === "OPTIONS") {
				return new Response(null, { status: 204, headers: corsHeaders });
			}

			return new Response(response.body, {
				status: response.status,
				statusText: response.statusText,
				headers: corsHeaders,
			});
		}

		// Serve static assets (SPA)
		const assets = env.ASSETS as { fetch: typeof fetch };
		return assets.fetch(request);
	},
};
