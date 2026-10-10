import { BookOpen, ClipboardCheck, Sparkles } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function StudyCoachAnswer({
  result,
  onPractice,
  onAssessment,
  startingPractice,
  startingAssessment,
}) {
  return (
    <div className="mt-5 space-y-4 border-t border-brand-100 pt-4" aria-live="polite">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${result.source === 'groq' ? 'bg-violet-100 text-violet-800' : 'bg-amber-100 text-amber-900'}`}>
          {result.source === 'groq' ? 'AI-generated guidance · Groq' : 'Lesson-grounded fallback'}
        </span>
        {result.evidence.status === 'insufficient_evidence' && (
          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">Insufficient assessment evidence</span>
        )}
      </div>

      <div>
        <h4 className="font-bold text-slate-900">Answer</h4>
        <p className="mt-1 whitespace-pre-line text-sm leading-7 text-slate-700">{result.explanation}</p>
      </div>
      {result.hints.length > 0 && (
        <div>
          <h4 className="font-bold text-slate-900">Hints</h4>
          <ol className="mt-2 list-inside list-decimal space-y-2 text-sm leading-6 text-slate-700">
            {result.hints.map((hint, index) => <li key={index}>{hint}</li>)}
          </ol>
        </div>
      )}
      {result.example.trim() && (
        <div className="rounded-xl border border-blue-100 bg-white p-4">
          <h4 className="font-bold text-slate-900">Example</h4>
          <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-slate-700">{result.example}</p>
        </div>
      )}
      <p className="rounded-xl bg-white/80 p-3 text-sm leading-6 text-slate-600">
        <span className="font-semibold text-slate-800">Assessment evidence:</span> {result.evidence.note}
      </p>
      <div className="flex flex-wrap gap-2">
        <Link to={result.links.lesson} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50">
          <BookOpen size={15} /> Review lesson
        </Link>
        <button type="button" onClick={onPractice} disabled={startingPractice} className="inline-flex items-center gap-2 rounded-xl border border-brand-200 bg-white px-3 py-2 text-sm font-semibold text-brand-800 hover:bg-brand-50 disabled:opacity-60">
          <Sparkles size={15} /> {startingPractice ? 'Preparing practice...' : 'Practise this lesson'}
        </button>
        <button type="button" onClick={onAssessment} disabled={startingAssessment} className="inline-flex items-center gap-2 rounded-xl border border-violet-200 bg-white px-3 py-2 text-sm font-semibold text-violet-800 hover:bg-violet-50 disabled:opacity-60">
          <ClipboardCheck size={15} /> {startingAssessment ? 'Preparing assessment...' : 'Assess this lesson'}
        </button>
      </div>
    </div>
  );
}
