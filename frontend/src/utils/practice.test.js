import test from 'node:test';
import assert from 'node:assert/strict';
import { validatePracticeAnswer } from './practice.js';

test('practice answer validation rejects empty responses', () => {
  assert.match(validatePracticeAnswer({ type: 'mcq' }, ''), /Select an answer/);
  assert.match(validatePracticeAnswer({ type: 'coding' }, '   '), /Enter an answer/);
});

test('practice answer validation checks choice identifiers and answer length', () => {
  const question = { type: 'mcq', options: [{ id: 'a' }, { id: 'b' }] };
  assert.match(validatePracticeAnswer(question, 'other'), /available answer options/);
  assert.match(validatePracticeAnswer({ type: 'coding' }, 'x'.repeat(6001)), /6,000/);
  assert.equal(validatePracticeAnswer(question, 'a'), '');
});
