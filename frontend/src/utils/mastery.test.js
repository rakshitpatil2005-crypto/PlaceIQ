import test from 'node:test';
import assert from 'node:assert/strict';
import { formatMasteryScore, masteryStatusLabel } from './mastery.js';

test('mastery UI does not invent scores when evidence is insufficient', () => {
  assert.equal(formatMasteryScore(null), '—');
  assert.equal(formatMasteryScore(undefined), '—');
  assert.equal(masteryStatusLabel('insufficient_evidence'), 'Insufficient evidence');
});

test('mastery UI formats evidence scores and proficiency statuses', () => {
  assert.equal(formatMasteryScore(82.5), '82.5%');
  assert.equal(masteryStatusLabel('demonstrated_proficiency'), 'Demonstrated proficiency');
  assert.equal(masteryStatusLabel('unexpected'), 'Insufficient evidence');
});
