import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, BookOpen, CheckCircle2, Circle, ClipboardCheck, Loader, RotateCcw, Sparkles } from 'lucide-react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import api from '../api';
import LearningLessonContent from '../components/LearningLessonContent';
import StudyCoachAnswer from '../components/StudyCoachAnswer';
import { getActiveCoachForm } from '../utils/learningPageState';
import { createStudyCoachRequest } from '../utils/studyCoach';

export default function Learning() {
  const [searchParams] = useSearchParams();
  const skillId = searchParams.get('skill') || '';
  const requestedLessonId = searchParams.get('lesson') || '';
  const [course, setCourse] = useState(null);
  const [lessonIndex, setLessonIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [startingPractice, setStartingPractice] = useState(false);
  const [startingAssessment, setStartingAssessment] = useState(false);
  const [coachForm, setCoachForm] = useState(null);
  const [coachSubmitting, setCoachSubmitting] = useState(false);
  const [coachErrorState, setCoachErrorState] = useState(null);
  const [coachResultState, setCoachResultState] = useState(null);
  const coachRequestSequence = useRef(0);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    const loadCourse = async () => {
      setLoading(true);
      setError('');
      setCourse(null);
      if (!skillId) {
        setError('Choose a skill lesson from your roadmap to get started.');
        setLoading(false);
        return;
      }

      try {
        const { data } = await api.get('/learning/skill', { params: { skill_id: skillId } });
        if (!active) return;
        setCourse(data);
        const lessons = data.content?.lessons || [];
        const completed = new Set(data.completed_lessons || []);
        const requestedIndex = lessons.findIndex((lesson) => lesson.lesson_id === requestedLessonId);
        const nextLesson = lessons.findIndex((lesson) => !completed.has(lesson.lesson_id));
        setLessonIndex(requestedIndex >= 0 ? requestedIndex : nextLesson === -1 ? Math.max(0, lessons.length - 1) : nextLesson);
      } catch (err) {
        if (active) setError(err.response?.data?.detail || 'Unable to load this skill lesson.');
      } finally {
        if (active) setLoading(false);
      }
    };

    loadCourse();
    return () => {
      active = false;
    };
  }, [skillId, requestedLessonId]);

  const lessons = course?.content?.lessons || [];
  const lesson = lessons[lessonIndex];
  const completedLessons = useMemo(() => new Set(course?.completed_lessons || []), [course]);
  const isComplete = lesson ? completedLessons.has(lesson.lesson_id) : false;
  const progress = course?.progress || { completed: 0, total: lessons.length };

  const selectLesson = (index) => {
    coachRequestSequence.current += 1;
    setLessonIndex(index);
    setCoachForm(null);
    setCoachErrorState(null);
    setCoachResultState(null);
    setCoachSubmitting(false);
  };

  const updateLessonCompletion = async () => {
    if (!course || !lesson || saving) return;
    setSaving(true);
    setError('');
    try {
      const { data } = await api.put('/learning/progress', {
        skill_id: course.skill_id,
        lesson_id: lesson.lesson_id,
        completed: !isComplete,
      });
      setCourse(data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Unable to save lesson progress. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const startPractice = async () => {
    if (!course || !lesson || startingPractice) return;
    setStartingPractice(true);
    setError('');
    try {
      const { data } = await api.post('/learning/practice', {
        skill_id: course.skill_id,
        lesson_id: lesson.lesson_id,
      });
      navigate(`/practice/${data.id}`);
    } catch (err) {
      setError(err.response?.data?.detail || 'Unable to prepare practice for this lesson.');
    } finally {
      setStartingPractice(false);
    }
  };

  const startAssessment = async () => {
    if (!course || !lesson || startingAssessment) return;
    setStartingAssessment(true);
    setError('');
    try {
      const { data } = await api.post('/learning/assessment', {
        skill_id: course.skill_id,
        lesson_id: lesson.lesson_id,
      });
      navigate(`/assessment/${data.id}`);
    } catch (err) {
      setError(err.response?.data?.detail || 'Unable to prepare an assessment for this lesson.');
    } finally {
      setStartingAssessment(false);
    }
  };

  const submitStudyCoachRequest = async (event) => {
    event.preventDefault();
    if (!course || !lesson || coachSubmitting) return;
    const requestSequence = ++coachRequestSequence.current;

    let payload;
    try {
      payload = createStudyCoachRequest({
        skillId: course.skill_id,
        lessonId: lesson.lesson_id,
        concept: coachConcept,
        question: coachQuestion,
      });
    } catch (err) {
      setCoachErrorState({ lessonId: lesson.lesson_id, message: err.message });
      return;
    }

    setCoachSubmitting(true);
    setCoachErrorState({ lessonId: lesson.lesson_id, message: '' });
    setCoachResultState({ lessonId: lesson.lesson_id, data: null });
    try {
      const { data } = await api.post('/learning/coach', payload);
      if (coachRequestSequence.current === requestSequence) {
        setCoachResultState({ lessonId: lesson.lesson_id, data });
      }
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (coachRequestSequence.current === requestSequence) {
        setCoachErrorState({
          lessonId: lesson.lesson_id,
          message: typeof detail === 'string' ? detail : 'Unable to get Study Coach guidance. Please try again.',
        });
      }
    } finally {
      if (coachRequestSequence.current === requestSequence) setCoachSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="panel-card flex min-h-64 flex-col items-center justify-center gap-3 text-slate-500" role="status">
        <Loader className="animate-spin text-brand-600" size={28} />
        <p className="font-medium">Preparing your skill lesson...</p>
      </div>
    );
  }

  if (error && !course) {
    return (
      <div className="panel-card space-y-4 text-center">
        <div className="mx-auto inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-50 text-amber-600">
          <BookOpen size={24} />
        </div>
        <h1 className="text-xl font-bold text-slate-900">Lesson unavailable</h1>
        <p className="text-sm text-slate-600" role="alert">{error}</p>
        <Link to="/roadmap" className="btn-modern">Return to roadmap</Link>
      </div>
    );
  }

  if (!course || lessons.length === 0) {
    return (
      <div className="panel-card space-y-3 text-center">
        <h1 className="text-xl font-bold text-slate-900">No concepts are available yet</h1>
        <p className="text-sm text-slate-600">Return to your roadmap and open a mapped skill lesson.</p>
        <Link to="/roadmap" className="btn-modern">Return to roadmap</Link>
      </div>
    );
  }

  if (!lesson) {
    return (
      <div className="panel-card space-y-3 text-center">
        <h1 className="text-xl font-bold text-slate-900">Lesson unavailable</h1>
        <p className="text-sm text-slate-600" role="alert">
          The selected lesson is not present in this skill course. Choose a lesson from the lesson navigation or return to your roadmap.
        </p>
        <Link to="/roadmap" className="btn-modern">Return to roadmap</Link>
      </div>
    );
  }

  const activeCoachForm = getActiveCoachForm(coachForm, lesson);
  const coachConcept = activeCoachForm.concept;
  const coachQuestion = activeCoachForm.question;
  const coachError = coachErrorState && coachErrorState.lessonId === lesson.lesson_id
    ? coachErrorState.message
    : '';
  const coachResult = coachResultState && coachResultState.lessonId === lesson.lesson_id
    ? coachResultState.data
    : null;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <header className="page-header">
        <div>
          <div className="soft-label mb-3"><BookOpen size={13} /> Skill learning</div>
          <h1 className="page-title">{course.skill_id}</h1>
          <p className="page-subtitle mt-2">{course.content.introduction}</p>
        </div>
        <Link to="/roadmap" className="inline-flex items-center gap-2 text-sm font-semibold text-brand-700 hover:text-brand-900">
          <ArrowLeft size={16} /> Back to roadmap
        </Link>
      </header>

      <section className="panel-card space-y-4" aria-label="Learning context and objectives">
        <div className="flex flex-wrap gap-2">
          {course.context?.target_role && <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700">{course.context.target_role}</span>}
          {course.context?.branch && <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700">{course.context.branch}{course.context.semester ? ` · Semester ${course.context.semester}` : ''}</span>}
          {course.context?.roadmap?.study_type && <span className="rounded-full bg-violet-50 px-3 py-1 text-xs font-medium capitalize text-violet-700">{course.context.roadmap.study_type}</span>}
          {course.context?.roadmap?.week && <span className="rounded-full bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700">Roadmap week {course.context.roadmap.week}</span>}
        </div>

        {course.context?.vtu_subjects?.length > 0 && (
          <p className="text-sm text-slate-600"><span className="font-semibold text-slate-800">Related VTU subjects:</span> {course.context.vtu_subjects.join(', ')}</p>
        )}

        <div>
          <h2 className="section-title">Learning objectives</h2>
          <ul className="mt-3 grid gap-2 sm:grid-cols-2">
            {course.content.learning_objectives.map((objective, index) => (
              <li key={index} className="flex items-start gap-2 rounded-xl bg-slate-50 p-3 text-sm text-slate-700">
                <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-brand-600" />
                {objective}
              </li>
            ))}
          </ul>
        </div>
      </section>

      {course.content_source === 'fallback' && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900" role="status">
          AI lesson generation is unavailable. This structured starter guide includes recommended references and can still be used to begin learning.
        </div>
      )}

      <section className="panel-card space-y-5" aria-label="Lesson progress">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-500">Concept {lessonIndex + 1} of {lessons.length}</p>
            <h2 className="mt-1 text-xl font-bold text-slate-900">{lesson.title}</h2>
          </div>
          <p className="text-sm font-semibold text-slate-600">{progress.completed} of {progress.total} lessons completed</p>
        </div>

        <div className="h-2 overflow-hidden rounded-full bg-slate-100" aria-label={`${progress.completed} of ${progress.total} lessons completed`}>
          <div className="h-full rounded-full bg-brand-500 transition-[width]" style={{ width: `${progress.total ? (progress.completed / progress.total) * 100 : 0}%` }} />
        </div>

        <nav className="flex gap-2 overflow-x-auto pb-1" aria-label="Lesson navigation">
          {lessons.map((item, index) => {
            const done = completedLessons.has(item.lesson_id);
            return (
              <button
                key={item.lesson_id}
                type="button"
                onClick={() => selectLesson(index)}
                aria-current={index === lessonIndex ? 'step' : undefined}
                className={`flex min-w-fit items-center gap-2 rounded-xl border px-3 py-2 text-sm font-medium ${
                  index === lessonIndex ? 'border-brand-300 bg-brand-50 text-brand-800' : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
                }`}
              >
                {done ? <CheckCircle2 size={16} /> : <Circle size={16} />}
                {item.title}
              </button>
            );
          })}
        </nav>

        <LearningLessonContent lesson={lesson} />

        <section className="rounded-2xl border border-brand-100 bg-brand-50/40 p-4 sm:p-5" aria-label="Ask the Study Coach" aria-busy={coachSubmitting}>
          <div className="flex items-start gap-3">
            <div className="rounded-xl bg-white p-2 text-brand-700 shadow-sm"><Sparkles size={18} /></div>
            <div>
              <h3 className="font-bold text-slate-900">Ask the Study Coach</h3>
              <p className="mt-1 text-sm leading-6 text-slate-600">
                Ask about <span className="font-medium">{lesson.title}</span> or a related concept. Get a direct answer with useful detail, hints, or an example when they help. AI guidance can be inaccurate; check important details.
              </p>
            </div>
          </div>

          <form className="mt-4 space-y-3" onSubmit={submitStudyCoachRequest}>
            <div>
              <label htmlFor="coach-concept" className="mb-1 block text-sm font-semibold text-slate-800">Concept</label>
              <input
                id="coach-concept"
                name="concept"
                type="text"
                value={coachConcept}
                onChange={(event) => setCoachForm({
                  lessonId: lesson.lesson_id,
                  concept: event.target.value,
                  question: coachQuestion,
                })}
                maxLength={120}
                required
                className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
                aria-describedby="coach-concept-help"
              />
              <p id="coach-concept-help" className="mt-1 text-xs text-slate-500">Choose the concept or topic your question is about.</p>
            </div>
            <div>
              <label htmlFor="coach-question" className="mb-1 block text-sm font-semibold text-slate-800">What would you like help with? <span className="font-normal text-slate-500">(optional)</span></label>
              <textarea
                id="coach-question"
                name="question"
                value={coachQuestion}
                onChange={(event) => setCoachForm({
                  lessonId: lesson.lesson_id,
                  concept: coachConcept,
                  question: event.target.value,
                })}
                maxLength={500}
                rows={3}
                className="w-full resize-y rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
                placeholder="Ask a question about this concept or a related topic."
              />
            </div>
            <button type="submit" disabled={coachSubmitting} className="btn-modern disabled:cursor-not-allowed disabled:opacity-60">
              {coachSubmitting ? <Loader className="animate-spin" size={16} /> : <Sparkles size={16} />}
              {coachSubmitting ? 'Preparing guidance...' : 'Ask the Study Coach'}
            </button>
          </form>

          {coachError && <p className="mt-3 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700" role="alert">{coachError}</p>}

          {coachResult && (
            <StudyCoachAnswer
              result={coachResult}
              onPractice={startPractice}
              onAssessment={startAssessment}
              startingPractice={startingPractice}
              startingAssessment={startingAssessment}
            />
          )}
          {!coachResult && !coachError && !coachSubmitting && (
            <p className="mt-3 text-xs text-slate-500">Your request is sent only when you select “Ask the Study Coach.”</p>
          )}
        </section>

        {error && <p className="rounded-xl bg-red-50 p-3 text-sm text-red-700" role="alert">{error}</p>}

        <div className="flex flex-col-reverse gap-3 border-t border-slate-100 pt-4 sm:flex-row sm:justify-between">
          <button
            type="button"
            onClick={() => selectLesson(Math.max(0, lessonIndex - 1))}
            disabled={lessonIndex === 0}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <ArrowLeft size={16} /> Previous lesson
          </button>
          <button
            type="button"
            onClick={updateLessonCompletion}
            disabled={saving}
            className="btn-modern"
          >
            {saving ? <Loader className="animate-spin" size={16} /> : isComplete ? <RotateCcw size={16} /> : <CheckCircle2 size={16} />}
            {saving ? 'Saving...' : isComplete ? 'Mark as not completed' : 'Mark lesson complete'}
          </button>
          <button
            type="button"
            onClick={startPractice}
            disabled={startingPractice}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-brand-200 bg-brand-50 px-4 py-2.5 text-sm font-semibold text-brand-800 hover:bg-brand-100 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {startingPractice ? <Loader className="animate-spin" size={16} /> : <Sparkles size={16} />}
            {startingPractice ? 'Preparing practice...' : 'Practice this concept'}
          </button>
          <button
            type="button"
            onClick={startAssessment}
            disabled={startingAssessment}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-violet-200 bg-violet-50 px-4 py-2.5 text-sm font-semibold text-violet-800 hover:bg-violet-100 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {startingAssessment ? <Loader className="animate-spin" size={16} /> : <ClipboardCheck size={16} />}
            {startingAssessment ? 'Preparing assessment...' : 'Assess this concept'}
          </button>
          <button
            type="button"
            onClick={() => selectLesson(Math.min(lessons.length - 1, lessonIndex + 1))}
            disabled={lessonIndex === lessons.length - 1}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Next lesson <ArrowRight size={16} />
          </button>
        </div>
      </section>

      {progress.total > 0 && progress.completed === progress.total && (
        <section className="rounded-2xl border border-emerald-200 bg-emerald-50 p-5 text-center">
          <CheckCircle2 className="mx-auto text-emerald-600" size={30} />
          <h2 className="mt-2 text-lg font-bold text-emerald-900">All lessons completed</h2>
          <p className="mt-1 text-sm text-emerald-800">You have finished this learning guide. Lesson completion is progress tracking, not proof of skill mastery.</p>
          <Link to="/roadmap" className="mt-4 inline-flex font-semibold text-emerald-800 underline underline-offset-4">Return to your roadmap</Link>
        </section>
      )}

      <p className="text-center text-xs text-slate-500">{course.completion_notice}</p>
    </div>
  );
}
