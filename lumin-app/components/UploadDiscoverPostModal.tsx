'use client';

import { useState } from 'react';
import { X } from 'lucide-react';
import type { Interest, VideoPost } from '@/lib/types';
import { VideoUploader } from './MerchantPosts';

interface UploadDiscoverPostModalProps {
  posterName: string;
  // Same lifted list DiscoverOnboarding/SettingsScreen use — see page.tsx's
  // fetch for why this isn't a local import of the mock list anymore.
  interests: Interest[];
  onSave: (post: VideoPost) => void | Promise<void>;
  onCancel: () => void;
  // Set to change a post that is already up: only the caption and topics can change (not the video itself).
  editing?: VideoPost;
}

export function UploadDiscoverPostModal({
  posterName,
  interests,
  onSave,
  onCancel,
  editing,
}: UploadDiscoverPostModalProps) {
  const [videoUrl, setVideoUrl] = useState('');
  const [thumbnailUrl, setThumbnailUrl] = useState<string | undefined>(undefined);
  // 9:16 is just the starting guess until a real file is picked —
  // VideoUploader's onDimensionsChange below replaces these with the
  // actual file's dimensions, same as PostEditor does for shop posts.
  // See that component's own comment on why this matters: without it,
  // any video that isn't actually 9:16 renders at the wrong aspect
  // ratio the moment it's posted, then visibly resizes once VideoStage
  // catches the mismatch against the real file.
  const [width, setWidth] = useState(1080);
  const [height, setHeight] = useState(1920);
  const [description, setDescription] = useState(editing?.description ?? '');
  const [selectedInterestIds, setSelectedInterestIds] = useState<string[]>(editing?.interestIds ?? []);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const toggleInterest = (id: string) => {
    setSelectedInterestIds((prev) =>
      prev.includes(id) ? prev.filter((existing) => existing !== id) : [...prev, id],
    );
  };

  const canSave = !saving && (editing ? true : videoUrl.length > 0);

  const handleSave = () => {
    if (editing) {
      setSaving(true);
      setSaveError(null);
      Promise.resolve(onSave({ ...editing, description: description.trim(), interestIds: selectedInterestIds }))
        .catch(() => {
          setSaveError("Couldn't save your changes. Check your connection and try again.");
          setSaving(false);
        });
      return;
    }
    onSave({
      id: `discover-${Date.now()}`,
      posterName,
      postedAt: 'Just now',
      description: description.trim(),
      videoUrl,
      thumbnailUrl,
      width,
      height,
      likes: 0,
      comments: 0,
      shares: 0,
      saves: 0,
      interestIds: selectedInterestIds.length > 0 ? selectedInterestIds : undefined,
    });
  };

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/40 lg:items-center">
      <div className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-t-2xl bg-surface p-5 lg:rounded-2xl">
        <div className="mb-4 flex items-center justify-between">
          <p className="text-[14px] font-bold text-text">{editing ? 'Edit Discover post' : 'New Discover post'}</p>
          <button onClick={onCancel} aria-label="Close" className="-m-3 p-3">
            <X size={18} className="text-text-mute" />
          </button>
        </div>

        {editing ? (
          <p className="rounded-lg bg-panel px-3 py-2 text-[12.5px] text-text-mute">
            You can change the caption and topics. To use a different video, delete this post and post again.
          </p>
        ) : (
        <VideoUploader
          videoUrl={videoUrl}
          onChange={setVideoUrl}
          onThumbnailChange={setThumbnailUrl}
          onDimensionsChange={(w, h) => {
            setWidth(w);
            setHeight(h);
          }}
          destinationLabel="Discover"
        />
        )}

        <label className="mb-4 mt-4 block">
          <span className="mb-1 block text-[12.5px] font-bold text-text">
            Caption <span className="font-normal text-text-mute">(optional)</span>
          </span>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            placeholder="Describe this video..."
            className="w-full resize-none rounded-lg border border-line px-3 py-2 text-[13.5px] text-text focus:border-mark focus:outline-none"
          />
        </label>

        <span className="mb-2 block text-[12.5px] font-bold text-text">
          Topics (optional — helps it show up in the right Discover rows)
        </span>
        <div className="mb-4 flex flex-wrap gap-1.5">
          {interests.map((interest) => {
            const selected = selectedInterestIds.includes(interest.id);
            return (
              <button
                key={interest.id}
                onClick={() => toggleInterest(interest.id)}
                aria-pressed={selected}
                className={`rounded-full border px-3 py-1.5 text-[12.5px] font-medium ${
                  selected ? 'fill-violet border-transparent text-white' : 'border-line text-text'
                }`}
              >
                {interest.label}
              </button>
            );
          })}
        </div>

        <button
          onClick={() => canSave && handleSave()}
          disabled={!canSave}
          className="brand-gradient w-full rounded-full py-2.5 text-[13px] font-bold text-white disabled:opacity-40"
        >
          {editing ? (saving ? 'Saving…' : 'Save changes') : 'Post to Discover'}
        </button>
        {saveError && <p className="mt-2 text-[12.5px] font-semibold text-danger">{saveError}</p>}
      </div>
    </div>
  );
}
