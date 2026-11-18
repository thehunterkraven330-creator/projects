'use client';

import { useEffect, useState } from 'react';
import { CheckCircle2, Landmark } from 'lucide-react';
import type { MerchantAccount } from '@/lib/types';
import {
  listBanks,
  ApiError,
  getStripePayoutStatus,
  openStripeDashboard,
  startStripeOnboarding,
  type ApiBank,
  type ApiStripePayoutStatus,
} from '@/lib/api';

interface MerchantPayoutsProps {
  account: MerchantAccount;
  onSave: (bankCode: string, accountNumber: string) => Promise<void>;
  // Stripe says this seller's readiness differs from what the app last knew (they just came back from Stripe's page):
  // lets the dashboard drop its "Set up payouts" banner without a reload.
  onReadyChange?: (ready: boolean) => void;
}

// Where release_to_merchant (backend app/escrow.py) actually sends money
// once an order's held funds are ready to move — a merchant with no
// payout details set up can list products and take orders same as
// always, but every one of their orders just sits at payout_status
// 'held' forever until this exists. Two real Paystack calls happen
// behind onSave, in order: resolve the account (confirms it's real,
// returns the actual name on file) then register it as a transfer
// recipient — see routers/merchant.py's own comment on why in that
// order, not the reverse.
export function MerchantPayouts({ account, onSave, onReadyChange }: MerchantPayoutsProps) {
  // Stripe collects identity and bank details on its own page, so there is no bank form of ours to show.
  if (account.payoutProvider === 'stripe') return <StripePayouts account={account} onReadyChange={onReadyChange} />;
  return <BankPayouts account={account} onSave={onSave} />;
}

