import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { createServer } from 'vite';

test('Premium route and navigation entry are registered', async () => {
  const appSource = await readFile(new URL('../App.jsx', import.meta.url), 'utf8');
  const navbarSource = await readFile(new URL('../components/Navbar.jsx', import.meta.url), 'utf8');
  const navigationSource = await readFile(new URL('../utils/placementDashboard.js', import.meta.url), 'utf8');

  assert.match(appSource, /<Route path="\/premium" element={<Premium \/>} \/>/);
  assert.match(navbarSource, /getNavigationItems\(role\)/);
  assert.match(navigationSource, /path: '\/premium', icon: Crown, label: 'Premium'/);
});

test('shows an accessible loading state while the plan request is pending', async () => {
  const vite = await createServer({
    configFile: fileURLToPath(new URL('../../vite.config.js', import.meta.url)),
    server: { middlewareMode: true, hmr: false },
    appType: 'custom',
  });

  try {
    const { default: Premium } = await vite.ssrLoadModule('/src/pages/Premium.jsx');
    const markup = renderToStaticMarkup(
      React.createElement(MemoryRouter, null, React.createElement(Premium)),
    );
    assert.match(markup, /role="status"/);
    assert.match(markup, /Loading your plan and access status/);
  } finally {
    await vite.close();
  }
});

test('renders the Core plan, transparent pricing, feature comparison, and request-access action', async () => {
  const vite = await createServer({
    configFile: fileURLToPath(new URL('../../vite.config.js', import.meta.url)),
    server: { middlewareMode: true, hmr: false },
    appType: 'custom',
  });

  try {
    const { PremiumExperience } = await vite.ssrLoadModule('/src/pages/Premium.jsx');
    const markup = renderToStaticMarkup(
      React.createElement(
        MemoryRouter,
        null,
        React.createElement(PremiumExperience, {
          plan: {
            plan: 'free',
            entitlement_status: 'inactive',
            access_request_pending: false,
            pricing: {
              display: 'Pricing not configured',
              billing_period: '',
              payment_provider_configured: false,
            },
          },
          onRequestAccess: () => {},
        }),
      ),
    );

    assert.match(markup, /Your placement journey, in one clearer view/);
    assert.match(markup, /Core plan/);
    assert.match(markup, /Pricing not configured/);
    assert.match(markup, /Request Premium Access/);
    assert.match(markup, /No payment is taken/);
    assert.match(markup, /authorized administrator reviews requests/);
    assert.match(markup, /Advanced Progress Analytics/);
    assert.match(markup, /Personalized Placement Report/);
    assert.match(markup, /Core and Premium/);
    assert.match(markup, /Not configured/);
    assert.match(markup, /href="\/dashboard"/);
    assert.doesNotMatch(markup, /Premium access active/);

    const requestingMarkup = renderToStaticMarkup(
      React.createElement(
        MemoryRouter,
        null,
        React.createElement(PremiumExperience, {
          plan: {
            plan: 'free',
            entitlement_status: 'inactive',
            access_request_pending: false,
            pricing: { display: 'Pricing not configured', payment_provider_configured: false },
          },
          requesting: true,
          onRequestAccess: () => {},
        }),
      ),
    );
    assert.match(requestingMarkup, /Submitting request/);
    assert.match(requestingMarkup, /disabled=""/);
  } finally {
    await vite.close();
  }
});

