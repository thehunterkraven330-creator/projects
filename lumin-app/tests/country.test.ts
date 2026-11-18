import test from 'node:test';
import assert from 'node:assert/strict';

async function load(launch?: string) {
  if (launch !== undefined) process.env.NEXT_PUBLIC_LAUNCH_COUNTRIES = launch;
  else delete process.env.NEXT_PUBLIC_LAUNCH_COUNTRIES;
  return await import(`../lib/country.ts?l=${launch ?? 'none'}`);
}

test('with no launch limit every country is offered and a guess is always a real code', async () => {
  const c = await load();
  assert.ok(c.pickupCountries.length > 190);
  assert.match(c.detectCountry(), /^[A-Z]{2}$/);
  assert.equal(c.pickupCountries.find((x: { code: string }) => x.code === 'NG')?.name, 'Nigeria');
});

test('limited to Nigeria, only Nigeria is offered and it is the default', async () => {
  const c = await load('ng');
  assert.deepEqual(c.pickupCountries.map((x: { code: string }) => x.code), ['NG']);
  assert.equal(c.detectCountry(), 'NG'); // this machine is not in Nigeria: the guess falls to the first open country
});

test('several launch countries are all offered, in name order', async () => {
  const c = await load('NG, gh');
  assert.deepEqual(c.pickupCountries.map((x: { code: string }) => x.code), ['GH', 'NG']);
});

test('a code from an old free-text address is shown as it is, a real one by name', async () => {
  const c = await load();
  assert.equal(c.countryName('NG'), 'Nigeria');
  assert.equal(c.countryName('Nigeria'), 'Nigeria');
  assert.equal(c.countryName(undefined), '');
});
