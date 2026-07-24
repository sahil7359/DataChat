import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // We lint with our own flat config (`pnpm lint`); Next's bundled
  // eslint-config-next is incompatible with ESLint 9 flat config.
  eslint: { ignoreDuringBuilds: true },
  // The FE is a thin renderer: no secrets, no server intelligence. Only the
  // public API base is exposed to the browser.
  env: {
    NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1",
  },
};

export default nextConfig;