test('renders active Premium with evidence-empty and measured states rather than fabricated scores', async () => {
  const vite = await createServer({
    configFile: fileURLToPath(new URL('../../vite.config.js', import.meta.url)),
    server: { middlewareMode: true, hmr: false },
    appType: 'custom',
  });

  try {
    const { PremiumExperience } = await vite.ssrLoadModule('/src/pages/Premium.jsx');
    const markup = renderToStaticMarkup(
      React.createElement(
        MemoryRouter,
        null,
        React.createElement(PremiumExperience, {
          plan: {
            plan: 'premium',
            entitlement_status: 'active',
            pricing: { display: 'Pricing configured by admin', payment_provider_configured: false },
          },
          overview: {
            analytics: {
              readiness_current: { total: 72 },
              readiness_history: [{ id: 1, total: 72, created_at: '2026-10-10' }],
              roadmap_progress: null,
              assessment_accuracy: { assessments: 1, correct: 3, questions: 4, accuracy_pct: 75 },
              skill_mastery: [
                {
                  skill_id: 'Python',
                  status: 'demonstrated_proficiency',
                  score_pct: 90,
                  evidence_assessments: 2,
                  evidence_questions: 8,
                },
                {
                  skill_id: 'SQL',
                  status: 'insufficient_evidence',
                  score_pct: null,
                  evidence_assessments: 1,
                  evidence_questions: 2,
                },
              ],
              recommendations: [],
              recommendation_notice: 'Recommendations do not change readiness.',
            },
            placement_report: {
              target_role: null,
              resume: null,
              skill_gap: {
                match_pct: 70,
                missing: [{ skill: 'System Design', status: 'learn from scratch', weight: 3 }],
              },
              roadmap: null,
              latest_interview: {
                completed: true,
                overall_score: 75,
                weak_skills: ['System Design'],
                feedback: [
                  {
                    question_index: 0,
                    score_out_of_10: 8,
                    is_correct: true,
                    explanation: 'The submitted choice uses the expected method.',
                    improvement_suggestions: 'Review the related concept.',
                  },
                ],
              },
            },
            notice: 'Measured from saved records.',
          },
        }),
      ),
    );

    assert.match(markup, /Premium access active/);
    assert.match(markup, /72\/100/);
    assert.match(markup, /Not enough stored evidence yet/);
    assert.match(markup, /Latest recorded readiness: <strong>72\/100<\/strong>/);
    assert.match(markup, /Demonstrated proficiency/);
    assert.match(markup, /90% demonstrated accuracy/);
    assert.match(markup, /Not enough assessment evidence for a mastery score/);
    assert.match(markup, /System Design · learn from scratch · priority weight 3\/3/);
    assert.match(markup, /No resume record yet/);
    assert.match(markup, /No saved roadmap yet/);
    assert.match(markup, /Question 1 · 8\/10 · Correct/);
    assert.match(markup, /The submitted choice uses the expected method/);
    assert.match(markup, /Next improvement/);
    assert.match(markup, /Recommendations do not change readiness/);
  } finally {
    await vite.close();
  }
});

test('Premium report preview shows clear empty states without inventing evidence', async () => {
  const vite = await createServer({
    configFile: fileURLToPath(new URL('../../vite.config.js', import.meta.url)),
    server: { middlewareMode: true, hmr: false },
    appType: 'custom',
  });

  try {
    const { PremiumExperience } = await vite.ssrLoadModule('/src/pages/Premium.jsx');
    const markup = renderToStaticMarkup(
      React.createElement(
        MemoryRouter,
        null,
        React.createElement(PremiumExperience, {
          plan: {
            plan: 'premium',
            entitlement_status: 'active',
            pricing: { display: 'Pricing not configured' },
          },
          overview: {
            analytics: {
              readiness_current: null,
              readiness_history: [],
              roadmap_progress: null,
              assessment_accuracy: null,
              skill_mastery: [],
              recommendations: [],
            },
            placement_report: { resume: null, skill_gap: null, roadmap: null, latest_interview: null },
          },
        }),
      ),
    );

    assert.match(markup, /Placement report preview/);
    assert.match(markup, /No readiness history has been recorded yet/);
    assert.match(markup, /No submitted assessment evidence yet/);
    assert.match(markup, /No saved interview evidence yet/);
    assert.match(markup, /Not enough stored evidence yet/);
    assert.doesNotMatch(markup, />0%<\/p>/);
    assert.doesNotMatch(markup, />0\/100<\/p>/);
  } finally {
    await vite.close();
  }
});

