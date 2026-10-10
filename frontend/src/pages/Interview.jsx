import { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import {
  AlertCircle, CheckCircle, HelpCircle, Loader, MessageSquare, Send,
  ThumbsUp, TrendingUp,
} from 'lucide-react';
import api from '../api';

const TECHNICAL_COUNT = 5;
const toTwoDecimals = (value) => Math.round(value * 100) / 100;

function questionIndexMap(records = []) {
  return Object.fromEntries(
    records
      .filter((record) => Number.isInteger(record.question_index))
      .map((record) => [record.question_index, record]),
  );
}

export default function Interview() {
  const [questions, setQuestions] = useState([]);
  const [targetRole, setTargetRole] = useState('');
  const [currentQIndex, setCurrentQIndex] = useState(0);
  const [answers, setAnswers] = useState({});
  const [evaluations, setEvaluations] = useState({});
  const [difficulty, setDifficulty] = useState('Intermediate');
  const [focusArea, setFocusArea] = useState('');
  const [generationNotice, setGenerationNotice] = useState('');
  const [restoredOverallScore, setRestoredOverallScore] = useState(null);
  const [loadingQuestions, setLoadingQuestions] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [error, setError] = useState('');

  const currentQuestion = questions[currentQIndex];
  const currentAnswer = answers[currentQIndex] || '';
  const currentEvaluation = evaluations[currentQIndex];
  const completed = questions.length > 0 && questions.every((_, index) => evaluations[index]);
  const technicalScore = useMemo(() => {
    const evaluated = Object.values(evaluations).filter((item) => item.question_type === 'technical_mcq');
    return evaluated.length
      ? toTwoDecimals((evaluated.reduce((sum, item) => sum + item.score_out_of_10, 0) / TECHNICAL_COUNT) * 10)
      : 0;
  }, [evaluations]);
  const hrScore = useMemo(() => {
    const evaluated = Object.values(evaluations).filter((item) => item.question_type === 'hr');
    return evaluated.length
      ? toTwoDecimals((evaluated.reduce((sum, item) => sum + item.score_out_of_10, 0) / 3) * 10)
      : 0;
  }, [evaluations]);
  const completedEvaluation = Object.values(evaluations).find((item) => item.completed);
  const overallScore = completed
    ? (completedEvaluation?.overall_score ?? restoredOverallScore ?? toTwoDecimals((technicalScore * 0.5) + (hrScore * 0.5)))
    : 0;

  useEffect(() => {
    let active = true;
    api.get('/interview/session')
      .then(({ data }) => {
        if (!active || !data?.questions?.length) return;
        const scoreMap = questionIndexMap(data.scores);
        setQuestions(data.questions);
        setTargetRole(data.target_role || 'Software Engineer');
        setAnswers(Object.fromEntries(
          (data.answers || [])
            .filter((item) => Number.isInteger(item.question_index))
            .map((item) => [item.question_index, item.answer]),
        ));
        setEvaluations(scoreMap);
        setRestoredOverallScore(data.overall_score ?? null);
        const next = data.questions.findIndex((_, index) => !scoreMap[index]);
        setCurrentQIndex(next < 0 ? data.questions.length : next);
      })
      .catch(() => {
        if (active) setError('Could not restore the previous interview session.');
      });
    return () => { active = false; };
  }, []);

  const generateQuestions = async () => {
    setLoadingQuestions(true);
    setError('');
    try {
      const { data } = await api.get('/interview/generate', {
        params: { difficulty, focus_area: focusArea },
      });
      setQuestions(data.questions || []);
      setTargetRole(data.target_role || 'Software Engineer');
      setAnswers({});
      setEvaluations({});
      setRestoredOverallScore(null);
      setCurrentQIndex(0);
      setGenerationNotice(data.content_source === 'fallback'
        ? 'AI question generation was unavailable. This session uses the built-in technical question fallback.'
        : '');
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to generate questions.');
    } finally {
      setLoadingQuestions(false);
    }
  };

  const submitAnswer = async () => {
    if (!currentQuestion || currentEvaluation || evaluating) return;
    if (currentQuestion.type === 'technical_mcq' && !currentAnswer) return;
    setEvaluating(true);
    setError('');
    try {
      const { data } = await api.post('/interview/evaluate', {
        question: currentQuestion.question,
        answer: currentAnswer,
        target_role: targetRole,
        question_index: currentQIndex,
      });
      setEvaluations((previous) => ({ ...previous, [currentQIndex]: data }));
      if (data.completed) setRestoredOverallScore(data.overall_score);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to evaluate answer.');
    } finally {
      setEvaluating(false);
    }
  };

  const updateAnswer = (value) => {
    setAnswers((previous) => ({ ...previous, [currentQIndex]: value }));
  };

  const showEvaluation = (evaluation) => {
    if (!evaluation) return null;
    if (evaluation.question_type === 'technical_mcq') {
      return (
        <section className={`rounded-xl border p-5 space-y-2 ${evaluation.is_correct ? 'border-green-200 bg-green-50' : 'border-amber-200 bg-amber-50'}`}>
          <h4 className="font-bold flex items-center gap-2">
            <CheckCircle size={18} /> {evaluation.is_correct ? 'Correct answer' : 'Not quite'} · {evaluation.score_out_of_10}/10
          </h4>
          <p className="text-sm text-gray-700">{evaluation.explanation}</p>
        </section>
      );
    }
    return (
      <section className="space-y-4 rounded-xl border border-gray-200 bg-gray-50 p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h4 className="font-bold text-gray-900">HR answer feedback</h4>
          <span className="rounded-full bg-brand-50 px-3 py-1 text-sm font-bold text-brand-700">Score: {evaluation.score_out_of_10}/10</span>
        </div>
        {evaluation.evaluation_source === 'fallback' && (
          <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800">AI evaluation was unavailable. This is limited, automated fallback feedback.</p>
        )}
        <div className="rounded-lg border border-green-100 bg-green-50/60 p-4">
          <p className="mb-1 flex items-center gap-1.5 text-xs font-bold uppercase text-green-800"><ThumbsUp size={14} /> Strengths</p>
          <p className="text-sm text-gray-700">{evaluation.strengths}</p>
        </div>
        <div className="rounded-lg border border-amber-100 bg-amber-50/60 p-4">
          <p className="mb-1 flex items-center gap-1.5 text-xs font-bold uppercase text-amber-800"><TrendingUp size={14} /> Missing points and improvements</p>
          <p className="text-sm text-gray-700">{evaluation.missing_points}</p>
          <p className="mt-2 text-sm text-gray-700">{evaluation.improvement_suggestions || evaluation.improvements}</p>
        </div>
        {evaluation.feedback && <p className="text-sm leading-relaxed text-gray-700">{evaluation.feedback}</p>}
        {evaluation.ideal_answer && (
          <div className="rounded-lg border border-blue-100 bg-blue-50/50 p-4">
            <p className="mb-1 flex items-center gap-1.5 text-xs font-bold uppercase text-blue-800"><HelpCircle size={14} /> Model answer guidance</p>
            <p className="text-sm leading-relaxed text-gray-700">{evaluation.ideal_answer}</p>
          </div>
        )}
      </section>
    );
  };

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="mx-auto max-w-4xl space-y-6">
      <div className="flex flex-col items-center justify-between gap-4 rounded-2xl border border-gray-100 bg-white p-6 shadow-sm md:flex-row">
        <div>
          <h2 className="flex items-center gap-2 text-xl font-bold text-gray-900">
            <MessageSquare className="text-brand-500" /> AI Mock Interview
          </h2>
          <p className="text-sm text-gray-500">Five scored technical questions and three written HR questions, personalized to your profile.</p>
        </div>
        <div className="flex w-full flex-col gap-2 md:w-auto md:flex-row">
          <select aria-label="Interview difficulty" value={difficulty} onChange={(event) => setDifficulty(event.target.value)} className="input-modern">
            <option>Beginner</option><option>Intermediate</option><option>Advanced</option>
          </select>
          <input aria-label="Interview focus area" value={focusArea} onChange={(event) => setFocusArea(event.target.value)} placeholder="Focus area (optional)" className="input-modern" maxLength={120} />
          <button onClick={generateQuestions} disabled={loadingQuestions} className="btn-modern flex min-w-[160px] items-center justify-center gap-2">
            {loadingQuestions ? <Loader className="animate-spin" size={20} /> : 'Start New Session'}
          </button>
        </div>
      </div>

      {error && <div role="alert" className="flex items-center gap-2 rounded-xl border border-red-100 bg-red-50 p-4 text-red-600"><AlertCircle size={20} /> {error}</div>}
      {generationNotice && <div role="status" className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">{generationNotice}</div>}

      {currentQuestion && (
        <div className="space-y-6 rounded-2xl border border-gray-100 bg-white p-5 shadow-sm sm:p-8">
          <div className="space-y-3 border-b border-gray-100 pb-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-bold uppercase tracking-wider text-brand-600">Question {currentQIndex + 1} of {questions.length}</span>
                <span className="rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-semibold text-gray-600">
                  {currentQuestion.type === 'technical_mcq' ? 'Technical MCQ' : 'HR / Written'}
                </span>
              </div>
              <span className="text-sm font-medium text-gray-400">Role: {targetRole}</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-gray-100" aria-label="Interview progress">
              <div className="h-full rounded-full bg-brand-500 transition-all" style={{ width: `${((currentQIndex + 1) / questions.length) * 100}%` }} />
            </div>
          </div>

          <div>
            {currentQuestion.skill && <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">Focus: {currentQuestion.skill}</p>}
            <h3 className="text-xl font-medium leading-snug text-gray-900">{currentQuestion.question}</h3>
            {currentQuestion.code && <pre className="mt-4 overflow-x-auto rounded-lg bg-gray-900 p-4 text-sm text-gray-100">{currentQuestion.code}</pre>}
          </div>

          {!currentEvaluation && currentQuestion.type === 'technical_mcq' && (
            <fieldset className="space-y-3" disabled={evaluating}>
              <legend className="sr-only">Select one answer</legend>
              {currentQuestion.options?.map((option) => (
                <label key={option.id} className={`flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition ${currentAnswer === option.id ? 'border-brand-500 bg-brand-50' : 'border-gray-200 hover:border-brand-300'}`}>
                  <input type="radio" name={`interview-question-${currentQIndex}`} value={option.id} checked={currentAnswer === option.id} onChange={() => updateAnswer(option.id)} className="mt-1 accent-brand-600" />
                  <span className="text-sm text-gray-800">{option.text}</span>
                </label>
              ))}
            </fieldset>
          )}

          {!currentEvaluation && currentQuestion.type === 'hr' && (
            <textarea
              className="input-modern min-h-[150px] resize-y"
              placeholder="Share a concise, honest response. Use a real academic, project, or personal example where relevant."
              value={currentAnswer}
              onChange={(event) => updateAnswer(event.target.value)}
              disabled={evaluating}
            />
          )}

          {showEvaluation(currentEvaluation)}

          {!currentEvaluation && (
            <button onClick={submitAnswer} disabled={evaluating || (currentQuestion.type === 'technical_mcq' && !currentAnswer)} className="btn-modern flex w-full items-center justify-center gap-2">
              {evaluating ? <Loader className="animate-spin" size={20} /> : <><Send size={18} /> Submit answer</>}
            </button>
          )}

          <div className="flex justify-between gap-3">
            <button type="button" onClick={() => setCurrentQIndex((index) => Math.max(0, index - 1))} disabled={currentQIndex === 0 || evaluating} className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-semibold text-gray-700 disabled:opacity-40">
              Previous
            </button>
            {currentEvaluation && (
              <button type="button" onClick={() => setCurrentQIndex((index) => Math.min(questions.length, index + 1))} className="btn-modern">
                {currentQIndex === questions.length - 1 ? 'View summary' : 'Next question'}
              </button>
            )}
          </div>
        </div>
      )}

      {questions.length > 0 && currentQIndex === questions.length && completed && (
        <div className="space-y-5 rounded-2xl border border-gray-100 bg-white p-8 text-center shadow-sm">
          <CheckCircle className="mx-auto text-green-500" size={56} />
          <h3 className="text-2xl font-bold text-gray-900">Interview Session Complete</h3>
          <p className="text-gray-500">Your answers and feedback are saved to your interview history.</p>
          <div className="grid gap-3 text-sm sm:grid-cols-3">
            <div className="rounded-xl bg-gray-50 p-4"><p className="text-gray-500">Technical (50%)</p><p className="text-xl font-bold">{technicalScore}/100</p></div>
            <div className="rounded-xl bg-gray-50 p-4"><p className="text-gray-500">HR (50%)</p><p className="text-xl font-bold">{hrScore}/100</p></div>
            <div className="rounded-xl bg-brand-50 p-4"><p className="text-brand-700">Overall score</p><p className="text-xl font-bold text-brand-800">{overallScore}/100</p></div>
          </div>
          <div className="text-left">
            <h4 className="mb-2 font-bold">Areas to improve</h4>
            <ul className="list-inside list-disc space-y-1 text-sm text-gray-600">
              {Object.values(evaluations).filter((item) => item.question_type === 'technical_mcq' && !item.is_correct).map((item) => (
                <li key={item.question_index}>{item.skill || `Technical question ${item.question_index + 1}`}</li>
              ))}
              {Object.values(evaluations).filter((item) => item.question_type === 'hr' && item.score_out_of_10 < 5).map((item) => (
                <li key={item.question_index}>HR response {item.question_index - 4}: {item.missing_points}</li>
              ))}
            </ul>
          </div>
          <button onClick={generateQuestions} className="btn-modern mt-2">Start New Session</button>
        </div>
      )}
    </motion.div>
  );
}
