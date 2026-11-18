import test from 'node:test';
import assert from 'node:assert/strict';
import { addRecent, removeRecent, loadRecent, saveRecent, RECENT_SEARCHES_KEY } from '../lib/recentSearches.ts';

test('newest first, trimmed, empty ignored', () => {
  assert.deepEqual(addRecent(['a'], '  b  '), ['b', 'a']);
  assert.deepEqual(addRecent(['a'], '   '), ['a']);
});

test('a repeat moves to the top, any capitalisation, no duplicates', () => {
  assert.deepEqual(addRecent(['red dress', 'shoes'], 'Shoes'), ['Shoes', 'red dress']);
});

test('keeps at most 8', () => {
  let l: string[] = [];
  for (let i = 0; i < 12; i++) l = addRecent(l, `t${i}`);
  assert.equal(l.length, 8);
  assert.equal(l[0], 't11');
});

test('remove drops one entry', () => {
  assert.deepEqual(removeRecent(['a', 'b'], 'a'), ['b']);
});

test('storage: round trip, bad data ignored, throwing storage tolerated', () => {
  const store: Record<string, string> = {};
  (globalThis as any).window = {
    localStorage: {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = v; },
      removeItem: (k: string) => { delete store[k]; },
    },
  };
  saveRecent(['x', 'y']);
  assert.deepEqual(loadRecent(), ['x', 'y']);
  store[RECENT_SEARCHES_KEY] = '{not json';
  assert.deepEqual(loadRecent(), []);
  store[RECENT_SEARCHES_KEY] = '[1,"ok",null]';
  assert.deepEqual(loadRecent(), ['ok']);
  saveRecent([]);
  assert.equal(RECENT_SEARCHES_KEY in store, false);
  (globalThis as any).window = {
    localStorage: { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); }, removeItem() { throw new Error('blocked'); } },
  };
  assert.deepEqual(loadRecent(), []);
  saveRecent(['z']); // must not throw
  delete (globalThis as any).window;
});
