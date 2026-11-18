'use client';

import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { Download, Eye, Flag, MoreVertical, Radio, Trash2, Video, X } from 'lucide-react';
import { ApiError, deleteLive, getWatermarkedLiveDownload, listLive, listLiveReplays, type ApiLiveStream } from '@/lib/api';
import { LiveReportDialog } from './LiveReportDialog';
import { formatCount } from '@/lib/format';
import { PageHeader } from './PageHeader';
import { Loading } from './TwinLoader';
import { UserAvatar } from './UserAvatar';

// How often the list of who is live refreshes while this screen is open.
const REFRESH_MS = 8000;

function LivePill({ className = '' }: { className?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md bg-[#E0245E] px-1.5 py-[3px] text-[10px] font-extrabold uppercase tracking-wider text-white ${className}`}
    >
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" />
      Live
    </span>
  );
}

function Tile({
  stream,
  onOpen,
  replay = false,
  menu,
}: {
  stream: ApiLiveStream;
  onOpen: () => void;
  replay?: boolean;
  // Recent lives only: the three-dot menu, drawn by the screen (it owns the dialogs).
  menu?: ReactNode;
}) {
  const first = stream.products[0];
  const thumb = first?.images?.[0]?.url;
  const still = stream.thumbnail_url;
  return (
    <div className="relative">
      <button
        onClick={onOpen}
        className="group relative block aspect-[3/4] w-full overflow-hidden rounded-xl2 bg-ink text-left shadow-sm transition-transform active:scale-[0.98] lg:hover:-translate-y-0.5"
      >
        {still ? (
          // A frame from the live itself.
          // eslint-disable-next-line @next/next/no-img-element
          <img src={still} alt="" className="absolute inset-0 h-full w-full object-cover" />
        ) : (
          // No still yet (the live just started): the host's picture, blown up and softened.
          <span className="absolute inset-0 scale-125 blur-xl">
            <UserAvatar url={stream.host_avatar_url} name={stream.host_name} shape="square" className="!rounded-none" />
          </span>
        )}
        <span className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/10 to-black/30" />

        <span className="absolute left-2.5 top-2.5 flex items-center gap-1.5">
          {replay ? (
            <span className="inline-flex items-center gap-1 rounded-md bg-black/55 px-1.5 py-[3px] text-[10px] font-extrabold uppercase tracking-wider text-white backdrop-blur-sm">
              Replay
            </span>
          ) : (
            <>
              <LivePill />
              <span className="inline-flex items-center gap-1 rounded-md bg-black/45 px-1.5 py-[3px] text-[10.5px] font-bold text-white backdrop-blur-sm">
                <Eye size={11} /> {formatCount(stream.viewer_count)}
              </span>
            </>
          )}
        </span>

        {!still && (
          <span className="absolute inset-x-0 top-1/2 flex -translate-y-[62%] justify-center">
            <span className="h-20 w-20 overflow-hidden rounded-full ring-2 ring-white/70 ring-offset-2 ring-offset-transparent">
              <UserAvatar url={stream.host_avatar_url} name={stream.host_name} />
            </span>
          </span>
        )}

        <span className="absolute inset-x-0 bottom-0 p-3">
          <span className="line-clamp-2 text-[14px] font-extrabold leading-tight text-white">{stream.title}</span>
          <span className="mt-1.5 flex items-center gap-2">
            {/* The streamer's picture sits beside their name. */}
            <span className="h-6 w-6 shrink-0 overflow-hidden rounded-full ring-1 ring-white/60">
              <UserAvatar url={stream.host_avatar_url} name={stream.host_name} />
            </span>
            <span className="min-w-0 flex-1 truncate text-[12px] font-semibold text-white/90">
              {stream.business_name ?? stream.host_name}
            </span>
            {thumb && !replay && (
              <span className="relative h-7 w-7 shrink-0 overflow-hidden rounded-lg border border-white/50 bg-box">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={thumb} alt="" className="h-full w-full object-cover" />
                {stream.products.length > 1 && (
                  <span className="absolute inset-0 flex items-center justify-center bg-black/55 text-[10px] font-extrabold text-white">
                    +{stream.products.length - 1}
                  </span>
                )}
              </span>
            )}
          </span>
        </span>
      </button>
      {menu}
    </div>
  );
}

// Save the recording to the device: the copy with the platform's mark and end card (made on the server, like a feed video's
// saved copy). If that cannot be made (a very long live, or it is not ready), the plain recording is saved instead. A browser
// that will not let the page read the file gets it opened in a tab so it can still be saved from there.
async function downloadReplay(stream: ApiLiveStream) {
  if (!stream.replay_url) return;
  let url = stream.replay_url;
  try {
    const marked = await getWatermarkedLiveDownload(stream.id);
    if (marked.url) url = marked.url;
  } catch {
    /* fall back to the plain recording */
  }
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error('not ready');
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${stream.title.replace(/[^\w\- ]+/g, '').trim() || 'live'}.mp4`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 10000);
  } catch {
    window.open(url, '_blank', 'noopener');
  }
}

function ReplayMenu({
  stream,
  isOwner,
  onRemoved,
}: {
  stream: ApiLiveStream;
  isOwner: boolean;
  onRemoved: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [dialog, setDialog] = useState<null | 'remove' | 'report'>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const closeAll = () => {
    setOpen(false);
    setDialog(null);
    setNote(null);
  };

  const remove = async () => {
    setBusy(true);
    try {
      await deleteLive(stream.id);
      onRemoved(stream.id);
      closeAll();
    } catch (e) {
      setNote(e instanceof ApiError ? e.message : "Couldn't remove this video. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button
        aria-label="More options"
        onClick={() => setOpen((o) => !o)}
        className="absolute right-2 top-2 z-10 flex h-8 w-8 items-center justify-center rounded-full bg-black/45 text-white backdrop-blur-sm"
      >
        <MoreVertical size={17} />
      </button>
      {open && !dialog && (
        <>
          <div className="fixed inset-0 z-20" onClick={() => setOpen(false)} aria-hidden="true" />
          <div className="absolute right-2 top-11 z-30 w-48 overflow-hidden rounded-xl border border-line bg-surface py-1 shadow-lg">
            {isOwner ? (
              <>
                <button
                  disabled={saving}
                  onClick={() => {
                    setSaving(true);
                    void downloadReplay(stream).finally(() => {
                      setSaving(false);
                      setOpen(false);
                    });
                  }}
                  className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left text-[13.5px] font-semibold text-text hover:bg-box disabled:opacity-60"
                >
                  <Download size={16} /> {saving ? 'Preparing…' : 'Save to device'}
                </button>
                <button
                  onClick={() => setDialog('remove')}
                  className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left text-[13.5px] font-semibold text-red-600 hover:bg-box"
                >
                  <Trash2 size={16} /> Remove video
                </button>
              </>
            ) : (
              <button
                onClick={() => setDialog('report')}
                className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left text-[13.5px] font-semibold text-text hover:bg-box"
              >
                <Flag size={16} /> Report this video
              </button>
            )}
          </div>
        </>
      )}
      {dialog === 'report' && <LiveReportDialog streamId={stream.id} onClose={closeAll} />}
      {dialog === 'remove' && (
        <div className="fixed inset-0 z-[80] flex items-end justify-center bg-black/50 p-4 sm:items-center" onClick={closeAll}>
          <div
            role="dialog"
            aria-modal="true"
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-sm rounded-2xl bg-surface p-5 text-text shadow-xl"
          >
            <div className="flex items-start justify-between gap-3">
              <h3 className="text-[16px] font-extrabold">Remove this video?</h3>
              <button onClick={closeAll} aria-label="Close" className="text-text-mute">
                <X size={18} />
              </button>
            </div>
            <p className="mt-2 text-[13.5px] text-text-mute">
              The recording of &ldquo;{stream.title}&rdquo; will be deleted for everyone. This can&apos;t be undone.
            </p>
            {note && <p className="mt-2 text-[13px] font-semibold text-red-600">{note}</p>}
            <div className="mt-4 flex gap-2">
              <button onClick={closeAll} className="flex-1 rounded-full bg-box py-2.5 text-[13.5px] font-bold">
                Keep it
              </button>
              <button
                onClick={() => void remove()}
                disabled={busy}
                className="flex-1 rounded-full bg-red-600 py-2.5 text-[13.5px] font-bold text-white disabled:opacity-60"
              >
                {busy ? 'Removing…' : 'Remove'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

interface LiveScreenProps {
  onBack: () => void;
  onWatch: (id: string) => void;
  // A recorded live from the Recent lives row.
  onWatchReplay: (stream: ApiLiveStream) => void;
  // Only business accounts get the Go live button.
  canGoLive: boolean;
  onGoLive: () => void;
  // The signed-in user's id, to tell whose recording is whose (owners can save/remove, everyone else can report).
  currentUserId?: string;
}

export function LiveScreen({ onBack, onWatch, onWatchReplay, canGoLive, onGoLive, currentUserId }: LiveScreenProps) {
  const [streams, setStreams] = useState<ApiLiveStream[] | null>(null);
  const [replays, setReplays] = useState<ApiLiveStream[]>([]);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    try {
      setStreams(await listLive());
      setFailed(false);
      // Recent lives are a bonus: if they fail to load the live ones still show.
      listLiveReplays().then(setReplays).catch(() => {});
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    void load();
    const t = setInterval(() => {
      if (!document.hidden) void load();
    }, REFRESH_MS);
    return () => clearInterval(t);
  }, [load]);

  return (
    <div className="flex h-full flex-col bg-surface">
      <PageHeader
        title="New Arrivals"
        onBack={onBack}
        backLabel="Back to shop"
        rightSlot={
          canGoLive ? (
            <button
              onClick={onGoLive}
              className="brand-gradient flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-3.5 py-2 text-[12.5px] font-bold text-white"
            >
              <Video size={14} strokeWidth={2.4} aria-hidden="true" /> Go live
            </button>
          ) : undefined
        }
      />
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[1200px] px-4 py-4 lg:px-8 lg:py-6">
          {streams === null && !failed && <Loading label="Looking for lives…" className="py-24" />}
          {failed && streams === null && (
            <div className="py-16 text-center">
              <p className="text-[13.5px] font-bold text-text">Couldn&apos;t load lives</p>
              <button onClick={() => void load()} className="mt-2 text-[13px] font-bold text-accent-ink">
                Try again
              </button>
            </div>
          )}
          {streams !== null && streams.length === 0 && (
            <div className="flex flex-col items-center gap-2 py-20 text-center">
              <span className="flex h-14 w-14 items-center justify-center rounded-full bg-box text-text-mute">
                <Radio size={24} />
              </span>
              <p className="text-[14.5px] font-extrabold text-text">No one is live right now</p>
              <p className="max-w-[260px] text-[13px] text-text-mute">
                When a seller goes live to show off a product, it shows up here. You can watch, chat and shop from it.
              </p>
              {canGoLive && (
                <button onClick={onGoLive} className="brand-gradient mt-2 rounded-full px-5 py-2.5 text-[13px] font-bold text-white">
                  Go live
                </button>
              )}
            </div>
          )}
          {streams !== null && streams.length > 0 && (
            <>
              <p className="mb-3 flex items-center gap-2 text-[11px] font-extrabold uppercase tracking-[0.14em] text-text-mute">
                <LivePill /> {streams.length} live now
              </p>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 lg:gap-4 xl:grid-cols-5">
                {streams.map((s) => (
                  <Tile key={s.id} stream={s} onOpen={() => onWatch(s.id)} />
                ))}
              </div>
            </>
          )}

          {replays.length > 0 && (
            <>
              <p className="mb-3 mt-8 text-[11px] font-extrabold uppercase tracking-[0.14em] text-text-mute">Recent lives</p>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 lg:gap-4 xl:grid-cols-5">
                {replays.map((s) => (
                  <Tile
                    key={s.id}
                    stream={s}
                    replay
                    onOpen={() => onWatchReplay(s)}
                    menu={
                      <ReplayMenu
                        stream={s}
                        isOwner={Boolean(currentUserId) && s.host_id === currentUserId}
                        onRemoved={(id) => setReplays((prev) => prev.filter((r) => r.id !== id))}
                      />
                    }
                  />
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
