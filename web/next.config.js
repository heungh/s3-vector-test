/** @type {import('next').NextConfig} */
const isStatic = process.env.STATIC_EXPORT === "1";

// Hosted under /demo on CloudFront; assets and data must be prefixed accordingly.
const BASE_PATH = process.env.BASE_PATH || (isStatic ? "/demo" : "");

const nextConfig = {
  reactStrictMode: true,
  // When building the customer-facing CloudFront bundle we export a fully static
  // site (demo mode). The live app (npm run dev / npm run build) keeps the API route.
  ...(isStatic ? { output: "export", basePath: BASE_PATH, assetPrefix: BASE_PATH, trailingSlash: true } : {}),
  images: { unoptimized: true },
  env: {
    NEXT_PUBLIC_DEMO_MODE: isStatic ? "1" : process.env.NEXT_PUBLIC_DEMO_MODE || "0",
    NEXT_PUBLIC_BASE_PATH: isStatic ? BASE_PATH : "",
  },
};

module.exports = nextConfig;