test('access request submits once, shows pending only after server confirmation, and permits retry on failure', async () => {
  const vite = await createServer({
    configFile: fileURLToPath(new URL('../../vite.config.js', import.meta.url)),
    server: { middlewareMode: true, hmr: false },
    appType: 'custom',
  });

  try {
    const { PremiumExperience } = await vite.ssrLoadModule('/src/pages/Premium.jsx');
    const { submitPremiumAccessRequest } = await vite.ssrLoadModule('/src/utils/premiumAccessRequest.js');
    const currentPlan = {
      plan: 'free',
      entitlement_status: 'inactive',
      access_request_pending: false,
      pricing: { display: 'Pricing not configured' },
    };
    let renderedPlan = currentPlan;
    const view = (props = {}) => renderToStaticMarkup(
      React.createElement(
        MemoryRouter,
        null,
        React.createElement(PremiumExperience, { plan: renderedPlan, onRequestAccess: () => {}, ...props }),
      ),
    );

    const initialMarkup = view();
    assert.match(initialMarkup, /Request Premium Access/);
    assert.doesNotMatch(initialMarkup, /role="status"/);

    let resolveRequest;
    let requestCount = 0;
    let requestLock = { current: false };
    let plan = currentPlan;
    let message = '';
    let error = '';
    let requesting = false;
    const postRequest = () => {
      requestCount += 1;
      return new Promise((resolve) => { resolveRequest = resolve; });
    };
    const state = {
      requestLock,
      currentPlan: plan,
      postRequest,
      setRequesting(value) { requesting = value; },
      setError(value) { error = value; },
      setRequestMessage(value) { message = value; },
      setPlan(value) { plan = value; },
      setRequestFailed() {},
    };
    const first = submitPremiumAccessRequest(state);
    const duplicate = submitPremiumAccessRequest(state);
    assert.equal(requestCount, 1);
    assert.equal(requesting, true);
    assert.equal(message, '');
    const loadingMarkup = view({ requesting: true });
    assert.match(loadingMarkup, /Submitting request/);
    assert.match(loadingMarkup, /disabled=""/);
    assert.doesNotMatch(loadingMarkup, /role="status"/);

    const confirmedPlan = {
      ...currentPlan,
      access_request_pending: true,
      status: 'request_recorded',
      message: 'Your demo access request was recorded.',
    };
    resolveRequest({ data: confirmedPlan });
    await Promise.all([first, duplicate]);

    assert.equal(plan, confirmedPlan);
    assert.equal(requesting, false);
    assert.equal(error, '');
    assert.match(message, /pending review/);
    renderedPlan = plan;
    const pendingMarkup = view({ requestMessage: message });
    assert.match(pendingMarkup, /Request Pending/);
    assert.match(pendingMarkup, /pending review/);
    assert.match(pendingMarkup, /disabled=""/);

    let requestFailed = false;
    error = '';
    const requestFailure = new Error('Request service is temporarily unavailable.');
    requestFailure.response = { data: { detail: requestFailure.message } };
    renderedPlan = currentPlan;
    await submitPremiumAccessRequest({
      ...state,
      currentPlan,
      requestLock: { current: false },
      postRequest: async () => { throw requestFailure; },
      setRequestFailed(value) { requestFailed = value; },
    });
    assert.equal(requesting, false);
    assert.equal(requestFailed, true);
    assert.equal(error, 'Request service is temporarily unavailable.');
    const retryMarkup = view({ error, retryRequest: requestFailed });
    assert.match(retryMarkup, /role="alert"/);
    assert.match(retryMarkup, /Request service is temporarily unavailable/);
    assert.match(retryMarkup, /Retry access request/);
    assert.match(retryMarkup, /Request Premium Access/);
    assert.doesNotMatch(retryMarkup, /Request Pending/);

    await submitPremiumAccessRequest({
      ...state,
      currentPlan,
      requestLock: { current: false },
      postRequest: async () => ({ data: confirmedPlan }),
      setRequestFailed(value) { requestFailed = value; },
    });
    assert.equal(requestFailed, false);
    assert.equal(error, '');
    assert.match(message, /pending review/);
    assert.equal(plan, confirmedPlan);
  } finally {
    await vite.close();
  }
});

