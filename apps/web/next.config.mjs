/** @type {import('next').NextConfig} */

const nextConfig = {
  reactStrictMode: true,
  // Required by the container image: ships a minimal server bundle.
  output: "standalone",

  /*
   * Backend proxying lives in route handlers (src/app/api/*), not here.
   *
   * next.config rewrites are resolved at build time and frozen into the routes
   * manifest, so an image built without the service origins set would proxy to
   * its own localhost regardless of runtime configuration. Route handlers read
   * the environment per request, so one image works everywhere.
   */
};

export default nextConfig;
