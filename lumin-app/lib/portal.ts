// Where a popup, menu or sheet should be drawn. Normally the page body, but while a video area is full screen the browser draws
// only that element (and what is inside it): a menu portalled to the body would be there but invisible, so the three-dot menu,
// the share sheet and the like did nothing in full screen. Inside the full-screen element they show.
export function portalTarget(): HTMLElement {
  if (typeof document === 'undefined') return undefined as unknown as HTMLElement;
  const d = document as Document & { webkitFullscreenElement?: Element | null };
  const fs = document.fullscreenElement ?? d.webkitFullscreenElement ?? null;
  return fs instanceof HTMLElement ? fs : document.body;
}
