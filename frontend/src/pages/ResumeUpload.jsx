import { useState } from 'react';
import { motion } from 'framer-motion';
import { UploadCloud, FileText, CheckCircle, AlertCircle, Sparkles } from 'lucide-react';
import api from '../api';

export default function ResumeUpload() {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!file) return;
    
    const formData = new FormData();
    formData.append('file', file);

    setLoading(true);
    setError('');
    
    try {
      const { data } = await api.post('/resume/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setResult(data.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to analyze resume.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="max-w-4xl mx-auto space-y-6">
      <div className="bg-white p-8 rounded-2xl border border-gray-100 shadow-sm text-center">
        <div className="inline-flex items-center justify-center w-16 h-16 bg-brand-50 text-brand-600 rounded-full mb-4">
          <UploadCloud size={32} />
        </div>
        <h2 className="text-2xl font-bold text-gray-900">Upload Your Resume</h2>
        <p className="text-gray-500 mt-2 mb-6">Our AI will extract your skills and calculate your base ATS score.</p>
        
        <form onSubmit={handleUpload} className="max-w-md mx-auto">
          <div className="flex items-center justify-center w-full mb-4">
            <label className="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed rounded-xl cursor-pointer bg-gray-50 border-gray-300 hover:bg-gray-100 transition-colors">
              <div className="flex flex-col items-center justify-center pt-5 pb-6">
                <FileText className="w-8 h-8 text-gray-400 mb-2" />
                <p className="text-sm text-gray-500 font-medium">
                  {file ? file.name : "Click to select a PDF"}
                </p>
              </div>
              <input type="file" className="hidden" accept=".pdf" onChange={(e) => setFile(e.target.files[0])} />
            </label>
          </div>
          
          {error && <p className="text-red-500 text-sm mb-4 bg-red-50 p-2 rounded-lg">{error}</p>}
          
          <button type="submit" disabled={!file || loading} className="w-full btn-modern disabled:opacity-50 flex items-center justify-center gap-2">
            {loading ? <span className="animate-pulse">Analyzing with AI...</span> : 'Analyze Resume'}
          </button>
        </form>
      </div>

      {result && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="col-span-1 bg-white p-6 rounded-2xl border border-gray-100 shadow-sm flex flex-col items-center justify-center text-center">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">ATS Score</h3>
            <div className="text-5xl font-extrabold text-brand-600">{result.ats_score}</div>
            <p className="text-sm text-gray-500 mt-2">Out of 100</p>
          </div>
          
          <div className="col-span-1 md:col-span-2 bg-white p-6 rounded-2xl border border-gray-100 shadow-sm">
            <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
              <Sparkles size={20} className="text-amber-500"/> AI Suggestions
            </h3>
            <ul className="space-y-3">
              {result.suggestions?.map((sugg, i) => (
                <li key={i} className="flex items-start gap-3 text-gray-600 bg-gray-50 p-3 rounded-lg">
                  <AlertCircle size={18} className="text-brand-500 shrink-0 mt-0.5" />
                  <span className="text-sm">{sugg}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="col-span-1 md:col-span-3 bg-white p-6 rounded-2xl border border-gray-100 shadow-sm">
            <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
              <CheckCircle size={20} className="text-brand-500"/> Extracted Skills
            </h3>
            <div className="flex flex-wrap gap-2">
              {result.skills?.map((skill, i) => (
                <span key={i} className="px-3 py-1 bg-brand-50 text-brand-700 text-sm font-medium rounded-full border border-brand-100">
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