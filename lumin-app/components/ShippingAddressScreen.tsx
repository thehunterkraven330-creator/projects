'use client';

import { useState } from 'react';
import type { ShippingAddress } from '@/lib/types';
import { ApiError } from '@/lib/api';
import { detectCountry, pickupCountries } from '@/lib/country';
import { PageHeader } from './PageHeader';

interface ShippingAddressScreenProps {
  address?: ShippingAddress;
  onBack: () => void;
  // Returns the promise (not swallowed) so this screen can show its own
  // inline error and stay put on failure — same "a form someone
  // explicitly submitted needs to visibly succeed or fail, not silently
  // revert" reasoning as ProfileScreen's Edit profile form. The caller
  // (page.tsx) decides what happens next on success — navigating back,
  // or resuming a checkout that was waiting on this — not this screen.
  onSave: (address: ShippingAddress) => Promise<void>;
}

const REQUIRED_FIELDS: { key: keyof ShippingAddress; label: string }[] = [
  { key: 'recipientName', label: 'Recipient name' },
  { key: 'phone', label: 'Phone number' },
  { key: 'line1', label: 'Address' },
  { key: 'city', label: 'City' },
  { key: 'postalCode', label: 'Postal code' },
  { key: 'country', label: 'Country' },
];

// One saved address per account, not an address book — matches the
// backend (ShippingAddressMixin's own comment explains why: nothing in
// this app needs more than one). A checkout with no address on file sends the person here; once saved they land
// back where they were and tap Pay / Buy now again (a payment form must open from a real tap).
export function ShippingAddressScreen({ address, onBack, onSave }: ShippingAddressScreenProps) {
  const [form, setForm] = useState<ShippingAddress>(() =>
    address
      ? // Addresses saved before the country became a two-letter code ("Nigeria") start blank: they have to be picked again.
        { ...address, country: /^[A-Za-z]{2}$/.test(address.country ?? '') ? address.country.toUpperCase() : '' }
      : {
      recipientName: '',
      phone: '',
      line1: '',
      line2: '',
      city: '',
      state: '',
      postalCode: '',
      country: detectCountry(), // from the phone's time zone / language; the USA if it can't tell
    },
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = (key: keyof ShippingAddress) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((prev) => ({ ...prev, [key]: e.target.value }));

  const missing = REQUIRED_FIELDS.filter(({ key }) => !form[key]?.trim());

  const handleSave = (e?: React.FormEvent) => {
    e?.preventDefault();
    if (missing.length > 0) {
      setError(`${missing.map((f) => f.label).join(', ')} — required.`);
      return;
    }
    setSaving(true);
    setError(null);
    onSave(form)
      .catch((err) =>
        setError(err instanceof ApiError && err.status < 500 ? err.message : "Couldn't save — check your connection and try again."),
      )
      .finally(() => setSaving(false));
  };

  // 16px on phones: anything smaller makes iOS Safari zoom the page when a field is tapped.
  const inputClass =
    'w-full rounded-lg border border-line bg-surface px-3 py-2.5 text-base text-text focus:border-mark focus:outline-none disabled:opacity-60 sm:text-[13.5px]';
  const labelClass = 'mb-1 block text-[12.5px] font-bold text-text-mute';

  // One field: the label is tied to the input (tap the label to focus; screen readers read it) and autoComplete lets the
  // phone fill name, phone and address in one tap.
  const field = (
    key: keyof ShippingAddress,
    label: string,
    opts: { type?: string; autoComplete: string; placeholder?: string; inputMode?: 'tel' | 'text' | 'numeric' } ,
  ) => (
    <div>
      <label htmlFor={`ship-${key}`} className={labelClass}>
        {label}
      </label>
      <input
        id={`ship-${key}`}
        name={key}
        type={opts.type ?? 'text'}
        inputMode={opts.inputMode}
        autoComplete={opts.autoComplete}
        value={form[key] ?? ''}
        onChange={set(key)}
        disabled={saving}
        className={inputClass}
        placeholder={opts.placeholder}
      />
    </div>
  );

  return (
    <div className="flex h-full flex-col bg-panel">
      <PageHeader title="Shipping address" onBack={onBack} backLabel="Back" />
      <div className="flex-1 overflow-y-auto">
        <form onSubmit={handleSave} className="mx-auto flex w-full max-w-md flex-col gap-3 px-4 py-4 lg:px-0 lg:py-6">
          {field('recipientName', 'Recipient name', { autoComplete: 'name', placeholder: "Who's this for?" })}
          {field('phone', 'Phone number', { type: 'tel', inputMode: 'tel', autoComplete: 'tel', placeholder: 'With country code, e.g. +234 803 123 4567' })}
          {field('line1', 'Address', { autoComplete: 'address-line1', placeholder: 'Street address' })}
          {field('line2', 'Apartment, suite, etc. (optional)', { autoComplete: 'address-line2' })}
          <div className="grid grid-cols-2 gap-3">
            {field('city', 'City', { autoComplete: 'address-level2' })}
            {field('state', 'State / province (optional)', { autoComplete: 'address-level1' })}
          </div>
          <div className="grid grid-cols-2 gap-3">
            {field('postalCode', 'Postal code', { autoComplete: 'postal-code' })}
            <div>
              <label htmlFor="ship-country" className={labelClass}>
                Country
              </label>
              <select
                id="ship-country"
                name="country"
                autoComplete="country"
                value={form.country ?? ''}
                onChange={(e) => setForm((prev) => ({ ...prev, country: e.target.value }))}
                disabled={saving}
                className={inputClass}
              >
                <option value="">Choose…</option>
                {pickupCountries.map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {error && (
            <p role="alert" className="text-[12.5px] font-medium text-accent-ink">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={saving}
            className="brand-gradient mt-1 w-full rounded-full py-3.5 text-[15px] font-bold text-white disabled:opacity-60"
          >
            {saving ? 'Saving…' : 'Save address'}
          </button>
        </form>
      </div>
    </div>
  );
}
