import test from 'node:test';
import assert from 'node:assert/strict';
import { getDashboardRecommendations } from './dashboardRecommendations.js';

const recommendation = (skillId) => ({
  skill_id: skillId,
  action: 'study',
  reason: 'This is based on roadmap context.',
  evidence: ['An incomplete roadmap task exists.'],
  next_step: 'Open a lesson.',
  href: `/learn?skill=${skillId}`,
});

test('dashboard limits recommendations to two valid learning actions', () => {
  const result = getDashboardRecommendations({
    recommendations: [
      recommendation('Python'),
      recommendation('SQL'),
      recommendation('Java'),
    ],
  });
  assert.deepEqual(result.map((item) => item.skill_id), ['Python', 'SQL']);
});

test('dashboard ignores malformed or non-learning recommendation links', () => {
  const result = getDashboardRecommendations({
    recommendations: [
      null,
      { ...recommendation('Python'), href: 'https://example.test' },
      { ...recommendation('SQL'), evidence: null },
      recommendation('JavaScript'),
    ],
  });
  assert.deepEqual(result.map((item) => item.skill_id), ['JavaScript']);
  assert.deepEqual(getDashboardRecommendations(null), []);
});
