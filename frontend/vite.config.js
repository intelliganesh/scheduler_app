import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The React plugin enables the automatic JSX runtime, so components do not need `import React`.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
