import { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { AlertCircle, ArrowRight, Gauge, Lightbulb, Sparkles, Target, TrendingUp } from 'lucide-react';
import { Link } from 'react-router-dom';
import api from '../api';

const clamp = (value) => Math.max(0, Math.min(100, Number(value) || 0));

export default function Readiness() {
  const [readiness, setReadiness] = useState({
    readiness_score: 0,
    resume_score: 0,
    skill_score: 0,
    roadmap_score: 0,
    interview_score: 0,
  });
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchReadiness = async () => {
      try {
        const [scoreRes, historyRes] = await Promise.all([
          api.get('/readiness/score').catch(() => ({ data: { readiness_score: 0, resume_score: 0, skill_score: 0, roadmap_score: 0, interview_score: 0 } })),
          api.get('/readiness/history').catch(() => ({ data: { history: [] } })),
        ]);

        setReadiness({
          readiness_score: clamp(scoreRes.data?.readiness_score),
          resume_score: clamp(scoreRes.data?.resume_score),
          skill_score: clamp(scoreRes.data?.skill_score),
          roadmap_score: clamp(scoreRes.data?.roadmap_score),
          interview_score: clamp(scoreRes.data?.interview_score),
        });

        setHistory(Array.isArray(historyRes.data?.history) ? historyRes.data.history : []);
      } catch (err) {
        setError('Unable to load readiness details.');
      } finally {
        setLoading(false);
      }
    };

    fetchReadiness();
  }, []);

  const summary = useMemo(() => {
    const biggestOpportunity = [
      { label: 'Resume Score', value: readiness.resume_score },
      { label: 'Skill Match', value: readiness.skill_score },
      { label: 'Roadmap Completion', value: readiness.roadmap_score },
      { label: 'Interview Score', value: readiness.interview_score },
    ].sort((a, b) => a.value - b.value)[0];

    return {
      biggestOpportunity,
      strongestArea: [
        { label: 'Resume Score', value: readiness.resume_score },
        { label: 'Skill Match', value: readiness.skill_score },
        { label: 'Roadmap Completion', value: readiness.roadmap_score },
        { label: 'Interview Score', value: readiness.interview_score },
      ].sort((a, b) => b.value - a.value)[0],
    };
  }, [readiness]);

  const metricCards = [
    { label: 'Resume Score', value: readiness.resume_score, weight: '25%', tone: 'bg-blue-50 text-blue-600', border: 'border-blue-200' },
    { label: 'Skill Match', value: readiness.skill_score, weight: '30%', tone: 'bg-emerald-50 text-emerald-600', border: 'border-emerald-200' },
    { label: 'Roadmap Completion', value: readiness.roadmap_score, weight: '15%', tone: 'bg-violet-50 text-violet-600', border: 'border-violet-200' },
    { label: 'Interview Score', value: readiness.interview_score, weight: '30%', tone: 'bg-amber-50 text-amber-600', border: 'border-amber-200' },
  ];

  if (loading) {
    return (
      <div className="panel-card text-center text-slate-500">
        <div className="inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-600">
          <Gauge className="animate-pulse" size={24} />
        </div>
        <p className="mt-4 text-lg font-semibold text-slate-700">Loading readiness.</p>
      </div>
    );
  }

  return (
    <motion.div initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <div className="page-header">
        <div>
          <div className="soft-label mb-3">
            <Gauge size={12} />
            Placement readiness
          </div>
          <h2 className="page-title">Your readiness is {readiness.readiness_score}/100</h2>
          <p className="page-subtitle mt-2">A clear summary of how prepared you are for your target role based on resume quality, skill alignment, roadmap progress, and interview performance.</p>
        </div>

        <Link to="/gap" className="btn-modern">
          View Skill Gap
          <ArrowRight size={16} />
        </Link>
      </div>

      {error && (
        <div className="auth-error">
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      <div className="panel-card">
        <div className="flex flex-col items-center gap-5 text-center md:flex-row md:justify-between md:text-left">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-500">Overall score</div>
            <div className="mt-2 text-6xl font-black tracking-tight text-slate-900">{readiness.readiness_score}</div>
            <div className="mt-2 text-sm text-slate-500">Based on the readiness formula: 25% Resume + 30% Skill Match + 15% Roadmap + 30% Interview.</div>
          </div>

          <div className="w-full max-w-xs">
            <div className="relative h-32 w-32 mx-auto">
              <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90">
                <circle cx="60" cy="60" r="44" stroke="#e2e8f0" strokeWidth="10" fill="none" />
                <circle
                  cx="60"
                  cy="60"
                  r="44"
                  stroke={readiness.readiness_score >= 70 ? '#16a34a' : readiness.readiness_score >= 40 ? '#f59e0b' : '#ef4444'}
                  strokeWidth="10"
                  strokeLinecap="round"
                  fill="none"
                  strokeDasharray={2 * Math.PI * 44}
                  strokeDashoffset={2 * Math.PI * 44 * (1 - readiness.readiness_score / 100)}
                />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center text-xl font-extrabold text-slate-900">{readiness.readiness_score}</div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {metricCards.map(({ label, value, weight, tone, border }) => (
          <div key={label} className={`panel-card border ${border}`}>
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm text-slate-500">{label}</span>
              <span className="rounded-full bg-slate-100 px-2 py-1 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-600">{weight}</span>
            </div>
            <div className={`mt-4 inline-flex h-12 w-12 items-center justify-center rounded-2xl ${tone}`}>
              <TrendingUp size={22} />
            </div>
            <div className="mt-4 text-4xl font-black tracking-tight text-slate-900">{value}</div>
            <div className="mt-3 h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
              <div className="h-full rounded-full bg-gradient-to-r from-brand-500 to-emerald-500" style={{ width: `${value}%` }} />
            </div>
          </div>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="panel-card">
          <div className="mb-4 flex items-center gap-2 text-slate-900">
            <Lightbulb size={18} className="text-amber-500" />
            <h3 className="text-lg font-bold">What is helping your score</h3>
          </div>
          <ul className="space-y-3 text-sm text-slate-600">
            {readiness.resume_score >= 60 && <li>• Your resume quality is solid and contributing well to your placement profile.</li>}
            {readiness.skill_score >= 60 && <li>• Your skill match is strong and aligned with your target role.</li>}
            {readiness.roadmap_score >= 50 && <li>• Your roadmap momentum is helping you maintain consistent learning progress.</li>}
            {readiness.interview_score >= 50 && <li>• Your interview performance is providing a meaningful boost to readiness.</li>}
            {readiness.readiness_score < 50 && <li>• Your biggest opportunity is improving the weakest area shown above.</li>}
          </ul>
        </div>

        <div className="panel-card">
          <div className="mb-4 flex items-center gap-2 text-slate-900">
            <Target size={18} className="text-brand-600" />
            <h3 className="text-lg font-bold">What is lowering your score</h3>
          </div>
          <ul className="space-y-3 text-sm text-slate-600">
            {summary.biggestOpportunity && (
              <li>• Your biggest opportunity is improving {summary.biggestOpportunity.label.toLowerCase()} from {summary.biggestOpportunity.value}% to a stronger range.</li>
            )}
            {readiness.resume_score < 60 && <li>• Resume quality and ATS strength still have room to improve.</li>}
            {readiness.skill_score < 60 && <li>• Skill alignment with your target role could be strengthened through focused learning.</li>}
            {readiness.roadmap_score < 50 && <li>• Roadmap completion needs more consistent practice and follow-through.</li>}
            {readiness.interview_score < 50 && <li>• Interview confidence and technical clarity remain the main improvement area.</li>}
          </ul>
        </div>
      </div>

      <div className="panel-card">
        <div className="mb-4 flex items-center gap-2 text-slate-900">
          <Sparkles size={18} className="text-emerald-600" />
          <h3 className="text-lg font-bold">Recommended next action</h3>
        </div>

        {summary.biggestOpportunity && (
          <div className="rounded-2xl border border-brand-100 bg-brand-50 p-4 text-sm text-slate-700">
            <span className="font-bold text-slate-900">Your biggest opportunity:</span> improve {summary.biggestOpportunity.label.toLowerCase()} from {summary.biggestOpportunity.value}% to a higher score.
          </div>
        )}

        <div className="mt-4 flex flex-wrap gap-3">
          <Link to="/gap" className="btn-modern">
            View Skill Gap
          </Link>
          <Link to="/roadmap" className="btn-modern secondary-style">
            Continue Roadmap
          </Link>
        </div>
      </div>

      {history.length > 0 && (
        <div className="panel-card">
          <div className="mb-4 text-lg font-bold text-slate-900">Readiness history</div>
          <div className="space-y-3">
            {history.slice(0, 5).map((item) => (
              <div key={item.id} className="flex items-center justify-between rounded-2xl border border-slate-200 bg-slate-50 p-3 text-sm text-slate-600">
                <span>{new Date(item.created_at).toLocaleDateString()}</span>
                <span className="font-bold text-slate-900">{item.total}/100</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </motion.div>
  );
}
