import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

// Default Vite config for standalone frontend deployments
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
})
