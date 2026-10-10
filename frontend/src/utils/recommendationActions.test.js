import test from 'node:test';
import assert from 'node:assert/strict';

import { recommendationLinkLabel } from './recommendationActions.js';

test('recommendation links guide students to the relevant lesson action', () => {
  assert.equal(recommendationLinkLabel('practise'), 'Open lesson to practise');
  assert.equal(recommendationLinkLabel('reassess'), 'Open lesson to reassess');
  assert.equal(recommendationLinkLabel('revise'), 'Review lesson and practise');
  assert.equal(recommendationLinkLabel('study'), 'Open learning lesson');
});
