// Shrink a picture on the device before it is uploaded (a phone photo is several MB; a story is shown at phone size).
// If the browser can't do it, the original goes up unchanged.
export async function shrinkImage(file: File, maxSide: number, quality = 0.85): Promise<Blob> {
  try {
    if (typeof createImageBitmap !== 'function' || typeof document === 'undefined') return file;
    const bmp = await createImageBitmap(file);
    const k = Math.min(1, maxSide / Math.max(bmp.width, bmp.height));
    if (k >= 1 && file.size <= 1_200_000) {
      bmp.close?.();
      return file;
    }
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(bmp.width * k));
    canvas.height = Math.max(1, Math.round(bmp.height * k));
    const ctx = canvas.getContext('2d');
    if (!ctx) return file;
    ctx.drawImage(bmp, 0, 0, canvas.width, canvas.height);
    bmp.close?.();
    return (await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', quality))) ?? file;
  } catch {
    return file;
  }
}
