import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  ChevronLeft, ChevronRight, GraduationCap, LogOut, Menu, Sparkles,
} from 'lucide-react';
import api from '../api';
import { getNavigationItems } from '../utils/placementDashboard';

export default function Navbar({ collapsed, onCollapsedChange }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [plan, setPlan] = useState(null);
  const [role, setRole] = useState(null);
  const [mobileOpenPath, setMobileOpenPath] = useState(null);
  const mobileOpen = mobileOpenPath === location.pathname;
  const navItems = getNavigationItems(role);

  useEffect(() => {
    let active = true;
    api.get('/auth/me')
      .then(({ data }) => {
        if (active) setRole(data.role || null);
      })
      .catch((error) => {
        console.error('Unable to load the user role for placement navigation.', error);
        if (active) setRole(null);
      });
    api.get('/premium/plan')
      .then(({ data }) => {
        if (active) setPlan(data.plan === 'premium' ? 'premium' : 'free');
      })
      .catch(() => {
        if (active) setPlan(null);
      });
    return () => { active = false; };
  }, []);

  const handleLogout = () => {
    localStorage.removeItem('token');
    navigate('/login');
  };

  const activePath = (path) => (
    location.pathname === path
    || (path === '/placement' && location.pathname.startsWith('/placement/students/'))
    || (path === '/learn' && ['/practice/', '/assessment/'].some((prefix) => location.pathname.startsWith(prefix)))
  );

  return (
    <>
      <div className="mobile-sidebar-trigger">
        <div className="mobile-sidebar-brand">
          <span className="brand-mark"><GraduationCap size={19} aria-hidden="true" /></span>
          <span>PlaceIQ</span>
        </div>
        <button
          type="button"
          className="mobile-menu-button"
          aria-label="Open navigation menu"
          aria-expanded={mobileOpen}
          aria-controls="main-sidebar"
          onClick={() => setMobileOpenPath(location.pathname)}
        >
          <Menu size={20} aria-hidden="true" />
        </button>
      </div>

      {mobileOpen && (
        <button
          type="button"
          className="sidebar-overlay"
          aria-label="Close navigation menu"
          onClick={() => setMobileOpenPath(null)}
        />
      )}

      <aside
        className={`sidebar ${collapsed ? 'collapsed' : ''} ${mobileOpen ? 'mobile-open' : ''}`}
        id="main-sidebar"
        aria-label="Main navigation"
        onKeyDown={(event) => {
          if (event.key === 'Escape') setMobileOpenPath(null);
        }}
      >
        <div className="sidebar-brand">
          <span className="brand-mark"><GraduationCap size={21} aria-hidden="true" /></span>
          <div className="brand-copy">
            <div className="brand-text">PlaceIQ</div>
            <div className="brand-subtext">Career intelligence</div>
          </div>
        </div>

        <p className="sidebar-section-label">Workspace</p>
        <nav className="sidebar-nav" aria-label="Workspace">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = activePath(item.path);
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`sidebar-link ${active ? 'active' : ''}`}
                aria-current={active ? 'page' : undefined}
                aria-label={item.label}
                title={collapsed ? item.label : undefined}
                onClick={() => setMobileOpenPath(null)}
              >
                <span className="sidebar-link-icon"><Icon size={19} aria-hidden="true" /></span>
                <span className="sidebar-link-label">{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="sidebar-bottom">
          <Link
            to="/premium"
            className="sidebar-plan"
            aria-label={`Current plan: ${plan || 'unavailable'}`}
            title={collapsed ? `Current plan: ${plan || 'unavailable'}` : undefined}
            onClick={() => setMobileOpenPath(null)}
          >
            <Sparkles size={18} aria-hidden="true" />
            <span className="sidebar-bottom-label">
              {plan === 'premium' ? 'Premium access' : plan === 'free' ? 'Core plan' : 'Plan unavailable'}
            </span>
          </Link>
          <button
            type="button"
            className="sidebar-control sidebar-collapse"
            aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}
            title={collapsed ? 'Expand navigation' : 'Collapse navigation'}
            onClick={() => onCollapsedChange(!collapsed)}
          >
            {collapsed ? <ChevronRight size={18} aria-hidden="true" /> : <ChevronLeft size={18} aria-hidden="true" />}
            <span className="sidebar-bottom-label">{collapsed ? 'Expand sidebar' : 'Collapse sidebar'}</span>
          </button>
          <button
            type="button"
            className="sidebar-control"
            aria-label="Logout"
            title={collapsed ? 'Logout' : undefined}
            onClick={handleLogout}
          >
            <LogOut size={18} aria-hidden="true" />
            <span className="sidebar-bottom-label">Log out</span>
          </button>
        </div>
      </aside>
    </>
  );
}
