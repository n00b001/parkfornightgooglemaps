/**
 * Cloudflare Worker entry point.
 *
 * Static assets (Vite build) are served automatically via the `assets` binding
 * in wrangler.toml. SPA routing (returning index.html for unknown paths) is
 * handled by `[assets.not_found_handling] single_page_app = true`.
 *
 * This Worker currently has no custom logic — it just serves the frontend.
 * Add request/response middleware here if needed (caching, headers, etc.).
 */
export default {
	async fetch(): Promise<Response> {
		// All requests are handled by the static assets binding.
		// This code path is unreachable unless you add custom routing.
		return new Response("OK", { status: 200 });
	},
};
