import assert from 'node:assert/strict';
import test from 'node:test';

import { isKstRefreshImminent } from './formatters';

test('isKstRefreshImminent returns true from 59:50 until the hour changes', () => {
  assert.equal(isKstRefreshImminent('2026-09-18T09:59:49+09:00'), false);
  assert.equal(isKstRefreshImminent('2026-09-18T09:59:50+09:00'), true);
  assert.equal(isKstRefreshImminent('2026-09-18T09:59:59+09:00'), true);
  assert.equal(isKstRefreshImminent('2026-09-18T10:00:00+09:00'), false);
});

test('isKstRefreshImminent rejects missing and invalid timestamps', () => {
  assert.equal(isKstRefreshImminent(), false);
  assert.equal(isKstRefreshImminent('invalid'), false);
});
