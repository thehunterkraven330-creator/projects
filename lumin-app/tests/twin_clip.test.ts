import test from 'node:test';
import assert from 'node:assert/strict';
import { productIdsInClip } from '../lib/twins';
import type { Twin } from '../lib/types';

const twin = (productId: string, startMs: number, endMs: number, reviewStatus?: 'pending' | 'approved' | 'flagged'): Twin =>
  ({ id: `${productId}-${startMs}`, productId, label: productId, startMs, endMs, reviewStatus }) as Twin;

test('a product on screen during the recording is in the clip', () => {
  const ids = productIdsInClip([twin('shirt', 0, 5000), twin('shoes', 12000, 15000)], 2, 6); // 2s..8s
  assert.deepEqual([...ids], ['shirt']);
});

test('a product that only appears after the recording ended is not', () => {
  assert.equal(productIdsInClip([twin('shoes', 12000, 15000)], 2, 6).size, 0);
});

test('touching at an edge does not count', () => {
  assert.equal(productIdsInClip([twin('a', 0, 2000)], 2, 6).size, 0); // ends exactly where the clip starts
  assert.equal(productIdsInClip([twin('a', 8000, 9000)], 2, 6).size, 0); // starts exactly where the clip ends
});

test('a reported twin never counts', () => {
  assert.equal(productIdsInClip([twin('a', 0, 5000, 'flagged')], 1, 2).size, 0);
});

test('with no clip length the window is the single moment', () => {
  const twins = [twin('a', 3000, 4000), twin('b', 5000, 6000)];
  assert.deepEqual([...productIdsInClip(twins, 3.5, null)], ['a']);
  assert.deepEqual([...productIdsInClip(twins, 3.5, 0)], ['a']);
});

test('no twins means nothing is singled out', () => {
  assert.equal(productIdsInClip(undefined, 2, 6).size, 0);
  assert.equal(productIdsInClip([], 2, 6).size, 0);
});

test('a product with two twins counts once', () => {
  const ids = productIdsInClip([twin('a', 0, 3000), twin('a', 4000, 7000)], 1, 5);
  assert.deepEqual([...ids], ['a']);
});
