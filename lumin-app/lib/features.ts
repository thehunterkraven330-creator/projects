// Feature switches, read at build time.
//
// NEXT_PUBLIC_TWIN_ENABLED=true turns on the twin discovery layer: twin search ("Seen something
// else?"), the Wanted board, the creator twins inbox/impact page, the timeline pins and the
// merchant Demand tab. Off by default. Scanning a video (the Scan buttons, /scan/*) is NOT part
// of this switch: it is always on, and works with this off. Turn it on together with TWIN_ENABLED=true on the
// backend (lumin-backend/README.md, "Switching twins off"). Sellers tagging products on their
// own videos (the product pills) is not part of this switch and always works.
export const TWIN_ENABLED = process.env.NEXT_PUBLIC_TWIN_ENABLED === 'true';
