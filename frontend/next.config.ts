import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/:path*",
      },
      {
        source: "/api/v1/ws/:path*",
        destination: "http://localhost:8000/v1/ws/:path*",
      },
    ];
  },
};

export default nextConfig;
