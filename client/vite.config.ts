import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'Park4Night Google Maps',
        short_name: 'P4N-GM',
        theme_color: '#ffffff',
        icons: []
      }
    })
  ]
});
