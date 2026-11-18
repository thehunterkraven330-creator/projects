// Turn a story made of words (and/or a picture with a line of text on it) into one ordinary picture, so it is stored,
// shown and removed exactly like any other story. The picture is always 1080 x 1920 (phone shape), the same shape the
// composer previews, so what you see is what is posted.
export const STORY_W = 1080;
export const STORY_H = 1920;

export const BACKGROUNDS: { id: string; css: string; stops: [string, string] }[] = [
  { id: 'night', css: 'linear-gradient(160deg,#1f1f2e,#0b0b12)', stops: ['#1f1f2e', '#0b0b12'] },
  { id: 'ember', css: 'linear-gradient(160deg,#F5334A,#EE5A24)', stops: ['#F5334A', '#EE5A24'] },
  { id: 'ocean', css: 'linear-gradient(160deg,#2563eb,#06b6d4)', stops: ['#2563eb', '#06b6d4'] },
  { id: 'forest', css: 'linear-gradient(160deg,#047857,#84cc16)', stops: ['#047857', '#84cc16'] },
  { id: 'plum', css: 'linear-gradient(160deg,#7c3aed,#db2777)', stops: ['#7c3aed', '#db2777'] },
  { id: 'sand', css: 'linear-gradient(160deg,#f5e6c8,#e8c99a)', stops: ['#f5e6c8', '#e8c99a'] },
];
export const TEXT_COLOURS = ['#ffffff', '#111111', '#ffd60a'];

// Text size as a share of the picture's width: the preview uses the same numbers (container-query units).
export const OVERLAY_SIZE = 0.07;
export const TEXT_ONLY_SIZE = 0.09;
const LINE = 1.25;
const WIDTH_SHARE = 0.84;

function wrap(ctx: CanvasRenderingContext2D, text: string, maxWidth: number): string[] {
  const lines: string[] = [];
  for (const para of text.split('\n')) {
    let line = '';
    for (const word of para.split(/\s+/).filter(Boolean)) {
      const test = line ? `${line} ${word}` : word;
      if (ctx.measureText(test).width <= maxWidth || !line) line = test;
      else {
        lines.push(line);
        line = word;
      }
    }
    lines.push(line);
  }
  return lines;
}

export async function renderStoryImage(opts: {
  text: string;
  colour: string;
  background?: string; // BACKGROUNDS id, for a story of words only
  picture?: ImageBitmap; // for a picture with text on it
}): Promise<Blob> {
  const canvas = document.createElement('canvas');
  canvas.width = STORY_W;
  canvas.height = STORY_H;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('This browser cannot make the picture.');
  if (opts.picture) {
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, STORY_W, STORY_H);
    const k = Math.min(STORY_W / opts.picture.width, STORY_H / opts.picture.height);
    const w = opts.picture.width * k;
    const h = opts.picture.height * k;
    ctx.drawImage(opts.picture, (STORY_W - w) / 2, (STORY_H - h) / 2, w, h);
  } else {
    const bg = BACKGROUNDS.find((b) => b.id === opts.background) ?? BACKGROUNDS[0];
    const g = ctx.createLinearGradient(0, 0, STORY_W * 0.4, STORY_H);
    g.addColorStop(0, bg.stops[0]);
    g.addColorStop(1, bg.stops[1]);
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, STORY_W, STORY_H);
  }
  const text = opts.text.trim();
  if (text) {
    const size = Math.round(STORY_W * (opts.picture ? OVERLAY_SIZE : TEXT_ONLY_SIZE));
    ctx.font = `700 ${size}px system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = opts.colour;
    if (opts.picture) {
      ctx.shadowColor = 'rgba(0,0,0,0.55)';
      ctx.shadowBlur = 14;
    }
    const lines = wrap(ctx, text, STORY_W * WIDTH_SHARE);
    const lh = size * LINE;
    const top = STORY_H / 2 - ((lines.length - 1) * lh) / 2;
    lines.forEach((l, i) => ctx.fillText(l, STORY_W / 2, top + i * lh));
  }
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.88));
  if (!blob) throw new Error('This browser cannot make the picture.');
  return blob;
}
