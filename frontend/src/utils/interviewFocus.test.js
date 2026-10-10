import assert from 'node:assert/strict';
import test from 'node:test';
import {
  INTERVIEW_FOCUS_OPTIONS,
  interviewFocusDescription,
  interviewGenerationError,
  interviewFocusRequestValue,
  interviewGenerationReducer,
} from './interviewFocus.js';

test('interview focus menu contains the recommended, requested, and custom choices', () => {
  assert.deepEqual(
    INTERVIEW_FOCUS_OPTIONS.map(({ value }) => value),
    [
      'recommended',
      'programming_languages',
      'web_development',
      'data_structures_algorithms',
      'database_sql',
      'core_computer_science',
      'ai_machine_learning',
      'cloud_computing',
      'full_stack_development',
      'custom',
    ],
  );
  assert.ok(INTERVIEW_FOCUS_OPTIONS.every(({ description }) => description.trim()));
  assert.match(interviewFocusDescription('recommended'), /saved role, resume skills, skill gaps/i);
});

test('custom focus is trimmed and sent through the existing focus_area query value', () => {
  assert.equal(interviewFocusRequestValue('recommended', ''), 'recommended');
  assert.equal(interviewFocusRequestValue('custom', '  Python  '), 'custom:Python');
  assert.equal(interviewFocusRequestValue('custom', ''), 'custom:');
});

test('generation success clears prior errors and loading state', () => {
  const previous = { loading: true, error: 'Interview unavailable', notice: 'Old notice' };

  assert.deepEqual(
    interviewGenerationReducer(previous, { type: 'success', contentSource: 'llm' }),
    { loading: false, error: '', notice: '' },
  );
  assert.deepEqual(
    interviewGenerationReducer(previous, { type: 'failure', message: 'Try again.' }),
    { loading: false, error: 'Try again.', notice: '' },
  );
});

test('generation errors distinguish provider limits and preserve active sessions', () => {
  assert.match(
    interviewGenerationError(429, 'provider detail', true, '20'),
    /current interview session and saved results are unchanged.*rate-limited.*wait about 20 seconds/i,
  );
  assert.match(
    interviewGenerationError(503, 'Generated interview validation failed (option_count). Please retry.', false),
    /validation failed \(option_count\).*retry/i,
  );
  assert.match(
    interviewGenerationError(429, 'Provider quota is currently exhausted.', false),
    /quota.*exhausted/i,
  );
});
