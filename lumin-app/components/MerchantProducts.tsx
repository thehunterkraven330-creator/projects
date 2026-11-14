'use client';

import { useEffect, useRef, useState } from 'react';
import { Camera, ImagePlus, MoreVertical, Plus, Trash2, X } from 'lucide-react';
import type { Category, CategoryBanner, Product } from '@/lib/types';
import { ApiError, getCollectInfo, listMySponsoredTwins, setSponsoredTwin, uploadFile, type ApiSponsoredStats, type SponsoredTags } from '@/lib/api';

import { ProductThumbnail } from './Thumbnails';
import { formatMoney } from '@/lib/money';
function emptyProduct(bannerId: string): Product {
  return {
    id: `mp-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    name: '',
    price: 0,
    cartCount: 0,
    colors: [],
    sizes: [],
    images: [],
    bannerId,
    // Untracked/unlimited by default — same as every product behaved
    // before stock existed. A merchant opts into tracking by actually
    // setting a number in the Stock field below.
    stockQuantity: undefined,
    weightGrams: undefined,
    inStock: true,
  };
}

interface PhotoEntry {
  id: string;
  // blob: while uploading, the real URL once done — either way, what
  // the <img> below actually renders.
  previewUrl: string;
  status: 'uploading' | 'done' | 'error';
  error?: string;
}

// Real files, real uploads — `URL.createObjectURL` gives an instant local
// preview the moment a file's picked, while the actual upload happens in
// the background against POST /uploads. `images` (the value `onChange`
// reports, and so what ends up in the product's image_urls) only ever
// contains real, persistent URLs from entries that finished — never a
// blob: one, which stops resolving the moment this tab closes and would
// leave the saved product pointing at a dead link.
function PhotoUploader({ images, onChange, onBusyChange }: { images: string[]; onChange: (images: string[]) => void; onBusyChange?: (busy: boolean) => void }) {
  const galleryInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  // Seeded once from the incoming images (real URLs already, if editing
  // an existing product) — ProductForm remounts fresh per product being
  // edited, so this only ever needs to run once per editing session, not
  // resync against a prop that changes underneath it.
  const [entries, setEntries] = useState<PhotoEntry[]>(() =>
    images.map((url) => ({ id: url, previewUrl: url, status: 'done' as const })),
  );

  // Tell the form while a photo is still on its way up, so Save can wait for it (a photo still uploading would be left out).
  const uploading = entries.some((e) => e.status === 'uploading');
  useEffect(() => {
    onBusyChange?.(uploading);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uploading]);

  const commit = (next: PhotoEntry[]) => {
    setEntries(next);
    onChange(next.filter((e) => e.status === 'done').map((e) => e.previewUrl));
  };

  const handleFiles = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const fileList = Array.from(files);
    const newEntries: PhotoEntry[] = fileList.map((file) => ({
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      previewUrl: URL.createObjectURL(file),
      status: 'uploading',
    }));
    // No need to route this through commit() — every new entry starts as
    // 'uploading', so filtering to 'done' never includes any of them yet;
    // onChange genuinely has nothing new to report until the first one
    // actually finishes.
    setEntries((prev) => [...prev, ...newEntries]);

    newEntries.forEach((entry, i) => {
      uploadFile(fileList[i])
        .then(({ url }) => {
          URL.revokeObjectURL(entry.previewUrl);
          setEntries((prev) => {
            const next = prev.map((e) => (e.id === entry.id ? { ...e, previewUrl: url, status: 'done' as const } : e));
            onChange(next.filter((e) => e.status === 'done').map((e) => e.previewUrl));
            return next;
          });
        })
        .catch((err) => {
          setEntries((prev) =>
            prev.map((e) =>
              e.id === entry.id
                ? { ...e, status: 'error' as const, error: err instanceof ApiError ? err.message : 'Upload failed' }
                : e,
            ),
          );
        });
    });
  };

  const handleRemove = (id: string) => {
    const target = entries.find((e) => e.id === id);
    // Only revoke a blob: url still standing in for an in-flight upload
    // — a 'done' entry's previewUrl is the real uploaded URL by then,
    // and revoking a non-blob string is a silent no-op anyway, but this
    // keeps the intent explicit.
    if (target?.status === 'uploading' && target.previewUrl.startsWith('blob:')) {
      URL.revokeObjectURL(target.previewUrl);
    }
    commit(entries.filter((e) => e.id !== id));
  };

  return (
    <div>
      <span className="mb-1 block text-[12.5px] font-bold text-text">Photos</span>
      <p className="mb-2 text-[11.5px] text-text-mute">
        Snap one with your camera or pick from your gallery. The first photo is the cover people see first.
      </p>

      <div className="flex flex-wrap gap-2">
        {entries.map((entry) => (
          <div key={entry.id} className="relative h-16 w-16 shrink-0 overflow-hidden rounded-lg border border-line">
            {/* eslint-disable-next-line @next/next/no-img-element -- blob:
                URLs from the file picker (and the real uploaded URLs that
                replace them) aren't compatible with next/image. */}
            <img src={entry.previewUrl} alt="" className="h-full w-full object-cover" />
            {entry.status === 'uploading' && (
              <div className="absolute inset-0 flex items-center justify-center bg-black/40">
                <span className="text-[10.5px] font-bold text-white">Uploading…</span>
              </div>
            )}
            {entry.status === 'error' && (
              <div
                className="absolute inset-0 flex items-center justify-center bg-danger/70 p-1"
                title={entry.error}
              >
                <span className="text-center text-[9.5px] font-bold leading-tight text-white">
                  Failed — remove and retry
                </span>
              </div>
            )}
            <button
              onClick={() => handleRemove(entry.id)}
              aria-label="Remove photo"
              className="absolute right-0.5 top-0.5 flex h-6 w-6 items-center justify-center rounded-full bg-black/60 text-white"
            >
              <X size={12} />
            </button>
          </div>
        ))}

        <button
          onClick={() => cameraInputRef.current?.click()}
          className="flex h-16 w-16 shrink-0 flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-line text-text-mute"
        >
          <Camera size={18} />
          <span className="text-[10.5px]">Camera</span>
        </button>
        {/* `capture="environment"` is what actually opens the device
            camera directly on a phone/tablet instead of just the generic
            file picker — without it, camera access is inconsistent across
            browsers. No `multiple` here: a camera shot is one photo per
            trip, same as taking a real photo would be; tap again to add
            another. Desktop browsers without a camera just ignore
            `capture` and fall back to a normal file picker, so this never
            blocks anyone without one. */}
        <input
          ref={cameraInputRef}
          type="file"
          accept="image/*"
          capture="environment"
          onChange={(e) => {
            handleFiles(e.target.files);
            e.target.value = '';
          }}
          className="hidden"
        />

        <button
          onClick={() => galleryInputRef.current?.click()}
          className="flex h-16 w-16 shrink-0 flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-line text-text-mute"
        >
          <ImagePlus size={18} />
          <span className="text-[10.5px]">Gallery</span>
        </button>
        <input
          ref={galleryInputRef}
          type="file"
          accept="image/*"
          multiple
          onChange={(e) => {
            handleFiles(e.target.files);
            // Reset so selecting the exact same file again still fires
            // onChange — without this, re-picking an identical file after
            // removing it wouldn't register as a new change.
            e.target.value = '';
          }}
          className="hidden"
        />
      </div>
    </div>
  );
}

const PRESET_COLORS: { name: string; hex: string }[] = [
  { name: 'Black', hex: '#1c1c1c' },
  { name: 'White', hex: '#f5f5f5' },
  { name: 'Grey', hex: '#8a8a8a' },
  { name: 'Beige', hex: '#d8cfbd' },
  { name: 'Brown', hex: '#7a5230' },
  { name: 'Red', hex: '#d62839' },
  { name: 'Pink', hex: '#f08aa5' },
  { name: 'Orange', hex: '#ee7a24' },
  { name: 'Yellow', hex: '#f2c230' },
  { name: 'Green', hex: '#3f8f5a' },
  { name: 'Blue', hex: '#2f6fd6' },
  { name: 'Navy', hex: '#1f2f5c' },
  { name: 'Purple', hex: '#7b4bc2' },
];

// Tap the colours the product comes in. Stored as colour codes (what the product page paints its swatches with), so
// nobody has to type one; the round picker at the end adds any other colour.
function ColorPicker({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const has = (hex: string) => value.some((c) => c.toLowerCase() === hex.toLowerCase());
  const toggle = (hex: string) => onChange(has(hex) ? value.filter((c) => c.toLowerCase() !== hex.toLowerCase()) : [...value, hex]);
  const extra = value.filter((c) => !PRESET_COLORS.some((p) => p.hex.toLowerCase() === c.toLowerCase()));
  return (
    <div>
      <span className="mb-1.5 block text-[12.5px] font-bold text-text">
        Colours <span className="font-normal text-text-mute">(tap the ones it comes in)</span>
      </span>
      <div className="flex flex-wrap items-center gap-2">
        {[...PRESET_COLORS, ...extra.map((hex) => ({ name: hex, hex }))].map((c) => (
          <button
            key={c.hex}
            type="button"
            onClick={() => toggle(c.hex)}
            aria-label={c.name}
            aria-pressed={has(c.hex)}
            title={c.name}
            className={`h-9 w-9 rounded-full border-2 ${has(c.hex) ? 'border-mark shadow-[0_0_0_2px_rgb(var(--c-surface))_inset]' : 'border-line'}`}
            style={{ backgroundColor: c.hex }}
          />
        ))}
        <label className="relative flex h-9 w-9 cursor-pointer items-center justify-center rounded-full border border-dashed border-line text-text-mute" title="Another colour">
          <Plus size={16} />
          <input
            type="color"
            aria-label="Pick another colour"
            className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
            onChange={(e) => {
              if (!has(e.target.value)) onChange([...value, e.target.value]);
            }}
          />
        </label>
      </div>
      {value.length > 0 && (
        <p className="mt-1.5 text-[11.5px] text-text-mute">
          {value.length} colour{value.length === 1 ? '' : 's'} chosen. Tap again to remove.
        </p>
      )}
    </div>
  );
}

const PRESET_SIZES = ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'One size'];

function SizePicker({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const [custom, setCustom] = useState('');
  const has = (z: string) => value.includes(z);
  const toggle = (z: string) => onChange(has(z) ? value.filter((x) => x !== z) : [...value, z]);
  const extra = value.filter((z) => !PRESET_SIZES.includes(z));
  const addCustom = () => {
    const z = custom.trim();
    if (z && !has(z)) onChange([...value, z]);
    setCustom('');
  };
  return (
    <div>
      <span className="mb-1.5 block text-[12.5px] font-bold text-text">
        Sizes <span className="font-normal text-text-mute">(optional)</span>
      </span>
      <div className="flex flex-wrap gap-1.5">
        {[...PRESET_SIZES, ...extra].map((z) => (
          <button
            key={z}
            type="button"
            onClick={() => toggle(z)}
            aria-pressed={has(z)}
            className={`rounded-full border px-3.5 py-1.5 text-[12.5px] font-semibold ${has(z) ? 'border-mark bg-panel text-accent-ink' : 'border-line text-text-mute'}`}
          >
            {z}
          </button>
        ))}
      </div>
      <div className="mt-2 flex gap-2">
        <input
          type="text"
          value={custom}
          onChange={(e) => setCustom(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              addCustom();
            }
          }}
          placeholder="Another size, e.g. 42 or 128GB"
          className="min-w-0 flex-1 rounded-lg border border-line px-3 py-2.5 text-base text-text focus:border-mark focus:outline-none sm:text-[13.5px]"
        />
        <button type="button" onClick={addCustom} disabled={!custom.trim()} className="shrink-0 rounded-lg border border-line px-3.5 text-[13px] font-bold text-text disabled:opacity-50">
          Add
        </button>
      </div>
    </div>
  );
}

function ProductForm({
  product,
  categories,
  categoryBanners,
  onSave,
  onCancel,
}: {
  product: Product;
  categories: Category[];
  categoryBanners: CategoryBanner[];
  onSave: (product: Product) => void | Promise<void>;
  onCancel: () => void;
}) {
  const initialBanner = categoryBanners.find((b) => b.id === product.bannerId);
  // A new product starts in the first category that HAS a collection, with that collection chosen, so the picker is never
  // showing one category's collections while holding another's id.
  const firstWithBanner = categories.find((c) => categoryBanners.some((b) => b.categoryId === c.id));
  const startCategory = initialBanner?.categoryId ?? firstWithBanner?.id ?? categories[0]?.id ?? '';
  const [categoryId, setCategoryId] = useState(startCategory);
  const [draft, setDraft] = useState<Product>(() =>
    initialBanner ? product : { ...product, bannerId: categoryBanners.find((b) => b.categoryId === startCategory)?.id ?? '' },
  );
  // Days a buyer has to come and decide (from the server), for the collect-in-person note below.
  const [collectDays, setCollectDays] = useState<number | null>(null);
  useEffect(() => {
    getCollectInfo()
      .then((r) => setCollectDays(r.window_days))
      .catch(() => {});
  }, []);
  const [photosBusy, setPhotosBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const bannersForCategory = categoryBanners.filter((b) => b.categoryId === categoryId);

  const handleCategoryChange = (id: string) => {
    setCategoryId(id);
    const firstBanner = categoryBanners.find((b) => b.categoryId === id);
    setDraft((d) => ({ ...d, bannerId: firstBanner?.id ?? '' }));
  };

  // Only a hint: words that usually mean "too big to post". The server decides by weight (heavier than the courier limit,
  // 30 kg by default, is always collected in person).
  const looksBulky =
    !draft.collectInPerson &&
    /\b(machine|machinery|generator|lathe|press|engine|compressor|forklift|pallet|tractor|furnace|boiler|industrial|bulk|container|wholesale)\b/i.test(
      `${draft.name} ${draft.description ?? ''}`,
    );

  // Over 5 kg a posted item must also say how big it is (the server checks the same). Collect-in-person items don't need it.
  const needsSize =
    !draft.collectInPerson && (draft.weightGrams ?? 0) > 5000 && !(draft.lengthCm && draft.widthCm && draft.heightCm);

  const hasPhoto = (draft.images ?? []).length > 0;
  const missing = [
    !hasPhoto && 'a photo',
    draft.name.trim().length === 0 && 'a name',
    !(draft.price > 0) && 'a price',
    (draft.description ?? '').trim().length === 0 && 'a description',
    !draft.collectInPerson && !(draft.weightGrams && draft.weightGrams > 0) && 'a weight',
    needsSize && 'the size (length, width, height)',
    // Only asked for when the category has collections to choose from; a category with none must not block listing.
    bannersForCategory.length > 0 && (draft.bannerId ?? '').length === 0 && 'a collection',
  ].filter(Boolean) as string[];
  const canSave =
    !photosBusy &&
    !saving &&
    hasPhoto &&
    draft.name.trim().length > 0 &&
    draft.price > 0 &&
    (bannersForCategory.length === 0 || (draft.bannerId ?? '').length > 0) &&
    (!!draft.collectInPerson || (!!draft.weightGrams && draft.weightGrams > 0)) &&
    !needsSize &&
    (draft.description ?? '').trim().length > 0;

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/40 lg:items-center">
      <div className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-t-2xl bg-surface p-5 lg:rounded-2xl">
        <div className="mb-4 flex items-center justify-between">
          <p className="text-[14px] font-bold text-text">{product.name ? 'Edit product' : 'New product'}</p>
          <button onClick={onCancel} aria-label="Close">
            <X size={18} className="text-text-mute" />
          </button>
        </div>

        <div className="flex flex-col gap-3">
          {/* Photos come first — before the rest of this form, per how
              listing a product is meant to start. */}
          <PhotoUploader images={draft.images ?? []} onChange={(images) => setDraft((d) => ({ ...d, images }))} onBusyChange={setPhotosBusy} />

          <label className="block">
            <span className="mb-1 block text-[12.5px] font-bold text-text">Product name</span>
            <input
              type="text"
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              placeholder="e.g. Lightweight scarf"
              className="w-full rounded-lg border border-line px-3 py-2.5 text-base text-text focus:border-mark sm:text-[13.5px] focus:outline-none"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-[12.5px] font-bold text-text">Price</span>
            <input
              type="number"
              value={draft.price || ''}
              onChange={(e) => setDraft({ ...draft, price: Number(e.target.value) || 0 })}
              placeholder="0.00"
              className="w-full rounded-lg border border-line px-3 py-2.5 text-base text-text focus:border-mark sm:text-[13.5px] focus:outline-none"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-[12.5px] font-bold text-text">Description</span>
            <textarea
              value={draft.description ?? ''}
              onChange={(e) => setDraft({ ...draft, description: e.target.value })}
              rows={3}
              placeholder="What is it, what's it made of, why would someone want it?"
              className="w-full resize-none rounded-lg border border-line px-3 py-2.5 text-base text-text focus:border-mark sm:text-[13.5px] focus:outline-none"
            />
          </label>

          {/* Where this shows up in the consumer-facing category catalog —
              required, since that placement is the whole point of this
              tab existing separately from Posts. */}
          <label className="block">
            <span className="mb-1 block text-[12.5px] font-bold text-text">Category</span>
            <select
              value={categoryId}
              onChange={(e) => handleCategoryChange(e.target.value)}
              className="w-full rounded-lg border border-line px-3 py-2.5 text-base text-text focus:border-mark sm:text-[13.5px] focus:outline-none"
            >
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="mb-1 block text-[12.5px] font-bold text-text">
              Collection{bannersForCategory.length === 0 ? ' (none in this category yet)' : ''}
            </span>
            <select
              value={draft.bannerId ?? ''}
              disabled={bannersForCategory.length === 0}
              onChange={(e) => setDraft({ ...draft, bannerId: e.target.value })}
              className="w-full rounded-lg border border-line px-3 py-2.5 text-base text-text focus:border-mark sm:text-[13.5px] focus:outline-none"
            >
              {bannersForCategory.length === 0 && <option value="">No collections in this category yet</option>}
              {bannersForCategory.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.title}
                </option>
              ))}
            </select>
          </label>

          <ColorPicker value={draft.colors} onChange={(colors) => setDraft({ ...draft, colors })} />

          <SizePicker value={draft.sizes} onChange={(sizes) => setDraft({ ...draft, sizes })} />

          <label className="flex items-center gap-2 py-1">
            <input
              type="checkbox"
              checked={Boolean(draft.isNew)}
              onChange={(e) => setDraft({ ...draft, isNew: e.target.checked })}
              className="h-4 w-4 rounded border-line accent-accent"
            />
            <span className="text-[13.5px] text-text">
              Mark as a new arrival
              <span className="block text-[11.5px] text-text-mute">
                Shows up when someone taps &quot;New Arrivals&quot; from the shop sidebar
              </span>
            </span>
          </label>

          {looksBulky && (
            <p className="rounded-lg bg-accent/20 px-3 py-2 text-[12.5px] leading-snug text-text">
              This may be too big to post.{' '}
              <button type="button" onClick={() => setDraft({ ...draft, collectInPerson: true })} className="font-bold underline">
                Sell it as collect in person
              </button>
              ?
            </p>
          )}
          <label className="flex items-start gap-2.5 rounded-lg border border-line p-3">
            <input
              type="checkbox"
              checked={!!draft.collectInPerson}
              onChange={(e) => setDraft({ ...draft, collectInPerson: e.target.checked })}
              className="mt-0.5 h-4 w-4"
            />
            <span>
              <span className="block text-[12.5px] font-bold text-text">Too big to post: buyer collects in person</span>
              <span className="mt-0.5 block text-[11.5px] text-text-mute">
                For machines and bulk goods. The buyer pays first and the money is held safely. They come to your pickup address (add it in
                your shop settings, with your visiting hours), inspect the item{collectDays ? ` within ${collectDays} day${collectDays === 1 ? '' : 's'}` : ''}, and when they accept you are paid. If it isn&apos;t
                right they are refunded and you keep the item. No courier, no delivery fee.
              </span>
            </span>
          </label>

          <label className="block">
            <span className="mb-1 block text-[12.5px] font-bold text-text">Weight (grams){draft.collectInPerson ? ' (optional)' : ''}</span>
            <input
              type="number"
              inputMode="numeric"
              min={1}
              max={20000000}
              value={draft.weightGrams ?? ''}
              onChange={(e) =>
                setDraft({ ...draft, weightGrams: e.target.value === '' ? undefined : Math.min(20000000, Math.max(0, Math.round(Number(e.target.value)))) })
              }
              placeholder="e.g. 450"
              className="w-full rounded-lg border border-line px-3 py-2.5 text-base text-text focus:border-mark sm:text-[13.5px] focus:outline-none"
            />
            <span className="mt-1 block text-[11.5px] text-text-mute">
              One item, packed. The courier prices delivery by weight, so a wrong number costs money. 1000 g = 1 kg. Anything over 30 kg is sold collect in person automatically.
            </span>
          </label>

          <div>
            <span className="mb-1 block text-[12.5px] font-bold text-text">
              Size in cm, packed <span className="font-normal text-text-mute">({(draft.weightGrams ?? 0) > 5000 && !draft.collectInPerson ? 'required over 5 kg' : 'optional'})</span>
            </span>
            <div className="grid grid-cols-3 gap-2">
              {(['lengthCm', 'widthCm', 'heightCm'] as const).map((key, i) => (
                <input
                  key={key}
                  type="number"
                  inputMode="numeric"
                  min={1}
                  max={5000}
                  value={draft[key] ?? ''}
                  onChange={(e) => setDraft({ ...draft, [key]: e.target.value === '' ? undefined : Math.min(5000, Math.max(0, Math.round(Number(e.target.value)))) })}
                  placeholder={['Length', 'Width', 'Height'][i]}
                  className="w-full rounded-lg border border-line px-3 py-2.5 text-base text-text focus:border-mark sm:text-[13.5px] focus:outline-none"
                />
              ))}
            </div>
            <span className="mt-1 block text-[11.5px] text-text-mute">
              Couriers charge by the bigger of weight and size, so a big box counts as heavy however light it is. Very big items are sold collect in
              person automatically.
            </span>
          </div>

          <label className="block">
            <span className="mb-1 block text-[12.5px] font-bold text-text">
              Stock <span className="font-normal text-text-mute">(optional)</span>
            </span>
            <input
              type="number"
              min={0}
              value={draft.stockQuantity ?? ''}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  // Empty field means untracked/unlimited (stockQuantity:
                  // undefined) — same as leaving this alone entirely.
                  // Typing "0" is a real, distinct value (out of stock),
                  // not the same as empty, so this checks the raw string
                  // rather than falling back on `Number('') || 0`, which
                  // would make 0 and blank indistinguishable.
                  stockQuantity: e.target.value === '' ? undefined : Math.max(0, Number(e.target.value)),
                })
              }
              placeholder="Leave blank for unlimited"
              className="w-full rounded-lg border border-line px-3 py-2.5 text-base text-text focus:border-mark sm:text-[13.5px] focus:outline-none"
            />
            <span className="mt-1 block text-[11.5px] text-text-mute">
              Leave blank if you don&apos;t want stock tracked or enforced for this product.
            </span>
          </label>

          <label className="block">
            <span className="mb-1 block text-[12.5px] font-bold text-text">
              Discount % <span className="font-normal text-text-mute">(optional)</span>
            </span>
            <input
              type="number"
              min={0}
              max={100}
              value={draft.discountPercent ?? ''}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  // Same blank-means-unset convention as Stock above —
                  // typing 0 is a real "no discount" value distinct from
                  // never having set one, so this checks the raw string
                  // rather than `Number('') || 0`.
                  discountPercent: e.target.value === '' ? undefined : Math.min(100, Math.max(0, Number(e.target.value))),
                })
              }
              placeholder="Leave blank for no discount"
              className="w-full rounded-lg border border-line px-3 py-2.5 text-base text-text focus:border-mark sm:text-[13.5px] focus:outline-none"
            />
            <span className="mt-1 block text-[11.5px] text-text-mute">
              Raising this notifies anyone who&apos;s saved this product to their cart or a video&apos;s watchlist.
            </span>
            <span className="mt-1 block text-[11.5px] leading-snug text-text-mute">
              Shoppers see the discounted price with your normal price struck through, and are charged the discounted price.
            </span>
          </label>
        </div>

        <div className="sticky -bottom-5 -mx-5 mt-4 bg-surface px-5 pb-1 pt-2">
          {saveError && <p role="alert" className="mb-2 text-center text-[12.5px] font-semibold text-danger">{saveError}</p>}
          {!saveError && photosBusy && <p className="mb-2 text-center text-[12px] font-semibold text-text-mute">Photos are still uploading. One moment.</p>}
          {!saveError && !photosBusy && missing.length > 0 && (
            <p className="mb-2 text-center text-[12px] font-semibold text-text-mute">Still needed: {missing.join(', ')}.</p>
          )}
          <button
            onClick={() => {
              if (!canSave) return;
              setSaving(true);
              setSaveError(null);
              Promise.resolve(onSave(draft)).catch((err: unknown) => {
                setSaveError(err instanceof ApiError ? err.message : "Couldn't save. Check your connection and try again.");
                setSaving(false);
              });
            }}
            disabled={!canSave}
            className="brand-gradient w-full rounded-full py-3.5 text-[15px] font-bold text-white disabled:opacity-40"
          >
            {saving ? 'Saving…' : 'Save product'}
          </button>
        </div>
      </div>
    </div>
  );
}

interface MerchantProductsProps {
  products: Product[];
  categories: Category[];
  categoryBanners: CategoryBanner[];
  onAddProduct: (product: Product) => void | Promise<void>;
  onUpdateProduct: (product: Product) => void | Promise<void>;
  onDeleteProduct: (id: string) => void;
}

// Step one of the required sequence — a product has to exist here before
// it can be attached to a video in the Posts tab. Every product created
// here also actually appears in the real consumer-facing category catalog
// (merged in by page.tsx via bannerId), not just in this dashboard.
export function MerchantProducts({
  products,
  categories,
  categoryBanners,
  onAddProduct,
  onUpdateProduct,
  onDeleteProduct,
}: MerchantProductsProps) {
  const [editing, setEditing] = useState<Product | null>(null);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  // Which products are promoted as a "Sponsored twin" on scan results, with their numbers.
  const [promo, setPromo] = useState<Record<string, ApiSponsoredStats>>({});
  useEffect(() => {
    listMySponsoredTwins()
      .then((rows) => setPromo(Object.fromEntries(rows.map((r) => [r.product_id, r]))))
      .catch(() => {});
  }, []);
  // Promoting asks for the product's style, main colour and who it is for, so the "Complete the look" kit can match the
  // video's look. All optional; "Not sure" leaves it out. Editing the tags of one already promoted reuses the same form.
  const [tagging, setTagging] = useState<{ productId: string; tags: SponsoredTags } | null>(null);
  const [tagBusy, setTagBusy] = useState(false);
  const openTagForm = (productId: string) => {
    const cur = promo[productId];
    setOpenMenuId(null);
    setTagging({ productId, tags: { style: cur?.style ?? null, color: cur?.color ?? null, audience: cur?.audience ?? null } });
  };
  const savePromo = () => {
    if (!tagging || tagBusy) return;
    setTagBusy(true);
    setPromoError(null);
    setSponsoredTwin(tagging.productId, true)
      .then((r) => {
        setPromo((p) => ({ ...p, [tagging.productId]: r }));
        setTagging(null);
      })
      .catch((err: unknown) => setPromoError(err instanceof ApiError ? err.message : "Couldn't save. Try again."))
      .finally(() => setTagBusy(false));
  };
  const stopPromo = (productId: string) => {
    setOpenMenuId(null);
    setSponsoredTwin(productId, false)
      .then((r) => setPromo((p) => ({ ...p, [productId]: r })))
      .catch(() => {});
  };

  const startNew = () => setEditing(emptyProduct(''));
  const startEdit = (product: Product) => {
    setEditing(product);
    setOpenMenuId(null);
  };
  // The form stays open until the server accepts the product; a failure is shown inside it.
  const handleSave = async (product: Product) => {
    if (products.some((p) => p.id === product.id)) await onUpdateProduct(product);
    else await onAddProduct(product);
    setEditing(null);
  };
  // Deleting cannot be undone, so the menu only asks; this holds the product being asked about.
  const [askDelete, setAskDelete] = useState<Product | null>(null);
  const [promoError, setPromoError] = useState<string | null>(null);

  const bannerTitle = (bannerId?: string) => categoryBanners.find((b) => b.id === bannerId)?.title ?? 'Uncategorized';

  return (
    <div className="flex-1 px-4 py-5 lg:px-8 lg:py-8">
      {openMenuId && <div className="fixed inset-0 z-10" onClick={() => setOpenMenuId(null)} aria-hidden="true" />}

      {tagging && (
        <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/40 lg:items-center" role="dialog" aria-label="Offer as an add-on">
          <div className="w-full max-w-lg rounded-t-2xl bg-surface p-5 lg:rounded-2xl">
            <div className="mb-1 flex items-center justify-between">
              <p className="text-[14px] font-bold text-text">Offer as an add-on</p>
              <button onClick={() => setTagging(null)} aria-label="Close">
                <X size={18} className="text-text-mute" />
              </button>
            </div>
            <p className="mb-4 text-[12px] leading-snug text-text-mute">
              Your product is shown to shoppers as something that goes with the outfit or kit they are looking at. We match it from what
              you already entered: its name, description, colours, price and category, so a clear name and description, and real colours,
              get it matched better.
            </p>
            <p className="mb-4 rounded-lg bg-panel px-3 py-2 text-[12px] leading-snug text-text">
              <span className="font-bold">No upfront cost.</span> You only pay when it sells: {promo[tagging.productId]?.percent ?? 10}% of the sale price
              (shown on each order) is taken from your payout for every sale made as an add-on.
            </p>
            {promoError && <p role="alert" className="mb-2 text-[12.5px] font-semibold text-danger">{promoError}</p>}
            <button
              onClick={savePromo}
              disabled={tagBusy}
              className="brand-gradient mt-1 w-full rounded-lg py-2.5 text-[13px] font-bold text-white disabled:opacity-60"
            >
              {tagBusy ? 'Saving…' : 'Start offering'}
            </button>
          </div>
        </div>
      )}

      <div className="mb-1 flex items-center justify-between">
        <p className="text-[13px] font-bold text-text">
          {products.length} product{products.length === 1 ? '' : 's'}
        </p>
        <button
          onClick={startNew}
          className="fill-violet flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[12.5px] font-bold text-white"
        >
          <Plus size={15} />
          New product
        </button>
      </div>
      <p className="mb-4 text-[12.5px] text-text-mute">
        Products you list here show up in the category catalog, and are what you&apos;ll pick from
        when you make a video in the Posts tab.
      </p>

      {products.length === 0 ? (
        <p className="py-16 text-center text-[13.5px] text-text-mute">
          No products yet — create one to list it in the category catalog.
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          {products.map((product) => (
            <div
              key={product.id}
              className="relative flex items-center gap-3 rounded-xl border border-line bg-surface p-3"
            >
              <span className="h-11 w-11 shrink-0 overflow-hidden rounded-lg border border-line bg-box">
                <ProductThumbnail product={product} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13.5px] font-bold text-text">{product.name}</p>
                <p className="text-[12.5px] text-text-mute">
                  {formatMoney(product.price)} · {bannerTitle(product.bannerId)}
                  {!!product.discountPercent && (
                    <span className="ml-1.5 font-bold text-sale">{product.discountPercent}% off</span>
                  )}
                </p>
                {promo[product.id]?.active && (
                  <p className="text-[11.5px] text-text-mute">
                    Offered as an add-on · {promo[product.id].impressions} shown · {promo[product.id].reveals} opened · {promo[product.id].clicks} taps
                  </p>
                )}
                {promo[product.id]?.active && (
                  <p className="text-[11.5px] text-text-mute">
                    {promo[product.id].sales} sold through it · {formatMoney(promo[product.id].sales_total)} · fee {promo[product.id].percent}% ={' '}
                    {formatMoney(promo[product.id].fee_total)}
                  </p>
                )}
              </div>
              <button
                onClick={() => setOpenMenuId((id) => (id === product.id ? null : product.id))}
                aria-label="Product options"
                aria-expanded={openMenuId === product.id}
                className="shrink-0 rounded-full p-2 text-text-mute hover:text-text"
              >
                <MoreVertical size={17} />
              </button>
              {openMenuId === product.id && (
                <div className="absolute right-2 top-11 z-20 overflow-hidden rounded-lg bg-surface shadow-[0_4px_16px_rgba(0,0,0,0.25)]">
                  <button
                    onClick={() => startEdit(product)}
                    className="block w-full whitespace-nowrap px-3 py-2 text-left text-[12.5px] font-medium text-text"
                  >
                    Edit product
                  </button>
                  <button
                    onClick={() => (promo[product.id]?.active ? stopPromo(product.id) : openTagForm(product.id))}
                    className="block w-full whitespace-nowrap px-3 py-2 text-left text-[12.5px] font-medium text-text"
                  >
                    {promo[product.id]?.active ? 'Stop offering as an add-on' : 'Offer as an add-on'}
                  </button>
                  <button
                    onClick={() => {
                      setAskDelete(product);
                      setOpenMenuId(null);
                    }}
                    className="flex items-center gap-1.5 whitespace-nowrap px-3 py-2 text-[12.5px] font-medium text-danger"
                  >
                    <Trash2 size={14} />
                    Delete product
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {askDelete && (
        <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/40 lg:items-center" role="dialog" aria-label="Delete product">
          <div className="w-full max-w-sm rounded-t-2xl bg-surface p-5 lg:rounded-2xl">
            <p className="text-[14px] font-bold text-text">Delete &quot;{askDelete.name}&quot;?</p>
            <p className="mt-1 text-[12.5px] leading-snug text-text-mute">
              It disappears from the catalog and from your videos. This cannot be undone.
            </p>
            <div className="mt-4 flex gap-2">
              <button onClick={() => setAskDelete(null)} className="flex-1 rounded-full border border-line py-2.5 text-[13.5px] font-bold text-text">
                Keep it
              </button>
              <button
                onClick={() => {
                  onDeleteProduct(askDelete.id);
                  setAskDelete(null);
                }}
                className="flex-1 rounded-full btn-neutral py-2.5 text-[13.5px] font-bold"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {editing && (
        <ProductForm
          product={editing}
          categories={categories}
          categoryBanners={categoryBanners}
          onSave={handleSave}
          onCancel={() => setEditing(null)}
        />
      )}
    </div>
  );
}
