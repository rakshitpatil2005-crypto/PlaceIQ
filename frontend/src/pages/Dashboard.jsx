import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Activity, Target, BookOpen, FileText } from 'lucide-react';
import api from '../api';

export default function Dashboard() {
  const [stats, setStats] = useState({
    ats_score: 0,
    total_skills_extracted: 0,
    skill_match_pct: 0,
    target_role: 'Loading...',
    roadmap_progress: 0
  });

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const { data } = await api.get('/dashboard/stats');
        setStats(data);
      } catch (err) {
        console.error("Failed to load dashboard stats", err);
      }
    };
    fetchStats();
  }, []);

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="max-w-6xl mx-auto space-y-6">
      
      <div className="bg-white p-8 rounded-2xl border border-gray-100 shadow-sm">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Welcome to PlaceIQ</h1>
        <p className="text-gray-500">Here is your live placement readiness overview.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        
        {/* ATS Score Card */}
        <div className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm flex flex-col items-center justify-center text-center">
          <div className="p-3 bg-blue-50 text-blue-600 rounded-full mb-4">
            <FileText size={24} />
          </div>
          <p className="text-sm font-medium text-gray-500 mb-1">Latest ATS Score</p>
          <h3 className="text-3xl font-bold text-gray-900">{stats.ats_score}<span className="text-lg text-gray-400">/100</span></h3>
        </div>

        {/* Skill Match Card */}
        <div className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm flex flex-col items-center justify-center text-center">
          <div className="p-3 bg-green-50 text-green-600 rounded-full mb-4">
            <Target size={24} />
          </div>
          <p className="text-sm font-medium text-gray-500 mb-1">Skill Match for {stats.target_role}</p>
          <h3 className="text-3xl font-bold text-green-600">{stats.skill_match_pct}%</h3>
        </div>

        {/* Roadmap Progress Card */}
        <div className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm flex flex-col items-center justify-center text-center">
          <div className="p-3 bg-purple-50 text-purple-600 rounded-full mb-4">
            <Activity size={24} />
          </div>
          <p className="text-sm font-medium text-gray-500 mb-1">Roadmap Progress</p>
          <h3 className="text-3xl font-bold text-purple-600">{stats.roadmap_progress}%</h3>
        </div>

        {/* Total Skills Card */}
        <div className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm flex flex-col items-center justify-center text-center">
          <div className="p-3 bg-brand-50 text-brand-600 rounded-full mb-4">
            <BookOpen size={24} />
          </div>
          <p className="text-sm font-medium text-gray-500 mb-1">Total Verified Skills</p>
          <h3 className="text-3xl font-bold text-gray-900">{stats.total_skills_extracted}</h3>
        </div>

      </div>
    </motion.div>
  );
}