import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Map, CheckCircle2, Circle, Loader, AlertCircle, Sparkles, CheckSquare } from 'lucide-react';
import api from '../api';
import RoadmapLearningLink from '../components/RoadmapLearningLink.js';
import { getAdaptivePriorityDisplay } from '../utils/adaptivePriority.js';

export default function Roadmap() {
  const [roadmap, setRoadmap] = useState(null);
  const [loading, setLoading] = useState(false);
  const [adapting, setAdapting] = useState(false);
  const [adaptationMessage, setAdaptationMessage] = useState('');
  const [error, setError] = useState('');
  const [learningMappings, setLearningMappings] = useState({});
  const [mappingError, setMappingError] = useState('');
  const [selectedRole, setSelectedRole] = useState('Embedded Systems Engineer');

  const ROLES = [
    "Embedded Systems Engineer",
    "Backend Developer",
    "Frontend Developer",
    "Full Stack Developer",
    "Data Analyst",
    "ML Engineer",
    "Data Scientist",
    "DevOps Engineer",
    "Cloud Engineer",
    "Software Engineer",
    "Cybersecurity Analyst"
  ];

  const applyLearningMappings = (data) => {
    const mappings = {};
    (data.mappings || []).forEach(({ week_index, task_index, skill_id }) => {
      mappings[`${week_index}-${task_index}`] = skill_id;
    });
    setLearningMappings(mappings);
    setMappingError('');
  };

  const fetchLearningMappings = async () => {
    try {
      const { data } = await api.get('/learning/roadmap-mappings');
      applyLearningMappings(data);
    } catch {
      setLearningMappings({});
      setMappingError('Learning links could not be loaded. Your roadmap is still available.');
    }
  };

  useEffect(() => {
    let active = true;
    const loadRoadmap = async () => {
      const [roadmapResult, mappingsResult] = await Promise.allSettled([
        api.get('/roadmap'),
        api.get('/learning/roadmap-mappings'),
      ]);
      if (!active) return;

      if (roadmapResult.status === 'fulfilled') {
        if (roadmapResult.value.data) setRoadmap(roadmapResult.value.data);
      } else {
        console.error('Failed to load roadmap.', roadmapResult.reason);
      }

      if (mappingsResult.status === 'fulfilled') {
        applyLearningMappings(mappingsResult.value.data);
      } else {
        setMappingError('Learning links could not be loaded. Your roadmap is still available.');
      }
    };
    loadRoadmap();
    return () => {
      active = false;
    };
  }, []);

  const handleGenerate = async () => {
    setLoading(true);
    setError('');
    try {
      const { data } = await api.post('/roadmap/generate', { target_role: selectedRole });
      setRoadmap(data);
      setLearningMappings({});
      await fetchLearningMappings();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to generate roadmap.');
    } finally {
      setLoading(false);
    }
  };

  const handleAdapt = async () => {
    setAdapting(true);
    setError('');
    setAdaptationMessage('');
    try {
      const { data } = await api.post('/roadmap/adapt');
      setRoadmap(data.roadmap);
      setAdaptationMessage(data.message);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to adapt roadmap priorities.');
    } finally {
      setAdapting(false);
    }
  };

  const toggleTask = async (weekIndex, taskIndex) => {
    if (!roadmap || !roadmap.weeks) return;

    // Optimistic UI state update
    const updatedRoadmap = JSON.parse(JSON.stringify(roadmap));
    const targetTask = updatedRoadmap.weeks[weekIndex].tasks[taskIndex];
    const newCompletedState = !targetTask.completed;
    targetTask.completed = newCompletedState;
    setRoadmap(updatedRoadmap);

    // Persist completion state to SQLite backend
    try {
      await api.post('/roadmap/task/toggle', {
        week_index: weekIndex,
        task_index: taskIndex,
        completed: newCompletedState
      });
    } catch (err) {
      console.error("Failed to save task completion:", err);
      try {
        const { data } = await api.get('/roadmap');
        setRoadmap(data);
      } catch (refreshError) {
        console.error('Failed to refresh roadmap after a task update error.', refreshError);
        setRoadmap(roadmap);
      }
    }
  };

  // Helper to compute overall progress statistics
  const getProgressStats = () => {
    if (!roadmap || !roadmap.weeks) return { total: 0, completed: 0, pct: 0 };
    let total = 0;
    let completed = 0;
    roadmap.weeks.forEach(w => {
      (w.tasks || []).forEach(t => {
        total++;
        if (t.completed) completed++;
      });
    });
    const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
    return { total, completed, pct };
  };

  const stats = getProgressStats();

  // Helper to parse and highlight task tag (REVISE vs LEARN vs PROJECT)
  const getTaskTagBadge = (taskText) => {
    if (taskText.includes('[REVISE]')) {
      return <span className="bg-amber-100 text-amber-800 text-xs font-semibold px-2 py-0.5 rounded border border-amber-200">Syllabus Revise</span>;
    }
    if (taskText.includes('[LEARN]')) {
      return <span className="bg-purple-100 text-purple-800 text-xs font-semibold px-2 py-0.5 rounded border border-purple-200">Learn from Scratch</span>;
    }
    if (taskText.includes('[PROJECT') || taskText.includes('[MOCK')) {
      return <span className="bg-emerald-100 text-emerald-800 text-xs font-semibold px-2 py-0.5 rounded border border-emerald-200">Project & Placement</span>;
    }
    return <span className="bg-blue-100 text-blue-800 text-xs font-semibold px-2 py-0.5 rounded border border-blue-200">Study Task</span>;
  };

  // Clean task text by removing type tags for display
  const cleanTaskText = (taskText) => {
    return taskText.replace(/\[(REVISE|LEARN|PROJECT & RESUME|MOCK PREP|PROJECT|PRACTICE|STUDY)\]\s*/g, '');
  };

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="max-w-5xl mx-auto space-y-6">
      
      {/* Top Header & Role Selector */}
      <div className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm flex flex-col md:flex-row justify-between items-center gap-4">
        <div>
          <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            <Map className="text-brand-500" />
            Personalized 6-Week Learning Roadmap
          </h2>
          <p className="text-sm text-gray-500">VTU curriculum-aligned learning plan prioritizing missing skills & prerequisites.</p>
        </div>
        
        <div className="flex flex-col sm:flex-row gap-3 w-full md:w-auto">
          <select 
            value={selectedRole}
            onChange={(e) => setSelectedRole(e.target.value)}
            className="input-modern"
          >
            {ROLES.map(role => (
              <option key={role} value={role}>{role}</option>
            ))}
          </select>

          <button onClick={handleGenerate} disabled={loading} className="btn-modern whitespace-nowrap min-w-[160px] flex justify-center items-center gap-2">
            {loading ? <Loader className="animate-spin" size={20} /> : <><Sparkles size={18} /> Generate Plan</>}
          </button>
          <button
            onClick={handleAdapt}
            disabled={adapting || loading || !roadmap}
            className="whitespace-nowrap min-h-11 rounded-xl border border-brand-200 bg-brand-50 px-4 py-2 text-sm font-semibold text-brand-800 transition hover:bg-brand-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {adapting ? 'Adapting…' : 'Adapt future priorities'}
          </button>
        </div>
      </div>

      {adaptationMessage && (
        <p className="rounded-xl border border-brand-100 bg-brand-50 p-3 text-sm text-brand-800" role="status">
          {adaptationMessage}
        </p>
      )}

      {error && (
        <div className="bg-red-50 text-red-600 p-4 rounded-xl flex items-center gap-2 border border-red-100">
          <AlertCircle size={20} /> {error}
        </div>
      )}

      {/* Progress Bar Card */}
      {roadmap && (
        <div className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm space-y-3">
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-2 text-gray-800 font-semibold">
              <CheckSquare className="text-brand-500" size={20} />
              <span>Roadmap Completion Progress</span>
            </div>
            <span className="text-sm font-bold text-brand-600 bg-brand-50 px-3 py-1 rounded-full">
              {stats.completed} of {stats.total} Tasks ({stats.pct}%)
            </span>
          </div>
          
          <div className="w-full bg-gray-100 h-3 rounded-full overflow-hidden">
            <div 
              className="bg-brand-500 h-full rounded-full transition-all duration-500 ease-out" 
              style={{ width: `${stats.pct}%` }}
            />
          </div>
        </div>
      )}

      {/* 6-Week Roadmap Timeline Cards */}
      {roadmap && (
        <div className="space-y-6">
          {roadmap.weeks.map((weekData, wIdx) => (
            <motion.div 
              initial={{ opacity: 0, x: -20 }} 
              animate={{ opacity: 1, x: 0 }} 
              transition={{ delay: wIdx * 0.08 }}
              key={wIdx} 
              className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm space-y-4"
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-gray-100 pb-4 gap-2">
                <div className="flex items-center gap-3">
                  <span className="bg-brand-600 text-white text-sm font-bold px-3.5 py-1.5 rounded-xl shadow-sm">
                    Week {weekData.week}
                  </span>
                  <h3 className="text-lg font-semibold text-gray-800">{weekData.theme}</h3>
                </div>
                <span className="text-xs text-gray-400 font-medium">
                  {weekData.tasks.filter(t => t.completed).length} / {weekData.tasks.length} Done
                </span>
              </div>
              
              <div className="space-y-3">
                {weekData.tasks.map((task, tIdx) => (
                  <div 
                    key={tIdx} 
                    onClick={() => toggleTask(wIdx, tIdx)}
                    className={`flex items-start gap-3.5 p-4 rounded-xl cursor-pointer transition-all border ${
                      task.completed ? 'bg-green-50/40 border-green-200' : 'bg-white hover:bg-gray-50/80 border-gray-100 shadow-2xs'
                    }`}
                  >
                    <div className="mt-0.5 shrink-0">
                      {task.completed ? (
                        <CheckCircle2 className="text-green-500 fill-green-50" size={22} />
                      ) : (
                        <Circle className="text-gray-300 hover:text-gray-400" size={22} />
                      )}
                    </div>
                    
                    <div className="space-y-1.5 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        {getTaskTagBadge(task.task)}
                        <span className={`text-sm font-medium ${task.completed ? 'text-gray-500 line-through' : 'text-gray-800'}`}>
                          {cleanTaskText(task.task)}
                        </span>
                      </div>
                      {learningMappings[`${wIdx}-${tIdx}`] && (
                        <RoadmapLearningLink skillId={learningMappings[`${wIdx}-${tIdx}`]} />
                      )}
                      {!task.completed && task.adaptive && (
                        (() => {
                          const priorityDisplay = getAdaptivePriorityDisplay(
                            task.adaptive.evidence_category,
                          );
                          if (!priorityDisplay) return null;
                          return (
                            <div className={`mt-2 space-y-1 rounded-lg border p-3 text-xs ${priorityDisplay.className}`}>
                              <p className="font-semibold">
                                Priority {task.adaptive.priority}: {priorityDisplay.label}
                              </p>
                              <p>{task.adaptive.reason}</p>
                              {task.adaptive.evidence?.map((item) => (
                                <p key={item}>{item}</p>
                              ))}
                              {task.adaptive.context?.vtu_subjects?.length > 0 && (
                                <p>
                                  VTU context: {task.adaptive.context.vtu_subjects.join(', ')}
                                </p>
                              )}
                            </div>
                          );
                        })()
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          ))}
        </div>
      )}

      {mappingError && (
        <p className="text-sm text-amber-700" role="status">{mappingError}</p>
      )}
    </motion.div>
  );
}