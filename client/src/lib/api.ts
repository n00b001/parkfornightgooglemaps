import { supabase } from "./supabase";

/**
 * Call an API endpoint on the Cloudflare Worker.
 * The worker serves both the frontend and API on the same domain,
 * so we use relative URLs like /functions/v1/get-places.
 */
export async function api(
  functionName: string,
  options?: {
    method?: "GET" | "POST" | "DELETE";
    body?: Record<string, unknown>;
    searchParams?: Record<string, string>;
  },
) {
  const {
    method = "GET",
    body,
    searchParams,
  } = options ?? {};

  // Build URL
  const url = new URL(`/functions/v1/${functionName}`, window.location.origin);
  if (searchParams) {
    for (const [key, value] of Object.entries(searchParams)) {
      url.searchParams.set(key, value);
    }
  }

  // Get auth token
  const {
    data: { session },
  } = await supabase.auth.getSession();
  const token = session?.access_token;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(url, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({
      error: `HTTP ${response.status}`,
    }));
    throw new Error(error.error ?? `HTTP ${response.status}`);
  }

  return response.json();
}
