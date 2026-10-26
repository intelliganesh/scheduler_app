import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The React plugin enables the automatic JSX runtime, so components do not need `import React`.
export default defineConfig({
  plugins: [react()],
});
