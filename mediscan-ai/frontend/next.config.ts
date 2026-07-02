import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // No image optimization domains needed — this app doesn't render remote
  // images, only accepts uploads that are sent straight to the backend.
};

export default nextConfig;
