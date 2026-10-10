import test from 'node:test';
import assert from 'node:assert/strict';
import { validateAssessmentAnswers } from './assessment.js';

const questions = [
  { question_id: 'q1', type: 'mcq', options: [{ id: 'a' }, { id: 'b' }] },
  { question_id: 'q2', type: 'code_output' },
  { question_id: 'q3', type: 'mcq', options: [{ id: 'a' }, { id: 'b' }] },
];

test('assessment validation requires a complete answer set', () => {
  assert.match(validateAssessmentAnswers(questions, { q1: 'a' }), /Answer question 2/);
  assert.match(validateAssessmentAnswers(questions, { q1: 'a', q2: ' ', q3: 'b' }), /Answer question 2/);
  assert.equal(validateAssessmentAnswers(questions, { q1: 'a', q2: '42', q3: 'b' }), '');
});

test('assessment validation rejects invalid options and oversized responses', () => {
  assert.match(validateAssessmentAnswers(questions, { q1: 'x', q2: '42', q3: 'b' }), /available option/);
  assert.match(validateAssessmentAnswers(questions, { q1: 'a', q2: 'x'.repeat(6001), q3: 'b' }), /6,000/);
});
