// @ts-check
import { defineConfig } from "astro/config";

export default defineConfig({
  site: "https://impact.jocal.dev",
  output: "static",
  trailingSlash: "ignore",
  build: {
    format: "directory",
  },
});
