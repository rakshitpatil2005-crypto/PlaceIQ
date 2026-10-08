import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Navbar from './components/Navbar';
import ResumeUpload from './pages/ResumeUpload';
import SkillGap from './pages/SkillGap';
import Roadmap from './pages/Roadmap';
import Interview from './pages/Interview';
import Readiness from './pages/Readiness';

function PrivateRoute({ children }) {
  const token = localStorage.getItem('token');
  return token ? children : <Navigate to="/login" />;
}

function App() {
  return (
    <Router>
      <div className="app-shell">
        <div className="orb orb-one" />
        <div className="orb orb-two" />

        <Routes>
          <Route path="/login" element={<Login />} />

          <Route
            path="/*"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navbar />
                  <main className="app-main">
                    <div className="content-shell">
                      <Routes>
                        <Route path="/dashboard" element={<Dashboard />} />
                        <Route path="/resume" element={<ResumeUpload />} />
                        <Route path="/gap" element={<SkillGap />} />
                        <Route path="/roadmap" element={<Roadmap />} />
                        <Route path="/interview" element={<Interview />} />
                        <Route path="/readiness" element={<Readiness />} />
                        <Route path="*" element={<Navigate to="/dashboard" />} />
                      </Routes>
                    </div>
                  </main>
                </div>
              </PrivateRoute>
            }
          />
        </Routes>
      </div>
    </Router>
  );
}

export default App;