// Stripe Connect payouts: one button to Stripe's hosted onboarding page, then status. Our server never sees bank numbers.
function StripePayouts({ account, onReadyChange }: { account: MerchantAccount; onReadyChange?: (ready: boolean) => void }) {
  const [status, setStatus] = useState<ApiStripePayoutStatus | null>(null);
  const [checking, setChecking] = useState(true);
  const [checkFailed, setCheckFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const check = () => {
    setChecking(true);
    setCheckFailed(false);
    getStripePayoutStatus()
      .then((st) => {
        setStatus(st);
        if (st.ready !== account.payoutReady) onReadyChange?.(st.ready);
      })
      .catch(() => setCheckFailed(true))
      .finally(() => setChecking(false));
  };

  useEffect(() => {
    // Coming back from Stripe (or just opening the tab): ask Stripe where things stand, and tidy ?payouts= from the address bar.
    check();
    const url = new URL(window.location.href);
    if (url.searchParams.has('payouts')) {
      url.searchParams.delete('payouts');
      window.history.replaceState({}, '', url.toString());
    }
    // Pressing Back from Stripe's page can restore this screen as it was (button stuck on "Opening Stripe…"): reset it.
    const onShow = (e: PageTransitionEvent) => {
      if (e.persisted) {
        setBusy(false);
        check();
      }
    };
    window.addEventListener('pageshow', onShow);
    return () => window.removeEventListener('pageshow', onShow);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const ready = status ? status.ready : account.payoutReady;
  // Stripe has the details but is still verifying them (or wants one more thing): not "start again", not "done".
  const reviewing = !ready && !!status?.details_submitted;
  const go = async (open: () => Promise<{ url: string }>) => {
    setBusy(true);
    setError(null);
    try {
      const { url } = await open();
      window.location.href = url; // Stripe's own page; it sends the seller back here when done
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not open Stripe. Check your connection and try again.');
      setBusy(false);
    }
  };

  return (
    <div className="px-4 py-5 lg:px-8 lg:py-8">
      <h2 className="text-lg font-bold text-text">Payouts</h2>
      <div className="mt-4 max-w-sm rounded-xl border border-line bg-surface p-4" aria-busy={checking}>
        {checking && !status && !account.payoutReady ? (
          <p className="text-[13px] text-text-mute">Checking with Stripe…</p>
        ) : ready ? (
          <>
            <div className="flex items-center gap-1.5 text-green-600">
              <CheckCircle2 size={18} />
              <span className="text-[13.5px] font-bold">Payouts are set up</span>
            </div>
            <p className="mt-2 text-[12.5px] text-text-mute">
              An order&apos;s money is sent to your Stripe account once the buyer confirms receipt, or 48 hours after delivery if
              they don&apos;t report a problem first. Stripe then pays it out to your bank.
            </p>
            <button
              onClick={() => go(openStripeDashboard)}
              disabled={busy}
              className="mt-3 text-[12.5px] font-bold text-accent-ink disabled:opacity-40"
            >
              {busy ? 'Opening…' : 'View balance and bank details'}
            </button>
          </>
        ) : reviewing ? (
          <>
            <p className="text-[13.5px] font-bold text-text">Stripe is checking your details</p>
            <p className="mt-1 text-[12.5px] text-text-mute">
              This usually takes a few minutes, sometimes longer. Your orders keep selling and your money is held safely until it is
              done. If Stripe asks for anything else, you can add it below.
            </p>
            <button
              onClick={() => go(startStripeOnboarding)}
              disabled={busy}
              className="mt-3 text-[12.5px] font-bold text-accent-ink disabled:opacity-40"
            >
              {busy ? 'Opening Stripe…' : 'Open Stripe to check or add details'}
            </button>
            <button onClick={check} disabled={checking} className="mt-2 block text-[12.5px] font-bold text-text-mute disabled:opacity-40">
              {checking ? 'Checking…' : 'Check again'}
            </button>
          </>
        ) : (
          <>
            <p className="text-[13.5px] font-bold text-text">
              {status?.has_account ? 'Finish setting up payouts' : 'Set up payouts'}
            </p>
            <p className="mt-1 text-[12.5px] text-text-mute">
              {status?.has_account
                ? 'Stripe still needs a few details before it can send you money. Your orders keep selling and your money stays safe meanwhile.'
                : 'Stripe will ask for your identity and the bank account to pay into. It takes a few minutes, and this app never sees your bank details. Until it is done, your orders keep selling and the money is held safely.'}
            </p>
            <button
              onClick={() => go(startStripeOnboarding)}
              disabled={busy}
              className="brand-gradient mt-3 flex w-full items-center justify-center gap-1.5 rounded-full py-2.5 text-[14px] font-bold text-white disabled:opacity-40"
            >
              <Landmark size={15} />
              {busy ? 'Opening Stripe…' : status?.has_account ? 'Continue with Stripe' : 'Set up with Stripe'}
            </button>
          </>
        )}
        {checkFailed && !checking && (
          <p className="mt-2.5 text-[12.5px] text-text-mute">
            Couldn&apos;t check with Stripe just now.{' '}
            <button onClick={check} className="font-bold text-accent-ink">
              Try again
            </button>
          </p>
        )}
        {error && (
          <p role="alert" className="mt-2.5 text-[13px] text-danger">
            {error}
          </p>
        )}
      </div>
    </div>
  );
}

function BankPayouts({ account, onSave }: MerchantPayoutsProps) {
  const [banks, setBanks] = useState<ApiBank[]>([]);
  const [banksError, setBanksError] = useState(false);
  const [bankCode, setBankCode] = useState('');
  const [accountNumber, setAccountNumber] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Toggled open explicitly rather than always showing the form — once
  // payout details exist, the default view should read as "here's your
  // status," not re-prompt for bank details every visit.
  const [editing, setEditing] = useState(!account.payoutReady);

  useEffect(() => {
    listBanks()
      .then(setBanks)
      .catch(() => setBanksError(true));
  }, []);

  const canSave = bankCode.length > 0 && accountNumber.trim().length > 0 && !saving;

  const handleSave = async () => {
    if (!canSave) return;
    setSaving(true);
    setError(null);
    try {
      await onSave(bankCode, accountNumber.trim());
      setEditing(false);
    } catch (err) {
      // A failed resolve_account (wrong account number for that bank)
      // comes back with a specific message worth showing verbatim
      // rather than a generic "something went wrong."
      setError(err instanceof ApiError ? err.message : 'Could not save payout details — try again.');
    } finally {
      setSaving(false);
    }
  };

  if (!editing && account.payoutReady) {
    return (
      <div className="px-4 py-5 lg:px-8 lg:py-8">
        <h2 className="text-lg font-bold text-text">Payouts</h2>
        <div className="mt-4 max-w-sm rounded-xl border border-line bg-surface p-4">
          <div className="flex items-center gap-1.5 text-green-600">
            <CheckCircle2 size={18} />
            <span className="text-[13.5px] font-bold">Payouts are set up</span>
          </div>
          <p className="mt-2 text-[14px] text-text">{account.accountName}</p>
          <p className="text-[12.5px] text-text-mute">
            {banks.find((b) => b.code === account.bankCode)?.name ?? 'Bank on file'} ····{' '}
            {account.accountNumber?.slice(-4)}
          </p>
          <p className="mt-3 text-[12.5px] text-text-mute">
            An order&apos;s funds release here automatically once the buyer confirms receipt, or 48 hours
            after delivery if they don&apos;t report a problem first.
          </p>
          <button onClick={() => setEditing(true)} className="mt-3 text-[12.5px] font-bold text-accent-ink">
            Change payout details
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="px-4 py-5 lg:px-8 lg:py-8">
      <h2 className="text-lg font-bold text-text">Payouts</h2>
      <p className="mt-1 max-w-sm text-[13.5px] text-text-mute">
        Add the bank account your order payments should release to. This app never asks for a name —
        it&apos;s confirmed straight from Paystack once you enter the account number below.
      </p>

      <div className="mt-4 max-w-sm rounded-xl border border-line bg-surface p-4">
        <label className="mb-3 block">
          <span className="mb-1.5 block text-[12.5px] font-bold text-text">Bank</span>
          {banksError ? (
            <p className="text-[13px] text-danger">Couldn&apos;t load the bank list — refresh to try again.</p>
          ) : (
            <select
              value={bankCode}
              onChange={(e) => setBankCode(e.target.value)}
              className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-[13px] text-text focus:border-mark focus:outline-none"
            >
              <option value="">{banks.length === 0 ? 'Loading banks…' : 'Select a bank'}</option>
              {banks.map((bank) => (
                <option key={bank.code} value={bank.code}>
                  {bank.name}
                </option>
              ))}
            </select>
          )}
        </label>

        <label className="mb-3 block">
          <span className="mb-1.5 block text-[12.5px] font-bold text-text">Account number</span>
          <input
            type="text"
            inputMode="numeric"
            value={accountNumber}
            onChange={(e) => setAccountNumber(e.target.value)}
            placeholder="10-digit account number"
            className="w-full rounded-lg border border-line px-3 py-2 text-[13px] text-text placeholder:text-text-mute focus:border-mark focus:outline-none"
          />
        </label>

        <div className="flex gap-2">
          {account.payoutReady && (
            <button
              onClick={() => setEditing(false)}
              className="flex-1 rounded-full border border-line py-2.5 text-[14px] font-bold text-text"
            >
              Cancel
            </button>
          )}
          <button
            onClick={handleSave}
            disabled={!canSave}
            className="brand-gradient flex flex-1 items-center justify-center gap-1.5 rounded-full py-2.5 text-[14px] font-bold text-white disabled:opacity-40"
          >
            <Landmark size={15} />
            {saving ? 'Verifying with Paystack…' : 'Verify & save'}
          </button>
        </div>
        {error && <p className="mt-2.5 text-[13px] text-danger">{error}</p>}
      </div>
    </div>
  );
}
