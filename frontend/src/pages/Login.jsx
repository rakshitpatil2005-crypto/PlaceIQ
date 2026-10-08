import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Mail, Lock, User, BookOpen, GraduationCap, ArrowRight } from 'lucide-react';
import api from '../api';

export default function Login() {
  const navigate = useNavigate();
  const [isLogin, setIsLogin] = useState(true);
  const [formData, setFormData] = useState({ name: '', email: '', password: '', branch: 'CSE', semester: 5 });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const endpoint = isLogin ? '/auth/login' : '/auth/register';
      const payload = isLogin ? { email: formData.email, password: formData.password } : formData;
      const { data } = await api.post(endpoint, payload);
      localStorage.setItem('token', data.access_token);
      navigate('/dashboard');
    } catch (err) {
      setError(err.response?.data?.detail || 'Authentication failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-brand-50 to-emerald-100 p-4">
      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md bg-white rounded-2xl shadow-xl overflow-hidden border border-gray-100"
      >
        <div className="p-8">
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-12 h-12 bg-brand-100 rounded-xl mb-4 text-brand-600">
              <GraduationCap size={28} />
            </div>
            <h2 className="text-3xl font-bold text-gray-900">PlaceIQ</h2>
            <p className="text-gray-500 mt-2">{isLogin ? 'Welcome back, future engineer.' : 'Start your placement journey.'}</p>
          </div>

          {error && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mb-4 p-3 bg-red-50 text-red-600 text-sm rounded-lg text-center">
              {error}
            </motion.div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <AnimatePresence mode="popLayout">
              {!isLogin && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="space-y-4 overflow-hidden"
                >
                  <div className="relative">
                    <User className="absolute left-3 top-3 text-gray-400" size={20} />
                    <input type="text" placeholder="Full Name" required={!isLogin} className="w-full pl-10 pr-4 py-2 border rounded-lg focus:ring-2 focus:ring-brand-500 outline-none" onChange={e => setFormData({...formData, name: e.target.value})} />
                  </div>
                  <div className="flex gap-4">
                    <div className="relative flex-1">
                      <BookOpen className="absolute left-3 top-3 text-gray-400" size={20} />
                      <select className="w-full pl-10 pr-4 py-2 border rounded-lg focus:ring-2 focus:ring-brand-500 appearance-none bg-white" onChange={e => setFormData({...formData, branch: e.target.value})}>
                        <option value="CSE">CSE</option>
                        <option value="ISE">ISE</option>
                        <option value="ECE">ECE</option>
                      </select>
                    </div>
                    <div className="relative flex-1">
                      <input type="number" min="1" max="8" placeholder="Sem (1-8)" required={!isLogin} className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-brand-500 outline-none" onChange={e => setFormData({...formData, semester: parseInt(e.target.value)})} />
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            <div className="relative">
              <Mail className="absolute left-3 top-3 text-gray-400" size={20} />
              <input type="email" placeholder="Email Address" required className="w-full pl-10 pr-4 py-2 border rounded-lg focus:ring-2 focus:ring-brand-500 outline-none" onChange={e => setFormData({...formData, email: e.target.value})} />
            </div>

            <div className="relative">
              <Lock className="absolute left-3 top-3 text-gray-400" size={20} />
              <input type="password" placeholder="Password" required className="w-full pl-10 pr-4 py-2 border rounded-lg focus:ring-2 focus:ring-brand-500 outline-none" onChange={e => setFormData({...formData, password: e.target.value})} />
            </div>

            <button type="submit" disabled={loading} className="w-full btn-modern flex items-center justify-center gap-2 mt-6">
              {loading ? 'Processing...' : (isLogin ? 'Sign In' : 'Create Account')}
              {!loading && <ArrowRight size={18} />}
            </button>
          </form>

          <div className="mt-6 text-center">
            <button onClick={() => setIsLogin(!isLogin)} className="text-brand-600 hover:text-brand-700 font-medium text-sm transition-colors">
              {isLogin ? "Don't have an account? Register" : "Already have an account? Sign In"}
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );
}