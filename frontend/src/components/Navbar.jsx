import { Link, useLocation, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { LayoutDashboard, FileText, Target, Map, MessagesSquare, LogOut, GraduationCap, Sparkles, Award } from 'lucide-react';

export default function Navbar() {
  const location = useLocation();
  const navigate = useNavigate();

  const handleLogout = () => {
    localStorage.removeItem('token');
    navigate('/login');
  };

  const navItems = [
    { path: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
    { path: '/resume', icon: FileText, label: 'Resume' },
    { path: '/gap', icon: Target, label: 'Skill Gap' },
    { path: '/roadmap', icon: Map, label: 'Roadmap' },
    { path: '/mastery', icon: Award, label: 'Skill Mastery' },
    { path: '/interview', icon: MessagesSquare, label: 'Interview' },
    { path: '/readiness', icon: Sparkles, label: 'Readiness' },
  ];

  return (
    <nav className="topbar">
      <div className="topbar-inner">
        <div className="brand-wrap">
          <div className="brand-mark">
            <GraduationCap size={22} />
          </div>
          <div>
            <div className="brand-text">PlaceIQ</div>
            <div className="brand-subtext">Career intelligence</div>
          </div>
        </div>

        <div className="nav-items desktop-nav">
          {navItems.map((item) => {
            const isActive = location.pathname === item.path;
            const Icon = item.icon;
            return (
              <Link key={item.path} to={item.path} className={`nav-link ${isActive ? 'active' : ''}`}>
                <Icon size={18} />
                <span>{item.label}</span>
                {isActive && <motion.span layoutId="nav-pill" className="nav-pill" />}
              </Link>
            );
          })}
        </div>

        <div className="nav-actions">
          <div className="status-chip">
            <Sparkles size={14} />
            <span>Premium plan</span>
          </div>
          <button onClick={handleLogout} className="logout-button" aria-label="Logout">
            <LogOut size={18} />
          </button>
        </div>
      </div>
    </nav>
  );
}