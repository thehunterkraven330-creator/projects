'use client';

import type { PickupAddress } from '@/lib/types';
import { detectCountry, pickupCountries } from '@/lib/country';

// The pickup-address inputs, shared by "Create a Page" and the dashboard's Pickup tab so both ask for exactly the same thing.
export const emptyPickupAddress = (): PickupAddress => ({
  contactName: '',
  phone: '',
  line1: '',
  line2: '',
  city: '',
  state: '',
  postalCode: '',
  country: detectCountry(), // from the time zone / language; the USA if it can't tell
  visitingHours: '',
});

const REQUIRED: { key: keyof PickupAddress; label: string }[] = [
  { key: 'contactName', label: 'Contact name' },
  { key: 'phone', label: 'Phone number' },
  { key: 'line1', label: 'Street address' },
  { key: 'city', label: 'City' },
  { key: 'state', label: 'State' },
  { key: 'postalCode', label: 'Postal code' },
  { key: 'country', label: 'Country' },
];

// The labels of the required fields still empty ([] when the address is complete enough to send).
export function missingPickupFields(a: PickupAddress): string[] {
  const missing = REQUIRED.filter(({ key }) => !String(a[key] ?? '').trim()).map((f) => f.label);
  if (a.phone.trim() && a.phone.replace(/\D/g, '').length < 7 && !missing.includes('Phone number')) missing.push('Phone number');
  return missing;
}

// 16px on phones so iOS Safari doesn't zoom when a field is tapped.
const inputClass =
  'w-full rounded-lg border border-line bg-surface px-3 py-2.5 text-base text-text placeholder:text-text-mute focus:border-mark focus:outline-none disabled:opacity-60 sm:text-[13.5px]';
const labelClass = 'mb-1 block text-[12.5px] font-bold text-text';

export function PickupAddressFields({
  value,
  onChange,
  disabled,
  idPrefix = 'pickup',
}: {
  value: PickupAddress;
  onChange: (next: PickupAddress) => void;
  disabled?: boolean;
  idPrefix?: string;
}) {
  const set = (key: keyof PickupAddress) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    onChange({ ...value, [key]: e.target.value });

  const text = (
    key: keyof PickupAddress,
    label: string,
    opts: { autoComplete: string; placeholder?: string; type?: string; inputMode?: 'tel' | 'text'; maxLength?: number },
  ) => (
    <div>
      <label htmlFor={`${idPrefix}-${key}`} className={labelClass}>
        {label}
      </label>
      <input
        id={`${idPrefix}-${key}`}
        name={`${idPrefix}-${key}`}
        type={opts.type ?? 'text'}
        inputMode={opts.inputMode}
        autoComplete={opts.autoComplete}
        placeholder={opts.placeholder}
        maxLength={opts.maxLength}
        value={value[key] ?? ''}
        onChange={set(key)}
        disabled={disabled}
        className={inputClass}
      />
    </div>
  );

  return (
    <div className="flex flex-col gap-3">
      {text('contactName', 'Contact name', { autoComplete: 'name', placeholder: 'Who the driver asks for', maxLength: 100 })}
      {text('phone', 'Phone number', { type: 'tel', inputMode: 'tel', autoComplete: 'tel', placeholder: 'The driver will call this', maxLength: 30 })}
      {text('line1', 'Street address', { autoComplete: 'address-line1', placeholder: 'House number and street', maxLength: 200 })}
      {text('line2', 'Landmark, floor or suite (optional)', { autoComplete: 'address-line2', maxLength: 200 })}
      <div className="grid grid-cols-2 gap-3">
        {text('city', 'City', { autoComplete: 'address-level2', maxLength: 100 })}
        {text('state', 'State', { autoComplete: 'address-level1', maxLength: 100 })}
      </div>
      {text('visitingHours', 'Visiting hours (optional)', {
        autoComplete: 'off',
        placeholder: 'For buyers who collect in person, e.g. Mon to Sat, 9am to 5pm',
        maxLength: 200,
      })}
      <div className="grid grid-cols-2 gap-3">
        {text('postalCode', 'Postal code', { autoComplete: 'postal-code', maxLength: 20 })}
        <div>
          <label htmlFor={`${idPrefix}-country`} className={labelClass}>
            Country
          </label>
          <select
            id={`${idPrefix}-country`}
            value={value.country}
            onChange={set('country')}
            disabled={disabled}
            className={inputClass}
            autoComplete="country"
          >
            {pickupCountries.map((c) => (
              <option key={c.code} value={c.code}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}
