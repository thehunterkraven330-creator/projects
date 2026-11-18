'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { isolate } from '@/lib/isolate';
import { createPortal } from 'react-dom';
import { ArrowLeft, BadgeCheck, Eye, Flag, MoreHorizontal, Trash2, X } from 'lucide-react';
import {
  ApiError,
  deleteStory,
  fileReport,
  listStoryViewers,
  markStorySeen,
  reactToStory,
  STORY_REACTIONS,
  type ApiReportReason,
  type ApiStory,
  type ApiStoryGroup,
  type ApiStoryViewer,
} from '@/lib/api';
import { apiProductToProduct } from '@/lib/adapters';
import { BRAND } from '@/lib/brand';
import { formatMoney } from '@/lib/money';
import { portalTarget } from '@/lib/portal';
import { unitPrice } from '@/lib/price';
import type { Product } from '@/lib/types';
import { ProductThumbnail } from './Thumbnails';
import { STORIES_CHANGED } from '@/lib/storyRings';
import { UserAvatar } from './UserAvatar';
import { StoryAnnouncement } from './StoryAnnouncement';
import { useCountdown } from '@/lib/useCountdown';
import { useStoryActions } from '@/lib/storyActions';

const IMAGE_MS = 6000;
const MAX_CLIP_MS = 15000;
const REASONS: { value: ApiReportReason; label: string }[] = [
  { value: 'spam', label: 'Spam or misleading' },
  { value: 'counterfeit', label: 'Selling fake goods' },
  { value: 'inappropriate', label: 'Inappropriate content' },
  { value: 'harassment', label: 'Harassment or bullying' },
  { value: 'other', label: 'Something else' },
];

interface Props {
  back?: boolean; // opened from a profile picture: show a back arrow instead of a close button
  startStory?: number; // begin at this story instead of the first unseen one
  hostKeeps?: boolean; // the screen under this player stays open, so a profile opened from "Seen by" can come back to it
  onLeave?: () => void; // going to a live or a product: the screen that opened this player should close too, so the person lands there and not back on it
  groups: ApiStoryGroup[];
  startGroup: number;
  onClose: () => void;
  onChanged: () => void; // something was seen or deleted: refresh the row
  onOpenProduct: (product: Product) => void;
  onAddToCart: (product: Product, color: string, size: string) => void;
}

function ago(iso: string): string {
  const m = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  return m < 1 ? 'now' : m < 60 ? `${m}m` : `${Math.floor(m / 60)}h`;
}
function left(iso: string): string {
  const m = Math.max(0, Math.round((new Date(iso).getTime() - Date.now()) / 60000));
  return m < 60 ? `${m}m left` : `${Math.floor(m / 60)}h left`;
}

