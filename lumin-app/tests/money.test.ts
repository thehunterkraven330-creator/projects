import test from 'node:test';
import assert from 'node:assert/strict';

async function load(currency?: string) {
  if (currency) process.env.NEXT_PUBLIC_CURRENCY = currency;
  else delete process.env.NEXT_PUBLIC_CURRENCY;
  return await import(`../lib/money.ts?c=${currency ?? 'none'}`);
}

test('the default is dollars with cents, as before', async () => {
  const m = await load();
  assert.equal(m.CURRENCY, 'USD');
  assert.equal(m.formatMoney(12), '$12.00');
  assert.equal(m.formatMoney(1234.5), '$1,234.50');
  assert.equal(m.formatMoneyShort(12), '$12');
  assert.equal(m.formatMoneyShort(12.5), '$12.50');
});

test('naira shows the naira sign and drops .00 on whole amounts', async () => {
  const m = await load('ngn');
  assert.equal(m.CURRENCY, 'NGN');
  assert.equal(m.formatMoney(1500), '₦1,500');
  assert.equal(m.formatMoney(1500.5), '₦1,500.50');
  assert.equal(m.formatMoney(0), '₦0');
});

test('pounds keep their cents', async () => {
  const m = await load('GBP');
  assert.equal(m.formatMoney(20), '£20.00');
});

test('a non-number shows nothing, and an unknown currency does not throw', async () => {
  const m = await load('XXX');
  assert.equal(m.formatMoney(NaN), '');
  assert.equal(typeof m.formatMoney(5), 'string');
});

test('a product can be shown in its own currency, whatever the app default is', async () => {
  const m = await load('USD');
  assert.equal(m.formatMoney(1500, 'NGN'), '₦1,500');
  assert.equal(m.formatMoneyShort(20, 'gbp'), '£20');
  assert.equal(m.formatMoney(12, null), '$12.00'); // none given: the default
  assert.equal(m.formatMoney(12, 'not a code'), '$12.00'); // junk is ignored, never thrown on
});
