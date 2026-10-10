import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { createServer } from 'vite';

test('renders the direct answer and hides empty hints and example sections', async () => {
  const vite = await createServer({
    configFile: fileURLToPath(new URL('../../vite.config.js', import.meta.url)),
    server: { middlewareMode: true },
    appType: 'custom',
  });

  try {
    const { default: StudyCoachAnswer } = await vite.ssrLoadModule(
      '/src/components/StudyCoachAnswer.jsx',
    );
    const markup = renderToStaticMarkup(
      React.createElement(
        MemoryRouter,
        null,
        React.createElement(StudyCoachAnswer, {
          result: {
            source: 'groq',
            explanation: 'A JOIN combines rows from related tables.',
            hints: [],
            example: '',
            evidence: {
              status: 'insufficient_evidence',
              note: 'There is not enough assessment evidence.',
            },
            links: {
              lesson: '/learn?skill=SQL&lesson=lesson-1',
              practice: { href: '/learning/practice' },
              assessment: { href: '/learning/assessment' },
            },
          },
          onPractice: () => {},
          onAssessment: () => {},
          startingPractice: false,
          startingAssessment: false,
        }),
      ),
    );

    assert.match(markup, /A JOIN combines rows from related tables/);
    assert.doesNotMatch(markup, />Hints</);
    assert.doesNotMatch(markup, />Example</);
    assert.match(markup, /Assessment evidence:/);
    assert.match(markup, /Review lesson/);
  } finally {
    await vite.close();
  }
});

test('renders optional hints and example when present', async () => {
  const vite = await createServer({
    configFile: fileURLToPath(new URL('../../vite.config.js', import.meta.url)),
    server: { middlewareMode: true },
    appType: 'custom',
  });

  try {
    const { default: StudyCoachAnswer } = await vite.ssrLoadModule(
      '/src/components/StudyCoachAnswer.jsx',
    );
    const markup = renderToStaticMarkup(
      React.createElement(
        MemoryRouter,
        null,
        React.createElement(StudyCoachAnswer, {
          result: {
            source: 'groq',
            explanation: 'Precision is the share of predicted positives that are correct.',
            hints: ['Check the denominator used in precision.'],
            example: 'A classifier marks 10 items positive and 8 are truly positive.',
            evidence: {
              status: 'insufficient_evidence',
              note: 'There is not enough assessment evidence.',
            },
            links: {
              lesson: '/learn?skill=Statistics&lesson=lesson-1',
              practice: { href: '/learning/practice' },
              assessment: { href: '/learning/assessment' },
            },
          },
          onPractice: () => {},
          onAssessment: () => {},
          startingPractice: false,
          startingAssessment: false,
        }),
      ),
    );

    assert.match(markup, />Hints</);
    assert.match(markup, /Check the denominator used in precision/);
    assert.match(markup, />Example</);
    assert.match(markup, /8 are truly positive/);
  } finally {
    await vite.close();
  }
});
