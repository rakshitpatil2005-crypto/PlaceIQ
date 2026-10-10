import { lazy, Suspense, useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Navbar from './components/Navbar';
import ResumeUpload from './pages/ResumeUpload';
import SkillGap from './pages/SkillGap';
import Roadmap from './pages/Roadmap';
import Interview from './pages/Interview';
import Readiness from './pages/Readiness';
import Premium from './pages/Premium';
const Learning = lazy(() => import('./pages/Learning'));
const Practice = lazy(() => import('./pages/Practice'));
const Assessment = lazy(() => import('./pages/Assessment'));
const Mastery = lazy(() => import('./pages/Mastery'));
const PlacementDashboard = lazy(() => import('./pages/PlacementDashboard'));

function PrivateRoute({ children }) {
  const token = localStorage.getItem('token');
  return token ? children : <Navigate to="/login" />;
}

function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
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
                <div className={`app-layout ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
                  <Navbar collapsed={sidebarCollapsed} onCollapsedChange={setSidebarCollapsed} />
                  <main className="app-main">
                    <div className="content-shell">
                      <Routes>
                        <Route path="/dashboard" element={<Dashboard />} />
                        <Route path="/resume" element={<ResumeUpload />} />
                        <Route path="/gap" element={<SkillGap />} />
                        <Route path="/roadmap" element={<Roadmap />} />
                        <Route
                          path="/learn"
                          element={
                            <Suspense fallback={<div className="panel-card text-center text-slate-500">Loading skill learning...</div>}>
                              <Learning />
                            </Suspense>
                          }
                        />
                        <Route
                          path="/practice/:sessionId"
                          element={
                            <Suspense fallback={<div className="panel-card text-center text-slate-500">Loading practice...</div>}>
                              <Practice />
                            </Suspense>
                          }
                        />
                        <Route
                          path="/assessment/:assessmentId"
                          element={
                            <Suspense fallback={<div className="panel-card text-center text-slate-500">Loading assessment...</div>}>
                              <Assessment />
                            </Suspense>
                          }
                        />
                        <Route
                          path="/mastery"
                          element={
                            <Suspense fallback={<div className="panel-card text-center text-slate-500">Loading skill mastery...</div>}>
                              <Mastery />
                            </Suspense>
                          }
                        />
                        <Route path="/interview" element={<Interview />} />
                        <Route path="/readiness" element={<Readiness />} />
                        <Route path="/premium" element={<Premium />} />
                        <Route
                          path="/placement"
                          element={
                            <Suspense fallback={<div className="panel-card text-center text-slate-500">Loading placement-cell analytics...</div>}>
                              <PlacementDashboard />
                            </Suspense>
                          }
                        />
                        <Route
                          path="/placement/students/:studentId"
                          element={
                            <Suspense fallback={<div className="panel-card text-center text-slate-500">Loading placement-cell analytics...</div>}>
                              <PlacementDashboard />
                            </Suspense>
                          }
                        />
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