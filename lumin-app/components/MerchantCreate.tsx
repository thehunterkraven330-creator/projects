'use client';

import { useState } from 'react';
import { merchantCategories } from '@/lib/data';
import { ApiError } from '@/lib/api';
import type { MerchantAccount } from '@/lib/types';
import { PageHeader } from './PageHeader';
import { PickupAddressFields, emptyPickupAddress, missingPickupFields } from './PickupAddressFields';

interface MerchantCreateProps {
  onBack: () => void;
  // May return a promise: the form then waits for it and shows the message if it fails, instead of looking like nothing happened.
  onCreate: (account: MerchantAccount) => void | Promise<void>;
}

// One merchant page per personal account for now (confirmed as the v1
// scope) — so this form only ever runs once per account; there's no
// "create another page" entry point anywhere else in the app.
export function MerchantCreate({ onBack, onCreate }: MerchantCreateProps) {
  const [businessName, setBusinessName] = useState('');
  const [category, setCategory] = useState(merchantCategories[0]);
  const [description, setDescription] = useState('');
  const [pickup, setPickup] = useState(emptyPickupAddress);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const missing = missingPickupFields(pickup);
  const canSubmit = businessName.trim().length > 0 && !saving;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    if (missing.length > 0) {
      setError(`Pickup address: ${missing.join(', ')} ${missing.length === 1 ? 'is' : 'are'} required.`);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onCreate({
      id: 'merchant-1',
      businessName: businessName.trim(),
      category,
      description: description.trim(),
      // Overwritten immediately by the real server response anyway
      // (handleCreateMerchant in page.tsx), but the type needs a value
      // here regardless — a brand new merchant account never starts
      // with payouts already set up.
      payoutReady: false,
      pickupAddress: {
        ...pickup,
        contactName: pickup.contactName.trim(),
        phone: pickup.phone.trim(),
        line1: pickup.line1.trim(),
        line2: pickup.line2?.trim() || undefined,
        city: pickup.city.trim(),
        state: pickup.state.trim(),
        postalCode: pickup.postalCode?.trim() || undefined,
      },
      });
      // Success moves to the dashboard (this screen goes away), so there is nothing to reset here.
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't create your page. Check your connection and try again.");
      setSaving(false);
    }
  };

  return (
    <div className="flex h-full flex-col bg-panel">
      <PageHeader title="Create a Page" onBack={onBack} backLabel="Back to profile" />
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-md px-4 py-6 lg:px-0 lg:py-10">
          <p className="mb-1 text-[15px] font-bold text-text">Set up your business page</p>
          <p className="mb-6 text-[13.5px] leading-snug text-text-mute">
            This is the seller-facing side of your account — separate from your personal
            profile, the way a Facebook Page sits alongside a personal account. You can switch
            between the two any time.
          </p>

          <label className="mb-4 block">
            <span className="mb-1.5 block text-[12.5px] font-bold text-text">Business name</span>
            <input
              type="text"
              value={businessName}
              onChange={(e) => setBusinessName(e.target.value)}
              placeholder="e.g. Nadia's Vintage Finds"
              className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-base text-text placeholder:text-text-mute focus:border-mark focus:outline-none sm:text-[13px]"
              maxLength={100}
              disabled={saving}
            />
          </label>

          <label className="mb-4 block">
            <span className="mb-1.5 block text-[12.5px] font-bold text-text">Category</span>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-base text-text focus:border-mark focus:outline-none sm:text-[13px]"
              disabled={saving}
            >
              {merchantCategories.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>

          <label className="mb-6 block">
            <span className="mb-1.5 block text-[12.5px] font-bold text-text">
              Description <span className="font-normal text-text-mute">(optional)</span>
            </span>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What do you sell?"
              rows={3}
              className="w-full resize-none rounded-lg border border-line bg-surface px-3 py-2 text-base text-text placeholder:text-text-mute focus:border-mark focus:outline-none sm:text-[13px]"
              maxLength={500}
              disabled={saving}
            />
          </label>

          <div className="mb-6 rounded-xl border border-line bg-surface p-4">
            <p className="text-[13.5px] font-bold text-text">Pickup address</p>
            <p className="mb-3 mt-0.5 text-[12.5px] leading-snug text-text-mute">
              Where the delivery driver collects your sold items. We pass it to the courier when an order is sealed, so make sure
              someone is there and the phone number works. You can change it any time from your dashboard.
            </p>
            <PickupAddressFields value={pickup} onChange={setPickup} disabled={saving} idPrefix="create-pickup" />
          </div>

          {error && (
            <p role="alert" className="mb-3 text-[12.5px] font-medium text-danger">
              {error}
            </p>
          )}
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="brand-gradient w-full rounded-full py-2.5 text-[13px] font-bold text-white disabled:opacity-40"
          >
            {saving ? 'Creating…' : 'Create page'}
          </button>
          <p className="mt-3 text-center text-[12px] text-text-mute">
            Next you&apos;ll add a product, post a video about it, and set up payouts.
          </p>
        </div>
      </div>
    </div>
  );
}
