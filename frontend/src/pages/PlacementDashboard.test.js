import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { createServer } from 'vite';

async function loadPlacementModules() {
  const vite = await createServer({
    configFile: fileURLToPath(new URL('../../vite.config.js', import.meta.url)),
    server: { middlewareMode: true, hmr: false },
    appType: 'custom',
  });
  const page = await vite.ssrLoadModule('/src/pages/PlacementDashboard.jsx');
  const helpers = await vite.ssrLoadModule('/src/utils/placementDashboard.js');
  return { vite, ...page, PlacementDashboard: page.default, ...helpers };
}

function renderView(View, props) {
  return renderToStaticMarkup(
    React.createElement(MemoryRouter, null, React.createElement(View, props)),
  );
}

test('placement navigation is staff/admin-only and routes do not replace the student dashboard', async () => {
  const { vite, isPlacementStaffRole, getNavigationItems } = await loadPlacementModules();
  try {
    assert.equal(isPlacementStaffRole('student'), false);
    assert.equal(isPlacementStaffRole('placement_staff'), true);
    assert.equal(isPlacementStaffRole('admin'), true);
    const studentItems = getNavigationItems('student').map(({ label }) => label);
    const staffItems = getNavigationItems('placement_staff').map(({ label }) => label);
    const adminItems = getNavigationItems('admin').map(({ label }) => label);
    assert.ok(studentItems.includes('Learn & Practice'));
    assert.ok(studentItems.includes('Premium'));
    assert.ok(!studentItems.includes('Placement Cell'));
    assert.ok(staffItems.includes('Placement Cell'));
    assert.ok(adminItems.includes('Placement Cell'));

    const appSource = await readFile(new URL('../App.jsx', import.meta.url), 'utf8');
    const navbarSource = await readFile(new URL('../components/Navbar.jsx', import.meta.url), 'utf8');
    assert.match(appSource, /<Route path="\/dashboard" element={<Dashboard \/>} \/>/);
    assert.match(appSource, /<Route\s+path="\/placement"/);
    assert.match(appSource, /<Route\s+path="\/placement\/students\/:studentId"/);
    assert.match(navbarSource, /getNavigationItems\(role\)/);
    assert.match(navbarSource, /aria-label="Main navigation"/);
    assert.match(navbarSource, /aria-label=\{collapsed \? 'Expand navigation' : 'Collapse navigation'\}/);
    assert.match(navbarSource, /aria-label="Open navigation menu"/);
    const styles = await readFile(new URL('../index.css', import.meta.url), 'utf8');
    assert.match(styles, /@media \(max-width: 767px\)/);
    assert.match(styles, /\.sidebar\.mobile-open\s*\{[\s\S]*?transform: translateX\(0\)/);
    assert.match(styles, /@media \(prefers-reduced-motion: reduce\)/);
    const { default: Navbar } = await vite.ssrLoadModule('/src/components/Navbar.jsx');
    const sidebarMarkup = renderView(Navbar, { collapsed: true, onCollapsedChange: () => {} });
    assert.match(sidebarMarkup, /aria-label="Main navigation"/);
    assert.match(sidebarMarkup, /aria-label="Open navigation menu"/);
    assert.match(sidebarMarkup, /aria-label="Expand navigation"/);
    assert.match(sidebarMarkup, /title="Dashboard"/);
    assert.doesNotMatch(sidebarMarkup, /href="\/placement"/);
  } finally {
    await vite.close();
  }
});

test('builds only supported filter, pagination, and allowlisted sort parameters', async () => {
  const { vite, buildPlacementQuery } = await loadPlacementModules();
  try {
    assert.deepEqual(
      buildPlacementQuery(
        { branch: ' CSE ', semester: '6', target_role: ' Backend Engineer ' },
        2,
        25,
        'readiness',
        'desc',
      ),
      {
        page: 2,
        page_size: 25,
        sort_by: 'readiness',
        sort_order: 'desc',
        branch: 'CSE',
        semester: 6,
        target_role: 'Backend Engineer',
      },
    );
    assert.deepEqual(
      buildPlacementQuery({ branch: '', semester: '', target_role: '' }),
      { page: 1, page_size: 25, sort_by: 'name', sort_order: 'asc' },
    );
  } finally {
    await vite.close();
  }
});

test('renders explicit loading, API-error, and forbidden states', async () => {
  const { vite, PlacementDashboardView } = await loadPlacementModules();
  try {
    assert.match(renderView(PlacementDashboardView, { access: 'loading' }), /Checking placement dashboard access/);
    assert.match(renderView(PlacementDashboardView, { loading: true }), /Loading placement-cell analytics/);
    assert.match(renderView(PlacementDashboardView, { error: { status: 500 } }), /analytics service is unavailable/i);
    assert.match(renderView(PlacementDashboardView, { access: 'forbidden' }), /Access forbidden/);
    assert.match(renderView(PlacementDashboardView, { error: { status: 403 } }), /not authorized/i);
  } finally {
    await vite.close();
  }
});

test('plots only recorded readiness and component measurements', async () => {
  const { vite, PlacementDashboardView } = await loadPlacementModules();
  try {
    const markup = renderView(PlacementDashboardView, {
      summary: {
        cohort: { student_count: 2, status: 'available' },
        readiness: { average: 62, student_count: 1 },
        components: {
          resume: { average: 0, student_count: 1 },
          roadmap: { average: null, student_count: 0 },
        },
        roadmap: {},
        interviews: {},
        common_missing_skills: { student_count: 0, skills: [] },
        readiness_trend: {
          status: 'available',
          points: [{ month: '2025-01', average_readiness: 0, student_count: 1 }],
        },
      },
      directory: { students: [], total_students: 0, page_size: 25 },
    });
    assert.match(markup, /Average readiness by component chart/);
    assert.match(markup, /Recorded readiness trend chart/);
    assert.doesNotMatch(markup, /No component score evidence is available to chart/);
  } finally {
    await vite.close();
  }
});

test('overview route renders before any student detail record is loaded', async () => {
  const { vite, PlacementDashboard } = await loadPlacementModules();
  try {
    const markup = renderView(PlacementDashboard, {});
    assert.match(markup, /Checking placement dashboard access/);
  } finally {
    await vite.close();
  }
});

test('renders empty cohorts and distinguishes unavailable evidence from measured values', async () => {
  const { vite, PlacementDashboardView } = await loadPlacementModules();
  try {
    const emptyMarkup = renderView(PlacementDashboardView, {
      summary: { cohort: { student_count: 0, status: 'empty' } },
      directory: { students: [], total_students: 0, page_size: 25 },
    });
    assert.match(emptyMarkup, /No students match these filters/);
    assert.match(emptyMarkup, /No metrics are inferred/);

    const markup = renderView(PlacementDashboardView, {
      summary: {
        cohort: { student_count: 2, status: 'available' },
        readiness: { average: null, student_count: 0 },
        components: {
          resume: { average: null, student_count: 0 },
          skill_gap: { average: 0, student_count: 1 },
          roadmap: { average: null, student_count: 0 },
          interview: { average: null, student_count: 0 },
        },
        roadmap: { average_progress_pct: null, completed_tasks: 0, total_tasks: 0 },
        interviews: { average_score: null, student_count: 0 },
        common_missing_skills: { student_count: 0, skills: [] },
        readiness_trend: { status: 'insufficient_history', points: [] },
      },
      directory: { students: [], total_students: 0, page_size: 25 },
    });
    assert.match(markup, /No evidence recorded/);
    assert.match(markup, /0%/);
    assert.match(markup, /History is sparse/);
    assert.match(markup, /No completed interview evidence/);
  } finally {
    await vite.close();
  }
});

test('renders supported filters, paginated student entries, and detail navigation', async () => {
  const { vite, PlacementDashboardView } = await loadPlacementModules();
  try {
    const markup = renderView(PlacementDashboardView, {
      summary: {
        cohort: { student_count: 26, status: 'available' },
        readiness: { average: 72, student_count: 20 },
        components: {},
        roadmap: {},
        interviews: {},
        common_missing_skills: { student_count: 0, skills: [] },
        readiness_trend: { status: 'unavailable', points: [] },
      },
      directory: {
        total_students: 26,
        page_size: 25,
        students: [{
          user_id: 47,
          name: 'A Student',
          branch: 'CSE',
          semester: 6,
          target_role: 'Developer',
          readiness_score: null,
          evidence_coverage: { available_components: 0, total_components: 4 },
          roadmap_progress_pct: null,
          interview_score: null,
        }],
      },
      page: 1,
      filters: { branch: 'CSE', semester: '6', target_role: 'Developer' },
    });
    assert.match(markup, /Branch/);
    assert.match(markup, /Semester/);
    assert.match(markup, /Target role/);
    assert.match(markup, /A Student/);
    assert.match(markup, /Page 1 of 2/);
    assert.match(markup, /disabled=""/);
    assert.match(markup, /href="\/placement\/students\/47"/);
    assert.match(markup, /0 \/ 4/);
  } finally {
    await vite.close();
  }
});

test('renders the minimized student drill-down and recorded-history empty state', async () => {
  const { vite, PlacementDashboardView } = await loadPlacementModules();
  try {
    const markup = renderView(PlacementDashboardView, {
      studentId: '47',
      detail: {
        student: { user_id: 47, name: 'A Student', branch: 'CSE', semester: 6, target_role: 'Developer' },
        readiness: {
          score: null,
          components: { resume_score: null, skill_score: 0, roadmap_score: null, interview_score: null },
          evidence_coverage: { available_components: 1, total_components: 4 },
        },
        skill_gap: { match_pct: null, missing_skills: [] },
        roadmap: { completed_tasks: 0, total_tasks: 0, progress_pct: null },
        interview: { score: null, weak_skills: [] },
        recorded_readiness_history: { status: 'unavailable', points: [] },
      },
    });
    assert.match(markup, /Authorized student drill-down/);
    assert.match(markup, /Back to placement dashboard/);
    assert.match(markup, /No evidence recorded/);
    assert.match(markup, /No recorded readiness history/);
    assert.doesNotMatch(markup, /password|resume text|private answer/i);
  } finally {
    await vite.close();
  }
});
