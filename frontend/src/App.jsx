import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Navbar from './components/Navbar';
import ResumeUpload from './pages/ResumeUpload';
import SkillGap from './pages/SkillGap';
import Roadmap from './pages/Roadmap';
import Interview from './pages/Interview';

function PrivateRoute({ children }) {
  const token = localStorage.getItem('token');
  return token ? children : <Navigate to="/login" />;
}

function App() {
  return (
    <Router>
      <div className="min-h-screen flex flex-col bg-gray-50">
        <Routes>
          <Route path="/login" element={<Login />} />
          
          <Route path="/*" element={
            <PrivateRoute>
              <Navbar />
              <main className="flex-1 w-full max-w-7xl mx-auto p-4 sm:p-6 lg:p-8">
                <Routes>
                  <Route path="/dashboard" element={<Dashboard />} />
                  <Route path="/resume" element={<ResumeUpload />} />
                  <Route path="/gap" element={<SkillGap />} />
                  <Route path="/roadmap" element={<Roadmap />} />
                  <Route path="/interview" element={<Interview />} /> 
                  <Route path="*" element={<Navigate to="/dashboard" />} />
                </Routes>
              </main>
            </PrivateRoute>
          } />
        </Routes>
      </div>
    </Router>
  );
}

export default App;