import { useCallback, useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import {
  AlertCircle, ArrowRight, BookOpenCheck, BriefcaseBusiness, Check,
  Crown, FileSearch, Gauge, Loader, Map, MessageSquareText, Sparkles, Target,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import api from '../api';
import { submitPremiumAccessRequest } from '../utils/premiumAccessRequest';
import {
  createPremiumCheckoutOptions,
  loadRazorpayCheckout,
  preparePremiumCheckout,
  reservePremiumCheckout,
  verifyPremiumCheckout,
} from '../utils/premiumPayment';

const premiumFeatures = [
  {
    icon: FileSearch,
    title: 'Advanced Resume Intelligence',
    text: 'Bring your latest ATS score, extracted skills, projects, and role-match evidence together.',
    area: 'Available in Core',
  },
  {
    icon: Map,
    title: 'Personalized Placement Roadmap',
    text: 'Review real task completion and explainable next steps informed by your learning evidence.',
    area: 'Available in Core',
  },
  {
    icon: MessageSquareText,
    title: 'Advanced Mock Interview',
    text: 'Keep the established five technical MCQs and three HR prompts, with saved score and weak-skill feedback.',
    area: 'Available in Core',
  },
  {
    icon: BookOpenCheck,
    title: 'Context-aware Study Coach',
    text: 'Use lesson-grounded explanations, hints, examples, and safe stored-lesson fallback.',
    area: 'Available in Core',
  },
  {
    icon: Gauge,
    title: 'Advanced Progress Analytics',
    text: 'See actual readiness history, assessment accuracy, roadmap completion, and evidence-based mastery.',
    area: 'Premium workspace',
  },
  {
    icon: BriefcaseBusiness,
    title: 'Personalized Placement Report',
    text: 'Review your real resume, gap, roadmap, interview, and readiness evidence in one private view.',
    area: 'Premium workspace',
  },
];

function EvidenceValue({ label, value, suffix = '' }) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p>
        <p className="mt-2 text-sm text-slate-500">Not enough stored evidence yet</p>
      </div>
    );
  }
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-extrabold text-slate-900">{value}{suffix}</p>
    </div>
  );
}

function ReadinessTrend({ history = [] }) {
  if (!history.length) {
    return <p className="mt-3 text-sm text-slate-500">No readiness history has been recorded yet.</p>;
  }
  const scores = history.map((item) => Number(item.total)).filter(Number.isFinite);
  if (!scores.length) {
    return <p className="mt-3 text-sm text-slate-500">No readiness history has been recorded yet.</p>;
  }
  const min = Math.min(...scores);
  const max = Math.max(...scores);
  const points = scores.map((score, index) => {
    const x = scores.length === 1 ? 50 : (index / (scores.length - 1)) * 100;
    const y = max === min ? 50 : 100 - ((score - min) / (max - min)) * 80 - 10;
    return `${x},${y}`;
  }).join(' ');
  return (
    <div className="mt-3">
      {scores.length > 1 ? (
        <svg viewBox="0 0 100 100" role="img" aria-label="Readiness score history trend" className="h-28 w-full overflow-visible">
          <polyline points={points} fill="none" stroke="currentColor" strokeWidth="3" vectorEffect="non-scaling-stroke" className="text-brand-600" />
          {scores.map((score, index) => (
            <circle
              key={`${history[index]?.id || index}-${score}`}
              cx={scores.length === 1 ? 50 : (index / (scores.length - 1)) * 100}
              cy={max === min ? 50 : 100 - ((score - min) / (max - min)) * 80 - 10}
              r="2.5"
              className="fill-brand-600"
            />
          ))}
        </svg>
      ) : (
        <p className="text-sm text-slate-600">Latest recorded readiness: <strong>{scores[0]}/100</strong></p>
      )}
      <div className="flex flex-wrap gap-2">
        {history.slice(-6).map((item, index) => (
          <span key={item.id || `${item.created_at}-${index}`} className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-600">
            {item.total}/100
          </span>
        ))}
      </div>
    </div>
  );
}

