import test from 'node:test';
import assert from 'node:assert/strict';
import { formatCount } from '../lib/format.ts';

test('small counts are shown as they are', () => {
  assert.equal(formatCount(0), '0');
  assert.equal(formatCount(7), '7');
  assert.equal(formatCount(999), '999');
});

test('thousands: one decimal at most, no trailing .0', () => {
  assert.equal(formatCount(1000), '1k');
  assert.equal(formatCount(1049), '1k');
  assert.equal(formatCount(4500), '4.5k');
  assert.equal(formatCount(12300), '12.3k');
});

test('rolls up instead of reading 1000k', () => {
  assert.equal(formatCount(999949), '999.9k');
  assert.equal(formatCount(999950), '1M');
  assert.equal(formatCount(1_000_000), '1M');
  assert.equal(formatCount(2_500_000), '2.5M');
  assert.equal(formatCount(1_000_000_000), '1B');
});

test('bad input reads 0', () => {
  assert.equal(formatCount(-3), '0');
  assert.equal(formatCount(NaN), '0');
});
