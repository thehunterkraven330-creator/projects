import type { SyntheticEvent } from 'react';

// A full-screen layer (the Updates screen, a person's updates, the player, the composer) is drawn with a portal, but React still
// passes its events up to the component that opened it. Opened from a video on desktop, that parent is the video feed, so a scroll
// or a click inside the layer was also taken as a scroll or a click on the feed, which moved to the next video underneath.
// Spread this on the layer's root element and nothing inside it reaches the feed.
const stop = (e: SyntheticEvent) => e.stopPropagation();
export const isolate = {
  onWheel: stop,
  onClick: stop,
  onDoubleClick: stop,
  onMouseDown: stop,
  onPointerDown: stop,
  onTouchStart: stop,
  onTouchMove: stop,
  onTouchEnd: stop,
};
// The marker VideoStage looks for so its arrow-key shortcuts stay quiet while any of these layers is open.
export const LAYER_ATTR = 'data-story-layer';
