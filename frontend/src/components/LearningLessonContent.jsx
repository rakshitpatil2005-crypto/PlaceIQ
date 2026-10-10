import { CheckCircle2 } from 'lucide-react';

export default function LearningLessonContent({ lesson }) {
  if (!lesson) return null;

  return (
    <article className="space-y-5 border-t border-slate-100 pt-5">
      <div className="space-y-2">
        <h3 className="text-xs font-bold uppercase tracking-[0.14em] text-brand-700">Start here</h3>
        <p className="text-sm leading-7 text-slate-700">{lesson.introduction}</p>
      </div>

      <div className="space-y-2">
        <h3 className="text-xs font-bold uppercase tracking-[0.14em] text-brand-700">Understand the concept</h3>
        <p className="whitespace-pre-line text-sm leading-7 text-slate-700">{lesson.explanation}</p>
      </div>

      <div className="rounded-2xl border border-blue-100 bg-blue-50/60 p-4">
        <h3 className="text-sm font-bold text-blue-900">Example</h3>
        <p className="mt-2 whitespace-pre-line text-sm leading-6 text-slate-700">{lesson.example}</p>
        {lesson.code_example && (
          <pre className="mt-3 overflow-x-auto rounded-xl bg-slate-950 p-4 text-xs leading-6 text-slate-100"><code>{lesson.code_example}</code></pre>
        )}
        {lesson.example_explanation && <p className="mt-3 text-sm leading-6 text-slate-700">{lesson.example_explanation}</p>}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-2xl border border-slate-100 p-4">
          <h3 className="font-bold text-slate-900">Where it is used</h3>
          <ul className="mt-2 list-inside list-disc space-y-1 text-sm leading-6 text-slate-600">
            {lesson.real_world_applications.map((item, index) => <li key={index}>{item}</li>)}
          </ul>
        </div>
        <div className="rounded-2xl border border-amber-100 bg-amber-50/50 p-4">
          <h3 className="font-bold text-amber-900">Common mistakes</h3>
          <ul className="mt-2 list-inside list-disc space-y-1 text-sm leading-6 text-slate-700">
            {lesson.common_mistakes.map((item, index) => <li key={index}>{item}</li>)}
          </ul>
        </div>
      </div>

      <div className="rounded-2xl border border-emerald-100 bg-emerald-50/50 p-4">
        <h3 className="font-bold text-slate-900">Key takeaways</h3>
        <ul className="mt-2 list-inside list-disc space-y-1 text-sm leading-6 text-slate-700">
          {lesson.key_takeaways.map((item, index) => (
            <li key={index} className="flex items-start gap-2">
              <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-brand-600" />
              {item}
            </li>
          ))}
        </ul>
        <p className="mt-3 border-t border-emerald-100 pt-3 text-sm leading-6 text-slate-700"><span className="font-semibold">Quick recap:</span> {lesson.quick_recap}</p>
      </div>
    </article>
  );
}
