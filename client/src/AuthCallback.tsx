import React, { useEffect } from "react";
import { supabase } from "./lib/supabase";

/**
 * OAuth callback page — handles the redirect from Google OAuth.
 * Supabase puts the session in the URL hash. This component extracts it
 * and redirects to the main app.
 */
const AuthCallback: React.FC = () => {
	useEffect(() => {
		// Supabase automatically extracts the session from the URL hash
		// when getURL is called. We just need to wait for the session
		// to be set and then redirect.
		const hash = window.location.hash;
		if (hash) {
			// Exchange the code for a session
			supabase.auth
				.exchangeCodeForSession(hash)
				.then(({ error }) => {
					if (error) {
						console.error("OAuth error:", error.message);
						window.location.href = "/";
					} else {
						window.location.href = "/";
					}
				})
				.catch((err) => {
					console.error("OAuth callback error:", err);
					window.location.href = "/";
				});
		} else {
			// No hash — redirect to home
			window.location.href = "/";
		}
	}, []);

	return (
		<div className="flex items-center justify-center h-screen bg-gray-100">
			<div className="text-center">
				<div className="w-16 h-16 border-4 border-blue-50 border-t-blue-600 rounded-full animate-spin mx-auto" />
				<p className="mt-4 text-gray-600 font-bold">Signing in...</p>
			</div>
		</div>
	);
};

export default AuthCallback;
