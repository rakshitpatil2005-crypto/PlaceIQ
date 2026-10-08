import { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { Activity, ArrowRight, BarChart3, BookOpen, CheckCircle2, Circle, FileText, Gauge, Map, MessageSquare, Sparkles, Target } from 'lucide-react';
import { Link } from 'react-router-dom';
import api from '../api';

const defaultProfile = {
  name: 'Student',
  branch: 'CSE',
  semester: '5',
  target_role: 'Software Engineer',
};

export default function Dashboard() {
  const [profile, setProfile] = useState(defaultProfile);
  const [stats, setStats] = useState({
    ats_score: 0,
    total_skills_extracted: 0,
    skill_match_pct: 0,
    target_role: 'Software Engineer',
    roadmap_progress: 0,
  });
  const [readiness, setReadiness] = useState({
    readiness_score: 0,
    resume_score: 0,
    skill_score: 0,
    roadmap_score: 0,
    interview_score: 0,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        const [profileRes, statsRes, readinessRes] = await Promise.all([
          api.get('/auth/me').catch(() => ({ data: defaultProfile })),
          api.get('/dashboard/stats').catch(() => ({
            data: {
              ats_score: 0,
              total_skills_extracted: 0,
              skill_match_pct: 0,
              target_role: 'Software Engineer',
              roadmap_progress: 0,
            },
          })),
          api.get('/readiness/score').catch(() => ({
            data: {
              readiness_score: 0,
              resume_score: 0,
              skill_score: 0,
              roadmap_score: 0,
              interview_score: 0,
            },
          })),
        ]);

        setProfile({
          name: profileRes.data?.name || defaultProfile.name,
          branch: profileRes.data?.branch || defaultProfile.branch,
          semester: profileRes.data?.semester || defaultProfile.semester,
          target_role: profileRes.data?.target_role || statsRes.data?.target_role || defaultProfile.target_role,
        });

        setStats({
          ats_score: Number(statsRes.data?.ats_score || 0),
          total_skills_extracted: Number(statsRes.data?.total_skills_extracted || 0),
          skill_match_pct: Number(statsRes.data?.skill_match_pct || 0),
          target_role: statsRes.data?.target_role || profileRes.data?.target_role || defaultProfile.target_role,
          roadmap_progress: Number(statsRes.data?.roadmap_progress || 0),
        });

        setReadiness({
          readiness_score: Number(readinessRes.data?.readiness_score || 0),
          resume_score: Number(readinessRes.data?.resume_score || 0),
          skill_score: Number(readinessRes.data?.skill_score || 0),
          roadmap_score: Number(readinessRes.data?.roadmap_score || 0),
          interview_score: Number(readinessRes.data?.interview_score || 0),
        });
      } catch (err) {
        console.error('Failed to load dashboard data', err);
      } finally {
        setLoading(false);
      }
    };

    fetchDashboardData();
  }, []);

  const journey = useMemo(() => {
    const stages = [
      { label: 'Resume', path: '/resume', done: stats.ats_score > 0 },
      { label: 'Skill Gap', path: '/gap', done: stats.skill_match_pct > 0 },
      { label: 'Roadmap', path: '/roadmap', done: stats.roadmap_progress > 0 },
      { label: 'Interview', path: '/interview', done: readiness.interview_score > 0 },
      { label: 'Readiness', path: '/readiness', done: readiness.readiness_score > 0 },
    ];

    const nextStage = stages.find((stage) => !stage.done) || stages[stages.length - 1];

    return {
      stages,
      nextStage,
      completedCount: stages.filter((stage) => stage.done).length,
    };
  }, [stats, readiness]);

  const nextActionLabel = (() => {
    if (stats.ats_score <= 0) return 'Upload your resume →';
    if (stats.skill_match_pct <= 0) return 'Analyze my VTU skill gap →';
    if (stats.roadmap_progress <= 0) return 'Generate my learning roadmap →';
    if (readiness.interview_score <= 0) return 'Start my AI mock interview →';
    return 'View my placement readiness →';
  })();

  const cards = [
    {
      label: 'Latest ATS score',
      value: `${stats.ats_score}`,
      suffix: '/100',
      icon: FileText,
      accent: 'bg-blue-50 text-blue-600',
      summary: 'Resume strength',
    },
    {
      label: `Skill match`,
      value: `${stats.skill_match_pct}`,
      suffix: '%',
      icon: Target,
      accent: 'bg-emerald-50 text-emerald-600',
      summary: 'Role alignment',
    },
    {
      label: 'Roadmap progress',
      value: `${stats.roadmap_progress}`,
      suffix: '%',
      icon: Activity,
      accent: 'bg-violet-50 text-violet-600',
      summary: 'Learning momentum',
    },
    {
      label: 'Interview score',
      value: `${readiness.interview_score}`,
      suffix: '/100',
      icon: MessageSquare,
      accent: 'bg-amber-50 text-amber-600',
      summary: 'Mock interview',
    },
  ];

  const actionLabel = nextActionLabel;

  return (
    <motion.div initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <header className="page-header dashboard-hero">
        <div>
          <div className="soft-label mb-3">
            <Sparkles size={12} />
            Placement journey
          </div>
          <h1 className="page-title">Welcome back, {profile.name}</h1>
          <div className="mt-3 flex flex-wrap gap-3 text-sm text-slate-600">
            <span className="rounded-full bg-slate-100 px-3 py-1.5 font-medium">Target Role: {profile.target_role}</span>
            <span className="rounded-full bg-slate-100 px-3 py-1.5 font-medium">Branch: {profile.branch}</span>
            <span className="rounded-full bg-slate-100 px-3 py-1.5 font-medium">Semester: {profile.semester}</span>
          </div>
        </div>

        <Link to={journey.nextStage.path} className="btn-modern">
          {actionLabel}
          <ArrowRight size={16} />
        </Link>
      </header>

      <div className="panel-card">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div className="section-title">Placement journey</div>
          <div className="text-sm font-semibold text-slate-500">
            {journey.completedCount}/{journey.stages.length} complete
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-5">
          {journey.stages.map((stage, index) => (
            <Link key={stage.label} to={stage.path} className={`rounded-2xl border p-3 transition-all ${stage.done ? 'border-brand-100 bg-brand-50' : 'border-slate-200 bg-slate-50/80'}`}>
              <div className="flex items-center justify-between gap-2">
                <div className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Step {index + 1}</div>
                {stage.done ? <CheckCircle2 size={16} className="text-brand-600" /> : <Circle size={16} className="text-slate-400" />}
              </div>
              <div className="mt-3 text-base font-bold text-slate-900">{stage.label}</div>
            </Link>
          ))}
        </div>
      </div>

      <div className="dashboard-grid">
        {cards.map(({ label, value, suffix, icon: Icon, accent, summary }, index) => (
          <motion.div
            key={label}
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.06 }}
            className="panel-card metric-card"
          >
            <div className="flex items-start justify-between gap-3">
              <div className={`inline-flex h-12 w-12 items-center justify-center rounded-2xl ${accent}`}>
                <Icon size={22} />
              </div>
              <span className="rounded-full bg-slate-100 px-2 py-1 text-[10px] font-bold uppercase tracking-[0.15em] text-slate-500">
                {summary}
              </span>
            </div>

            <div className="mt-6 space-y-2">
              <p className="text-sm font-medium text-slate-500">{label}</p>
              <div className="flex items-end gap-2">
                <h3 className="metric-value">{loading ? '—' : value}</h3>
                {suffix && <span className="mb-1 text-lg font-semibold text-slate-400">{suffix}</span>}
              </div>
            </div>
          </motion.div>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
        <div className="panel-card">
          <div className="mb-4 flex items-center justify-between">
            <div className="section-title">Readiness overview</div>
            <BarChart3 className="h-5 w-5 text-brand-600" />
          </div>
          <div className="space-y-4">
            <div>
              <div className="mb-2 flex justify-between text-sm text-slate-500">
                <span>Resume performance</span>
                <span>{stats.ats_score}/100</span>
              </div>
              <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
                <div className="h-full rounded-full bg-gradient-to-r from-sky-500 to-blue-600" style={{ width: `${Math.min(stats.ats_score, 100)}%` }} />
              </div>
            </div>
            <div>
              <div className="mb-2 flex justify-between text-sm text-slate-500">
                <span>Role fit</span>
                <span>{stats.skill_match_pct}%</span>
              </div>
              <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
                <div className="h-full rounded-full bg-gradient-to-r from-brand-500 to-emerald-600" style={{ width: `${Math.min(stats.skill_match_pct, 100)}%` }} />
              </div>
            </div>
            <div>
              <div className="mb-2 flex justify-between text-sm text-slate-500">
                <span>Roadmap completion</span>
                <span>{stats.roadmap_progress}%</span>
              </div>
              <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
                <div className="h-full rounded-full bg-gradient-to-r from-violet-500 to-purple-600" style={{ width: `${Math.min(stats.roadmap_progress, 100)}%` }} />
              </div>
            </div>
          </div>
        </div>

        <div className="panel-card">
          <div className="mb-5 flex items-center justify-between">
            <div className="section-title">Your next step</div>
            <Gauge className="h-5 w-5 text-brand-600" />
          </div>
          <div className="rounded-2xl border border-brand-100 bg-brand-50 p-4">
            <div className="text-xs font-bold uppercase tracking-[0.14em] text-brand-700">Recommended action</div>
            <div className="mt-2 text-xl font-extrabold text-slate-900">{actionLabel}</div>
            <p className="mt-2 text-sm text-slate-600">
              You are currently at <span className="font-semibold text-slate-800">{journey.nextStage.label}</span>. Complete this step to move the rest of your placement journey forward.
            </p>
            <Link to={journey.nextStage.path} className="mt-4 inline-flex items-center gap-2 text-sm font-bold text-brand-700">
              Continue <ArrowRight size={16} />
            </Link>
          </div>
        </div>
      </div>
    </motion.div>
  );
}