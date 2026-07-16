import type { NextConfig } from "next";

// Static export — Catalyst Web Client Hosting serves plain files.
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  // Catalyst Web Client Hosting serves the client under /app/, so all routes and
  // _next asset URLs must be prefixed with /app — otherwise CSS/JS resolve to the
  // domain root and 404 (the page renders unstyled).
  basePath: "/app",
};

export default nextConfig;
