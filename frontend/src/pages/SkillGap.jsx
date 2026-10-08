import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Target, CheckCircle2, AlertCircle, XCircle } from 'lucide-react';
import api from '../api';

export default function SkillGap() {
  const [role, setRole] = useState('Embedded Systems Engineer');
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState(null);
  const [error, setError] = useState('');

  // Auto-fetch if there's a stored target role or just default to selection
  const analyzeGap = async () => {
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
  };

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="max-w-6xl mx-auto space-y-6">
      
      <div className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm flex flex-col md:flex-row justify-between items-center gap-4">
        <div>
          <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            <Target className="text-brand-500" /> Target Role Analysis
          </h2>
          <p className="text-sm text-gray-500">Select your dream role to generate a VTU-aware skill gap report.</p>
        </div>
        
        <div className="flex w-full md:w-auto gap-2">
          <select 
            value={role} 
            onChange={(e) => setRole(e.target.value)}
            className="px-4 py-2 border rounded-lg focus:ring-2 focus:ring-brand-500 outline-none bg-gray-50"
          >
            <option value="Embedded Systems Engineer">Embedded Systems Engineer</option>
            <option value="Backend Developer">Backend Developer</option>
            <option value="Frontend Developer">Frontend Developer</option>
            <option value="Data Analyst">Data Analyst</option>
            <option value="Full Stack Developer">Full Stack Developer</option>
            <option value="ML Engineer">ML Engineer</option>
          </select>
          <button onClick={analyzeGap} disabled={loading} className="btn-modern whitespace-nowrap">
            {loading ? 'Analyzing...' : 'Run Gap Analysis'}
          </button>
        </div>
      </div>

      {error && <div className="bg-red-50 text-red-600 p-4 rounded-xl text-center border border-red-100">{error}</div>}

      {report && (
        <div className="space-y-6">
          <div className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm text-center">
            <h3 className="text-lg font-semibold text-gray-500">Overall Match for {report.target_role}</h3>
            <div className="text-6xl font-black text-brand-600 mt-2">{report.skill_match_pct}%</div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* VTU Syllabus Column */}
            <div className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm">
              <h3 className="font-bold text-gray-900 flex items-center gap-2 mb-4 border-b pb-2">
                <CheckCircle2 className="text-blue-500" /> VTU Syllabus / Found
              </h3>
              <ul className="space-y-3">
                {report.covered_by_syllabus?.map((item, i) => (
                  <li key={i} className="flex flex-col bg-blue-50/50 p-2 rounded-lg">
                    <span className="font-medium text-blue-900">{item.skill}</span>
                    <span className="text-xs text-blue-600 uppercase font-semibold">{item.status}</span>
                  </li>
                ))}
                {report.from_resume?.map((skill, i) => (
                  <li key={`res-${i}`} className="flex flex-col bg-green-50 p-2 rounded-lg">
                    <span className="font-medium text-green-900">{skill}</span>
                    <span className="text-xs text-green-600 uppercase font-semibold">Self-Taught (On Resume)</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Missing Column */}
            <div className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm md:col-span-2">
              <h3 className="font-bold text-gray-900 flex items-center gap-2 mb-4 border-b pb-2">
                <XCircle className="text-red-500" /> Critical Missing Skills
              </h3>
              <p className="text-sm text-gray-500 mb-4">These skills are required for the role but were neither in your college syllabus nor on your resume.</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {report.missing?.map((item, i) => (
                  <div key={i} className="flex items-center gap-3 bg-red-50 border border-red-100 p-3 rounded-lg">
                    <AlertCircle size={18} className="text-red-500" />
                    <span className="font-medium text-red-900">{item.skill}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </motion.div>
  );
}