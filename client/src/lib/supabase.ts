import { createClient } from "@supabase/supabase-js";
import { api } from "./api";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

if (!supabaseUrl) throw new Error("Missing VITE_SUPABASE_URL");
if (!supabaseAnonKey) throw new Error("Missing VITE_SUPABASE_ANON_KEY");

export const supabase = createClient(supabaseUrl, supabaseAnonKey);

export type User = {
	id: string;
	email: string;
	name: string | null;
	avatar: string | null;
};

/**
 * Fetch the app user profile from the worker API.
 */
export async function getUserProfile(): Promise<User | null> {
	const {
		data: { session },
	} = await supabase.auth.getSession();
	if (!session) return null;

	try {
		const data = await api("get-user");
		return data;
	} catch (err) {
		console.error("Failed to get user profile:", err);
		return null;
	}
}

/**
 * Sign in with Google OAuth.
 * Redirects to Google consent screen, then back to the app.
 */
export async function signInWithGoogle(): Promise<void> {
	const { error } = await supabase.auth.signInWithOAuth({
		provider: "google",
		options: {
			redirectTo: window.location.origin,
		},
	});

	if (error) {
		throw error;
	}
}

/**
 * Sign out the current user.
 */
export async function signOut(): Promise<void> {
	const { error } = await supabase.auth.signOut();
	if (error) {
		throw error;
	}
}
