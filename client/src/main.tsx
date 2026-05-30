import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { registerSW } from 'virtual:pwa-register';
import App from './App';
import './index.css';

const queryClient = new QueryClient();

// Register service worker for PWA support (production only)
if (import.meta.env.PROD) {
	registerSW({
		onNeedRefresh() {
			console.log("New content available, the app will update on next load.");
		},
		onOfflineReady() {
			console.log("App is ready for offline use.");
		},
	});
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>
);
