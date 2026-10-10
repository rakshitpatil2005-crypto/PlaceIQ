import { useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { UploadCloud, FileText, CheckCircle, AlertCircle, Sparkles, Target, TrendingUp } from 'lucide-react';
import api from '../api';
import { runSingleFlight } from '../utils/singleFlight';

export default function ResumeUpload() {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const uploadInFlight = useRef(false);

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    return runSingleFlight(uploadInFlight, async () => {
      setLoading(true);
      setError('');

      try {
        const { data } = await api.post('/resume/upload', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
        setResult(data.data);
      } catch (err) {
        const detail = err.response?.data?.detail || 'Failed to analyze resume.';
        const retryAfter = Number(err.response?.headers?.['retry-after']);
        setError(
          retryAfter > 0
            ? `${detail} Try again in about ${Math.ceil(retryAfter)} seconds.`
            : detail,
        );
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
            <UploadCloud size={12} />
            Resume intelligence
          </div>
          <h2 className="page-title">Upload your resume</h2>
          <p className="page-subtitle mt-2">AI extracts skills, validates your resume strength, and prepares your profile for detailed placement analysis.</p>
        </div>
      </div>

      <div className="panel-card mx-auto max-w-4xl p-8 text-center">
        <form onSubmit={handleUpload} className="mx-auto max-w-xl">
          <div className="mb-6 flex items-center justify-center">
            <label className="flex h-40 w-full cursor-pointer flex-col items-center justify-center rounded-[1.75rem] border-2 border-dashed border-slate-300 bg-slate-50/80 transition-all duration-300 hover:border-brand-400 hover:bg-brand-50/50">
              <div className="flex flex-col items-center justify-center gap-3">
                <div className="inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-white text-brand-600 shadow-sm">
                  <FileText size={28} />
                </div>
                <div className="text-center">
                  <p className="text-lg font-semibold text-slate-700">{file ? file.name : 'Choose a PDF resume'}</p>
                  <p className="text-sm text-slate-500">Accepted format: PDF</p>
                </div>
              </div>
              <input type="file" className="hidden" accept=".pdf" onChange={(e) => setFile(e.target.files[0])} />
            </label>
          </div>

          {error && (
            <div className="auth-error mb-4 text-left">
              <AlertCircle size={18} />
              <span>{error}</span>
            </div>
          )}

          <button type="submit" disabled={!file || loading} className="btn-modern w-full">
            {loading ? <span className="animate-pulse">Analyzing with AI...</span> : 'Analyze resume'}
          </button>
        </form>
      </div>

      {result && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="grid gap-6 md:grid-cols-3">
          <div className="panel-card flex flex-col items-center justify-center text-center">
            <div className="mb-4 inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
              <Target size={28} />
            </div>
            <p className="text-sm font-medium text-slate-500">ATS score</p>
            <div className="mt-2 flex items-end gap-2">
              <span className="text-5xl font-black tracking-tight text-slate-900">{result.ats_score}</span>
              <span className="pb-2 text-sm font-semibold text-slate-400">/100</span>
            </div>
          </div>

          <div className="panel-card md:col-span-2">
            <div className="mb-4 flex items-center gap-2 text-slate-900">
              <Sparkles size={18} className="text-amber-500" />
              <h3 className="text-lg font-bold">AI suggestions</h3>
            </div>
            <ul className="space-y-3">
              {result.suggestions?.map((sugg, i) => (
                <li key={i} className="flex items-start gap-3 rounded-2xl bg-slate-50 p-3 text-sm text-slate-600">
                  <TrendingUp size={18} className="mt-0.5 shrink-0 text-brand-600" />
                  <span>{sugg}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="panel-card md:col-span-3">
            <div className="mb-4 flex items-center gap-2 text-slate-900">
              <CheckCircle size={18} className="text-brand-600" />
              <h3 className="text-lg font-bold">Extracted skills</h3>
            </div>
            <div className="flex flex-wrap gap-2">
              {result.skills?.map((skill, i) => (
                <span key={i} className="rounded-full border border-brand-100 bg-brand-50 px-3 py-1.5 text-sm font-semibold text-brand-700">
                  {skill}
                </span>
              ))}
            </div>
          </div>
        </motion.div>
      )}
    </motion.div>
  );
}