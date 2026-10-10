import test from 'node:test';
import assert from 'node:assert/strict';

import { getAdaptivePriorityDisplay } from './adaptivePriority.js';

test('labels assessment-supported demonstrated weaknesses', () => {
  assert.equal(
    getAdaptivePriorityDisplay('demonstrated_weakness').label,
    'Assessment-supported weakness',
  );
});

test('labels insufficient evidence without implying failure', () => {
  assert.equal(
    getAdaptivePriorityDisplay('insufficient_evidence').label,
    'Insufficient assessment evidence',
  );
});

test('labels upcoming learning without a demonstrated weakness', () => {
  assert.equal(
    getAdaptivePriorityDisplay('upcoming_learning').label,
    'Upcoming learning · no demonstrated weakness',
  );
});

test('does not render an unknown evidence category as a misleading label', () => {
  assert.equal(getAdaptivePriorityDisplay('unknown'), null);
});
