import assert from 'node:assert/strict';
import test from 'node:test';
import {
  createStudyCoachRequest,
  STUDY_COACH_CONCEPT_LIMIT,
  STUDY_COACH_QUESTION_LIMIT,
} from './studyCoach.js';

test('study coach request uses the selected skill and lesson with trimmed inputs', () => {
  assert.deepEqual(
    createStudyCoachRequest({
      skillId: 'JavaScript',
      lessonId: 'lesson-2',
      concept: '  Promises  ',
      question: '  How does chaining work?  ',
    }),
    {
      skill_id: 'JavaScript',
      lesson_id: 'lesson-2',
      concept: 'Promises',
      question: 'How does chaining work?',
    },
  );
});

test('study coach request permits an omitted optional question', () => {
  assert.equal(
    createStudyCoachRequest({
      skillId: 'Python',
      lessonId: 'lesson-1',
      concept: 'Lists',
      question: '',
    }).question,
    null,
  );
});

test('study coach request rejects empty and oversized inputs', () => {
  assert.throws(
    () => createStudyCoachRequest({ skillId: 'Python', lessonId: 'lesson-1', concept: ' ' }),
    /Enter a concept/,
  );
  assert.throws(
    () => createStudyCoachRequest({
      skillId: 'Python',
      lessonId: 'lesson-1',
      concept: 'x'.repeat(STUDY_COACH_CONCEPT_LIMIT + 1),
    }),
    /concept under/,
  );
  assert.throws(
    () => createStudyCoachRequest({
      skillId: 'Python',
      lessonId: 'lesson-1',
      concept: 'Lists',
      question: 'x'.repeat(STUDY_COACH_QUESTION_LIMIT + 1),
    }),
    /question under/,
  );
});
