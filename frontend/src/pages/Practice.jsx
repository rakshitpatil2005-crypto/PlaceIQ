import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, ArrowRight, CheckCircle2, Circle, Loader, RotateCcw } from 'lucide-react';
import api from '../api';
import { validatePracticeAnswer } from '../utils/practice';

export default function Practice() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const [practice, setPractice] = useState(null);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [answers, setAnswers] = useState({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    api.get(`/learning/practice/${sessionId}`)
      .then(({ data }) => {
        if (!active) return;
        setPractice(data);
        setAnswers(Object.fromEntries(
          Object.entries(data.attempts || {}).map(([questionId, attempt]) => [questionId, attempt.answer]),
        ));
      })
      .catch((err) => {
        if (active) setError(err.response?.data?.detail || 'Unable to load this practice session.');
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [sessionId]);

  const questions = practice?.questions || [];
  const question = questions[questionIndex];
  const attempt = question ? practice?.attempts?.[question.question_id] : null;
  const answeredCount = useMemo(() => Object.keys(practice?.attempts || {}).length, [practice]);
  const returnToLesson = () => {
    if (practice) {
      navigate(`/learn?skill=${encodeURIComponent(practice.skill_id)}&lesson=${encodeURIComponent(practice.lesson_id)}`);
    } else {
      navigate(-1);
    }
  };

  const submitAnswer = async () => {
    if (!question || submitting) return;
    const validationError = validatePracticeAnswer(question, answers[question.question_id] || '');
    if (validationError) {
      setError(validationError);
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      const { data } = await api.post(`/learning/practice/${sessionId}/answers`, {
        question_id: question.question_id,
        answer: answers[question.question_id],
      });
      setPractice((current) => ({
        ...current,
        attempts: { ...current.attempts, [question.question_id]: data },
      }));
    } catch (err) {
      setError(err.response?.data?.detail || 'Unable to save your answer. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="panel-card flex min-h-64 flex-col items-center justify-center gap-3 text-slate-500" role="status">
        <Loader className="animate-spin text-brand-600" size={28} />
        <p className="font-medium">Loading your practice...</p>
      </div>
    );
  }

  if (error && !practice) {
    return (
      <div className="panel-card space-y-4 text-center">
        <h1 className="text-xl font-bold text-slate-900">Practice unavailable</h1>
        <p className="text-sm text-slate-600" role="alert">{error}</p>
        <button type="button" className="btn-modern" onClick={returnToLesson}>Return to lesson</button>
      </div>
    );
  }

  if (!practice || questions.length === 0) {
    return (
      <div className="panel-card space-y-4 text-center">
        <h1 className="text-xl font-bold text-slate-900">No practice questions are available</h1>
        <button type="button" className="btn-modern" onClick={returnToLesson}>Return to lesson</button>
      </div>
    );
  }

  const allAnswered = answeredCount === questions.length;

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <header className="page-header">
        <div>
          <div className="soft-label mb-3">Lesson practice</div>
          <h1 className="page-title">{practice.skill_id}</h1>
          <p className="page-subtitle mt-2">Apply the ideas from this lesson. Practice answers are saved separately from lesson completion and do not represent skill mastery.</p>
        </div>
        <button type="button" onClick={returnToLesson} className="inline-flex items-center gap-2 text-sm font-semibold text-brand-700 hover:text-brand-900">
          <ArrowLeft size={16} /> Back to lesson
        </button>
      </header>

      {practice.content_source === 'fallback' && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900" role="status">
          Generated questions are unavailable. You can continue with the structured practice set.
        </div>
      )}

      <section className="panel-card space-y-5" aria-label="Practice questions">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-500">Question {questionIndex + 1} of {questions.length}</p>
            <p className="mt-1 text-sm font-semibold text-slate-600">{answeredCount} of {questions.length} questions answered</p>
          </div>
          <nav className="flex gap-2 overflow-x-auto" aria-label="Question navigation">
            {questions.map((item, index) => (
              <button
                key={item.question_id}
                type="button"
                onClick={() => { setQuestionIndex(index); setError(''); }}
                aria-label={`Question ${index + 1}${practice.attempts?.[item.question_id] ? ', answered' : ''}`}
                aria-current={index === questionIndex ? 'step' : undefined}
                className={`inline-flex h-10 w-10 items-center justify-center rounded-xl border text-sm font-semibold ${
                  index === questionIndex ? 'border-brand-300 bg-brand-50 text-brand-800' : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                }`}
              >
                {practice.attempts?.[item.question_id] ? <CheckCircle2 size={16} /> : <Circle size={16} />}
                <span className="sr-only">Question {index + 1}</span>
              </button>
            ))}
          </nav>
        </div>

        <article className="space-y-5 border-t border-slate-100 pt-5">
          <div>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-slate-600">{question.type.replace('_', ' ')}</span>
            <h2 className="mt-4 text-xl font-bold leading-8 text-slate-900">{question.prompt}</h2>
          </div>
          {question.code && (
            <pre className="overflow-x-auto rounded-xl bg-slate-950 p-4 text-sm leading-6 text-slate-100"><code>{question.code}</code></pre>
          )}
          {question.starter_code && (
            <pre className="overflow-x-auto rounded-xl bg-slate-950 p-4 text-sm leading-6 text-slate-100"><code>{question.starter_code}</code></pre>
          )}

          {question.type === 'mcq' ? (
            <fieldset className="space-y-3">
              <legend className="sr-only">Select an answer</legend>
              {question.options.map((option) => (
                <label key={option.id} className="flex cursor-pointer items-start gap-3 rounded-xl border border-slate-200 p-4 text-sm text-slate-700 hover:border-brand-300">
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
              <span className="text-sm font-semibold text-slate-700">{question.type === 'code_output' ? 'Your expected output' : 'Your response'}</span>
              <textarea
                rows={question.type === 'code_output' ? 2 : 7}
                maxLength={6000}
                value={answers[question.question_id] || ''}
                onChange={(event) => setAnswers((current) => ({ ...current, [question.question_id]: event.target.value }))}
                placeholder={question.type === 'code_output' ? 'Enter the output...' : 'Explain your reasoning or write your solution...'}
                className="w-full rounded-xl border border-slate-200 p-3 text-sm leading-6 text-slate-800 outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
              />
            </label>
          )}
        </article>

        {attempt && (
          <div className={`rounded-xl border p-4 ${attempt.is_correct ? 'border-emerald-200 bg-emerald-50' : 'border-amber-200 bg-amber-50'}`} role="status">
            <p className={`font-semibold ${attempt.is_correct ? 'text-emerald-900' : 'text-amber-900'}`}>
              {attempt.is_correct ? 'Nice work' : 'Review and try again'}
            </p>
            <p className="mt-1 text-sm text-slate-700">{attempt.feedback}</p>
            <p className="mt-2 text-sm leading-6 text-slate-700">{attempt.explanation}</p>
          </div>
        )}

        {error && <p className="rounded-xl bg-red-50 p-3 text-sm text-red-700" role="alert">{error}</p>}

        <div className="flex flex-col-reverse gap-3 border-t border-slate-100 pt-4 sm:flex-row sm:items-center sm:justify-between">
          <button
            type="button"
            onClick={() => { setQuestionIndex((index) => Math.max(0, index - 1)); setError(''); }}
            disabled={questionIndex === 0}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <ArrowLeft size={16} /> Previous question
          </button>
          <button type="button" onClick={submitAnswer} disabled={submitting} className="btn-modern">
            {submitting ? <Loader className="animate-spin" size={16} /> : attempt ? <RotateCcw size={16} /> : <CheckCircle2 size={16} />}
            {submitting ? 'Saving answer...' : attempt ? 'Submit another attempt' : 'Check answer'}
          </button>
          <button
            type="button"
            onClick={() => { setQuestionIndex((index) => Math.min(questions.length - 1, index + 1)); setError(''); }}
            disabled={questionIndex === questions.length - 1}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Next question <ArrowRight size={16} />
          </button>
        </div>
      </section>

      {allAnswered && (
        <section className="rounded-2xl border border-emerald-200 bg-emerald-50 p-5 text-center">
          <CheckCircle2 className="mx-auto text-emerald-600" size={30} />
          <h2 className="mt-2 text-lg font-bold text-emerald-900">Practice set completed</h2>
          <p className="mt-1 text-sm text-emerald-800">Your responses are saved. You can revisit any question to review or submit another attempt.</p>
        </section>
      )}
    </div>
  );
}
