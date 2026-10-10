import { useEffect, useState } from 'react';
import { Award, BookOpenCheck, Loader, TrendingUp } from 'lucide-react';
import { Link } from 'react-router-dom';
import api from '../api';
import { formatMasteryScore, masteryStatusLabel } from '../utils/mastery';

function statusClasses(status) {
  if (status === 'demonstrated_proficiency' || status === 'strength') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-800';
  }
  if (status === 'developing' || status === 'review') {
    return 'border-amber-200 bg-amber-50 text-amber-800';
  }
  return 'border-slate-200 bg-slate-50 text-slate-600';
}

export default function Mastery() {
  const [mastery, setMastery] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    api.get('/learning/mastery')
      .then(({ data }) => {
        if (active) setMastery(data);
      })
      .catch((err) => {
        if (active) setError(err.response?.data?.detail || 'Unable to load assessment-based skill mastery.');
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  if (loading) {
    return (
      <div className="panel-card flex min-h-64 flex-col items-center justify-center gap-3 text-slate-500" role="status">
        <Loader className="animate-spin text-brand-600" size={28} />
        <p className="font-medium">Loading your assessment evidence...</p>
      </div>
    );
  }

  if (error) {
    return <div className="panel-card text-sm text-red-700" role="alert">{error}</div>;
  }

  const skills = mastery?.skills || [];

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header className="page-header">
        <div>
          <div className="soft-label mb-3"><Award size={14} /> Skill mastery</div>
          <h1 className="page-title">Assessment-based progress</h1>
          <p className="page-subtitle mt-2">See how your submitted assessment evidence develops across canonical skills and concepts.</p>
        </div>
      </header>

      <section className="panel-card border-brand-100 bg-brand-50/60" aria-label="Mastery scoring policy">
        <h2 className="font-bold text-slate-900">How this is calculated</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-6 text-slate-700">
          <li>{mastery.policy.evidence}</li>
          <li>{mastery.policy.weighting}</li>
          <li>{mastery.policy.minimum_evidence}</li>
          <li>{mastery.policy.proficiency}</li>
          <li>{mastery.policy.concepts}</li>
          <li>{mastery.policy.practice_and_interviews}</li>
        </ul>
        <p className="mt-3 border-t border-brand-100 pt-3 text-xs leading-5 text-slate-600">{mastery.notice}</p>
      </section>

      {!skills.length ? (
        <section className="panel-card py-12 text-center">
          <BookOpenCheck className="mx-auto text-slate-400" size={32} />
          <h2 className="mt-3 text-lg font-bold text-slate-900">No submitted assessment evidence yet</h2>
          <p className="mt-2 text-sm text-slate-600">Complete a lesson assessment to begin building an explainable mastery history. No score is assigned before evidence exists.</p>
        </section>
      ) : (
        <div className="space-y-5">
          {skills.map((skill) => (
            <article key={skill.skill_id} className="panel-card space-y-5">
              <header className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-xl font-bold text-slate-900">{skill.skill_id}</h2>
                  <p className="mt-1 text-sm text-slate-600">
                    {skill.evidence_assessments} submitted assessment{skill.evidence_assessments === 1 ? '' : 's'} · {skill.evidence_correct}/{skill.evidence_questions} correct answers
                  </p>
                </div>
                <div className="text-right">
                  <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold ${statusClasses(skill.status)}`}>
                    {masteryStatusLabel(skill.status)}
                  </span>
                  <p className="mt-2 text-2xl font-extrabold text-slate-900">
                    {formatMasteryScore(skill.score_pct)}
                  </p>
                  <p className="text-xs text-slate-500">assessment evidence score</p>
                </div>
              </header>

              <div className="grid gap-5 lg:grid-cols-2">
                <section aria-label={`${skill.skill_id} concepts`}>
                  <h3 className="font-semibold text-slate-800">Concept evidence</h3>
                  {skill.concepts.length ? (
                    <ul className="mt-3 space-y-2">
                      {skill.concepts.map((concept) => (
                        <li key={concept.concept} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-100 p-3">
                          <span className="text-sm text-slate-700">{concept.concept}</span>
                          <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${statusClasses(concept.status)}`}>
                            {concept.score_pct === null ? masteryStatusLabel(concept.status) : `${formatMasteryScore(concept.score_pct)} · ${masteryStatusLabel(concept.status)}`}
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : <p className="mt-2 text-sm text-slate-500">No concept evidence is available.</p>}
                </section>

                <section aria-label={`${skill.skill_id} mastery history`}>
                  <h3 className="flex items-center gap-2 font-semibold text-slate-800"><TrendingUp size={16} /> Evidence history</h3>
                  {skill.history.length ? (
                    <ol className="mt-3 space-y-2">
                      {skill.history.map((item, index) => (
                        <li key={item.assessment_id} className="flex items-center justify-between gap-3 rounded-xl border border-slate-100 p-3">
                          <div>
                            <p className="text-sm font-medium text-slate-800">Assessment {index + 1}</p>
                            <p className="text-xs text-slate-500">
                              {item.submitted_at ? new Date(item.submitted_at).toLocaleString() : 'Submission date unavailable'} · {item.evidence_assessments} attempt{item.evidence_assessments === 1 ? '' : 's'}, {item.evidence_questions} answer{item.evidence_questions === 1 ? '' : 's'}
                            </p>
                            <Link to={`/assessment/${item.assessment_id}`} className="mt-1 inline-block text-xs font-semibold text-brand-700 underline underline-offset-2">
                              Review assessment
                            </Link>
                          </div>
                          <div className="text-right">
                            <p className="font-semibold text-slate-800">
                              {formatMasteryScore(item.evidence_score_pct)}
                            </p>
                            <p className="text-xs text-slate-500">{masteryStatusLabel(item.status)}</p>
                          </div>
                        </li>
                      ))}
                    </ol>
                  ) : <p className="mt-2 text-sm text-slate-500">No submitted assessments are available.</p>}
                  <p className="mt-3 text-xs text-slate-500">Latest individual assessment: {formatMasteryScore(skill.latest_assessment_score_pct)}</p>
                </section>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
