import { createClient, type SupabaseClient } from "npm:@supabase/supabase-js@2";

let supabase: SupabaseClient;

export function getSupabase(): SupabaseClient {
	if (!supabase) {
		supabase = createClient(
			Deno.env.get("SUPABASE_URL")!,
			Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
		);
	}
	return supabase;
}
