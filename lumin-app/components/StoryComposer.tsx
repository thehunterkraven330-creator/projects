'use client';

import { isolate } from '@/lib/isolate';
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { Camera, Image as ImageIcon, Package, Type, X } from 'lucide-react';
import { ApiError, createStory, listMyMerchantProducts, search, uploadFile, type ApiProduct } from '@/lib/api';
import { BRAND } from '@/lib/brand';
import { portalTarget } from '@/lib/portal';
import { shrinkImage } from '@/lib/shrinkImage';
import { BACKGROUNDS, OVERLAY_SIZE, TEXT_COLOURS, TEXT_ONLY_SIZE, renderStoryImage } from '@/lib/storyImage';

const MAX_CLIP_SECONDS = 15;
const MAX_CLIP_BYTES = 40 * 1024 * 1024; // a story is short: keep uploads (and everyone's data) small
const CAPTION_MAX = 200;

interface Props {
  onClose: () => void;
  onPosted: () => void;
}

const WORDS_MAX = 180;
const OVERLAY_MAX = 80;

// The phone-shaped (9:16) box the story is previewed in: the same shape and text size the posted picture is drawn with.
function Phone({ background, children }: { background?: string; children: ReactNode }) {
  const wrap = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  useLayoutEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const calc = () => {
      const w = Math.max(0, Math.min(el.clientWidth, (el.clientHeight * 9) / 16));
      setSize({ w, h: (w * 16) / 9 });
    };
    calc();
    const ro = new ResizeObserver(calc);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return (
    <div ref={wrap} className="mx-auto flex min-h-[300px] w-full max-w-[460px] flex-1 items-center justify-center">
      <div className="relative overflow-hidden rounded-2xl bg-black [container-type:inline-size]" style={{ width: size.w, height: size.h, background }}>
        {children}
      </div>
    </div>
  );
}

// Words in the middle of the picture, typed right there. Grows with what is typed.
function TextBox({ value, onChange, max, size, colour, placeholder, autoFocus }: { value: string; onChange: (v: string) => void; max: number; size: number; colour: string; placeholder: string; autoFocus?: boolean }) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, [value]);
  return (
    <textarea
      ref={ref}
      rows={1}
      autoFocus={autoFocus}
      value={value}
      maxLength={max}
      onChange={(e) => onChange(e.target.value.slice(0, max))}
      placeholder={placeholder}
      aria-label={placeholder}
      className="absolute left-[8%] top-1/2 w-[84%] -translate-y-1/2 resize-none bg-transparent text-center font-bold placeholder:opacity-50 focus:outline-none"
      style={{ fontSize: `${size * 100}cqw`, lineHeight: 1.25, color: colour, textShadow: size === OVERLAY_SIZE ? '0 1px 6px rgba(0,0,0,0.55)' : undefined }}
    />
  );
}

