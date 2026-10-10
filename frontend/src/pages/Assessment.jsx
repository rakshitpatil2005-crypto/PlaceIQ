import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, CheckCircle2, ClipboardCheck, Loader } from 'lucide-react';
import api from '../api';
import { validateAssessmentAnswers } from '../utils/assessment';

export default function Assessment() {
  const { assessmentId } = useParams();
  const navigate = useNavigate();
  const [assessment, setAssessment] = useState(null);
  const [answers, setAnswers] = useState({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [refreshingRoadmap, setRefreshingRoadmap] = useState(false);
  const [roadmapMessage, setRoadmapMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    api.get(`/learning/assessment/${assessmentId}`)
      .then(({ data }) => {
        if (!active) return;
        setAssessment(data);
        if (data.submitted) setAnswers(data.submitted_answers || {});
      })
      .catch((err) => {
        if (active) setError(err.response?.data?.detail || 'Unable to load this assessment.');
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [assessmentId]);

  const submitAssessment = async () => {
    const validationError = validateAssessmentAnswers(assessment?.questions, answers);
    if (validationError) {
      setError(validationError);
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      const { data } = await api.post(`/learning/assessment/${assessmentId}/submit`, {
        answers: assessment.questions.map((question) => ({
          question_id: question.question_id,
          answer: answers[question.question_id],
        })),
      });
      setAssessment(data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Unable to submit your assessment. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  const refreshRoadmapPriorities = async () => {
    if (refreshingRoadmap) return;
    setRefreshingRoadmap(true);
    setError('');
    setRoadmapMessage('');
    try {
      const { data } = await api.post('/roadmap/adapt');
      setRoadmapMessage(data.message || 'Roadmap priorities refreshed from your latest learning evidence.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Unable to refresh roadmap priorities.');
    } finally {
      setRefreshingRoadmap(false);
    }
  };

  if (loading) {
    return (
      <div className="panel-card flex min-h-64 flex-col items-center justify-center gap-3 text-slate-500" role="status">
        <Loader className="animate-spin text-brand-600" size={28} />
        <p className="font-medium">Loading your assessment...</p>
      </div>
    );
  }

  if (error && !assessment) {
    return (
      <div className="panel-card space-y-4 text-center">
        <h1 className="text-xl font-bold text-slate-900">Assessment unavailable</h1>
        <p className="text-sm text-slate-600" role="alert">{error}</p>
        <button type="button" className="btn-modern" onClick={() => navigate('/roadmap')}>Return to roadmap</button>
      </div>
    );
  }

  if (!assessment || !assessment.questions?.length) {
    return (
      <div className="panel-card space-y-4 text-center">
        <h1 className="text-xl font-bold text-slate-900">No assessment questions are available</h1>
        <button type="button" className="btn-modern" onClick={() => navigate('/roadmap')}>Return to roadmap</button>
      </div>
    );
  }

  const strengths = assessment.result?.concepts.filter((item) => item.status === 'strength') || [];
  const reviewConcepts = assessment.result?.concepts.filter((item) => item.status === 'review') || [];

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <header className="page-header">
        <div>
          <div className="soft-label mb-3"><ClipboardCheck size={14} /> Lesson assessment</div>
          <h1 className="page-title">{assessment.skill_id}</h1>
          <p className="page-subtitle mt-2">Check your understanding of this lesson. Results describe only this assessment attempt; they are not a skill-mastery or placement-readiness score.</p>
        </div>
        <button
          type="button"
          onClick={() => navigate(`/learn?skill=${encodeURIComponent(assessment.skill_id)}&lesson=${encodeURIComponent(assessment.lesson_id)}`)}
          className="inline-flex items-center gap-2 text-sm font-semibold text-brand-700 hover:text-brand-900"
        >
          <ArrowLeft size={16} /> Back to lesson
        </button>
      </header>

      {assessment.content_source === 'fallback' && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900" role="status">
          Generated questions are unavailable. This structured lesson assessment uses the available lesson content.
        </div>
      )}

      {assessment.submitted && (
        <>
          <section className="panel-card text-center" aria-label="Assessment result">
            <CheckCircle2 className="mx-auto text-brand-600" size={32} />
            <p className="mt-3 text-xs font-bold uppercase tracking-[0.14em] text-slate-500">Assessment result</p>
            <p className="mt-1 text-4xl font-extrabold text-slate-900">{assessment.result.correct} <span className="text-2xl text-slate-500">/ {assessment.result.total}</span></p>
            <p className="mt-1 text-lg font-semibold text-brand-800">{assessment.result.score_pct}% on this attempt</p>
            <p className="mt-3 text-sm text-slate-600">{assessment.result.notice}</p>
            <button
              type="button"
              onClick={() => navigate('/mastery')}
              className="mt-4 inline-flex items-center gap-2 rounded-xl border border-brand-200 bg-brand-50 px-4 py-2.5 text-sm font-semibold text-brand-800 hover:bg-brand-100"
            >
              View skill mastery history
            </button>
            <button
              type="button"
              onClick={refreshRoadmapPriorities}
              disabled={refreshingRoadmap}
              className="ml-2 mt-4 inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-wait disabled:opacity-60"
            >
              {refreshingRoadmap ? 'Refreshing roadmap…' : 'Refresh roadmap priorities'}
            </button>
            {roadmapMessage && (
              <p className="mt-3 text-sm text-emerald-800" role="status">{roadmapMessage}</p>
            )}
            {error && <p className="mt-3 text-sm text-red-700" role="alert">{error}</p>}
            <div className="mt-5 grid gap-4 text-left sm:grid-cols-2">
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
                <h2 className="font-bold text-emerald-900">Strengths in this attempt</h2>
                {strengths.length ? (
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-emerald-900">
                    {strengths.map((item) => <li key={item.concept}>{item.concept}</li>)}
                  </ul>
                ) : <p className="mt-2 text-sm text-emerald-900">No concepts were answered correctly on every question this time.</p>}
              </div>
              <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
                <h2 className="font-bold text-amber-900">Concepts to review</h2>
                {reviewConcepts.length ? (
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-amber-900">
                    {reviewConcepts.map((item) => <li key={item.concept}>{item.concept}</li>)}
                  </ul>
                ) : <p className="mt-2 text-sm text-amber-900">No concepts were marked for review in this attempt.</p>}
              </div>
            </div>
          </section>

          <section className="space-y-4" aria-label="Answer review">
            <h2 className="section-title">Answer review</h2>
            {assessment.result.questions.map((item, index) => (
              <article key={item.question_id} className={`panel-card space-y-3 border-l-4 ${item.is_correct ? 'border-l-emerald-500' : 'border-l-amber-500'}`}>
                <p className="text-xs font-bold uppercase tracking-wide text-slate-500">Question {index + 1} · {item.concept}</p>
                <h3 className="font-semibold leading-7 text-slate-900">{item.prompt}</h3>
                {item.code && <pre className="overflow-x-auto rounded-xl bg-slate-950 p-4 text-sm leading-6 text-slate-100"><code>{item.code}</code></pre>}
                <p className="text-sm text-slate-700"><span className="font-semibold">Your answer:</span> {item.answer}</p>
                <p className="text-sm text-slate-700"><span className="font-semibold">Correct answer:</span> {item.correct_answer}</p>
                <p className="text-sm leading-6 text-slate-600">{item.explanation}</p>
              </article>
            ))}
          </section>
        </>
      )}

      {!assessment.submitted && (
        <section className="panel-card space-y-6" aria-label="Assessment questions">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-4">
            <div>
              <h2 className="text-xl font-bold text-slate-900">Assessment questions</h2>
              <p className="mt-1 text-sm text-slate-600">{assessment.questions.length} questions · All answers are required before submission</p>
            </div>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">{assessment.skill_id}</span>
          </div>
          {assessment.questions.map((question, index) => (
            <article key={question.question_id} className="space-y-4 border-b border-slate-100 pb-6 last:border-0 last:pb-0">
              <div>
                <p className="text-xs font-bold uppercase tracking-wide text-slate-500">Question {index + 1} · {question.concept}</p>
                <h3 className="mt-2 font-semibold leading-7 text-slate-900">{question.prompt}</h3>
              </div>
              {question.code && <pre className="overflow-x-auto rounded-xl bg-slate-950 p-4 text-sm leading-6 text-slate-100"><code>{question.code}</code></pre>}
              {question.type === 'mcq' ? (
                <fieldset className="space-y-2">
                  <legend className="sr-only">Choose an answer for question {index + 1}</legend>
                  {question.options.map((option) => (
                    <label key={option.id} className="flex cursor-pointer items-start gap-3 rounded-xl border border-slate-200 p-3 text-sm text-slate-700 hover:border-brand-300">
                      <input
                        type="radio"
                        name={`answer-${question.question_id}`}
                        value={option.id}
                        checked={answers[question.question_id] === option.id}
                        onChange={(event) => setAnswers((current) => ({ ...current, [question.question_id]: event.target.value }))}
                        className="mt-0.5 accent-brand-600"
                      />
                      <span>{option.text}</span>
                    </label>
                  ))}
                </fieldset>
              ) : (
                <label className="block space-y-2">
                  <span className="text-sm font-semibold text-slate-700">Your expected output</span>
                  <textarea
                    rows={2}
                    maxLength={6000}
                    value={answers[question.question_id] || ''}
                    onChange={(event) => setAnswers((current) => ({ ...current, [question.question_id]: event.target.value }))}
                    className="w-full rounded-xl border border-slate-200 p-3 font-mono text-sm leading-6 text-slate-800 outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
                  />
                </label>
              )}
            </article>
          ))}
          {error && <p className="rounded-xl bg-red-50 p-3 text-sm text-red-700" role="alert">{error}</p>}
          <button type="button" onClick={submitAssessment} disabled={submitting} className="btn-modern">
            {submitting && <Loader className="animate-spin" size={16} />}
            {submitting ? 'Submitting assessment...' : 'Submit assessment'}
          </button>
        </section>
      )}
    </div>
  );
}
