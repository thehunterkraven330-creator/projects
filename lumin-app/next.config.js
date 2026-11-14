/** @type {import('next').NextConfig} */
const nextConfig = {
  // Produces a self-contained .next/standalone build — a minimal
  // server.js plus only the node_modules files actually reached by
  // this app's own import graph, traced automatically — rather than
  // needing the full node_modules directory (dev tooling included)
  // copied into the final Docker image. Dockerfile's runner stage
  // depends on this output existing; without it, that stage would have
  // nothing to copy and the image wouldn't build. Irrelevant to `next
  // dev`/`npm run dev`, so this changes nothing about local development.
  output: 'standalone',
  // Never tell visitors which framework runs the site.
  poweredByHeader: false,
  // Basic browser protections on every page. (No Content-Security-Policy yet: a wrong one blocks payments, maps, video or
  // uploads, so it needs a staging run to get right; see SECURITY_REVIEW.md.)
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          // The address (which can carry a reset-password or share token) is not passed on to other sites.
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'X-Frame-Options', value: 'SAMEORIGIN' },
          { key: 'Strict-Transport-Security', value: 'max-age=31536000' },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
