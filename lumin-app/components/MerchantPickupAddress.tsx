'use client';

import { useState } from 'react';
import { ApiError } from '@/lib/api';
import type { MerchantAccount, PickupAddress } from '@/lib/types';
import { PickupAddressFields, emptyPickupAddress, missingPickupFields } from './PickupAddressFields';

// The seller's pickup address: where the courier collects sealed orders. Asked once at registration; this is where it is
// changed later, and where sellers who registered before it existed add it.
export function MerchantPickupAddress({
  account,
  onSave,
}: {
  account: MerchantAccount;
  onSave: (address: PickupAddress) => Promise<void>;
}) {
  const [value, setValue] = useState<PickupAddress>(account.pickupAddress ?? emptyPickupAddress());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const missing = missingPickupFields(value);

  const change = (next: PickupAddress) => {
    setValue(next);
    setSaved(false);
  };

  const handleSave = async () => {
    if (saving) return;
    if (missing.length > 0) {
      setError(`${missing.join(', ')} ${missing.length === 1 ? 'is' : 'are'} required.`);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave({
        ...value,
        contactName: value.contactName.trim(),
        phone: value.phone.trim(),
        line1: value.line1.trim(),
        line2: value.line2?.trim() || undefined,
        city: value.city.trim(),
        state: value.state.trim(),
        postalCode: value.postalCode?.trim() || undefined,
      });
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save the address. Check your connection and try again.");
    }
    setSaving(false);
  };

  return (
    <div className="px-4 py-5 lg:px-8 lg:py-8">
      <h2 className="text-lg font-bold text-text">Pickup address</h2>
      <p className="mt-1 max-w-md text-[12.5px] leading-snug text-text-mute">
        Where the delivery driver collects your sold items. When you seal an order, this address goes to the courier, so keep it
        current and make sure the phone number is answered.
        {!account.pickupAddress && ' You need this before you can seal your first order.'}
      </p>
      <div className="mt-4 max-w-md rounded-xl border border-line bg-surface p-4">
        <PickupAddressFields value={value} onChange={change} disabled={saving} idPrefix="dash-pickup" />
        {error && (
          <p role="alert" className="mt-3 text-[13px] text-danger">
            {error}
          </p>
        )}
        {saved && !error && (
          <p role="status" className="mt-3 text-[13px] font-medium text-text">
            Saved. Drivers will collect from this address.
          </p>
        )}
        <button
          onClick={handleSave}
          disabled={saving}
          className="brand-gradient mt-4 w-full rounded-full py-2.5 text-[14px] font-bold text-white disabled:opacity-40"
        >
          {saving ? 'Saving…' : account.pickupAddress ? 'Save changes' : 'Save pickup address'}
        </button>
      </div>
    </div>
  );
}