export function PremiumExperience({
  plan,
  overview,
  onRequestAccess,
  requesting = false,
  requestMessage = '',
  error = '',
  onRetry,
  retryRequest = false,
  checkoutBusy = false,
  onStartCheckout,
  paymentOrderId,
  paymentMessage = '',
  paymentError = '',
  onRefreshPaymentStatus,
}) {
  const premiumActive = plan?.plan === 'premium' && plan?.entitlement_status === 'active';
  const pricing = plan?.pricing || {};
  const analytics = overview?.analytics || {};
  const report = overview?.placement_report || {};
  const roadmapProgress = analytics.roadmap_progress;
  const accuracy = analytics.assessment_accuracy;
  const recommendations = analytics.recommendations || [];
  const mastery = analytics.skill_mastery || [];
  let configuredPrice = null;
  if (pricing.checkout_enabled && Number.isFinite(Number(pricing.amount))) {
    try {
      const formatter = new Intl.NumberFormat(undefined, {
        style: 'currency',
        currency: pricing.currency,
      });
      const fractionDigits = formatter.resolvedOptions().maximumFractionDigits;
      configuredPrice = formatter.format(Number(pricing.amount) / (10 ** fractionDigits));
    } catch {
      configuredPrice = `${pricing.amount} ${pricing.currency} minor units`;
    }
  }
  const pricingDisplay = pricing.display === 'Pricing not configured' && configuredPrice
    ? configuredPrice
    : pricing.display || 'Pricing not configured';
  const missingSkills = (report.skill_gap?.missing || [])
    .map((item) => (typeof item === 'string' ? { skill: item } : item))
    .filter((item) => item && typeof item.skill === 'string' && item.skill.trim());

  return (
    <motion.div initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} className="mx-auto max-w-6xl space-y-7">
      <section className="relative overflow-hidden rounded-[2rem] bg-gradient-to-br from-emerald-950 via-emerald-900 to-teal-800 p-7 text-white shadow-xl sm:p-10">
        <div className="pointer-events-none absolute -right-16 -top-20 h-64 w-64 rounded-full bg-emerald-300/10 blur-3xl" />
        <div className="relative grid gap-8 lg:grid-cols-[1.4fr_0.8fr] lg:items-center">
          <div>
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3 py-1.5 text-xs font-semibold">
              <Crown size={15} /> PLACEIQ PREMIUM
            </div>
            <h1 className="max-w-2xl text-3xl font-black tracking-tight sm:text-5xl">Your placement journey, in one clearer view.</h1>
            <p className="mt-4 max-w-2xl text-sm leading-7 text-emerald-50/90 sm:text-base">
              Connect your real resume, VTU skill gaps, learning progress, interview feedback, and readiness history—without changing how your core tools work.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              {premiumActive ? (
                <span className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-white px-5 py-2.5 text-sm font-bold text-emerald-900">
                  <Check size={17} /> Premium access active
                </span>
              ) : (
                <button
                  type="button"
                  onClick={onRequestAccess}
                  disabled={requesting || plan?.access_request_pending}
                  className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-white px-5 py-2.5 text-sm font-bold text-emerald-900 transition hover:bg-emerald-50 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-white/40 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
                >
                  {requesting ? <Loader className="animate-spin" size={17} /> : <Crown size={17} />}
                  {requesting ? 'Submitting request…' : plan?.access_request_pending ? 'Request Pending' : 'Request Premium Access'}
                  {!requesting && !plan?.access_request_pending && <ArrowRight size={17} />}
                </button>
              )}
              {!premiumActive && pricing.checkout_enabled && (
                <button
                  type="button"
                  onClick={onStartCheckout}
                  disabled={checkoutBusy || Boolean(paymentOrderId)}
                  className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-5 py-2.5 text-sm font-bold text-emerald-950 transition hover:bg-emerald-100 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-white/40 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
                >
                  {checkoutBusy ? <Loader className="animate-spin" size={17} /> : <Check size={17} />}
                  {checkoutBusy
                    ? 'Connecting to Razorpay…'
                    : paymentOrderId ? 'Payment verification pending' : 'Continue to Test Mode checkout'}
                </button>
              )}
              <Link to="/dashboard" className="inline-flex min-h-11 w-full items-center justify-center rounded-xl border border-white/25 px-5 py-2.5 text-sm font-semibold text-white hover:bg-white/10 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-white/40 sm:w-auto">
                Explore Core features
              </Link>
            </div>
            <p className="mt-3 max-w-xl text-xs leading-5 text-emerald-100/80">
              No payment is taken by an access request. {pricing.checkout_enabled
                ? 'Checkout is Razorpay Test Mode only; PlaceIQ grants access only after server-confirmed payment capture.'
                : 'An authorized administrator reviews requests and activates access separately.'}
            </p>
          </div>
          <div className="rounded-3xl border border-white/15 bg-white/10 p-5 backdrop-blur-sm sm:p-6">
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-emerald-100">Plan &amp; pricing</p>
            <p className="mt-3 text-2xl font-black">{premiumActive ? 'Premium' : 'Core'}</p>
            <p className="mt-1 text-sm text-emerald-50/80">
              {pricingDisplay}
              {pricing.billing_period ? ` · ${pricing.billing_period}` : ''}
            </p>
            <div className="mt-4 border-t border-white/15 pt-4 text-xs leading-5 text-emerald-50/80">
              {pricing.checkout_enabled
                ? 'Razorpay Test Mode is configured. Settlement is verified by the backend; this does not collect real money.'
                : `${pricing.unavailable_reason || 'Payment integration is unavailable.'} Pricing is informational only; an authorized administrator activates Premium access separately.`}
            </div>
            {pricing.checkout_enabled && (
              <p className="mt-3 text-xs font-semibold text-emerald-100">
                Configured Test Mode amount: {configuredPrice}
              </p>
            )}
            <p className="mt-4 text-xs font-semibold text-white">
              Current account: {premiumActive ? 'Premium access active' : 'Core plan'}
            </p>
          </div>
        </div>
      </section>

      {error && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-800" role="alert">
          <span className="flex items-center gap-2"><AlertCircle size={18} />{error}</span>
          {retryRequest ? (
            <button type="button" onClick={onRequestAccess} className="font-semibold underline underline-offset-4">Retry access request</button>
          ) : onRetry && (
            <button type="button" onClick={onRetry} className="font-semibold underline underline-offset-4">Try again</button>
          )}
        </div>
      )}
      {requestMessage && (
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm leading-6 text-emerald-900" role="status">
          {requestMessage}
        </div>
      )}
      {paymentMessage && (
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm leading-6 text-emerald-900" role="status">
          {paymentMessage}
          {paymentOrderId && (
            <button
              type="button"
              onClick={onRefreshPaymentStatus}
              disabled={checkoutBusy}
              className="ml-3 font-semibold underline underline-offset-4 disabled:opacity-60"
            >
              {checkoutBusy ? 'Refreshing…' : 'Refresh payment status'}
            </button>
          )}
        </div>
      )}
      {paymentError && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-800" role="alert">
          <span className="flex items-center gap-2"><AlertCircle size={18} />{paymentError}</span>
          {paymentOrderId && (
            <button
              type="button"
              onClick={onRefreshPaymentStatus}
              disabled={checkoutBusy}
              className="font-semibold underline underline-offset-4 disabled:opacity-60"
            >
              Refresh payment status
            </button>
          )}
        </div>
      )}
      {plan?.access_request_pending && !requestMessage && (
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm leading-6 text-emerald-900" role="status">
          Your Premium access request is pending review.
        </div>
      )}

      <section className="space-y-4" aria-labelledby="premium-benefits-heading">
        <div>
          <p className="soft-label mb-2"><Sparkles size={13} />Built around your evidence</p>
          <h2 id="premium-benefits-heading" className="text-2xl font-extrabold text-slate-900">One platform. A more connected plan.</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            PlaceIQ’s resume analysis, roadmap, interviews, and Study Coach stay available in Core. Premium adds a consolidated analytics and report workspace using saved student records.
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {premiumFeatures.map(({ icon: Icon, title, text, area }) => (
            <article key={title} className="panel-card flex h-full flex-col gap-3 p-5">
              <div className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-50 text-brand-700"><Icon size={21} /></div>
              <div className="flex-1">
                <h3 className="font-bold text-slate-900">{title}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-600">{text}</p>
              </div>
              <span className={`w-fit rounded-full px-2.5 py-1 text-xs font-semibold ${area === 'Premium workspace' ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600'}`}>
                {area}
              </span>
            </article>
          ))}
        </div>
      </section>

      <section className="panel-card min-w-0 space-y-4" aria-labelledby="plan-comparison-heading">
        <div>
          <p className="soft-label mb-2"><Target size={13} />Transparent plan details</p>
          <h2 id="plan-comparison-heading" className="text-xl font-extrabold text-slate-900">Core and Premium</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[580px] border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-slate-500">
                <th scope="col" className="py-3 pr-4 font-semibold">Capability</th>
                <th scope="col" className="px-4 py-3 font-semibold">Core</th>
                <th scope="col" className="px-4 py-3 font-semibold">Premium</th>
              </tr>
            </thead>
            <tbody>
              {[
                ['Resume, VTU gap, roadmap, interviews, Study Coach', 'Included', 'Included'],
                ['Practice, assessments, and evidence-based mastery', 'Included', 'Included'],
                ['Historical readiness and assessment analytics', 'Individual tools', 'Consolidated view'],
                ['Personalized placement evidence report', 'Individual tools', 'Unified report'],
                ['Payment checkout', 'Not applicable', 'Not configured'],
              ].map(([feature, core, premium]) => (
                <tr key={feature} className="border-b border-slate-100 last:border-0">
                  <th scope="row" className="py-3 pr-4 font-medium text-slate-700">{feature}</th>
                  <td className="px-4 py-3 text-slate-600">{core}</td>
                  <td className="px-4 py-3 font-medium text-emerald-800">{premium}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs leading-5 text-slate-500">Existing learning and placement capabilities are not disabled to force an upgrade. Premium reports use only records belonging to the signed-in student.</p>
      </section>

      <section className="panel-card space-y-4 sm:space-y-5" aria-labelledby="report-preview-heading">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="soft-label mb-2"><BriefcaseBusiness size={13} />Your saved evidence</p>
            <h2 id="report-preview-heading" className="text-xl font-extrabold text-slate-900 sm:text-2xl">Placement report preview</h2>
          </div>
          <p className="max-w-xl text-sm leading-6 text-slate-600">
            {premiumActive
              ? 'A concise view of your saved readiness, learning, and interview evidence.'
              : 'This private preview uses your saved records and appears here when an administrator activates Premium access.'}
          </p>
        </div>
        {premiumActive ? (
          <>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <EvidenceValue label="Latest readiness" value={analytics.readiness_current?.total} suffix="/100" />
              <EvidenceValue
                label="Roadmap completion"
                value={roadmapProgress && roadmapProgress.total_tasks > 0
                  ? Math.round(roadmapProgress.completed_tasks / roadmapProgress.total_tasks * 100)
                  : null}
                suffix="%"
              />
              <EvidenceValue label="Assessment accuracy" value={accuracy?.accuracy_pct} suffix="%" />
              <EvidenceValue
                label="Resume evidence"
                value={report.resume ? `${report.resume.skills.length} skills` : null}
              />
            </div>
            <div className="grid gap-4 lg:grid-cols-3">
              <article className="min-w-0 rounded-2xl border border-slate-200 p-4">
                <h3 className="font-bold text-slate-900">Readiness history</h3>
                <ReadinessTrend history={analytics.readiness_history || []} />
              </article>
              <article className="min-w-0 rounded-2xl border border-slate-200 p-4">
                <h3 className="font-bold text-slate-900">Skill mastery evidence</h3>
                {mastery.length ? (
                  <ul className="mt-3 space-y-2">
                    {mastery.slice(0, 3).map((skill) => (
                      <li key={skill.skill_id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                        <span className="font-medium text-slate-700">{skill.skill_id}</span>
                        <span className="text-slate-500">
                          {skill.score_pct == null ? 'Insufficient evidence' : `${skill.score_pct}%`}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-2 text-sm text-slate-500">No submitted assessment evidence yet.</p>
                )}
              </article>
              <article className="min-w-0 rounded-2xl border border-slate-200 p-4">
                <h3 className="font-bold text-slate-900">Interview feedback</h3>
                {report.latest_interview ? (
                  <>
                    <p className="mt-2 text-sm text-slate-600">
                      {report.latest_interview.completed && report.latest_interview.overall_score != null
                        ? `Latest score: ${report.latest_interview.overall_score}/100`
                        : 'Interview feedback is still in progress.'}
                    </p>
                    {report.latest_interview.feedback?.[0]?.feedback && (
                      <p className="mt-2 line-clamp-3 text-sm leading-5 text-slate-500">
                        {report.latest_interview.feedback[0].feedback}
                      </p>
                    )}
                    {!report.latest_interview.feedback?.length && (
                      <p className="mt-2 text-sm text-slate-500">No submitted interview feedback yet.</p>
                    )}
                  </>
                ) : (
                  <p className="mt-2 text-sm text-slate-500">No saved interview evidence yet.</p>
                )}
              </article>
            </div>
            <p className="text-xs leading-5 text-slate-500">
              {report.skill_gap
                ? `VTU skill-gap report available${report.target_role ? ` for ${report.target_role}` : ''}.`
                : 'No saved VTU skill-gap report yet.'}
              {' '}All values come from your stored records; missing evidence is not estimated.
            </p>
          </>
        ) : (
          <div className="grid gap-3 sm:grid-cols-3">
            {['Readiness history', 'Roadmap progress', 'Assessment and interview evidence'].map((label) => (
              <div key={label} className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-4">
                <p className="text-sm font-semibold text-slate-700">{label}</p>
                <p className="mt-1 text-sm text-slate-500">Available in the private Premium report.</p>
              </div>
            ))}
          </div>
        )}
      </section>

      {premiumActive && (
        <>
          <section className="space-y-4" aria-labelledby="premium-analytics-heading">
            <div>
              <p className="soft-label mb-2"><Gauge size={13} />Measured from saved records</p>
              <h2 id="premium-analytics-heading" className="text-2xl font-extrabold text-slate-900">Your progress analytics</h2>
            </div>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <EvidenceValue label="Readiness score" value={analytics.readiness_current?.total} suffix="/100" />
              <EvidenceValue label="Roadmap completion" value={
                roadmapProgress && roadmapProgress.total_tasks > 0
                  ? Math.round(roadmapProgress.completed_tasks / roadmapProgress.total_tasks * 100)
                  : null
              } suffix="%" />
              <EvidenceValue label="Assessment accuracy" value={accuracy?.accuracy_pct} suffix="%" />
              <EvidenceValue label="Submitted assessments" value={accuracy?.assessments ?? null} />
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <article className="panel-card">
                <h3 className="font-bold text-slate-900">Readiness history</h3>
                <p className="mt-1 text-xs text-slate-500">Stored snapshots only; the existing readiness formula is unchanged.</p>
                <ReadinessTrend history={analytics.readiness_history || []} />
              </article>
              <article className="panel-card">
                <h3 className="font-bold text-slate-900">Assessment evidence</h3>
                {accuracy ? (
                  <p className="mt-2 text-sm leading-6 text-slate-600">
                    {accuracy.correct} correct answers from {accuracy.questions} submitted questions across {accuracy.assessments} assessments.
                    Mastery is shown only where the existing evidence threshold is met.
                  </p>
                ) : (
                  <p className="mt-2 text-sm leading-6 text-slate-500">No submitted assessment results yet. Complete an assessment to begin building measured learning evidence.</p>
                )}
                <Link to="/mastery" className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-brand-700 hover:text-brand-900">Review skill mastery <ArrowRight size={15} /></Link>
              </article>
              <article className="panel-card lg:col-span-2">
                <h3 className="font-bold text-slate-900">Demonstrated skill mastery</h3>
                <p className="mt-1 text-xs text-slate-500">Based on submitted assessment answers only; insufficient evidence is shown without a score.</p>
                {mastery.length ? (
                  <ul className="mt-3 grid gap-3 sm:grid-cols-2">
                    {mastery.map((skill) => (
                      <li key={skill.skill_id} className="rounded-xl border border-slate-200 p-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-semibold text-slate-800">{skill.skill_id}</span>
                          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-700">
                            {skill.status === 'demonstrated_proficiency'
                              ? 'Demonstrated proficiency'
                              : skill.status === 'developing'
                                ? 'Developing'
                                : 'Insufficient evidence'}
                          </span>
                        </div>
                        <p className="mt-2 text-sm text-slate-600">
                          {skill.score_pct === null || skill.score_pct === undefined
                            ? 'Not enough assessment evidence for a mastery score.'
                            : `${skill.score_pct}% demonstrated accuracy`}
                          {' · '}{skill.evidence_assessments} assessments, {skill.evidence_questions} questions
                        </p>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-2 text-sm text-slate-500">No submitted assessment evidence yet.</p>
                )}
              </article>
            </div>
          </section>

          <section className="panel-card space-y-4" aria-labelledby="placement-report-heading">
            <div>
              <p className="soft-label mb-2"><BriefcaseBusiness size={13} />Private to your account</p>
              <h2 id="placement-report-heading" className="text-2xl font-extrabold text-slate-900">Personalized placement report</h2>
              <p className="mt-1 text-sm text-slate-600">
                {report.target_role ? `Evidence for ${report.target_role}.` : 'Add a target role to personalize your placement evidence.'}
              </p>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <article className="rounded-2xl border border-slate-200 p-4">
                <h3 className="font-bold text-slate-900">Resume</h3>
                {report.resume ? (
                  <>
                    <p className="mt-2 text-sm text-slate-700">Latest ATS score: <strong>{report.resume.ats_score ?? 'Not recorded'}</strong></p>
                    <p className="mt-2 text-sm text-slate-600">{report.resume.skills.length} extracted skills · {report.resume.projects.length} saved projects</p>
                  </>
                ) : <p className="mt-2 text-sm text-slate-500">No resume record yet.</p>}
                <Link to="/resume" className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-brand-700">Open resume tools <ArrowRight size={14} /></Link>
              </article>
              <article className="rounded-2xl border border-slate-200 p-4">
                <h3 className="font-bold text-slate-900">VTU skill gap</h3>
                {report.skill_gap ? (
                  <>
                    <p className="mt-2 text-sm text-slate-700">Role match: <strong>{report.skill_gap.match_pct}%</strong></p>
                    <p className="mt-2 text-sm text-slate-600">{missingSkills.length} identified gap{missingSkills.length === 1 ? '' : 's'}</p>
                    {missingSkills.length > 0 && (
                      <ul className="mt-2 space-y-1">
                        {missingSkills.map((item, index) => (
                          <li key={`${item.skill}-${index}`} className="text-sm text-slate-600">
                            {item.skill}
                            {item.status ? ` · ${item.status}` : ''}
                            {item.weight ? ` · priority weight ${item.weight}/3` : ''}
                          </li>
                        ))}
                      </ul>
                    )}
                  </>
                ) : <p className="mt-2 text-sm text-slate-500">No saved skill-gap report yet.</p>}
                <Link to="/gap" className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-brand-700">Open skill-gap tools <ArrowRight size={14} /></Link>
              </article>
              <article className="rounded-2xl border border-slate-200 p-4">
                <h3 className="font-bold text-slate-900">Roadmap progress</h3>
                {roadmapProgress ? (
                  <p className="mt-2 text-sm text-slate-700">{roadmapProgress.completed_tasks} of {roadmapProgress.total_tasks} tasks complete across {roadmapProgress.weeks} weeks.</p>
                ) : <p className="mt-2 text-sm text-slate-500">No saved roadmap yet.</p>}
                <Link to="/roadmap" className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-brand-700">Open roadmap <ArrowRight size={14} /></Link>
              </article>
              <article className="rounded-2xl border border-slate-200 p-4">
                <h3 className="font-bold text-slate-900">Latest mock interview</h3>
                {report.latest_interview ? (
                  <>
                    <p className="mt-2 text-sm text-slate-700">Overall score: <strong>{report.latest_interview.completed ? `${report.latest_interview.overall_score}/100` : 'Not completed'}</strong></p>
                    <p className="mt-2 text-sm text-slate-600">{report.latest_interview.weak_skills.length ? `Review areas: ${report.latest_interview.weak_skills.join(', ')}` : 'No weak-skill flags recorded.'}</p>
                    {report.latest_interview.feedback?.length > 0 && (
                      <ul className="mt-3 space-y-3">
                        {report.latest_interview.feedback.map((item) => (
                          <li key={item.question_index} className="rounded-xl bg-slate-50 p-3">
                            <p className="text-sm font-semibold text-slate-800">
                              Question {item.question_index + 1}
                              {item.score_out_of_10 !== undefined ? ` · ${item.score_out_of_10}/10` : ''}
                              {item.is_correct === true ? ' · Correct' : item.is_correct === false ? ' · Review' : ''}
                            </p>
                            {item.feedback && <p className="mt-1 text-sm text-slate-600">{item.feedback}</p>}
                            {item.explanation && <p className="mt-1 text-sm text-slate-600"><strong>Explanation:</strong> {item.explanation}</p>}
                            {item.improvement_suggestions && <p className="mt-1 text-sm text-slate-600"><strong>Next improvement:</strong> {item.improvement_suggestions}</p>}
                          </li>
                        ))}
                      </ul>
                    )}
                  </>
                ) : <p className="mt-2 text-sm text-slate-500">No interview session yet.</p>}
                <Link to="/interview" className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-brand-700">Open interview practice <ArrowRight size={14} /></Link>
              </article>
            </div>
            <div className="rounded-2xl bg-brand-50 p-4">
              <h3 className="font-bold text-slate-900">Evidence-backed next steps</h3>
              {recommendations.length ? (
                <ul className="mt-3 space-y-3">
                  {recommendations.map((item, index) => (
                    <li key={`${item.skill_id || item.title}-${index}`} className="rounded-xl border border-brand-100 bg-white p-3">
                      <p className="text-sm font-semibold text-slate-800">{item.title || item.skill_id || 'Learning recommendation'}</p>
                      {item.reason && <p className="mt-1 text-sm leading-5 text-slate-600">{item.reason}</p>}
                      {item.evidence?.length > 0 && <p className="mt-1 text-xs text-slate-500">{item.evidence.join(' ')}</p>}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-sm text-slate-600">No next step is available from current saved assessment, roadmap, or skill-gap evidence.</p>
              )}
              <p className="mt-3 text-xs leading-5 text-slate-500">{analytics.recommendation_notice}</p>
            </div>
            <p className="border-t border-slate-100 pt-4 text-xs leading-5 text-slate-500">{overview?.notice}</p>
          </section>
        </>
      )}
    </motion.div>
  );
}

async function fetchPlanAndOverview() {
  const { data: plan } = await api.get('/premium/plan');
  let overview = null;
  if (plan.plan === 'premium' && plan.entitlement_status === 'active') {
    const { data } = await api.get('/premium/overview');
    overview = data;
  }
  return { plan, overview };
}

export default function Premium() {
  const [plan, setPlan] = useState(null);
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [requesting, setRequesting] = useState(false);
  const [requestMessage, setRequestMessage] = useState('');
  const [requestFailed, setRequestFailed] = useState(false);
  const [checkoutBusy, setCheckoutBusy] = useState(false);
  const [paymentOrderId, setPaymentOrderId] = useState(null);
  const [paymentMessage, setPaymentMessage] = useState('');
  const [paymentError, setPaymentError] = useState('');
  const [error, setError] = useState('');
  const requestLock = useRef(false);
  const checkoutLock = useRef(false);

  const loadPlan = useCallback(async () => {
    try {
      const result = await fetchPlanAndOverview();
      setPlan(result.plan);
      setOverview(result.overview);
      setError('');
    } catch (err) {
      setError(err.response?.data?.detail || 'Unable to load Premium plan details.');
    } finally {
      setLoading(false);
    }
  }, []);

  const retryPlan = useCallback(() => {
    setLoading(true);
    setError('');
    loadPlan();
  }, [loadPlan]);

  useEffect(() => {
    let active = true;
    fetchPlanAndOverview()
      .then((result) => {
        if (!active) return;
        setPlan(result.plan);
        setOverview(result.overview);
        setError('');
      })
      .catch((err) => {
        if (active) setError(err.response?.data?.detail || 'Unable to load Premium plan details.');
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, []);

  const requestAccess = useCallback(() => submitPremiumAccessRequest({
    postRequest: () => api.post('/premium/access-request'),
    currentPlan: plan,
    requestLock,
    setRequesting,
    setError,
    setRequestMessage,
    setPlan,
    setRequestFailed,
  }), [plan]);

  const refreshPaymentStatus = useCallback(async () => {
    if (!paymentOrderId) return;
    setCheckoutBusy(true);
    setPaymentError('');
    try {
      const { data } = await api.get(`/premium/payment/orders/${paymentOrderId}`);
      if (data.status === 'paid' && data.entitlement_active) {
        const result = await fetchPlanAndOverview();
        setPlan(result.plan);
        setOverview(result.overview);
        setPaymentMessage('Payment confirmed by PlaceIQ. Premium access is active.');
        setPaymentOrderId(null);
      } else {
        setPaymentMessage('Payment verification is still pending. Refresh status to check again.');
      }
    } catch (err) {
      setPaymentError(err.response?.data?.detail || 'Unable to refresh payment status. Please retry.');
    } finally {
      setCheckoutBusy(false);
    }
  }, [paymentOrderId]);

  const startCheckout = useCallback(async () => {
    if (!plan?.pricing?.checkout_enabled || !reservePremiumCheckout(checkoutLock)) return;
    setCheckoutBusy(true);
    setPaymentError('');
    setPaymentMessage('');
    try {
      const { Razorpay, order } = await preparePremiumCheckout({
        loadCheckout: () => loadRazorpayCheckout(),
        createOrder: async () => {
          const { data } = await api.post('/premium/payment/orders');
          return data;
        },
      });
      let paymentHandling = false;
      const handleSuccess = async (response) => {
        if (paymentHandling) return;
        paymentHandling = true;
        setPaymentOrderId(order.payment_order_id);
        setPaymentMessage('Payment received by Checkout. PlaceIQ is verifying settlement with Razorpay.');
        let backendConfirmed = false;
        try {
          const result = await verifyPremiumCheckout({
            response,
            verifyPayment: (payload) => api.post('/premium/payment/verify', payload),
          });
          if (result.status === 'confirmed') {
            backendConfirmed = true;
            const result = await fetchPlanAndOverview();
            setPlan(result.plan);
            setOverview(result.overview);
            setPaymentMessage('Payment confirmed by PlaceIQ. Premium access is active.');
            setPaymentOrderId(null);
          } else {
            setPaymentMessage('Payment verification is pending. Refresh status to check settlement.');
          }
        } catch (err) {
          if (backendConfirmed) {
            setPaymentMessage('Payment is confirmed. Account status refresh is still pending.');
            setPaymentError(err.response?.data?.detail || 'Unable to refresh the Premium account state. Refresh payment status to retry.');
          } else if (err.response) {
            setPaymentMessage('');
            setPaymentError(err.response.data?.detail || 'Payment verification failed. You can retry checkout.');
          } else {
            setPaymentMessage('Payment verification is pending. Refresh status to check settlement.');
            setPaymentError('Unable to reach PlaceIQ to confirm payment. Please refresh status before retrying.');
          }
        } finally {
          checkoutLock.current = false;
          setCheckoutBusy(false);
        }
      };
      const options = createPremiumCheckoutOptions({
        order,
        onSuccess: handleSuccess,
        onDismiss: () => {
          if (paymentHandling) return;
          setPaymentMessage('Checkout was closed. No Premium access was granted.');
          checkoutLock.current = false;
          setCheckoutBusy(false);
        },
      });
      const checkout = new Razorpay(options);
      checkout.on('payment.failed', () => {
        if (paymentHandling) return;
        setPaymentError('Razorpay did not complete the payment. You can retry checkout.');
        checkoutLock.current = false;
        setCheckoutBusy(false);
      });
      checkout.open();
    } catch (err) {
      setPaymentError(err.response?.data?.detail || err.message || 'Unable to start Razorpay Test Mode checkout. Please retry.');
      checkoutLock.current = false;
      setCheckoutBusy(false);
    }
  }, [plan]);

  if (loading && !plan) {
    return (
      <div className="panel-card flex min-h-64 flex-col items-center justify-center gap-3 text-slate-500" role="status">
        <Loader className="animate-spin text-brand-600" size={28} />
        <p className="font-medium">Loading your plan and access status…</p>
      </div>
    );
  }
  if (error && !plan) {
    return (
      <div className="panel-card space-y-4 text-center">
        <AlertCircle className="mx-auto text-red-600" size={28} />
        <p className="text-sm text-red-800" role="alert">{error}</p>
        <button type="button" onClick={retryPlan} className="btn-modern">Retry</button>
      </div>
    );
  }
  return (
    <PremiumExperience
      plan={plan}
      overview={overview}
      onRequestAccess={requestAccess}
      requesting={requesting}
      requestMessage={requestMessage}
      error={error}
      onRetry={retryPlan}
      retryRequest={requestFailed}
      checkoutBusy={checkoutBusy}
      onStartCheckout={startCheckout}
      paymentOrderId={paymentOrderId}
      paymentMessage={paymentMessage}
      paymentError={paymentError}
      onRefreshPaymentStatus={refreshPaymentStatus}
    />
  );
}
