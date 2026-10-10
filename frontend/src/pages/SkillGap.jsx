import { useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { Target, CheckCircle2, AlertCircle, XCircle, Sparkles, ArrowRight } from 'lucide-react';
import api from '../api';
import { runSingleFlight } from '../utils/singleFlight';

export default function SkillGap() {
  const [role, setRole] = useState('Embedded Systems Engineer');
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState(null);
  const [error, setError] = useState('');
  const analysisInFlight = useRef(false);

  const analyzeGap = async () => {
    return runSingleFlight(analysisInFlight, async () => {
      setLoading(true);
      setError('');
      try {
        const { data } = await api.post('/gap/analyze', { target_role: role });
        setReport(data);
      } catch (err) {
        setError(err.response?.data?.detail || 'Analysis failed. Please upload a resume first.');
      } finally {
        setLoading(false);
      }
    });
  };

  return (
    <motion.div initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <div className="page-header">
        <div>
          <div className="soft-label mb-3">
            <Target size={12} />
            Skill intelligence
          </div>
          <h2 className="page-title">Target role analysis</h2>
          <p className="page-subtitle mt-2">Select your ideal role to compare your profile against VTU curriculum coverage and missing placement skills.</p>
        </div>

        <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row">
          <select value={role} onChange={(e) => setRole(e.target.value)} className="input-modern min-w-[240px]">
            <option value="Embedded Systems Engineer">Embedded Systems Engineer</option>
            <option value="Backend Developer">Backend Developer</option>
            <option value="Frontend Developer">Frontend Developer</option>
            <option value="Data Analyst">Data Analyst</option>
            <option value="Full Stack Developer">Full Stack Developer</option>
            <option value="ML Engineer">ML Engineer</option>
          </select>
          <button onClick={analyzeGap} disabled={loading} className="btn-modern whitespace-nowrap">
            {loading ? 'Analyzing...' : 'Run gap analysis'}
            {!loading && <ArrowRight size={16} />}
          </button>
        </div>
      </div>

      {error && (
        <div className="auth-error">
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      {report && (
        <div className="space-y-6">
          <div className="panel-card text-center">
            <div className="text-sm font-bold uppercase tracking-[0.18em] text-slate-500">Overall match for {report.target_role}</div>
            <div className="mt-3 text-6xl font-black tracking-tight text-brand-600">{report.skill_match_pct}%</div>
          </div>

          <div className="grid gap-6 md:grid-cols-3">
            <div className="panel-card md:col-span-1">
              <div className="mb-4 flex items-center gap-2 text-slate-900">
                <CheckCircle2 className="text-blue-500" size={20} />
                <h3 className="text-lg font-bold">VTU coverage & resume fit</h3>
              </div>
              <div className="space-y-3">
                {report.covered_by_syllabus?.map((item, i) => (
                  <div key={i} className="rounded-2xl border border-blue-100 bg-blue-50/60 p-3">
                    <div className="font-semibold text-blue-900">{item.skill}</div>
                    <div className="mt-1 text-[10px] font-bold uppercase tracking-[0.14em] text-blue-700">{item.status}</div>
                  </div>
                ))}
                {report.from_resume?.map((skill, i) => (
                  <div key={`resume-${i}`} className="rounded-2xl border border-emerald-100 bg-emerald-50/70 p-3">
                    <div className="font-semibold text-emerald-900">{skill}</div>
                    <div className="mt-1 text-[10px] font-bold uppercase tracking-[0.14em] text-emerald-700">Resume match</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="panel-card md:col-span-2">
              <div className="mb-4 flex items-center gap-2 text-slate-900">
                <XCircle className="text-red-500" size={20} />
                <h3 className="text-lg font-bold">Critical missing skills</h3>
              </div>
              <p className="mb-4 text-sm text-slate-500">These are the gaps that still need attention for this target role.</p>
              <div className="grid gap-3 sm:grid-cols-2">
                {report.missing?.map((item, i) => (
                  <div key={i} className="flex items-center gap-3 rounded-2xl border border-red-100 bg-red-50 p-3">
                    <AlertCircle size={18} className="text-red-500" />
                    <span className="font-medium text-red-900">{item.skill}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {!report && !error && (
        <div className="panel-card text-center text-slate-500">
          <div className="inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-100 text-slate-600">
            <Sparkles size={24} />
          </div>
          <p className="mt-4 text-lg font-semibold text-slate-700">No report generated yet</p>
          <p className="mt-1 text-sm text-slate-500">Choose a target role and run analysis to build your skills gap report.</p>
        </div>
      )}
    </motion.div>
  );
}