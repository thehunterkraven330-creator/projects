// Scan a screenshot or photo. The picture is shrunk on the device first (a phone screenshot is several MB; the server needs
// about 1300 px), which keeps the upload small on mobile data. If the browser can't shrink it, the original is sent.
import { scanImage, type ApiScanImage } from './api';

const MAX_SIDE = 1300;
const MAX_ORIGINAL_BYTES = 8 * 1024 * 1024;

async function shrink(file: File): Promise<Blob> {
  try {
    if (typeof createImageBitmap !== 'function' || typeof document === 'undefined') return file;
    const bmp = await createImageBitmap(file);
    const k = Math.min(1, MAX_SIDE / Math.max(bmp.width, bmp.height));
    if (k >= 1 && file.size <= 1_500_000) {
      bmp.close?.();
      return file; // already small
    }
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(bmp.width * k));
    canvas.height = Math.max(1, Math.round(bmp.height * k));
    const ctx = canvas.getContext('2d');
    if (!ctx) return file;
    ctx.drawImage(bmp, 0, 0, canvas.width, canvas.height);
    bmp.close?.();
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.88));
    return blob ?? file;
  } catch {
    return file; // e.g. a format this browser can't decode: let the server try
  }
}

export async function scanPicture(file: File): Promise<ApiScanImage> {
  const picture = await shrink(file);
  if (picture.size > MAX_ORIGINAL_BYTES) throw new Error('That picture is too large. Try a screenshot instead.');
  return scanImage(picture);
}