test('renders error and success status messages accessibly', async () => {
  const vite = await createServer({
    configFile: fileURLToPath(new URL('../../vite.config.js', import.meta.url)),
    server: { middlewareMode: true, hmr: false },
    appType: 'custom',
  });

  test('checkout remains unavailable unless the backend marks pricing and Test Mode credentials ready', async () => {
    const vite = await createServer({
      configFile: fileURLToPath(new URL('../../vite.config.js', import.meta.url)),
      server: { middlewareMode: true, hmr: false },
      appType: 'custom',
    });

    try {
      const { PremiumExperience } = await vite.ssrLoadModule('/src/pages/Premium.jsx');
      const render = (pricing) => renderToStaticMarkup(
        React.createElement(
          MemoryRouter,
          null,
          React.createElement(PremiumExperience, {
            plan: {
              plan: 'free',
              entitlement_status: 'inactive',
              pricing,
            },
            onRequestAccess: () => {},
            onStartCheckout: () => {},
          }),
        ),
      );

      const noAmount = render({
        display: 'Pricing not configured',
        checkout_enabled: false,
        unavailable_reason: 'Premium pricing is not configured.',
      });
      assert.doesNotMatch(noAmount, /Continue to Test Mode checkout/);
      assert.match(noAmount, /Premium pricing is not configured/);

      const noCredentials = render({
        display: 'Premium plan',
        checkout_enabled: false,
        unavailable_reason: 'Razorpay Test Mode credentials are not fully configured.',
      });
      assert.doesNotMatch(noCredentials, /Continue to Test Mode checkout/);
      assert.match(noCredentials, /Razorpay Test Mode credentials are not fully configured/);

      const enabled = render({
        display: 'Pricing not configured',
        checkout_enabled: true,
        amount: 2500,
        currency: 'INR',
      });
      assert.match(enabled, /Continue to Test Mode checkout/);
      assert.match(enabled, /Razorpay Test Mode only/);
      assert.match(enabled, /₹25\.00/);
      assert.doesNotMatch(enabled, /Pricing not configured/);
    } finally {
      await vite.close();
    }
  });

  test('shows pending payment verification, refresh affordance, and retryable errors', async () => {
    const vite = await createServer({
      configFile: fileURLToPath(new URL('../../vite.config.js', import.meta.url)),
      server: { middlewareMode: true, hmr: false },
      appType: 'custom',
    });

    try {
      const { PremiumExperience } = await vite.ssrLoadModule('/src/pages/Premium.jsx');
      const markup = renderToStaticMarkup(
        React.createElement(
          MemoryRouter,
          null,
          React.createElement(PremiumExperience, {
            plan: {
              plan: 'free',
              entitlement_status: 'inactive',
              pricing: { checkout_enabled: false },
            },
            paymentOrderId: 7,
            paymentMessage: 'Payment verification is pending.',
            paymentError: 'Payment status is temporarily unavailable.',
            onRefreshPaymentStatus: () => {},
          }),
        ),
      );
      assert.match(markup, /Payment verification is pending/);
      assert.match(markup, /Refresh payment status/);
      assert.match(markup, /Payment status is temporarily unavailable/);
    } finally {
      await vite.close();
    }
  });

  try {
    const { PremiumExperience } = await vite.ssrLoadModule('/src/pages/Premium.jsx');
    const markup = renderToStaticMarkup(
      React.createElement(
        MemoryRouter,
        null,
        React.createElement(PremiumExperience, {
          plan: {
            plan: 'free',
            entitlement_status: 'inactive',
            access_request_pending: true,
            pricing: { display: 'Pricing not configured', payment_provider_configured: false },
          },
          error: 'Plan information could not be refreshed.',
          requestMessage: 'Your demo request was recorded. No payment was taken.',
          onRetry: () => {},
        }),
      ),
    );
    assert.match(markup, /role="alert"/);
    assert.match(markup, /role="status"/);
    assert.match(markup, /Request Pending/);
    assert.match(markup, /Try again/);
  } finally {
    await vite.close();
  }
});
