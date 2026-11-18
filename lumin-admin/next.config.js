/** @type {import('next').NextConfig} */
const nextConfig = {
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
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'Strict-Transport-Security', value: 'max-age=31536000' },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
