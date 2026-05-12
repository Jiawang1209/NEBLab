import type { NextConfig } from "next";

const FASTAPI_URL = process.env.NEBLAB_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${FASTAPI_URL}/:path*`,
      },
    ];
  },
};

export default nextConfig;