// The value a datetime-local box wants: local time, to the minute.
function localInput(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

// Add a story: a picture or a clip of up to 15 seconds, an optional caption, optionally a product, and who can see it.
// It disappears after 24 hours.
export function StoryComposer({ onClose, onPosted }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [isVideo, setIsVideo] = useState(false);
  const [caption, setCaption] = useState('');
  const [writing, setWriting] = useState(false); // a story of words only
  const [words, setWords] = useState('');
  const [bg, setBg] = useState(BACKGROUNDS[0].id);
  const [colour, setColour] = useState(TEXT_COLOURS[0]);
  const [overlay, setOverlay] = useState(''); // a line of text on a picture
  const [addingText, setAddingText] = useState(false);
  const [audience, setAudience] = useState<'everyone' | 'followers'>('everyone');
  const [product, setProduct] = useState<ApiProduct | null>(null);
  const [tagging, setTagging] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<ApiProduct[]>([]);
  const [kind, setKind] = useState<'post' | 'live' | 'sale'>('post');
  const [eventAt, setEventAt] = useState(() => localInput(new Date(Date.now() + 2 * 3600_000)));
  const [mine, setMine] = useState<ApiProduct[] | null>(null); // the poster's own products, null until loaded
  const [salePercent, setSalePercent] = useState(20);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const camera = useRef<HTMLInputElement>(null);
  const gallery = useRef<HTMLInputElement>(null);

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  // The poster's own products, so a seller picks from their list instead of typing the name. A buyer has none: the list stays empty.
  useEffect(() => {
    if (!tagging || mine !== null) return;
    let alive = true;
    listMyMerchantProducts()
      .then((r) => alive && setMine(r))
      .catch(() => alive && setMine([]));
    return () => {
      alive = false;
    };
  }, [tagging, mine]);

  useEffect(() => {
    if (!tagging || kind === 'sale' || query.trim().length < 2) {
      setResults([]);
      return;
    }
    let alive = true;
    const t = setTimeout(() => {
      search({ q: query.trim(), filter: 'product', limit: 8 })
        .then((r) => alive && setResults(r.products?.items ?? []))
        .catch(() => alive && setResults([]));
    }, 250);
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, [query, tagging, kind]);

  const pick = (f: File | undefined) => {
    if (!f) return;
    setError(null);
    const video = f.type.startsWith('video/');
    if (!video && !f.type.startsWith('image/')) {
      setError('Choose a picture or a video.');
      return;
    }
    if (video && f.size > MAX_CLIP_BYTES) {
      setError(`That clip is too big (max ${Math.round(MAX_CLIP_BYTES / (1024 * 1024))} MB). Try a shorter one.`);
      return;
    }
    const url = URL.createObjectURL(f);
    if (!video) {
      setFile(f);
      setIsVideo(false);
      setPreview(url);
      return;
    }
    const probe = document.createElement('video');
    probe.preload = 'metadata';
    probe.onloadedmetadata = () => {
      if (probe.duration > MAX_CLIP_SECONDS + 0.5) {
        URL.revokeObjectURL(url);
        setError(`Clips can be up to ${MAX_CLIP_SECONDS} seconds. Trim it and try again.`);
        return;
      }
      setFile(f);
      setIsVideo(true);
      setPreview(url);
    };
    probe.onerror = () => {
      // some browsers can't read the length: let it through, the viewer stops at the limit anyway
      setFile(f);
      setIsVideo(true);
      setPreview(url);
    };
    probe.src = url;
  };

  const post = async () => {
    if ((!file && !(writing && words.trim())) || busy) return;
    setError(null);
    let when: string | undefined;
    if (kind !== 'post') {
      const t = new Date(eventAt).getTime();
      if (Number.isNaN(t) || t <= Date.now()) return setError('Pick a time that is still ahead.');
      if (t > Date.now() + 24 * 3600_000) return setError('Updates last 24 hours, so pick a time within the next 24 hours.');
      if (kind === 'sale' && !product) return setError('Tag one of your products for a flash sale.');
      if (kind === 'sale' && salePercent <= (product?.discount_percent ?? 0)) return setError('A flash sale has to be a bigger discount than the product has now.');
      when = new Date(t).toISOString();
    }
    setBusy(true);
    try {
      let body: Blob;
      let video = false;
      if (!file) {
        body = await renderStoryImage({ text: words, colour, background: bg }); // a story of words only
      } else if (!isVideo && overlay.trim()) {
        const bmp = await createImageBitmap(file);
        try {
          body = await renderStoryImage({ text: overlay, colour, picture: bmp });
        } finally {
          bmp.close?.();
        }
      } else {
        video = isVideo;
        body = isVideo ? file : await shrinkImage(file, 1080);
      }
      const { url } = await uploadFile(body);
      await createStory({
        media_url: url,
        media_type: video ? 'video' : 'image',
        caption: file ? caption.trim() || undefined : undefined,
        product_id: product?.id,
        audience: kind === 'post' ? audience : 'everyone',
        kind,
        event_at: when,
        sale_percent: kind === 'sale' ? salePercent : undefined,
      });
      window.dispatchEvent(new Event('lumin:stories-changed'));
      onPosted();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : e instanceof TypeError ? "Couldn't reach the server. Check your connection and try again." : 'Something went wrong. Please try again.');
      setBusy(false);
    }
  };

  const target = portalTarget();
  if (!target) return null;
  return createPortal(
    <div role="dialog" data-story-layer {...isolate} onKeyDown={(e) => e.stopPropagation()} onKeyUp={(e) => e.stopPropagation()} aria-label="Add an update" className="fixed inset-0 z-[85] flex flex-col overflow-y-auto bg-black text-white">
      <div className="flex shrink-0 items-center justify-between px-3 pb-2 pt-[max(12px,env(safe-area-inset-top))]">
        <button type="button" onClick={onClose} aria-label="Close" className="flex h-9 w-9 items-center justify-center rounded-full bg-white/15">
          <X size={20} />
        </button>
        <p className="text-[14px] font-bold">Your update</p>
        <span className="w-9" />
      </div>

      {!file && !writing ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 px-8 text-center">
          <p className="max-w-[280px] text-[13.5px] text-white/70">A picture or a clip of up to {MAX_CLIP_SECONDS} seconds. It disappears after 24 hours.</p>
          <input ref={camera} type="file" accept="image/*,video/*" capture="environment" className="hidden" onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ''; }} />
          <input ref={gallery} type="file" accept="image/*,video/*" className="hidden" onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ''; }} />
          <button type="button" onClick={() => camera.current?.click()} className="brand-gradient flex w-full max-w-[280px] items-center justify-center gap-2 rounded-full py-3 text-[14px] font-bold text-white">
            <Camera size={18} /> Take a photo or video
          </button>
          <button type="button" onClick={() => gallery.current?.click()} className="flex w-full max-w-[280px] items-center justify-center gap-2 rounded-full bg-white/15 py-3 text-[14px] font-bold">
            <ImageIcon size={18} /> Choose from your gallery
          </button>
          <button type="button" onClick={() => setWriting(true)} className="flex w-full max-w-[280px] items-center justify-center gap-2 rounded-full bg-white/15 py-3 text-[14px] font-bold">
            <Type size={18} /> Write something
          </button>
          {error && <p role="alert" className="max-w-[280px] text-[12.5px] text-red-300">{error}</p>}
        </div>
      ) : (
        <>
          {file ? (
            <Phone>
              {isVideo ? (
                // eslint-disable-next-line jsx-a11y/media-has-caption
                <video src={preview ?? undefined} className="absolute inset-0 h-full w-full object-contain" autoPlay loop muted playsInline />
              ) : (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={preview ?? undefined} alt="Your update" className="absolute inset-0 h-full w-full object-contain" />
              )}
              {!isVideo && addingText && (
                <TextBox value={overlay} onChange={setOverlay} max={OVERLAY_MAX} size={OVERLAY_SIZE} colour={colour} placeholder="Type something…" autoFocus />
              )}
              {!isVideo && !addingText && overlay.trim() && (
                <button type="button" onClick={() => setAddingText(true)} aria-label="Edit text" className="absolute left-[8%] top-1/2 w-[84%] -translate-y-1/2 whitespace-pre-wrap break-words text-center font-bold" style={{ fontSize: `${OVERLAY_SIZE * 100}cqw`, lineHeight: 1.25, color: colour, textShadow: '0 1px 6px rgba(0,0,0,0.55)' }}>
                  {overlay}
                </button>
              )}
              <button type="button" onClick={() => { setFile(null); setPreview(null); setOverlay(''); setAddingText(false); }} className="absolute left-2 top-2 rounded-full bg-black/55 px-3 py-1 text-[12px] font-semibold">
                Change
              </button>
              {!isVideo && (
                <button type="button" onClick={() => setAddingText((v) => !v)} aria-label="Add text to the picture" className="absolute right-2 top-2 flex items-center gap-1 rounded-full bg-black/55 px-3 py-1 text-[12px] font-semibold">
                  <Type size={14} /> {addingText ? 'Done' : 'Text'}
                </button>
              )}
            </Phone>
          ) : (
            <Phone background={BACKGROUNDS.find((b) => b.id === bg)?.css}>
              <TextBox value={words} onChange={setWords} max={WORDS_MAX} size={TEXT_ONLY_SIZE} colour={colour} placeholder="Write something…" autoFocus />
              <button type="button" onClick={() => { setWriting(false); setWords(''); }} className="absolute left-2 top-2 rounded-full bg-black/55 px-3 py-1 text-[12px] font-semibold text-white">
                Back
              </button>
            </Phone>
          )}

          {(!file || (!isVideo && addingText)) && (
            <div className="mx-auto flex w-full max-w-[460px] shrink-0 items-center gap-2 px-3 pt-2.5">
              {!file &&
                BACKGROUNDS.map((b) => (
                  <button key={b.id} type="button" onClick={() => setBg(b.id)} aria-label={`Background ${b.id}`} aria-pressed={bg === b.id} className={`h-7 w-7 rounded-full border-2 ${bg === b.id ? 'border-white' : 'border-transparent'}`} style={{ background: b.css }} />
                ))}
              <span className="flex-1" />
              {TEXT_COLOURS.map((c) => (
                <button key={c} type="button" onClick={() => setColour(c)} aria-label={`Text colour ${c}`} aria-pressed={colour === c} className={`h-7 w-7 rounded-full border-2 ${colour === c ? 'border-white' : 'border-white/30'}`} style={{ background: c }} />
              ))}
            </div>
          )}

          <div className="mx-auto w-full max-w-[460px] shrink-0 space-y-2 px-3 pb-[max(12px,env(safe-area-inset-bottom))] pt-3">
            {file && (
            <input
              value={caption}
              onChange={(e) => setCaption(e.target.value.slice(0, CAPTION_MAX))}
              placeholder="Add a caption…"
              aria-label="Caption"
              className="w-full rounded-xl bg-white/15 px-3.5 py-2.5 text-[14px] text-white placeholder:text-white/50 focus:outline-none"
            />
            )}

            <div className="flex gap-2" role="radiogroup" aria-label="Type of update">
              {([['post', 'Update'], ['live', 'Going live'], ['sale', 'Flash sale']] as const).map(([k, label]) => (
                <button
                  key={k}
                  type="button"
                  role="radio"
                  aria-checked={kind === k}
                  onClick={() => setKind(k)}
                  className={`flex-1 rounded-full py-2 text-[13px] font-bold ${kind === k ? 'bg-white text-black' : 'bg-white/15 text-white'}`}
                >
                  {label}
                </button>
              ))}
            </div>
            {kind !== 'post' && (
              <label className="block rounded-xl bg-white/15 px-3 py-2 text-[12.5px] font-semibold">
                {kind === 'live' ? 'When are you going live?' : 'When does the sale end?'}
                <input
                  type="datetime-local"
                  value={eventAt}
                  min={localInput(new Date())}
                  max={localInput(new Date(Date.now() + 24 * 3600_000))}
                  onChange={(e) => setEventAt(e.target.value)}
                  className="mt-1 block w-full rounded-lg bg-black/30 px-3 py-2 text-[14px] text-white [color-scheme:dark] focus:outline-none"
                />
                {kind === 'sale' && (
                  <>
                    <span className="mt-2.5 block">How much off?</span>
                    <span className="mt-1 flex gap-1.5" role="radiogroup" aria-label="Sale discount">
                      {[10, 20, 30, 50].map((n) => (
                        <button key={n} type="button" role="radio" aria-checked={salePercent === n} onClick={() => setSalePercent(n)} className={`flex-1 rounded-full py-1.5 text-[13px] font-bold ${salePercent === n ? 'bg-white text-black' : 'bg-black/30 text-white'}`}>
                          {n}%
                        </button>
                      ))}
                    </span>
                    <span className="mt-1.5 block text-[11.5px] font-normal text-white/60">Tag one of your products below. The price drops while the sale runs and goes back by itself when it ends or if you delete this update.</span>
                  </>
                )}
              </label>
            )}

            {product ? (
              <div className="flex items-center gap-2 rounded-xl bg-white/15 px-3 py-2">
                <Package size={16} className="shrink-0" />
                <span className="min-w-0 flex-1 truncate text-[13px] font-semibold">{product.name}</span>
                <button type="button" onClick={() => setProduct(null)} aria-label="Remove product" className="shrink-0 text-white/70">
                  <X size={16} />
                </button>
              </div>
            ) : tagging ? (
              <div className="rounded-xl bg-white/15 p-2">
                <input
                  autoFocus
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={kind === 'sale' ? 'Search your products…' : 'Search for a product…'}
                  aria-label="Search for a product to tag"
                  className="w-full rounded-lg bg-black/30 px-3 py-2 text-[13.5px] text-white placeholder:text-white/50 focus:outline-none"
                />
                {(() => {
                  const q = query.trim().toLowerCase();
                  const own = (mine ?? []).filter((p) => !q || p.name.toLowerCase().includes(q));
                  const ownIds = new Set((mine ?? []).map((p) => p.id));
                  const others = results.filter((p) => !ownIds.has(p.id));
                  const choose = (p: ApiProduct) => {
                    setProduct(p);
                    setTagging(false);
                    setQuery('');
                  };
                  return (
                    <ul className="mt-1.5 max-h-48 overflow-y-auto">
                      {own.length > 0 && <li className="px-2 pb-1 pt-1.5 text-[11px] font-bold tracking-wide text-white/50">YOUR PRODUCTS</li>}
                      {own.map((p) => (
                        <li key={p.id}>
                          <button type="button" onClick={() => choose(p)} className="w-full truncate rounded-lg px-2 py-2 text-left text-[13px] hover:bg-white/10">
                            {p.name}
                          </button>
                        </li>
                      ))}
                      {kind !== 'sale' && others.length > 0 && <li className="px-2 pb-1 pt-1.5 text-[11px] font-bold tracking-wide text-white/50">ALL PRODUCTS</li>}
                      {kind !== 'sale' &&
                        others.map((p) => (
                          <li key={p.id}>
                            <button type="button" onClick={() => choose(p)} className="w-full truncate rounded-lg px-2 py-2 text-left text-[13px] hover:bg-white/10">
                              {p.name}
                            </button>
                          </li>
                        ))}
                      {mine !== null && own.length === 0 && (kind === 'sale' || others.length === 0) && (
                        <li className="px-2 py-2 text-[12.5px] text-white/60">{kind === 'sale' ? 'You have no products matching that.' : query.trim().length < 2 ? 'Type to search for a product.' : 'No products found.'}</li>
                      )}
                    </ul>
                  );
                })()}
              </div>
            ) : (
              <button type="button" onClick={() => setTagging(true)} className="flex w-full items-center gap-2 rounded-xl bg-white/15 px-3 py-2.5 text-[13.5px] font-semibold">
                <Package size={16} /> Tag a product
              </button>
            )}

            <div className={`flex gap-2 ${kind !== 'post' ? 'hidden' : ''}`} role="radiogroup" aria-label="Who can see it">
              {(['everyone', 'followers'] as const).map((a) => (
                <button
                  key={a}
                  type="button"
                  role="radio"
                  aria-checked={audience === a}
                  onClick={() => setAudience(a)}
                  className={`flex-1 rounded-full py-2 text-[13px] font-bold ${audience === a ? 'bg-white text-black' : 'bg-white/15 text-white'}`}
                >
                  {a === 'everyone' ? 'Everyone' : 'Followers only'}
                </button>
              ))}
            </div>

            {error && <p role="alert" className="text-[12.5px] text-red-300">{error}</p>}
            <button type="button" disabled={busy || (!file && !words.trim())} onClick={() => void post()} className="brand-gradient w-full rounded-full py-3 text-[14.5px] font-bold text-white disabled:opacity-60">
              {busy ? 'Posting…' : `Post to your ${BRAND.name} updates`}
            </button>
            <p className="text-center text-[11.5px] text-white/50">Disappears after 24 hours. You can delete it any time.</p>
          </div>
        </>
      )}
    </div>,
    target,
  );
}
