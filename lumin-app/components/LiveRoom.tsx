'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ChevronLeft, Eye, Flag, Heart, Mic, MicOff, Send, UserX, Video, VideoOff, Volume2 } from 'lucide-react';
import {
  ApiError,
  endLive,
  getLiveChat,
  getToken,
  joinLive,
  liveHeartbeat,
  sendLiveHearts,
  sendLiveMessage,
  setLiveThumbnail,
  startLiveRecording,
  type ApiLiveJoin,
  type ApiLiveMessage,
  type ApiProduct,
  listModeratedLive,
  moderateLive,
  type ApiModeratedPerson,
} from '@/lib/api';
import { formatCount } from '@/lib/format';
import { useLuminLite } from '@/lib/lite';
import type { Product } from '@/lib/types';
import { LiveProducts } from './LiveProducts';
import { LiveReportDialog } from './LiveReportDialog';
import { UserAvatar } from './UserAvatar';

// Only the parts of livekit-client this screen uses, described here so the screen does not depend on the library's own types
// (the library is loaded on demand, so that nothing of it is downloaded until someone opens a live).
interface LkTrack {
  kind: string;
  attach: (el: HTMLMediaElement) => HTMLMediaElement;
  detach: () => unknown;
}
interface LkRoom {
  connect(url: string, token: string): Promise<unknown>;
  disconnect(): unknown;
  on(event: string, cb: (...args: never[]) => void): unknown;
  canPlaybackAudio: boolean;
  startAudio(): Promise<unknown>;
  localParticipant: {
    setCameraEnabled(on: boolean, options?: object): Promise<unknown>;
    setMicrophoneEnabled(on: boolean): Promise<unknown>;
    getTrackPublication(source: string): { track?: LkTrack } | undefined;
  };
}
interface LkModule {
  Room: new (options?: object) => LkRoom;
  RoomEvent: Record<string, string>;
  Track: { Source: Record<string, string> };
}

const CHAT_POLL_MS = 2000;
// Most hearts floated for other people's taps per poll, however many arrived: a flood looks like a flood, not a thousand icons.
const MAX_FLOATED_PER_POLL = 14;
// A playful spread, not one brand colour: reds and pinks, oranges and yellows, a green, a teal, blues and purples.
const HEART_COLOURS = [
  '#FF3B6B', '#FF6B35', '#FFB020', '#FACC15', '#34D399', '#22D3EE', '#3B82F6', '#8B5CF6', '#D946EF', '#F472B6', '#FB7185', '#A3E635',
];
let heartSeq = 0;
const HEARTBEAT_MS = 20000;

interface LiveRoomProps {
  // Watching: the live's id. Broadcasting: the join that came back from starting it.
  id?: string;
  hostJoin?: ApiLiveJoin;
  onBack: () => void;
  onSelectProduct?: (product: Product) => void;
  onNeedLogin: () => void;
}

type Tone = 'overlay' | 'panel';

function messageLine(m: ApiLiveMessage, tone: Tone, onPick?: (m: ApiLiveMessage) => void) {
  const nameCls = tone === 'overlay' ? 'text-white/70' : 'text-text-mute';
  const bodyCls = tone === 'overlay' ? 'text-white' : 'text-text';
  return (
    <li
      key={m.id}
      onClick={onPick && m.user_id && !m.is_host ? () => onPick(m) : undefined}
      className={`flex items-start gap-2 py-[3px] ${onPick && m.user_id && !m.is_host ? 'cursor-pointer' : ''}`}
    >
      <span className="mt-[1px] h-6 w-6 shrink-0">
        <UserAvatar url={m.avatar_url} name={m.name} />
      </span>
      <span className={`min-w-0 flex-1 break-words text-[13.5px] leading-snug ${bodyCls}`}>
        <span className={`mr-1.5 font-extrabold ${nameCls}`}>
          {m.name}
          {m.is_host && (
            <span className="ml-1 rounded bg-[#E0245E] px-1 py-px align-middle text-[9px] font-extrabold uppercase tracking-wide text-white">Host</span>
          )}
        </span>
        {m.body}
      </span>
    </li>
  );
}

