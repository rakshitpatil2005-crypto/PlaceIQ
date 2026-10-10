import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import RoadmapLearningLink from './RoadmapLearningLink.js';

test('renders a visible accessible link to the selected canonical skill lesson', () => {
  const markup = renderToStaticMarkup(
    createElement(
      MemoryRouter,
      { initialEntries: ['/roadmap'] },
      createElement(RoadmapLearningLink, { skillId: 'JavaScript' }),
    ),
  );

  assert.match(markup, /<a\b/);
  assert.match(markup, /href="\/learn\?skill=JavaScript"/);
  assert.match(markup, />Open skill lesson<\/a>/);
  assert.doesNotMatch(markup, /<a[^>]*\bhidden\b|<a[^>]*aria-hidden="true"/);
});

test('encodes canonical skill identifiers in the learning page URL', () => {
  const markup = renderToStaticMarkup(
    createElement(
      MemoryRouter,
      { initialEntries: ['/roadmap'] },
      createElement(RoadmapLearningLink, { skillId: 'C++' }),
    ),
  );

  assert.match(markup, /href="\/learn\?skill=C%2B%2B"/);
});
