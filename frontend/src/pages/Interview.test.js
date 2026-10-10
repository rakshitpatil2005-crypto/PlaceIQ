import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

test('renders an accessible responsive interview setup with every focus choice', async () => {
  const vite = await createServer({
    configFile: fileURLToPath(new URL('../../vite.config.js', import.meta.url)),
    server: { middlewareMode: true },
    appType: 'custom',
  });

  try {
    const { default: Interview } = await vite.ssrLoadModule('/src/pages/Interview.jsx');
    const markup = renderToStaticMarkup(React.createElement(Interview));

    for (const label of [
      'Recommended for me',
      'Programming Languages',
      'Web Development',
      'Data Structures &amp; Algorithms',
      'Database &amp; SQL',
      'Core Computer Science',
      'AI &amp; Machine Learning',
      'Cloud Computing',
      'Full Stack Development',
      'My own focus',
    ]) {
      assert.ok(markup.includes(label), `Expected focus choice: ${label}`);
    }

    assert.match(markup, /aria-label="Interview difficulty"/);
    assert.match(markup, /aria-label="Interview focus area"/);
    assert.match(markup, /Start New Session/);
    assert.match(markup, /grid-cols-1 gap-3 sm:grid-cols-2/);
    assert.match(markup, /minmax\(17rem,1\.3fr\)/);
    assert.match(markup, /focus-visible:ring-brand-100/);
    assert.doesNotMatch(markup, /aria-label="Custom interview focus"/);
  } finally {
    await vite.close();
  }
});