export function LiveRoom({ id, hostJoin, onBack, onSelectProduct, onNeedLogin }: LiveRoomProps) {
  const isHost = Boolean(hostJoin);
  const [join, setJoin] = useState<ApiLiveJoin | null>(hostJoin ?? null);
  const [error, setError] = useState<string | null>(null);
  const [mediaError, setMediaError] = useState<string | null>(null);
  const [ended, setEnded] = useState(false);
  const [picked, setPicked] = useState<ApiLiveMessage | null>(null); // host: the chat line they tapped
  const [modList, setModList] = useState<ApiModeratedPerson[] | null>(null); // host: muted / removed people, when the list is open
  const [modBusy, setModBusy] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [removed, setRemoved] = useState<string | null>(null); // host took me out of this live
  const [chatOff, setChatOff] = useState(false);
  const [hasVideo, setHasVideo] = useState(false);
  const lite = useLuminLite();
  const liteRef = useRef(lite);
  liteRef.current = lite;
  const tierRef = useRef({ w: 1280, h: 720, bitrate: 2_000_000 });
  const [needsAudio, setNeedsAudio] = useState(false);
  const [micOn, setMicOn] = useState(true);
  const [camOn, setCamOn] = useState(true);
  const [confirmEnd, setConfirmEnd] = useState(false);
  const [viewers, setViewers] = useState(hostJoin?.stream.viewer_count ?? 0);
  const [messages, setMessages] = useState<ApiLiveMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  // Hearts currently floating up: each has its own colour, sideways drift and delay so a burst fans out.
  const [hearts, setHearts] = useState<{ key: number; colour: string; drift: number; delay: number; size: number; tilt: number }[]>([]);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const roomRef = useRef<LkRoom | null>(null);
  const lastId = useRef(0);
  const lastHearts = useRef<number | null>(null);
  const ownUnsent = useRef(0); // my taps not yet sent to the server
  const ownSentSincePoll = useRef(0); // my taps the next poll's total will already include (so they are not floated twice)
  // Two chat lists exist (a mobile overlay and a desktop panel); only one is on screen, but both are refs-free: they scroll to
  // the newest line by id.
  const mobileListRef = useRef<HTMLUListElement | null>(null);
  const desktopListRef = useRef<HTMLUListElement | null>(null);

  const streamId = join?.stream.id;
  const stream = join?.stream;

  // Watching: ask to join (needs an account — it is what lets people chat and be counted).
  useEffect(() => {
    if (isHost || !id) return;
    if (!getToken()) {
      onNeedLogin();
      return;
    }
    let off = false;
    joinLive(id)
      .then((j) => !off && setJoin(j))
      .catch((e) => {
        if (off) return;
        if (e instanceof ApiError && e.status === 409) setEnded(true);
        else setError(e instanceof ApiError ? e.message : "Couldn't open this live. Check your connection and try again.");
      });
    return () => {
      off = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, isHost]);

  // The video: connect to LiveKit. The host publishes camera + microphone; everyone else just plays what arrives.
  useEffect(() => {
    if (!join || ended) return;
    let cancelled = false;
    let room: LkRoom | null = null;
    (async () => {
      try {
        const lk = (await import('livekit-client')) as unknown as LkModule;
        if (cancelled) return;
        // Product reviews need a sharp picture, so everyone gets full HD. The only exception is someone who has chosen to
        // save data themselves (Lumin Lite or the browser's Data Saver), who gets a lighter stream.
        const saver = liteRef.current || Boolean((navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData);
        const tier = saver
          ? { w: 1280, h: 720, bitrate: 2_000_000 }
          : { w: 1920, h: 1080, bitrate: 6_000_000 };
        const r = new lk.Room({
          // Viewers: the stream is picked for the size the video is SHOWN at (a phone-sized video gets a mid-size stream,
          // not the full-HD one), and it steps down further when the connection cannot keep up. Large desktop screens
          // ask for full screen density.
          adaptiveStream: { pixelDensity: saver ? 1 : 'screen' },
          dynacast: true,
          // Host: capture and send at the tier above; LiveKit also makes smaller copies so weaker viewers stay smooth.
          videoCaptureDefaults: { resolution: { width: tier.w, height: tier.h, frameRate: 30 } },
          publishDefaults: { simulcast: true, videoCodec: 'h264', videoEncoding: { maxBitrate: tier.bitrate, maxFramerate: 30 }, degradationPreference: 'maintain-resolution' },
        });
        tierRef.current = tier;
        room = r;
        roomRef.current = r;
        r.on(lk.RoomEvent['TrackSubscribed'], ((track: LkTrack) => {
          if (videoRef.current) track.attach(videoRef.current);
          if (track.kind === 'video') setHasVideo(true);
        }) as never);
        r.on(lk.RoomEvent['TrackUnsubscribed'], ((track: LkTrack) => {
          track.detach();
          if (track.kind === 'video') setHasVideo(false);
        }) as never);
        r.on(lk.RoomEvent['AudioPlaybackStatusChanged'], (() => setNeedsAudio(!r.canPlaybackAudio)) as never);
        await r.connect(join.url, join.token);
        if (cancelled) {
          void r.disconnect();
          return;
        }
        setNeedsAudio(!r.canPlaybackAudio);
        if (join.is_host) {
          try {
            await r.localParticipant.setCameraEnabled(true, { resolution: { width: tierRef.current.w, height: tierRef.current.h, frameRate: 30 } });
            await r.localParticipant.setMicrophoneEnabled(true);
          } catch {
            setMediaError('Allow camera and microphone access in your browser to go live.');
            return;
          }
          const cam = r.localParticipant.getTrackPublication(lk.Track.Source['Camera']);
          if (cam?.track && videoRef.current) {
            cam.track.attach(videoRef.current);
            setHasVideo(true);
          }
          // The room exists now, so it can be recorded (a failed recording never affects the live).
          startLiveRecording(join.stream.id).catch(() => {});
        }
      } catch {
        if (!cancelled) setMediaError("Couldn't connect to the live video. Check your connection and try again.");
      }
    })();
    return () => {
      cancelled = true;
      roomRef.current = null;
      if (room) void room.disconnect();
    };
  }, [join, ended]);

  const addMessages = useCallback((list: ApiLiveMessage[]) => {
    if (list.length === 0) return;
    setMessages((prev) => {
      const seen = new Set(prev.map((m) => m.id));
      const merged = [...prev, ...list.filter((m) => !seen.has(m.id))].sort((a, b) => a.id - b.id);
      return merged.slice(-200);
    });
    lastId.current = Math.max(lastId.current, ...list.map((m) => m.id));
  }, []);

  const floatHearts = useCallback((n: number) => {
    const born = Array.from({ length: Math.min(n, MAX_FLOATED_PER_POLL) }, (_, i) => ({
      key: ++heartSeq,
      colour: HEART_COLOURS[Math.floor(Math.random() * HEART_COLOURS.length)],
      drift: Math.round((Math.random() - 0.5) * 110),
      delay: Math.round(i * 90 + Math.random() * 120),
      size: 20 + Math.round(Math.random() * 16),
      tilt: Math.round((Math.random() - 0.5) * 50),
    }));
    if (born.length === 0) return;
    setHearts((prev) => [...prev, ...born].slice(-40));
    // Each heart's animation is ~2.4s; drop them from state after.
    window.setTimeout(() => {
      const gone = new Set(born.map((h) => h.key));
      setHearts((prev) => prev.filter((h) => !gone.has(h.key)));
    }, 2800 + MAX_FLOATED_PER_POLL * 90);
  }, []);

  // Chat, viewer count and "has it ended" all come from one poll.
  useEffect(() => {
    if (!streamId || ended || removed) return;
    let stop = false;
    const tick = async () => {
      if (document.hidden) return; // nobody is looking: no need to use data
      try {
        const page = await getLiveChat(streamId, lastId.current);
        if (stop) return;
        addMessages(page.messages);
        setViewers(page.viewer_count);
        // Hearts from everyone else since the last poll (my own already floated when I tapped).
        if (lastHearts.current !== null) {
          const others = page.hearts - lastHearts.current - ownSentSincePoll.current;
          if (others > 0) floatHearts(others);
        }
        lastHearts.current = page.hearts;
        ownSentSincePoll.current = 0;
        if (page.status === 'ended') setEnded(true);
      } catch (e) {
        if (e instanceof ApiError && e.status === 403 && !isHost) setRemoved("The host removed you from this live.");
        // any other missed poll is fine, the next one catches up
      }
    };
    void tick();
    const t = setInterval(() => void tick(), CHAT_POLL_MS);
    return () => {
      stop = true;
      clearInterval(t);
    };
  }, [streamId, ended, removed, isHost, addMessages, floatHearts]);

  // Host only: tell the server the broadcast is still going, and end it if the page is closed.
  useEffect(() => {
    if (!isHost || !streamId || ended) return;
    const beat = () => {
      liveHeartbeat(streamId)
        .then((r) => r.status === 'ended' && setEnded(true))
        .catch(() => {});
    };
    beat();
    const t = setInterval(beat, HEARTBEAT_MS);
    const onHide = () => void endLive(streamId, true).catch(() => {});
    window.addEventListener('pagehide', onHide);
    return () => {
      clearInterval(t);
      window.removeEventListener('pagehide', onHide);
    };
  }, [isHost, streamId, ended]);

  // Host only: a still from the live's own video becomes the tile's picture. First one a few seconds after the camera is
  // up, then refreshed every minute so the tile keeps looking like what is on air. Never matters to the broadcast.
  useEffect(() => {
    if (!isHost || !streamId || ended || !hasVideo) return;
    let stop = false;
    const snap = () => {
      const v = videoRef.current;
      if (stop || !v || v.videoWidth === 0) return;
      try {
        const w = 480;
        const h = Math.round((v.videoHeight / v.videoWidth) * w);
        const canvas = document.createElement('canvas');
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        ctx.drawImage(v, 0, 0, w, h);
        canvas.toBlob(
          (blob) => {
            if (blob && !stop) setLiveThumbnail(streamId, blob).catch(() => {});
          },
          'image/jpeg',
          0.8,
        );
      } catch {
        /* a frame that cannot be read is skipped */
      }
    };
    const first = setTimeout(snap, 4000);
    const t = setInterval(snap, 60000);
    return () => {
      stop = true;
      clearTimeout(first);
      clearInterval(t);
    };
  }, [isHost, streamId, ended, hasVideo]);

  // Send my taps in small batches (about once a second) rather than one request per tap.
  useEffect(() => {
    if (!streamId || ended) return;
    const t = setInterval(() => {
      const n = Math.min(ownUnsent.current, 30);
      if (n <= 0) return;
      ownUnsent.current -= n;
      ownSentSincePoll.current += n;
      sendLiveHearts(streamId, n).catch(() => {});
    }, 1000);
    return () => clearInterval(t);
  }, [streamId, ended]);

  const tapHeart = () => {
    if (!getToken()) {
      onNeedLogin();
      return;
    }
    floatHearts(1);
    ownUnsent.current += 1;
  };

  // Keep the newest chat line in view.
  useEffect(() => {
    for (const el of [mobileListRef.current, desktopListRef.current]) {
      if (el) el.scrollTop = el.scrollHeight;
    }
  }, [messages]);

  const submit = async () => {
    const text = draft.trim();
    if (!text || !streamId || sending) return;
    if (!getToken()) {
      onNeedLogin();
      return;
    }
    setSending(true);
    try {
      const m = await sendLiveMessage(streamId, text);
      setDraft('');
      addMessages([m]);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) setEnded(true);
      else if (e instanceof ApiError && e.status === 403) setChatOff(true);
    } finally {
      setSending(false);
    }
  };

  const moderate = async (action: 'mute' | 'block') => {
    if (!picked?.user_id || !streamId) return;
    setModBusy(true);
    try {
      await moderateLive(streamId, picked.user_id, action);
      const uid = picked.user_id;
      setMessages((prev) => prev.filter((x) => x.user_id !== uid));
      setPicked(null);
    } catch {
      setPicked(null);
    } finally {
      setModBusy(false);
    }
  };

  const openModList = () => {
    if (!streamId) return;
    setModList([]);
    listModeratedLive(streamId).then(setModList).catch(() => setModList([]));
  };
  const undoModeration = async (userId: string) => {
    if (!streamId) return;
    try {
      await moderateLive(streamId, userId, 'clear');
      setModList((l) => (l ? l.filter((p) => p.user_id !== userId) : l));
    } catch {
      /* the row stays, the host can tap again */
    }
  };

  const finishBroadcast = async () => {
    if (!streamId) return;
    try {
      await endLive(streamId);
    } catch {
      // the heartbeat timing out ends it anyway
    }
    setConfirmEnd(false);
    setEnded(true);
  };

  const toggleMic = () => {
    const next = !micOn;
    setMicOn(next);
    void roomRef.current?.localParticipant.setMicrophoneEnabled(next);
  };
  const toggleCam = () => {
    const next = !camOn;
    setCamOn(next);
    void roomRef.current?.localParticipant.setCameraEnabled(next);
  };

  const products: ApiProduct[] = stream?.products ?? [];

  const chatList = (tone: Tone, ref: React.MutableRefObject<HTMLUListElement | null>, cls: string) => (
    <ul ref={ref} className={`overflow-y-auto overscroll-contain [scrollbar-width:none] [&::-webkit-scrollbar]:hidden ${cls}`}>
      {messages.length === 0 ? (
        <li className={`py-1 text-[12.5px] ${tone === 'overlay' ? 'text-white/70' : 'text-text-mute'}`}>
          {isHost ? 'Chat will show up here.' : 'Say hi — ask about the products.'}
        </li>
      ) : (
        messages.map((m) => messageLine(m, tone, isHost ? setPicked : undefined))
      )}
    </ul>
  );

  const productStrip = (tone: Tone) => <LiveProducts products={products} tone={tone} disabled={isHost} onSelect={onSelectProduct} />;

  const composer = (tone: Tone) => (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
      className="flex items-center gap-2"
    >
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        maxLength={300}
        disabled={chatOff}
        placeholder={chatOff ? 'The host turned off your chat' : getToken() ? 'Add a comment…' : 'Log in to chat'}
        onFocus={() => !getToken() && onNeedLogin()}
        className={`min-w-0 flex-1 rounded-full px-4 py-2.5 text-[14px] outline-none ${
          tone === 'overlay' ? 'bg-black/50 text-white placeholder:text-white/60 backdrop-blur-md' : 'bg-box text-text placeholder:text-text-mute'
        }`}
      />
      {!isHost && (
        <button
          type="button"
          onClick={tapHeart}
          aria-label="Send a heart"
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-[#E0245E] active:scale-90 ${
            tone === 'overlay' ? 'bg-black/50 backdrop-blur-md' : 'bg-box'
          }`}
        >
          <Heart size={20} fill="currentColor" />
        </button>
      )}
      <button
        type="submit"
        disabled={!draft.trim() || sending}
        aria-label="Send"
        className="brand-gradient flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-white disabled:opacity-40"
      >
        <Send size={16} />
      </button>
    </form>
  );

  const hostRow = (tone: Tone) =>
    stream && (
      <div className="flex min-w-0 items-center gap-2">
        <span className="h-9 w-9 shrink-0 overflow-hidden rounded-full ring-2 ring-[#E0245E]">
          <UserAvatar url={stream.host_avatar_url} name={stream.host_name} />
        </span>
        <span className="min-w-0">
          <span className={`block truncate text-[13.5px] font-extrabold leading-tight ${tone === 'overlay' ? 'text-white' : 'text-text'}`}>
            {stream.title}
          </span>
          <span className={`block truncate text-[11.5px] ${tone === 'overlay' ? 'text-white/75' : 'text-text-mute'}`}>
            {stream.business_name ?? stream.host_name}
          </span>
        </span>
      </div>
    );

  const statusPills = (
    <span className="flex shrink-0 items-center gap-1.5">
      <span className="inline-flex items-center gap-1 rounded-md bg-[#E0245E] px-1.5 py-[3px] text-[10px] font-extrabold uppercase tracking-wider text-white">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" /> Live
      </span>
      <span className="inline-flex items-center gap-1 rounded-md bg-black/50 px-1.5 py-[3px] text-[11px] font-bold text-white backdrop-blur-sm">
        <Eye size={11} /> {formatCount(viewers)}
      </span>
    </span>
  );

  const hostControls = isHost && (
    <span className="flex items-center gap-2">
      <button
        onClick={toggleMic}
        aria-label={micOn ? 'Mute microphone' : 'Unmute microphone'}
        className="flex h-9 w-9 items-center justify-center rounded-full bg-black/55 text-white backdrop-blur-sm"
      >
        {micOn ? <Mic size={16} /> : <MicOff size={16} />}
      </button>
      <button
        onClick={toggleCam}
        aria-label={camOn ? 'Turn camera off' : 'Turn camera on'}
        className="flex h-9 w-9 items-center justify-center rounded-full bg-black/55 text-white backdrop-blur-sm"
      >
        {camOn ? <Video size={16} /> : <VideoOff size={16} />}
      </button>
      <button
        onClick={openModList}
        aria-label="Muted and removed viewers"
        className="flex h-9 w-9 items-center justify-center rounded-full bg-black/55 text-white backdrop-blur-sm"
      >
        <UserX size={16} />
      </button>
      <button onClick={() => setConfirmEnd(true)} className="rounded-full bg-[#E0245E] px-3.5 py-2 text-[12.5px] font-extrabold text-white">
        End
      </button>
    </span>
  );

  return (
    <div className="dark flex h-full w-full flex-col bg-black lg:flex-row">
      {/* ---- the video ---- */}
      <div className="relative min-h-0 flex-1 bg-black">
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted={isHost}
          className={`absolute inset-0 h-full w-full object-contain ${isHost ? '-scale-x-100' : ''} ${hasVideo && !ended ? '' : 'invisible'}`}
        />

        {!hasVideo && !ended && !error && !mediaError && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-white/80">
            <span className="h-14 w-14 animate-pulse overflow-hidden rounded-full">
              <UserAvatar url={stream?.host_avatar_url} name={stream?.host_name ?? '…'} />
            </span>
            <p className="text-[13px] font-medium">{isHost ? 'Starting your camera…' : 'Waiting for the host…'}</p>
          </div>
        )}

        {/* hearts floating up the right side */}
        <div aria-hidden="true" className="pointer-events-none absolute bottom-28 right-3 z-10 h-[280px] w-16 overflow-visible lg:bottom-8">
          {hearts.map((h) => (
            <span
              key={h.key}
              className="live-heart absolute bottom-0 right-3"
              style={{ color: h.colour, animationDelay: `${h.delay}ms`, '--drift': `${h.drift}px` } as React.CSSProperties}
            >
              <Heart size={h.size} fill={h.colour} stroke={h.colour} style={{ transform: `rotate(${h.tilt}deg)` }} />
            </span>
          ))}
        </div>

        {/* top bar */}
        <div className="absolute inset-x-0 top-0 z-10 flex items-center gap-2 bg-gradient-to-b from-black/70 to-transparent px-3 pb-6 pt-[max(12px,env(safe-area-inset-top))]">
          <button
            onClick={() => (isHost && !ended ? setConfirmEnd(true) : onBack())}
            aria-label={isHost ? 'End live' : 'Leave live'}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-black/55 text-white backdrop-blur-sm"
          >
            <ChevronLeft size={20} />
          </button>
          <span className="min-w-0 flex-1">{hostRow('overlay')}</span>
          {statusPills}
          {hostControls}
          {!isHost && streamId && !ended && (
            <button
              onClick={() => (getToken() ? setReporting(true) : onNeedLogin())}
              aria-label="Report this live"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-black/55 text-white backdrop-blur-sm"
            >
              <Flag size={16} />
            </button>
          )}
        </div>

        {needsAudio && !isHost && !ended && (
          <button
            onClick={() => void roomRef.current?.startAudio()}
            className="absolute left-1/2 top-20 z-10 flex -translate-x-1/2 items-center gap-1.5 rounded-full bg-white px-4 py-2 text-[13px] font-extrabold text-ink shadow-lg"
          >
            <Volume2 size={15} /> Tap to hear
          </button>
        )}

        {/* mobile: chat, products and the comment box sit over the bottom of the video */}
        <div className="absolute inset-x-0 bottom-0 z-10 flex flex-col gap-2 bg-gradient-to-t from-black/80 via-black/40 to-transparent px-3 pb-[max(12px,env(safe-area-inset-bottom))] pt-16 lg:hidden">
          {chatList('overlay', mobileListRef, 'max-h-[30vh] [mask-image:linear-gradient(to_bottom,transparent,black_28%)]')}
          {productStrip('overlay')}
          {!ended && composer('overlay')}
        </div>

        {(error || mediaError) && (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-black/85 px-8 text-center">
            <p className="text-[14px] font-bold text-white">{error ?? mediaError}</p>
            <button onClick={onBack} className="rounded-full bg-white px-5 py-2 text-[13px] font-extrabold text-ink">
              Back
            </button>
          </div>
        )}

        {ended && (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-black/85 px-8 text-center">
            <p className="text-[16px] font-extrabold text-white">{isHost ? 'Your live has ended' : 'This live has ended'}</p>
            <p className="text-[13px] text-white/70">{isHost ? 'Thanks for going live.' : 'Thanks for watching.'}</p>
            <button onClick={onBack} className="brand-gradient rounded-full px-6 py-2.5 text-[13px] font-extrabold text-white">
              Back to New Arrivals
            </button>
          </div>
        )}


        {picked && (
          <div className="absolute inset-0 z-30 flex items-center justify-center bg-black/70 px-8" onClick={() => setPicked(null)}>
            <div onClick={(e) => e.stopPropagation()} className="theme-light w-full max-w-[300px] rounded-2xl bg-surface p-5 text-center text-text">
              <p className="text-[15px] font-extrabold">{picked.name}</p>
              <p className="mt-1 line-clamp-2 text-[13px] text-text-mute">{picked.body}</p>
              <div className="mt-4 flex flex-col gap-2">
                <button
                  disabled={modBusy}
                  onClick={() => void moderate('mute')}
                  className="rounded-full bg-box py-2.5 text-[13px] font-bold disabled:opacity-60"
                >
                  Mute in chat
                </button>
                <button
                  disabled={modBusy}
                  onClick={() => void moderate('block')}
                  className="rounded-full bg-[#E0245E] py-2.5 text-[13px] font-extrabold text-white disabled:opacity-60"
                >
                  Remove from live
                </button>
                <button onClick={() => setPicked(null)} className="py-1.5 text-[13px] font-semibold text-text-mute">
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}

        {modList && (
          <div className="absolute inset-0 z-30 flex items-center justify-center bg-black/70 px-8" onClick={() => setModList(null)}>
            <div onClick={(e) => e.stopPropagation()} className="theme-light w-full max-w-[320px] rounded-2xl bg-surface p-5 text-text">
              <p className="text-center text-[15px] font-extrabold">Muted and removed</p>
              {modList.length === 0 ? (
                <p className="mt-3 text-center text-[13px] text-text-mute">Nobody yet.</p>
              ) : (
                <ul className="mt-3 flex max-h-[50vh] flex-col gap-2 overflow-y-auto">
                  {modList.map((p) => (
                    <li key={p.user_id} className="flex items-center gap-2">
                      <span className="h-8 w-8 shrink-0">
                        <UserAvatar url={p.avatar_url} name={p.name} />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13.5px] font-bold">{p.name}</span>
                        <span className="text-[11.5px] text-text-mute">{p.kind === 'block' ? 'Removed' : 'Muted'}</span>
                      </span>
                      <button onClick={() => void undoModeration(p.user_id)} className="rounded-full bg-box px-3 py-1.5 text-[12px] font-bold">
                        Undo
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <button onClick={() => setModList(null)} className="mt-4 w-full rounded-full bg-box py-2.5 text-[13px] font-bold">
                Close
              </button>
            </div>
          </div>
        )}

        {removed && (
          <div className="absolute inset-0 z-40 flex items-center justify-center bg-black/85 px-8">
            <div className="theme-light w-full max-w-[300px] rounded-2xl bg-surface p-5 text-center text-text">
              <p className="text-[15px] font-extrabold">{removed}</p>
              <button onClick={onBack} className="brand-gradient mt-4 w-full rounded-full py-2.5 text-[13px] font-bold text-white">
                Back to live
              </button>
            </div>
          </div>
        )}

        {reporting && streamId && <LiveReportDialog streamId={streamId} onClose={() => setReporting(false)} />}

        {confirmEnd && (
          <div className="absolute inset-0 z-30 flex items-center justify-center bg-black/70 px-8">
            <div className="w-full max-w-[300px] rounded-2xl bg-surface p-5 text-center text-text">
              <p className="text-[15px] font-extrabold">End your live?</p>
              <p className="mt-1 text-[13px] text-text-mute">Everyone watching will be disconnected.</p>
              <div className="mt-4 flex gap-2">
                <button onClick={() => setConfirmEnd(false)} className="flex-1 rounded-full bg-box py-2.5 text-[13px] font-bold">
                  Keep going
                </button>
                <button onClick={() => void finishBroadcast()} className="flex-1 rounded-full bg-[#E0245E] py-2.5 text-[13px] font-extrabold text-white">
                  End live
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ---- desktop: chat and products in a side panel, like the comments sidebar ---- */}
      <aside className="theme-light hidden w-[360px] shrink-0 flex-col border-l border-line bg-surface lg:flex">
        <div className="border-b border-line px-4 py-3">{hostRow('panel')}</div>
        {products.length > 0 && (
          <div className="border-b border-line px-4 py-3">
            <p className="mb-2 text-[11px] font-extrabold uppercase tracking-[0.14em] text-text-mute">Shown in this live</p>
            {productStrip('panel')}
          </div>
        )}
        <div className="flex min-h-0 flex-1 flex-col px-4 pt-3">{chatList('panel', desktopListRef, 'min-h-0 flex-1')}</div>
        {!ended && <div className="border-t border-line p-3">{composer('panel')}</div>}
      </aside>
    </div>
  );
}