// Full-screen stories: one person's stories after another. Tap right for next, left for back, hold to pause, X to close.
// The tagged product sits at the bottom with the same View and Add to cart buttons as everywhere else.
export function StoryViewer({ back = false, startStory, onLeave, hostKeeps = false, groups: initial, startGroup, onClose, onChanged, onOpenProduct, onAddToCart }: Props) {
  const [groups, setGroups] = useState(initial);
  const [gi, setGi] = useState(startGroup);
  const [si, setSi] = useState(() => {
    if (startStory !== undefined) return startStory;
    const g = initial[startGroup];
    const firstUnseen = g ? g.stories.findIndex((s) => !s.seen) : -1; // pick up where they left off
    return firstUnseen > 0 ? firstUnseen : 0;
  });
  const actions = useStoryActions();
  const [progress, setProgress] = useState(0);
  const [paused, setPaused] = useState(false);
  const [menu, setMenu] = useState(false);
  const [panel, setPanel] = useState<null | 'viewers' | 'report' | 'delete'>(null);
  const [viewers, setViewers] = useState<ApiStoryViewer[] | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const video = useRef<HTMLVideoElement>(null);
  const holdTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const held = useRef(false);
  const changed = useRef(false);

  const group = groups[gi];
  const story: ApiStory | undefined = group?.stories[si];
  const frozen = paused || menu || panel !== null;
  // How long a picture has been shown, kept outside the effect so pausing and letting go carries on from the same spot instead of starting over.
  const imageElapsed = useRef(0);
  const frozenRef = useRef(false);
  frozenRef.current = frozen;

  const close = useCallback(() => {
    if (changed.current) {
      onChanged();
      window.dispatchEvent(new Event(STORIES_CHANGED)); // the rings around pictures follow
    }
    onClose();
  }, [onChanged, onClose]);

  const next = useCallback(() => {
    if (!group) return close();
    if (si < group.stories.length - 1) setSi(si + 1);
    else if (gi < groups.length - 1) {
      setGi(gi + 1);
      setSi(0);
    } else close();
  }, [group, si, gi, groups.length, close]);

  const prev = useCallback(() => {
    if (si > 0) setSi(si - 1);
    else if (gi > 0) {
      setGi(gi - 1);
      setSi(Math.max(0, groups[gi - 1].stories.length - 1));
    } else setProgress(0);
  }, [si, gi, groups]);

  // Mark seen, once per story.
  useEffect(() => {
    if (!story || group?.is_me) return;
    if (!story.seen) {
      changed.current = true;
      markStorySeen(story.id).catch(() => {});
      setGroups((gs) => gs.map((g, i) => (i === gi ? { ...g, stories: g.stories.map((s) => (s.id === story.id ? { ...s, seen: true } : s)) } : g)));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [story?.id]);

  // Progress: a picture takes 6 seconds; a clip plays to its end (at most 15 seconds).
  useEffect(() => {
    setProgress(0);
    setNote(null);
    imageElapsed.current = 0;
  }, [story?.id]);
  useEffect(() => {
    if (!story || story.media_type !== 'image') return;
    let raf = 0;
    let last = performance.now();
    const tick = (t: number) => {
      if (!frozenRef.current) imageElapsed.current += t - last;
      last = t;
      setProgress(Math.min(1, imageElapsed.current / IMAGE_MS));
      if (imageElapsed.current >= IMAGE_MS) next();
      else raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [story?.id, story?.media_type, next]);
  useEffect(() => {
    const v = video.current;
    if (!v) return;
    if (frozen) v.pause();
    else v.play().catch(() => {
      v.muted = true; // the browser refused sound: play silently rather than not at all
      v.play().catch(() => {});
    });
  }, [frozen, story?.id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (actions?.layersHidden) return; // a profile is showing over this
      if (e.key === 'Escape') close();
      else if (e.key === 'ArrowRight') next();
      else if (e.key === 'ArrowLeft') prev();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [close, next, prev, actions?.layersHidden]);

  const openViewers = () => {
    if (!story) return;
    setMenu(false);
    setPanel('viewers');
    setViewers(null);
    listStoryViewers(story.id).then(setViewers).catch(() => setViewers([]));
  };
  const confirmDelete = async () => {
    if (!story) return;
    try {
      await deleteStory(story.id);
      changed.current = true;
      setPanel(null);
      const remaining = group.stories.filter((s) => s.id !== story.id);
      if (remaining.length === 0) {
        const rest = groups.filter((_, i) => i !== gi);
        if (rest.length === 0) return close();
        setGroups(rest);
        setGi(Math.min(gi, rest.length - 1));
        setSi(0);
      } else {
        setGroups((gs) => gs.map((g, i) => (i === gi ? { ...g, stories: remaining } : g)));
        setSi(Math.min(si, remaining.length - 1));
      }
    } catch {
      setNote("Couldn't delete it. Try again.");
      setPanel(null);
    }
  };
  const react = (emoji: string) => {
    if (!story) return;
    const next = story.my_reaction === emoji ? null : emoji; // tapping it again takes it back
    setGroups((gs) => gs.map((g, i) => (i === gi ? { ...g, stories: g.stories.map((x) => (x.id === story.id ? { ...x, my_reaction: next, seen: true } : x)) } : g)));
    changed.current = true;
    reactToStory(story.id, next).catch(() => setNote("Couldn't send that. Try again."));
  };
  const report = async (reason: ApiReportReason) => {
    if (!story) return;
    try {
      await fileReport({ target_type: 'story', target_id: story.id, reason });
      setNote('Thanks, we got your report.');
    } catch (e) {
      setNote(e instanceof ApiError ? e.message : "Couldn't send your report. Try again.");
    }
    setPanel(null);
  };

  const remaining = useCountdown(story?.event_at);
  const target = portalTarget();
  if (!target || !group || !story) return null;
  const product = story.product ? apiProductToProduct(story.product) : null;
  const saleEnded = story.kind === 'sale' && ((remaining !== null && remaining <= 0) || (!!product && !product.discountPercent)); // no buying at the advertised price after it
  const simple = !!product && !saleEnded && product.inStock && product.sizes.length <= 1 && product.colors.length <= 1;

  const onDown = () => {
    held.current = false;
    holdTimer.current = setTimeout(() => {
      held.current = true;
      setPaused(true);
    }, 220);
  };
  const onUp = (side: 'left' | 'right') => {
    if (holdTimer.current) clearTimeout(holdTimer.current);
    if (held.current) {
      setPaused(false);
      return;
    }
    if (side === 'left') prev();
    else next();
  };

  return createPortal(
    <div role="dialog" data-story-layer {...isolate} aria-label={`${group.author.display_name}'s update`} style={actions?.layersHidden ? { display: 'none' } : undefined} className="fixed inset-0 z-[80] flex items-center justify-center bg-black text-white">
      {/* On a wide screen the back / close button sits at the edge of the screen, not inside the phone-width player */}
      <button type="button" onClick={close} aria-label={back ? 'Back' : 'Close'} className="absolute left-5 top-5 z-[90] hidden h-11 w-11 items-center justify-center rounded-full bg-white/10 hover:bg-white/20 lg:flex">
        {back ? <ArrowLeft size={22} /> : <X size={22} />}
      </button>
      <div className="relative h-full w-full max-w-[480px] overflow-hidden bg-black">
        {story.media_type === 'video' ? (
          <video
            key={story.id}
            ref={video}
            src={story.media_url}
            className="absolute inset-0 h-full w-full object-contain"
            autoPlay
            playsInline
            onTimeUpdate={(e) => {
              const v = e.currentTarget;
              const total = Math.min(v.duration || MAX_CLIP_MS / 1000, MAX_CLIP_MS / 1000);
              setProgress(Math.min(1, v.currentTime / total));
              if (v.currentTime >= total) next();
            }}
            onEnded={next}
          />
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img key={story.id} src={story.media_url} alt={story.caption ?? 'Story'} className="absolute inset-0 h-full w-full object-contain" />
        )}

        {/* tap zones */}
        <button type="button" aria-label="Previous" className="absolute inset-y-0 left-0 z-10 w-1/3" onPointerDown={onDown} onPointerUp={() => onUp('left')} onPointerLeave={() => holdTimer.current && clearTimeout(holdTimer.current)} />
        <button type="button" aria-label="Next" className="absolute inset-y-0 right-0 z-10 w-2/3" onPointerDown={onDown} onPointerUp={() => onUp('right')} onPointerLeave={() => holdTimer.current && clearTimeout(holdTimer.current)} />

        <div className="pointer-events-none absolute inset-x-0 top-0 z-20 bg-gradient-to-b from-black/60 to-transparent px-2.5 pb-6 pt-[max(8px,env(safe-area-inset-top))]">
          <div className="flex gap-1" aria-hidden="true">
            {group.stories.map((s, i) => (
              <span key={s.id} className="h-[3px] flex-1 overflow-hidden rounded-full bg-white/35">
                <span className="block h-full bg-white" style={{ width: `${i < si ? 100 : i === si ? progress * 100 : 0}%` }} />
              </span>
            ))}
          </div>
          <div className="pointer-events-auto mt-2.5 flex items-center gap-2">
            {back && (
              <button type="button" onClick={close} aria-label="Back" className="-ml-1 flex h-9 w-9 items-center lg:hidden justify-center rounded-full">
                <ArrowLeft size={22} />
              </button>
            )}
            <UserAvatar url={group.author.avatar_url} name={group.author.display_name} size={34} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13.5px] font-bold">{group.is_me ? 'Your update' : group.author.display_name}</p>
              <p className="text-[11.5px] text-white/70">{group.is_me ? left(story.expires_at) : ago(story.created_at)}{story.audience === 'followers' ? ' · Followers only' : ''}</p>
            </div>
            <button type="button" onClick={() => setMenu((m) => !m)} aria-label="More" className="flex h-9 w-9 items-center justify-center rounded-full">
              <MoreHorizontal size={20} />
            </button>
            {!back && (
              <button type="button" onClick={close} aria-label="Close" className="flex h-9 w-9 items-center lg:hidden justify-center rounded-full">
                <X size={22} />
              </button>
            )}
          </div>
          {menu && (
            <div className="pointer-events-auto absolute right-12 top-[max(56px,calc(env(safe-area-inset-top)+48px))] w-44 rounded-xl bg-neutral-900 p-1 shadow-xl">
              {group.is_me ? (
                <>
                  <button type="button" onClick={openViewers} className="flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left text-[13.5px] hover:bg-white/10">
                    <Eye size={16} /> Seen by {story.views_count ?? 0}{(story.reactions_count ?? 0) > 0 ? ` · ${story.reactions_count} reacted` : ''}
                  </button>
                  <button type="button" onClick={() => { setMenu(false); setPanel('delete'); }} className="flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left text-[13.5px] text-red-300 hover:bg-white/10">
                    <Trash2 size={16} /> Delete story
                  </button>
                </>
              ) : (
                <button type="button" onClick={() => { setMenu(false); setPanel('report'); }} className="flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left text-[13.5px] hover:bg-white/10">
                  <Flag size={16} /> Report
                </button>
              )}
            </div>
          )}
        </div>

        <div className="pointer-events-none absolute inset-x-0 bottom-0 z-20 space-y-2 bg-gradient-to-t from-black/75 via-black/30 to-transparent px-3 pb-[max(14px,env(safe-area-inset-bottom))] pt-16">
          {group.is_me && story.held && <p className="rounded-lg bg-black/60 px-3 py-2 text-[12px]">Hidden for now: people reported this update and it is being reviewed.</p>}
          {note && <p role="status" className="rounded-lg bg-black/60 px-3 py-2 text-[12px]">{note}</p>}
          {(story.kind === 'live' || story.kind === 'sale') && story.event_at && (
            <StoryAnnouncement
              kind={story.kind}
              eventAt={story.event_at}
              remaining={saleEnded ? 0 : remaining}
              percent={product?.discountPercent}
              onOpenLive={async () => {
                if (remaining !== null && remaining <= 0) {
                  const r = await actions?.watchLiveOf(group.author.id);
                  if (r === 'watching') (onLeave ?? close)();
                  else if (r === 'not_live') setNote(`${group.author.display_name} hasn't gone live yet. Check back soon.`);
                  else setNote("Couldn't check if they're live. Try again.");
                } else {
                  actions?.openLive();
                  (onLeave ?? close)();
                }
              }}
            />
          )}
          {story.caption && <p className="text-[14px] leading-snug drop-shadow">{story.caption}</p>}
          {group.is_me ? (
            <button type="button" onClick={openViewers} className="pointer-events-auto flex items-center gap-1.5 rounded-full bg-black/55 px-3 py-1.5 text-[12.5px] font-semibold">
              <Eye size={15} aria-hidden="true" /> {story.views_count ?? 0}
              {(story.reactions_count ?? 0) > 0 && <span className="text-white/80">· {story.reactions_count} reacted</span>}
              <span className="text-white/60">· Seen by</span>
            </button>
          ) : (
            <div className="pointer-events-auto flex justify-center gap-1.5" role="group" aria-label="React to this update">
              {STORY_REACTIONS.map((e) => (
                <button
                  key={e}
                  type="button"
                  onClick={() => react(e)}
                  aria-pressed={story.my_reaction === e}
                  aria-label={`React ${e}`}
                  className={`flex h-10 w-10 items-center justify-center rounded-full text-[20px] transition-transform active:scale-90 ${story.my_reaction === e ? 'scale-110 bg-white/30' : 'bg-black/40'}`}
                >
                  {e}
                </button>
              ))}
            </div>
          )}
          {product && (
            <div className="pointer-events-auto flex items-center gap-2.5 rounded-2xl bg-white p-2 text-black">
              <button type="button" onClick={() => { onOpenProduct(product); close(); }} className="flex min-w-0 flex-1 items-center gap-2.5 text-left" aria-label={`View ${product.name}`}>
                <span className="relative h-12 w-12 shrink-0 overflow-hidden rounded-lg bg-neutral-200">
                  <ProductThumbnail product={product} className="absolute inset-0 h-full w-full object-cover" />
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-[13px] font-semibold">{product.name}</span>
                  <span className="block text-[13px] font-extrabold">{formatMoney(unitPrice(product))}</span>
                  {story.bought && (
                    <span className="mt-0.5 flex items-center gap-1 text-[11px] font-semibold text-emerald-700">
                      <BadgeCheck size={13} aria-hidden="true" /> Bought on {BRAND.name}
                    </span>
                  )}
                </span>
              </button>
              <button
                type="button"
                onClick={() => {
                  if (simple) {
                    onAddToCart(product, product.colors[0] ?? '', product.sizes[0] ?? '');
                    setNote('Added to cart');
                  } else {
                    onOpenProduct(product);
                    close();
                  }
                }}
                className="brand-gradient shrink-0 rounded-full px-4 py-2 text-[13px] font-bold text-white"
              >
                {simple ? 'Add to cart' : 'View'}
              </button>
            </div>
          )}
        </div>

        {panel && (
          <div className="absolute inset-0 z-30 flex items-end bg-black/60" onClick={() => setPanel(null)}>
            <div className="max-h-[70%] w-full overflow-y-auto rounded-t-2xl bg-neutral-900 p-4 pb-[max(16px,env(safe-area-inset-bottom))]" onClick={(e) => e.stopPropagation()}>
              {panel === 'delete' && (
                <>
                  <p className="text-[15px] font-bold">Delete this update?</p>
                  <p className="mt-1 text-[13px] text-white/70">It will be removed for everyone right away.</p>
                  <div className="mt-4 flex gap-2">
                    <button type="button" onClick={() => setPanel(null)} className="flex-1 rounded-full bg-white/15 py-2.5 text-[14px] font-bold">Keep it</button>
                    <button type="button" onClick={() => void confirmDelete()} className="flex-1 rounded-full bg-red-500 py-2.5 text-[14px] font-bold">Delete</button>
                  </div>
                </>
              )}
              {panel === 'report' && (
                <>
                  <p className="text-[15px] font-bold">Report this update</p>
                  <ul className="mt-2">
                    {REASONS.map((r) => (
                      <li key={r.value}>
                        <button type="button" onClick={() => void report(r.value)} className="w-full rounded-lg px-2 py-3 text-left text-[14px] hover:bg-white/10">{r.label}</button>
                      </li>
                    ))}
                  </ul>
                </>
              )}
              {panel === 'viewers' && (
                <>
                  <p className="text-[15px] font-bold">Seen by {viewers ? viewers.length : story.views_count ?? 0}</p>
                  {viewers === null ? (
                    <p className="mt-3 text-[13px] text-white/60">Loading…</p>
                  ) : viewers.length === 0 ? (
                    <p className="mt-3 text-[13px] text-white/60">Nobody has seen this yet.</p>
                  ) : (
                    <ul className="mt-2 space-y-1">
                      {viewers.map((v) => (
                        <li key={v.user.id}>
                          <button
                            type="button"
                            onClick={() => {
                              actions?.openPoster({ id: v.user.id, name: v.user.display_name, avatar: v.user.avatar_url }, { returnHere: hostKeeps });
                              if (!hostKeeps) (onLeave ?? close)();
                            }}
                            aria-label={`View ${v.user.display_name}'s profile`}
                            className="flex w-full items-center gap-2.5 py-1.5 text-left"
                          >
                            <UserAvatar url={v.user.avatar_url} name={v.user.display_name} size={32} />
                            <span className="min-w-0 flex-1 truncate text-[13.5px]">{v.user.display_name}</span>
                            {v.reaction && <span className="text-[18px]" aria-label={`Reacted ${v.reaction}`}>{v.reaction}</span>}
                            <span className="text-[11.5px] text-white/50">{ago(v.viewed_at)}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>,
    target,
  );
}
