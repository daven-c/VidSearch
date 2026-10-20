import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tsconfigPaths from "vite-tsconfig-paths";

// https://vite.dev/config/
export default defineConfig({
	plugins: [react(), tsconfigPaths()],
	server: {
		// In dev, /api is forwarded to the FastAPI backend so the app needs no CORS or hardcoded host
		proxy: {
			"/api": {
				target: process.env.VIDSEARCH_API ?? "http://localhost:8000",
				rewrite: (p) => p.replace(/^\/api/, ""),
			},
		},
	},
});
