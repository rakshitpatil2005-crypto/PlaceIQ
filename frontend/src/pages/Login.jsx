import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Mail, Lock, User, BookOpen, GraduationCap, ArrowRight, Sparkles, TrendingUp, Briefcase, ShieldCheck } from 'lucide-react';
import api from '../api';
import { SUPPORTED_ROLES } from '../data/roles';

export default function Login() {
  const navigate = useNavigate();
  const [isLogin, setIsLogin] = useState(true);
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    password: '',
    branch: 'CSE',
    semester: '5',
    target_role: SUPPORTED_ROLES[0],
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      if (isLogin) {
        const { data } = await api.post('/auth/login', {
          email: formData.email,
          password: formData.password,
        });
        localStorage.setItem('token', data.access_token);
        navigate('/dashboard');
        return;
      }

      const registerPayload = {
        name: formData.name,
        email: formData.email,
        password: formData.password,
        branch: formData.branch,
        semester: Number(formData.semester) || 1,
      };

      await api.post('/auth/register', registerPayload);

      const loginRes = await api.post('/auth/login', {
        email: formData.email,
        password: formData.password,
      });

      localStorage.setItem('token', loginRes.data.access_token);

      await api.put('/auth/me/profile', {
        branch: formData.branch,
        semester: Number(formData.semester) || 1,
        target_role: formData.target_role,
      });

      navigate('/dashboard');
    } catch (err) {
      setError(err.response?.data?.detail || 'Authentication failed');
    } finally {
      setLoading(false);
    }
  };

  const visualFeatures = [
    { icon: TrendingUp, title: 'Placement readiness', text: 'Track your real-time score' },
    { icon: Briefcase, title: 'Tailored roadmap', text: 'AI built around your VTU gaps' },
    { icon: ShieldCheck, title: 'Interview confidence', text: 'Practice with structured feedback' },
  ];

  return (
    <div className="auth-shell">
      <motion.div initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} className="auth-panel">
        <div className="auth-visual">
          <div className="auth-badge">
            <Sparkles size={14} />
            Built for VTU 2025
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.8rem', marginTop: '1.25rem' }}>
            <div className="brand-mark" style={{ width: '3.1rem', height: '3.1rem' }}>
              <GraduationCap size={24} />
            </div>
            <span style={{ fontSize: '1.7rem', fontWeight: 800, letterSpacing: '-0.05em', color: '#0f172a' }}>PlaceIQ</span>
          </div>

          <h1>Turn your degree into a placement advantage.</h1>
          <p>
            Discover missing skills, build your roadmap, practice interviews, and monitor your readiness with a premium placement intelligence dashboard built for engineering students.
          </p>

          <div className="auth-feature-grid">
            {visualFeatures.map(({ icon: Icon, title, text }) => (
              <div key={title} className="auth-feature">
                <div className="auth-feature-icon">
                  <Icon size={18} />
                </div>
                <div>
                  <strong>{title}</strong>
                  <span>{text}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="auth-card">
          <div className="auth-card-inner">
            <div className="text-center mb-6">
              <div className="inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-50 text-brand-600 shadow-sm mb-4">
                <GraduationCap size={28} />
              </div>
              <h2 className="text-3xl font-black tracking-tight text-slate-900">
                {isLogin ? 'Welcome back' : 'Create account'}
              </h2>
              <p className="mt-2 text-sm text-slate-500">
                {isLogin ? 'Sign in to continue your placement journey.' : 'Set up your profile and target role to personalize your roadmap.'}
              </p>
            </div>

            {error && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="auth-error mb-4">
                <span>⚠</span>
                <span>{error}</span>
              </motion.div>
            )}

            <form onSubmit={handleSubmit} className="auth-form">
              <AnimatePresence mode="wait">
                {!isLogin && (
                  <motion.div
                    key="signup"
                    initial={{ opacity: 0, height: 0, marginTop: 0 }}
                    animate={{ opacity: 1, height: 'auto', marginTop: 0 }}
                    exit={{ opacity: 0, height: 0, marginTop: 0 }}
                    className="overflow-hidden"
                  >
                    <div className="form-field">
                      <User size={18} />
                      <input
                        type="text"
                        placeholder="Full name"
                        value={formData.name}
                        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                        required
                      />
                    </div>

                    <div className="form-row" style={{ marginTop: '0.9rem' }}>
                      <div className="form-field">
                        <BookOpen size={18} />
                        <select value={formData.branch} onChange={(e) => setFormData({ ...formData, branch: e.target.value })}>
                          <option value="CSE">CSE</option>
                          <option value="ISE">ISE</option>
                          <option value="ECE">ECE</option>
                        </select>
                      </div>

                      <div className="form-field">
                        <input
                          type="number"
                          min="1"
                          max="8"
                          value={formData.semester}
                          placeholder="Semester"
                          onChange={(e) => setFormData({ ...formData, semester: e.target.value })}
                          required
                        />
                      </div>
                    </div>

                    <div className="form-field" style={{ marginTop: '0.9rem' }}>
                      <GraduationCap size={18} />
                      <select value={formData.target_role} onChange={(e) => setFormData({ ...formData, target_role: e.target.value })}>
                        {SUPPORTED_ROLES.map((role) => (
                          <option key={role} value={role}>{role}</option>
                        ))}
                      </select>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              <div className="form-field">
                <Mail size={18} />
                <input
                  type="email"
                  placeholder="Email address"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  required
                />
              </div>

              <div className="form-field">
                <Lock size={18} />
                <input
                  type="password"
                  placeholder="Password"
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  required
                />
              </div>

              <button type="submit" disabled={loading} className="btn-modern auth-cta">
                {loading ? 'Processing...' : isLogin ? 'Sign in' : 'Create account'}
                {!loading && <ArrowRight size={18} />}
              </button>
            </form>

            <div className="auth-secondary">
              <span>{isLogin ? 'Need an account?' : 'Already a member?'}</span>{' '}
              <button type="button" onClick={() => setIsLogin(!isLogin)}>
                {isLogin ? 'Register now' : 'Sign in'}
              </button>
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );
}