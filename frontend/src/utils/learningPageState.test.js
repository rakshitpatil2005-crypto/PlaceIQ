import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { createServer } from 'vite';
import { getActiveCoachForm } from './learningPageState.js';

test('renders the Learning component loading state before a SQL course is available', async () => {
  const vite = await createServer({
    configFile: fileURLToPath(new URL('../../vite.config.js', import.meta.url)),
    server: { middlewareMode: true },
    appType: 'custom',
  });

  try {
    const [
      { default: Learning },
      { default: LearningLessonContent },
    ] = await Promise.all([
      vite.ssrLoadModule('/src/pages/Learning.jsx'),
      vite.ssrLoadModule('/src/components/LearningLessonContent.jsx'),
    ]);
    const markup = renderToStaticMarkup(
      React.createElement(
        MemoryRouter,
        { initialEntries: ['/learn?skill=SQL&lesson=lesson-1'] },
        React.createElement(Learning),
      ),
    );

    assert.match(markup, /Preparing your skill lesson/);
    assert.doesNotMatch(markup, /Ask the Study Coach/);

    const sqlLessonMarkup = renderToStaticMarkup(
      React.createElement(LearningLessonContent, {
        lesson: {
          lesson_id: 'lesson-1',
          title: 'SQL Foundations',
          introduction: 'SQL organizes and retrieves data from relational tables.',
          explanation: 'A SELECT query reads requested columns and rows from a table.',
          example: 'SELECT name FROM students;',
          code_example: 'SELECT name FROM students;',
          code_language: 'sql',
          example_explanation: 'This query returns the name column from each student row.',
          real_world_applications: ['Reading records for an application feature.'],
          common_mistakes: ['Forgetting which table contains the requested column.'],
          key_takeaways: ['Choose the required columns explicitly.'],
          quick_recap: 'SELECT identifies which table values to read.',
        },
      }),
    );
    assert.match(sqlLessonMarkup, /SQL organizes and retrieves data/);
    assert.match(sqlLessonMarkup, /SELECT name FROM students/);
    assert.match(sqlLessonMarkup, /Quick recap/);
  } finally {
    await vite.close();
  }
});

test('does not create coach state when the selected lesson is unavailable', () => {
  assert.equal(getActiveCoachForm(null, null), null);
});

test('Learning lesson content component tolerates an unavailable lesson', async () => {
  const vite = await createServer({
    configFile: fileURLToPath(new URL('../../vite.config.js', import.meta.url)),
    server: { middlewareMode: true },
    appType: 'custom',
  });

  try {
    const { default: LearningLessonContent } = await vite.ssrLoadModule(
      '/src/components/LearningLessonContent.jsx',
    );
    assert.equal(
      renderToStaticMarkup(React.createElement(LearningLessonContent, { lesson: null })),
      '',
    );
  } finally {
    await vite.close();
  }
});

test('initializes coach form from the selected SQL lesson without replacing its content', () => {
  const sqlLesson = {
    lesson_id: 'lesson-1',
    title: 'SQL Foundations',
    explanation: 'A SQL explanation supplied by the learning course.',
  };

  const form = getActiveCoachForm(null, sqlLesson);

  assert.deepEqual(form, {
    lessonId: 'lesson-1',
    concept: 'SQL Foundations',
    question: '',
  });
  assert.equal(sqlLesson.explanation, 'A SQL explanation supplied by the learning course.');
});

test('uses saved coach inputs only for the currently selected lesson', () => {
  const saved = { lessonId: 'lesson-1', concept: 'Joins', question: 'Which join should I use?' };

  assert.equal(getActiveCoachForm(saved, { lesson_id: 'lesson-1', title: 'SQL Joins' }), saved);
  assert.deepEqual(
    getActiveCoachForm(saved, { lesson_id: 'lesson-2', title: 'SQL Aggregates' }),
    { lessonId: 'lesson-2', concept: 'SQL Aggregates', question: '' },
  );
});
